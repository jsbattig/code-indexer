"""Ramping trigger detection and hysteresis management.

This module handles the detection of when to trigger ramping down behavior
and provides hysteresis to prevent rapid oscillation.
"""

import time
from typing import Optional


class RampingTriggerDetector:
    """Detects when ramping down behavior should be triggered."""

    def __init__(self, hysteresis_buffer: int = 2):
        """Initialize ramping trigger detector.

        Args:
            hysteresis_buffer: Buffer size to prevent oscillation
        """
        self.hysteresis_buffer = hysteresis_buffer
        self.ramping_started_at: Optional[float] = None
        self.is_ramping = False

    def should_trigger_ramping(self, active_threads: int, files_remaining: int) -> bool:
        """Determine if ramping down should be triggered.

        Args:
            active_threads: Number of active worker threads
            files_remaining: Number of files still to be processed

        Returns:
            True if ramping should be triggered
        """
        return files_remaining < active_threads

    def mark_ramping_started(self) -> None:
        """Mark that ramping has started."""
        self.ramping_started_at = time.time()
        self.is_ramping = True

    def should_continue_ramping(
        self, active_threads: int, files_remaining: int
    ) -> bool:
        """Determine if ramping should continue (with hysteresis).

        Args:
            active_threads: Number of active worker threads
            files_remaining: Number of files still to be processed

        Returns:
            True if ramping should continue
        """
        if not self.is_ramping:
            return False

        # Apply hysteresis buffer - continue ramping unless significant increase
        # Only reverse if files_remaining significantly exceeds active_threads
        return files_remaining < (active_threads - self.hysteresis_buffer)

    def is_final_completion(self, active_threads: int, files_remaining: int) -> bool:
        """Detect if processing has reached final completion.

        Args:
            active_threads: Number of active worker threads
            files_remaining: Number of files still to be processed

        Returns:
            True if final completion has been reached
        """
        # Final completion when no threads are active
        # (files_remaining might still be > 0 if queued but no active processing)
        return active_threads == 0
