"""Aggregate Progress Display for clean two-line progress reporting.

This module provides clean aggregate progress display that shows overall metrics
without individual file details, implementing Feature 2: Aggregate Progress Line
from the Rich Progress Display epic.

Target Format:
Line 1: Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
Line 2: 12.3 files/s | 456.7 KB/s | 8 threads
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


@dataclass
class ProgressMetrics:
    """Container for progress performance metrics."""

    files_per_second: float
    kb_per_second: float
    active_threads: int


@dataclass
class ProgressState:
    """Container for complete progress state."""

    current: int
    total: int
    elapsed_seconds: float
    estimated_remaining: float
    files_per_second: float
    kb_per_second: float
    active_threads: int


class ProgressMetricsCalculator:
    """Calculates real-time performance metrics from progress data."""

    def __init__(self) -> None:
        """Initialize metrics calculator."""
        self.progress_points: List[Tuple[float, int, int, int]] = (
            []
        )  # (timestamp, files, bytes, threads)

    def record_progress_point(
        self,
        timestamp: float,
        files_processed: int,
        bytes_processed: int,
        active_threads: int,
    ) -> None:
        """Record a progress data point for metrics calculation.

        Args:
            timestamp: Unix timestamp of the progress point
            files_processed: Total files processed so far
            bytes_processed: Total bytes processed so far
            active_threads: Number of active processing threads
        """
        self.progress_points.append(
            (timestamp, files_processed, bytes_processed, active_threads)
        )

        # Keep only recent points for sliding window calculation
        # Keep last 10 points to smooth out fluctuations
        if len(self.progress_points) > 10:
            self.progress_points = self.progress_points[-10:]

    def get_current_metrics(self) -> ProgressMetrics:
        """Calculate current performance metrics from recorded data points.

        Returns:
            ProgressMetrics with calculated rates and thread count
        """
        if len(self.progress_points) < 2:
            return ProgressMetrics(
                files_per_second=0.0, kb_per_second=0.0, active_threads=0
            )

        # Use first and last points for rate calculation
        start_time, start_files, start_bytes, _ = self.progress_points[0]
        end_time, end_files, end_bytes, current_threads = self.progress_points[-1]

        time_delta = end_time - start_time
        if time_delta <= 0:
            return ProgressMetrics(
                files_per_second=0.0, kb_per_second=0.0, active_threads=current_threads
            )

        # Calculate rates
        files_delta = end_files - start_files
        bytes_delta = end_bytes - start_bytes

        files_per_second = files_delta / time_delta
        kb_per_second = (bytes_delta / 1024) / time_delta

        return ProgressMetrics(
            files_per_second=files_per_second,
            kb_per_second=kb_per_second,
            active_threads=current_threads,
        )


def parse_progress_info(
    info: str,
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[str]]:
    """Parse current progress info format to extract metrics.

    Current format examples:
    - "Vector threads: 8, Queue: 12, 15.2 emb/s | filename.py"
    - "12.3 files/s | 456.7 KB/s | 8 threads | /path/to/file.py"

    Returns:
        Tuple of (files_per_second, kb_per_second, thread_count, filename)
    """
    files_per_second = None
    kb_per_second = None
    thread_count = None
    filename = None

    # Try to extract files/s
    files_match = re.search(r"(\d+\.?\d*)\s*files/s", info)
    if files_match:
        files_per_second = float(files_match.group(1))

    # Try to extract KB/s
    kb_match = re.search(r"(\d+\.?\d*)\s*KB/s", info)
    if kb_match:
        kb_per_second = float(kb_match.group(1))

    # Try to extract thread count (various formats)
    thread_match = re.search(r"(\d+)\s*threads?", info, re.IGNORECASE)
    if thread_match:
        thread_count = int(thread_match.group(1))
    else:
        # Try "Vector threads: N" format
        vector_thread_match = re.search(r"Vector threads:\s*(\d+)", info)
        if vector_thread_match:
            thread_count = int(vector_thread_match.group(1))

    # Extract filename (everything after the last |)
    if "|" in info:
        filename = info.split("|")[-1].strip()

    return files_per_second, kb_per_second, thread_count, filename


def create_aggregate_progress_bar() -> Progress:
    """Create a Rich Progress bar with aggregate-friendly column layout.

    Returns:
        Progress instance configured for clean aggregate display
    """
    return Progress(
        TextColumn("[bold blue]Indexing", justify="right"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        "•",
        TimeElapsedColumn(),
        "•",
        TimeRemainingColumn(),
        "•",
        TextColumn(
            "{task.fields[file_count]}",  # Custom field for file count
            table_column=None,
        ),
        transient=False,
    )


class AggregateProgressDisplay:
    """Clean aggregate progress display with two-line format.

    Provides overall progress metrics without showing individual file details.
    Separates progress bar (line 1) from performance metrics (line 2).
    """

    def __init__(self, console: Console) -> None:
        """Initialize aggregate progress display.

        Args:
            console: Rich console for output
        """
        self.console = console
        self.progress_bar = create_aggregate_progress_bar()
        self.task_id: Optional[int] = None
        self.current_state: Optional[ProgressState] = None

    def update_progress(
        self,
        current: int,
        total: int,
        elapsed_seconds: float,
        estimated_remaining: float,
        files_per_second: float,
        kb_per_second: float,
        active_threads: int,
    ) -> None:
        """Update progress with complete state information.

        Args:
            current: Current number of files processed
            total: Total number of files to process
            elapsed_seconds: Time elapsed since start
            estimated_remaining: Estimated time remaining
            files_per_second: Processing rate in files/s
            kb_per_second: Processing throughput in KB/s
            active_threads: Number of active processing threads
        """
        self.current_state = ProgressState(
            current=current,
            total=total,
            elapsed_seconds=elapsed_seconds,
            estimated_remaining=estimated_remaining,
            files_per_second=files_per_second,
            kb_per_second=kb_per_second,
            active_threads=active_threads,
        )

        # Initialize task if needed
        if self.task_id is None:
            self.task_id = self.progress_bar.add_task(
                "Processing files...",
                total=total,
                file_count=f"{current}/{total} files",
            )

        # Update progress bar with current state
        self.progress_bar.update(
            self.task_id, completed=current, file_count=f"{current}/{total} files"
        )

    def update_metrics(
        self, files_per_second: float, kb_per_second: float, active_threads: int
    ) -> None:
        """Update only the performance metrics.

        Args:
            files_per_second: Processing rate in files/s
            kb_per_second: Processing throughput in KB/s
            active_threads: Number of active processing threads
        """
        if self.current_state is None:
            # Initialize with default state if not yet set
            self.current_state = ProgressState(
                current=0,
                total=100,
                elapsed_seconds=0,
                estimated_remaining=0,
                files_per_second=files_per_second,
                kb_per_second=kb_per_second,
                active_threads=active_threads,
            )
        else:
            # Update just the metrics
            self.current_state.files_per_second = files_per_second
            self.current_state.kb_per_second = kb_per_second
            self.current_state.active_threads = active_threads

    def update_complete_state(
        self,
        current: int,
        total: int,
        elapsed_seconds: float,
        estimated_remaining: float,
        files_per_second: float,
        kb_per_second: float,
        active_threads: int,
    ) -> None:
        """Update complete progress state in a single call.

        Args:
            current: Current number of files processed
            total: Total number of files to process
            elapsed_seconds: Time elapsed since start
            estimated_remaining: Estimated time remaining
            files_per_second: Processing rate in files/s
            kb_per_second: Processing throughput in KB/s
            active_threads: Number of active processing threads
        """
        self.update_progress(
            current,
            total,
            elapsed_seconds,
            estimated_remaining,
            files_per_second,
            kb_per_second,
            active_threads,
        )

    def get_progress_line(self) -> str:
        """Get the first line showing progress bar with timing and file count.

        Returns:
            Formatted progress line string
        """
        if self.current_state is None:
            return "Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% • 0:00:00 • 0:00:00 • 0/0 files"

        state = self.current_state

        # Calculate percentage
        percentage = int((state.current / state.total) * 100) if state.total > 0 else 0

        # Format elapsed time as H:MM:SS
        elapsed_hours = int(state.elapsed_seconds // 3600)
        elapsed_min = int((state.elapsed_seconds % 3600) // 60)
        elapsed_sec = int(state.elapsed_seconds % 60)
        elapsed_str = f"{elapsed_hours}:{elapsed_min:02d}:{elapsed_sec:02d}"

        # Format remaining time as H:MM:SS
        remaining_hours = int(state.estimated_remaining // 3600)
        remaining_min = int((state.estimated_remaining % 3600) // 60)
        remaining_sec = int(state.estimated_remaining % 60)
        remaining_str = f"{remaining_hours}:{remaining_min:02d}:{remaining_sec:02d}"

        # Create progress bar visual (simplified for string representation)
        bar_width = 30
        filled = (
            int((state.current / state.total) * bar_width) if state.total > 0 else 0
        )
        empty = bar_width - filled
        progress_visual = "━" * filled + "━" * empty  # Unicode progress bar

        return f"Indexing {progress_visual} {percentage:>2}% • {elapsed_str} • {remaining_str} • {state.current}/{state.total} files"

    def get_metrics_line(self) -> str:
        """Get the second line showing performance metrics.

        Returns:
            Formatted metrics line string
        """
        if self.current_state is None:
            return "0.0 files/s | 0.0 KB/s | 0 threads"

        state = self.current_state
        return f"{state.files_per_second:.1f} files/s | {state.kb_per_second:.1f} KB/s | {state.active_threads} threads"

    def get_full_display(self) -> str:
        """Get the complete two-line display.

        Returns:
            Two-line formatted display string
        """
        progress_line = self.get_progress_line()
        metrics_line = self.get_metrics_line()
        return f"{progress_line}\n{metrics_line}"
