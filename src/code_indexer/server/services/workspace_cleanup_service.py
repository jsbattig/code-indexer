"""
Workspace Cleanup Service for SCIP Self-Healing (Story #647).

Provides automatic cleanup of temporary SCIP workspace directories
after configurable retention period, with safety checks for active jobs.

Features:
- Periodic cleanup job (AC2)
- Configurable retention period (AC1)
- Active job protection (AC6)
- Recent modification detection (AC6)
- Graceful error handling (AC6)
- Audit log preservation (AC3)
"""

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    JobStatus,
)
from code_indexer.server.utils.config_manager import ServerConfig

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """
    Result of workspace cleanup operation.

    Provides comprehensive summary of cleanup execution including
    counts, space reclaimed, errors, and execution time.
    """

    workspaces_scanned: int = 0
    workspaces_deleted: int = 0
    workspaces_preserved: int = 0
    space_reclaimed_bytes: int = 0
    errors: List[str] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0


class WorkspaceCleanupService:
    """
    Service for automatic cleanup of SCIP self-healing workspaces.

    Manages periodic cleanup of temporary workspace directories created
    during SCIP dependency resolution, with safety checks to protect
    active jobs and recently modified workspaces.

    AC2: Periodic cleanup job with workspace scanning and deletion
    AC6: Safety checks for active jobs and recent modifications
    """

    def __init__(
        self,
        config: ServerConfig,
        job_manager: BackgroundJobManager,
        workspace_root: str = "/tmp",
    ):
        """
        Initialize workspace cleanup service.

        Args:
            config: Server configuration with retention_days setting
            job_manager: Background job manager for checking active jobs
            workspace_root: Root directory containing workspaces (default: /tmp)
        """
        self.retention_days = config.scip_workspace_retention_days
        self.job_manager = job_manager
        self.workspace_root = Path(workspace_root)

        # Tracking for status API (AC5)
        self.last_cleanup_time: Optional[datetime] = None

    def scan_workspaces(self) -> List[Path]:
        """
        Scan workspace root for SCIP workspace directories.

        Returns:
            List of workspace directory paths matching cidx-scip-* pattern
        """
        workspaces = []

        if not self.workspace_root.exists():
            logger.warning(
                f"Workspace root does not exist: {self.workspace_root}"
            )
            return workspaces

        for item in self.workspace_root.iterdir():
            if item.is_dir() and item.name.startswith("cidx-scip-"):
                workspaces.append(item)

        return workspaces

    def is_workspace_expired(self, workspace_path: Path) -> bool:
        """
        Check if workspace has exceeded retention period.

        Uses directory modification time (mtime) to determine age.
        Note: Linux doesn't track true creation time, so we use mtime.

        Args:
            workspace_path: Path to workspace directory

        Returns:
            True if workspace is older than retention period, False otherwise
        """
        try:
            stats = workspace_path.stat()
            # Use mtime (modification time) since Linux doesn't track creation time
            # ctime is "change time" not "creation time" on Linux
            modification_time = stats.st_mtime
            current_time = time.time()

            age_seconds = current_time - modification_time
            age_days = age_seconds / (24 * 3600)

            return age_days > self.retention_days

        except Exception as e:
            logger.error(
                f"Error checking workspace age for {workspace_path}: {e}"
            )
            return False

    def is_workspace_recently_modified(
        self, workspace_path: Path, threshold_hours: int = 24
    ) -> bool:
        """
        Check if workspace has been modified within threshold period.

        AC6: Skip workspaces modified in last 24 hours regardless of age.
        Checks both directory and all files/subdirectories within.

        Args:
            workspace_path: Path to workspace directory
            threshold_hours: Modification threshold in hours (default: 24)

        Returns:
            True if workspace was modified within threshold, False otherwise
        """
        try:
            current_time = time.time()
            threshold_seconds = threshold_hours * 3600

            # Check directory itself
            dir_mtime = workspace_path.stat().st_mtime
            if (current_time - dir_mtime) < threshold_seconds:
                return True

            # Check all files/subdirectories (creating files doesn't update dir mtime)
            for entry in workspace_path.rglob("*"):
                entry_mtime = entry.stat().st_mtime
                if (current_time - entry_mtime) < threshold_seconds:
                    return True

            return False

        except Exception as e:
            logger.error(
                f"Error checking workspace modification time for {workspace_path}: {e}"
            )
            return False

    def get_active_job_ids(self) -> set:
        """
        Get set of job IDs for jobs in RESOLVING_PREREQUISITES state.

        AC6: Protect workspaces for active resolution jobs.

        Returns:
            Set of job IDs that are currently resolving prerequisites
        """
        active_job_ids = set()

        with self.job_manager._lock:
            for job_id, job in self.job_manager.jobs.items():
                if job.status == JobStatus.RESOLVING_PREREQUISITES:
                    # Extract job ID from workspace pattern
                    # Workspace format: cidx-scip-{job_id}
                    active_job_ids.add(job.job_id)

        return active_job_ids

    def extract_job_id_from_workspace(self, workspace_path: Path) -> Optional[str]:
        """
        Extract job ID from workspace directory name.

        Workspace format: cidx-scip-{job_id}

        Args:
            workspace_path: Path to workspace directory

        Returns:
            Job ID if extractable, None otherwise
        """
        name = workspace_path.name
        if name.startswith("cidx-scip-"):
            return name.replace("cidx-scip-", "")
        return None

    def calculate_directory_size(self, directory_path: Path) -> int:
        """
        Calculate total size of directory in bytes.

        Args:
            directory_path: Path to directory

        Returns:
            Total size in bytes
        """
        total_size = 0

        try:
            for entry in directory_path.rglob("*"):
                if entry.is_file():
                    total_size += entry.stat().st_size
        except Exception as e:
            logger.warning(
                f"Error calculating size for {directory_path}: {e}"
            )

        return total_size

    def delete_workspace(self, workspace_path: Path) -> tuple[bool, int]:
        """
        Delete workspace directory and calculate space reclaimed.

        Args:
            workspace_path: Path to workspace directory to delete

        Returns:
            Tuple of (success: bool, space_reclaimed: int)
        """
        try:
            # Calculate size before deletion
            size = self.calculate_directory_size(workspace_path)

            # Delete directory tree
            shutil.rmtree(workspace_path)

            logger.info(
                f"Deleted workspace {workspace_path.name}, "
                f"reclaimed {size:,} bytes"
            )

            return True, size

        except Exception as e:
            logger.error(
                f"Failed to delete workspace {workspace_path}: {e}"
            )
            return False, 0

    def cleanup_workspaces(self) -> CleanupResult:
        """
        Execute workspace cleanup operation.

        Scans for expired workspaces and deletes them with safety checks:
        - Skip workspaces for active jobs (RESOLVING_PREREQUISITES)
        - Skip workspaces modified in last 24 hours
        - Handle deletion errors gracefully
        - Track space reclaimed

        AC2: Core cleanup logic
        AC6: Safety checks and error handling

        Returns:
            CleanupResult with comprehensive cleanup summary
        """
        start_time = time.time()
        result = CleanupResult()

        # Get active job IDs to protect their workspaces (AC6)
        active_job_ids = self.get_active_job_ids()

        logger.info(
            f"Starting workspace cleanup (retention: {self.retention_days} days, "
            f"active jobs: {len(active_job_ids)})"
        )

        # Scan for workspace directories
        workspaces = self.scan_workspaces()
        result.workspaces_scanned = len(workspaces)

        for workspace_path in workspaces:
            workspace_name = workspace_path.name

            # Extract job ID from workspace name
            job_id = self.extract_job_id_from_workspace(workspace_path)

            # AC6: Skip workspaces for active jobs
            if job_id and job_id in active_job_ids:
                logger.info(
                    f"Skipping {workspace_name}: active job {job_id}"
                )
                result.skipped.append(
                    {
                        "workspace": workspace_name,
                        "reason": "active_job",
                        "job_id": job_id,
                    }
                )
                result.workspaces_preserved += 1
                continue

            # AC6: Skip recently modified workspaces
            if self.is_workspace_recently_modified(workspace_path):
                logger.info(
                    f"Skipping {workspace_name}: modified in last 24 hours"
                )
                result.skipped.append(
                    {
                        "workspace": workspace_name,
                        "reason": "recent_modification",
                    }
                )
                result.workspaces_preserved += 1
                continue

            # Check if workspace is expired
            if not self.is_workspace_expired(workspace_path):
                logger.debug(
                    f"Preserving {workspace_name}: within retention period"
                )
                result.workspaces_preserved += 1
                continue

            # Workspace is expired and safe to delete
            success, space_reclaimed = self.delete_workspace(workspace_path)

            if success:
                result.workspaces_deleted += 1
                result.space_reclaimed_bytes += space_reclaimed
            else:
                # AC6: Graceful error handling - continue with other workspaces
                error_msg = f"Failed to delete workspace {workspace_name}"
                result.errors.append(error_msg)

        # Calculate duration
        result.duration_seconds = time.time() - start_time

        # Update last cleanup time for status API (AC5)
        self.last_cleanup_time = datetime.now(timezone.utc)

        # Log summary
        logger.info(
            f"Workspace cleanup completed: scanned={result.workspaces_scanned}, "
            f"deleted={result.workspaces_deleted}, "
            f"preserved={result.workspaces_preserved}, "
            f"space_reclaimed={result.space_reclaimed_bytes:,} bytes, "
            f"errors={len(result.errors)}, "
            f"duration={result.duration_seconds:.2f}s"
        )

        return result

    def get_cleanup_status(self) -> Dict[str, Any]:
        """
        Get current cleanup status and workspace statistics.

        AC5: Cleanup status visibility for monitoring and admin dashboard.

        Returns:
            Dictionary containing:
            - last_cleanup_time: ISO format timestamp of last cleanup or None
            - workspace_count: Current number of workspaces
            - oldest_workspace_age: Age in days of oldest workspace or None
            - total_size_mb: Total size of all workspaces in MB
        """
        status = {
            "last_cleanup_time": None,
            "workspace_count": 0,
            "oldest_workspace_age": None,
            "total_size_mb": 0.0,
        }

        # Convert last cleanup time to ISO format
        if self.last_cleanup_time is not None:
            status["last_cleanup_time"] = self.last_cleanup_time.isoformat()

        # Scan for current workspaces
        workspaces = self.scan_workspaces()
        status["workspace_count"] = len(workspaces)

        if len(workspaces) == 0:
            return status

        # Calculate oldest workspace age
        current_time = time.time()
        oldest_age_days = None

        for workspace_path in workspaces:
            try:
                stats = workspace_path.stat()
                modification_time = stats.st_mtime
                age_seconds = current_time - modification_time
                age_days = age_seconds / (24 * 3600)

                if oldest_age_days is None or age_days > oldest_age_days:
                    oldest_age_days = age_days

            except Exception as e:
                logger.warning(
                    f"Error checking workspace age for {workspace_path}: {e}"
                )

        status["oldest_workspace_age"] = oldest_age_days

        # Calculate total size in MB
        total_bytes = 0
        for workspace_path in workspaces:
            total_bytes += self.calculate_directory_size(workspace_path)

        status["total_size_mb"] = total_bytes / (1024 * 1024)

        return status
