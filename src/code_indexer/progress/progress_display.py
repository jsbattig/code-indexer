"""Rich Live progress display manager for bottom-anchored progress reporting.

This module provides Rich Live component integration that creates bottom-locked
progress display while allowing other output to scroll above it.
"""

import logging
import queue
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

        # Async progress queue for non-blocking updates (Bug #470 fix)
        self._progress_queue: Optional[queue.Queue] = None
        self._progress_worker: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

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

            # Start async progress worker thread (Bug #470 fix)
            self._progress_queue = queue.Queue(maxsize=100)
            self._shutdown_event.clear()
            self._progress_worker = threading.Thread(
                target=self._async_progress_worker,
                name="progress_worker",
                daemon=True,
            )
            self._progress_worker.start()

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
        # Shutdown async worker thread first
        if self._progress_queue is not None:
            self._progress_queue.put(None)  # Shutdown signal
        if self._progress_worker is not None:
            self._progress_worker.join(timeout=2.0)  # Increased from 1.0s to prevent thread leaks

            # Warn if thread didn't terminate (potential thread leak)
            if self._progress_worker.is_alive():
                logging.warning(
                    "Progress worker thread did not terminate within 2.0s timeout. "
                    "Potential thread leak detected."
                )

        with self._lock:
            if self.live_component is not None:
                self.live_component.stop()
                self.live_component = None
            self.is_active = False
            self._progress_worker = None
            self._progress_queue = None

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

    def _async_progress_worker(self) -> None:
        """Worker thread that processes queued progress updates.

        Handles exceptions during update to prevent worker thread death.
        """
        # Type assertion: queue is guaranteed to be initialized before worker starts
        assert self._progress_queue is not None, "Worker started without queue"

        while True:
            content = self._progress_queue.get()
            if content is None:  # Shutdown signal
                break
            with self._lock:
                if self.is_active and self.live_component is not None:
                    try:
                        self.live_component.update(content)
                    except Exception as e:
                        # Log error but continue processing - don't let worker thread die
                        logging.error(
                            f"Error updating progress display: {e}. "
                            "Continuing to process subsequent updates."
                        )

    def async_handle_progress_update(self, content: Union[str, RenderableType]) -> None:
        """Queue progress update for async processing.

        Gracefully handles queue overflow by dropping updates instead of raising
        queue.Full exception. Progress updates are not critical - drops are acceptable
        to prevent crashes during high-throughput indexing.
        """
        if self._progress_queue is not None:
            try:
                self._progress_queue.put_nowait(content)
            except queue.Full:
                # Drop update gracefully - progress updates are not critical
                # Better to lose occasional updates than crash the process
                pass
