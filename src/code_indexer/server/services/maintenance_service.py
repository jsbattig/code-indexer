"""Maintenance State Service for CIDX Server.

Story #734: Job-Aware Auto-Update with Graceful Drain Mode

Provides in-memory singleton to track maintenance mode state.
NOT persisted to disk - server restart clears maintenance state.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level singleton instance
_maintenance_state: Optional["MaintenanceState"] = None
_instance_lock = threading.Lock()


def get_maintenance_state() -> "MaintenanceState":
    """Get the singleton MaintenanceState instance."""
    global _maintenance_state
    with _instance_lock:
        if _maintenance_state is None:
            _maintenance_state = MaintenanceState()
        return _maintenance_state


def _reset_maintenance_state() -> None:
    """Reset the singleton for testing. Simulates server restart."""
    global _maintenance_state
    with _instance_lock:
        _maintenance_state = None


class MaintenanceState:
    """In-memory singleton managing server maintenance mode.

    Thread-safe implementation for concurrent access.
    NOT persisted - server restart clears state (AC5).
    """

    def __init__(self) -> None:
        """Initialize maintenance state."""
        self._lock = threading.Lock()
        self._in_maintenance = False
        self._entered_at: Optional[datetime] = None
        self._job_trackers: List[Any] = []

    def is_maintenance_mode(self) -> bool:
        """Check if server is in maintenance mode."""
        with self._lock:
            return self._in_maintenance

    def enter_maintenance_mode(self) -> Dict[str, Any]:
        """Enter maintenance mode.

        Returns:
            Dict with maintenance_mode, running_jobs, queued_jobs, entered_at
        """
        with self._lock:
            if not self._in_maintenance:
                self._in_maintenance = True
                self._entered_at = datetime.now(timezone.utc)
                logger.info("Entered maintenance mode")

            running_jobs = self._get_running_jobs_count()
            queued_jobs = self._get_queued_jobs_count()

            return {
                "maintenance_mode": True,
                "running_jobs": running_jobs,
                "queued_jobs": queued_jobs,
                "entered_at": (
                    self._entered_at.isoformat() if self._entered_at else None
                ),
                "message": f"Maintenance mode active. {running_jobs} running, {queued_jobs} queued.",
            }

    def exit_maintenance_mode(self) -> Dict[str, Any]:
        """Exit maintenance mode.

        Returns:
            Dict with maintenance_mode and message
        """
        with self._lock:
            was_in_maintenance = self._in_maintenance
            self._in_maintenance = False
            self._entered_at = None

            if was_in_maintenance:
                logger.info("Exited maintenance mode")

            return {
                "maintenance_mode": False,
                "message": "Maintenance mode deactivated.",
            }

    def _get_running_jobs_count(self) -> int:
        """Get total running jobs from all trackers."""
        total = 0
        for tracker in self._job_trackers:
            try:
                total += tracker.get_running_jobs_count()
            except Exception as e:
                logger.warning(f"Failed to get running jobs from tracker: {e}")
        return total

    def _get_queued_jobs_count(self) -> int:
        """Get total queued jobs from all trackers."""
        total = 0
        for tracker in self._job_trackers:
            try:
                total += tracker.get_queued_jobs_count()
            except Exception as e:
                logger.warning(f"Failed to get queued jobs from tracker: {e}")
        return total

    def register_job_tracker(self, tracker: Any) -> None:
        """Register a job tracker for drain status monitoring."""
        with self._lock:
            if tracker not in self._job_trackers:
                self._job_trackers.append(tracker)

    def get_status(self) -> Dict[str, Any]:
        """Get current maintenance status.

        Returns:
            Dict with maintenance_mode, drained, running_jobs, queued_jobs, entered_at
        """
        with self._lock:
            running_jobs = self._get_running_jobs_count()
            queued_jobs = self._get_queued_jobs_count()
            drained = self._in_maintenance and running_jobs == 0 and queued_jobs == 0

            return {
                "maintenance_mode": self._in_maintenance,
                "drained": drained,
                "running_jobs": running_jobs,
                "queued_jobs": queued_jobs,
                "entered_at": (
                    self._entered_at.isoformat() if self._entered_at else None
                ),
            }

    def is_drained(self) -> bool:
        """Check if system is drained (no running or queued jobs).

        Only relevant when in maintenance mode.

        Returns:
            True if drained (running_jobs == 0 and queued_jobs == 0)
        """
        with self._lock:
            running = self._get_running_jobs_count()
            queued = self._get_queued_jobs_count()
            return running == 0 and queued == 0

    def get_drain_status(self) -> Dict[str, Any]:
        """Get drain status for API (AC2).

        Returns:
            Dict with drained, running_jobs, queued_jobs, estimated_drain_seconds, jobs
        """
        with self._lock:
            running_jobs = self._get_running_jobs_count()
            queued_jobs = self._get_queued_jobs_count()
            drained = running_jobs == 0 and queued_jobs == 0

            # Estimate based on running jobs (rough heuristic: 60s per job)
            estimated_seconds = 0 if drained else running_jobs * 60

            return {
                "drained": drained,
                "running_jobs": running_jobs,
                "queued_jobs": queued_jobs,
                "estimated_drain_seconds": estimated_seconds,
                "jobs": self._get_job_details_internal(),
            }

    def get_job_details(self) -> List[Dict[str, Any]]:
        """Get details of running jobs for drain status monitoring.

        Returns:
            List of job detail dicts with job_id, operation_type, started_at, progress
        """
        with self._lock:
            return self._get_job_details_internal()

    def _get_job_details_internal(self) -> List[Dict[str, Any]]:
        """Internal method to get job details (call within lock)."""
        jobs: List[Dict[str, Any]] = []
        for tracker in self._job_trackers:
            try:
                if hasattr(tracker, "get_running_jobs_details"):
                    jobs.extend(tracker.get_running_jobs_details())
            except Exception as e:
                logger.warning(f"Failed to get job details from tracker: {e}")
        return jobs
