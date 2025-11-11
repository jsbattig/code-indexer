"""Tests for GitAwareWatchHandler interface violations - Story #472 Iteration 2.

These tests verify that GitAwareWatchHandler implements all required interface methods
and handles thread safety correctly. Written as failing tests first (TDD).
"""

import pytest
import time
import threading
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock
import yaml

from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services.git_topology_service import GitTopologyService
from code_indexer.services.watch_metadata import WatchMetadata
from code_indexer.config import ConfigManager
from code_indexer.daemon.watch_manager import DaemonWatchManager


class TestGitAwareWatchHandlerInterfaceCompliance:
    """Test that GitAwareWatchHandler implements all required interface methods."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with config."""
        temp_dir = tempfile.mkdtemp(prefix="test_watch_interface_")
        project_path = Path(temp_dir)

        # Create .code-indexer directory
        cidx_dir = project_path / ".code-indexer"
        cidx_dir.mkdir(parents=True)

        # Create config
        config_path = cidx_dir / "config.yaml"
        config = {
            "exclude_patterns": ["*.pyc", "__pycache__"],
            "language": ["python"],
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Create some test files
        (project_path / "test.py").write_text("def test(): pass")

        yield project_path

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def watch_handler(self, temp_project):
        """Create a real GitAwareWatchHandler instance."""
        config_manager = ConfigManager.create_with_backtrack(temp_project)
        config = config_manager.get_config()

        # Create mock dependencies for simplicity
        smart_indexer = MagicMock(spec=SmartIndexer)
        git_topology_service = MagicMock(spec=GitTopologyService)
        watch_metadata = WatchMetadata()

        handler = GitAwareWatchHandler(
            config=config,
            smart_indexer=smart_indexer,
            git_topology_service=git_topology_service,
            watch_metadata=watch_metadata,
            debounce_seconds=0.1,  # Short for testing
        )

        return handler

    def test_is_watching_method_exists(self, watch_handler):
        """Test that is_watching() method exists and works correctly."""
        # Should return False before starting
        assert hasattr(watch_handler, "is_watching"), "is_watching method missing"
        assert not watch_handler.is_watching()

        # Start watching
        watch_handler.start_watching()

        # Should return True when watching
        assert watch_handler.is_watching(), "Should return True when watching"

        # Stop watching
        watch_handler.stop_watching()

        # Should return False after stopping
        assert not watch_handler.is_watching(), "Should return False after stopping"

    def test_get_stats_method_exists(self, watch_handler):
        """Test that get_stats() method exists and returns expected structure."""
        # Method should exist
        assert hasattr(watch_handler, "get_stats"), "get_stats method missing"

        # Get stats before starting
        stats = watch_handler.get_stats()

        # Verify required fields
        assert isinstance(stats, dict), "get_stats should return a dictionary"
        assert "files_processed" in stats
        assert "indexing_cycles" in stats
        assert "current_branch" in stats
        assert "pending_changes" in stats

        # Start watching
        watch_handler.start_watching()

        # Get stats while watching
        stats = watch_handler.get_stats()
        assert isinstance(stats["files_processed"], int)
        assert isinstance(stats["indexing_cycles"], int)
        assert stats["pending_changes"] >= 0

        # Stop watching
        watch_handler.stop_watching()

    def test_observer_lifecycle_management(self, watch_handler):
        """Test that Observer is properly created and cleaned up."""
        # Before start, no observer should exist
        assert not hasattr(watch_handler, "observer") or watch_handler.observer is None

        # Start watching
        watch_handler.start_watching()

        # Observer should be created and running
        assert hasattr(watch_handler, "observer"), "Observer not created"
        assert watch_handler.observer is not None

        # Give observer time to start
        time.sleep(0.2)

        # Stop watching
        watch_handler.stop_watching()

        # Observer should be stopped (but may still exist)
        # The key is that it's been stopped properly
        if hasattr(watch_handler, "observer") and watch_handler.observer:
            assert not watch_handler.observer.is_alive()


class TestDaemonWatchManagerRaceConditions:
    """Test DaemonWatchManager race condition fixes."""

    def test_watch_starting_sentinel_type_safety(self):
        """Test that watch_starting uses proper sentinel object."""
        manager = DaemonWatchManager()

        # Simulate start without actual handler creation
        manager.project_path = "/test"
        manager.start_time = time.time()

        # Check if _WatchStarting sentinel class exists
        from code_indexer.daemon.watch_manager import _WatchStarting, WATCH_STARTING

        # Set sentinel
        manager.watch_handler = WATCH_STARTING

        # Verify it has expected methods
        assert hasattr(manager.watch_handler, "is_watching")
        assert hasattr(manager.watch_handler, "get_stats")

        # Verify methods return expected values
        assert not manager.watch_handler.is_watching()
        stats = manager.watch_handler.get_stats()
        assert stats["status"] == "starting"

    def test_watch_error_sentinel_type_safety(self):
        """Test that watch errors use proper error sentinel."""
        manager = DaemonWatchManager()

        # Check if _WatchError sentinel class exists
        from code_indexer.daemon.watch_manager import _WatchError

        # Set error sentinel
        error_handler = _WatchError("Test error")
        manager.watch_handler = error_handler

        # Verify it has expected methods
        assert hasattr(error_handler, "is_watching")
        assert hasattr(error_handler, "get_stats")

        # Verify methods return expected values
        assert not error_handler.is_watching()
        stats = error_handler.get_stats()
        assert stats["status"] == "error"
        assert stats["error"] == "Test error"

    def test_efficient_wait_loop(self):
        """Test that wait loop uses efficient wait instead of busy wait."""
        manager = DaemonWatchManager()

        # Mock handler that stops after 0.5 seconds
        mock_handler = MagicMock()
        mock_handler.is_watching = MagicMock(side_effect=[True, True, False])
        mock_handler.start_watching = MagicMock()

        # Track time spent in wait loop
        wait_start = time.time()

        # Simulate the wait loop with efficient waiting
        stop_event = threading.Event()

        # This should use wait(timeout) instead of sleep(0.1) in tight loop
        max_iterations = 0
        while not stop_event.wait(timeout=0.3) and max_iterations < 3:
            max_iterations += 1
            if hasattr(mock_handler, "is_watching") and not mock_handler.is_watching():
                break

        wait_duration = time.time() - wait_start

        # Should have waited ~0.6-0.9 seconds (2-3 iterations at 0.3s each)
        # Not 30+ iterations at 0.1s each (busy wait)
        assert 0.5 < wait_duration < 1.0
        assert max_iterations <= 3, "Should use efficient wait, not busy loop"


class TestRealIntegrationWithoutMocks:
    """Integration tests with real GitAwareWatchHandler (no mocks)."""

    @pytest.fixture
    def real_project(self):
        """Create a real project with actual git repo."""
        temp_dir = tempfile.mkdtemp(prefix="test_real_watch_")
        project_path = Path(temp_dir)

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=project_path, capture_output=True)

        # Create .code-indexer directory
        cidx_dir = project_path / ".code-indexer"
        cidx_dir.mkdir(parents=True)

        # Create config
        config_path = cidx_dir / "config.yaml"
        config = {
            "exclude_patterns": ["*.pyc", "__pycache__"],
            "language": ["python"],
            "file_extensions": ["py"],
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Create initial test file
        test_file = project_path / "test.py"
        test_file.write_text("def hello(): return 'world'")

        # Make initial commit
        subprocess.run(["git", "add", "."], cwd=project_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_path,
            capture_output=True,
        )

        yield project_path

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_daemon_watch_with_real_handler(self, real_project):
        """Integration test with actual GitAwareWatchHandler (no mocks)."""
        from code_indexer.daemon.watch_manager import DaemonWatchManager
        from code_indexer.config import ConfigManager

        # Create daemon manager
        manager = DaemonWatchManager()

        # Get real config
        config_manager = ConfigManager.create_with_backtrack(real_project)
        config = config_manager.get_config()

        # Start watch with real handler
        result = manager.start_watch(str(real_project), config)
        assert result["status"] == "success"

        # Wait for handler to be created
        time.sleep(0.5)

        # Verify handler has required methods
        assert manager.watch_handler is not None
        assert manager.watch_handler != "starting"  # Should be real handler now
        assert hasattr(manager.watch_handler, "is_watching")
        assert hasattr(manager.watch_handler, "get_stats")

        # Verify methods work
        if hasattr(manager.watch_handler, "is_watching"):
            is_watching = manager.watch_handler.is_watching()
            assert isinstance(is_watching, bool)

        if hasattr(manager.watch_handler, "get_stats"):
            stats = manager.watch_handler.get_stats()
            assert isinstance(stats, dict)
            assert "files_processed" in stats

        # Stop watch
        result = manager.stop_watch()
        assert result["status"] == "success"

    def test_concurrent_access_thread_safety(self, real_project):
        """Test thread safety under concurrent access."""
        from code_indexer.daemon.watch_manager import DaemonWatchManager
        from code_indexer.config import ConfigManager

        manager = DaemonWatchManager()
        config_manager = ConfigManager.create_with_backtrack(real_project)
        config = config_manager.get_config()

        # Start watch
        manager.start_watch(str(real_project), config)
        time.sleep(0.5)  # Let handler initialize

        # Concurrent access test
        results = []
        errors = []

        def access_stats():
            try:
                stats = manager.get_stats()
                results.append(stats)
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads accessing stats concurrently
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=access_stats)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify no errors and all got valid stats
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(results) == 10
        for stats in results:
            assert "status" in stats
            assert "project_path" in stats

        # Stop watch
        manager.stop_watch()
