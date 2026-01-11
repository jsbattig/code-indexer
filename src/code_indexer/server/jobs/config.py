"""
Configuration utilities for sync job system.

Provides configuration management for sync job storage paths
integrating with existing CIDX server configuration system.
"""

from pathlib import Path
from typing import Optional

from ..utils.config_manager import ServerConfigManager


class SyncJobConfig:
    """
    Configuration manager for sync job system.

    Integrates with existing CIDX server configuration to provide
    proper storage paths for sync job persistence.
    """

    # Default concurrency and job configuration constants
    DEFAULT_MAX_CONCURRENT_JOBS_PER_USER = 3
    DEFAULT_MAX_TOTAL_CONCURRENT_JOBS = 10
    DEFAULT_AVERAGE_JOB_DURATION_MINUTES = 15

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize sync job configuration.

        Args:
            server_dir_path: Path to server directory (defaults to ~/.cidx-server)
        """
        self.config_manager = ServerConfigManager(server_dir_path)

        # Determine server directory
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        # Jobs are stored in data/jobs subdirectory
        self.jobs_dir = self.server_dir / "data" / "jobs"

    def get_jobs_storage_path(self) -> str:
        """
        Get the storage path for sync jobs.

        Returns:
            Full path to sync jobs storage file
        """
        # Ensure directories exist
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

        # Return path to sync jobs JSON file
        return str(self.jobs_dir / "sync_jobs.json")

    def setup_job_directories(self) -> None:
        """
        Setup job-related directories.

        Creates necessary directory structure for sync job operations.
        """
        # Ensure server directories exist first
        self.config_manager.create_server_directories()

        # Create jobs directory
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def get_concurrency_limits(self) -> dict:
        """
        Get concurrency limits configuration.

        Returns:
            Dictionary containing concurrency configuration
        """
        # Default concurrency limits - can be made configurable later
        return {
            "max_concurrent_jobs_per_user": 3,
            "max_total_concurrent_jobs": 10,
            "max_cpu_percent": 80.0,
            "max_memory_percent": 85.0,
            "degraded_mode_cpu_threshold": 70.0,
            "degraded_mode_memory_threshold": 75.0,
            "degraded_max_concurrent_jobs_per_user": 1,
            "degraded_max_total_concurrent_jobs": 3,
            "average_job_duration_minutes": 15,
            "queue_check_interval_seconds": 5.0,
            "resource_check_interval_seconds": 10.0,
        }
