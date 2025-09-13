"""
Test suite for graceful shutdown and memory monitoring functionality.

These tests validate signal handling for graceful server shutdown and
memory monitoring capabilities for detecting resource leaks during
CIDX server operations.
"""

import asyncio
import signal
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from code_indexer.server.repositories.resource_manager import (
    GracefulShutdownHandler,
    MemoryMonitor,
    ResourceManager,
    MemoryLeakWarning,
)


class TestGracefulShutdownHandler:
    """
    Test graceful shutdown signal handling for CIDX server.

    These tests validate proper signal handling, cleanup callback execution,
    timeout handling, and graceful termination of active operations.
    """

    def test_graceful_shutdown_handler_initialization(self):
        """Test GracefulShutdownHandler initialization with proper defaults."""
        handler = GracefulShutdownHandler()

        # Should initialize with proper defaults
        assert handler.shutdown_timeout == 30.0  # 30 seconds default
        assert handler.shutdown_requested is False
        assert len(handler.cleanup_callbacks) == 0
        assert len(handler.async_cleanup_callbacks) == 0

    def test_graceful_shutdown_handler_custom_timeout(self):
        """Test GracefulShutdownHandler with custom shutdown timeout."""
        handler = GracefulShutdownHandler(shutdown_timeout=60.0)

        assert handler.shutdown_timeout == 60.0
        assert handler.shutdown_requested is False

    def test_register_signal_handlers(self):
        """Test signal handler registration for SIGTERM and SIGINT."""
        handler = GracefulShutdownHandler()

        with patch("signal.signal") as mock_signal:
            handler.register_handlers()

            # Should register both SIGTERM and SIGINT handlers
            expected_calls = [
                call(signal.SIGTERM, handler._signal_handler),
                call(signal.SIGINT, handler._signal_handler),
            ]
            mock_signal.assert_has_calls(expected_calls, any_order=True)

    def test_register_cleanup_callback(self):
        """Test registering synchronous cleanup callbacks."""
        handler = GracefulShutdownHandler()

        def cleanup_func1():
            pass

        def cleanup_func2():
            pass

        handler.register_cleanup_callback(cleanup_func1)
        handler.register_cleanup_callback(cleanup_func2)

        assert len(handler.cleanup_callbacks) == 2
        assert cleanup_func1 in handler.cleanup_callbacks
        assert cleanup_func2 in handler.cleanup_callbacks

    def test_register_async_cleanup_callback(self):
        """Test registering asynchronous cleanup callbacks."""
        handler = GracefulShutdownHandler()

        async def async_cleanup1():
            pass

        async def async_cleanup2():
            pass

        handler.register_async_cleanup_callback(async_cleanup1)
        handler.register_async_cleanup_callback(async_cleanup2)

        assert len(handler.async_cleanup_callbacks) == 2
        assert async_cleanup1 in handler.async_cleanup_callbacks
        assert async_cleanup2 in handler.async_cleanup_callbacks

    def test_signal_handler_execution_sync_callbacks(self):
        """Test signal handler executes synchronous cleanup callbacks."""
        handler = GracefulShutdownHandler()

        cleanup_results = []

        def cleanup1():
            cleanup_results.append("cleanup1_executed")

        def cleanup2():
            cleanup_results.append("cleanup2_executed")

        handler.register_cleanup_callback(cleanup1)
        handler.register_cleanup_callback(cleanup2)

        # Simulate SIGTERM signal
        handler._signal_handler(signal.SIGTERM, None)

        # Should have executed both callbacks
        assert "cleanup1_executed" in cleanup_results
        assert "cleanup2_executed" in cleanup_results
        assert handler.shutdown_requested is True

    def test_signal_handler_execution_async_callbacks(self):
        """Test signal handler executes asynchronous cleanup callbacks."""
        handler = GracefulShutdownHandler()

        async_cleanup_results = []

        async def async_cleanup1():
            await asyncio.sleep(0.01)
            async_cleanup_results.append("async_cleanup1_executed")

        async def async_cleanup2():
            await asyncio.sleep(0.01)
            async_cleanup_results.append("async_cleanup2_executed")

        handler.register_async_cleanup_callback(async_cleanup1)
        handler.register_async_cleanup_callback(async_cleanup2)

        # Simulate SIGINT signal
        handler._signal_handler(signal.SIGINT, None)

        # Give time for async callbacks to complete
        time.sleep(0.1)

        # Should have executed both async callbacks
        assert "async_cleanup1_executed" in async_cleanup_results
        assert "async_cleanup2_executed" in async_cleanup_results
        assert handler.shutdown_requested is True

    def test_cleanup_timeout_handling(self):
        """Test that cleanup respects timeout and doesn't hang indefinitely."""
        handler = GracefulShutdownHandler(shutdown_timeout=0.5)  # 500ms timeout

        cleanup_started = []
        cleanup_completed = []

        def fast_cleanup():
            cleanup_started.append("fast_cleanup_started")
            time.sleep(0.1)  # Quick cleanup
            cleanup_completed.append("fast_cleanup_completed")

        def slow_cleanup():
            cleanup_started.append("slow_cleanup_started")
            time.sleep(2.0)  # Slow cleanup that exceeds timeout
            cleanup_completed.append("slow_cleanup_completed")

        handler.register_cleanup_callback(fast_cleanup)
        handler.register_cleanup_callback(slow_cleanup)

        start_time = time.time()
        handler._signal_handler(signal.SIGTERM, None)
        end_time = time.time()

        # Should complete within timeout bounds
        elapsed_time = end_time - start_time
        assert elapsed_time < 1.0  # Should not wait for slow cleanup

        # Fast cleanup should complete, slow cleanup may not
        assert "fast_cleanup_started" in cleanup_started
        assert "fast_cleanup_completed" in cleanup_completed
        assert "slow_cleanup_started" in cleanup_started
        # slow_cleanup_completed may or may not be present due to timeout

    def test_exception_handling_in_cleanup_callbacks(self):
        """Test that exceptions in cleanup callbacks don't prevent other cleanups."""
        handler = GracefulShutdownHandler()

        cleanup_results = []

        def failing_cleanup():
            cleanup_results.append("failing_cleanup_started")
            raise Exception("Cleanup failed")

        def working_cleanup1():
            cleanup_results.append("working_cleanup1_executed")

        def working_cleanup2():
            cleanup_results.append("working_cleanup2_executed")

        handler.register_cleanup_callback(working_cleanup1)
        handler.register_cleanup_callback(failing_cleanup)
        handler.register_cleanup_callback(working_cleanup2)

        # Should not raise exception despite failing cleanup
        handler._signal_handler(signal.SIGTERM, None)

        # Working cleanups should still execute
        assert "working_cleanup1_executed" in cleanup_results
        assert "working_cleanup2_executed" in cleanup_results
        assert "failing_cleanup_started" in cleanup_results
        assert handler.shutdown_requested is True

    def test_multiple_signal_handling(self):
        """Test handling multiple signals (should only execute cleanup once)."""
        handler = GracefulShutdownHandler()

        cleanup_count = []

        def cleanup_func():
            cleanup_count.append("cleanup_executed")

        handler.register_cleanup_callback(cleanup_func)

        # Send multiple signals
        handler._signal_handler(signal.SIGTERM, None)
        handler._signal_handler(signal.SIGINT, None)
        handler._signal_handler(signal.SIGTERM, None)

        # Cleanup should only execute once
        assert len(cleanup_count) == 1
        assert handler.shutdown_requested is True

    def test_resource_manager_integration_with_shutdown(self):
        """Test GracefulShutdownHandler integration with ResourceManager."""
        handler = GracefulShutdownHandler()
        resource_manager = ResourceManager()

        # Mock resources managed by ResourceManager
        temp_file = tempfile.NamedTemporaryFile(mode="w")
        mock_connection = MagicMock()
        temp_dir = tempfile.mkdtemp()

        def cleanup_resources():
            resource_manager.track_file_handle(temp_file)
            resource_manager.track_database_connection(mock_connection, "test_db")
            resource_manager.track_temp_file(Path(temp_dir))

            # Trigger ResourceManager cleanup
            asyncio.run(resource_manager.cleanup_all())

        handler.register_cleanup_callback(cleanup_resources)

        # Simulate shutdown signal
        handler._signal_handler(signal.SIGTERM, None)

        # Resources should be cleaned up
        assert temp_file.closed
        mock_connection.close.assert_called_once()
        assert not Path(temp_dir).exists()
        assert handler.shutdown_requested is True


class TestMemoryMonitor:
    """
    Test memory monitoring functionality for detecting resource leaks.

    These tests validate memory baseline capture, growth detection,
    leak warning generation, and garbage collection triggering.
    """

    def test_memory_monitor_initialization(self):
        """Test MemoryMonitor initialization and baseline capture."""
        monitor = MemoryMonitor()

        # Should capture baseline memory on initialization
        assert monitor.baseline_memory_mb is not None
        assert monitor.baseline_memory_mb > 0
        assert isinstance(monitor.baseline_memory_mb, (int, float))

    def test_memory_monitor_custom_leak_threshold(self):
        """Test MemoryMonitor with custom leak detection threshold."""
        monitor = MemoryMonitor(leak_threshold_mb=100)

        assert monitor.leak_threshold_mb == 100
        assert monitor.baseline_memory_mb is not None

    def test_get_current_memory_usage(self):
        """Test current memory usage measurement."""
        monitor = MemoryMonitor()

        current_memory = monitor.get_current_memory_mb()

        assert current_memory is not None
        assert current_memory > 0
        assert isinstance(current_memory, (int, float))

        # Current memory should be reasonably close to baseline
        memory_diff = abs(current_memory - monitor.baseline_memory_mb)
        assert memory_diff < 2000  # Within 2GB (reasonable for test environment)

    def test_memory_growth_calculation(self):
        """Test memory growth calculation from baseline."""
        monitor = MemoryMonitor()

        # Mock current memory higher than baseline
        baseline = monitor.baseline_memory_mb
        mock_current = baseline + 50  # 50MB growth

        with patch.object(monitor, "get_current_memory_mb", return_value=mock_current):
            growth = monitor.get_memory_growth_mb()
            assert growth == 50

    def test_memory_growth_negative_growth(self):
        """Test memory growth calculation when memory usage decreases."""
        monitor = MemoryMonitor()

        # Mock current memory lower than baseline
        baseline = monitor.baseline_memory_mb
        mock_current = baseline - 20  # 20MB decrease

        with patch.object(monitor, "get_current_memory_mb", return_value=mock_current):
            growth = monitor.get_memory_growth_mb()
            assert growth == -20

    def test_memory_leak_detection_no_leak(self):
        """Test memory leak detection when memory usage is within threshold."""
        monitor = MemoryMonitor(leak_threshold_mb=100)

        # Mock memory usage within threshold
        baseline = monitor.baseline_memory_mb
        mock_current = baseline + 50  # 50MB growth (within 100MB threshold)

        with patch.object(monitor, "get_current_memory_mb", return_value=mock_current):
            warnings = monitor.check_for_memory_leaks()

            # Should not generate warnings
            assert isinstance(warnings, list)
            assert len(warnings) == 0

    def test_memory_leak_detection_with_leak(self):
        """Test memory leak detection when memory usage exceeds threshold."""
        monitor = MemoryMonitor(leak_threshold_mb=50)

        # Mock memory usage exceeding threshold
        baseline = monitor.baseline_memory_mb
        mock_current = baseline + 100  # 100MB growth (exceeds 50MB threshold)

        with patch.object(monitor, "get_current_memory_mb", return_value=mock_current):
            warnings = monitor.check_for_memory_leaks()

            # Should generate warning
            assert isinstance(warnings, list)
            assert len(warnings) > 0

            warning_text = str(warnings[0]).lower()
            assert "memory" in warning_text
            assert "increased" in warning_text or "growth" in warning_text

    def test_memory_leak_detection_multiple_thresholds(self):
        """Test memory leak detection with multiple severity levels."""
        monitor = MemoryMonitor(leak_threshold_mb=50)

        # Test different memory growth levels
        baseline = monitor.baseline_memory_mb

        # Moderate growth (just above threshold)
        with patch.object(monitor, "get_current_memory_mb", return_value=baseline + 75):
            moderate_warnings = monitor.check_for_memory_leaks()
            assert len(moderate_warnings) > 0

        # Severe growth (well above threshold)
        with patch.object(
            monitor, "get_current_memory_mb", return_value=baseline + 200
        ):
            severe_warnings = monitor.check_for_memory_leaks()
            assert len(severe_warnings) > 0

    def test_force_garbage_collection(self):
        """Test forced garbage collection functionality."""
        monitor = MemoryMonitor()

        with patch("gc.collect") as mock_gc_collect:
            monitor.force_garbage_collection()

            # Should call garbage collection
            mock_gc_collect.assert_called_once()

    def test_memory_statistics_collection(self):
        """Test comprehensive memory statistics collection."""
        monitor = MemoryMonitor()

        stats = monitor.get_memory_statistics()

        # Should return dictionary with key memory metrics
        assert isinstance(stats, dict)

        required_keys = [
            "current_memory_mb",
            "baseline_memory_mb",
            "memory_growth_mb",
            "process_memory_percent",
        ]

        for key in required_keys:
            assert key in stats
            assert isinstance(stats[key], (int, float))

    def test_memory_statistics_with_leak_warnings(self):
        """Test memory statistics include leak warnings when applicable."""
        monitor = MemoryMonitor(leak_threshold_mb=30)

        # Mock memory usage exceeding threshold
        baseline = monitor.baseline_memory_mb
        mock_current = baseline + 50

        with patch.object(monitor, "get_current_memory_mb", return_value=mock_current):
            stats = monitor.get_memory_statistics()

            # Should include leak warnings in statistics
            assert "leak_warnings" in stats
            assert isinstance(stats["leak_warnings"], list)
            assert len(stats["leak_warnings"]) > 0

    def test_memory_monitor_psutil_process_info(self):
        """Test memory monitoring using psutil process information."""
        monitor = MemoryMonitor()

        with patch("psutil.Process") as mock_process_class:
            mock_process = MagicMock()
            mock_process.memory_info.return_value = MagicMock(
                rss=100 * 1024 * 1024
            )  # 100MB
            mock_process.memory_percent.return_value = 5.5  # 5.5%
            mock_process_class.return_value = mock_process

            # Get memory using psutil
            current_memory = monitor.get_current_memory_mb()
            process_percent = monitor.get_process_memory_percent()

            assert current_memory == 100  # 100MB
            assert process_percent == 5.5

    def test_memory_baseline_reset(self):
        """Test memory baseline reset functionality."""
        monitor = MemoryMonitor()

        # Simulate memory change and reset baseline
        time.sleep(0.01)  # Small delay to potentially change memory
        monitor.reset_baseline()

        new_baseline = monitor.baseline_memory_mb

        # New baseline should be captured
        assert new_baseline is not None
        assert isinstance(new_baseline, (int, float))
        # May or may not be different from original depending on system


class TestMemoryLeakWarning:
    """
    Test MemoryLeakWarning data structure and formatting.

    These tests validate the structure and presentation of memory leak warnings.
    """

    def test_memory_leak_warning_creation(self):
        """Test MemoryLeakWarning creation with proper attributes."""
        warning = MemoryLeakWarning(
            growth_mb=75,
            current_mb=250,
            baseline_mb=175,
            threshold_mb=50,
            message="Memory usage increased by 75MB",
        )

        assert warning.growth_mb == 75
        assert warning.current_mb == 250
        assert warning.baseline_mb == 175
        assert warning.threshold_mb == 50
        assert warning.message == "Memory usage increased by 75MB"

    def test_memory_leak_warning_string_representation(self):
        """Test MemoryLeakWarning string formatting."""
        warning = MemoryLeakWarning(
            growth_mb=100,
            current_mb=300,
            baseline_mb=200,
            threshold_mb=75,
            message="Significant memory growth detected",
        )

        warning_str = str(warning)

        # Should include key information in string representation
        assert "100" in warning_str  # growth
        assert "300" in warning_str  # current
        assert "200" in warning_str  # baseline
        assert "memory" in warning_str.lower()

    def test_memory_leak_warning_severity_classification(self):
        """Test memory leak warning severity classification."""
        # Moderate warning
        moderate_warning = MemoryLeakWarning(
            growth_mb=60,
            current_mb=210,
            baseline_mb=150,
            threshold_mb=50,
            message="Moderate memory growth",
        )

        assert moderate_warning.get_severity() == "moderate"

        # Severe warning
        severe_warning = MemoryLeakWarning(
            growth_mb=200,
            current_mb=350,
            baseline_mb=150,
            threshold_mb=50,
            message="Severe memory growth",
        )

        assert severe_warning.get_severity() == "severe"

    def test_memory_leak_warning_recommendations(self):
        """Test memory leak warning recommendations based on severity."""
        warning = MemoryLeakWarning(
            growth_mb=150,
            current_mb=300,
            baseline_mb=150,
            threshold_mb=50,
            message="High memory growth",
        )

        recommendations = warning.get_recommendations()

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        # Should include common leak mitigation recommendations
        rec_text = " ".join(recommendations).lower()
        assert any(
            term in rec_text
            for term in ["garbage", "collection", "cleanup", "resource"]
        )


class TestIntegratedResourceManagerMemoryMonitoring:
    """
    Test integration between ResourceManager and memory monitoring.

    These tests validate that ResourceManager properly integrates
    memory monitoring throughout resource lifecycle operations.
    """

    @pytest.mark.asyncio
    async def test_resource_manager_with_memory_monitoring(self):
        """Test ResourceManager integrated with memory monitoring."""
        async with ResourceManager(enable_memory_monitoring=True) as rm:
            # Should have memory monitoring enabled
            assert rm.memory_monitor is not None
            assert rm.memory_baseline_mb is not None

            # Create resources that consume memory
            temp_files = []
            for i in range(10):
                temp_file = tempfile.NamedTemporaryFile(mode="w")
                temp_file.write("x" * 1000)  # 1KB per file
                temp_files.append(temp_file)
                rm.track_file_handle(temp_file)

            # Memory monitoring should track growth
            current_memory = rm.get_current_memory_mb()
            assert current_memory is not None

        # After context, memory should be released and files closed
        for temp_file in temp_files:
            assert temp_file.closed

    @pytest.mark.asyncio
    async def test_memory_leak_detection_during_operations(self):
        """Test memory leak detection during resource-intensive operations."""
        async with ResourceManager(
            enable_memory_monitoring=True, memory_leak_threshold_mb=10
        ) as rm:
            # Simulate operations that might cause memory leaks
            large_objects = []

            for i in range(100):
                # Create objects that consume memory
                large_obj = "x" * 10000  # 10KB per object
                large_objects.append(large_obj)

                # Track some temporary resources
                if i % 10 == 0:
                    temp_file = tempfile.NamedTemporaryFile(mode="w")
                    rm.track_file_handle(temp_file)

            # Check for memory leaks
            leak_warnings = rm.check_for_memory_leaks()

            # May or may not have leaks depending on system, but should return list
            assert isinstance(leak_warnings, list)

    def test_graceful_shutdown_with_memory_cleanup(self):
        """Test graceful shutdown includes memory cleanup operations."""
        handler = GracefulShutdownHandler()
        memory_monitor = MemoryMonitor()

        cleanup_operations = []

        def memory_cleanup():
            # Force garbage collection
            memory_monitor.force_garbage_collection()
            cleanup_operations.append("gc_forced")

            # Log memory statistics
            stats = memory_monitor.get_memory_statistics()
            cleanup_operations.append(f"memory_logged_{stats['current_memory_mb']}")

        handler.register_cleanup_callback(memory_cleanup)

        # Simulate shutdown
        handler._signal_handler(signal.SIGTERM, None)

        # Memory cleanup should have been performed
        assert "gc_forced" in cleanup_operations
        assert any(op.startswith("memory_logged_") for op in cleanup_operations)
        assert handler.shutdown_requested is True

    @pytest.mark.asyncio
    async def test_resource_manager_memory_monitoring_concurrent_operations(self):
        """Test memory monitoring during concurrent resource operations."""

        async def concurrent_operation(rm: ResourceManager, op_id: int):
            """Simulate concurrent operation with resource usage."""
            # Each operation creates resources
            temp_files = []
            for i in range(5):
                temp_file = tempfile.NamedTemporaryFile(mode="w")
                temp_file.write(f"operation_{op_id}_file_{i}" * 100)
                temp_files.append(temp_file)
                rm.track_file_handle(temp_file)

            await asyncio.sleep(0.1)  # Simulate work
            return f"operation_{op_id}_completed"

        async with ResourceManager(enable_memory_monitoring=True) as rm:
            rm.get_current_memory_mb()

            # Run multiple concurrent operations
            tasks = []
            for i in range(5):
                task = asyncio.create_task(concurrent_operation(rm, i))
                rm.track_background_task(task, f"op_{i}")
                tasks.append(task)

            # Wait for all operations to complete
            results = await asyncio.gather(*tasks)

            # All operations should complete
            assert len(results) == 5
            for i, result in enumerate(results):
                assert result == f"operation_{i}_completed"

            # Memory usage should be tracked
            final_memory = rm.get_current_memory_mb()
            assert final_memory is not None

            # Check for potential memory leaks
            leak_warnings = rm.check_for_memory_leaks()
            assert isinstance(leak_warnings, list)

        # After context, all resources should be cleaned up
