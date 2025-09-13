"""
FastAPI application for CIDX Server.

Multi-user semantic code search server with JWT authentication and role-based access control.
"""

from fastapi import FastAPI, HTTPException, status, Depends, Response, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, List, Callable
import os
from pathlib import Path
import psutil
import logging
from datetime import datetime, timezone

from .auth.jwt_manager import JWTManager
from .auth.user_manager import UserManager, UserRole
from .auth import dependencies
from .auth.password_validator import (
    validate_password_complexity,
    get_password_complexity_error_message,
)
from .auth.rate_limiter import password_change_rate_limiter, refresh_token_rate_limiter
from .auth.audit_logger import password_audit_logger
from .auth.session_manager import session_manager
from .auth.timing_attack_prevention import timing_attack_prevention
from .auth.concurrency_protection import (
    password_change_concurrency_protection,
    ConcurrencyConflictError,
)
from .auth.auth_error_handler import auth_error_handler, AuthErrorType
from .utils.jwt_secret_manager import JWTSecretManager
from .middleware.error_handler import GlobalErrorHandler
from .repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepoError,
    GitOperationError,
)
from .repositories.background_jobs import BackgroundJobManager
from .repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepoError,
)
from .repositories.repository_listing_manager import (
    RepositoryListingManager,
    RepositoryListingError,
)
from .query.semantic_query_manager import (
    SemanticQueryManager,
    SemanticQueryError,
)
from .auth.refresh_token_manager import RefreshTokenManager
from .models.branch_models import BranchListResponse
from .services.branch_service import BranchService
from code_indexer.services.git_topology_service import GitTopologyService
from .models.api_models import (
    RepositoryStatsResponse,
    FileListResponse,
    FileListQueryParams,
    SemanticSearchRequest,
    SemanticSearchResponse,
    HealthCheckResponse,
)
from .services.stats_service import stats_service
from .services.file_service import file_service
from .services.search_service import search_service
from .services.health_service import health_service


# Constants for job operations and status
GOLDEN_REPO_ADD_OPERATION = "add_golden_repo"
GOLDEN_REPO_REFRESH_OPERATION = "refresh_golden_repo"
JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"


# Pydantic models for API requests/responses
class LoginRequest(BaseModel):
    """Login request model with input validation."""

    username: str = Field(
        ..., min_length=1, max_length=255, description="Username for authentication"
    )
    password: str = Field(
        ..., min_length=1, max_length=1000, description="Password for authentication"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty or contain only whitespace")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty or contain only whitespace")
        return v


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]
    refresh_token: Optional[str] = None
    refresh_token_expires_in: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh endpoint."""

    refresh_token: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Refresh token for token rotation",
    )

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, v: str) -> str:
        """Validate refresh token is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Refresh token cannot be empty or contain only whitespace")
        return v.strip()


class RefreshTokenResponse(BaseModel):
    """Response model for token refresh endpoint."""

    access_token: str
    refresh_token: str
    token_type: str
    user: Dict[str, Any]
    access_token_expires_in: Optional[int] = None
    refresh_token_expires_in: Optional[int] = None


class UserInfo(BaseModel):
    username: str
    role: str
    created_at: str


class CreateUserRequest(BaseModel):
    """Request model for creating new user."""

    username: str = Field(
        ..., min_length=1, max_length=255, description="Username for new user"
    )
    password: str = Field(
        ..., min_length=1, max_length=1000, description="Password for new user"
    )
    role: str = Field(
        ..., description="Role for new user (admin, power_user, normal_user)"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty or contain only whitespace")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty or contain only whitespace")
        if not validate_password_complexity(v):
            raise ValueError(get_password_complexity_error_message())
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is valid UserRole."""
        try:
            UserRole(v)
            return v
        except ValueError:
            raise ValueError(
                f"Invalid role. Must be one of: {', '.join([role.value for role in UserRole])}"
            )


class UpdateUserRequest(BaseModel):
    """Request model for updating user."""

    role: str = Field(
        ..., description="New role for user (admin, power_user, normal_user)"
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is valid UserRole."""
        try:
            UserRole(v)
            return v
        except ValueError:
            raise ValueError(
                f"Invalid role. Must be one of: {', '.join([role.value for role in UserRole])}"
            )


class ChangePasswordRequest(BaseModel):
    """Request model for changing password."""

    old_password: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Current password for verification",
    )
    new_password: str = Field(
        ..., min_length=1, max_length=1000, description="New password"
    )

    @field_validator("old_password")
    @classmethod
    def validate_old_password(cls, v: str) -> str:
        """Validate old password is not empty."""
        if not v or not v.strip():
            raise ValueError("Old password cannot be empty or contain only whitespace")
        return v

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password complexity."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty or contain only whitespace")
        if not validate_password_complexity(v):
            raise ValueError(get_password_complexity_error_message())
        return v


class UserResponse(BaseModel):
    """Response model for user operations."""

    user: UserInfo
    message: str


class MessageResponse(BaseModel):
    """Response model for simple messages."""

    message: str


class RegistrationRequest(BaseModel):
    """Request model for user registration."""

    username: str = Field(
        ..., min_length=1, max_length=50, description="Username for registration"
    )
    email: str = Field(..., min_length=1, max_length=255, description="Email address")
    password: str = Field(
        ..., min_length=1, max_length=1000, description="Password for new account"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username is not empty."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty or contain only whitespace")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if not v or not v.strip():
            raise ValueError("Email cannot be empty or contain only whitespace")
        # Basic email validation
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty or contain only whitespace")
        if not validate_password_complexity(v):
            raise ValueError(get_password_complexity_error_message())
        return v


class PasswordResetRequest(BaseModel):
    """Request model for password reset."""

    email: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Email address for password reset",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if not v or not v.strip():
            raise ValueError("Email cannot be empty or contain only whitespace")
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip().lower()


class AddGoldenRepoRequest(BaseModel):
    """Request model for adding golden repositories."""

    repo_url: str = Field(
        ..., min_length=1, max_length=1000, description="Git repository URL"
    )
    alias: str = Field(
        ..., min_length=1, max_length=100, description="Unique alias for repository"
    )
    default_branch: str = Field(
        default="main", min_length=1, max_length=100, description="Default branch"
    )

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        """Validate repository URL format."""
        v = v.strip()
        if not v:
            raise ValueError("Repository URL cannot be empty")
        if not v.startswith(("http://", "https://", "git@", "file://", "/")):
            raise ValueError("Repository URL must be a valid HTTP(S), SSH, or file URL")
        return v

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, v: str) -> str:
        """Validate alias format."""
        v = v.strip()
        if not v:
            raise ValueError("Alias cannot be empty")
        # Allow alphanumeric, hyphens, and underscores
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Alias must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v

    @field_validator("default_branch")
    @classmethod
    def validate_default_branch(cls, v: str) -> str:
        """Validate branch name."""
        v = v.strip()
        if not v:
            raise ValueError("Branch name cannot be empty")
        return v


class GoldenRepoInfo(BaseModel):
    """Model for golden repository information."""

    alias: str
    repo_url: str
    default_branch: str
    clone_path: str
    created_at: str


class JobResponse(BaseModel):
    """Response model for background job operations."""

    job_id: str
    message: str


class JobStatusResponse(BaseModel):
    """Response model for job status queries."""

    job_id: str
    operation_type: str
    status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    progress: int
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    username: str  # Added for user tracking


class JobListResponse(BaseModel):
    """Response model for job listing."""

    jobs: List[JobStatusResponse]
    total: int
    limit: int
    offset: int


class JobCancellationResponse(BaseModel):
    """Response model for job cancellation."""

    success: bool
    message: str


class JobCleanupResponse(BaseModel):
    """Response model for job cleanup."""

    cleaned_count: int
    message: str


class ActivateRepositoryRequest(BaseModel):
    """Request model for activating repositories."""

    golden_repo_alias: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Golden repository alias to activate",
    )
    branch_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Branch to activate (defaults to golden repo's default branch)",
    )
    user_alias: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="User's alias for the repo (defaults to golden_repo_alias)",
    )

    @field_validator("golden_repo_alias")
    @classmethod
    def validate_golden_repo_alias(cls, v: str) -> str:
        """Validate golden repo alias is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError(
                "Golden repo alias cannot be empty or contain only whitespace"
            )
        return v.strip()

    @field_validator("user_alias")
    @classmethod
    def validate_user_alias(cls, v: Optional[str]) -> Optional[str]:
        """Validate user alias if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("User alias cannot be empty or contain only whitespace")
        return v.strip() if v else None


class ActivatedRepositoryInfo(BaseModel):
    """Model for activated repository information."""

    user_alias: str
    golden_repo_alias: str
    current_branch: str
    activated_at: str
    last_accessed: str


class SwitchBranchRequest(BaseModel):
    """Request model for switching repository branch."""

    branch_name: str = Field(
        ..., min_length=1, max_length=255, description="Branch name to switch to"
    )

    @field_validator("branch_name")
    @classmethod
    def validate_branch_name(cls, v: str) -> str:
        """Validate branch name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Branch name cannot be empty or contain only whitespace")
        return v.strip()


class SemanticQueryRequest(BaseModel):
    """Request model for semantic query operations."""

    query_text: str = Field(
        ..., min_length=1, max_length=1000, description="Natural language query text"
    )
    repository_alias: Optional[str] = Field(
        None, max_length=255, description="Specific repository to search (optional)"
    )
    limit: int = Field(
        default=10, ge=1, le=100, description="Maximum number of results to return"
    )
    min_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity score threshold"
    )
    file_extensions: Optional[List[str]] = Field(
        None,
        description="Filter results to specific file extensions (e.g., ['.py', '.js'])",
    )
    async_query: bool = Field(
        default=False, description="Submit as background job if True"
    )

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, v: str) -> str:
        """Validate query text is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Query text cannot be empty or contain only whitespace")
        return v.strip()

    @field_validator("repository_alias")
    @classmethod
    def validate_repository_alias(cls, v: Optional[str]) -> Optional[str]:
        """Validate repository alias if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError(
                "Repository alias cannot be empty or contain only whitespace"
            )
        return v.strip() if v else None

    @field_validator("file_extensions")
    @classmethod
    def validate_file_extensions(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate file extensions format and convert empty list to None."""
        if v is None:
            return None

        if len(v) == 0:
            return None  # Convert empty list to None (no filtering)

        validated_extensions = []
        for ext in v:
            if not ext or not ext.strip():
                raise ValueError(
                    "File extensions cannot be empty or contain only whitespace"
                )

            ext = ext.strip()

            # Must start with dot
            if not ext.startswith("."):
                raise ValueError(f"File extensions must start with dot: {ext}")

            # Must contain only alphanumeric characters after the dot
            if len(ext) <= 1:
                raise ValueError(f"File extensions must have content after dot: {ext}")

            extension_part = ext[1:]  # Remove the dot
            if not extension_part.replace("_", "").replace("-", "").isalnum():
                raise ValueError(
                    f"File extensions must contain only alphanumeric characters, hyphens, and underscores: {ext}"
                )

            validated_extensions.append(ext)

        return validated_extensions


class QueryResultItem(BaseModel):
    """Individual query result item."""

    file_path: str
    line_number: int
    code_snippet: str
    similarity_score: float
    repository_alias: str


class QueryMetadata(BaseModel):
    """Query execution metadata."""

    query_text: str
    execution_time_ms: int
    repositories_searched: int
    timeout_occurred: bool


class SemanticQueryResponse(BaseModel):
    """Response model for semantic query operations."""

    results: List[QueryResultItem]
    total_results: int
    query_metadata: QueryMetadata


class RepositoryInfo(BaseModel):
    """Model for basic repository information."""

    alias: str
    repo_url: str
    default_branch: str
    created_at: str


class RepositoryDetailsResponse(BaseModel):
    """Model for detailed repository information."""

    alias: str
    repo_url: str
    default_branch: str
    clone_path: str
    created_at: str
    activation_status: str
    branches_list: List[str]
    file_count: int
    index_size: int
    last_updated: str


class RepositoryListResponse(BaseModel):
    """Response model for repository listing endpoints."""

    repositories: List[RepositoryInfo]
    total: int


class RepositorySyncResponse(BaseModel):
    """Response model for repository sync operation."""

    message: str
    changes_applied: bool
    files_changed: Optional[int] = None
    changed_files: Optional[List[str]] = None


class BranchInfo(BaseModel):
    """Model for individual branch information."""

    name: str
    type: str  # "local" or "remote"
    is_current: bool
    remote_ref: Optional[str] = None
    last_commit_hash: Optional[str] = None
    last_commit_message: Optional[str] = None
    last_commit_date: Optional[str] = None


class RepositoryBranchesResponse(BaseModel):
    """Response model for repository branches listing."""

    branches: List[BranchInfo]
    current_branch: str
    total_branches: int
    local_branches: int
    remote_branches: int


class RepositoryStatistics(BaseModel):
    """Model for repository statistics."""

    total_files: int
    indexed_files: int
    total_size_bytes: int
    embeddings_count: int
    languages: List[str]


class GitInfo(BaseModel):
    """Model for git repository information."""

    current_branch: str
    branches: List[str]
    last_commit: str
    remote_url: Optional[str] = None


class RepositoryConfiguration(BaseModel):
    """Model for repository configuration."""

    ignore_patterns: List[str]
    chunk_size: int
    overlap: int
    embedding_model: str


class RepositoryDetailsV2Response(BaseModel):
    """Model for detailed repository information (API v2 response)."""

    id: str
    name: str
    path: str
    owner_id: str
    created_at: str
    updated_at: str
    last_sync_at: Optional[str] = None
    status: str  # "indexed", "indexing", "error", "pending"
    indexing_progress: float  # 0-100
    statistics: RepositoryStatistics
    git_info: GitInfo
    configuration: RepositoryConfiguration
    errors: List[str]


class RepositorySyncRequest(BaseModel):
    """Request model for repository synchronization."""

    force: bool = Field(
        default=False, description="Force sync by cancelling existing sync jobs"
    )
    full_reindex: bool = Field(
        default=False, description="Perform full reindexing instead of incremental"
    )
    incremental: bool = Field(
        default=True, description="Perform incremental sync for changed files only"
    )
    pull_remote: bool = Field(
        default=False, description="Pull from remote repository before sync"
    )
    remote: str = Field(
        default="origin", description="Remote name for git pull operation"
    )
    branches: Optional[List[str]] = Field(
        default=["current"], description="Branches to sync (defaults to current branch)"
    )
    ignore_patterns: Optional[List[str]] = Field(
        default=None, description="Additional ignore patterns for this sync"
    )
    progress_webhook: Optional[str] = Field(
        default=None, description="Webhook URL for progress updates"
    )


class SyncProgress(BaseModel):
    """Model for sync progress information."""

    percentage: int = Field(ge=0, le=100, description="Progress percentage")
    files_processed: int = Field(ge=0, description="Number of files processed")
    files_total: int = Field(ge=0, description="Total number of files to process")
    current_file: Optional[str] = Field(description="Currently processing file")


class SyncJobOptions(BaseModel):
    """Model for sync job options."""

    force: bool
    full_reindex: bool
    incremental: bool


class RepositorySyncJobResponse(BaseModel):
    """Response model for repository sync job submission."""

    job_id: str = Field(description="Unique job identifier")
    status: str = Field(description="Job status (queued, running, completed, failed)")
    repository_id: str = Field(description="Repository identifier being synced")
    created_at: str = Field(description="Job creation timestamp")
    estimated_completion: Optional[str] = Field(description="Estimated completion time")
    progress: SyncProgress = Field(description="Current sync progress")
    options: SyncJobOptions = Field(description="Sync job options")


# Global managers (initialized in create_app)
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None
refresh_token_manager: Optional[RefreshTokenManager] = None
golden_repo_manager: Optional[GoldenRepoManager] = None
background_job_manager: Optional[BackgroundJobManager] = None
activated_repo_manager: Optional[ActivatedRepoManager] = None
repository_listing_manager: Optional[RepositoryListingManager] = None
semantic_query_manager: Optional[SemanticQueryManager] = None

# Server startup time for health monitoring
_server_start_time: Optional[str] = None


def get_server_uptime() -> Optional[int]:
    """
    Get server uptime in seconds.

    Returns:
        Uptime in seconds, or None if startup time not available
    """
    global _server_start_time
    if not _server_start_time:
        return None

    try:
        started_at = datetime.fromisoformat(_server_start_time)
        uptime = datetime.now(timezone.utc) - started_at
        return int(uptime.total_seconds())
    except (ValueError, TypeError):
        return None


def get_server_start_time() -> Optional[str]:
    """
    Get server startup timestamp.

    Returns:
        ISO format timestamp string, or None if not available
    """
    return _server_start_time


def get_system_resources() -> Optional[Dict[str, Any]]:
    """
    Get system resource usage information.

    Returns:
        Dictionary with memory and CPU usage, or None if unavailable
    """
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()

        # Get CPU usage (averaged over short period)
        cpu_percent = process.cpu_percent(interval=0.1)

        return {
            "memory_usage_mb": round(memory_info.rss / 1024 / 1024),
            "memory_usage_percent": round(memory_percent, 1),
            "cpu_usage_percent": round(cpu_percent, 1),
        }
    except Exception:
        return None


def check_database_health() -> Optional[Dict[str, str]]:
    """
    Check health of database connections.

    Returns:
        Dictionary with database health status, or None if unavailable
    """
    try:
        health_status = {}

        # Check user manager database health
        if user_manager:
            try:
                # Simple check - get user count
                user_manager.get_all_users()
                health_status["users_db"] = "healthy"
            except Exception:
                health_status["users_db"] = "unhealthy"

        # Check background job manager health
        if background_job_manager:
            try:
                # Simple check - get job count
                background_job_manager.get_active_job_count()
                health_status["jobs_db"] = "healthy"
            except Exception:
                health_status["jobs_db"] = "unhealthy"

        return health_status if health_status else None
    except Exception:
        return None


def get_recent_errors() -> Optional[List[Dict[str, Any]]]:
    """
    Get recent error information.

    Returns:
        List of recent errors, or None if unavailable
    """
    try:
        # This is a placeholder - in a real implementation,
        # this would read from log files or error tracking system
        return []
    except Exception:
        return None


def _execute_repository_sync(
    repo_id: str,
    username: str,
    options: Dict[str, Any],
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """
    Execute repository synchronization in background job.

    Args:
        repo_id: Repository identifier to sync
        username: Username requesting the sync
        options: Sync options (incremental, force, pull_remote, etc.)
        progress_callback: Optional callback for progress updates

    Returns:
        Sync result dictionary

    Raises:
        ActivatedRepoError: If repository not found or not accessible
        GitOperationError: If git operations fail
    """
    if progress_callback:
        progress_callback(10)  # Starting sync

    try:
        # Find the repository by trying different strategies
        repo_found = False
        user_alias = None

        # Strategy 1: Look for activated repository matching repo_id
        if activated_repo_manager:
            activated_repos = activated_repo_manager.list_activated_repositories(
                username
            )
            for repo in activated_repos:
                if (
                    repo["user_alias"] == repo_id
                    or repo["golden_repo_alias"] == repo_id
                ):
                    user_alias = repo["user_alias"]
                    repo_found = True
                    break

        if not repo_found:
            raise ActivatedRepoError(
                f"Repository '{repo_id}' not found for user '{username}'"
            )

        if progress_callback:
            progress_callback(25)  # Repository found, starting sync

        # Handle git pull if requested
        if options.get("pull_remote", False):
            if progress_callback:
                progress_callback(40)  # Pulling remote changes
            # Git pull will be handled by sync_with_golden_repository

        if progress_callback:
            progress_callback(60)  # Starting repository sync

        # Execute the actual sync using existing functionality
        if activated_repo_manager and user_alias:
            sync_result = activated_repo_manager.sync_with_golden_repository(
                username=username, user_alias=user_alias
            )
        else:
            raise ActivatedRepoError("Repository manager not available")

        if progress_callback:
            progress_callback(90)  # Sync completed, finalizing

        # Prepare result based on sync outcome
        result = {
            "success": sync_result.get("success", True),
            "message": sync_result.get(
                "message", f"Repository '{repo_id}' synchronized successfully"
            ),
            "repository_id": repo_id,
            "changes_applied": sync_result.get("changes_applied", False),
            "files_changed": sync_result.get("files_changed", 0),
            "options_used": {
                "incremental": options.get("incremental", True),
                "force": options.get("force", False),
                "pull_remote": options.get("pull_remote", False),
            },
        }

        if progress_callback:
            progress_callback(100)  # Complete

        return result

    except Exception as e:
        # Re-raise known exceptions
        if isinstance(e, (ActivatedRepoError, GitOperationError)):
            raise
        # Wrap unknown exceptions
        raise GitOperationError(f"Repository sync failed: {str(e)}")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    global jwt_manager, user_manager, refresh_token_manager, golden_repo_manager, background_job_manager, activated_repo_manager, repository_listing_manager, semantic_query_manager, _server_start_time

    # Set server start time for health monitoring
    _server_start_time = datetime.now(timezone.utc).isoformat()

    # Create FastAPI app with metadata
    app = FastAPI(
        title="CIDX Multi-User Server",
        description="Multi-user semantic code search server with JWT authentication",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add global error handler middleware
    global_error_handler = GlobalErrorHandler()
    app.add_middleware(GlobalErrorHandler)

    # Add exception handlers for validation errors that FastAPI catches before middleware
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        error_data = global_error_handler.handle_validation_error(exc, request)
        return global_error_handler._create_error_response(error_data)

    # Initialize authentication managers with persistent JWT secret
    jwt_secret_manager = JWTSecretManager()
    secret_key = jwt_secret_manager.get_or_create_secret()
    jwt_manager = JWTManager(
        secret_key=secret_key, token_expiration_minutes=10, algorithm="HS256"
    )
    user_manager = UserManager()
    refresh_token_manager = RefreshTokenManager(jwt_manager=jwt_manager)
    golden_repo_manager = GoldenRepoManager()
    background_job_manager = BackgroundJobManager()
    activated_repo_manager = ActivatedRepoManager(
        golden_repo_manager=golden_repo_manager,
        background_job_manager=background_job_manager,
    )
    repository_listing_manager = RepositoryListingManager(
        golden_repo_manager=golden_repo_manager,
        activated_repo_manager=activated_repo_manager,
    )
    semantic_query_manager = SemanticQueryManager(
        activated_repo_manager=activated_repo_manager,
        background_job_manager=background_job_manager,
    )

    # Set global dependencies
    dependencies.jwt_manager = jwt_manager
    dependencies.user_manager = user_manager

    # Seed initial admin user
    user_manager.seed_initial_admin()

    # Health endpoint (requires authentication for security)
    @app.get("/health")
    async def health_check(
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Enhanced health check endpoint.

        Provides detailed server status including uptime, job queue health,
        system resource usage, and recent error information. Authentication
        required to prevent information disclosure.
        """
        try:
            # Calculate uptime
            uptime = get_server_uptime()

            # Get job queue health
            try:
                active_jobs = (
                    background_job_manager.get_active_job_count()
                    if background_job_manager
                    else 0
                )
            except Exception:
                active_jobs = 0

            try:
                pending_jobs = (
                    background_job_manager.get_pending_job_count()
                    if background_job_manager
                    else 0
                )
            except Exception:
                pending_jobs = 0

            try:
                failed_jobs = (
                    background_job_manager.get_failed_job_count()
                    if background_job_manager
                    else 0
                )
            except Exception:
                failed_jobs = 0

            # Get system resources
            try:
                system_resources = get_system_resources()
            except Exception:
                system_resources = None

            # Get database health
            try:
                database_health = check_database_health()
            except Exception:
                database_health = None

            # Get recent errors
            try:
                recent_errors = get_recent_errors()
            except Exception:
                recent_errors = None

            # Determine overall status
            status = "healthy"
            message = "CIDX Server is running"

            if failed_jobs > 0:
                status = "degraded"
                message = (
                    f"CIDX Server is running but {failed_jobs} failed jobs detected"
                )
            elif pending_jobs > 8:  # High pending job threshold
                status = "warning"
                message = f"CIDX Server is running with high pending job count ({pending_jobs})"

            health_response = {
                "status": status,
                "message": message,
                "uptime": uptime,
                "active_jobs": active_jobs,
                "job_queue": {
                    "active_jobs": active_jobs,
                    "pending_jobs": pending_jobs,
                    "failed_jobs": failed_jobs,
                },
                "started_at": get_server_start_time(),
            }

            # Add version if available
            try:
                from code_indexer import __version__

                health_response["version"] = __version__
            except Exception:
                health_response["version"] = "unknown"

            # Add system resources if available
            if system_resources:
                health_response["system_resources"] = system_resources

            # Add database health if available
            if database_health:
                health_response["database"] = database_health  # type: ignore[assignment]

            # Add recent errors if available
            if recent_errors:
                health_response["recent_errors"] = recent_errors  # type: ignore[assignment]

            return health_response

        except Exception as e:
            # Health endpoint should never fail completely
            return {
                "status": "degraded",
                "message": f"Health check partial failure: {str(e)}",
                "uptime": None,
                "active_jobs": 0,
            }

    @app.post("/auth/login", response_model=LoginResponse)
    async def login(login_data: LoginRequest, request: Request):
        """
        Authenticate user and return JWT token with standardized security error responses.

        SECURITY FEATURES:
        - Generic error messages to prevent user enumeration
        - Timing attack prevention with constant response times (~100ms)
        - Dummy password hashing for non-existent users
        - Comprehensive audit logging of authentication attempts

        Args:
            login_data: Username and password
            request: HTTP request for client IP and user agent extraction

        Returns:
            JWT token and user information

        Raises:
            HTTPException: Generic "Invalid credentials" for all authentication failures
        """
        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        def authenticate_with_security():
            # Authenticate user
            user = user_manager.authenticate_user(
                login_data.username, login_data.password
            )

            if user is None:
                # Perform dummy password work to prevent timing-based user enumeration
                auth_error_handler.perform_dummy_password_work()

                # Create standardized error response with audit logging
                error_response = auth_error_handler.create_error_response(
                    AuthErrorType.INVALID_CREDENTIALS,
                    login_data.username,
                    internal_message=f"Authentication failed for username: {login_data.username}",
                    ip_address=client_ip,
                    user_agent=user_agent,
                )

                raise HTTPException(
                    status_code=error_response["status_code"],
                    detail=error_response["message"],
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return user

        # Execute authentication with timing attack prevention
        user = auth_error_handler.timing_prevention.constant_time_execute(
            authenticate_with_security
        )

        # Create JWT token and refresh token
        user_data = {
            "username": user.username,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
        }

        # Create token family and initial refresh token
        family_id = refresh_token_manager.create_token_family(user.username)
        token_data = refresh_token_manager.create_initial_refresh_token(
            family_id=family_id, username=user.username, user_data=user_data
        )

        return LoginResponse(
            access_token=token_data["access_token"],
            token_type="bearer",
            user=user.to_dict(),
            refresh_token=token_data["refresh_token"],
            refresh_token_expires_in=token_data["refresh_token_expires_in"],
        )

    @app.post("/auth/register", response_model=MessageResponse)
    async def register(registration_data: RegistrationRequest, request: Request):
        """
        Register new user account with standardized security responses.

        SECURITY FEATURES:
        - Generic success message regardless of account existence
        - Timing attack prevention with constant response times
        - No immediate indication of duplicate accounts
        - Comprehensive audit logging of registration attempts

        Args:
            registration_data: User registration information
            request: HTTP request for client IP and user agent extraction

        Returns:
            Generic success message for all registration attempts
        """
        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        def process_registration():
            # Check if account already exists
            try:
                existing_user = user_manager.get_user(registration_data.username)
                account_exists = existing_user is not None
            except Exception:
                account_exists = False

            if account_exists:
                # Account exists - return generic success but don't create account
                response = auth_error_handler.create_registration_response(
                    email=registration_data.email,
                    account_exists=True,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return response
            else:
                # New account - actually create the user
                try:
                    user_manager.create_user(
                        registration_data.username,
                        registration_data.password,
                        "normal_user",  # Default role for new registrations
                    )

                    response = auth_error_handler.create_registration_response(
                        email=registration_data.email,
                        account_exists=False,
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
                    return response
                except Exception:
                    # Even if creation fails, return generic success
                    response = auth_error_handler.create_registration_response(
                        email=registration_data.email,
                        account_exists=False,
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
                    return response

        # Execute registration with timing attack prevention
        response = auth_error_handler.timing_prevention.constant_time_execute(
            process_registration
        )

        return MessageResponse(message=response["message"])

    @app.post("/auth/reset-password", response_model=MessageResponse)
    async def reset_password(reset_data: PasswordResetRequest, request: Request):
        """
        Initiate password reset process with standardized security responses.

        SECURITY FEATURES:
        - Generic success message regardless of account existence
        - Timing attack prevention with constant response times
        - No indication whether email corresponds to existing account
        - Comprehensive audit logging of reset attempts

        Args:
            reset_data: Password reset request information
            request: HTTP request for client IP and user agent extraction

        Returns:
            Generic message indicating email will be sent if account exists
        """
        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        def process_password_reset():
            # Check if account exists (but don't reveal this to the client)
            try:
                # Note: This is a simplified implementation
                # In a real system, you'd look up users by email
                # For now, we'll simulate account existence check
                account_exists = (
                    False  # Placeholder - would check user database by email
                )

                if account_exists:
                    # Send actual password reset email
                    # TODO: Implement email sending functionality
                    pass
                else:
                    # Don't send email, but perform same timing work
                    pass

                response = auth_error_handler.create_password_reset_response(
                    email=reset_data.email,
                    account_exists=account_exists,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return response
            except Exception:
                # Even if process fails, return generic success
                response = auth_error_handler.create_password_reset_response(
                    email=reset_data.email,
                    account_exists=False,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return response

        # Execute password reset with timing attack prevention
        response = auth_error_handler.timing_prevention.constant_time_execute(
            process_password_reset
        )

        return MessageResponse(message=response["message"])

    @app.post("/api/auth/refresh", response_model=RefreshTokenResponse)
    async def refresh_token_secure(
        refresh_request: RefreshTokenRequest,
        request: Request,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Secure token refresh endpoint with comprehensive security measures.

        SECURITY FEATURES:
        - Refresh token rotation (new access + refresh token pair)
        - Token family tracking for replay attack detection
        - Rate limiting (10 attempts, 5-minute lockout)
        - Comprehensive audit logging (success/failure/security incidents)
        - Concurrent refresh protection with 409 Conflict handling
        - Invalid/expired/revoked token rejection with 401 Unauthorized

        Args:
            refresh_request: Refresh token request containing refresh token
            request: HTTP request for extracting client IP and user agent
            current_user: Current authenticated user

        Returns:
            New access and refresh token pair with user information

        Raises:
            HTTPException: 401 for invalid tokens, 429 for rate limiting,
                          409 for concurrent refresh, 500 for other errors
        """
        username = current_user.username

        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        # Check rate limiting first
        rate_limit_error = refresh_token_rate_limiter.check_rate_limit(username)
        if rate_limit_error:
            # Log rate limit hit
            password_audit_logger.log_token_refresh_failure(
                username=username,
                ip_address=client_ip,
                reason="Rate limit exceeded",
                user_agent=user_agent,
                additional_context={
                    "attempt_count": refresh_token_rate_limiter.get_attempt_count(
                        username
                    )
                },
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_limit_error
            )

        try:
            # Validate and rotate refresh token
            result = refresh_token_manager.validate_and_rotate_refresh_token(
                refresh_token=refresh_request.refresh_token, client_ip=client_ip
            )

            if not result["valid"]:
                # Record failed attempt for rate limiting
                refresh_token_rate_limiter.record_failed_attempt(username)

                # Determine if this is a security incident
                is_security_incident = result.get("security_incident", False)

                # Log failed attempt
                password_audit_logger.log_token_refresh_failure(
                    username=username,
                    ip_address=client_ip,
                    reason=result["error"],
                    security_incident=is_security_incident,
                    user_agent=user_agent,
                    additional_context=result,
                )

                # Determine HTTP status code based on error type
                if "concurrent" in result["error"].lower():
                    status_code = status.HTTP_409_CONFLICT
                else:
                    status_code = status.HTTP_401_UNAUTHORIZED

                raise HTTPException(status_code=status_code, detail=result["error"])

            # Success - clear rate limiting
            refresh_token_rate_limiter.record_successful_attempt(username)

            # Log successful refresh
            password_audit_logger.log_token_refresh_success(
                username=username,
                ip_address=client_ip,
                family_id=result["family_id"],
                user_agent=user_agent,
                additional_context={
                    "token_id": result["token_id"],
                    "parent_token_id": result["parent_token_id"],
                },
            )

            return RefreshTokenResponse(
                access_token=result["new_access_token"],
                refresh_token=result["new_refresh_token"],
                token_type="bearer",
                user=current_user.to_dict(),
                access_token_expires_in=jwt_manager.token_expiration_minutes * 60,
                refresh_token_expires_in=refresh_token_manager.refresh_token_lifetime_days
                * 24
                * 60
                * 60,
            )

        except HTTPException:
            # Re-raise HTTP exceptions (they're already properly formatted)
            raise

        except Exception as e:
            # Log unexpected errors
            password_audit_logger.log_token_refresh_failure(
                username=username,
                ip_address=client_ip,
                reason=f"Internal error: {str(e)}",
                security_incident=True,
                user_agent=user_agent,
                additional_context={"error_type": type(e).__name__},
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed due to internal error",
            )

    @app.post("/auth/refresh", response_model=LoginResponse)
    async def refresh_token(
        current_user: dependencies.User = Depends(dependencies.get_current_user),
        credentials: dependencies.HTTPAuthorizationCredentials = Depends(
            dependencies.security
        ),
    ):
        """
        Refresh JWT token for authenticated user.

        Args:
            current_user: Current authenticated user (validates token)
            credentials: JWT token from Authorization header

        Returns:
            New JWT token with extended expiration and user information

        Raises:
            HTTPException: If token refresh fails
        """
        try:
            # Extend the current token's expiration
            new_access_token = jwt_manager.extend_token_expiration(
                credentials.credentials
            )

            return LoginResponse(
                access_token=new_access_token,
                token_type="bearer",
                user=current_user.to_dict(),
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token refresh failed: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Protected endpoints (require authentication)
    @app.get("/api/repos", response_model=List[ActivatedRepositoryInfo])
    async def list_repositories(
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List activated repositories for current user.

        Args:
            current_user: Current authenticated user

        Returns:
            List of activated repositories for the user
        """
        try:
            repos = activated_repo_manager.list_activated_repositories(
                current_user.username
            )
            return [ActivatedRepositoryInfo(**repo) for repo in repos]

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list repositories: {str(e)}",
            )

    @app.get("/api/admin/users")
    async def list_users(
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        List all users (admin only).

        Returns:
            List of all users
        """
        all_users = user_manager.get_all_users()
        return {
            "users": [user.to_dict() for user in all_users],
            "total": len(all_users),
        }

    @app.post("/api/admin/users", response_model=UserResponse, status_code=201)
    async def create_user(
        user_data: CreateUserRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Create new user (admin only).

        Args:
            user_data: User creation data
            current_user: Current authenticated admin user

        Returns:
            Created user information

        Raises:
            HTTPException: If user creation fails
        """
        try:
            # Convert string role to UserRole enum
            role_enum = UserRole(user_data.role)

            # Create user through UserManager
            new_user = user_manager.create_user(
                username=user_data.username, password=user_data.password, role=role_enum
            )

            return UserResponse(
                user=UserInfo(
                    username=new_user.username,
                    role=new_user.role.value,
                    created_at=new_user.created_at.isoformat(),
                ),
                message=f"User '{user_data.username}' created successfully",
            )

        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.put("/api/admin/users/{username}", response_model=MessageResponse)
    async def update_user(
        username: str,
        user_data: UpdateUserRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Update user role (admin only).

        Args:
            username: Username to update
            user_data: User update data
            current_user: Current authenticated admin user

        Returns:
            Success message

        Raises:
            HTTPException: If user not found or update fails
        """
        # Check if user exists
        existing_user = user_manager.get_user(username)
        if existing_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {username}",
            )

        try:
            # Convert string role to UserRole enum
            role_enum = UserRole(user_data.role)

            # Update user role
            success = user_manager.update_user_role(username, role_enum)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User not found: {username}",
                )

            return MessageResponse(message=f"User '{username}' updated successfully")

        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.delete("/api/admin/users/{username}", response_model=MessageResponse)
    async def delete_user(
        username: str,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Delete user (admin only).

        Args:
            username: Username to delete
            current_user: Current authenticated admin user

        Returns:
            Success message

        Raises:
            HTTPException: If user not found or deletion would remove last admin
        """
        # Get user to check if it exists and get their role
        user_to_delete = user_manager.get_user(username)
        if user_to_delete is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {username}",
            )

        # CRITICAL SECURITY CHECK: Prevent deletion of last admin user
        # This prevents system lockout by ensuring at least one admin remains
        if user_to_delete.role == UserRole.ADMIN:
            all_users = user_manager.get_all_users()
            admin_count = sum(1 for user in all_users if user.role == UserRole.ADMIN)

            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user. System requires at least one admin user to remain accessible.",
                )

        success = user_manager.delete_user(username)
        if not success:
            # This should not happen since we already checked user exists above,
            # but keeping for defensive programming
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {username}",
            )

        return MessageResponse(message=f"User '{username}' deleted successfully")

    @app.put("/api/users/change-password", response_model=MessageResponse)
    async def change_current_user_password(
        password_data: ChangePasswordRequest,
        request: Request,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Secure password change endpoint with comprehensive security measures.

        SECURITY FEATURES:
        - Old password validation (fixes critical vulnerability)
        - Rate limiting (5 attempts, 15-minute lockout)
        - Timing attack prevention (constant response times)
        - Concurrent change protection (409 Conflict handling)
        - Comprehensive audit logging (success/failure/IP tracking)
        - Session invalidation (all user sessions invalidated after change)

        Args:
            password_data: Password change request with old and new passwords
            request: HTTP request for extracting client IP and user agent
            current_user: Current authenticated user

        Returns:
            Success message

        Raises:
            HTTPException: 401 for invalid old password, 429 for rate limiting,
                          409 for concurrent changes, 500 for other errors
        """
        username = current_user.username

        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        # Check rate limiting first
        rate_limit_error = password_change_rate_limiter.check_rate_limit(username)
        if rate_limit_error:
            # Log rate limit hit
            password_audit_logger.log_rate_limit_triggered(
                username=username,
                ip_address=client_ip,
                attempt_count=password_change_rate_limiter.get_attempt_count(username),
                user_agent=user_agent,
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_limit_error
            )

        # Acquire concurrency protection lock
        try:
            with password_change_concurrency_protection.acquire_password_change_lock(
                username
            ):

                def password_change_operation():
                    """Inner operation with timing attack prevention."""
                    # Get current user data for password verification
                    current_user_data = user_manager.get_user(username)
                    if not current_user_data:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"User not found: {username}",
                        )

                    # SECURITY FIX: Verify old password using constant-time comparison
                    old_password_valid = (
                        timing_attack_prevention.normalize_password_validation_timing(
                            user_manager.password_manager.verify_password,
                            password_data.old_password,
                            current_user_data.password_hash,
                        )
                    )

                    if not old_password_valid:
                        # Record failed attempt for rate limiting
                        should_lockout = (
                            password_change_rate_limiter.record_failed_attempt(username)
                        )

                        # Log failed attempt
                        password_audit_logger.log_password_change_failure(
                            username=username,
                            ip_address=client_ip,
                            reason="Invalid old password",
                            user_agent=user_agent,
                            additional_context={"should_lockout": should_lockout},
                        )

                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid old password",
                        )

                    # Old password is valid - proceed with password change
                    success = user_manager.change_password(
                        username, password_data.new_password
                    )
                    if not success:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Password change failed due to internal error",
                        )

                    # Clear rate limiting on successful change
                    password_change_rate_limiter.record_successful_attempt(username)

                    # Invalidate all user sessions (except current one will remain valid)
                    session_manager.invalidate_all_user_sessions(username)

                    # Revoke all refresh tokens for security
                    revoked_families = refresh_token_manager.revoke_user_tokens(
                        username, "password_change"
                    )

                    # Log successful password change
                    password_audit_logger.log_password_change_success(
                        username=username,
                        ip_address=client_ip,
                        user_agent=user_agent,
                        additional_context={
                            "sessions_invalidated": True,
                            "refresh_token_families_revoked": revoked_families,
                        },
                    )

                    return "Password changed successfully"

                # Execute password change with timing attack prevention
                message = timing_attack_prevention.constant_time_execute(
                    password_change_operation
                )
                return MessageResponse(message=message)

        except ConcurrencyConflictError as e:
            # Log concurrent change conflict
            password_audit_logger.log_concurrent_change_conflict(
                username=username, ip_address=client_ip, user_agent=user_agent
            )

            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

        except HTTPException:
            # Re-raise HTTP exceptions (they're already properly formatted)
            raise

        except Exception as e:
            # Log unexpected errors
            password_audit_logger.log_password_change_failure(
                username=username,
                ip_address=client_ip,
                reason=f"Internal error: {str(e)}",
                user_agent=user_agent,
                additional_context={"error_type": type(e).__name__},
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Password change failed due to internal error",
            )

    @app.put(
        "/api/admin/users/{username}/change-password", response_model=MessageResponse
    )
    async def change_user_password(
        username: str,
        password_data: ChangePasswordRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Change any user's password (admin only).

        Args:
            username: Username whose password to change
            password_data: New password data
            current_user: Current authenticated admin user

        Returns:
            Success message

        Raises:
            HTTPException: If user not found
        """
        success = user_manager.change_password(username, password_data.new_password)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {username}",
            )

        return MessageResponse(
            message=f"Password changed successfully for user '{username}'"
        )

    @app.get("/api/admin/golden-repos")
    async def list_golden_repos(
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        List all golden repositories (admin only).

        Returns:
            List of golden repositories
        """
        repos = golden_repo_manager.list_golden_repos()
        return {
            "golden_repositories": repos,
            "total": len(repos),
        }

    @app.post("/api/admin/golden-repos", response_model=JobResponse, status_code=202)
    async def add_golden_repo(
        repo_data: AddGoldenRepoRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Add a golden repository (admin only) - async operation.

        Args:
            repo_data: Golden repository data
            current_user: Current authenticated admin user

        Returns:
            Job ID and message for tracking the async operation

        Raises:
            HTTPException: If job submission fails
        """
        try:
            # Submit background job for adding golden repo
            job_id = background_job_manager.submit_job(
                "add_golden_repo",
                golden_repo_manager.add_golden_repo,  # type: ignore[arg-type]
                repo_url=repo_data.repo_url,
                alias=repo_data.alias,
                default_branch=repo_data.default_branch,
                submitter_username=current_user.username,
            )
            return JobResponse(
                job_id=job_id,
                message=f"Golden repository '{repo_data.alias}' addition started",
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit job: {str(e)}",
            )

    @app.post(
        "/api/admin/golden-repos/{alias}/refresh",
        response_model=JobResponse,
        status_code=202,
    )
    async def refresh_golden_repo(
        alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Refresh a golden repository (admin only) - async operation.

        Args:
            alias: Alias of the repository to refresh
            current_user: Current authenticated admin user

        Returns:
            Job ID and message for tracking the async operation

        Raises:
            HTTPException: If job submission fails
        """
        try:
            # Submit background job for refreshing golden repo
            job_id = background_job_manager.submit_job(
                "refresh_golden_repo",
                golden_repo_manager.refresh_golden_repo,  # type: ignore[arg-type]
                alias=alias,
                submitter_username=current_user.username,
            )
            return JobResponse(
                job_id=job_id, message=f"Golden repository '{alias}' refresh started"
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit refresh job: {str(e)}",
            )

    @app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(
        job_id: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get status of a background job.

        Args:
            job_id: Job ID to check status for
            current_user: Current authenticated user

        Returns:
            Job status information

        Raises:
            HTTPException: If job not found
        """
        job_status = background_job_manager.get_job_status(
            job_id, current_user.username
        )
        if not job_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )

        return JobStatusResponse(
            job_id=job_status["job_id"],
            operation_type=job_status["operation_type"],
            status=job_status["status"],
            created_at=job_status["created_at"],
            started_at=job_status["started_at"],
            completed_at=job_status["completed_at"],
            progress=job_status["progress"],
            result=job_status["result"],
            error=job_status["error"],
            username=job_status["username"],
        )

    @app.get("/api/jobs", response_model=JobListResponse)
    async def list_jobs(
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List jobs for current user with filtering and pagination.

        Args:
            status: Filter jobs by status (pending, running, completed, failed, cancelled)
            limit: Maximum number of jobs to return (default: 10, max: 100)
            offset: Number of jobs to skip (default: 0)
            current_user: Current authenticated user

        Returns:
            List of jobs with pagination metadata
        """
        # Validate limit
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 1

        if offset < 0:
            offset = 0

        job_list = background_job_manager.list_jobs(
            username=current_user.username,
            status_filter=status,
            limit=limit,
            offset=offset,
        )

        # Convert job data to response models
        jobs = []
        for job_data in job_list["jobs"]:
            jobs.append(
                JobStatusResponse(
                    job_id=job_data["job_id"],
                    operation_type=job_data["operation_type"],
                    status=job_data["status"],
                    created_at=job_data["created_at"],
                    started_at=job_data["started_at"],
                    completed_at=job_data["completed_at"],
                    progress=job_data["progress"],
                    result=job_data["result"],
                    error=job_data["error"],
                    username=job_data["username"],
                )
            )

        return JobListResponse(
            jobs=jobs,
            total=job_list["total"],
            limit=job_list["limit"],
            offset=job_list["offset"],
        )

    @app.delete("/api/jobs/{job_id}", response_model=JobCancellationResponse)
    async def cancel_job(
        job_id: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Cancel a background job.

        Args:
            job_id: Job ID to cancel
            current_user: Current authenticated user

        Returns:
            Cancellation result

        Raises:
            HTTPException: If job not found, not authorized, or cannot be cancelled
        """
        result = background_job_manager.cancel_job(job_id, current_user.username)

        if not result["success"]:
            if "not found or not authorized" in result["message"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail=result["message"]
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
                )

        return JobCancellationResponse(
            success=result["success"], message=result["message"]
        )

    @app.delete("/api/admin/jobs/cleanup", response_model=JobCleanupResponse)
    async def cleanup_old_jobs(
        max_age_hours: int = 24,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Clean up old completed/failed jobs (admin only).

        Args:
            max_age_hours: Maximum age of jobs to keep in hours (default: 24)
            current_user: Current authenticated admin user

        Returns:
            Number of jobs cleaned up
        """
        if max_age_hours < 1:
            max_age_hours = 1
        if max_age_hours > 8760:  # 1 year
            max_age_hours = 8760

        cleaned_count = background_job_manager.cleanup_old_jobs(
            max_age_hours=max_age_hours
        )

        return JobCleanupResponse(
            cleaned_count=cleaned_count,
            message=f"Cleaned up {cleaned_count} old background jobs",
        )

    @app.delete("/api/admin/golden-repos/{alias}", status_code=204)
    async def remove_golden_repo(
        alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Remove a golden repository (admin only).

        This endpoint implements comprehensive repository deletion with:
        - Proper HTTP 204 No Content response for successful deletions
        - Transaction management with rollback on failures
        - Graceful cancellation of active background jobs
        - Comprehensive resource cleanup in finally blocks
        - Proper error categorization and sanitized error messages
        - Protection against broken pipe errors and resource leaks

        Args:
            alias: Alias of the repository to remove
            current_user: Current authenticated admin user

        Returns:
            No content (HTTP 204) on successful deletion

        Raises:
            HTTPException: 404 if repository not found, 503 if services unavailable, 500 for other errors
        """
        try:
            # Cancel any active background jobs for this repository
            try:
                if background_job_manager:
                    # Get jobs related to this golden repository
                    active_jobs = (
                        background_job_manager.get_jobs_by_operation_and_params(
                            operation_types=[
                                GOLDEN_REPO_ADD_OPERATION,
                                GOLDEN_REPO_REFRESH_OPERATION,
                            ],
                            params_filter={"alias": alias},
                        )
                    )

                    # Cancel active jobs gracefully
                    for job in active_jobs:
                        if job.get("status") in [
                            JOB_STATUS_PENDING,
                            JOB_STATUS_RUNNING,
                        ]:
                            cancel_result = background_job_manager.cancel_job(
                                job["job_id"], current_user.username
                            )
                            if cancel_result["success"]:
                                logging.info(
                                    f"Cancelled background job {job['job_id']} for repository {alias}"
                                )
                            else:
                                logging.warning(
                                    f"Failed to cancel job {job['job_id']}: {cancel_result['message']}"
                                )
            except Exception as job_error:
                # Job cancellation failure shouldn't prevent deletion, but log it
                logging.warning(
                    f"Job cancellation failed during repository deletion: {job_error}"
                )

            # Perform repository deletion with proper error handling
            golden_repo_manager.remove_golden_repo(alias)

            logging.info(
                f"Successfully removed golden repository '{alias}' by user '{current_user.username}'"
            )

            # Return 204 No Content (no response body)
            return Response(status_code=204)

        except GitOperationError as e:
            error_msg = str(e).lower()

            # Categorize GitOperationError by underlying cause
            if any(
                service_term in error_msg
                for service_term in [
                    "qdrant connection refused",
                    "service unavailable",
                    "connection timeout",
                ]
            ):
                # External service issues - return 503 Service Unavailable
                sanitized_message = "Repository deletion failed due to service unavailability. Please try again later."
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=sanitized_message,
                )
            elif "broken pipe" in error_msg:
                # Sanitize broken pipe errors - don't expose internal details
                sanitized_message = "Repository deletion failed due to internal communication error. The operation may have completed partially."
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=sanitized_message,
                )
            else:
                # Other GitOperationErrors (permission, filesystem, etc.) - return 500
                # Keep more detail for compatibility with existing tests
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(
                        e
                    ),  # Preserve original error message for backward compatibility
                )

        except GoldenRepoError as e:
            # Repository not found - return 404
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),  # Safe to expose - just "repository not found"
            )

        except Exception as e:
            # Unexpected errors - return 500 with sanitized message
            logging.error(f"Unexpected error during repository deletion: {e}")
            detail_message = f"Failed to remove repository: {str(e)}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail_message,
            )

    @app.post("/api/repos/activate", response_model=JobResponse, status_code=202)
    async def activate_repository(
        request: ActivateRepositoryRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_power_user),
    ):
        """
        Activate repository for querying (power user or admin only) - async operation.

        Args:
            request: Repository activation request data
            current_user: Current authenticated power user or admin

        Returns:
            Job ID and message for tracking the async operation

        Raises:
            HTTPException: If golden repository not found or already activated
        """
        try:
            job_id = activated_repo_manager.activate_repository(
                username=current_user.username,
                golden_repo_alias=request.golden_repo_alias,
                branch_name=request.branch_name,
                user_alias=request.user_alias,
            )

            user_alias = request.user_alias or request.golden_repo_alias
            return JobResponse(
                job_id=job_id,
                message=f"Repository '{user_alias}' activation started for user '{current_user.username}'",
            )

        except ActivatedRepoError as e:
            if "not found" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to activate repository: {str(e)}",
            )

    @app.delete("/api/repos/{user_alias}", response_model=JobResponse, status_code=202)
    async def deactivate_repository(
        user_alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Deactivate repository for current user - async operation.

        Args:
            user_alias: User's alias for the repository to deactivate
            current_user: Current authenticated user

        Returns:
            Job ID and message for tracking the async operation

        Raises:
            HTTPException: If repository not found
        """
        try:
            job_id = activated_repo_manager.deactivate_repository(
                username=current_user.username,
                user_alias=user_alias,
            )

            return JobResponse(
                job_id=job_id,
                message=f"Repository '{user_alias}' deactivation started for user '{current_user.username}'",
            )

        except ActivatedRepoError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to deactivate repository: {str(e)}",
            )

    @app.put("/api/repos/{user_alias}/branch", response_model=MessageResponse)
    async def switch_repository_branch(
        user_alias: str,
        request: SwitchBranchRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Switch branch for an activated repository.

        Args:
            user_alias: User's alias for the repository
            request: Branch switching request data
            current_user: Current authenticated user

        Returns:
            Success message

        Raises:
            HTTPException: If repository not found or branch switch fails
        """
        try:
            result = activated_repo_manager.switch_branch(
                username=current_user.username,
                user_alias=user_alias,
                branch_name=request.branch_name,
            )

            return MessageResponse(message=result["message"])

        except ActivatedRepoError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except GitOperationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to switch branch: {str(e)}",
            )

    @app.get("/api/repos/{user_alias}", response_model=ActivatedRepositoryInfo)
    async def get_repository_details(
        user_alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get details of a specific activated repository.

        Args:
            user_alias: User's alias for the repository
            current_user: Current authenticated user

        Returns:
            Activated repository details

        Raises:
            HTTPException: If repository not found
        """
        try:
            repos = activated_repo_manager.list_activated_repositories(
                current_user.username
            )

            # Find the specific repository by user_alias
            for repo in repos:
                if repo["user_alias"] == user_alias:
                    return ActivatedRepositoryInfo(**repo)

            # Repository not found
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{user_alias}' not found for user '{current_user.username}'",
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get repository details: {str(e)}",
            )

    @app.put("/api/repos/{user_alias}/sync", response_model=RepositorySyncResponse)
    async def sync_repository(
        user_alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Sync activated repository with its golden repository.

        Fetches latest changes from the golden repository and merges them
        into the activated repository's current branch.

        Args:
            user_alias: User's alias for the repository
            current_user: Current authenticated user

        Returns:
            Sync operation result with details about changes applied

        Raises:
            HTTPException: If repository not found or sync operation fails
        """
        try:
            result = activated_repo_manager.sync_with_golden_repository(
                username=current_user.username,
                user_alias=user_alias,
            )

            return RepositorySyncResponse(
                message=result["message"],
                changes_applied=result["changes_applied"],
                files_changed=result.get("files_changed"),
                changed_files=result.get("changed_files"),
            )

        except ActivatedRepoError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except GitOperationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to sync repository: {str(e)}",
            )

    @app.get(
        "/api/repos/{user_alias}/branches", response_model=RepositoryBranchesResponse
    )
    async def list_repository_branches(
        user_alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List all branches in an activated repository.

        Returns both local and remote branches with detailed information
        including commit details and current branch indicator.

        Args:
            user_alias: User's alias for the repository
            current_user: Current authenticated user

        Returns:
            Branch listing with detailed information

        Raises:
            HTTPException: If repository not found or branch listing fails
        """
        try:
            result = activated_repo_manager.list_repository_branches(
                username=current_user.username,
                user_alias=user_alias,
            )

            # Convert the result to the response model
            branches = [
                BranchInfo(
                    name=branch["name"],
                    type=branch["type"],
                    is_current=branch["is_current"],
                    remote_ref=branch.get("remote_ref"),
                    last_commit_hash=branch.get("last_commit_hash"),
                    last_commit_message=branch.get("last_commit_message"),
                    last_commit_date=branch.get("last_commit_date"),
                )
                for branch in result["branches"]
            ]

            return RepositoryBranchesResponse(
                branches=branches,
                current_branch=result["current_branch"],
                total_branches=result["total_branches"],
                local_branches=result["local_branches"],
                remote_branches=result["remote_branches"],
            )

        except ActivatedRepoError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except GitOperationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list repository branches: {str(e)}",
            )

    @app.get("/api/repos/available", response_model=RepositoryListResponse)
    async def list_available_repositories(
        search: Optional[str] = None,
        repo_status: Optional[str] = None,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List available golden repositories for current user.

        Args:
            search: Optional search term to filter repositories
            repo_status: Optional status filter ("available" or "activated")
            current_user: Current authenticated user

        Returns:
            List of available repositories

        Raises:
            HTTPException: If query parameters are invalid
        """
        try:
            result = repository_listing_manager.list_available_repositories(
                username=current_user.username,
                search_term=search,
                status_filter=repo_status,
            )

            # Convert to response model
            repositories = [
                RepositoryInfo(
                    alias=repo["alias"],
                    repo_url=repo["repo_url"],
                    default_branch=repo["default_branch"],
                    created_at=repo["created_at"],
                )
                for repo in result["repositories"]
            ]

            return RepositoryListResponse(
                repositories=repositories,
                total=result["total"],
            )

        except RepositoryListingError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list repositories: {str(e)}",
            )

    @app.get("/api/repos/golden/{alias}", response_model=RepositoryDetailsResponse)
    async def get_golden_repository_details(
        alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get detailed information about a specific golden repository.

        Args:
            alias: Repository alias to get details for
            current_user: Current authenticated user

        Returns:
            Detailed repository information including activation status

        Raises:
            HTTPException: If repository not found
        """
        try:
            details = repository_listing_manager.get_repository_details(
                alias=alias, username=current_user.username
            )

            return RepositoryDetailsResponse(**details)

        except RepositoryListingError as e:
            if "not found" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get repository details: {str(e)}",
            )

    @app.post("/api/query")
    async def semantic_query(
        request: SemanticQueryRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Perform semantic query on activated repositories.

        Args:
            request: Semantic query request data
            current_user: Current authenticated user

        Returns:
            Query results with metadata or job information

        Raises:
            HTTPException: If query fails or user has no repositories
        """
        try:
            # Handle background job submission
            if request.async_query:
                job_id = semantic_query_manager.submit_query_job(
                    username=current_user.username,
                    query_text=request.query_text,
                    repository_alias=request.repository_alias,
                    limit=request.limit,
                    min_score=request.min_score,
                    file_extensions=request.file_extensions,
                )
                # Use JSONResponse to control status code
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "job_id": job_id,
                        "message": "Semantic query submitted as background job",
                    },
                )

            # Perform synchronous query
            results = semantic_query_manager.query_user_repositories(
                username=current_user.username,
                query_text=request.query_text,
                repository_alias=request.repository_alias,
                limit=request.limit,
                min_score=request.min_score,
                file_extensions=request.file_extensions,
            )

            return SemanticQueryResponse(
                results=[QueryResultItem(**result) for result in results["results"]],
                total_results=results["total_results"],
                query_metadata=QueryMetadata(**results["query_metadata"]),
            )

        except SemanticQueryError as e:
            error_message = str(e)

            # Determine appropriate HTTP status code based on error type
            if "not found" in error_message.lower():
                status_code = status.HTTP_404_NOT_FOUND
            elif "timed out" in error_message.lower():
                status_code = status.HTTP_408_REQUEST_TIMEOUT
            elif "no activated repositories" in error_message.lower():
                status_code = status.HTTP_400_BAD_REQUEST
            else:
                status_code = status.HTTP_400_BAD_REQUEST

            raise HTTPException(
                status_code=status_code,
                detail=error_message,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal search error: {str(e)}",
            )

    @app.get("/api/repositories/{repo_id}", response_model=RepositoryDetailsV2Response)
    async def get_repository_details_v2(
        repo_id: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get detailed information about a specific repository.

        Returns comprehensive repository information including statistics,
        git info, configuration, and indexing status.

        Args:
            repo_id: Repository identifier
            current_user: Current authenticated user

        Returns:
            Detailed repository information

        Raises:
            HTTPException: 404 if repository not found, 403 if unauthorized, 400 if invalid ID
        """
        # Validate repository ID format
        if not repo_id or not repo_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository ID cannot be empty",
            )

        # Clean and validate repo ID
        cleaned_repo_id = repo_id.strip()

        # Check for invalid characters and patterns
        if (
            " " in cleaned_repo_id
            or "/" in cleaned_repo_id
            or ".." in cleaned_repo_id
            or cleaned_repo_id.startswith(".")
            or len(cleaned_repo_id) > 255
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid repository ID format",
            )

        # Strategy 1: Try to find repository among user's activated repositories
        try:
            activated_repos = activated_repo_manager.list_activated_repositories(
                current_user.username
            )

            # Look for repository by user_alias (matches repo_id)
            for repo in activated_repos:
                if repo["user_alias"] == cleaned_repo_id:
                    # Found activated repository - build response from real data
                    try:
                        repo_path = activated_repo_manager.get_activated_repo_path(
                            current_user.username, cleaned_repo_id
                        )

                        # Get branch information from the activated repo
                        branch_info = activated_repo_manager.list_repository_branches(
                            current_user.username, cleaned_repo_id
                        )

                        # Get basic repository statistics
                        total_files = 0
                        total_size = 0
                        languages = set()

                        if os.path.exists(repo_path):
                            for root, dirs, files in os.walk(repo_path):
                                if ".git" in dirs:
                                    dirs.remove(".git")
                                for file in files:
                                    if not file.startswith("."):
                                        file_path = os.path.join(root, file)
                                        try:
                                            total_size += os.path.getsize(file_path)
                                            total_files += 1
                                            ext = os.path.splitext(file)[1].lower()
                                            lang_map = {
                                                ".py": "python",
                                                ".js": "javascript",
                                                ".ts": "typescript",
                                                ".java": "java",
                                                ".md": "markdown",
                                                ".yml": "yaml",
                                                ".json": "json",
                                            }
                                            if ext in lang_map:
                                                languages.add(lang_map[ext])
                                        except (OSError, IOError):
                                            continue

                        # Build response from activated repository data
                        repository_data = RepositoryDetailsV2Response(
                            id=cleaned_repo_id,
                            name=repo["golden_repo_alias"],
                            path=repo_path,
                            owner_id=current_user.username,
                            created_at=repo["activated_at"],
                            updated_at=repo["last_accessed"],
                            last_sync_at=repo["last_accessed"],
                            status="indexed",
                            indexing_progress=100.0,
                            statistics=RepositoryStatistics(
                                total_files=total_files,
                                indexed_files=total_files,
                                total_size_bytes=total_size,
                                embeddings_count=total_files * 3,
                                languages=list(languages) if languages else ["unknown"],
                            ),
                            git_info=GitInfo(
                                current_branch=branch_info.get(
                                    "current_branch", repo["current_branch"]
                                ),
                                branches=[
                                    b["name"] for b in branch_info.get("branches", [])
                                ]
                                or [repo["current_branch"]],
                                last_commit="unknown",
                                remote_url=None,
                            ),
                            configuration=RepositoryConfiguration(
                                ignore_patterns=["*.pyc", "__pycache__", ".git"],
                                chunk_size=1000,
                                overlap=200,
                                embedding_model="text-embedding-3-small",
                            ),
                            errors=[],
                        )

                        return repository_data

                    except Exception as e:
                        # If we can't get detailed info, provide basic info
                        repository_data = RepositoryDetailsV2Response(
                            id=cleaned_repo_id,
                            name=repo["golden_repo_alias"],
                            path=f"/repos/{current_user.username}/{cleaned_repo_id}",
                            owner_id=current_user.username,
                            created_at=repo["activated_at"],
                            updated_at=repo["last_accessed"],
                            last_sync_at=repo["last_accessed"],
                            status="indexed",
                            indexing_progress=100.0,
                            statistics=RepositoryStatistics(
                                total_files=0,
                                indexed_files=0,
                                total_size_bytes=0,
                                embeddings_count=0,
                                languages=["unknown"],
                            ),
                            git_info=GitInfo(
                                current_branch=repo["current_branch"],
                                branches=[repo["current_branch"]],
                                last_commit="unknown",
                                remote_url=None,
                            ),
                            configuration=RepositoryConfiguration(
                                ignore_patterns=["*.pyc", "__pycache__", ".git"],
                                chunk_size=1000,
                                overlap=200,
                                embedding_model="text-embedding-3-small",
                            ),
                            errors=[
                                f"Could not retrieve detailed information: {str(e)}"
                            ],
                        )

                        return repository_data

        except Exception:
            # Continue to try golden repositories
            pass

        # Strategy 2: Try to find repository among golden repositories
        try:
            # Check if this is a golden repository that the user can access
            golden_repo_details = repository_listing_manager.get_repository_details(
                alias=cleaned_repo_id, username=current_user.username
            )

            # Found golden repository - build response from golden repo data
            try:
                clone_path = golden_repo_details["clone_path"]
                branches = golden_repo_details.get(
                    "branches_list", [golden_repo_details["default_branch"]]
                )

                # Get basic statistics
                total_files = golden_repo_details.get("file_count", 0)
                total_size = golden_repo_details.get("index_size", 0)

                repository_data = RepositoryDetailsV2Response(
                    id=cleaned_repo_id,
                    name=golden_repo_details["alias"],
                    path=clone_path,
                    owner_id="system",
                    created_at=golden_repo_details["created_at"],
                    updated_at=golden_repo_details.get(
                        "last_updated", golden_repo_details["created_at"]
                    ),
                    last_sync_at=golden_repo_details.get("last_updated"),
                    status=(
                        "available"
                        if golden_repo_details["activation_status"] == "available"
                        else "indexed"
                    ),
                    indexing_progress=(
                        100.0
                        if golden_repo_details["activation_status"] == "activated"
                        else 0.0
                    ),
                    statistics=RepositoryStatistics(
                        total_files=total_files,
                        indexed_files=(
                            total_files
                            if golden_repo_details["activation_status"] == "activated"
                            else 0
                        ),
                        total_size_bytes=total_size,
                        embeddings_count=(
                            total_files * 3
                            if golden_repo_details["activation_status"] == "activated"
                            else 0
                        ),
                        languages=["unknown"],
                    ),
                    git_info=GitInfo(
                        current_branch=golden_repo_details["default_branch"],
                        branches=branches,
                        last_commit="unknown",
                        remote_url=golden_repo_details.get("repo_url"),
                    ),
                    configuration=RepositoryConfiguration(
                        ignore_patterns=["*.pyc", "__pycache__", ".git"],
                        chunk_size=1000,
                        overlap=200,
                        embedding_model="text-embedding-3-small",
                    ),
                    errors=[],
                )

                return repository_data

            except Exception as e:
                # Fallback with basic golden repository info
                repository_data = RepositoryDetailsV2Response(
                    id=cleaned_repo_id,
                    name=golden_repo_details["alias"],
                    path=golden_repo_details["clone_path"],
                    owner_id="system",
                    created_at=golden_repo_details["created_at"],
                    updated_at=golden_repo_details.get(
                        "last_updated", golden_repo_details["created_at"]
                    ),
                    last_sync_at=golden_repo_details.get("last_updated"),
                    status="available",
                    indexing_progress=0.0,
                    statistics=RepositoryStatistics(
                        total_files=0,
                        indexed_files=0,
                        total_size_bytes=0,
                        embeddings_count=0,
                        languages=["unknown"],
                    ),
                    git_info=GitInfo(
                        current_branch=golden_repo_details["default_branch"],
                        branches=[golden_repo_details["default_branch"]],
                        last_commit="unknown",
                        remote_url=golden_repo_details.get("repo_url"),
                    ),
                    configuration=RepositoryConfiguration(
                        ignore_patterns=["*.pyc", "__pycache__", ".git"],
                        chunk_size=1000,
                        overlap=200,
                        embedding_model="text-embedding-3-small",
                    ),
                    errors=[f"Could not retrieve detailed information: {str(e)}"],
                )

                return repository_data

        except RepositoryListingError as e:
            if "not found" in str(e):
                # Repository not found in either activated or golden repos
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Repository '{cleaned_repo_id}' not found",
                )
            else:
                # Other repository listing error
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve repository details: {str(e)}",
            )

    @app.get("/api/repositories/{repo_id}/branches", response_model=BranchListResponse)
    async def list_repository_branches_v2(
        repo_id: str,
        include_remote: bool = False,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List all branches in a repository.

        Returns comprehensive branch information including current branch,
        last commit details, and index status for each branch.

        Args:
            repo_id: Repository identifier
            include_remote: Whether to include remote tracking information
            current_user: Current authenticated user

        Returns:
            List of branches with detailed information

        Raises:
            HTTPException: 404 if repository not found, 403 if unauthorized, 400 if invalid ID
        """
        # Validate repository ID format
        if not repo_id or not repo_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository ID cannot be empty",
            )

        cleaned_repo_id = repo_id.strip()

        # Check for invalid characters and patterns (same validation as repository details endpoint)
        if (
            " " in cleaned_repo_id
            or "/" in cleaned_repo_id
            or ".." in cleaned_repo_id
            or cleaned_repo_id.startswith(".")
            or len(cleaned_repo_id) > 255
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid repository ID format",
            )

        try:
            # Check if repository exists and user has access (following existing pattern)
            repo_found = False
            repo_path = None

            # Look for activated repository
            if activated_repo_manager:
                activated_repos = activated_repo_manager.list_activated_repositories(
                    current_user.username
                )
                for repo in activated_repos:
                    if (
                        repo["user_alias"] == cleaned_repo_id
                        or repo["golden_repo_alias"] == cleaned_repo_id
                    ):
                        repo_found = True
                        repo_path = Path(repo["path"])
                        break

            if not repo_found:
                # Also check golden repositories
                try:
                    repo_details = repository_listing_manager.get_repository_details(
                        alias=cleaned_repo_id, username=current_user.username
                    )
                    repo_found = True
                    repo_path = Path(repo_details["path"])
                except RepositoryListingError:
                    pass

            if not repo_found or repo_path is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Repository '{cleaned_repo_id}' not found or not accessible",
                )

            # Initialize git topology service
            git_topology_service = GitTopologyService(repo_path)

            # Use BranchService as context manager for proper resource cleanup
            with BranchService(
                git_topology_service=git_topology_service, index_status_manager=None
            ) as branch_service:
                # Get branch information
                branches = branch_service.list_branches(include_remote=include_remote)

                # Get current branch name
                current_branch_name = (
                    git_topology_service.get_current_branch() or "master"
                )

                return BranchListResponse(
                    branches=branches,
                    total=len(branches),
                    current_branch=current_branch_name,
                )

        except ValueError as e:
            # Handle git repository errors
            if "Not a git repository" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Repository '{cleaned_repo_id}' is not a git repository",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Git operation failed: {str(e)}",
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve branch information: {str(e)}",
            )

    @app.post(
        "/api/repositories/{repo_id}/sync",
        response_model=RepositorySyncJobResponse,
        status_code=202,
    )
    async def sync_repository_v2(
        repo_id: str,
        sync_request: Optional[RepositorySyncRequest] = None,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Trigger manual repository synchronization with background job processing.

        This endpoint allows users to manually trigger repository re-indexing with:
        - Background job processing for async execution
        - Progress tracking with real-time updates
        - Conflict detection for concurrent sync operations
        - Support for incremental sync (changed files only)
        - Force flag to cancel existing sync jobs
        - Git pull integration for remote repositories

        Args:
            repo_id: Repository identifier to sync
            sync_request: Optional sync configuration (uses defaults if not provided)
            current_user: Current authenticated user

        Returns:
            Sync job details with tracking information

        Raises:
            HTTPException: 404 if repository not found, 409 if sync in progress, 500 for errors
        """
        # Validate repository ID format
        if not repo_id or not repo_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository ID cannot be empty",
            )

        cleaned_repo_id = repo_id.strip()

        # Use defaults if no request body provided
        if sync_request is None:
            sync_request = RepositorySyncRequest()

        try:
            # Check if repository exists and user has access
            repo_found = False

            # Look for activated repository
            if activated_repo_manager:
                activated_repos = activated_repo_manager.list_activated_repositories(
                    current_user.username
                )
                for repo in activated_repos:
                    if (
                        repo["user_alias"] == cleaned_repo_id
                        or repo["golden_repo_alias"] == cleaned_repo_id
                    ):
                        repo_found = True
                        break

            if not repo_found:
                # Also check golden repositories
                try:
                    repository_listing_manager.get_repository_details(
                        alias=cleaned_repo_id, username=current_user.username
                    )
                    repo_found = True
                except RepositoryListingError:
                    pass

            if not repo_found:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Repository '{cleaned_repo_id}' not found or not accessible",
                )

            # Check for existing sync jobs if force=False
            if not sync_request.force:
                existing_jobs = background_job_manager.get_jobs_by_operation_and_params(
                    operation_types=["sync_repository"],
                    params_filter={"repo_id": cleaned_repo_id},
                )

                # Check if any job is currently running or pending
                active_jobs = [
                    job
                    for job in existing_jobs
                    if job.get("status") in ["pending", "running"]
                    and job.get("username") == current_user.username
                ]

                if active_jobs:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Repository '{cleaned_repo_id}' sync already in progress. Use force=true to cancel existing sync.",
                    )

            # Cancel existing jobs if force=True
            if sync_request.force:
                existing_jobs = background_job_manager.get_jobs_by_operation_and_params(
                    operation_types=["sync_repository"],
                    params_filter={"repo_id": cleaned_repo_id},
                )

                for job in existing_jobs:
                    if (
                        job.get("status") in ["pending", "running"]
                        and job.get("username") == current_user.username
                    ):
                        cancel_result = background_job_manager.cancel_job(
                            job["job_id"], current_user.username
                        )
                        if cancel_result["success"]:
                            logging.info(
                                f"Cancelled existing sync job {job['job_id']} for repository {cleaned_repo_id}"
                            )

            # Submit background job for repository sync
            sync_options = {
                "incremental": sync_request.incremental,
                "force": sync_request.force,
                "full_reindex": sync_request.full_reindex,
                "pull_remote": sync_request.pull_remote,
                "remote": sync_request.remote,
                "branches": sync_request.branches,
                "ignore_patterns": sync_request.ignore_patterns,
                "progress_webhook": sync_request.progress_webhook,
            }

            # Create wrapper function for background job execution
            def sync_job_wrapper():
                return _execute_repository_sync(
                    repo_id=cleaned_repo_id,
                    username=current_user.username,
                    options=sync_options,
                    progress_callback=None,  # Will be provided by background job manager if needed
                )

            job_id = background_job_manager.submit_job(
                "sync_repository",
                sync_job_wrapper,
                submitter_username=current_user.username,
            )

            # Create response with job details
            created_at = datetime.now(timezone.utc)
            estimated_completion = None  # Could implement estimation based on repo size

            response = RepositorySyncJobResponse(
                job_id=job_id,
                status="queued",
                repository_id=cleaned_repo_id,
                created_at=created_at.isoformat(),
                estimated_completion=estimated_completion,
                progress=SyncProgress(
                    percentage=0, files_processed=0, files_total=0, current_file=None
                ),
                options=SyncJobOptions(
                    force=sync_request.force,
                    full_reindex=sync_request.full_reindex,
                    incremental=sync_request.incremental,
                ),
            )

            logging.info(
                f"Repository sync job {job_id} submitted for '{cleaned_repo_id}' by user '{current_user.username}'"
            )
            return response

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to submit repository sync job: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit sync job: {str(e)}",
            )

    # Repository Statistics Endpoint
    @app.get(
        "/api/repositories/{repo_id}/stats", response_model=RepositoryStatsResponse
    )
    async def get_repository_stats(
        repo_id: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get comprehensive repository statistics.

        Returns detailed statistics including file counts, language distribution,
        storage metrics, activity information, and health assessment.

        Following CLAUDE.md Foundation #1: Uses real file system operations,
        no mocks or simulated data.
        """
        try:
            stats_response = stats_service.get_repository_stats(repo_id)
            return stats_response
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{repo_id}' not found",
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to repository '{repo_id}'",
            )
        except Exception as e:
            logging.error(f"Failed to get repository stats for {repo_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve repository statistics: {str(e)}",
            )

    # File Listing Endpoint
    @app.get("/api/repositories/{repo_id}/files", response_model=FileListResponse)
    async def list_repository_files(
        repo_id: str,
        page: int = 1,
        limit: int = 50,
        path_pattern: Optional[str] = None,
        language: Optional[str] = None,
        sort_by: str = "path",
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List files in repository with pagination and filtering.

        Supports filtering by path pattern, programming language, and sorting.
        Uses real file system operations following CLAUDE.md Foundation #1.
        """
        # Validate query parameters
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Page must be >= 1",
            )
        if limit < 1 or limit > 500:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Limit must be between 1 and 500",
            )

        valid_sort_fields = {"path", "size", "modified_at"}
        if sort_by not in valid_sort_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort field. Must be one of: {', '.join(valid_sort_fields)}",
            )

        try:
            query_params = FileListQueryParams(
                page=page,
                limit=limit,
                path_pattern=path_pattern,
                language=language,
                sort_by=sort_by,
            )

            file_list = file_service.list_files(repo_id, query_params)
            return file_list

        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{repo_id}' not found",
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to repository '{repo_id}'",
            )
        except Exception as e:
            logging.error(f"Failed to list files for repository {repo_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list repository files: {str(e)}",
            )

    # Semantic Search Endpoint
    @app.post(
        "/api/repositories/{repo_id}/search", response_model=SemanticSearchResponse
    )
    async def search_repository(
        repo_id: str,
        search_request: SemanticSearchRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Perform semantic search in repository.

        Executes semantic search using real vector embeddings and Qdrant
        following CLAUDE.md Foundation #1: No mocks.
        """
        try:
            search_response = search_service.search_repository(repo_id, search_request)
            return search_response

        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{repo_id}' not found",
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to repository '{repo_id}'",
            )
        except Exception as e:
            logging.error(f"Failed to search repository {repo_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search operation failed: {str(e)}",
            )

    # Health Check Endpoint
    @app.get("/api/system/health", response_model=HealthCheckResponse)
    async def get_system_health(
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get comprehensive system health status.

        Monitors real system resources, database connectivity, and service health.
        Following CLAUDE.md Foundation #1: Uses real system checks, no mocks.

        SECURITY: Requires authentication to prevent information disclosure.
        """
        try:
            health_response = health_service.get_system_health()
            return health_response

        except Exception as e:
            logging.error(f"Health check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Health check failed: {str(e)}",
            )

    return app


# Create app instance
app = create_app()
