"""
Client-side progress handler for daemon progress callbacks via RPyC.

This module provides visual progress feedback in the client terminal when
indexing operations run in the daemon process. Progress updates are streamed
from the daemon to the client via RPyC callbacks and displayed using Rich
progress bars.

Key features:
- Real-time progress updates via RPyC
- Rich progress bar with file count, percentage, and status
- Setup message display (info messages before file processing)
- Completion and error handling
- RPyC-compatible callback wrapping
"""

import logging
from pathlib import Path
from typing import Optional

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.console import Console

logger = logging.getLogger(__name__)


class ClientProgressHandler:
    """
    Handle progress updates from daemon via RPyC.

    This class creates and manages a Rich progress bar that displays real-time
    updates from daemon indexing operations. It provides:
    - Progress bar initialization
    - Callback creation for RPyC transmission
    - Setup message display
    - File progress updates
    - Completion handling
    - Error handling
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize progress handler.

        Args:
            console: Optional Rich Console instance for output.
                    If not provided, creates a new Console.
        """
        self.console = console or Console()
        self.progress: Optional[Progress] = None
        self.task_id: Optional[int] = None

    def create_progress_callback(self):
        """
        Create RPyC-compatible progress callback.

        This creates a callback function that:
        1. Receives progress updates from daemon
        2. Updates Rich progress bar
        3. Handles setup messages (total=0)
        4. Handles file progress (total>0)
        5. Detects and handles completion

        Returns:
            Callable callback function for daemon to invoke via RPyC.
            The callback signature is: (current, total, file_path, info="")

        Note:
            The returned callback is wrapped with rpyc.async_() for
            non-blocking RPC calls. This ensures progress updates don't
            slow down the indexing operation.
        """
        # Create Rich progress bar with custom columns
        self.progress = Progress(
            SpinnerColumn(),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.description]{task.description}"),
            "•",
            TextColumn("{task.fields[status]}"),
            console=self.console,
            refresh_per_second=10,
        )

        # Start progress context
        self.progress.start()
        self.task_id = self.progress.add_task(
            "Indexing", total=100, status="Starting..."
        )

        # Create callback function for daemon
        def progress_callback(current: int, total: int, file_path, info: str = ""):
            """
            Callback that daemon will call via RPyC.

            Args:
                current: Current progress count (files processed)
                total: Total items to process (0 for info messages)
                file_path: Current file path (Path or str)
                info: Info string (setup message or progress details)
            """
            # Convert Path to string if needed
            if isinstance(file_path, Path):
                file_path_str = str(file_path)
            else:
                file_path_str = str(file_path) if file_path else ""

            if total == 0:
                # Info message (setup phase)
                if self.progress is not None and self.task_id is not None:
                    self.progress.update(
                        self.task_id, description=f"ℹ️ {info}", status=""
                    )
            else:
                # Progress update
                percentage = (current / total) * 100
                if self.progress is not None and self.task_id is not None:
                    self.progress.update(
                        self.task_id,
                        completed=percentage,
                        description=f"{current}/{total} files",
                        status=info or Path(file_path_str).name,
                    )

                # Check for completion
                if current == total:
                    self.complete()

        # Return callback (RPyC will handle async wrapping when transmitting)
        return progress_callback

    def complete(self):
        """
        Mark progress as complete and stop progress bar.

        This method:
        1. Updates progress to 100%
        2. Sets completion message
        3. Stops the progress bar
        """
        if self.progress and self.task_id is not None:
            self.progress.update(
                self.task_id, completed=100, description="Indexing complete", status="✓"
            )
            self.progress.stop()

    def error(self, error_msg: str):
        """
        Handle indexing error and stop progress bar.

        Args:
            error_msg: Error message to display
        """
        if self.progress and self.task_id is not None:
            self.progress.update(
                self.task_id, description=f"[red]Error: {error_msg}[/red]", status="✗"
            )
            self.progress.stop()
