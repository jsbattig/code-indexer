"""
Sync Phase Tracker for CIDX Repository Sync - Story 13: Multi-Phase Progress Tracking

Provides phase-aware progress tracking with accurate progress calculation across
different sync phases (git pull, indexing, validation) with proper phase transitions
and CIDX-compatible progress format integration.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

from code_indexer.server.middleware.correlation import get_correlation_id
from ..jobs.models import PhaseStatus


logger = logging.getLogger(__name__)


@dataclass
class PhaseProgressInfo:
    """Detailed progress information for a single phase."""

    phase_name: str
    status: PhaseStatus = PhaseStatus.PENDING
    progress: int = 0  # 0-100 percentage
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    info: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    skip_reason: Optional[str] = None
    current_file: Optional[str] = None
    files_processed: Optional[int] = None
    total_files: Optional[int] = None
    metrics: Optional[Dict[str, Any]] = field(default_factory=dict)


class SyncPhaseTracker:
    """
    Phase-aware progress tracker for multi-phase sync operations.

    Provides accurate progress calculation across different phases with proper
    weighting, seamless phase transitions, and CIDX-compatible progress reporting.

    Key Features:
    - Weighted progress calculation across all phases
    - Phase transition management with progress preservation
    - CIDX progress callback format integration
    - Progress state persistence and recovery
    """

    def __init__(
        self,
        phases: Optional[List[str]] = None,
        phase_weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize SyncPhaseTracker with phases and weights.

        Args:
            phases: List of phase names (defaults to standard sync phases)
            phase_weights: Weight of each phase for progress calculation (must sum to 1.0)

        Raises:
            ValueError: If phase weights don't sum to 1.0 or phases/weights mismatch
        """
        # Default phases for repository sync
        if phases is None:
            phases = ["git_pull", "indexing", "validation"]

        # Default weights for standard phases
        if phase_weights is None:
            phase_weights = {"git_pull": 0.1, "indexing": 0.8, "validation": 0.1}

        # Validate phase weights
        if (
            abs(sum(phase_weights.values()) - 1.0) > 0.001
        ):  # Allow small float precision errors
            raise ValueError(
                f"Phase weights must sum to 1.0, got {sum(phase_weights.values())}"
            )

        # Validate phases match weights
        if set(phases) != set(phase_weights.keys()):
            raise ValueError("Phases and phase weights must have matching keys")

        self.phases = phases
        self.phase_weights = phase_weights
        self.current_phase: Optional[str] = None
        self._overall_progress: float = 0.0

        # Initialize phase tracking
        self._phase_info: Dict[str, PhaseProgressInfo] = {}
        for phase_name in phases:
            self._phase_info[phase_name] = PhaseProgressInfo(phase_name=phase_name)

        logger.debug(
            f"SyncPhaseTracker initialized with phases: {phases}",
            extra={"correlation_id": get_correlation_id()},
        )

    @property
    def overall_progress(self) -> float:
        """Get current overall progress (0.0-100.0)."""
        return self._calculate_overall_progress()

    def start_phase(self, phase_name: str) -> PhaseProgressInfo:
        """
        Start a specific phase and update current phase.

        Args:
            phase_name: Name of phase to start

        Returns:
            PhaseProgressInfo for the started phase

        Raises:
            ValueError: If phase doesn't exist in configured phases
        """
        if phase_name not in self.phases:
            raise ValueError(f"Phase '{phase_name}' not found in phases: {self.phases}")

        self.current_phase = phase_name
        phase_info = self._phase_info[phase_name]

        phase_info.status = PhaseStatus.RUNNING
        phase_info.started_at = datetime.now(timezone.utc)
        phase_info.progress = 0

        logger.info(
            f"Started phase '{phase_name}'",
            extra={"correlation_id": get_correlation_id()},
        )
        return phase_info

    def update_phase_progress(
        self, phase_name: str, progress: int
    ) -> PhaseProgressInfo:
        """
        Update progress for a specific phase.

        Args:
            phase_name: Name of phase to update
            progress: Progress percentage (0-100)

        Returns:
            Updated PhaseProgressInfo

        Raises:
            ValueError: If phase doesn't exist or progress is invalid
        """
        if phase_name not in self.phases:
            raise ValueError(f"Phase '{phase_name}' not found in phases: {self.phases}")

        if not 0 <= progress <= 100:
            raise ValueError(f"Progress must be 0-100, got {progress}")

        phase_info = self._phase_info[phase_name]
        phase_info.progress = progress

        # If phase wasn't running, start it
        if phase_info.status == PhaseStatus.PENDING:
            phase_info.status = PhaseStatus.RUNNING
            phase_info.started_at = datetime.now(timezone.utc)

        # Update overall progress
        self._overall_progress = self._calculate_overall_progress()

        logger.debug(
            f"Phase '{phase_name}' progress updated to {progress}%",
            extra={"correlation_id": get_correlation_id()},
        )
        return phase_info

    def complete_phase(
        self, phase_name: str, result: Optional[Dict[str, Any]] = None
    ) -> PhaseProgressInfo:
        """
        Mark a phase as completed with 100% progress.

        Args:
            phase_name: Name of phase to complete
            result: Optional result data from phase completion

        Returns:
            Completed PhaseProgressInfo
        """
        phase_info = self._phase_info[phase_name]

        phase_info.status = PhaseStatus.COMPLETED
        phase_info.progress = 100
        phase_info.completed_at = datetime.now(timezone.utc)

        # Calculate duration if started
        if phase_info.started_at:
            duration = phase_info.completed_at - phase_info.started_at
            phase_info.duration_seconds = duration.total_seconds()

        # Store result data
        if result:
            if phase_info.metrics is None:
                phase_info.metrics = {}
            phase_info.metrics.update(result)

        # Update overall progress
        self._overall_progress = self._calculate_overall_progress()

        logger.info(
            f"Phase '{phase_name}' completed in {phase_info.duration_seconds:.1f}s",
            extra={"correlation_id": get_correlation_id()},
        )
        return phase_info

    def fail_phase(
        self, phase_name: str, error_message: str, error_code: Optional[str] = None
    ) -> PhaseProgressInfo:
        """
        Mark a phase as failed with error information.

        Args:
            phase_name: Name of phase that failed
            error_message: Error message describing failure
            error_code: Optional error code for categorization

        Returns:
            Failed PhaseProgressInfo
        """
        phase_info = self._phase_info[phase_name]

        phase_info.status = PhaseStatus.FAILED
        phase_info.error_message = error_message
        phase_info.error_code = error_code
        phase_info.completed_at = datetime.now(timezone.utc)

        # Calculate duration if started
        if phase_info.started_at:
            duration = phase_info.completed_at - phase_info.started_at
            phase_info.duration_seconds = duration.total_seconds()

        logger.error(
            f"Phase '{phase_name}' failed: {error_message}",
            extra={"correlation_id": get_correlation_id()},
        )
        return phase_info

    def skip_phase(self, phase_name: str, reason: str) -> PhaseProgressInfo:
        """
        Mark a phase as skipped with reason.

        Args:
            phase_name: Name of phase to skip
            reason: Reason for skipping phase

        Returns:
            Skipped PhaseProgressInfo
        """
        phase_info = self._phase_info[phase_name]

        phase_info.status = PhaseStatus.SKIPPED
        phase_info.skip_reason = reason
        phase_info.progress = 100  # Skipped phases count as complete for progress
        phase_info.completed_at = datetime.now(timezone.utc)

        # Update overall progress
        self._overall_progress = self._calculate_overall_progress()

        logger.info(
            f"Phase '{phase_name}' skipped: {reason}",
            extra={"correlation_id": get_correlation_id()},
        )
        return phase_info

    def get_phase_status(self, phase_name: str) -> PhaseProgressInfo:
        """
        Get current status of a specific phase.

        Args:
            phase_name: Name of phase to get status for

        Returns:
            PhaseProgressInfo for the requested phase

        Raises:
            ValueError: If phase doesn't exist
        """
        if phase_name not in self.phases:
            raise ValueError(f"Phase '{phase_name}' not found in phases: {self.phases}")

        return self._phase_info[phase_name]

    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive progress summary across all phases.

        Returns:
            Dictionary with overall progress, current phase, and phase details
        """
        completed_phases = [
            name
            for name, info in self._phase_info.items()
            if info.status in [PhaseStatus.COMPLETED, PhaseStatus.SKIPPED]
        ]

        phase_details = {}
        for name, info in self._phase_info.items():
            phase_details[name] = {
                "status": info.status.value,
                "progress": info.progress,
                "started_at": info.started_at.isoformat() if info.started_at else None,
                "completed_at": (
                    info.completed_at.isoformat() if info.completed_at else None
                ),
                "duration_seconds": info.duration_seconds,
                "error_message": info.error_message,
                "skip_reason": info.skip_reason,
            }

        return {
            "overall_progress": self.overall_progress,
            "current_phase": self.current_phase,
            "completed_phases": completed_phases,
            "phase_details": phase_details,
            "phase_weights": self.phase_weights,
        }

    def update_phase_progress_with_callback(
        self,
        phase_name: str,
        current: int,
        total: int,
        file_path: Path,
        info: str,
        progress_callback: Callable[[int, int, Path, str], None],
    ) -> PhaseProgressInfo:
        """
        Update phase progress and trigger CIDX-compatible progress callback.

        This method integrates phase progress tracking with the existing CIDX
        progress callback format to maintain compatibility.

        Args:
            phase_name: Name of phase being updated
            current: Current items processed
            total: Total items to process
            file_path: Current file being processed
            info: Progress information string (CIDX format)
            progress_callback: CIDX progress callback function

        Returns:
            Updated PhaseProgressInfo
        """
        # Calculate phase progress from current/total
        if total > 0:
            phase_progress = int((current / total) * 100)
        else:
            phase_progress = 0

        # Update phase info
        phase_info = self.update_phase_progress(phase_name, phase_progress)
        phase_info.current_file = str(file_path)
        phase_info.files_processed = current
        phase_info.total_files = total
        phase_info.info = info

        # Call CIDX progress callback
        progress_callback(current, total, file_path, info)

        return phase_info

    def reset(self) -> None:
        """Reset all phase progress and overall state."""
        self.current_phase = None
        self._overall_progress = 0.0

        # Reset all phase info
        for phase_name in self.phases:
            self._phase_info[phase_name] = PhaseProgressInfo(phase_name=phase_name)

        logger.info(
            "SyncPhaseTracker reset to initial state",
            extra={"correlation_id": get_correlation_id()},
        )

    def _calculate_overall_progress(self) -> float:
        """
        Calculate overall progress based on weighted phase progress.

        Returns:
            Overall progress percentage (0.0-100.0)
        """
        total_progress = 0.0

        for phase_name, weight in self.phase_weights.items():
            phase_info = self._phase_info[phase_name]

            # Use phase progress (0-100) multiplied by weight
            phase_contribution = (phase_info.progress / 100.0) * weight * 100.0
            total_progress += phase_contribution

        return round(total_progress, 2)
