"""
Exception classes for sync job management.

Provides specific exceptions for job management operations
following existing error handling patterns in the CIDX server.
"""

from typing import Optional


class SyncJobError(Exception):
    """Base exception for sync job operations."""

    pass


class DuplicateJobIdError(SyncJobError):
    """Raised when attempting to create a job with an existing job ID."""

    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' already exists")
        self.job_id = job_id


class JobNotFoundError(SyncJobError):
    """Raised when attempting to access a job that doesn't exist."""

    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' not found")
        self.job_id = job_id


class InvalidJobParametersError(SyncJobError):
    """Raised when job parameters are invalid."""

    def __init__(self, message: str):
        super().__init__(f"Invalid job parameters: {message}")


class JobPersistenceError(SyncJobError):
    """Raised when job persistence operations fail."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(f"Job persistence error: {message}")
        self.cause = cause


class ConcurrencyLimitExceededError(SyncJobError):
    """Raised when user or system concurrency limits are exceeded."""

    def __init__(self, username: str, current_count: int, limit: int):
        super().__init__(
            f"User '{username}' has {current_count} concurrent jobs, "
            f"which exceeds the limit of {limit}"
        )
        self.username = username
        self.current_count = current_count
        self.limit = limit


class DuplicateRepositorySyncError(SyncJobError):
    """Raised when attempting to sync a repository that's already being synced."""

    def __init__(self, repository_url: str, existing_job_id: str):
        super().__init__(
            f"Repository '{repository_url}' is already being synced by job '{existing_job_id}'"
        )
        self.repository_url = repository_url
        self.existing_job_id = existing_job_id


class ResourceLimitExceededError(SyncJobError):
    """Raised when system resource limits prevent new job creation."""

    def __init__(self, resource_type: str, current_usage: float, limit: float):
        super().__init__(
            f"{resource_type} usage ({current_usage:.1f}%) exceeds limit ({limit:.1f}%)"
        )
        self.resource_type = resource_type
        self.current_usage = current_usage
        self.limit = limit


class JobQueueError(SyncJobError):
    """Raised when job queue operations fail."""

    def __init__(self, message: str):
        super().__init__(f"Job queue error: {message}")


class InvalidJobStateTransitionError(SyncJobError):
    """Raised when attempting an invalid job state transition."""

    def __init__(self, job_id: str, current_state: str, attempted_state: str):
        super().__init__(
            f"Cannot transition job '{job_id}' from '{current_state}' to '{attempted_state}'"
        )
        self.job_id = job_id
        self.current_state = current_state
        self.attempted_state = attempted_state


class MaintenanceModeError(SyncJobError):
    """Raised when job creation is rejected due to maintenance mode.

    Story #734: Job-Aware Auto-Update with Graceful Drain Mode
    """

    def __init__(self, retry_after_seconds: int = 60):
        super().__init__(
            f"Server is in maintenance mode. New jobs are not accepted. "
            f"Please retry after {retry_after_seconds} seconds."
        )
        self.retry_after_seconds = retry_after_seconds
