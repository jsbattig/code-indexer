"""
Unit tests for AggregateProgressTracker.
Tests the aggregate progress tracking with rate calculations.
"""

import threading
import time
from unittest.mock import patch

from code_indexer.services.aggregate_progress_tracker import (
    AggregateProgressTracker,
    ProgressMetrics,
)


class TestProgressMetrics:
    """Test ProgressMetrics NamedTuple."""

    def test_progress_metrics_creation(self):
        """Test ProgressMetrics NamedTuple creation."""
        metrics = ProgressMetrics(
            completed_files=50,
            total_files=100,
            progress_percent=50.0,
            files_per_second=2.5,
            kb_per_second=128.0,
            active_threads=4,
        )

        assert metrics.completed_files == 50
        assert metrics.total_files == 100
        assert metrics.progress_percent == 50.0
        assert metrics.files_per_second == 2.5
        assert metrics.kb_per_second == 128.0
        assert metrics.active_threads == 4


class TestAggregateProgressTracker:
    """Test AggregateProgressTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = AggregateProgressTracker(total_files=100)

        assert tracker.total_files == 100
        assert tracker.completed_files_count == 0
        assert tracker.total_bytes_processed == 0
        assert tracker.start_time > 0
        assert len(tracker.completion_timestamps) == 0
        assert len(tracker.completion_sizes) == 0

    def test_mark_file_complete_single_file(self):
        """Test marking a single file complete."""
        tracker = AggregateProgressTracker(total_files=100)

        # Mark file complete
        tracker.mark_file_complete(file_size=1024)

        # Verify updates
        assert tracker.completed_files_count == 1
        assert tracker.total_bytes_processed == 1024
        assert len(tracker.completion_timestamps) == 1
        assert len(tracker.completion_sizes) == 1
        assert tracker.completion_sizes[0] == 1024

    def test_mark_file_complete_multiple_files(self):
        """Test marking multiple files complete."""
        tracker = AggregateProgressTracker(total_files=100)

        file_sizes = [512, 1024, 2048, 4096]

        for size in file_sizes:
            tracker.mark_file_complete(file_size=size)

        # Verify aggregates
        assert tracker.completed_files_count == 4
        assert tracker.total_bytes_processed == sum(file_sizes)
        assert len(tracker.completion_timestamps) == 4
        assert len(tracker.completion_sizes) == 4
        assert list(tracker.completion_sizes) == file_sizes

    def test_mark_file_complete_rolling_window(self):
        """Test rolling window behavior with maxlen=100."""
        tracker = AggregateProgressTracker(total_files=200)

        # Add 150 completions (exceeds maxlen=100)
        for i in range(150):
            tracker.mark_file_complete(file_size=1000)

        # Should only keep last 100
        assert tracker.completed_files_count == 150  # Total count maintained
        assert tracker.total_bytes_processed == 150 * 1000  # Total bytes maintained
        assert len(tracker.completion_timestamps) == 100  # Rolling window applied
        assert len(tracker.completion_sizes) == 100  # Rolling window applied

    def test_get_current_metrics_zero_files(self):
        """Test metrics calculation with zero completed files."""
        tracker = AggregateProgressTracker(total_files=100)

        metrics = tracker.get_current_metrics(active_thread_count=4)

        assert metrics.completed_files == 0
        assert metrics.total_files == 100
        assert metrics.progress_percent == 0.0
        assert metrics.files_per_second == 0.0
        assert metrics.kb_per_second == 0.0
        assert metrics.active_threads == 4

    def test_get_current_metrics_partial_progress(self):
        """Test metrics calculation with partial progress."""
        tracker = AggregateProgressTracker(total_files=200)

        # Complete 50 files
        for i in range(50):
            tracker.mark_file_complete(file_size=2048)  # 2KB each

        metrics = tracker.get_current_metrics(active_thread_count=6)

        assert metrics.completed_files == 50
        assert metrics.total_files == 200
        assert metrics.progress_percent == 25.0  # 50/200 * 100
        assert metrics.active_threads == 6

        # Files per second and KB per second should be > 0
        assert metrics.files_per_second > 0
        assert metrics.kb_per_second > 0

    def test_get_current_metrics_complete_progress(self):
        """Test metrics calculation with 100% progress."""
        tracker = AggregateProgressTracker(total_files=10)

        # Complete all files
        for i in range(10):
            tracker.mark_file_complete(file_size=1024)

        metrics = tracker.get_current_metrics(active_thread_count=2)

        assert metrics.completed_files == 10
        assert metrics.total_files == 10
        assert metrics.progress_percent == 100.0
        assert metrics.active_threads == 2

    def test_get_current_metrics_zero_total_files(self):
        """Test metrics calculation with zero total files."""
        tracker = AggregateProgressTracker(total_files=0)

        metrics = tracker.get_current_metrics(active_thread_count=1)

        assert metrics.completed_files == 0
        assert metrics.total_files == 0
        assert metrics.progress_percent == 0.0
        assert metrics.active_threads == 1

    @patch("code_indexer.services.aggregate_progress_tracker.time.time")
    def test_files_per_second_calculation_startup(self, mock_time):
        """Test files/s calculation during startup (less than 2 completions)."""
        # Mock time progression - need more calls for all time.time() usage
        mock_time.side_effect = [
            1000.0,
            1001.0,
            1002.0,
            1002.0,
        ]  # start, complete1, get_metrics, kb_calc

        tracker = AggregateProgressTracker(total_files=100)

        # Single completion
        tracker.mark_file_complete(file_size=1024)

        # Get metrics (should use total average)
        metrics = tracker.get_current_metrics(active_thread_count=1)

        # Should use total elapsed time: 1 file in 2 seconds = 0.5 files/s
        assert metrics.files_per_second == 0.5

    @patch("code_indexer.services.aggregate_progress_tracker.time.time")
    def test_files_per_second_calculation_rolling_window(self, mock_time):
        """Test files/s calculation using rolling window."""
        # Setup time progression: start at 1000, then 1001, 1002, 1003, get_metrics at 1004
        mock_time.side_effect = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]

        tracker = AggregateProgressTracker(total_files=100)

        # Multiple completions
        tracker.mark_file_complete(file_size=1024)  # t=1001
        tracker.mark_file_complete(file_size=1024)  # t=1002
        tracker.mark_file_complete(file_size=1024)  # t=1003

        # Get metrics (should use rolling window)
        metrics = tracker.get_current_metrics(active_thread_count=1)

        # Rolling window: 3 files from t=1001 to t=1003 = 3 files in 2 seconds = 1.5 files/s
        assert metrics.files_per_second == 1.5

    @patch("code_indexer.services.aggregate_progress_tracker.time.time")
    def test_kb_per_second_calculation(self, mock_time):
        """Test KB/s throughput calculation."""
        # Setup time progression - need extra calls for files_per_second calculation
        mock_time.side_effect = [
            1000.0,
            1002.0,
            1004.0,
            1004.0,
        ]  # start, complete, files/s calc, kb/s calc

        tracker = AggregateProgressTracker(total_files=100)

        # Complete file
        tracker.mark_file_complete(file_size=4096)  # 4KB

        # Get metrics
        metrics = tracker.get_current_metrics(active_thread_count=1)

        # 4KB in 4 seconds = 1 KB/s
        assert metrics.kb_per_second == 1.0

    def test_thread_safety_concurrent_completions(self):
        """Test thread safety during concurrent file completions."""
        tracker = AggregateProgressTracker(total_files=1000)
        errors = []

        def mark_complete_worker(file_size: int, iterations: int):
            try:
                for _ in range(iterations):
                    tracker.mark_file_complete(file_size=file_size)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=mark_complete_worker,
                args=(1024, 10),  # Each thread completes 10 files
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0
        assert tracker.completed_files_count == 50  # 5 threads * 10 files each
        assert tracker.total_bytes_processed == 50 * 1024
        assert len(tracker.completion_timestamps) == 50
        assert len(tracker.completion_sizes) == 50

    def test_thread_safety_concurrent_metrics_retrieval(self):
        """Test thread safety during concurrent metrics retrieval."""
        tracker = AggregateProgressTracker(total_files=100)

        # Pre-populate some data
        for i in range(20):
            tracker.mark_file_complete(file_size=1024)

        metrics_results = []
        errors = []

        def get_metrics_worker():
            try:
                for _ in range(10):
                    metrics = tracker.get_current_metrics(active_thread_count=3)
                    metrics_results.append(metrics)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Create multiple threads retrieving metrics
        threads = []
        for i in range(3):
            thread = threading.Thread(target=get_metrics_worker)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0
        assert len(metrics_results) == 30  # 3 threads * 10 metrics each

        # All metrics should have consistent base values
        for metrics in metrics_results:
            assert metrics.completed_files == 20
            assert metrics.total_files == 100
            assert metrics.progress_percent == 20.0
            assert metrics.active_threads == 3

    def test_mixed_operations_thread_safety(self):
        """Test thread safety with mixed completions and metrics retrieval."""
        tracker = AggregateProgressTracker(total_files=200)
        completion_count = 0
        metrics_count = 0
        errors = []

        def completion_worker():
            nonlocal completion_count
            try:
                for i in range(20):
                    tracker.mark_file_complete(file_size=512 * (i + 1))
                    completion_count += 1
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def metrics_worker():
            nonlocal metrics_count
            try:
                for _ in range(15):
                    tracker.get_current_metrics(active_thread_count=2)
                    metrics_count += 1
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Start both types of workers
        threads = []

        # 2 completion workers
        for i in range(2):
            thread = threading.Thread(target=completion_worker)
            threads.append(thread)
            thread.start()

        # 2 metrics workers
        for i in range(2):
            thread = threading.Thread(target=metrics_worker)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0
        assert completion_count == 40  # 2 workers * 20 completions
        assert metrics_count == 30  # 2 workers * 15 metrics
        assert tracker.completed_files_count == 40

    def test_edge_case_very_fast_completions(self):
        """Test edge case with very fast file completions."""
        tracker = AggregateProgressTracker(total_files=1000)

        # Complete files very quickly
        for i in range(100):
            tracker.mark_file_complete(file_size=100)

        # Get metrics
        metrics = tracker.get_current_metrics(active_thread_count=8)

        # Verify basic correctness
        assert metrics.completed_files == 100
        assert metrics.total_files == 1000
        assert metrics.progress_percent == 10.0
        assert metrics.active_threads == 8

        # Rate calculations should be reasonable
        assert metrics.files_per_second > 0
        assert metrics.kb_per_second > 0
