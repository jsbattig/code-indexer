"""
Job Phase Detector for Delegation Jobs.

Story #720: Poll Delegation Job with Progress Feedback

Determines the current phase of a delegation job and extracts
phase-specific progress metrics.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class JobPhase(Enum):
    """Phases of a delegation job execution."""

    REPO_REGISTRATION = "repo_registration"
    REPO_CLONING = "repo_cloning"
    CIDX_INDEXING = "cidx_indexing"
    JOB_RUNNING = "job_running"
    DONE = "done"


@dataclass
class PhaseProgress:
    """Progress information for a specific phase."""

    phase: JobPhase
    progress: Dict[str, Any]
    message: str
    is_terminal: bool = False


class JobPhaseDetector:
    """Determines current phase of delegation job."""

    def detect_phase(self, job_state: Dict[str, Any]) -> JobPhase:
        """
        Analyze job state to determine current phase.

        Args:
            job_state: Dictionary containing job status and repository info

        Returns:
            The current JobPhase based on job state analysis
        """
        status = job_state.get("status", "")

        # Check for terminal states first
        if status in ("completed", "failed"):
            return JobPhase.DONE

        # Get repository information
        repositories = job_state.get("repositories", [])

        # If no repositories, assume job is running (ready state)
        if not repositories:
            return JobPhase.JOB_RUNNING

        # Check registration phase
        all_registered = all(repo.get("registered", False) for repo in repositories)
        if not all_registered:
            return JobPhase.REPO_REGISTRATION

        # Check cloning phase
        all_cloned = all(repo.get("cloned", False) for repo in repositories)
        if not all_cloned:
            return JobPhase.REPO_CLONING

        # Check indexing phase
        all_indexed = all(repo.get("indexed", False) for repo in repositories)
        if not all_indexed:
            return JobPhase.CIDX_INDEXING

        # All repos ready, job is running
        return JobPhase.JOB_RUNNING

    def get_progress(self, job_state: Dict[str, Any], phase: JobPhase) -> PhaseProgress:
        """
        Extract phase-specific progress metrics.

        Args:
            job_state: Dictionary containing job status and repository info
            phase: The current job phase

        Returns:
            PhaseProgress with metrics and message for the phase
        """
        # Handle null from Claude Server (key exists but value is null)
        repositories = job_state.get("repositories") or []
        repos_total = len(repositories)
        status = job_state.get("status", "")

        if phase == JobPhase.REPO_REGISTRATION:
            repos_registered = sum(
                1 for repo in repositories if repo.get("registered", False)
            )
            return PhaseProgress(
                phase=phase,
                progress={
                    "repos_total": repos_total,
                    "repos_registered": repos_registered,
                },
                message=f"Registering repositories ({repos_registered}/{repos_total})...",
                is_terminal=False,
            )

        if phase == JobPhase.REPO_CLONING:
            repos_cloned = sum(1 for repo in repositories if repo.get("cloned", False))
            return PhaseProgress(
                phase=phase,
                progress={"repos_total": repos_total, "repos_cloned": repos_cloned},
                message=f"Cloning repositories ({repos_cloned}/{repos_total})...",
                is_terminal=False,
            )

        if phase == JobPhase.CIDX_INDEXING:
            repos_indexed = sum(
                1 for repo in repositories if repo.get("indexed", False)
            )
            return PhaseProgress(
                phase=phase,
                progress={"repos_total": repos_total, "repos_indexed": repos_indexed},
                message=f"Indexing repositories ({repos_indexed}/{repos_total})...",
                is_terminal=False,
            )

        if phase == JobPhase.JOB_RUNNING:
            exchange_count = job_state.get("exchange_count", 0)
            tool_use_count = job_state.get("tool_use_count", 0)
            return PhaseProgress(
                phase=phase,
                progress={
                    "exchange_count": exchange_count,
                    "tool_use_count": tool_use_count,
                },
                message=f"Processing query ({exchange_count} exchanges, {tool_use_count} tool calls)...",
                is_terminal=False,
            )

        # DONE phase
        if status == "completed":
            result = job_state.get("result", "")
            return PhaseProgress(
                phase=phase,
                progress={"result": result},
                message="Job completed successfully",
                is_terminal=True,
            )

        # Failed status
        error = job_state.get("error", "Unknown error")
        return PhaseProgress(
            phase=phase,
            progress={"error": error},
            message=f"Job failed: {error}",
            is_terminal=True,
        )
