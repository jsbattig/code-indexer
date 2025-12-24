"""
Test suite for ResourceManager - comprehensive resource cleanup for CIDX server operations.

This test suite implements Test-Driven Development for repository resource management,
covering file handles, database connections, memory management, and graceful shutdown.
"""

import asyncio
import signal
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from code_indexer.server.repositories.resource_manager import (
    ResourceManager,
    ResourceTracker,
    GracefulShutdownHandler,
    MemoryMonitor,
)


class TestResourceManager:
    """
    Test ResourceManager async context manager for comprehensive resource cleanup.

    These tests validate that ResourceManager properly tracks and cleans up
    all resources during normal operations and error conditions.
    """

    @pytest.mark.asyncio
    async def test_resource_manager_tracks_file_handles(self):
        """Test that ResourceManager properly tracks and closes file handles."""
        async with ResourceManager() as rm:
            # Track file handles
            temp_file1 = tempfile.NamedTemporaryFile(mode="w")
            temp_file2 = tempfile.NamedTemporaryFile(mode="r")

            rm.track_file_handle(temp_file1)
            rm.track_file_handle(temp_file2)

            # Verify files are tracked
            assert len(rm.tracked_files) == 2
            assert temp_file1 in rm.tracked_files
            assert temp_file2 in rm.tracked_files

            # Files should be open at this point
            assert not temp_file1.closed
            assert not temp_file2.closed

        # After context exit, files should be automatically closed
        assert temp_file1.closed
        assert temp_file2.closed

    @pytest.mark.asyncio
    async def test_resource_manager_tracks_database_connections(self):
        """Test that ResourceManager properly tracks database connections."""
        mock_connection1 = MagicMock()
        mock_connection2 = MagicMock()

        async with ResourceManager() as rm:
            rm.track_database_connection(mock_connection1, "user_db")
            rm.track_database_connection(mock_connection2, "job_db")

            # Verify connections are tracked
            assert len(rm.tracked_connections) == 2
            assert ("user_db", mock_connection1) in rm.tracked_connections.items()
            assert ("job_db", mock_connection2) in rm.tracked_connections.items()

        # After context exit, connections should be closed
        mock_connection1.close.assert_called_once()
        mock_connection2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_manager_tracks_temp_files(self):
        """Test that ResourceManager properly cleans up temporary files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path1 = Path(temp_dir) / "temp1.txt"
            temp_path2 = Path(temp_dir) / "temp2.txt"

            async with ResourceManager() as rm:
                # Create temp files
                temp_path1.write_text("test content 1")
                temp_path2.write_text("test content 2")

                rm.track_temp_file(temp_path1)
                rm.track_temp_file(temp_path2)

                # Verify files exist and are tracked
                assert temp_path1.exists()
                assert temp_path2.exists()
                assert len(rm.tracked_temp_files) == 2

            # After context exit, temp files should be deleted
            assert not temp_path1.exists()
            assert not temp_path2.exists()

    @pytest.mark.asyncio
    async def test_resource_manager_tracks_background_tasks(self):
        """Test that ResourceManager properly cancels background tasks."""

        async def background_task():
            await asyncio.sleep(10)  # Long-running task

        async with ResourceManager() as rm:
            task1 = asyncio.create_task(background_task())
            task2 = asyncio.create_task(background_task())

            rm.track_background_task(task1, "task1")
            rm.track_background_task(task2, "task2")

            # Verify tasks are tracked and running
            assert len(rm.tracked_tasks) == 2
            assert not task1.done()
            assert not task2.done()

        # After context exit, tasks should be cancelled
        assert task1.cancelled()
        assert task2.cancelled()

    @pytest.mark.asyncio
    async def test_resource_manager_cleanup_on_exception(self):
        """Test that ResourceManager cleans up resources even when exceptions occur."""
        temp_file = tempfile.NamedTemporaryFile(mode="w")
        mock_connection = MagicMock()

        with pytest.raises(ValueError, match="Test exception"):
            async with ResourceManager() as rm:
                rm.track_file_handle(temp_file)
                rm.track_database_connection(mock_connection, "test_db")

                # Files and connections should be tracked
                assert len(rm.tracked_files) == 1
                assert len(rm.tracked_connections) == 1

                raise ValueError("Test exception")

        # Even with exception, resources should be cleaned up
        assert temp_file.closed
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_manager_concurrent_access_safety(self):
        """Test that ResourceManager handles concurrent resource operations safely."""
        results = []

        async def concurrent_resource_user(rm: ResourceManager, user_id: int):
            temp_file = tempfile.NamedTemporaryFile(mode="w")
            rm.track_file_handle(temp_file)

            # Simulate some work
            await asyncio.sleep(0.1)
            results.append(f"user_{user_id}_completed")

        async with ResourceManager() as rm:
            # Create multiple concurrent tasks accessing the ResourceManager
            tasks = [
                asyncio.create_task(concurrent_resource_user(rm, i)) for i in range(5)
            ]

            await asyncio.gather(*tasks)

            # All users should have completed
            assert len(results) == 5
            for i in range(5):
                assert f"user_{i}_completed" in results

        # All file handles should be closed
        assert len([f for f in rm.tracked_files if not f.closed]) == 0

    @pytest.mark.asyncio
    async def test_resource_manager_cleanup_all_method(self):
        """Test ResourceManager cleanup_all() method for comprehensive resource cleanup."""

        async def background_task():
            await asyncio.sleep(10)

        rm = ResourceManager()

        # Add various resources
        temp_file = tempfile.NamedTemporaryFile(mode="w")
        mock_connection = MagicMock()
        temp_path = Path(tempfile.mktemp())
        temp_path.write_text("test")
        task = asyncio.create_task(background_task())

        await rm.__aenter__()
        try:
            rm.track_file_handle(temp_file)
            rm.track_database_connection(mock_connection, "test_db")
            rm.track_temp_file(temp_path)
            rm.track_background_task(task, "test_task")

            # Verify resources are tracked
            assert len(rm.tracked_files) == 1
            assert len(rm.tracked_connections) == 1
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_tasks) == 1

            # Call cleanup_all explicitly
            await rm.cleanup_all()

            # Verify all resources are cleaned up
            assert temp_file.closed
            mock_connection.close.assert_called_once()
            assert not temp_path.exists()
            assert task.cancelled()

            # Tracked collections should be empty
            assert len(rm.tracked_files) == 0
            assert len(rm.tracked_connections) == 0
            assert len(rm.tracked_temp_files) == 0
            assert len(rm.tracked_tasks) == 0

        finally:
            await rm.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_resource_manager_partial_cleanup_failure_continues(self):
        """Test that ResourceManager continues cleanup even if some resources fail to clean."""
        # Mock a connection that fails to close
        failing_connection = MagicMock()
        failing_connection.close.side_effect = Exception("Connection close failed")

        working_connection = MagicMock()
        temp_file = tempfile.NamedTemporaryFile(mode="w")

        # Should not raise exception despite failing connection cleanup
        async with ResourceManager() as rm:
            rm.track_database_connection(failing_connection, "failing_db")
            rm.track_database_connection(working_connection, "working_db")
            rm.track_file_handle(temp_file)

        # Working resources should still be cleaned up
        working_connection.close.assert_called_once()
        assert temp_file.closed

        # Failing connection should have attempted cleanup
        failing_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_manager_memory_baseline_tracking(self):
        """Test that ResourceManager tracks memory usage baseline."""
        async with ResourceManager() as rm:
            # Should track initial memory baseline
            assert rm.memory_baseline_mb is not None
            assert rm.memory_baseline_mb > 0

            # Should be able to get current memory usage
            current_memory = rm.get_current_memory_mb()
            assert current_memory is not None
            assert current_memory > 0


class TestResourceTracker:
    """
    Test ResourceTracker for individual resource type management.

    ResourceTracker should provide specialized tracking for different resource types.
    """

    def test_resource_tracker_file_handle_management(self):
        """Test ResourceTracker for file handle management."""
        tracker = ResourceTracker()

        temp_file1 = tempfile.NamedTemporaryFile(mode="w")
        temp_file2 = tempfile.NamedTemporaryFile(mode="r")

        # Track files
        tracker.track_file_handle(temp_file1)
        tracker.track_file_handle(temp_file2)

        assert len(tracker.file_handles) == 2
        assert not temp_file1.closed
        assert not temp_file2.closed

        # Cleanup files
        tracker.cleanup_file_handles()

        assert temp_file1.closed
        assert temp_file2.closed
        assert len(tracker.file_handles) == 0

    def test_resource_tracker_database_connection_management(self):
        """Test ResourceTracker for database connection management."""
        tracker = ResourceTracker()

        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()

        tracker.track_database_connection(mock_conn1, "db1")
        tracker.track_database_connection(mock_conn2, "db2")

        assert len(tracker.database_connections) == 2

        tracker.cleanup_database_connections()

        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()
        assert len(tracker.database_connections) == 0

    @pytest.mark.asyncio
    async def test_resource_tracker_background_task_management(self):
        """Test ResourceTracker for background task management."""
        tracker = ResourceTracker()

        async def long_task():
            await asyncio.sleep(10)

        task1 = asyncio.create_task(long_task())
        task2 = asyncio.create_task(long_task())

        tracker.track_background_task(task1, "task1")
        tracker.track_background_task(task2, "task2")

        assert len(tracker.background_tasks) == 2
        assert not task1.done()
        assert not task2.done()

        await tracker.cleanup_background_tasks()

        assert task1.cancelled()
        assert task2.cancelled()
        assert len(tracker.background_tasks) == 0

    def test_resource_tracker_temp_file_management(self):
        """Test ResourceTracker for temporary file management."""
        tracker = ResourceTracker()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path1 = Path(temp_dir) / "temp1.txt"
            temp_path2 = Path(temp_dir) / "temp2.txt"

            temp_path1.write_text("content1")
            temp_path2.write_text("content2")

            tracker.track_temp_file(temp_path1)
            tracker.track_temp_file(temp_path2)

            assert len(tracker.temp_files) == 2
            assert temp_path1.exists()
            assert temp_path2.exists()

            tracker.cleanup_temp_files()

            assert not temp_path1.exists()
            assert not temp_path2.exists()
            assert len(tracker.temp_files) == 0


class TestGracefulShutdownHandler:
    """
    Test graceful shutdown signal handling for CIDX server operations.

    These tests validate proper signal handling and graceful resource cleanup
    during server shutdown scenarios.
    """

    def test_graceful_shutdown_handler_signal_registration(self):
        """Test that GracefulShutdownHandler registers signal handlers correctly."""
        handler = GracefulShutdownHandler()

        # Should register SIGTERM and SIGINT handlers
        with patch("signal.signal") as mock_signal:
            handler.register_handlers()

            # Should register both SIGTERM and SIGINT
            expected_calls = [
                call(signal.SIGTERM, handler._signal_handler),
                call(signal.SIGINT, handler._signal_handler),
            ]
            mock_signal.assert_has_calls(expected_calls, any_order=True)

    def test_graceful_shutdown_handler_cleanup_callback(self):
        """Test that shutdown handler calls registered cleanup callbacks."""
        handler = GracefulShutdownHandler()

        cleanup_called = []

        def cleanup_callback():
            cleanup_called.append("cleanup_executed")

        handler.register_cleanup_callback(cleanup_callback)

        # Simulate signal reception
        handler._signal_handler(signal.SIGTERM, None)

        assert "cleanup_executed" in cleanup_called
        assert handler.shutdown_requested

    def test_graceful_shutdown_handler_multiple_callbacks(self):
        """Test that shutdown handler executes multiple cleanup callbacks."""
        handler = GracefulShutdownHandler()

        callback_results = []

        def callback1():
            callback_results.append("callback1")

        def callback2():
            callback_results.append("callback2")

        def callback3():
            callback_results.append("callback3")

        handler.register_cleanup_callback(callback1)
        handler.register_cleanup_callback(callback2)
        handler.register_cleanup_callback(callback3)

        # Simulate shutdown signal
        handler._signal_handler(signal.SIGINT, None)

        # All callbacks should have been executed
        assert "callback1" in callback_results
        assert "callback2" in callback_results
        assert "callback3" in callback_results
        assert len(callback_results) == 3

    def test_graceful_shutdown_handler_timeout_handling(self):
        """Test that shutdown handler skips callbacks that would start after timeout."""
        handler = GracefulShutdownHandler(shutdown_timeout=0.5)  # 0.5 second timeout

        callback_results = []

        def first_callback():
            time.sleep(0.2)  # Takes 0.2s (well within timeout)
            callback_results.append("first_completed")

        def second_callback():
            time.sleep(0.2)  # Takes 0.2s (total would be 0.4s, still within timeout)
            callback_results.append("second_completed")

        def third_callback():
            # This callback would start at 0.4s, which is within the 0.5s timeout
            # But it would complete at 0.6s, exceeding the timeout
            time.sleep(0.2)
            callback_results.append("third_completed")

        def fourth_callback():
            # This callback would start at 0.6s, which exceeds the 0.5s timeout
            # It should be skipped entirely
            callback_results.append("fourth_completed")

        # Register callbacks in order
        handler.register_cleanup_callback(first_callback)
        handler.register_cleanup_callback(second_callback)
        handler.register_cleanup_callback(third_callback)
        handler.register_cleanup_callback(fourth_callback)

        # Simulate shutdown
        start_time = time.time()
        handler._signal_handler(signal.SIGTERM, None)
        end_time = time.time()
        total_time = end_time - start_time

        # First two callbacks should complete (0.2s + 0.2s = 0.4s, within 0.5s timeout)
        assert "first_completed" in callback_results
        assert "second_completed" in callback_results

        # Third and fourth callbacks should be skipped because timeout would be exceeded
        # (they would start at 0.4s and 0.6s respectively, but timeout is 0.5s)
        assert "third_completed" not in callback_results
        assert "fourth_completed" not in callback_results

        # Total time should respect the timeout
        assert total_time >= 0.4  # At least time for first two callbacks
        assert total_time < 0.8  # But not allow all callbacks to complete

    @pytest.mark.asyncio
    async def test_graceful_shutdown_async_resource_cleanup(self):
        """Test graceful shutdown with async resource cleanup."""
        handler = GracefulShutdownHandler()

        async_cleanup_completed = []

        async def async_cleanup():
            await asyncio.sleep(0.1)  # Brief async work
            async_cleanup_completed.append("async_cleanup_done")

        # Register async cleanup
        handler.register_async_cleanup_callback(async_cleanup)

        # Simulate shutdown signal - this schedules async cleanup tasks
        handler._signal_handler(signal.SIGTERM, None)

        # Allow the event loop to process the scheduled async cleanup
        # The call_soon mechanism schedules tasks in the next iteration
        await asyncio.sleep(0.2)

        # Verify async cleanup was executed
        assert "async_cleanup_done" in async_cleanup_completed


class TestMemoryMonitor:
    """
    Test MemoryMonitor for tracking memory usage and detecting leaks.

    These tests validate memory monitoring capabilities and leak detection.
    """

    def test_memory_monitor_baseline_capture(self):
        """Test that MemoryMonitor captures baseline memory usage."""
        monitor = MemoryMonitor()

        # Should capture baseline on initialization
        assert monitor.baseline_memory_mb is not None
        assert monitor.baseline_memory_mb > 0

    def test_memory_monitor_current_usage_measurement(self):
        """Test current memory usage measurement."""
        monitor = MemoryMonitor()

        current_memory = monitor.get_current_memory_mb()
        assert current_memory is not None
        assert current_memory > 0

        # Current memory should be reasonably close to baseline
        assert abs(current_memory - monitor.baseline_memory_mb) < 1000  # Within 1GB

    def test_memory_monitor_growth_detection(self):
        """Test memory growth detection."""
        monitor = MemoryMonitor()
        initial_baseline = monitor.baseline_memory_mb

        # Simulate memory growth
        with patch.object(
            monitor, "get_current_memory_mb", return_value=initial_baseline + 100
        ):
            memory_growth = monitor.get_memory_growth_mb()
            assert memory_growth == 100

    def test_memory_monitor_leak_warning_threshold(self):
        """Test memory leak warning when growth exceeds threshold."""
        monitor = MemoryMonitor(leak_threshold_mb=50)

        # Mock excessive memory usage
        excessive_memory = monitor.baseline_memory_mb + 100  # 100MB over baseline

        with patch.object(
            monitor, "get_current_memory_mb", return_value=excessive_memory
        ):
            leak_warnings = monitor.check_for_memory_leaks()

            # Should detect memory growth exceeding threshold
            assert len(leak_warnings) > 0
            assert "memory usage increased" in str(leak_warnings[0]).lower()

    def test_memory_monitor_force_garbage_collection(self):
        """Test forced garbage collection capability."""
        monitor = MemoryMonitor()

        with patch("gc.collect") as mock_gc_collect:
            monitor.force_garbage_collection()
            mock_gc_collect.assert_called_once()

    def test_memory_monitor_memory_statistics(self):
        """Test comprehensive memory statistics collection."""
        monitor = MemoryMonitor()

        stats = monitor.get_memory_statistics()

        # Should include key memory metrics
        assert "current_memory_mb" in stats
        assert "baseline_memory_mb" in stats
        assert "memory_growth_mb" in stats
        assert "process_memory_percent" in stats

        # All values should be numeric
        assert isinstance(stats["current_memory_mb"], (int, float))
        assert isinstance(stats["baseline_memory_mb"], (int, float))
        assert isinstance(stats["memory_growth_mb"], (int, float))


class TestResourceManagerIntegrationWithExistingOperations:
    """
    Integration tests for ResourceManager with existing CIDX server operations.

    These tests validate that ResourceManager integrates properly with
    repository operations, background jobs, and server lifecycle.
    """

    @pytest.mark.asyncio
    async def test_resource_manager_with_golden_repo_operations(self):
        """Test ResourceManager integration with golden repository operations."""
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )

        # Mock GoldenRepoManager operations
        with patch.object(GoldenRepoManager, "__init__", return_value=None):
            MagicMock()

            async with ResourceManager() as rm:
                # Simulate golden repo operations that create resources
                temp_clone_dir = tempfile.mkdtemp()
                temp_metadata_file = tempfile.NamedTemporaryFile(mode="w")

                # Track resources created during golden repo operations
                rm.track_temp_file(Path(temp_clone_dir))
                rm.track_file_handle(temp_metadata_file)

                # Simulate some repo operations
                assert Path(temp_clone_dir).exists()
                assert not temp_metadata_file.closed

            # After context, resources should be cleaned up
            assert not Path(temp_clone_dir).exists()
            assert temp_metadata_file.closed

    @pytest.mark.asyncio
    async def test_resource_manager_with_background_job_operations(self):
        """Test ResourceManager integration with background job operations."""

        async def mock_repository_sync_job(rm: ResourceManager):
            # Simulate resource creation during background job
            temp_git_dir = tempfile.mkdtemp()
            log_file = tempfile.NamedTemporaryFile(mode="w")

            rm.track_temp_file(Path(temp_git_dir))
            rm.track_file_handle(log_file)

            # Simulate some work
            await asyncio.sleep(0.1)
            return {"success": True, "changes_applied": True}

        async with ResourceManager() as rm:
            result = await mock_repository_sync_job(rm)

            assert result["success"] is True

            # Resources should be tracked
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_files) == 1

        # After context, all resources should be cleaned up
        assert len(rm.tracked_temp_files) == 0
        assert len(rm.tracked_files) == 0

    @pytest.mark.asyncio
    async def test_resource_manager_with_activated_repo_operations(self):
        """Test ResourceManager integration with activated repository operations."""

        MagicMock()

        async with ResourceManager() as rm:
            # Simulate activated repo operations
            user_repo_dir = tempfile.mkdtemp()
            config_file = tempfile.NamedTemporaryFile(mode="w")

            # Track resources from repo activation
            rm.track_temp_file(Path(user_repo_dir))
            rm.track_file_handle(config_file)

            # Simulate repository sync operation
            async def mock_sync_task():
                await asyncio.sleep(0.2)
                return "sync_completed"

            sync_task = asyncio.create_task(mock_sync_task())
            rm.track_background_task(sync_task, "repo_sync")

            # Wait for sync to complete
            sync_result = await sync_task
            assert sync_result == "sync_completed"

        # ResourceManager should clean up all resources
        assert not Path(user_repo_dir).exists()
        assert config_file.closed

    def test_resource_manager_integration_with_server_startup(self):
        """Test ResourceManager integration with server startup and shutdown."""
        # Mock server components
        mock_jwt_manager = MagicMock()
        mock_user_manager = MagicMock()
        mock_background_job_manager = MagicMock()

        # Create graceful shutdown handler
        shutdown_handler = GracefulShutdownHandler()
        ResourceManager()

        def cleanup_server_resources():
            """Cleanup callback for server shutdown."""
            # Close all active connections
            mock_jwt_manager.cleanup()
            mock_user_manager.close_connections()
            mock_background_job_manager.stop_all_jobs()

        shutdown_handler.register_cleanup_callback(cleanup_server_resources)

        # Simulate server shutdown signal
        shutdown_handler._signal_handler(signal.SIGTERM, None)

        # Verify server resources were cleaned up
        assert shutdown_handler.shutdown_requested
        mock_jwt_manager.cleanup.assert_called_once()
        mock_user_manager.close_connections.assert_called_once()
        mock_background_job_manager.stop_all_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_manager_memory_monitoring_during_operations(self):
        """Test memory monitoring during actual repository operations."""
        async with ResourceManager() as rm:
            initial_memory = rm.get_current_memory_mb()

            # Simulate memory-intensive operations
            large_data = []
            for i in range(1000):
                # Create some objects that consume memory
                temp_data = f"data_{i}" * 100
                large_data.append(temp_data)

            # Memory should have increased (allow for small measurement variations)
            current_memory = rm.get_current_memory_mb()
            # Use a small tolerance for memory measurement precision
            assert (
                current_memory >= initial_memory
            )  # May be equal due to GC or measurement precision

            # Force garbage collection
            rm.force_garbage_collection()

            # Check for memory leaks
            memory_warnings = rm.check_for_memory_leaks()

            # Memory warnings should be list (may be empty if no leaks)
            assert isinstance(memory_warnings, list)
