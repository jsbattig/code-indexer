"""Rich Live progress display manager for bottom-anchored progress reporting.

This module provides Rich Live component integration that creates bottom-locked
progress display while allowing other output to scroll above it.
"""

import threading
from pathlib import Path
from typing import Optional, Union
from rich.console import Console, RenderableType
from rich.live import Live


class RichLiveProgressManager:
    """Rich Live progress manager for bottom-anchored display.

    Provides separation between scrolling console output and fixed
    bottom-anchored progress display using Rich Live component.

    Thread-safe: All operations are protected by internal locking to prevent
    race conditions during parallel processing when multiple threads may
    access the progress manager simultaneously.
    """

    def __init__(self, console: Console):
        """Initialize Rich Live progress manager.

        Args:
            console: Rich console instance for output
        """
        self.console = console
        self.live_component: Optional[Live] = None
        self.is_active = False
        # Thread safety lock for protecting concurrent access to state
        self._lock = threading.Lock()

    def start_bottom_display(self) -> None:
        """Start bottom-anchored display with Rich Live component.

        Creates and starts Rich Live component configured for bottom-locked
        progress display with real-time updates.

        Thread-safe: Protected by internal lock to prevent concurrent start operations.
        """
        with self._lock:
            if self.is_active:
                return  # Already started

            self.live_component = Live(
                renderable="",
                console=self.console,
                refresh_per_second=10,
                transient=False,
            )
            self.live_component.start()
            self.is_active = True

    def update_display(self, content: Union[str, RenderableType]) -> None:
        """Update bottom-anchored display content.

        Args:
            content: New content to display in bottom-anchored area (string or Rich renderable)

        Raises:
            RuntimeError: If display not started

        Thread-safe: Protected by internal lock to prevent concurrent access to live_component.
        """
        with self._lock:
            if not self.is_active or self.live_component is None:
                raise RuntimeError(
                    "Display not started. Call start_bottom_display() first."
                )

            self.live_component.update(content)

    def stop_display(self) -> None:
        """Stop bottom-anchored display and cleanup Live component.

        Thread-safe: Protected by internal lock to prevent concurrent stop operations.
        """
        with self._lock:
            if self.live_component is not None:
                self.live_component.stop()
                self.live_component = None
            self.is_active = False

    def handle_setup_message(self, message: str) -> None:
        """Handle setup messages by printing to scrolling console area.

        Setup messages (like ✅ Collection initialized) should scroll above
        the bottom-anchored progress display.

        Args:
            message: Setup message to display
        """
        self.console.print(f"ℹ️  {message}", style="cyan")

    def handle_progress_update(self, content: Union[str, RenderableType]) -> None:
        """Handle progress updates by updating bottom-anchored display.

        Progress updates should appear in the fixed bottom area without
        affecting scrolling content above.

        Args:
            content: Progress information to display (string or Rich renderable)

        Thread-safe: Protected by internal lock to prevent concurrent access to live_component.
        """
        with self._lock:
            if self.is_active and self.live_component is not None:
                self.live_component.update(content)

    def handle_error_message(self, file_path: Path, error_msg: str) -> None:
        """Handle error messages by printing to scrolling console area.

        Error messages should scroll above the bottom-anchored progress display.

        Args:
            file_path: File that generated the error
            error_msg: Error message details
        """
        self.console.print(
            f"❌ Failed to process {file_path}: {error_msg}", style="red"
        )

    def get_state(self) -> tuple[bool, bool]:
        """Get current state in a thread-safe manner.

        Returns:
            tuple: (is_active, has_live_component) - both boolean values
        """
        with self._lock:
            return (self.is_active, self.live_component is not None)
