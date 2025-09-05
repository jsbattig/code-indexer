"""Multi-threaded progress display components for Feature 4.

This module implements concurrent file line display with real-time updates
and ramping down behavior for multi-threaded file processing.

Key Components:
- ConcurrentFileDisplay: Thread-safe display of up to 8 concurrent file lines
- RampingDownManager: Handles gradual reduction from 8→4→2→1→0 lines
- MultiThreadedProgressManager: Integrates with existing Rich Live display
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
from rich.console import Console
from rich.progress import (
    Progress,
    TaskID,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from .progress_display import RichLiveProgressManager


@dataclass
class FileProcessingLine:
    """Data class for a single file processing line."""

    thread_id: int
    file_path: Path
    file_size: int
    estimated_seconds: int
    status: str
    created_at: float
    last_updated: float


@dataclass
class TimingConfig:
    """Configuration for ramping timing behavior."""

    min_delay_between_reductions: float
    max_delay_between_reductions: float


@dataclass
class TransitionStep:
    """Single step in a visual transition."""

    opacity: float
    duration_seconds: float


@dataclass
class TransitionEffect:
    """Complete transition effect with multiple steps."""

    steps: List[TransitionStep]
    total_duration_seconds: float


class ConcurrentFileDisplay:
    """Thread-safe display component for concurrent file processing lines.

    Manages up to max_lines concurrent file lines with real-time updates.
    Provides thread-safe operations for add/update/remove file lines.
    """

    def __init__(self, console: Console, max_lines: int = 8):
        """Initialize concurrent file display.

        Args:
            console: Rich console for rendering
            max_lines: Maximum number of concurrent lines to display
        """
        self.console = console
        self.max_lines = max_lines
        self.active_lines: Dict[int, FileProcessingLine] = {}
        self._lock = threading.Lock()

    def add_file_line(
        self, thread_id: int, file_path: Path, file_size: int, estimated_seconds: int
    ) -> None:
        """Add a new file processing line.

        Args:
            thread_id: Unique thread identifier
            file_path: Path of file being processed
            file_size: Size of file in bytes
            estimated_seconds: Estimated processing time
        """
        with self._lock:
            # Enforce max lines limit
            if (
                len(self.active_lines) >= self.max_lines
                and thread_id not in self.active_lines
            ):
                # Remove oldest line to make room
                if self.active_lines:
                    oldest_thread_id = min(
                        self.active_lines.keys(),
                        key=lambda tid: self.active_lines[tid].created_at,
                    )
                    del self.active_lines[oldest_thread_id]

            current_time = time.time()
            self.active_lines[thread_id] = FileProcessingLine(
                thread_id=thread_id,
                file_path=file_path,
                file_size=file_size,
                estimated_seconds=estimated_seconds,
                status="starting...",
                created_at=current_time,
                last_updated=current_time,
            )

    def update_file_line(self, thread_id: int, status: str) -> None:
        """Update status of an existing file line.

        Args:
            thread_id: Thread identifier to update
            status: New status text
        """
        with self._lock:
            if thread_id in self.active_lines:
                self.active_lines[thread_id].status = status
                self.active_lines[thread_id].last_updated = time.time()

    def remove_file_line(self, thread_id: int) -> None:
        """Remove a file processing line.

        Args:
            thread_id: Thread identifier to remove
        """
        with self._lock:
            if thread_id in self.active_lines:
                del self.active_lines[thread_id]

    def get_active_line_count(self) -> int:
        """Get count of currently active lines.

        Returns:
            Number of active file processing lines
        """
        with self._lock:
            return len(self.active_lines)

    def get_rendered_lines(self) -> List[str]:
        """Get list of rendered file processing lines.

        Returns:
            List of formatted line strings ready for display
        """
        with self._lock:
            rendered = []

            # Sort by thread_id for consistent ordering
            for thread_id in sorted(self.active_lines.keys()):
                line_data = self.active_lines[thread_id]
                formatted_line = self._format_file_line(line_data)
                rendered.append(formatted_line)

            return rendered

    def _format_file_line(self, line_data: FileProcessingLine) -> str:
        """Format a single file line for display.

        Args:
            line_data: File processing line data

        Returns:
            Formatted line string with tree-style indicator
        """
        # Convert file size to human-readable format
        if line_data.file_size < 1024:
            size_str = f"{line_data.file_size} B"
        elif line_data.file_size < 1024 * 1024:
            size_str = f"{line_data.file_size / 1024:.1f} KB"
        else:
            size_str = f"{line_data.file_size / (1024 * 1024):.1f} MB"

        # Format: ├─ filename.py (size, estimated_time) status
        return f"├─ {line_data.file_path.name} ({size_str}, {line_data.estimated_seconds}s) {line_data.status}"


class RampingDownManager:
    """Manages ramping down behavior as threads complete processing.

    Handles gradual reduction of display lines from 8→4→2→1→0
    as fewer files remain than active threads.
    """

    def __init__(self, console: Console):
        """Initialize ramping down manager.

        Args:
            console: Rich console for rendering
        """
        self.console = console
        self.timing_config = TimingConfig(
            min_delay_between_reductions=0.5, max_delay_between_reductions=2.0
        )

    def should_start_ramping_down(
        self, active_threads: int, files_remaining: int
    ) -> bool:
        """Determine if ramping down should be triggered.

        Args:
            active_threads: Number of active worker threads
            files_remaining: Number of files still to be processed

        Returns:
            True if ramping down should start
        """
        return files_remaining <= active_threads

    def calculate_target_lines(self, active_threads: int, files_remaining: int) -> int:
        """Calculate target number of display lines.

        Args:
            active_threads: Number of active worker threads
            files_remaining: Number of files still to be processed

        Returns:
            Target number of display lines
        """
        if files_remaining <= 0:
            return 0
        return min(files_remaining, active_threads)

    def ramp_down_to_count(
        self, display: ConcurrentFileDisplay, target_count: int
    ) -> None:
        """Ramp down display to target line count.

        Args:
            display: Concurrent file display to modify
            target_count: Target number of lines to maintain
        """
        current_count = display.get_active_line_count()

        if current_count <= target_count:
            return  # Already at or below target

        # Calculate lines to remove
        lines_to_remove = current_count - target_count

        # Get current thread IDs sorted by creation time (oldest first)
        with display._lock:
            thread_ids_by_age = sorted(
                display.active_lines.keys(),
                key=lambda tid: display.active_lines[tid].created_at,
            )

        # Remove oldest lines first
        for i in range(lines_to_remove):
            if i < len(thread_ids_by_age):
                display.remove_file_line(thread_ids_by_age[i])

    def get_timing_config(self) -> TimingConfig:
        """Get current timing configuration.

        Returns:
            Current timing configuration
        """
        return self.timing_config

    def set_timing_config(self, min_delay: float, max_delay: float) -> None:
        """Set timing configuration.

        Args:
            min_delay: Minimum delay between reductions
            max_delay: Maximum delay between reductions
        """
        self.timing_config = TimingConfig(
            min_delay_between_reductions=min_delay,
            max_delay_between_reductions=max_delay,
        )


class MultiThreadedProgressManager:
    """Main manager for multi-threaded progress display integration.

    Integrates concurrent file display with existing Rich Live progress
    and aggregate progress components from Features 1-3.
    """

    def __init__(
        self, console: Console, live_manager: Optional[RichLiveProgressManager] = None
    ):
        """Initialize multi-threaded progress manager.

        Args:
            console: Rich console for rendering
            live_manager: Optional existing Rich Live manager for integration
        """
        self.console = console
        self.live_manager = live_manager
        self.concurrent_display = ConcurrentFileDisplay(console, max_lines=8)
        self.ramping_manager = RampingDownManager(console)

        # Create Rich Progress component for visual progress bar
        self.progress = Progress(
            TextColumn("Indexing"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            "•",
            TimeElapsedColumn(),
            "•",
            TimeRemainingColumn(),
            "•",
            TextColumn("{task.fields[files_info]}"),
            console=console,
            transient=False,
            expand=False,
        )
        self.main_task_id: Optional[TaskID] = None
        self._current_metrics_info = ""
        self._progress_started = False

    def update_progress(
        self,
        current: int,
        total: int,
        active_threads: int,
        concurrent_files: List[Dict[str, Any]],
    ) -> None:
        """Update complete progress state with concurrent file information.

        Args:
            current: Current number of processed files
            total: Total number of files to process
            active_threads: Number of active worker threads
            concurrent_files: List of files currently being processed
        """
        # Update concurrent file display
        self.update_concurrent_files(concurrent_files)

        # Check if ramping down is needed
        files_remaining = total - current
        if self.ramping_manager.should_start_ramping_down(
            active_threads, files_remaining
        ):
            target_lines = self.ramping_manager.calculate_target_lines(
                active_threads, files_remaining
            )
            self.ramping_manager.ramp_down_to_count(
                self.concurrent_display, target_lines
            )

    def update_concurrent_files(self, concurrent_files: List[Dict[str, Any]]) -> None:
        """Update concurrent file display with current file processing state.

        Args:
            concurrent_files: List of file processing dictionaries
        """
        # Update or add file lines based on current state
        for file_data in concurrent_files:
            thread_id = file_data["thread_id"]

            if thread_id not in self.concurrent_display.active_lines:
                # Add new file line
                self.concurrent_display.add_file_line(
                    thread_id=thread_id,
                    file_path=Path(file_data["file_path"]),
                    file_size=file_data["file_size"],
                    estimated_seconds=file_data.get("estimated_seconds", 5),
                )

            # Update status
            self.concurrent_display.update_file_line(
                thread_id=thread_id, status=file_data["status"]
            )

    def update_complete_state(
        self,
        current: int,
        total: int,
        files_per_second: float,
        kb_per_second: float,
        active_threads: int,
        concurrent_files: List[Dict[str, Any]],
    ) -> None:
        """Update complete state including aggregate progress and concurrent files.

        Args:
            current: Current progress count
            total: Total items to process
            files_per_second: Processing rate in files/second
            kb_per_second: Processing rate in KB/second
            active_threads: Number of active threads
            concurrent_files: List of concurrent file processing data
        """
        # Initialize progress bar if not started
        if not self._progress_started and total > 0:
            files_info = f"{current}/{total} files"
            self.main_task_id = self.progress.add_task(
                "Indexing", total=total, completed=current, files_info=files_info
            )
            self._progress_started = True

        # Update Rich Progress bar
        if self._progress_started and self.main_task_id is not None:
            files_info = f"{current}/{total} files"
            self.progress.update(
                self.main_task_id, completed=current, files_info=files_info
            )

        # Store metrics info for display below progress bar
        self._current_metrics_info = (
            f"{files_per_second:.1f} files/s | "
            f"{kb_per_second:.1f} KB/s | "
            f"{active_threads} threads"
        )

        # Update concurrent files first
        self.update_concurrent_files(concurrent_files)

        # Handle ramping down
        files_remaining = total - current
        if self.ramping_manager.should_start_ramping_down(
            active_threads, files_remaining
        ):
            target_lines = self.ramping_manager.calculate_target_lines(
                active_threads, files_remaining
            )
            self.ramping_manager.ramp_down_to_count(
                self.concurrent_display, target_lines
            )

    def get_integrated_display(self) -> Table:
        """Get integrated display combining Rich progress bar and concurrent files.

        Returns:
            Rich Table with progress bar at top, metrics line, and file lines
        """
        # Create main table to hold all display components
        main_table = Table.grid(padding=(0, 0))
        main_table.add_column(justify="left")

        # Add Rich Progress bar at the top
        if self._progress_started:
            main_table.add_row(self.progress)
        else:
            # Show initializing message until progress starts
            main_table.add_row(
                Text("Initializing progress display...", style="dim cyan")
            )

        # Add metrics line below progress bar
        if self._current_metrics_info:
            metrics_text = Text(self._current_metrics_info, style="dim white")
            main_table.add_row(metrics_text)

        # Add concurrent file lines
        file_lines = self.concurrent_display.get_rendered_lines()
        for line in file_lines:
            file_text = Text(line, style="dim blue")
            main_table.add_row(file_text)

        return main_table

    def get_final_display(self) -> Table:
        """Get final display for 100% completion.

        Returns:
            Rich Table with final progress bar at 100%
        """
        # Create final completion table
        final_table = Table.grid(padding=(0, 0))
        final_table.add_column(justify="left")

        if self._progress_started:
            # Show completed progress bar
            final_table.add_row(self.progress)
            final_table.add_row(Text("Processing completed ✅", style="bold green"))
        else:
            final_table.add_row(
                Text("Processing completed (100%) ✅", style="bold green")
            )

        return final_table

    def handle_final_completion(self, display: ConcurrentFileDisplay) -> None:
        """Handle final completion by removing all file lines.

        Args:
            display: Concurrent file display to clear
        """
        # Remove all active lines
        with display._lock:
            thread_ids = list(display.active_lines.keys())

        for thread_id in thread_ids:
            display.remove_file_line(thread_id)

    def get_completion_display(self) -> Table:
        """Get completion display showing 100% progress.

        Returns:
            Rich Table with completion display
        """
        return self.get_final_display()

    def stop_progress(self) -> None:
        """Stop and cleanup the progress bar.

        Should be called when indexing is complete or cancelled.
        """
        if self._progress_started:
            self.progress.stop()
            self._progress_started = False
