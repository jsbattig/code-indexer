"""Integration tests for daemon watch mode - Story #472.

This module tests the integrated daemon watch mode with DaemonWatchManager,
verifying non-blocking operation and CLI delegation.
"""

import pytest
import threading
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import yaml

from code_indexer.daemon.service import CIDXDaemonService


class TestDaemonWatchIntegration:
    """Integration tests for daemon watch mode."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with config."""
        temp_dir = tempfile.mkdtemp(prefix="test_watch_")
        project_path = Path(temp_dir)

        # Create .code-indexer directory
        cidx_dir = project_path / ".code-indexer"
        cidx_dir.mkdir(parents=True)

        # Create config with daemon enabled
        config_path = cidx_dir / "config.yaml"
        config = {
            "daemon": True,
            "exclude_patterns": ["*.pyc", "__pycache__"],
            "language": ["python"],
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Create some test files
        (project_path / "test.py").write_text("def test(): pass")
        (project_path / "main.py").write_text("print('hello')")

        yield project_path

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def daemon_service(self):
        """Create a daemon service instance."""
        service = CIDXDaemonService()
        yield service

        # Cleanup - stop watch if running
        if service.watch_manager.is_running():
            service.watch_manager.stop_watch()

    def test_daemon_watch_start_non_blocking(self, daemon_service, temp_project):
        """Test that watch_start returns immediately (non-blocking)."""
        # Act - start watch
        start_time = time.time()
        result = daemon_service.exposed_watch_start(str(temp_project))
        elapsed = time.time() - start_time

        # Assert - should return quickly (< 1 second)
        assert elapsed < 1.0, f"Watch start took {elapsed}s, should be < 1s"
        assert result["status"] == "success"
        assert result["message"] == "Watch started in background"

        # Verify watch is running
        status = daemon_service.exposed_watch_status()
        assert status["running"]
        assert status["project_path"] == str(temp_project)

        # Stop watch for cleanup
        daemon_service.exposed_watch_stop(str(temp_project))

    def test_daemon_watch_concurrent_queries(self, daemon_service, temp_project):
        """Test that daemon can handle queries while watch is running."""
        # Start watch
        result = daemon_service.exposed_watch_start(str(temp_project))
        assert result["status"] == "success"

        # Verify daemon can handle other operations concurrently
        # (In real scenario, these would be RPC calls from different threads)

        # Get status while watch is running
        status = daemon_service.exposed_get_status()
        assert "watch_running" in status
        assert status["watch_running"]

        # Ping daemon while watch is running
        ping_result = daemon_service.exposed_ping()
        assert ping_result["status"] == "ok"

        # Get watch status
        watch_status = daemon_service.exposed_watch_status()
        assert watch_status["running"]

        # Stop watch
        stop_result = daemon_service.exposed_watch_stop(str(temp_project))
        assert stop_result["status"] == "success"

    def test_daemon_watch_prevents_duplicate_starts(self, daemon_service, temp_project):
        """Test that daemon prevents duplicate watch starts."""
        # Start first watch
        result1 = daemon_service.exposed_watch_start(str(temp_project))
        assert result1["status"] == "success"

        # Try to start second watch (should fail)
        result2 = daemon_service.exposed_watch_start(str(temp_project))
        assert result2["status"] == "error"
        assert "already running" in result2["message"].lower()

        # Stop watch
        daemon_service.exposed_watch_stop(str(temp_project))

    def test_daemon_watch_graceful_stop(self, daemon_service, temp_project):
        """Test graceful watch stop with statistics."""
        # Start watch
        result = daemon_service.exposed_watch_start(str(temp_project))
        assert result["status"] == "success"

        # Let it run briefly
        time.sleep(0.5)

        # Stop watch
        start_time = time.time()
        stop_result = daemon_service.exposed_watch_stop(str(temp_project))
        elapsed = time.time() - start_time

        # Assert
        assert elapsed < 5.1, f"Stop took {elapsed}s, should be < 5.1s"
        assert stop_result["status"] == "success"
        assert stop_result["message"] == "Watch stopped"

        # Verify watch is stopped
        status = daemon_service.exposed_watch_status()
        assert not status["running"]

    def test_daemon_shutdown_stops_watch(self, daemon_service, temp_project):
        """Test that daemon shutdown properly stops watch."""
        # Start watch
        result = daemon_service.exposed_watch_start(str(temp_project))
        assert result["status"] == "success"

        # Mock os.kill to prevent actual shutdown
        with patch("os.kill"):
            # Shutdown daemon
            shutdown_result = daemon_service.exposed_shutdown()
            assert shutdown_result["status"] == "success"

        # Verify watch was stopped
        assert not daemon_service.watch_manager.is_running()

    def test_watch_manager_thread_lifecycle(self, daemon_service, temp_project):
        """Test watch manager thread lifecycle and cleanup."""
        # Start watch
        result = daemon_service.exposed_watch_start(str(temp_project))
        assert result["status"] == "success"

        # Get thread reference
        watch_thread = daemon_service.watch_manager.watch_thread
        assert watch_thread is not None
        assert watch_thread.is_alive()
        assert watch_thread.daemon  # Should be daemon thread

        # Stop watch
        daemon_service.exposed_watch_stop(str(temp_project))

        # Wait for thread to finish (slightly longer timeout for slower systems)
        watch_thread.join(timeout=8.0)

        # Verify thread is stopped
        assert not watch_thread.is_alive(), "Watch thread did not stop in time"
        assert daemon_service.watch_manager.watch_thread is None

    def test_watch_status_reporting(self, daemon_service, temp_project):
        """Test watch status reporting with uptime and stats."""
        # Start watch
        result = daemon_service.exposed_watch_start(str(temp_project))
        assert result["status"] == "success"

        # Let it run briefly
        time.sleep(0.5)

        # Get detailed status
        status = daemon_service.exposed_get_status()

        # Verify watch-related fields
        assert status["watch_running"]
        assert status["watch_project"] == str(temp_project)
        assert status["watch_uptime_seconds"] > 0
        assert "watch_files_processed" in status

        # Stop watch
        daemon_service.exposed_watch_stop(str(temp_project))
