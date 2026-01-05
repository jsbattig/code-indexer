from code_indexer.server.middleware.correlation import get_correlation_id
"""
Dashboard Data Service.

Aggregates data from various internal services for the admin dashboard.
Following CLAUDE.md Foundation #1: No mocks - uses real service integrations.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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

    def get_stats_partial(
        self, username: str, time_filter: str = "24h", recent_filter: str = "30d"
    ) -> Dict[str, Any]:
        """
        Get statistics data for partial refresh.

        Args:
            username: Current user's username
            time_filter: Time filter for job stats ("24h", "7d", "30d")
            recent_filter: Time filter for recent activity ("24h", "7d", "30d")

        Returns:
            Dictionary containing job and repo counts
        """
        return {
            "job_counts": self._get_job_counts(username, time_filter),
            "repo_counts": self._get_repo_counts(username),
            "recent_jobs": self._get_recent_jobs(username, recent_filter),
        }

    def _get_health_data(self) -> HealthCheckResponse:
        """Get system health data."""
        try:
            return health_service.get_system_health()
        except Exception as e:
            logger.error(f"Failed to get health data: {e}", extra={"correlation_id": get_correlation_id()})
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

    def _get_job_counts(self, username: str, time_filter: str = "24h") -> JobCounts:
        """
        Get job count statistics.

        Args:
            username: Current user's username
            time_filter: Time filter ("24h", "7d", "30d")

        Returns:
            JobCounts dataclass
        """
        try:
            # Access global background job manager
            job_manager = self._get_background_job_manager()
            if not job_manager:
                return JobCounts()

            # Story #541 AC3: Use time-filtered job stats
            stats = job_manager.get_job_stats_with_filter(time_filter)

            # Get current running and queued counts (not time-filtered)
            running = job_manager.get_active_job_count()
            queued = job_manager.get_pending_job_count()

            return JobCounts(
                running=running,
                queued=queued,
                completed_24h=stats["completed"],
                failed_24h=stats["failed"],
            )

        except Exception as e:
            logger.error(f"Failed to get job counts: {e}", extra={"correlation_id": get_correlation_id()})
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
            logger.error(f"Failed to get golden repos count: {e}", extra={"correlation_id": get_correlation_id()})

        # Get activated repos count and aggregate vector store file counts
        try:
            activated_manager = self._get_activated_repo_manager()
            if activated_manager:
                # For admin, get all activated repos across all users
                # If not admin, filter by username
                activated_repos = activated_manager.list_activated_repositories(
                    username
                )
                activated_count = len(activated_repos) if activated_repos else 0

                # Story #541 AC1/AC2: Sum FilesystemVectorStore counts from all activated repos
                # Import here to avoid circular dependency
                from pathlib import Path
                from code_indexer.storage.filesystem_vector_store import (
                    FilesystemVectorStore,
                )

                # Create shared vector store instance for all repos
                # Use manager's data directory for index storage
                index_dir = Path(activated_manager.data_dir) / "index"
                store = FilesystemVectorStore(base_path=index_dir)

                for repo in activated_repos or []:
                    try:
                        # Get indexed file count from vector store for this repo
                        collection_name = repo.get("collection_name")
                        if not collection_name:
                            logger.warning(f"Repo missing collection_name: {repo}", extra={"correlation_id": get_correlation_id()})
                            continue

                        count = store.get_indexed_file_count_fast(collection_name)
                        total_files += count
                    except Exception as e:
                        logger.warning(
                            f"Failed to get vector store count for {repo.get('collection_name', 'unknown')}: {e}"
                        , extra={"correlation_id": get_correlation_id()})
                        # Continue with other repos even if one fails
                        continue

        except Exception as e:
            logger.error(f"Failed to get activated repos count: {e}", extra={"correlation_id": get_correlation_id()})

        return RepoCounts(
            golden=golden_count,
            activated=activated_count,
            total_files=total_files,
        )

    def _get_recent_jobs(
        self, username: str, time_filter: str = "30d"
    ) -> List[RecentJob]:
        """
        Get recent completed jobs.

        Args:
            username: Current user's username
            time_filter: Time filter ("24h", "7d", "30d"), default 30d

        Returns:
            List of RecentJob objects (up to 20)
        """
        try:
            job_manager = self._get_background_job_manager()
            if not job_manager:
                return []

            # Story #541 AC5/AC6: Use time-filtered recent jobs with limit of 20
            recent_jobs_data = job_manager.get_recent_jobs_with_filter(
                time_filter=time_filter, limit=20
            )

            recent = []
            for job in recent_jobs_data:
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
                        completion_time=job.get("completed_at", ""),
                        status=job.get("status", "unknown"),
                    )
                )

            return recent

        except Exception as e:
            logger.error(f"Failed to get recent jobs: {e}", extra={"correlation_id": get_correlation_id()})
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

    def get_temporal_index_status(self, username: str, repo_alias: str) -> Dict[str, Any]:
        """
        Get temporal indexing status for repository.

        Detects format (v1/v2/none) and returns status information.

        Args:
            username: Username for repository lookup
            repo_alias: Repository alias

        Returns:
            Dict with format, file_count, needs_reindex, message

        Raises:
            FileNotFoundError: If repository not found
        """
        # Get repository info
        activated_manager = self._get_activated_repo_manager()
        if not activated_manager:
            raise FileNotFoundError(f"Repository not found: {repo_alias}")

        repo_info = activated_manager.get_repository(username, repo_alias)
        if not repo_info:
            raise FileNotFoundError(f"Repository not found: {repo_alias}")

        # Check if temporal collection exists
        index_dir = Path(activated_manager.data_dir) / "index"
        temporal_collection_name = "code-indexer-temporal"
        temporal_collection_path = index_dir / temporal_collection_name

        if not temporal_collection_path.exists():
            return {
                "format": "none",
                "file_count": 0,
                "needs_reindex": False,
                "message": "No temporal index (git history not indexed)"
            }

        # Detect format using TemporalMetadataStore
        from code_indexer.storage.temporal_metadata_store import TemporalMetadataStore

        format_version = TemporalMetadataStore.detect_format(temporal_collection_path)

        # Count vector files in temporal collection
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=index_dir)
        file_count = store.get_indexed_file_count_fast(temporal_collection_name)

        # Return appropriate status based on format
        if format_version == "v2":
            return {
                "format": "v2",
                "file_count": file_count,
                "needs_reindex": False,
                "message": f"Temporal indexing active (v2 format) - {file_count} files indexed"
            }
        else:  # v1 format
            return {
                "format": "v1",
                "file_count": file_count,
                "needs_reindex": True,
                "message": "Legacy temporal index format (v1) detected - Re-index required: cidx index --index-commits --reconcile"
            }


# Global service instance
dashboard_service = DashboardService()
