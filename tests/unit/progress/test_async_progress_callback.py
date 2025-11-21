"""Test async progress callback to eliminate worker thread blocking.

Bug #470: Worker threads block synchronously on Rich terminal I/O during progress
callbacks, causing 10x performance degradation (6.5% thread utilization, 11.6
threads waiting on futex).

This test verifies that progress callbacks execute in <1ms using async queue
pattern instead of blocking on terminal I/O.
"""

import queue
import threading
import time
from unittest.mock import patch

import pytest

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestAsyncProgressCallback:
    """Test async progress callback eliminates worker thread blocking."""

    def test_async_progress_worker_processes_updates(self):
        """Async progress updates are processed by dedicated worker thread.

        This test verifies that async_handle_progress_update actually queues
        updates for processing by a dedicated worker thread, not just a no-op.

        Expected to FAIL initially because async queue infrastructure doesn't exist.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            # Track actual Rich Live updates
            update_count = 0
            original_update = manager.live_component.update

            def counting_update(content):
                nonlocal update_count
                update_count += 1
                original_update(content)

            manager.live_component.update = counting_update

            # Send 10 async updates
            for i in range(10):
                manager.async_handle_progress_update(f"Update {i}")

            # Wait for async worker to process queue
            time.sleep(0.2)

            # Verify updates were actually processed
            assert (
                update_count == 10
            ), f"Expected 10 updates processed, got {update_count}"

        finally:
            manager.stop_display()

    def test_async_progress_callback_nonblocking(self):
        """Async progress callback executes in <1ms using queue pattern.

        This test verifies that after implementing async queue pattern, progress
        callbacks from worker threads complete in <1ms (non-blocking queue.put).

        Expected to FAIL initially because async_handle_progress_update doesn't exist yet.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            # Simulate worker thread making async progress callbacks
            callback_times = []

            def worker_thread_task():
                """Simulate worker thread making async progress updates."""
                for i in range(50):  # More iterations to test throughput
                    start_time = time.time()

                    # Async progress callback using queue (should be <1ms)
                    manager.async_handle_progress_update(
                        f"Progress: {i}/50 files | 5.2 files/s | 128 KB/s"
                    )

                    elapsed_ms = (time.time() - start_time) * 1000
                    callback_times.append(elapsed_ms)

            # Run worker thread
            thread = threading.Thread(target=worker_thread_task)
            thread.start()
            thread.join(timeout=5.0)

            # Verify thread completed
            assert not thread.is_alive(), "Worker thread should complete quickly"

            # Calculate statistics
            avg_callback_time = sum(callback_times) / len(callback_times)
            max_callback_time = max(callback_times)
            p95_callback_time = sorted(callback_times)[int(len(callback_times) * 0.95)]

            # PASS criteria: <1ms average, <5ms p95, <10ms max
            assert (
                avg_callback_time < 1.0
            ), f"Async callback took {avg_callback_time:.2f}ms (avg) - should be <1ms"
            assert (
                p95_callback_time < 5.0
            ), f"Async callback p95 {p95_callback_time:.2f}ms - should be <5ms"
            assert (
                max_callback_time < 10.0
            ), f"Async callback max {max_callback_time:.2f}ms - should be <10ms"

        finally:
            manager.stop_display()
            # Wait for async progress worker to drain queue
            time.sleep(0.1)

    def test_async_progress_worker_shutdown(self):
        """Verify async progress worker thread shuts down cleanly.

        Expected to FAIL initially because stop_display doesn't shutdown worker.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        # Send some updates
        for i in range(5):
            manager.async_handle_progress_update(f"Update {i}")

        # Stop display (should shutdown async worker)
        manager.stop_display()

        # Verify worker thread terminated
        time.sleep(0.2)
        progress_worker_alive = any(
            "progress_worker" in t.name for t in threading.enumerate()
        )
        assert (
            not progress_worker_alive
        ), "Async progress worker should terminate after stop_display()"

    def test_queue_overflow_drops_updates_gracefully(self):
        """Queue overflow should drop updates gracefully without raising queue.Full.

        Issue #2: async_handle_progress_update() uses put_nowait() which raises
        queue.Full when queue is full. This causes crashes during high-throughput
        indexing.

        Expected to FAIL initially: queue.Full exception will be raised.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            # Block worker thread to simulate slow terminal I/O
            manager._shutdown_event.set()  # Stop worker from processing

            # Fill queue beyond capacity (maxsize=100)
            # This MUST NOT raise queue.Full exception
            for i in range(150):  # More than maxsize=100
                try:
                    manager.async_handle_progress_update(f"Update {i}")
                except queue.Full:
                    pytest.fail(
                        f"async_handle_progress_update raised queue.Full at iteration {i}. "
                        "Should drop updates gracefully instead."
                    )

            # Test passes if no exception raised
            # (drops are acceptable for progress updates - better than crashes)

        finally:
            manager._shutdown_event.clear()
            manager.stop_display()

    def test_stop_display_increases_timeout_for_slow_shutdown(self):
        """stop_display should use 2.0s timeout instead of 1.0s.

        Issue #3: 1.0s timeout may be insufficient for worker thread to drain
        queue and shutdown cleanly, causing thread leaks.

        Expected to FAIL initially: Timeout is 1.0s.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        # Queue many updates to simulate slow drain
        for i in range(100):
            manager.async_handle_progress_update(f"Update {i}")

        # Mock join to verify timeout value
        original_join = manager._progress_worker.join
        join_timeout = None

        def mock_join(timeout=None):
            nonlocal join_timeout
            join_timeout = timeout
            original_join(timeout=timeout)

        manager._progress_worker.join = mock_join

        # Stop display
        manager.stop_display()

        # Verify timeout is 2.0s (not 1.0s)
        assert join_timeout is not None, "join() was not called with timeout"
        assert (
            join_timeout >= 2.0
        ), f"Thread join timeout is {join_timeout}s - should be >= 2.0s to prevent thread leaks"

    def test_stop_display_warns_if_thread_doesnt_terminate(self):
        """stop_display should log warning if worker thread doesn't terminate.

        Issue #3: If worker thread doesn't terminate within timeout, should log
        warning instead of silently leaking thread.

        Expected to FAIL initially: No warning logged.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        # Mock join to simulate timeout (thread still alive)

        def mock_join(timeout=None):
            time.sleep(0.01)  # Simulate some time passing

        def mock_is_alive():
            return True  # Simulate thread still alive after join

        manager._progress_worker.join = mock_join
        manager._progress_worker.is_alive = mock_is_alive

        # Capture log warnings
        with patch("code_indexer.progress.progress_display.logging") as mock_logging:
            manager.stop_display()

            # Verify warning was logged
            warning_calls = [
                call
                for call in mock_logging.warning.call_args_list
                if "progress worker" in str(call).lower()
                and "terminate" in str(call).lower()
            ]
            assert (
                len(warning_calls) > 0
            ), "Expected warning log when progress worker thread fails to terminate"

    def test_worker_thread_handles_update_exceptions(self):
        """Worker thread should handle exceptions during live_component.update().

        Issue #4: If live_component.update() raises exception, worker thread dies
        silently, causing all subsequent progress updates to be lost.

        Expected to FAIL initially: Exception kills worker thread.
        """
        from rich.console import Console

        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            # Make live_component.update raise exception
            update_call_count = 0

            def failing_update(content):
                nonlocal update_call_count
                update_call_count += 1
                if update_call_count == 5:
                    raise RuntimeError("Simulated Rich rendering error")

            manager.live_component.update = failing_update

            # Send 10 updates (5th will raise exception)
            for i in range(10):
                manager.async_handle_progress_update(f"Update {i}")

            # Wait for processing
            time.sleep(0.3)

            # Verify worker thread is still alive after exception
            worker_alive = manager._progress_worker.is_alive()
            assert worker_alive, (
                "Worker thread died after exception in live_component.update(). "
                "Should handle exceptions gracefully and continue processing."
            )

            # Verify subsequent updates still processed (after exception)
            assert update_call_count > 5, (
                f"Worker processed only {update_call_count} updates before dying. "
                "Should continue processing after exceptions."
            )

        finally:
            manager.stop_display()
