"""
Real-Time Feedback Manager for eliminating silent periods - Story 04.

This module implements continuous real-time feedback throughout file processing
to ensure no silent periods longer than 10 seconds occur.

Key Components:
- RealTimeFeedbackManager: Main coordinator for continuous feedback
- HeartbeatMonitor: Provides activity updates every 5-10 seconds
- FileStatusTracker: Real-time file status transitions with icons
- Processing rate calculations and comprehensive progress formatting

Requirements:
- Immediate processing start feedback (< 100ms)
- Continuous activity indication (every 5-10 seconds)
- Real-time file status transitions (< 100ms)
- Multi-threaded processing visibility
- Comprehensive progress information
- No silent periods > 10 seconds
"""

import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEvent:
    """Represents a feedback event for analysis and monitoring."""

    timestamp: float
    current: int
    total: int
    file_path: Path
    info: str
    event_type: str


class HeartbeatMonitor:
    """Monitors processing activity and provides heartbeat updates to prevent silent periods."""

    def __init__(self, interval_seconds: float = 5.0):
        """Initialize heartbeat monitor.

        Args:
            interval_seconds: Interval between heartbeat updates (default 5 seconds)
        """
        self.interval_seconds = interval_seconds
        self.last_heartbeat_time = 0.0
        self.lock = threading.Lock()

    def start_monitoring(self, callback: Optional[Callable] = None) -> None:
        """Start heartbeat monitoring.

        Args:
            callback: Optional progress callback for initial heartbeat
        """
        with self.lock:
            self.last_heartbeat_time = time.time()

    def check_heartbeat(
        self, active_workers: int, callback: Optional[Callable]
    ) -> bool:
        """Check if heartbeat update is needed and trigger if so.

        Args:
            active_workers: Number of active worker threads
            callback: Progress callback for heartbeat updates

        Returns:
            True if heartbeat was triggered, False otherwise
        """
        current_time = time.time()

        with self.lock:
            if current_time - self.last_heartbeat_time >= self.interval_seconds:
                self.trigger_heartbeat(active_workers, callback)
                self.last_heartbeat_time = current_time
                return True

        return False

    def trigger_heartbeat(
        self, active_workers: int, callback: Optional[Callable]
    ) -> None:
        """Trigger a heartbeat update.

        Args:
            active_workers: Number of active worker threads
            callback: Progress callback for heartbeat update
        """
        if callback:
            heartbeat_msg = f"⚙️ {active_workers} workers active, processing files..."
            callback(0, 0, Path(""), info=heartbeat_msg)


class FileStatusTracker:
    """Tracks and formats real-time file status transitions with appropriate icons."""

    STATUS_ICONS = {
        "queued": "📥",
        "processing": "🔄",
        "complete": "✅",
        "error": "❌",
    }

    def __init__(self):
        """Initialize file status tracker."""
        self.lock = threading.Lock()

    def get_status_icon(self, status: str) -> str:
        """Get icon for the given status.

        Args:
            status: Status name (queued, processing, complete, error)

        Returns:
            Unicode icon for the status
        """
        return self.STATUS_ICONS.get(status.lower(), "🔄")  # Default to processing icon

    def format_status_message(self, file_path: Path, status: str) -> str:
        """Format a status message with icon and file name.

        Args:
            file_path: Path to the file
            status: Current status

        Returns:
            Formatted status message with icon
        """
        icon = self.get_status_icon(status)
        status_text = status.title()
        return f"{icon} {status_text} {file_path.name}"


class RealTimeFeedbackManager:
    """
    Main manager for real-time feedback throughout processing.

    Coordinates immediate start feedback, continuous activity heartbeat,
    real-time file status transitions, and comprehensive progress information
    to eliminate all silent periods > 10 seconds.
    """

    def __init__(
        self, total_files: int, thread_count: int, activity_interval: float = 5.0
    ):
        """Initialize real-time feedback manager.

        Args:
            total_files: Total number of files to process
            thread_count: Number of worker threads
            activity_interval: Interval for activity heartbeat updates
        """
        self.total_files = total_files
        self.thread_count = thread_count
        self.activity_interval = activity_interval

        # Initialize components
        self.heartbeat_monitor = HeartbeatMonitor(activity_interval)
        self.file_status_tracker = FileStatusTracker()

        # Timing tracking
        self.last_feedback_time = 0.0
        self.processing_start_time = 0.0

        # Rate calculation tracking
        self.lock = threading.Lock()
        self.file_completion_history: List[tuple[float, int]] = []
        self.bytes_completion_history: List[tuple[float, int]] = []
        self.rolling_window_seconds = 5.0

        logger.info(
            f"Initialized RealTimeFeedbackManager: {total_files} files, {thread_count} threads"
        )

    def initialize_continuous_feedback(self, callback: Optional[Callable]) -> None:
        """Initialize continuous feedback with immediate start message.

        Provides immediate feedback within 100ms of processing start.

        Args:
            callback: Progress callback for immediate start feedback
        """
        start_time = time.time()

        if callback:
            start_msg = (
                f"🚀 Starting parallel processing with {self.thread_count} workers"
            )
            callback(0, 0, Path(""), info=start_msg)

        # Initialize timing tracking
        with self.lock:
            self.last_feedback_time = start_time
            self.processing_start_time = start_time
            self.file_completion_history.clear()
            self.bytes_completion_history.clear()

        # Start heartbeat monitoring
        self.heartbeat_monitor.start_monitoring(callback)

        end_time = time.time()
        elapsed = end_time - start_time

        logger.info(f"Provided immediate start feedback in {elapsed:.3f}s")

    def provide_continuous_activity_updates(
        self, active_workers: int, callback: Optional[Callable]
    ) -> bool:
        """Provide continuous activity updates to prevent silent periods.

        Args:
            active_workers: Number of active worker threads
            callback: Progress callback for activity updates

        Returns:
            True if heartbeat was triggered, False otherwise
        """
        # Also check for silent period prevention
        self.ensure_no_silent_periods(callback)

        return self.heartbeat_monitor.check_heartbeat(active_workers, callback)

    def update_file_status_realtime(
        self, file_path: Path, status: str, callback: Optional[Callable]
    ) -> None:
        """Update file status in real-time with immediate feedback.

        Provides status transition updates within 100ms.

        Args:
            file_path: Path to the file
            status: New status (queued, processing, complete, error)
            callback: Progress callback for status update
        """
        if callback:
            status_msg = self.file_status_tracker.format_status_message(
                file_path, status
            )
            callback(0, 0, file_path, info=status_msg)

        # Update last feedback time
        with self.lock:
            self.last_feedback_time = time.time()

    def update_overall_progress_realtime(
        self,
        completed_files: int,
        total_files: int,
        files_per_second: float = 0.0,
        kb_per_second: float = 0.0,
        active_threads: int = 0,
        current_file: str = "",
        callback: Optional[Callable] = None,
    ) -> Any:
        """Update overall progress with comprehensive information.

        Args:
            completed_files: Number of completed files
            total_files: Total number of files
            files_per_second: Processing rate in files per second
            kb_per_second: Processing rate in KB per second
            active_threads: Number of active threads
            current_file: Name of current file being processed
            callback: Progress callback for comprehensive update
        """
        if not callback:
            return None

        # Calculate percentage
        progress_pct = (completed_files / total_files * 100) if total_files > 0 else 0

        # Format comprehensive progress information
        info_parts = [
            f"{completed_files}/{total_files} files ({progress_pct:.0f}%)",
            f"{files_per_second:.1f} files/s",
            f"{kb_per_second:.1f} KB/s",
            f"{active_threads} threads",
        ]

        if current_file:
            info_parts.append(f"processing {current_file}")

        comprehensive_info = " | ".join(info_parts)

        callback_result = callback(
            completed_files, total_files, Path(""), info=comprehensive_info
        )

        # Update last feedback time
        with self.lock:
            self.last_feedback_time = time.time()

        return callback_result

    def update_multithreaded_visibility(
        self, concurrent_files: List[Dict[str, Any]], callback: Optional[Callable]
    ) -> None:
        """Update multi-threaded processing visibility.

        Args:
            concurrent_files: List of concurrent file processing data
            callback: Progress callback for multi-threaded update
        """
        if not callback or not concurrent_files:
            return

        # Format multi-threaded display
        worker_info = []
        for file_data in concurrent_files[:8]:  # Limit to 8 workers for display
            thread_id = file_data.get("thread_id", 0)
            file_path = file_data.get("file_path", "unknown")
            progress = file_data.get("progress_percent", 0)

            worker_info.append(
                f"Worker {thread_id}: {Path(file_path).name} ({progress}%)"
            )

        if worker_info:
            multithreaded_display = " | ".join(worker_info)
            callback(0, 0, Path(""), info=multithreaded_display)

            # Update last feedback time
            with self.lock:
                self.last_feedback_time = time.time()

    def ensure_no_silent_periods(self, callback: Optional[Callable]) -> bool:
        """Monitor and prevent silent periods > 10 seconds.

        Args:
            callback: Progress callback for silent period prevention

        Returns:
            True if silent period prevention was triggered
        """
        current_time = time.time()

        with self.lock:
            time_since_feedback = current_time - self.last_feedback_time

        if time_since_feedback > 10.0:
            if callback:
                callback(0, 0, Path(""), info="⚙️ Processing continues...")

            with self.lock:
                self.last_feedback_time = current_time

            logger.warning(
                f"Prevented silent period of {time_since_feedback:.1f} seconds"
            )
            return True

        return False

    def _initialize_rate_tracking(self) -> None:
        """Initialize rate tracking for files/second and KB/second calculations."""
        with self.lock:
            self.processing_start_time = time.time()
            self.file_completion_history.clear()
            self.bytes_completion_history.clear()

    def _calculate_files_per_second(self, completed_files: int) -> float:
        """Calculate files per second using rolling window for smooth updates.

        Args:
            completed_files: Current number of completed files

        Returns:
            Files per second processing rate
        """
        current_time = time.time()

        with self.lock:
            # Don't reset start time if already set
            if not self.processing_start_time:
                # Only auto-initialize if called without explicit initialization
                self.processing_start_time = current_time
                # Return 0 for first call when auto-initializing
                return 0.0

            # Add current state to history
            self.file_completion_history.append((current_time, completed_files))

            # Remove entries older than rolling window
            cutoff_time = current_time - self.rolling_window_seconds
            self.file_completion_history = [
                (timestamp, count)
                for timestamp, count in self.file_completion_history
                if timestamp >= cutoff_time
            ]

            # Calculate rate using rolling window
            if len(self.file_completion_history) >= 2:
                oldest_time, oldest_count = self.file_completion_history[0]
                newest_time, newest_count = self.file_completion_history[-1]

                time_diff = newest_time - oldest_time
                files_diff = newest_count - oldest_count

                if (
                    time_diff > 0.1 and files_diff > 0
                ):  # Require minimum time difference
                    return float(files_diff / time_diff)

            # Fall back to total average if we have data points and elapsed time
            elapsed_total = current_time - self.processing_start_time
            if (
                elapsed_total > 0.1 and completed_files > 0
            ):  # Require minimum elapsed time
                return float(completed_files / elapsed_total)

            return 0.0

    def time_since_last_feedback(self) -> float:
        """Get time since last feedback was provided.

        Returns:
            Seconds since last feedback
        """
        with self.lock:
            return time.time() - self.last_feedback_time
