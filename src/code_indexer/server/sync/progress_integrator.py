"""
Progress Callback Integrator for CIDX Server sync operations - Enhanced with SyncPhaseTracker.

Integrates progress callbacks from git and indexing operations with
job status updates and multi-phase progress tracking, providing comprehensive
real-time progress tracking through the job management system.
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from code_indexer.server.middleware.correlation import get_correlation_id
from ..jobs.manager import SyncJobManager
from .progress_tracker import SyncPhaseTracker


# Configure logging
logger = logging.getLogger(__name__)


class ProgressCallbackIntegrator:
    """
    Integrates progress callbacks with job status updates and multi-phase progress tracking.

    Enhanced version that uses SyncPhaseTracker for accurate multi-phase progress
    calculation while maintaining compatibility with existing progress callbacks.
    Monitors progress from git and indexing operations, detects which phase
    is active, and updates job status with appropriate progress information.
    """

    def __init__(
        self,
        job_manager: SyncJobManager,
        job_id: str,
        phases: Optional[list] = None,
        phase_weights: Optional[Dict[str, float]] = None,
        min_update_interval: float = 0.05,  # 50ms minimum between updates
        track_detailed_metrics: bool = True,  # Enable detailed metrics by default
    ):
        """
        Initialize ProgressCallbackIntegrator with enhanced multi-phase tracking.

        Args:
            job_manager: SyncJobManager instance for job updates
            job_id: Job ID to update
            phases: Optional list of phases (defaults to ["git_pull", "indexing", "validation"])
            phase_weights: Optional phase weights for progress calculation
            min_update_interval: Minimum time between job updates (seconds)
            track_detailed_metrics: Track detailed metrics like embedding rate
        """
        self.job_manager = job_manager
        self.job_id = job_id
        self.min_update_interval = min_update_interval
        self.track_detailed_metrics = track_detailed_metrics

        # Initialize SyncPhaseTracker for accurate multi-phase progress calculation
        if phases is None:
            phases = ["git_pull", "indexing", "validation"]
        if phase_weights is None:
            phase_weights = {"git_pull": 0.1, "indexing": 0.8, "validation": 0.1}

        self.phase_tracker = SyncPhaseTracker(
            phases=phases, phase_weights=phase_weights
        )

        # Rate limiting
        self._last_update_time = 0.0
        self._last_progress_by_phase: Dict[str, int] = {}

        # Phase detection patterns
        self._git_patterns = [
            r"validating repository",
            r"creating.*backup",
            r"executing git pull",
            r"git pull.*completed",
            r"analyzing changes",
            r"fetching from remote",
        ]

        self._indexing_patterns = [
            r"starting.*cidx indexing",
            r"internal cidx indexing",
            r"\d+/\d+ files.*\d+.*emb/s",  # "25/100 files (25%) | 5.2 emb/s"
            r"processing file embeddings",
            r"building vector database",
            r"indexing completed",
        ]

        logger.debug(f"ProgressCallbackIntegrator initialized for job {job_id}")

    def progress_callback(self, current: int, total: int, file_path: Path, info: str):
        """
        Enhanced progress callback with multi-phase tracking integration.

        Args:
            current: Current progress count
            total: Total count (0 for setup messages)
            file_path: Current file being processed
            info: Progress information string
        """
        try:
            # Rate limiting - avoid spam updates
            current_time = time.time()
            if current_time - self._last_update_time < self.min_update_interval:
                return

            # Detect which phase this progress belongs to
            phase = self._detect_phase_from_info(info)

            # Handle setup messages (total=0)
            if total == 0:
                self._update_phase_info(phase, info)
                return

            # Ensure phase is started in phase tracker
            if phase in self.phase_tracker.phases:
                current_tracker_phase = self.phase_tracker.current_phase
                if current_tracker_phase != phase:
                    if (
                        current_tracker_phase
                        and current_tracker_phase in self.phase_tracker.phases
                    ):
                        # Complete previous phase if not already completed
                        prev_status = self.phase_tracker.get_phase_status(
                            current_tracker_phase
                        )
                        if prev_status.status.value == "running":
                            self.phase_tracker.complete_phase(current_tracker_phase)

                    # Start new phase in tracker
                    self.phase_tracker.start_phase(phase)

            # Calculate phase progress percentage
            phase_progress = int((current / total * 100)) if total > 0 else 0

            # Check if this is a meaningful progress change
            last_progress = self._last_progress_by_phase.get(phase, -1)
            if abs(phase_progress - last_progress) < 5 and phase_progress < 100:
                # Skip small progress changes (less than 5%) unless completion
                return

            # Update phase tracker with progress
            if phase in self.phase_tracker.phases:
                self.phase_tracker.update_phase_progress(phase, phase_progress)
                overall_progress = self.phase_tracker.overall_progress

                # Update job manager with comprehensive progress state
                self.job_manager.update_job_progress(
                    job_id=self.job_id,
                    overall_progress=overall_progress,
                    current_phase=phase,
                    files_processed=current,
                    total_files=total,
                    info=info,
                    processing_speed=self._extract_processing_speed(info),
                )

                # Update job manager phase system (legacy compatibility)
                self._ensure_legacy_phase_started(phase)
                self._update_phase_progress(
                    phase, current, total, phase_progress, file_path, info
                )

                # Complete phase if at 100%
                if phase_progress == 100:
                    self.phase_tracker.complete_phase(phase)
                    self._complete_phase_if_needed(phase)

                # Create recovery checkpoints at significant progress points
                if phase_progress % 25 == 0 and phase_progress > 0:  # Every 25%
                    self._create_recovery_checkpoint(
                        phase, current, total, file_path, overall_progress
                    )

            # Update rate limiting state
            self._last_update_time = current_time
            self._last_progress_by_phase[phase] = phase_progress

        except Exception as e:
            # Don't let progress callback errors break the operation
            logger.warning(
                f"Progress callback integration error: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def _detect_phase_from_info(self, info: str) -> str:
        """
        Detect which phase is active based on progress info.

        Args:
            info: Progress information string

        Returns:
            Phase name ("git_pull" or "indexing")
        """
        info_lower = info.lower()

        # Check git patterns first
        for pattern in self._git_patterns:
            if re.search(pattern, info_lower):
                return "git_pull"

        # Check indexing patterns
        for pattern in self._indexing_patterns:
            if re.search(pattern, info_lower):
                return "indexing"

        # Default fallback - try to infer from current job state
        try:
            job = self.job_manager.get_job(self.job_id)
            current_phase = job.get("current_phase", "git_pull")
            return str(current_phase) if current_phase else "git_pull"
        except Exception:
            return "git_pull"  # Safe default

    def _update_phase_info(self, phase: str, info: str):
        """
        Update phase information without changing progress.

        Args:
            phase: Phase name
            info: Information string
        """
        try:
            self.job_manager.update_phase_progress(
                job_id=self.job_id,
                phase=phase,
                progress=None,  # Don't change progress
                info=info,
            )
        except Exception as e:
            logger.warning(
                f"Failed to update phase info for {phase}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def _update_phase_progress(
        self,
        phase: str,
        current: int,
        total: int,
        progress: int,
        file_path: Path,
        info: str,
    ):
        """
        Update phase progress with detailed information.

        Args:
            phase: Phase name
            current: Current progress count
            total: Total count
            progress: Progress percentage
            file_path: Current file being processed
            info: Progress information string
        """
        try:
            # Extract detailed metrics if enabled
            metrics = {}
            if self.track_detailed_metrics and phase == "indexing":
                metrics = self._extract_indexing_metrics(info)

            # Update phase progress
            self.job_manager.update_phase_progress(
                job_id=self.job_id,
                phase=phase,
                progress=progress,
                info=info,
                current_file=str(file_path) if file_path != Path("") else None,
                files_processed=current if phase == "indexing" else None,
                total_files=total if phase == "indexing" else None,
                metrics=metrics if metrics else None,
            )

        except Exception as e:
            logger.warning(
                f"Failed to update phase progress for {phase}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def _extract_indexing_metrics(self, info: str) -> Dict[str, Any]:
        """
        Extract detailed metrics from indexing progress info.

        Args:
            info: Progress information string like "25/100 files (25%) | 12.5 emb/s | 4 threads"

        Returns:
            Dictionary with extracted metrics
        """
        metrics = {}

        try:
            # Extract embedding rate (e.g., "12.5 emb/s")
            emb_rate_match = re.search(r"(\d+\.?\d*)\s*emb/s", info)
            if emb_rate_match:
                metrics["embedding_rate"] = float(emb_rate_match.group(1))

            # Extract thread count (e.g., "4 threads")
            threads_match = re.search(r"(\d+)\s*threads?", info)
            if threads_match:
                metrics["thread_count"] = int(threads_match.group(1))

            # Extract file counts (e.g., "25/100 files")
            files_match = re.search(r"(\d+)/(\d+)\s*files", info)
            if files_match:
                metrics["files_processed"] = int(files_match.group(1))
                metrics["total_files"] = int(files_match.group(2))

        except Exception as e:
            logger.debug(f"Failed to extract metrics from '{info}': {e}")

        return metrics

    def _ensure_phase_started(self, phase: str):
        """
        Ensure phase is started before updating progress.

        Args:
            phase: Phase name
        """
        try:
            job = self.job_manager.get_job(self.job_id)
            if job.get("phases", {}).get(phase, {}).get("status") == "pending":
                self.job_manager.start_phase(self.job_id, phase)
        except Exception as e:
            logger.debug(f"Could not start phase {phase}: {e}")

    def _complete_phase_if_needed(self, phase: str):
        """
        Complete phase if it's running and at 100% progress.

        Args:
            phase: Phase name
        """
        try:
            job = self.job_manager.get_job(self.job_id)
            phase_info = job.get("phases", {}).get(phase, {})

            phase_status = phase_info.get("status")
            if (
                phase_status == "running" or str(phase_status) == "running"
            ) and phase_info.get("progress") == 100:

                self.job_manager.complete_phase(
                    job_id=self.job_id, phase=phase, result={"auto_completed": True}
                )
                logger.debug(f"Auto-completed phase {phase} at 100% progress")

        except Exception as e:
            logger.debug(f"Could not complete phase {phase}: {e}")

    def _handle_phase_transition(self, new_phase: str):
        """
        Handle automatic phase transitions based on progress callbacks.

        When progress from a new phase is detected, this method ensures
        the previous phase is completed and the new phase is ready.

        Args:
            new_phase: The phase detected from current progress
        """
        try:
            job = self.job_manager.get_job(self.job_id)
            current_phase = job.get("current_phase")

            # If we're moving to a different phase
            if current_phase != new_phase and current_phase is not None:
                current_phase_info = job.get("phases", {}).get(current_phase, {})

                # Complete current phase if it's running but not completed
                if current_phase_info.get("status") == "running":
                    self.job_manager.complete_phase(
                        job_id=self.job_id,
                        phase=current_phase,
                        result={"auto_completed_for_transition": True},
                    )
                    logger.debug(
                        f"Auto-completed phase {current_phase} to transition to {new_phase}"
                    )

        except Exception as e:
            logger.debug(f"Could not handle phase transition to {new_phase}: {e}")

    # Enhanced methods for SyncPhaseTracker integration

    def _extract_processing_speed(self, info: str) -> Optional[float]:
        """
        Extract processing speed from info string.

        Args:
            info: Progress information string

        Returns:
            Processing speed in appropriate units or None
        """
        try:
            # Look for patterns like "2.5 emb/s" or "1.8 files/sec"
            emb_match = re.search(r"(\d+\.?\d*)\s*emb/s", info)
            if emb_match:
                return float(emb_match.group(1))

            files_match = re.search(r"(\d+\.?\d*)\s*files?/s", info)
            if files_match:
                return float(files_match.group(1))

        except (ValueError, AttributeError):
            pass

        return None

    def _ensure_legacy_phase_started(self, phase: str):
        """
        Ensure phase is started in legacy job manager phase system.

        Args:
            phase: Phase name
        """
        try:
            self._ensure_phase_started(phase)
        except Exception as e:
            logger.debug(f"Could not start legacy phase {phase}: {e}")

    def _create_recovery_checkpoint(
        self,
        phase: str,
        current: int,
        total: int,
        file_path: Path,
        overall_progress: float,
    ) -> None:
        """
        Create recovery checkpoint using job manager persistence.

        Args:
            phase: Current phase name
            current: Current items processed
            total: Total items to process
            file_path: Current file being processed
            overall_progress: Overall progress percentage
        """
        try:
            checkpoint_data = {
                "phase": phase,
                "progress": overall_progress,
                "last_file": str(file_path),
                "files_processed": current,
                "total_files": total,
                "phase_progress": (current / total * 100) if total > 0 else 0,
            }

            self.job_manager.create_recovery_checkpoint(self.job_id, checkpoint_data)
            logger.debug(
                f"Created recovery checkpoint for job {self.job_id} at {overall_progress:.1f}%"
            )

        except Exception as e:
            logger.warning(
                f"Failed to create recovery checkpoint for job {self.job_id}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def get_phase_tracker_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive progress summary from phase tracker.

        Returns:
            Dictionary with detailed progress information
        """
        try:
            return self.phase_tracker.get_progress_summary()
        except Exception as e:
            logger.error(
                f"Error getting phase tracker summary: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return {"overall_progress": 0.0, "error": str(e)}

    def start_phase(self, phase_name: str) -> None:
        """
        Manually start a phase in progress tracker and job manager.

        Args:
            phase_name: Name of phase to start
        """
        try:
            if phase_name in self.phase_tracker.phases:
                self.phase_tracker.start_phase(phase_name)

            self._ensure_legacy_phase_started(phase_name)
            logger.info(f"Manually started phase '{phase_name}' for job {self.job_id}")

        except Exception as e:
            logger.error(
                f"Error manually starting phase {phase_name}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def complete_phase(
        self, phase_name: str, result: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Manually complete a phase in progress tracker and job manager.

        Args:
            phase_name: Name of phase to complete
            result: Optional result data from phase completion
        """
        try:
            if phase_name in self.phase_tracker.phases:
                self.phase_tracker.complete_phase(phase_name, result)

            # Update overall progress from tracker
            overall_progress = self.phase_tracker.overall_progress
            self.job_manager.update_job_progress(
                job_id=self.job_id,
                overall_progress=overall_progress,
                current_phase=self.phase_tracker.current_phase,
            )

            # Complete in legacy system
            try:
                self.job_manager.complete_phase(self.job_id, phase_name, result or {})
            except Exception as e:
                logger.debug(f"Legacy phase completion failed for {phase_name}: {e}")

            logger.info(
                f"Manually completed phase '{phase_name}' for job {self.job_id}"
            )

        except Exception as e:
            logger.error(
                f"Error manually completing phase {phase_name}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    def fail_phase(
        self, phase_name: str, error_message: str, error_code: Optional[str] = None
    ) -> None:
        """
        Manually fail a phase in progress tracker and job manager.

        Args:
            phase_name: Name of phase that failed
            error_message: Error message describing failure
            error_code: Optional error code for categorization
        """
        try:
            if phase_name in self.phase_tracker.phases:
                self.phase_tracker.fail_phase(phase_name, error_message, error_code)

            # Mark job as interrupted in job manager
            self.job_manager.mark_job_interrupted(
                self.job_id,
                {
                    "error_message": f"Phase {phase_name} failed: {error_message}",
                    "interrupted_phase": phase_name,
                    "error_code": error_code,
                },
            )

            logger.error(
                f"Manually failed phase '{phase_name}' for job {self.job_id}: {error_message}",
                extra={"correlation_id": get_correlation_id()},
            )

        except Exception as e:
            logger.error(
                f"Error manually failing phase {phase_name}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
