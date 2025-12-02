"""
Dashboard Data Service.

Aggregates data from various internal services for the admin dashboard.
Following CLAUDE.md Foundation #1: No mocks - uses real service integrations.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from .health_service import health_service
from ..models.api_models import HealthCheckResponse, HealthStatus

logger = logging.getLogger(__name__)


@dataclass
class JobCounts:
    """Job count statistics."""

    running: int = 0
    queued: int = 0
    completed_24h: int = 0
    failed_24h: int = 0


@dataclass
class RepoCounts:
    """Repository count statistics."""

    golden: int = 0
    activated: int = 0
    total_files: int = 0


@dataclass
class RecentJob:
    """Recent job information."""

    job_id: str
    repo_name: str
    job_type: str
    completion_time: str
    status: str


@dataclass
class DashboardData:
    """Complete dashboard data aggregate."""

    health: HealthCheckResponse
    job_counts: JobCounts
    repo_counts: RepoCounts
    recent_jobs: List[RecentJob]


class DashboardService:
    """Service for aggregating dashboard data from various internal sources."""

    def get_dashboard_data(self, username: str) -> DashboardData:
        """
        Get all dashboard data for display.

        Args:
            username: Current user's username

        Returns:
            DashboardData containing all sections
        """
        # Get health data
        health_data = self._get_health_data()

        # Get job statistics
        job_counts = self._get_job_counts(username)

        # Get repository statistics
        repo_counts = self._get_repo_counts(username)

        # Get recent jobs
        recent_jobs = self._get_recent_jobs(username)

        return DashboardData(
            health=health_data,
            job_counts=job_counts,
            repo_counts=repo_counts,
            recent_jobs=recent_jobs,
        )

    def get_health_partial(self) -> HealthCheckResponse:
        """Get health data for partial refresh."""
        return self._get_health_data()

    def get_stats_partial(self, username: str) -> Dict[str, Any]:
        """
        Get statistics data for partial refresh.

        Args:
            username: Current user's username

        Returns:
            Dictionary containing job and repo counts
        """
        return {
            "job_counts": self._get_job_counts(username),
            "repo_counts": self._get_repo_counts(username),
            "recent_jobs": self._get_recent_jobs(username),
        }

    def _get_health_data(self) -> HealthCheckResponse:
        """Get system health data."""
        try:
            return health_service.get_system_health()
        except Exception as e:
            logger.error(f"Failed to get health data: {e}")
            # Return degraded status on error
            from ..models.api_models import (
                ServiceHealthInfo,
                SystemHealthInfo,
            )

            return HealthCheckResponse(
                status=HealthStatus.UNHEALTHY,
                timestamp=datetime.now(timezone.utc),
                services={
                    "database": ServiceHealthInfo(
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        error_message="Unable to check health",
                    ),
                    "vector_store": ServiceHealthInfo(
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        error_message="Unable to check health",
                    ),
                    "storage": ServiceHealthInfo(
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        error_message="Unable to check health",
                    ),
                },
                system=SystemHealthInfo(
                    memory_usage_percent=0.0,
                    cpu_usage_percent=0.0,
                    active_jobs=0,
                    disk_free_space_gb=0.0,
                ),
            )

    def _get_job_counts(self, username: str) -> JobCounts:
        """
        Get job count statistics.

        Args:
            username: Current user's username

        Returns:
            JobCounts dataclass
        """
        try:
            # Access global background job manager
            job_manager = self._get_background_job_manager()
            if not job_manager:
                return JobCounts()

            # Get all jobs for the user
            # Note: In real implementation, we would filter by user
            # For admin dashboard, we show all jobs
            all_jobs = job_manager.list_jobs(status=None, limit=1000, offset=0)

            running = 0
            queued = 0
            completed_24h = 0
            failed_24h = 0

            # Calculate time threshold for 24h metrics
            now = datetime.now(timezone.utc)
            threshold_24h = now - timedelta(hours=24)

            for job in all_jobs.get("jobs", []):
                job_status = job.get("status", "").lower()
                completed_at_str = job.get("completed_at")

                if job_status == "running":
                    running += 1
                elif job_status in ["pending", "queued"]:
                    queued += 1
                elif job_status == "completed":
                    if completed_at_str:
                        try:
                            # Parse completion time
                            completed_at = self._parse_datetime(completed_at_str)
                            if completed_at and completed_at > threshold_24h:
                                completed_24h += 1
                        except Exception:
                            pass
                elif job_status == "failed":
                    if completed_at_str:
                        try:
                            completed_at = self._parse_datetime(completed_at_str)
                            if completed_at and completed_at > threshold_24h:
                                failed_24h += 1
                        except Exception:
                            pass

            return JobCounts(
                running=running,
                queued=queued,
                completed_24h=completed_24h,
                failed_24h=failed_24h,
            )

        except Exception as e:
            logger.error(f"Failed to get job counts: {e}")
            return JobCounts()

    def _get_repo_counts(self, username: str) -> RepoCounts:
        """
        Get repository count statistics.

        Args:
            username: Current user's username

        Returns:
            RepoCounts dataclass
        """
        golden_count = 0
        activated_count = 0
        total_files = 0

        # Get golden repos count
        try:
            golden_manager = self._get_golden_repo_manager()
            if golden_manager:
                golden_repos = golden_manager.list_golden_repos()
                golden_count = len(golden_repos) if golden_repos else 0
        except Exception as e:
            logger.error(f"Failed to get golden repos count: {e}")

        # Get activated repos count
        try:
            activated_manager = self._get_activated_repo_manager()
            if activated_manager:
                # For admin, get all activated repos across all users
                # If not admin, filter by username
                activated_repos = activated_manager.list_activated_repositories(
                    username
                )
                activated_count = len(activated_repos) if activated_repos else 0

                # Sum total files from all activated repos
                for repo in activated_repos or []:
                    if hasattr(repo, "file_count"):
                        total_files += repo.file_count
        except Exception as e:
            logger.error(f"Failed to get activated repos count: {e}")

        return RepoCounts(
            golden=golden_count,
            activated=activated_count,
            total_files=total_files,
        )

    def _get_recent_jobs(self, username: str) -> List[RecentJob]:
        """
        Get the last 5 completed jobs.

        Args:
            username: Current user's username

        Returns:
            List of RecentJob objects
        """
        try:
            job_manager = self._get_background_job_manager()
            if not job_manager:
                return []

            # Get recent completed/failed jobs
            all_jobs = job_manager.list_jobs(status=None, limit=100, offset=0)

            recent = []
            for job in all_jobs.get("jobs", []):
                job_status = job.get("status", "").lower()

                # Only include completed or failed jobs
                if job_status in ["completed", "failed"]:
                    completed_at_str = job.get("completed_at") or job.get("created_at")

                    # Extract repo name from result or operation type
                    repo_name = "Unknown"
                    result = job.get("result", {}) or {}
                    if isinstance(result, dict):
                        repo_name = result.get("alias") or result.get(
                            "repository", "Unknown"
                        )

                    recent.append(
                        RecentJob(
                            job_id=job.get("job_id", ""),
                            repo_name=repo_name,
                            job_type=job.get("operation_type", "unknown"),
                            completion_time=completed_at_str or "",
                            status=job_status,
                        )
                    )

            # Sort by completion time (most recent first) and take first 5
            recent.sort(key=lambda x: x.completion_time, reverse=True)
            return recent[:5]

        except Exception as e:
            logger.error(f"Failed to get recent jobs: {e}")
            return []

    def _get_background_job_manager(self) -> Optional[Any]:
        """Get the background job manager instance."""
        try:
            from ..app import background_job_manager

            return background_job_manager
        except Exception:
            return None

    def _get_golden_repo_manager(self) -> Optional[Any]:
        """Get the golden repo manager instance."""
        try:
            from ..app import golden_repo_manager

            return golden_repo_manager
        except Exception:
            return None

    def _get_activated_repo_manager(self) -> Optional[Any]:
        """Get the activated repo manager instance."""
        try:
            from ..app import activated_repo_manager

            return activated_repo_manager
        except Exception:
            return None

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """
        Parse a datetime string to datetime object.

        Args:
            dt_str: Datetime string

        Returns:
            Parsed datetime or None
        """
        if not dt_str:
            return None

        # Try various formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(dt_str, fmt)
                # Make timezone-aware if not already
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue

        return None


# Global service instance
dashboard_service = DashboardService()
