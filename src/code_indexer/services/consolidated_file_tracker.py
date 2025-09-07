"""
Consolidated file tracking system.

This module consolidates the three duplicate file tracking systems:
1. FileLineTracker (file_line_tracker.py)
2. ConcurrentFileDisplay (multi_threaded_display.py)
3. HighThroughputProcessor._active_threads

Provides a single, thread-safe solution that eliminates code duplication
and fixes race conditions and lock contention issues.
"""

import logging
import time
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class FileStatus(Enum):
    """File processing status enumeration."""

    QUEUED = "queued"
    CHUNKING = "chunking"
    VECTORIZING = "vectorizing"
    STARTING = "starting..."
    PROCESSING = "processing"
    COMPLETING = "finalizing..."
    COMPLETE = "complete"


@dataclass
class FileTrackingData:
    """Complete file tracking data structure."""

    thread_id: int
    file_path: Path
    file_size: int
    status: FileStatus
    start_time: float
    completion_time: Optional[float] = None
    estimated_seconds: int = 5


class ConsolidatedFileTracker:
    """Consolidated file tracking system.

    Thread-safe tracker that replaces:
    - FileLineTracker for individual file display
    - ConcurrentFileDisplay for multi-threaded display
    - HighThroughputProcessor._active_threads for concurrent data

    Features:
    - Thread-safe operations with minimal lock contention
    - No file I/O in critical sections
    - Race condition-free cleanup
    - Automatic cleanup of completed files after 3 seconds
    - Support for up to max_concurrent_files concurrent files
    """

    def __init__(
        self, max_concurrent_files: int = 8, cleanup_delay_seconds: float = 3.0
    ):
        """Initialize consolidated file tracker.

        Args:
            max_concurrent_files: Maximum number of concurrent files to track
            cleanup_delay_seconds: Delay before cleaning up completed files
        """
        self.max_concurrent_files = max_concurrent_files
        self.cleanup_delay_seconds = cleanup_delay_seconds

        # Thread-safe data storage
        self._active_files: Dict[int, FileTrackingData] = {}
        self._lock = threading.Lock()

        # Thread counter for consistent ordering
        self._next_display_order = 0
        self._display_order_lock = threading.Lock()

        # PERFORMANCE FIX: Cleanup thread to avoid doing work in hot path
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()
        self._start_cleanup_thread()

    def start_file_processing(
        self, thread_id: int, file_path: Path, file_size: Optional[int] = None
    ) -> None:
        """Start tracking file processing.

        Args:
            thread_id: Unique thread identifier
            file_path: Path to file being processed
            file_size: File size in bytes (if None, will calculate outside lock)
        """
        # Calculate file size OUTSIDE critical section to avoid lock contention
        if file_size is None:
            try:
                file_size = file_path.stat().st_size
            except OSError as e:
                # Fail explicitly - no fallbacks
                raise OSError(f"Cannot access file {file_path}: {e}") from e

        current_time = time.time()

        # Create tracking data
        tracking_data = FileTrackingData(
            thread_id=thread_id,
            file_path=file_path,
            file_size=file_size,
            status=FileStatus.STARTING,
            start_time=current_time,
            estimated_seconds=max(1, file_size // 10000),  # Simple estimation
        )

        # Enter critical section only for data structure modification
        with self._lock:
            # Enforce max concurrent files limit
            if (
                len(self._active_files) >= self.max_concurrent_files
                and thread_id not in self._active_files
            ):
                self._remove_oldest_file()

            self._active_files[thread_id] = tracking_data
            logger.debug(f"Started tracking file {file_path} on thread {thread_id}")

    def update_file_status(self, thread_id: int, status: FileStatus) -> None:
        """Update file processing status.

        Args:
            thread_id: Thread identifier to update
            status: New file status
        """
        with self._lock:
            if thread_id in self._active_files:
                self._active_files[thread_id].status = status
                logger.debug(f"Updated thread {thread_id} status to {status}")

    def complete_file_processing(self, thread_id: int) -> None:
        """Mark file processing as complete and schedule cleanup.

        Args:
            thread_id: Thread identifier to complete
        """
        with self._lock:
            if thread_id in self._active_files:
                self._active_files[thread_id].status = FileStatus.COMPLETE
                self._active_files[thread_id].completion_time = time.time()
                logger.debug(f"Completed tracking for thread {thread_id}")

    def get_concurrent_files_data(self) -> List[Dict[str, Any]]:
        """Get concurrent files data for progress callback.

        Returns:
            List of file data dictionaries compatible with progress callback
        """
        with self._lock:
            # PERFORMANCE FIX: Removed cleanup from hot path - cleanup thread handles it
            # This method is called for EVERY file completion, must be fast!

            # Build concurrent files list
            concurrent_files = []

            # Sort by thread_id for consistent ordering
            for thread_id in sorted(self._active_files.keys()):
                tracking_data = self._active_files[thread_id]

                file_data = {
                    "thread_id": thread_id,
                    "file_path": str(tracking_data.file_path),
                    "file_size": tracking_data.file_size,
                    "estimated_seconds": tracking_data.estimated_seconds,
                    "status": tracking_data.status.value,
                }
                concurrent_files.append(file_data)

            return concurrent_files

    def get_formatted_display_lines(self) -> List[str]:
        """Get formatted display lines for Rich display.

        Returns:
            List of formatted line strings with tree-style indicators
        """
        with self._lock:
            # PERFORMANCE FIX: Removed cleanup from hot path - cleanup thread handles it

            display_lines = []

            # Sort by thread_id for consistent display order
            for thread_id in sorted(self._active_files.keys()):
                tracking_data = self._active_files[thread_id]
                formatted_line = self._format_display_line(tracking_data)
                display_lines.append(formatted_line)

            return display_lines

    def get_active_file_count(self) -> int:
        """Get count of currently active files.

        Returns:
            Number of active files being tracked
        """
        with self._lock:
            # PERFORMANCE FIX: Removed cleanup from hot path - cleanup thread handles it
            return len(self._active_files)

    def _remove_oldest_file(self) -> None:
        """Remove oldest file to make room for new file.

        Note: Must be called within lock context.
        """
        if not self._active_files:
            return

        # Find oldest file by start time
        oldest_thread_id = min(
            self._active_files.keys(),
            key=lambda tid: self._active_files[tid].start_time,
        )

        del self._active_files[oldest_thread_id]
        logger.debug(f"Removed oldest file thread {oldest_thread_id} to make room")

    def _cleanup_expired_files(self) -> None:
        """Clean up completed files that have exceeded cleanup delay.

        Note: Must be called within lock context.
        """
        current_time = time.time()
        expired_thread_ids = []

        for thread_id, tracking_data in self._active_files.items():
            if (
                tracking_data.status == FileStatus.COMPLETE
                and tracking_data.completion_time is not None
                and current_time - tracking_data.completion_time
                >= self.cleanup_delay_seconds
            ):
                expired_thread_ids.append(thread_id)

        # Remove expired files
        for thread_id in expired_thread_ids:
            del self._active_files[thread_id]
            logger.debug(f"Cleaned up expired completed file thread {thread_id}")

    def _format_display_line(self, tracking_data: FileTrackingData) -> str:
        """Format a single file line for display.

        Args:
            tracking_data: File tracking data to format

        Returns:
            Formatted line string with tree-style indicator
        """
        # Format file size
        size_str = self._format_file_size(tracking_data.file_size)

        # Calculate elapsed time
        current_time = time.time()
        elapsed_seconds = current_time - tracking_data.start_time
        elapsed_str = self._format_elapsed_time(elapsed_seconds)

        # Format status with user-friendly display
        if tracking_data.status == FileStatus.QUEUED:
            status_str = "📥 Queued"
        elif tracking_data.status == FileStatus.CHUNKING:
            status_str = "🔄 Chunking"
        elif tracking_data.status == FileStatus.VECTORIZING:
            status_str = "🔄 Vectorizing"
        elif tracking_data.status == FileStatus.STARTING:
            status_str = "📥 Starting"
        elif tracking_data.status == FileStatus.PROCESSING:
            status_str = "🔄 Processing"
        elif tracking_data.status == FileStatus.COMPLETING:
            status_str = "📝 Finalizing"
        elif tracking_data.status == FileStatus.COMPLETE:
            status_str = "✅ Complete"
        else:
            status_str = tracking_data.status.value

        return f"├─ {tracking_data.file_path.name} ({size_str}, {elapsed_str}) {status_str}"

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format.

        Args:
            size_bytes: File size in bytes

        Returns:
            Human-readable size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _format_elapsed_time(self, elapsed_seconds: float) -> str:
        """Format elapsed processing time.

        Args:
            elapsed_seconds: Elapsed time in seconds

        Returns:
            Human-readable elapsed time string
        """
        # Round to nearest second, with minimum of 1s
        rounded_seconds = max(1, round(elapsed_seconds))
        return f"{rounded_seconds}s"

    def _start_cleanup_thread(self) -> None:
        """Start background cleanup thread for expired files.

        PERFORMANCE FIX: Move cleanup out of hot path to avoid lock contention.
        Cleanup runs every second in background instead of on every get_concurrent_files_data() call.
        """

        def cleanup_worker():
            """Background worker that periodically cleans up expired files."""
            while not self._cleanup_stop_event.is_set():
                # Wait 1 second between cleanups
                if self._cleanup_stop_event.wait(1.0):
                    break

                # Perform cleanup with minimal lock time
                with self._lock:
                    self._cleanup_expired_files()

            logger.debug("Cleanup thread stopped")

        self._cleanup_thread = threading.Thread(
            target=cleanup_worker,
            name="FileTrackerCleanup",
            daemon=True,  # Daemon thread will exit when main program exits
        )
        self._cleanup_thread.start()
        logger.debug("Started file tracker cleanup thread")

    def stop_cleanup_thread(self) -> None:
        """Stop the background cleanup thread.

        Call this when shutting down to cleanly stop the cleanup thread.
        """
        if self._cleanup_thread:
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=2.0)
            logger.debug("Stopped file tracker cleanup thread")
