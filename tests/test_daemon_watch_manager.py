"""Tests for DaemonWatchManager - Story #472.

This module tests the daemon watch manager that enables non-blocking
watch mode in the daemon, allowing concurrent operations while watching
for file changes.
"""

import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from code_indexer.daemon.watch_manager import DaemonWatchManager


class TestDaemonWatchManager:
    """Test suite for DaemonWatchManager."""

    @pytest.fixture
    def manager(self):
        """Create a DaemonWatchManager instance."""
        return DaemonWatchManager()

    def test_initial_state(self, manager):
        """Test manager starts in correct initial state."""
        assert manager.watch_thread is None
        assert manager.watch_handler is None
        assert manager.project_path is None
        assert manager.start_time is None
        assert not manager.is_running()
        stats = manager.get_stats()
        assert stats["status"] == "idle"
        assert stats["project_path"] is None
        assert stats["uptime_seconds"] == 0
        assert stats["files_processed"] == 0

    def test_start_watch_creates_background_thread(self, manager):
        """Test start_watch creates and starts a background thread."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.start_watching = MagicMock()  # Non-blocking mock
            mock_create.return_value = mock_handler

            # Act
            result = manager.start_watch(project_path, config)

            # Assert
            assert result["status"] == "success"
            assert result["message"] == "Watch started in background"
            assert manager.watch_thread is not None
            assert isinstance(manager.watch_thread, threading.Thread)
            assert manager.watch_thread.daemon
            assert manager.watch_thread.is_alive()
            assert manager.project_path == project_path
            assert manager.start_time is not None

            # Wait a bit for the thread to set the handler
            time.sleep(0.2)
            # Handler should be set (either "starting" or the real mock)
            assert manager.watch_handler in ["starting", mock_handler]
            assert manager.is_running()

    def test_start_watch_returns_immediately(self, manager):
        """Test start_watch returns within 1 second (non-blocking)."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        # Mock handler creation to simulate slow operation
        def slow_handler_creation(*args, **kwargs):
            time.sleep(0.1)  # Simulate some work
            mock = MagicMock()
            mock.start_watching = MagicMock()  # Non-blocking
            return mock

        with patch.object(
            manager, "_create_watch_handler", side_effect=slow_handler_creation
        ):
            # Act
            start_time = time.time()
            result = manager.start_watch(project_path, config)
            elapsed = time.time() - start_time

            # Assert - should return immediately, not wait for handler creation
            assert elapsed < 1.0, f"start_watch took {elapsed}s, should be < 1s"
            assert result["status"] == "success"

    def test_start_watch_prevents_duplicate_starts(self, manager):
        """Test that start_watch prevents duplicate watch sessions."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.start_watching = MagicMock()  # Non-blocking mock
            mock_create.return_value = mock_handler

            # Act - start first watch
            result1 = manager.start_watch(project_path, config)
            assert result1["status"] == "success"

            # Wait for thread to start properly
            time.sleep(0.1)

            # Act - try to start second watch
            result2 = manager.start_watch(project_path, config)

            # Assert
            assert result2["status"] == "error"
            assert "already running" in result2["message"].lower()
            assert mock_create.call_count == 1  # Only called once

    def test_stop_watch_graceful_shutdown(self, manager):
        """Test stop_watch performs graceful shutdown within 5 seconds."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.stop_watching = MagicMock()
            mock_handler.get_stats = MagicMock(return_value={"files_processed": 10})
            mock_handler.start_watching = MagicMock()  # Non-blocking mock
            mock_create.return_value = mock_handler

            # Start watch
            manager.start_watch(project_path, config)
            time.sleep(0.1)  # Wait for thread to start
            assert manager.is_running()

            # Act - stop watch
            start_time = time.time()
            result = manager.stop_watch()
            elapsed = time.time() - start_time

            # Assert
            assert elapsed < 5.1, f"stop_watch took {elapsed}s, should be < 5.1s"
            assert result["status"] == "success"
            assert result["message"] == "Watch stopped"
            assert "stats" in result
            assert result["stats"]["files_processed"] == 10
            mock_handler.stop_watching.assert_called_once()

            # Verify cleanup
            assert manager.watch_thread is None
            assert manager.watch_handler is None
            assert manager.project_path is None
            assert manager.start_time is None
            assert not manager.is_running()

    def test_stop_watch_when_not_running(self, manager):
        """Test stop_watch handles case when no watch is running."""
        # Act
        result = manager.stop_watch()

        # Assert
        assert result["status"] == "error"
        assert "not running" in result["message"].lower()

    def test_get_stats_when_running(self, manager):
        """Test get_stats returns correct statistics when watch is running."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.get_stats = MagicMock(
                return_value={"files_processed": 25, "indexing_cycles": 5}
            )
            mock_handler.start_watching = MagicMock()  # Non-blocking
            mock_create.return_value = mock_handler

            # Start watch
            manager.start_watch(project_path, config)
            time.sleep(0.2)  # Wait for thread to start and let some time pass

            # Act
            stats = manager.get_stats()

            # Assert
            assert stats["status"] == "running"
            assert stats["project_path"] == project_path
            assert stats["uptime_seconds"] > 0
            assert stats["files_processed"] == 25
            assert stats["indexing_cycles"] == 5

    def test_thread_safety_concurrent_operations(self, manager):
        """Test thread-safe operations under concurrent access."""
        # Arrange
        results = []
        errors = []

        def try_start(project_path, config):
            try:
                result = manager.start_watch(project_path, config)
                results.append(result)
            except Exception as e:
                errors.append(e)

        def try_stop():
            try:
                result = manager.stop_watch()
                results.append(result)
            except Exception as e:
                errors.append(e)

        def try_get_stats():
            try:
                stats = manager.get_stats()
                results.append(stats)
            except Exception as e:
                errors.append(e)

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.start_watching = MagicMock()  # Non-blocking mock
            mock_create.return_value = mock_handler

            # Act - concurrent operations
            threads = []
            # First test concurrent starts only
            for i in range(5):
                # All try to start the SAME project path to test thread safety
                threads.append(
                    threading.Thread(
                        target=try_start, args=("/test/project", MagicMock())
                    )
                )

            for t in threads:
                t.start()

            for t in threads:
                t.join(timeout=5)

            # Assert
            assert len(errors) == 0, f"Thread safety errors: {errors}"

            # Debug output to understand what's happening
            start_results = [
                r
                for r in results
                if "message" in r
                and ("started" in r["message"] or "already" in r["message"])
            ]
            success_starts = [r for r in start_results if r.get("status") == "success"]
            error_starts = [r for r in start_results if r.get("status") == "error"]

            # Only one start should succeed, rest should fail with "already running"
            assert (
                len(success_starts) <= 1
            ), f"Too many successful starts: {success_starts}"
            assert (
                len(success_starts) + len(error_starts) == 5
            ), f"Expected 5 start attempts, got {len(start_results)}"

            if len(success_starts) == 1:
                # If one succeeded, others should have failed with "already running"
                for error in error_starts:
                    assert "already running" in error["message"].lower()

    def test_watch_handler_error_handling(self, manager):
        """Test proper error handling when watch handler creation fails."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_create.side_effect = Exception("Handler creation failed")

            # Act
            result = manager.start_watch(project_path, config)

            # Assert - start returns success (non-blocking)
            assert result["status"] == "success"

            # Wait for thread to fail and clean up
            time.sleep(0.5)

            # After error, watch should not be running
            assert not manager.is_running()
            assert manager.watch_thread is None
            assert manager.watch_handler is None

    def test_watch_thread_cleanup_on_exception(self, manager):
        """Test that watch thread cleans up properly on exception."""
        # Arrange
        project_path = "/test/project"
        config = MagicMock()

        with patch.object(manager, "_create_watch_handler") as mock_create:
            mock_handler = MagicMock()
            mock_handler.start_watching.side_effect = Exception("Watch failed")
            mock_create.return_value = mock_handler

            # Act
            result = manager.start_watch(project_path, config)
            time.sleep(0.5)  # Let thread fail and clean up

            # Assert
            # Thread should have cleaned up after exception
            assert not manager.is_running()
            stats = manager.get_stats()
            assert stats["status"] == "idle"
