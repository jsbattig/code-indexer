"""
Comprehensive Error Handling System for CIDX Repository Sync Operations.

Provides hierarchical error classification, context capture, and intelligent
error categorization for sync operations with proper severity levels and
recovery strategy recommendations.
"""

import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any

from code_indexer.server.middleware.correlation import get_correlation_id


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for sync operations."""

    INFO = "info"
    WARNING = "warning"
    RECOVERABLE = "recoverable"
    FATAL = "fatal"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """High-level error categories for sync operations."""

    NETWORK = "network"
    AUTHENTICATION = "authentication"
    GIT_OPERATION = "git_operation"
    INDEXING = "indexing"
    FILE_SYSTEM = "file_system"
    SYSTEM_RESOURCE = "system_resource"
    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    JOB_MANAGEMENT = "job_management"


@dataclass
class ErrorContext:
    """Rich error context information for comprehensive error reporting."""

    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    phase: str = ""
    repository: str = ""
    user_id: str = ""
    job_id: Optional[str] = None
    stack_trace: str = ""
    system_info: Dict[str, Any] = field(default_factory=dict)
    recovery_suggestions: List[str] = field(default_factory=list)
    related_errors: List[str] = field(default_factory=list)
    diagnostic_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error context to dictionary for serialization."""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "repository": self.repository,
            "user_id": self.user_id,
            "job_id": self.job_id,
            "stack_trace": self.stack_trace,
            "system_info": self.system_info,
            "recovery_suggestions": self.recovery_suggestions,
            "related_errors": self.related_errors,
            "diagnostic_data": self.diagnostic_data,
        }


# Base Sync Error Hierarchy


class SyncError(Exception):
    """Base exception for all sync operations with comprehensive context."""

    def __init__(
        self,
        message: str,
        error_code: str,
        severity: ErrorSeverity = ErrorSeverity.FATAL,
        category: ErrorCategory = ErrorCategory.GIT_OPERATION,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        recovery_suggestions: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.severity = severity
        self.category = category
        self.context = context or ErrorContext()
        self.cause = cause

        # Set recovery suggestions in context if provided
        if recovery_suggestions:
            self.context.recovery_suggestions = recovery_suggestions

        # Capture stack trace
        self.context.stack_trace = traceback.format_exc()

        logger.error(
            f"SyncError [{self.error_code}]: {message} "
            f"(severity={severity.value}, category={category.value})",
            extra={"correlation_id": get_correlation_id()},
        )


class RecoverableError(SyncError):
    """Base class for recoverable errors that can be retried or automatically handled."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("severity", ErrorSeverity.RECOVERABLE)
        super().__init__(message, error_code, **kwargs)


class FatalError(SyncError):
    """Base class for fatal errors that require manual intervention."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("severity", ErrorSeverity.FATAL)
        super().__init__(message, error_code, **kwargs)


class CriticalError(SyncError):
    """Base class for critical system errors that affect system stability."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("severity", ErrorSeverity.CRITICAL)
        super().__init__(message, error_code, **kwargs)


# Network Error Classes


class NetworkError(RecoverableError):
    """Base class for network-related errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.NETWORK)
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check network connectivity",
                "Verify DNS resolution",
                "Try again after a short delay",
                "Check firewall and proxy settings",
            ],
        )
        super().__init__(message, error_code, **kwargs)


class ConnectionTimeoutError(NetworkError):
    """Connection timeout during network operations."""

    def __init__(self, timeout_seconds: int, endpoint: str, **kwargs):
        message = f"Connection timeout after {timeout_seconds}s to {endpoint}"
        super().__init__(message, "CONN_TIMEOUT", **kwargs)
        self.timeout_seconds = timeout_seconds
        self.endpoint = endpoint


class DNSResolutionError(NetworkError):
    """DNS resolution failure."""

    def __init__(self, hostname: str, **kwargs):
        message = f"Failed to resolve hostname: {hostname}"
        super().__init__(message, "DNS_FAILURE", **kwargs)
        self.hostname = hostname


class NetworkUnavailableError(NetworkError):
    """Network or service unavailable."""

    def __init__(self, service: str, **kwargs):
        message = f"Service unavailable: {service}"
        super().__init__(message, "SERVICE_UNAVAILABLE", **kwargs)
        self.service = service


class RateLimitExceededError(NetworkError):
    """API rate limiting exceeded."""

    def __init__(
        self, service: str, retry_after_seconds: Optional[int] = None, **kwargs
    ):
        message = f"Rate limit exceeded for {service}"
        if retry_after_seconds:
            message += f" - retry after {retry_after_seconds}s"
        super().__init__(message, "RATE_LIMITED", **kwargs)
        self.service = service
        self.retry_after_seconds = retry_after_seconds


class SSLCertificateError(NetworkError):
    """SSL certificate validation error."""

    def __init__(self, hostname: str, **kwargs):
        message = f"SSL certificate error for {hostname}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check SSL certificate validity",
                "Verify system clock accuracy",
                "Update certificate store",
                "Contact repository administrator",
            ],
        )
        super().__init__(message, "SSL_CERT_ERROR", **kwargs)
        self.hostname = hostname


# Authentication Error Classes


class AuthenticationError(RecoverableError):
    """Base class for authentication-related errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.AUTHENTICATION)
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check credentials validity",
                "Verify access permissions",
                "Refresh authentication tokens",
                "Contact repository administrator",
            ],
        )
        super().__init__(message, error_code, **kwargs)


class InvalidCredentialsError(AuthenticationError):
    """Invalid username/password or token."""

    def __init__(self, auth_type: str = "credentials", **kwargs):
        message = f"Invalid {auth_type}"
        super().__init__(message, "INVALID_CREDENTIALS", **kwargs)
        self.auth_type = auth_type


class TokenExpiredError(AuthenticationError):
    """Authentication token expired."""

    def __init__(self, token_type: str = "access", **kwargs):
        message = f"{token_type.title()} token expired"
        super().__init__(message, "TOKEN_EXPIRED", **kwargs)
        self.token_type = token_type


class AccessDeniedError(AuthenticationError):
    """Access denied to repository or resource."""

    def __init__(self, resource: str, **kwargs):
        message = f"Access denied to resource: {resource}"
        super().__init__(message, "ACCESS_DENIED", **kwargs)
        self.resource = resource


class TwoFactorAuthRequiredError(AuthenticationError):
    """Two-factor authentication required."""

    def __init__(self, **kwargs):
        message = "Two-factor authentication required"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Enable two-factor authentication",
                "Use personal access token instead",
                "Update authentication method",
            ],
        )
        super().__init__(message, "2FA_REQUIRED", **kwargs)


# Git Operation Error Classes


class GitOperationError(RecoverableError):
    """Base class for git operation errors."""

    def __init__(
        self, message: str, error_code: str, git_output: Optional[str] = None, **kwargs
    ):
        kwargs.setdefault("category", ErrorCategory.GIT_OPERATION)
        super().__init__(message, error_code, **kwargs)
        self.git_output = git_output

        if git_output:
            self.context.diagnostic_data["git_output"] = git_output


class RepositoryNotFoundError(GitOperationError):
    """Repository not found or not accessible."""

    def __init__(self, repository_url: str, **kwargs):
        message = f"Repository not found: {repository_url}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Verify repository URL is correct",
                "Check repository permissions",
                "Ensure repository exists",
                "Verify network connectivity",
            ],
        )
        super().__init__(message, "REPO_NOT_FOUND", **kwargs)
        self.repository_url = repository_url


class MergeConflictError(GitOperationError):
    """Merge conflicts during git pull operation."""

    def __init__(self, conflicted_files: List[str], **kwargs):
        message = f"Merge conflicts in {len(conflicted_files)} files"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Resolve merge conflicts manually",
                "Use force merge strategy if appropriate",
                "Create backup before resolving conflicts",
                "Consider rebasing instead of merging",
            ],
        )
        super().__init__(message, "MERGE_CONFLICT", **kwargs)
        self.conflicted_files = conflicted_files
        self.context.diagnostic_data["conflicted_files"] = conflicted_files


class BranchDivergenceError(GitOperationError):
    """Local and remote branches have diverged."""

    def __init__(self, branch_name: str, **kwargs):
        message = f"Branch '{branch_name}' has diverged from remote"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Use force merge strategy",
                "Rebase local changes",
                "Reset to remote branch",
                "Merge remote changes manually",
            ],
        )
        super().__init__(message, "BRANCH_DIVERGED", **kwargs)
        self.branch_name = branch_name


class WorkingTreeDirtyError(GitOperationError):
    """Working tree has uncommitted changes."""

    def __init__(self, dirty_files: List[str], **kwargs):
        message = f"Working tree dirty with {len(dirty_files)} uncommitted files"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Commit or stash uncommitted changes",
                "Use git reset to discard changes",
                "Create backup of uncommitted work",
                "Use force pull if changes are not needed",
            ],
        )
        super().__init__(message, "WORKING_TREE_DIRTY", **kwargs)
        self.dirty_files = dirty_files
        self.context.diagnostic_data["dirty_files"] = dirty_files


class DetachedHeadError(GitOperationError):
    """Repository is in detached HEAD state."""

    def __init__(self, current_commit: str, **kwargs):
        message = f"Repository in detached HEAD state at {current_commit}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Checkout a branch before pulling",
                "Create new branch from current state",
                "Merge changes into main branch",
                "Reset to main branch if changes not needed",
            ],
        )
        super().__init__(message, "DETACHED_HEAD", **kwargs)
        self.current_commit = current_commit


class CorruptRepositoryError(FatalError):
    """Git repository is corrupted."""

    def __init__(self, repository_path: str, **kwargs):
        message = f"Git repository corrupted: {repository_path}"
        kwargs.setdefault("category", ErrorCategory.GIT_OPERATION)
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Run git fsck to check repository integrity",
                "Clone fresh copy of repository",
                "Restore from backup if available",
                "Contact repository administrator",
            ],
        )
        super().__init__(message, "REPO_CORRUPTED", **kwargs)
        self.repository_path = repository_path


# Indexing Error Classes


class IndexingError(RecoverableError):
    """Base class for indexing operation errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.INDEXING)
        super().__init__(message, error_code, **kwargs)


class EmbeddingProviderError(IndexingError):
    """Embedding provider API error."""

    def __init__(self, provider: str, api_error: str, **kwargs):
        message = f"Embedding provider '{provider}' error: {api_error}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check API credentials and limits",
                "Verify network connectivity",
                "Try alternative embedding provider",
                "Reduce batch size or request rate",
            ],
        )
        super().__init__(message, "EMBEDDING_API_ERROR", **kwargs)
        self.provider = provider
        self.api_error = api_error


class VectorDatabaseError(IndexingError):
    """Vector database operation error."""

    def __init__(self, database: str, operation: str, db_error: str, **kwargs):
        message = f"Vector database '{database}' {operation} error: {db_error}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check database connectivity",
                "Verify database service is running",
                "Check disk space and memory",
                "Restart database service if needed",
            ],
        )
        super().__init__(message, "VECTOR_DB_ERROR", **kwargs)
        self.database = database
        self.operation = operation
        self.db_error = db_error


class FileProcessingError(IndexingError):
    """Error processing individual files during indexing."""

    def __init__(self, file_path: str, processing_error: str, **kwargs):
        message = f"Error processing file '{file_path}': {processing_error}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check file permissions and accessibility",
                "Verify file is not corrupted",
                "Skip problematic files and continue",
                "Update file processing rules",
            ],
        )
        super().__init__(message, "FILE_PROCESSING_ERROR", **kwargs)
        self.file_path = file_path
        self.processing_error = processing_error


class IndexCorruptionError(FatalError):
    """Vector index corruption detected."""

    def __init__(self, index_name: str, **kwargs):
        message = f"Vector index corruption detected: {index_name}"
        kwargs.setdefault("category", ErrorCategory.INDEXING)
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Rebuild index from scratch",
                "Restore index from backup",
                "Run index consistency checks",
                "Check underlying database integrity",
            ],
        )
        super().__init__(message, "INDEX_CORRUPTED", **kwargs)
        self.index_name = index_name


# File System Error Classes


class FileSystemError(RecoverableError):
    """Base class for file system errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.FILE_SYSTEM)
        super().__init__(message, error_code, **kwargs)


class DiskSpaceError(FileSystemError):
    """Insufficient disk space."""

    def __init__(self, required_mb: float, available_mb: float, **kwargs):
        message = f"Insufficient disk space: need {required_mb:.1f}MB, have {available_mb:.1f}MB"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Free up disk space",
                "Move to directory with more space",
                "Clean up temporary files",
                "Increase storage allocation",
            ],
        )
        super().__init__(message, "DISK_SPACE_LOW", **kwargs)
        self.required_mb = required_mb
        self.available_mb = available_mb


class PermissionDeniedError(FileSystemError):
    """File or directory permission denied."""

    def __init__(self, path: str, operation: str, **kwargs):
        message = f"Permission denied: {operation} on '{path}'"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check file/directory permissions",
                "Run with appropriate user privileges",
                "Change file ownership if needed",
                "Verify directory is accessible",
            ],
        )
        super().__init__(message, "PERMISSION_DENIED", **kwargs)
        self.path = path
        self.operation = operation


class FileNotFoundError(FileSystemError):
    """Required file or directory not found."""

    def __init__(self, path: str, **kwargs):
        message = f"File or directory not found: '{path}'"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Verify path exists and is correct",
                "Check if file was moved or deleted",
                "Recreate missing directories",
                "Update configuration with correct paths",
            ],
        )
        super().__init__(message, "FILE_NOT_FOUND", **kwargs)
        self.path = path


# System Resource Error Classes


class SystemResourceError(RecoverableError):
    """Base class for system resource errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.SYSTEM_RESOURCE)
        super().__init__(message, error_code, **kwargs)


class OutOfMemoryError(SystemResourceError):
    """System out of memory."""

    def __init__(self, memory_required_mb: Optional[float] = None, **kwargs):
        message = "System out of memory"
        if memory_required_mb:
            message += f" (required: {memory_required_mb:.1f}MB)"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Close other applications to free memory",
                "Increase system memory",
                "Reduce batch sizes",
                "Process in smaller chunks",
            ],
        )
        super().__init__(message, "OUT_OF_MEMORY", **kwargs)
        self.memory_required_mb = memory_required_mb


class CPUOverloadError(SystemResourceError):
    """System CPU overloaded."""

    def __init__(self, cpu_percent: float, **kwargs):
        message = f"System CPU overloaded: {cpu_percent:.1f}%"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Wait for system load to decrease",
                "Reduce parallel processing threads",
                "Close other CPU-intensive applications",
                "Reschedule operation for off-peak hours",
            ],
        )
        super().__init__(message, "CPU_OVERLOAD", **kwargs)
        self.cpu_percent = cpu_percent


class ProcessInterruptedError(SystemResourceError):
    """Process was interrupted or killed."""

    def __init__(self, signal_name: str, **kwargs):
        message = f"Process interrupted by signal: {signal_name}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Restart operation if safe to do so",
                "Check for system shutdown or restart",
                "Verify process permissions",
                "Check system resource availability",
            ],
        )
        super().__init__(message, "PROCESS_INTERRUPTED", **kwargs)
        self.signal_name = signal_name


# Configuration Error Classes


class ConfigurationError(FatalError):
    """Base class for configuration errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.CONFIGURATION)
        super().__init__(message, error_code, **kwargs)


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration values."""

    def __init__(
        self, config_key: str, config_value: Any, validation_error: str, **kwargs
    ):
        message = (
            f"Invalid configuration '{config_key}={config_value}': {validation_error}"
        )
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Check configuration file syntax",
                "Verify configuration values are valid",
                "Restore from backup configuration",
                "Use default configuration values",
            ],
        )
        super().__init__(message, "INVALID_CONFIG", **kwargs)
        self.config_key = config_key
        self.config_value = config_value
        self.validation_error = validation_error


class MissingConfigurationError(ConfigurationError):
    """Required configuration missing."""

    def __init__(self, config_key: str, **kwargs):
        message = f"Required configuration missing: '{config_key}'"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Add missing configuration value",
                "Run configuration setup wizard",
                "Check configuration file completeness",
                "Use cidx init to recreate configuration",
            ],
        )
        super().__init__(message, "MISSING_CONFIG", **kwargs)
        self.config_key = config_key


# Validation Error Classes


class ValidationError(RecoverableError):
    """Base class for validation errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.VALIDATION)
        super().__init__(message, error_code, **kwargs)


class IndexValidationError(ValidationError):
    """Index validation failed."""

    def __init__(
        self, validation_type: str, health_score: float, threshold: float, **kwargs
    ):
        message = f"Index validation failed: {validation_type} score {health_score:.2f} < {threshold:.2f}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Rebuild index to improve quality",
                "Adjust validation thresholds",
                "Check for underlying data issues",
                "Run index optimization",
            ],
        )
        super().__init__(message, "INDEX_VALIDATION_FAILED", **kwargs)
        self.validation_type = validation_type
        self.health_score = health_score
        self.threshold = threshold


class DataIntegrityError(ValidationError):
    """Data integrity validation failed."""

    def __init__(self, integrity_check: str, **kwargs):
        message = f"Data integrity check failed: {integrity_check}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Restore from known good backup",
                "Run data repair utilities",
                "Rebuild corrupted data structures",
                "Check for underlying storage issues",
            ],
        )
        super().__init__(message, "DATA_INTEGRITY_ERROR", **kwargs)
        self.integrity_check = integrity_check


# Job Management Error Classes


class JobManagementError(RecoverableError):
    """Base class for job management errors."""

    def __init__(self, message: str, error_code: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.JOB_MANAGEMENT)
        super().__init__(message, error_code, **kwargs)


class JobExecutionError(JobManagementError):
    """Job execution failed."""

    def __init__(self, job_id: str, phase: str, execution_error: str, **kwargs):
        message = f"Job {job_id} execution failed in phase '{phase}': {execution_error}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Retry job execution",
                "Check job parameters and configuration",
                "Review system resource availability",
                "Check job dependencies and prerequisites",
            ],
        )
        super().__init__(message, "JOB_EXECUTION_FAILED", **kwargs)
        self.job_id = job_id
        self.phase = phase
        self.execution_error = execution_error


class ResourceLimitError(JobManagementError):
    """System resource limits exceeded."""

    def __init__(
        self, limit_type: str, current_value: float, limit_value: float, **kwargs
    ):
        message = f"Resource limit exceeded: {limit_type} {current_value:.1f} > {limit_value:.1f}"
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Wait for system resources to be available",
                "Increase resource limits",
                "Reschedule job for off-peak hours",
                "Optimize job resource usage",
            ],
        )
        super().__init__(message, "RESOURCE_LIMIT_EXCEEDED", **kwargs)
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value


class ConcurrencyLimitError(JobManagementError):
    """Job concurrency limits exceeded."""

    def __init__(self, job_type: str, current_count: int, limit_count: int, **kwargs):
        message = (
            f"Concurrency limit exceeded: {current_count}/{limit_count} {job_type} jobs"
        )
        kwargs.setdefault(
            "recovery_suggestions",
            [
                "Wait for running jobs to complete",
                "Increase concurrency limits",
                "Cancel non-essential jobs",
                "Queue job for later execution",
            ],
        )
        super().__init__(message, "CONCURRENCY_LIMIT_EXCEEDED", **kwargs)
        self.job_type = job_type
        self.current_count = current_count
        self.limit_count = limit_count


def classify_error(
    exception: Exception, context: Optional[ErrorContext] = None
) -> SyncError:
    """
    Classify a generic exception into appropriate SyncError subclass.

    Args:
        exception: The original exception to classify
        context: Optional error context to attach

    Returns:
        Appropriate SyncError subclass instance
    """
    error_context = context or ErrorContext()
    error_context.stack_trace = traceback.format_exc()

    # Already a SyncError - just update context
    if isinstance(exception, SyncError):
        if context:
            exception.context = context
        return exception

    exception_str = str(exception).lower()
    exception_type = type(exception).__name__

    # Network-related errors
    if any(keyword in exception_str for keyword in ["timeout", "timed out"]):
        return ConnectionTimeoutError(
            timeout_seconds=30,  # Default timeout
            endpoint="unknown",
            context=error_context,
            cause=exception,
        )

    if any(
        keyword in exception_str for keyword in ["dns", "name resolution", "hostname"]
    ):
        return DNSResolutionError(
            hostname="unknown", context=error_context, cause=exception
        )

    if any(
        keyword in exception_str for keyword in ["connection refused", "unreachable"]
    ):
        return NetworkUnavailableError(
            service="unknown", context=error_context, cause=exception
        )

    if any(keyword in exception_str for keyword in ["ssl", "certificate", "tls"]):
        return SSLCertificateError(
            hostname="unknown", context=error_context, cause=exception
        )

    # Authentication errors
    if any(
        keyword in exception_str
        for keyword in ["authentication", "unauthorized", "401"]
    ):
        return InvalidCredentialsError(context=error_context, cause=exception)

    if any(
        keyword in exception_str for keyword in ["access denied", "forbidden", "403"]
    ):
        return AccessDeniedError(
            resource="unknown", context=error_context, cause=exception
        )

    # File system errors
    if any(
        keyword in exception_str
        for keyword in ["permission denied", "access is denied"]
    ):
        return PermissionDeniedError(
            path="unknown", operation="unknown", context=error_context, cause=exception
        )

    if any(
        keyword in exception_str
        for keyword in ["no such file", "file not found", "not found"]
    ):
        return FileNotFoundError(path="unknown", context=error_context, cause=exception)

    if any(
        keyword in exception_str
        for keyword in ["disk space", "no space left", "quota exceeded"]
    ):
        return DiskSpaceError(
            required_mb=0.0, available_mb=0.0, context=error_context, cause=exception
        )

    # Memory errors
    if (
        exception_type in ["MemoryError", "OutOfMemoryError"]
        or "memory" in exception_str
    ):
        return OutOfMemoryError(context=error_context, cause=exception)

    # Git errors
    if any(keyword in exception_str for keyword in ["merge conflict", "conflict"]):
        return MergeConflictError(
            conflicted_files=[], context=error_context, cause=exception
        )

    if any(
        keyword in exception_str
        for keyword in ["repository not found", "repo not found"]
    ):
        return RepositoryNotFoundError(
            repository_url="unknown", context=error_context, cause=exception
        )

    if any(
        keyword in exception_str for keyword in ["working tree", "uncommitted changes"]
    ):
        return WorkingTreeDirtyError(
            dirty_files=[], context=error_context, cause=exception
        )

    # Default to generic SyncError
    return SyncError(
        message=f"Unclassified error: {str(exception)}",
        error_code="UNCLASSIFIED_ERROR",
        severity=ErrorSeverity.FATAL,
        context=error_context,
        cause=exception,
    )


def create_error_context(
    phase: str = "",
    repository: str = "",
    user_id: str = "",
    job_id: Optional[str] = None,
    additional_info: Optional[Dict[str, Any]] = None,
) -> ErrorContext:
    """
    Create error context with system information.

    Args:
        phase: Current operation phase
        repository: Repository path or URL
        user_id: User ID performing the operation
        job_id: Associated job ID if any
        additional_info: Additional diagnostic information

    Returns:
        ErrorContext with system information populated
    """
    context = ErrorContext(
        phase=phase, repository=repository, user_id=user_id, job_id=job_id
    )

    # Collect system information
    try:
        import platform
        import psutil
        import os

        context.system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            "memory_available_gb": psutil.virtual_memory().available / (1024**3),
            "disk_usage_gb": psutil.disk_usage(".").free / (1024**3),
            "load_average": (
                psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else None
            ),
            "process_id": os.getpid(),
        }
    except Exception as e:
        logger.warning(
            f"Failed to collect system info for error context: {e}",
            extra={"correlation_id": get_correlation_id()},
        )
        context.system_info = {"error": f"Failed to collect system info: {str(e)}"}

    # Add additional diagnostic info
    if additional_info:
        context.diagnostic_data.update(additional_info)

    return context
