"""
Aggregate progress tracker for running totals and rate calculations.
Maintains cumulative statistics separate from slot-based display.
"""

import time
from collections import deque
from threading import Lock
from typing import NamedTuple


class ProgressMetrics(NamedTuple):
    """Progress calculation results."""

    completed_files: int
    total_files: int
    progress_percent: float
    files_per_second: float
    kb_per_second: float
    active_threads: int


class AggregateProgressTracker:
    """Tracks cumulative progress and calculates rates."""

    def __init__(self, total_files: int):
        self.total_files = total_files
        self.completed_files_count = 0
        self.total_bytes_processed = 0
        self.start_time = time.time()

        # Rolling window for rate calculations (30-second window)
        self.completion_timestamps: deque[float] = deque(maxlen=100)
        self.completion_sizes: deque[int] = deque(maxlen=100)

        # Thread safety
        self._lock = Lock()

    def mark_file_complete(self, file_size: int):
        """Mark file complete and update running totals."""
        current_time = time.time()

        with self._lock:
            self.completed_files_count += 1
            self.total_bytes_processed += file_size
            self.completion_timestamps.append(current_time)
            self.completion_sizes.append(file_size)

    def get_current_metrics(self, active_thread_count: int) -> ProgressMetrics:
        """Calculate current progress metrics."""
        with self._lock:
            # Progress percentage
            progress_percent = (
                (self.completed_files_count / self.total_files * 100)
                if self.total_files > 0
                else 0
            )

            # Files per second (rolling window)
            files_per_second = self._calculate_files_per_second()

            # KB per second
            kb_per_second = self._calculate_kb_per_second()

            return ProgressMetrics(
                completed_files=self.completed_files_count,
                total_files=self.total_files,
                progress_percent=progress_percent,
                files_per_second=files_per_second,
                kb_per_second=kb_per_second,
                active_threads=active_thread_count,
            )

    def _calculate_files_per_second(self) -> float:
        """Calculate files/s using rolling window."""
        if len(self.completion_timestamps) < 2:
            # Use total average for startup
            elapsed = time.time() - self.start_time
            return self.completed_files_count / elapsed if elapsed > 0 else 0

        # Rolling window calculation
        window_start = self.completion_timestamps[0]
        window_end = self.completion_timestamps[-1]
        time_diff = window_end - window_start
        files_in_window = len(self.completion_timestamps)

        return files_in_window / time_diff if time_diff > 0 else 0

    def _calculate_kb_per_second(self) -> float:
        """Calculate KB/s throughput."""
        elapsed = time.time() - self.start_time
        return (self.total_bytes_processed / 1024) / elapsed if elapsed > 0 else 0
