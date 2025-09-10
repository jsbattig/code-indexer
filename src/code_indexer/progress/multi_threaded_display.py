"""Multi-threaded progress display components for Feature 4.

This module implements direct array access display with real-time updates
using only CleanSlotTracker.status_array for single data structure architecture.

Key Components:
- MultiThreadedProgressManager: Integrates with CleanSlotTracker array access
- Direct slot scanning: for slot_id in range(threadcount+2)
- No dictionaries, no complex data operations
"""

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
    ) -> None:
        """Update complete state using direct slot tracker array access.

        Args:
            current: Current progress count
            total: Total items to process
            files_per_second: Processing rate in files/second
            kb_per_second: Processing rate in KB/second
            active_threads: Number of active threads
            concurrent_files: List of concurrent file data (compatibility)
            slot_tracker: CleanSlotTracker with status_array
        """
        # Store slot_tracker for get_integrated_display() - use consistent attribute
        if slot_tracker is not None:
            # Set slot tracker for direct connection (replaces CLI connection)
            self.set_slot_tracker(slot_tracker)

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

        # Use existing slot tracker reference (set via set_slot_tracker or constructor)
        # self.slot_tracker is already available

    def get_integrated_display(self) -> Table:
        """Get integrated display using direct slot tracker array access.

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

        # ADD: Simple slot display lines (NEW)
        if self.slot_tracker is not None:
            for slot_id in range(self.slot_tracker.max_slots):
                file_data = self.slot_tracker.status_array[slot_id]
                if file_data is not None:
                    status_display = file_data.status.value
                    if status_display == "complete":
                        status_display = "complete ✓"
                    elif status_display in ["vectorizing", "processing"]:
                        status_display = "vectorizing..."
                    elif status_display == "finalizing":
                        status_display = "finalizing..."
                    elif status_display == "chunking":
                        status_display = "chunking..."
                    elif status_display == "starting":
                        status_display = "starting"

                    line = f"├─ {file_data.filename} ({file_data.file_size/1024:.1f} KB) {status_display}"
                    main_table.add_row(Text(line, style="dim blue"))

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
