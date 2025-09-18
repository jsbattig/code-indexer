"""
Exception classes for sync operations.

Provides specialized exceptions for sync orchestration, job execution,
and indexing failures during repository synchronization operations.

Legacy exceptions that now inherit from the comprehensive error handling system
for enhanced error context and recovery.
"""

from typing import Optional

# Import comprehensive error handling system
from .error_handler import (
    SyncError,
    JobManagementError,
    IndexingError as BaseIndexingError,
    ErrorSeverity,
    ErrorCategory,
    create_error_context,
)


class SyncOrchestratorError(SyncError):
    """Base exception for sync orchestrator operations."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        # Create error context
        context = create_error_context(phase="orchestration")

        super().__init__(
            message=message,
            error_code=error_code or "ORCHESTRATOR_ERROR",
            severity=ErrorSeverity.FATAL,
            category=ErrorCategory.JOB_MANAGEMENT,
            context=context,
            cause=cause,
        )

        # Maintain properties
        self.message = message
        self.error_code = error_code or "ORCHESTRATOR_ERROR"
        self.cause = cause


class JobExecutionError(JobManagementError):
    """Exception raised when job execution fails."""

    def __init__(
        self,
        message: str,
        job_id: str,
        phase: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        # Create enhanced error context with job information
        context = create_error_context(phase=phase or "job_execution", job_id=job_id)

        super().__init__(
            message=message,
            error_code=error_code or "JOB_EXECUTION_ERROR",
            context=context,
        )

        # Override error code if provided
        if error_code:
            self.error_code = error_code

        # Maintain properties
        self.message = message
        self.job_id = job_id
        self.phase = phase


class IndexingError(BaseIndexingError):
    """Exception raised when indexing operations fail."""

    def __init__(
        self, message: str, repository_path: str, error_code: Optional[str] = None
    ):
        # Create enhanced error context with repository information
        context = create_error_context(phase="indexing", repository=repository_path)

        super().__init__(
            message=message,
            error_code=error_code or "INDEXING_OPERATION_ERROR",
            context=context,
        )

        # Override error code if provided
        if error_code:
            self.error_code = error_code

        # Maintain properties
        self.message = message
        self.repository_path = repository_path
