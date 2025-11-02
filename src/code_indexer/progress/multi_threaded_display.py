"""Multi-threaded progress display components for Feature 4.

This module implements direct array access display with real-time updates
using only CleanSlotTracker.status_array for single data structure architecture.

Key Components:
- MultiThreadedProgressManager: Integrates with CleanSlotTracker array access
- Direct slot scanning: for slot_id in range(threadcount+2)
- No dictionaries, no complex data operations
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
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
from ..services.clean_slot_tracker import CleanSlotTracker, FileData

logger = logging.getLogger(__name__)


class MultiThreadedProgressManager:
    """Main manager for multi-threaded progress display integration.

    Uses direct array access to CleanSlotTracker.status_array only.
    No dictionaries, no complex data operations - simple array scanning.
    """

    def __init__(
        self,
        console: Console,
        live_manager: Optional[RichLiveProgressManager] = None,
        max_slots: int = 14,  # threadcount+2
    ):
        """Initialize multi-threaded progress manager.

        Args:
            console: Rich console for rendering
            live_manager: Optional existing Rich Live manager for integration
            max_slots: Maximum number of slots (threadcount+2)
        """
        self.console = console
        self.live_manager = live_manager
        self.max_slots = max_slots
        self.slot_tracker: Optional[CleanSlotTracker] = None
        self._current_phase = "Indexing"  # Default phase
        self._concurrent_files: List[Dict[str, Any]] = (
            []
        )  # Store concurrent files for display

        # Create Rich Progress component for visual progress bar
        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
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

    def set_slot_tracker(self, slot_tracker: CleanSlotTracker) -> None:
        """Set the slot tracker for direct array access.

        Args:
            slot_tracker: CleanSlotTracker instance with status_array
        """
        self.slot_tracker = slot_tracker

    def get_display_lines_from_tracker(
        self, slot_tracker: CleanSlotTracker, max_slots: Optional[int] = None
    ) -> List[str]:
        """Get display lines by scanning slot tracker array directly.

        CONSOLIDATED METHOD: Eliminates code duplication from 3 similar methods.

        Args:
            slot_tracker: CleanSlotTracker with status_array to scan
            max_slots: Number of slots to scan (defaults to self.max_slots)

        Returns:
            List of formatted display lines
        """
        display_lines = []
        slots_to_scan = max_slots or self.max_slots

        # Simple array scanning: for slot_id in range(threadcount+2)
        for slot_id in range(slots_to_scan):
            file_data = slot_tracker.status_array[slot_id]
            if file_data is not None:
                formatted_line = self._format_file_line_from_data(file_data)
                display_lines.append(formatted_line)

        return display_lines

    def get_array_display_lines(
        self, slot_tracker: CleanSlotTracker, max_slots: int
    ) -> List[str]:
        """DEPRECATED: Use get_display_lines_from_tracker() instead."""
        return self.get_display_lines_from_tracker(slot_tracker, max_slots)

    def get_current_display_lines(self, slot_tracker: CleanSlotTracker) -> List[str]:
        """DEPRECATED: Use get_display_lines_from_tracker() instead."""
        return self.get_display_lines_from_tracker(slot_tracker)

    def _format_file_line_from_data(self, file_data: FileData) -> str:
        """Format a single file line from FileData.

        Args:
            file_data: FileData from slot tracker

        Returns:
            Formatted display line string
        """
        # Convert file size to human-readable format
        if file_data.file_size < 1024:
            size_str = f"{file_data.file_size} B"
        elif file_data.file_size < 1024 * 1024:
            size_str = f"{file_data.file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_data.file_size / (1024 * 1024):.1f} MB"

        # Format status with custom mappings
        status_value = (
            file_data.status.value
            if hasattr(file_data.status, "value")
            else str(file_data.status)
        )

        if status_value == "starting":
            status_str = "starting"
        elif status_value == "chunking":
            status_str = "chunking..."
        elif status_value == "vectorizing":
            status_str = "vectorizing..."
        elif status_value == "processing":
            status_str = "vectorizing..."
        elif status_value == "finalizing":
            status_str = "finalizing..."
        elif status_value == "complete":
            status_str = "complete ✓"
        else:
            status_str = status_value

        # Format: ├─ filename.py (size, 1s) status
        return f"├─ {Path(file_data.filename).name} ({size_str}, 1s) {status_str}"

    def update_complete_state(
        self,
        current: int,
        total: int,
        files_per_second: float,
        kb_per_second: float,
        active_threads: int,
        concurrent_files: List[Dict[str, Any]],
        slot_tracker=None,
        info: Optional[str] = None,
    ) -> None:
        """Update complete state using direct slot tracker array access.

        Args:
            current: Current progress count (or -1 for display-only update)
            total: Total items to process (or -1 for display-only update)
            files_per_second: Processing rate in files/second
            kb_per_second: Processing rate in KB/second
            active_threads: Number of active threads
            concurrent_files: List of concurrent file data (compatibility)
            slot_tracker: CleanSlotTracker with status_array
            info: Optional info string containing phase indicators
        """
        # DEFENSIVE: Ensure current and total are always integers, never None
        # This prevents "None/None" display and TypeError exceptions
        if current is None:
            logger.warning("BUG: None current value in progress! Converting to 0.")
            current = 0
        if total is None:
            logger.warning("BUG: None total value in progress! Converting to 0.")
            total = 0

        # BUG FIX: Handle display-only updates (current=-1, total=-1)
        # FileChunkingManager sends -1/-1 to update concurrent_files display without progress bar change
        if current == -1 and total == -1:
            # Display update only - don't update progress bar
            self._concurrent_files = concurrent_files or []
            if slot_tracker is not None:
                self.set_slot_tracker(slot_tracker)
            return

        # Store slot_tracker for get_integrated_display() - use consistent attribute
        if slot_tracker is not None:
            # Set slot tracker for direct connection (replaces CLI connection)
            self.set_slot_tracker(slot_tracker)
        else:
            # CRITICAL FIX: Clear stale slot_tracker when None is passed (e.g., hash phase)
            # This ensures concurrent_files data is used instead of stale slot tracker data
            self.slot_tracker = None

        # Store concurrent files for display when slot_tracker is None (e.g., hash phase)
        # Note: This is only used as fallback when slot_tracker is None
        self._concurrent_files = concurrent_files or []

        # Detect phase from info string if provided
        if info:
            if "🔍" in info:
                self._current_phase = "🔍 Hashing"
            elif "📊" in info:
                self._current_phase = "🚀 Indexing"
            elif "🔒" in info:
                self._current_phase = "🔒 Branch isolation"
            # Keep current phase if no clear indicator

        # Initialize progress bar if not started
        if not self._progress_started and total > 0:
            files_info = f"{current}/{total} files"
            self.main_task_id = self.progress.add_task(
                self._current_phase,
                total=total,
                completed=current,
                files_info=files_info,
            )
            self._progress_started = True

        # Update Rich Progress bar
        if self._progress_started and self.main_task_id is not None:
            files_info = f"{current}/{total} files"
            self.progress.update(
                self.main_task_id,
                completed=current,
                files_info=files_info,
                description=self._current_phase,
            )

        # Store metrics info for display below progress bar
        self._current_metrics_info = (
            f"{files_per_second:.1f} files/s | "
            f"{kb_per_second:.1f} KB/s | "
            f"{active_threads} threads"
        )

        # Use existing slot tracker reference (set via set_slot_tracker or constructor)
        # self.slot_tracker is already available

    def get_integrated_display(self) -> Table:
        """Get integrated display using direct slot tracker array access.

        Returns:
            Rich Table with progress bar at top, metrics line, and file lines
        """
        # CRITICAL FIX: Capture slot_tracker in local variable to prevent race condition
        # where self.slot_tracker becomes None between check and attribute access
        slot_tracker = self.slot_tracker

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

        # CRITICAL FIX: PREFER serialized concurrent_files over RPyC proxy calls
        # In daemon mode:
        #   - self._concurrent_files = Fresh serialized data passed in kwargs (FAST, always current)
        #   - slot_tracker.get_concurrent_files_data() = RPyC proxy call (SLOW, may be stale)
        # CORRECT PRECEDENCE: Use serialized data first, fallback to proxy only if unavailable
        # This ensures Rich Live refresh (10x/sec) uses pre-serialized data, not slow RPyC calls

        # Get concurrent files data with correct precedence
        fresh_concurrent_files = []
        if self._concurrent_files:
            # PREFER serialized concurrent_files - it's already fresh from daemon
            fresh_concurrent_files = self._concurrent_files
        elif slot_tracker is not None:
            # Fallback to slot_tracker only if concurrent_files not available
            # This happens in direct mode (non-daemon) or when daemon doesn't send concurrent_files
            fresh_concurrent_files = slot_tracker.get_concurrent_files_data()

        if fresh_concurrent_files:
            for file_info in fresh_concurrent_files:
                if file_info:
                    filename = file_info.get("file_path", "unknown")
                    if isinstance(filename, Path):
                        filename = filename.name
                    elif "/" in str(filename):
                        filename = str(filename).split("/")[-1]
                    file_size = file_info.get("file_size", 0)
                    status = file_info.get("status", "processing")

                    # Format status for display
                    if status == "complete":
                        status_display = "complete ✓"
                    elif status == "processing":
                        if self._current_phase == "🔍 Hashing":
                            status_display = "hashing..."
                        else:
                            status_display = "processing..."
                    else:
                        status_display = status

                    line = f"├─ {filename} ({file_size/1024:.1f} KB) {status_display}"
                    main_table.add_row(Text(line, style="cyan"))

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

    def handle_final_completion(self) -> None:
        """Handle final completion - no cleanup needed with array access.

        CleanSlotTracker handles slot cleanup automatically.
        """
        # No cleanup needed - direct array access has no state to clear
        pass

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

    def reset_progress_timers(self) -> None:
        """Reset progress display for new phase after timing reset.

        This method resets the Rich Progress component's internal timers
        to fix the frozen timing issue when transitioning from hash to indexing phase.
        The Rich Progress component tracks its own start time which must be reset
        separately from the stats timer reset.

        BUG FIX: Create NEW Progress instance instead of reusing stopped one.
        When Progress.stop() is called, the internal timers become frozen and cannot
        be properly reset by restarting the same instance. Creating a fresh Progress
        instance ensures elapsed time and ETA calculations start from zero.
        """
        if self._progress_started:
            # Stop current progress to clear internal timers
            self.progress.stop()

            # BUG FIX: Create NEW Progress instance with fresh timers
            # Reusing stopped Progress instance causes frozen elapsed/remaining time
            self.progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                "•",
                TimeElapsedColumn(),
                "•",
                TimeRemainingColumn(),
                "•",
                TextColumn("{task.fields[files_info]}"),
                console=self.console,
                transient=False,
                expand=False,
            )

            # Reset progress state to allow fresh initialization
            self._progress_started = False
            self.main_task_id = None

            # Progress will re-initialize with fresh timers on next update_complete_state call
            # This ensures both Rich Progress timers AND stats timers are aligned
