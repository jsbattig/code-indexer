"""
FastAPI application for CIDX Server.

Multi-user semantic code search server with JWT authentication and role-based access control.
"""

from fastapi import FastAPI, HTTPException, status, Depends, Response, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Dict, Any, Optional, List, Callable, Literal
import os
import json
from pathlib import Path
import psutil
import logging
import requests  # type: ignore
from datetime import datetime, timezone

# Initialize logger for server module
logger = logging.getLogger(__name__)

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
from .auth.oauth.routes import router as oauth_router
from .mcp.protocol import mcp_router
from .models.branch_models import BranchListResponse
from .models.activated_repository import ActivatedRepository
from .services.branch_service import BranchService
from code_indexer.services.git_topology_service import GitTopologyService
from .validators.composite_repo_validator import CompositeRepoValidator
from .models.api_models import (
    RepositoryStatsResponse,
    FileListQueryParams,
    SemanticSearchRequest,
    SemanticSearchResponse,
    HealthCheckResponse,
    RepositoryStatusSummary,
    ActivatedRepositorySummary,
    AvailableRepositorySummary,
    RecentActivity,
    TemporalIndexOptions,
)
from .models.repository_discovery import (
    RepositoryDiscoveryResponse,
)
from .services.repository_discovery_service import RepositoryDiscoveryError
from .services.stats_service import stats_service
from .services.file_service import file_service
from .services.search_service import search_service
from .services.health_service import health_service
from .managers.composite_file_listing import _list_composite_files


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
    description: Optional[str] = Field(
        default=None, max_length=500, description="Optional repository description"
    )
    enable_temporal: bool = False
    temporal_options: Optional["TemporalIndexOptions"] = None

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

    golden_repo_alias: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Golden repository alias to activate (single repo)",
    )
    golden_repo_aliases: Optional[List[str]] = Field(
        None,
        description="Golden repository aliases for composite activation (multi-repo)",
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

    @model_validator(mode="after")
    def validate_repo_parameters(self) -> "ActivateRepositoryRequest":
        """Validate mutual exclusivity and requirements for repository parameters."""
        golden_alias = self.golden_repo_alias
        golden_aliases = self.golden_repo_aliases

        # Check mutual exclusivity
        if golden_alias and golden_aliases:
            raise ValueError(
                "Cannot specify both golden_repo_alias and golden_repo_aliases"
            )

        # Validate composite repository requirements BEFORE checking if at least one is provided
        # This ensures empty lists get the correct error message
        if golden_aliases is not None:
            if len(golden_aliases) < 2:
                raise ValueError(
                    "Composite activation requires at least 2 repositories"
                )

            # Validate each alias in the list
            for alias in golden_aliases:
                if not alias or not alias.strip():
                    raise ValueError(
                        "Golden repo aliases cannot contain empty or whitespace-only strings"
                    )

        # Check that at least one is provided (after composite validation)
        if not golden_alias and not golden_aliases:
            raise ValueError(
                "Must specify either golden_repo_alias or golden_repo_aliases"
            )

        return self

    @field_validator("golden_repo_alias")
    @classmethod
    def validate_golden_repo_alias(cls, v: Optional[str]) -> Optional[str]:
        """Validate golden repo alias is not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError(
                "Golden repo alias cannot be empty or contain only whitespace"
            )
        return v.strip() if v else None

    @field_validator("user_alias")
    @classmethod
    def validate_user_alias(cls, v: Optional[str]) -> Optional[str]:
        """Validate user alias if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("User alias cannot be empty or contain only whitespace")
        return v.strip() if v else None


class ActivatedRepositoryInfo(BaseModel):
    """
    Model for activated repository information.

    Supports both single and composite repositories:
    - Single repos: Have golden_repo_alias and current_branch
    - Composite repos: Have golden_repo_aliases and discovered_repos instead
    """

    user_alias: str
    golden_repo_alias: Optional[str] = None  # Optional for composite repos
    current_branch: Optional[str] = None  # Optional for composite repos
    activated_at: str
    last_accessed: str


class SwitchBranchRequest(BaseModel):
    """Request model for switching repository branch."""

    branch_name: str = Field(
        ..., min_length=1, max_length=255, description="Branch name to switch to"
    )
    create: bool = Field(default=False, description="Create branch if it doesn't exist")

    @field_validator("branch_name")
    @classmethod
    def validate_branch_name(cls, v: str) -> str:
        """Validate branch name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Branch name cannot be empty or contain only whitespace")
        return v.strip()


class SemanticQueryRequest(BaseModel):
    """Request model for semantic query operations with FTS support."""

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

    # Search mode selection (Story 5)
    search_mode: Literal["semantic", "fts", "hybrid"] = Field(
        default="semantic",
        description="Search mode: 'semantic' (AI-based, default), 'fts' (full-text), 'hybrid' (both in parallel)",
    )

    # FTS-specific parameters (Story 5)
    case_sensitive: bool = Field(
        default=False, description="FTS only: Enable case-sensitive matching"
    )
    fuzzy: bool = Field(
        default=False, description="FTS only: Enable fuzzy matching (edit distance 1)"
    )
    edit_distance: int = Field(
        default=0,
        ge=0,
        le=3,
        description="FTS only: Fuzzy match tolerance (0=exact, 1-3=typo tolerance)",
    )
    snippet_lines: int = Field(
        default=5,
        ge=0,
        le=50,
        description="FTS only: Context lines around matches (0=list only, default=5)",
    )

    # Common filtering parameters
    language: Optional[str] = Field(
        None,
        description="Filter by programming language (e.g., 'python', 'javascript')",
    )
    path_filter: Optional[str] = Field(
        None, description="Filter by path pattern (e.g., '*/tests/*', '*.py')"
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


# Import QueryResultItem from api_models (re-exported for backward compatibility)
from .models.api_models import QueryResultItem


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


class FTSResultItem(BaseModel):
    """Individual FTS (full-text search) result item (Story 5)."""

    path: str = Field(description="File path relative to repository root")
    line_start: int = Field(description="Starting line number of match")
    line_end: int = Field(description="Ending line number of match")
    snippet: str = Field(description="Code snippet with context around match")
    language: str = Field(description="Programming language detected")
    repository_alias: str = Field(description="Repository alias")


class UnifiedSearchMetadata(BaseModel):
    """Unified metadata for all search modes (Story 5)."""

    query_text: str
    search_mode_requested: str = Field(description="Search mode requested by user")
    search_mode_actual: str = Field(description="Actual mode used (after degradation)")
    execution_time_ms: int
    fts_available: bool = Field(description="Whether FTS index is available")
    semantic_available: bool = Field(description="Whether semantic index is available")
    repositories_searched: int = Field(default=0)


class UnifiedSearchResponse(BaseModel):
    """Unified response for all search modes: semantic, FTS, hybrid (Story 5)."""

    search_mode: str = Field(description="Search mode used")
    query: str = Field(description="Query text")
    fts_results: List[FTSResultItem] = Field(
        default_factory=list, description="FTS results (if FTS or hybrid mode)"
    )
    semantic_results: List[QueryResultItem] = Field(
        default_factory=list,
        description="Semantic results (if semantic or hybrid mode)",
    )
    metadata: UnifiedSearchMetadata


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
    enable_temporal: bool = False
    temporal_status: Optional[Dict[str, Any]] = None


class RepositoryListResponse(BaseModel):
    """Response model for repository listing endpoints."""

    repositories: List[ActivatedRepositoryInfo]
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


class ComponentRepoInfo(BaseModel):
    """Information about each component repository in a composite repository."""

    name: str
    path: str
    has_index: bool
    collection_exists: bool
    indexed_files: int
    last_indexed: Optional[datetime] = None
    size_mb: float


class CompositeRepositoryDetails(BaseModel):
    """Details for a composite repository with aggregated component information."""

    user_alias: str
    is_composite: bool = True
    activated_at: datetime
    last_accessed: datetime
    component_repositories: List[ComponentRepoInfo]
    total_files: int
    total_size_mb: float

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


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


class GeneralRepositorySyncRequest(BaseModel):
    """Request model for general repository synchronization via repository alias."""

    repository_alias: str = Field(description="Repository alias to synchronize")
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
    ignore_patterns: Optional[List[str]] = Field(
        default=None, description="Additional ignore patterns for this sync"
    )
    progress_webhook: Optional[str] = Field(
        default=None, description="Webhook URL for progress updates"
    )


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


# Helper functions for composite repository details (Story 3.2)
def _analyze_component_repo(repo_path: Path, name: str) -> ComponentRepoInfo:
    """
    Analyze a single component repository.

    Args:
        repo_path: Path to the component repository
        name: Name of the component repository

    Returns:
        ComponentRepoInfo with repository analysis
    """
    # Check for index
    index_dir = repo_path / ".code-indexer"
    has_index = index_dir.exists()

    # Get file count from metadata
    file_count = 0
    last_indexed = None
    if has_index:
        metadata_file = index_dir / "metadata.json"
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text())
                file_count = metadata.get("indexed_files", 0)
                # Try to get last_indexed timestamp if available
                if "last_indexed" in metadata:
                    try:
                        last_indexed = datetime.fromisoformat(metadata["last_indexed"])
                    except (ValueError, TypeError):
                        pass
            except (json.JSONDecodeError, IOError):
                # If metadata is corrupted, treat as 0 files
                file_count = 0

    # Calculate repo size
    total_size = 0
    for item in repo_path.rglob("*"):
        if item.is_file():
            try:
                total_size += item.stat().st_size
            except (OSError, IOError):
                # Skip files we can't stat
                continue

    return ComponentRepoInfo(
        name=name,
        path=str(repo_path),
        has_index=has_index,
        collection_exists=has_index,
        indexed_files=file_count,
        last_indexed=last_indexed,
        size_mb=total_size / (1024 * 1024),
    )


def _get_composite_details(repo: ActivatedRepository) -> CompositeRepositoryDetails:
    """
    Aggregate details from all component repositories.

    Args:
        repo: ActivatedRepository instance (must be composite)

    Returns:
        CompositeRepositoryDetails with aggregated information
    """
    from code_indexer.proxy.config_manager import ProxyConfigManager

    component_info = []
    total_files = 0
    total_size = 0.0

    # Use ProxyConfigManager to get component repos
    proxy_config = ProxyConfigManager(repo.path)

    try:
        discovered_repos = proxy_config.get_repositories()
    except Exception:
        # If we can't load proxy config, use discovered_repos from metadata
        discovered_repos = repo.discovered_repos

    for repo_name in discovered_repos:
        subrepo_path = repo.path / repo_name
        if subrepo_path.exists():
            info = _analyze_component_repo(subrepo_path, repo_name)
            component_info.append(info)
            total_files += info.indexed_files
            total_size += info.size_mb

    return CompositeRepositoryDetails(
        user_alias=repo.user_alias,
        is_composite=True,
        activated_at=repo.activated_at,
        last_accessed=repo.last_accessed,
        component_repositories=component_info,
        total_files=total_files,
        total_size_mb=total_size,
    )


# Token blacklist for logout functionality (Story #491) - MODULE LEVEL
token_blacklist: set[str] = set()

def blacklist_token(jti: str) -> None:
    """Add token JTI to blacklist."""
    token_blacklist.add(jti)

def is_token_blacklisted(jti: str) -> bool:
    """Check if token JTI is blacklisted."""
    return jti in token_blacklist


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    global jwt_manager, user_manager, refresh_token_manager, golden_repo_manager, background_job_manager, activated_repo_manager, repository_listing_manager, semantic_query_manager, _server_start_time

    # Initialize exception logger EARLY for server mode
    from ..utils.exception_logger import ExceptionLogger

    exception_logger = ExceptionLogger.initialize(
        project_root=Path.home(), mode="server"
    )
    exception_logger.install_thread_exception_hook()
    logger.info("ExceptionLogger initialized for server mode")

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

    # Add CORS middleware for Claude.ai OAuth compatibility
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://claude.ai",
            "https://claude.com",
            "https://www.anthropic.com",
            "https://api.anthropic.com",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
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

    # Initialize UserManager with server data directory support
    server_data_dir = os.environ.get(
        "CIDX_SERVER_DATA_DIR", str(Path.home() / ".cidx-server")
    )
    Path(server_data_dir).mkdir(parents=True, exist_ok=True)
    users_file_path = str(Path(server_data_dir) / "users.json")
    user_manager = UserManager(users_file_path=users_file_path)
    refresh_token_manager = RefreshTokenManager(jwt_manager=jwt_manager)

    # Initialize OAuth manager
    oauth_db_path = str(Path(server_data_dir) / "oauth.db")
    from .auth.oauth.oauth_manager import OAuthManager
    oauth_manager = OAuthManager(
        db_path=oauth_db_path,
        issuer=None,
        user_manager=user_manager
    )

    golden_repo_manager = GoldenRepoManager()
    background_job_manager = BackgroundJobManager()
    # Inject BackgroundJobManager into GoldenRepoManager for async operations
    golden_repo_manager.background_job_manager = background_job_manager
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
    dependencies.oauth_manager = oauth_manager

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
        # Extract client information for audit logging
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        try:
            # First validate the refresh token to get user information
            # Validate and rotate refresh token
            result = refresh_token_manager.validate_and_rotate_refresh_token(
                refresh_token=refresh_request.refresh_token,
                client_ip=client_ip,
                user_manager=user_manager,
            )

            if not result["valid"]:
                # Get username from result for logging
                username = result.get("user_data", {}).get("username", "unknown")

                # Check rate limiting for failed attempts
                rate_limit_error = refresh_token_rate_limiter.check_rate_limit(username)
                if rate_limit_error:
                    # Get current attempt count for logging
                    attempt_count = refresh_token_rate_limiter.get_attempt_count(
                        username
                    )

                    # Log rate limit hit
                    password_audit_logger.log_rate_limit_triggered(
                        username=username,
                        ip_address=client_ip,
                        attempt_count=attempt_count,
                        user_agent=user_agent,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=rate_limit_error,
                    )

                # Record failed attempt for rate limiting
                should_lock = refresh_token_rate_limiter.record_failed_attempt(username)
                if should_lock:
                    # Get updated attempt count for logging (after recording failed attempt)
                    attempt_count = refresh_token_rate_limiter.get_attempt_count(
                        username
                    )

                    # Log lockout triggered
                    password_audit_logger.log_rate_limit_triggered(
                        username=username,
                        ip_address=client_ip,
                        attempt_count=attempt_count,
                        user_agent=user_agent,
                    )

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

            # Success - get username from successful result
            username = result["user_data"]["username"]

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
                user=result["user_data"],
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
            # Log unexpected errors (username might not be defined if error occurred early)
            username_for_log = locals().get("username", "unknown")
            password_audit_logger.log_token_refresh_failure(
                username=username_for_log,
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
        refresh_request: RefreshTokenRequest,
    ):
        """
        Refresh JWT token using refresh token.

        Args:
            refresh_request: Request containing refresh token

        Returns:
            New JWT token with extended expiration and user information

        Raises:
            HTTPException: If token refresh fails
        """
        try:
            # Use the refresh token manager to validate and create new tokens
            result = refresh_token_manager.validate_and_rotate_refresh_token(
                refresh_token=refresh_request.refresh_token, client_ip="unknown"
            )

            return LoginResponse(
                access_token=result["new_access_token"],
                token_type="bearer",
                user=result["user_data"],
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token refresh failed: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Protected endpoints (require authentication)
    @app.get("/api/repos", response_model=RepositoryListResponse)
    async def list_repositories(
        filter: Optional[str] = None,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List activated repositories for current user.

        Args:
            filter: Optional filter pattern for repository aliases
            current_user: Current authenticated user

        Returns:
            List of activated repositories for the user
        """
        try:
            repos = activated_repo_manager.list_activated_repositories(
                current_user.username
            )

            # Apply filter if provided
            if filter:
                filtered_repos = []
                for repo in repos:
                    if filter.lower() in repo["user_alias"].lower():
                        filtered_repos.append(repo)
                repos = filtered_repos

            # Return wrapped in RepositoryListResponse for consistency
            return RepositoryListResponse(
                repositories=[ActivatedRepositoryInfo(**repo) for repo in repos],
                total=len(repos),
            )

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

                        # Check if this attempt triggered rate limiting
                        if should_lockout:
                            # Log rate limit trigger event
                            password_audit_logger.log_rate_limit_triggered(
                                username=username,
                                ip_address=client_ip,
                                attempt_count=password_change_rate_limiter.get_attempt_count(
                                    username
                                ),
                                user_agent=user_agent,
                            )

                            raise HTTPException(
                                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many failed attempts. Please try again in 15 minutes.",
                            )
                        else:
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
            func_kwargs = {
                "repo_url": repo_data.repo_url,
                "alias": repo_data.alias,
                "default_branch": repo_data.default_branch,
                "description": repo_data.description,
                "enable_temporal": repo_data.enable_temporal,
            }

            # Add temporal_options if provided
            if repo_data.temporal_options:
                func_kwargs["temporal_options"] = (
                    repo_data.temporal_options.model_dump()
                )

            job_id = background_job_manager.submit_job(
                "add_golden_repo",
                golden_repo_manager.add_golden_repo,  # type: ignore[arg-type]
                submitter_username=current_user.username,
                **func_kwargs,  # type: ignore[arg-type]
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

    @app.get("/api/admin/jobs/stats")
    async def admin_jobs_stats(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user)
    ):
        """Get job statistics for admin dashboard."""
        from datetime import datetime, timezone

        # Get all jobs from the background job manager
        all_jobs = list(background_job_manager.jobs.values())

        # Filter by date range if provided
        filtered_jobs = all_jobs
        if start_date or end_date:
            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None

            filtered_jobs = [
                job for job in all_jobs
                if (not start_dt or job.created_at >= start_dt) and
                   (not end_dt or job.created_at <= end_dt)
            ]

        # Calculate statistics
        total_jobs = len(filtered_jobs)

        # Count by status
        by_status = {}
        for job in filtered_jobs:
            status = job.status.value
            by_status[status] = by_status.get(status, 0) + 1

        # Count by type
        by_type = {}
        for job in filtered_jobs:
            job_type = job.operation_type
            by_type[job_type] = by_type.get(job_type, 0) + 1

        # Calculate success rate
        completed_jobs = by_status.get("completed", 0)
        failed_jobs = by_status.get("failed", 0)
        total_finished = completed_jobs + failed_jobs
        success_rate = (completed_jobs / total_finished * 100.0) if total_finished > 0 else 0.0

        # Calculate average duration for completed jobs
        durations = []
        for job in filtered_jobs:
            if job.completed_at and job.started_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                durations.append(duration)

        average_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_jobs": total_jobs,
            "by_status": by_status,
            "by_type": by_type,
            "success_rate": success_rate,
            "average_duration": average_duration,
        }

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
                    detail=str(e),  # Preserve original error message
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

        Supports both single repository and composite repository activation.

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
                golden_repo_aliases=request.golden_repo_aliases,
                branch_name=request.branch_name,
                user_alias=request.user_alias,
            )

            # Determine appropriate user_alias for response message
            if request.golden_repo_aliases:
                # Composite activation
                user_alias_str: str = request.user_alias or "composite_repository"
                repo_count = len(request.golden_repo_aliases)
                return JobResponse(
                    job_id=job_id,
                    message=f"Composite repository '{user_alias_str}' activation started for user '{current_user.username}' ({repo_count} repositories)",
                )
            else:
                # Single repository activation
                user_alias_str = (
                    request.user_alias or request.golden_repo_alias or "repository"
                )
                return JobResponse(
                    job_id=job_id,
                    message=f"Repository '{user_alias_str}' activation started for user '{current_user.username}'",
                )

        except ActivatedRepoError as e:
            error_msg = str(e)

            if "not found" in error_msg:
                # Provide repository suggestions
                available_repos = golden_repo_manager.list_golden_repos()
                suggestions = [repo.get("alias", "") for repo in available_repos[:5]]

                detail: Dict[str, Any] = {
                    "error": error_msg,
                    "available_repositories": suggestions,
                    "guidance": "Use 'GET /api/repos/golden' to see all available repositories",
                }

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=detail,
                )
            elif "already activated" in error_msg:
                # Provide conflict resolution guidance
                user_alias_conflict: str = (
                    request.user_alias or request.golden_repo_alias or "repository"
                )
                conflict_detail: Dict[str, Any] = {
                    "error": error_msg,
                    "conflict_resolution": {
                        "options": [
                            {
                                "action": "switch_branch",
                                "description": f"Switch to different branch in existing repository '{user_alias_conflict}'",
                                "endpoint": f"PUT /api/repos/{user_alias_conflict}/branch",
                            },
                            {
                                "action": "use_different_alias",
                                "description": "Choose a different user_alias for this activation",
                                "example": f"{user_alias_conflict}_v2",
                            },
                            {
                                "action": "deactivate_first",
                                "description": f"Deactivate existing repository '{user_alias_conflict}' before reactivating",
                                "endpoint": f"DELETE /api/repos/{user_alias_conflict}",
                            },
                        ]
                    },
                    "guidance": "Repository conflicts occur when trying to activate a repository with an alias that's already in use",
                }

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=conflict_detail,
                )
            else:
                # Generic bad request with troubleshooting guidance
                troubleshoot_detail: Dict[str, Any] = {
                    "error": error_msg,
                    "troubleshooting": {
                        "common_causes": [
                            "Invalid branch name specified",
                            "Insufficient permissions",
                            "Repository corruption in golden repository",
                        ],
                        "recommended_actions": [
                            "Verify the golden repository exists: GET /api/repos/golden",
                            "Check available branches: GET /api/repos/golden/{alias}/branches",
                            "Ensure you have power user privileges",
                        ],
                    },
                }

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=troubleshoot_detail,
                )
        except Exception as e:
            # Log the error for administrative review
            logging.error(
                f"Repository activation failed for user '{current_user.username}': {str(e)}",
                extra={
                    "username": current_user.username,
                    "golden_repo_alias": request.golden_repo_alias,
                    "branch_name": request.branch_name,
                    "user_alias": request.user_alias,
                    "error_type": type(e).__name__,
                },
            )

            detail = {
                "error": f"Internal error during repository activation: {str(e)}",
                "administrative_guidance": "This error has been logged for administrator review",
                "user_actions": [
                    "Try again in a few minutes",
                    "Contact administrator if problem persists",
                    "Check system status at /api/health",
                ],
            }

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail,
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

    @app.get("/api/repos/activation/{job_id}/progress")
    async def get_activation_progress(
        job_id: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get real-time activation progress for monitoring.

        Args:
            job_id: Job ID returned from activation request
            current_user: Current authenticated user

        Returns:
            Real-time progress information including step details

        Raises:
            HTTPException: If job not found or access denied
        """
        try:
            # Get job status from background job manager
            job_status = activated_repo_manager.background_job_manager.get_job_status(
                job_id, current_user.username
            )

            if not job_status:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": f"Activation job '{job_id}' not found",
                        "guidance": "Job may have expired or you may not have permission to view it",
                        "troubleshooting": [
                            "Verify the job ID is correct",
                            "Check if the job belongs to your user account",
                            "Jobs older than 24 hours may be automatically cleaned up",
                        ],
                    },
                )

            # Enhance job status with activation-specific details
            enhanced_status = {
                "job_id": job_status["job_id"],
                "status": job_status["status"],
                "progress_percentage": job_status["progress"],
                "created_at": job_status["created_at"],
                "started_at": job_status["started_at"],
                "completed_at": job_status["completed_at"],
                "operation_type": job_status["operation_type"],
                "error": job_status.get("error"),
                "result": job_status.get("result"),
            }

            # Add progress interpretation for activation jobs
            if job_status["operation_type"] == "activate_repository":
                progress = job_status["progress"]
                if progress == 0 and job_status["status"] == "pending":
                    enhanced_status["current_step"] = "Queued for processing"
                    enhanced_status["next_step"] = "Validation and setup"
                elif progress <= 20:
                    enhanced_status["current_step"] = "Validating golden repository"
                    enhanced_status["next_step"] = "Creating user directory structure"
                elif progress <= 40:
                    enhanced_status["current_step"] = "Setting up workspace"
                    enhanced_status["next_step"] = "Cloning repository"
                elif progress <= 60:
                    enhanced_status["current_step"] = "Cloning repository data"
                    enhanced_status["next_step"] = "Configuring branches"
                elif progress <= 80:
                    enhanced_status["current_step"] = "Configuring repository branches"
                    enhanced_status["next_step"] = "Creating metadata"
                elif progress <= 95:
                    enhanced_status["current_step"] = "Finalizing setup"
                    enhanced_status["next_step"] = "Completing activation"
                elif progress == 100:
                    enhanced_status["current_step"] = (
                        "Activation completed successfully"
                    )
                    enhanced_status["next_step"] = "Repository ready for use"
                else:
                    enhanced_status["current_step"] = "Processing"
                    enhanced_status["next_step"] = "Please wait"

                # Add time estimation
                if job_status["started_at"] and job_status["status"] == "running":
                    from datetime import datetime, timezone

                    started = datetime.fromisoformat(
                        job_status["started_at"].replace("Z", "+00:00")
                    )
                    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

                    # Estimate total time based on progress (typical activation: 30-120 seconds)
                    if progress > 0:
                        estimated_total = (elapsed / progress) * 100
                        estimated_remaining = max(0, estimated_total - elapsed)
                        enhanced_status["time_estimates"] = {
                            "elapsed_seconds": round(elapsed),
                            "estimated_remaining_seconds": round(estimated_remaining),
                            "estimated_total_seconds": round(estimated_total),
                        }

            return enhanced_status

        except HTTPException:
            raise
        except Exception as e:
            logging.error(
                f"Failed to get activation progress for job '{job_id}': {str(e)}",
                extra={
                    "job_id": job_id,
                    "username": current_user.username,
                    "error_type": type(e).__name__,
                },
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": f"Failed to retrieve activation progress: {str(e)}",
                    "guidance": "This error has been logged for administrator review",
                },
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
            # Get repository path and validate it's not a composite repository
            repo_path = activated_repo_manager.get_activated_repo_path(
                username=current_user.username,
                user_alias=user_alias,
            )
            CompositeRepoValidator.check_operation(Path(repo_path), "branch_switch")

            result = activated_repo_manager.switch_branch(
                username=current_user.username,
                user_alias=user_alias,
                branch_name=request.branch_name,
                create=request.create,
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

    # Repository Discovery Endpoint
    @app.get("/api/repos/discover", response_model=RepositoryDiscoveryResponse)
    async def discover_repositories(
        source: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Discover matching repositories by git origin URL or source pattern.

        Finds matching golden and activated repositories based on the provided
        source pattern, returning repository candidates for intelligent client linking.

        Args:
            source: Git repository URL or source pattern to search for
            current_user: Current authenticated user

        Returns:
            Repository discovery response with matching repositories

        Raises:
            HTTPException: 400 if invalid URL, 401 if unauthorized, 500 if server error
        """
        try:
            # Initialize repository discovery service
            from .services.repository_discovery_service import (
                RepositoryDiscoveryService,
            )

            discovery_service = RepositoryDiscoveryService(
                golden_repo_manager=golden_repo_manager,
                activated_repo_manager=activated_repo_manager,
            )

            # Discover matching repositories
            discovery_response = await discovery_service.discover_repositories(
                repo_url=source,
                user=current_user,
            )

            logging.info(
                f"Repository discovery for {source} by {current_user.username}: "
                f"{discovery_response.total_matches} matches found"
            )

            return discovery_response

        except RepositoryDiscoveryError as e:
            # Handle known discovery errors with appropriate status codes
            if "Invalid git URL" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid git URL format: {str(e)}",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Repository discovery failed: {str(e)}",
                )

        except Exception as e:
            logging.error(f"Unexpected error in repository discovery: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Repository discovery operation failed: {str(e)}",
            )

    # NOTE: Moved generic {user_alias} route after specific routes to avoid path conflicts

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
            # Get repository path and validate it's not a composite repository
            repo_path = activated_repo_manager.get_activated_repo_path(
                username=current_user.username,
                user_alias=user_alias,
            )
            CompositeRepoValidator.check_operation(Path(repo_path), "sync")

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

    @app.post(
        "/api/repos/sync", response_model=RepositorySyncJobResponse, status_code=202
    )
    async def sync_repository_general(
        sync_request: GeneralRepositorySyncRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Trigger manual repository synchronization with repository alias in request body.

        This endpoint provides a general sync API that accepts the repository alias
        in the request body instead of the URL path, matching the format expected
        by manual testing and external API consumers.

        This endpoint supports the same functionality as POST /api/repositories/{repo_id}/sync
        but with a more convenient request format for general usage.

        Args:
            sync_request: Repository sync configuration including repository alias
            current_user: Current authenticated user

        Returns:
            Sync job details with tracking information

        Raises:
            HTTPException: 404 if repository not found, 409 if sync in progress, 500 for errors
        """
        try:
            # Extract repository alias from request body
            input_alias = sync_request.repository_alias

            # Clean and validate repository alias
            cleaned_input_alias = input_alias.strip()
            if not cleaned_input_alias:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Repository alias cannot be empty",
                )

            def resolve_repository_alias_to_id(alias: str, username: str) -> str:
                """
                Resolve repository alias to actual repository ID.

                Args:
                    alias: Input alias from user request
                    username: Current user's username

                Returns:
                    Resolved repository ID

                Raises:
                    HTTPException: If alias cannot be resolved or access denied
                """
                try:
                    activated_repos = (
                        activated_repo_manager.list_activated_repositories(username)
                    )

                    # Strategy 1: Look for exact user_alias match
                    for repo in activated_repos:
                        if repo["user_alias"] == alias:
                            # Return the actual repository ID if available, otherwise use user_alias
                            return str(repo.get("actual_repo_id", repo["user_alias"]))

                    # Strategy 2: Look for golden_repo_alias match
                    for repo in activated_repos:
                        if repo.get("golden_repo_alias") == alias:
                            return str(repo.get("actual_repo_id", repo["user_alias"]))

                    # Strategy 3: Check if alias is already a repository ID
                    for repo in activated_repos:
                        if repo.get("actual_repo_id") == alias:
                            return alias  # Already resolved ID

                    # Strategy 4: Fall back to repository listing manager for discovery
                    try:
                        repository_listing_manager.get_repository_details(
                            alias, username
                        )
                        # If this succeeds, the alias exists but might not be activated
                        # Return the alias as the ID for now
                        return alias
                    except Exception:
                        pass

                    # If all strategies fail, raise not found error
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=(
                            f"Repository alias '{alias}' could not be resolved to a valid "
                            f"repository ID for user '{username}'"
                        ),
                    )

                except HTTPException:
                    raise  # Re-raise HTTP exceptions
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error resolving repository alias '{alias}': {str(e)}",
                    )

            # Resolve the alias to actual repository ID
            resolved_repo_id = resolve_repository_alias_to_id(
                cleaned_input_alias, current_user.username
            )

            # Use resolved repository ID for all subsequent operations
            cleaned_repo_id = resolved_repo_id

            # Check for existing sync jobs if force=False
            if not sync_request.force:
                existing_jobs = background_job_manager.get_jobs_by_operation_and_params(
                    operation_types=["sync_repository"],
                    params_filter={"repo_id": cleaned_repo_id},
                )

                if existing_jobs:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Repository '{cleaned_repo_id}' sync already in progress. Use force=true to cancel existing sync.",
                    )

            # Cancel existing sync jobs if force=True
            if sync_request.force:
                existing_jobs = background_job_manager.get_jobs_by_operation_and_params(
                    operation_types=["sync_repository"],
                    params_filter={"repo_id": cleaned_repo_id},
                )

                critical_cancellation_failures = []
                minor_cancellation_failures = []

                for job in existing_jobs:
                    try:
                        background_job_manager.cancel_job(
                            job["job_id"], current_user.username
                        )
                        logging.info(
                            f"Cancelled existing sync job {job['job_id']} for repository {cleaned_repo_id}"
                        )
                    except Exception as e:
                        error_message = str(e).lower()
                        job_id = job["job_id"]

                        # Categorize failure types
                        if any(
                            critical_keyword in error_message
                            for critical_keyword in [
                                "locked",
                                "permission denied",
                                "access denied",
                                "critical",
                                "in progress",
                            ]
                        ):
                            critical_cancellation_failures.append(
                                {"job_id": job_id, "error": str(e), "type": "critical"}
                            )
                            logging.error(
                                f"Critical cancellation failure for job {job_id}: {str(e)}"
                            )
                        else:
                            minor_cancellation_failures.append(
                                {"job_id": job_id, "error": str(e), "type": "minor"}
                            )
                            logging.warning(
                                f"Minor cancellation failure for job {job_id}: {str(e)}"
                            )

                # If there are critical cancellation failures, abort the new sync
                if critical_cancellation_failures:
                    failed_jobs = [
                        f"job {f['job_id']}: {f['error']}"
                        for f in critical_cancellation_failures
                    ]
                    error_details = "; ".join(failed_jobs)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Cannot proceed with sync - critical cancellation failures: "
                            f"{error_details}. Some existing jobs could not be safely cancelled."
                        ),
                    )

                # Log minor failures but proceed with sync
                if minor_cancellation_failures:
                    failed_jobs = [
                        f"job {f['job_id']}" for f in minor_cancellation_failures
                    ]
                    logging.info(
                        f"Proceeding with sync despite minor cancellation failures: "
                        f"{', '.join(failed_jobs)}"
                    )

            # Submit background job for repository sync
            sync_options = {
                "incremental": sync_request.incremental,
                "force": sync_request.force,
                "full_reindex": sync_request.full_reindex,
                "pull_remote": sync_request.pull_remote,
                "remote": sync_request.remote,
                "ignore_patterns": sync_request.ignore_patterns,
                "progress_webhook": sync_request.progress_webhook,
            }

            def create_webhook_callback(
                webhook_url: Optional[str],
            ) -> Optional[Callable[[int], None]]:
                """Create a webhook callback function if webhook URL is provided."""
                if not webhook_url:
                    return None

                def webhook_callback(progress: int) -> None:
                    """Send progress updates to webhook URL."""
                    try:
                        payload = {
                            "repository_id": cleaned_repo_id,
                            "progress": progress,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "username": current_user.username,
                        }
                        response = requests.post(
                            webhook_url,
                            json=payload,
                            timeout=5,  # Don't wait too long for webhook responses
                            headers={"Content-Type": "application/json"},
                        )
                        # Log webhook failures but don't interrupt sync
                        if not response.ok:
                            logging.warning(
                                f"Webhook {webhook_url} returned {response.status_code}"
                            )
                    except Exception as e:
                        logging.warning(
                            f"Failed to send webhook to {webhook_url}: {str(e)}"
                        )

                return webhook_callback

            def sync_job_wrapper():
                # Create webhook callback if webhook URL provided
                webhook_callback = create_webhook_callback(
                    sync_options.get("progress_webhook")
                )

                return _execute_repository_sync(
                    repo_id=cleaned_repo_id,
                    username=current_user.username,
                    options=sync_options,
                    progress_callback=webhook_callback,
                )

            job_id = background_job_manager.submit_job(
                "sync_repository",
                sync_job_wrapper,
                params={"repo_id": cleaned_repo_id},
                submitter_username=current_user.username,
            )

            # Return job details
            return RepositorySyncJobResponse(
                job_id=job_id,
                status="queued",
                repository_id=cleaned_repo_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                estimated_completion=None,
                progress=SyncProgress(
                    percentage=0, files_processed=0, files_total=0, current_file=None
                ),
                options=SyncJobOptions(
                    force=sync_request.force,
                    full_reindex=sync_request.full_reindex,
                    incremental=sync_request.incremental,
                ),
            )

        except HTTPException:
            # Re-raise HTTPExceptions as-is
            raise
        except Exception as e:
            logging.error(f"Failed to submit general repository sync job: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit sync job: {str(e)}",
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

    # NOTE: Routes moved before generic {user_alias} route to avoid path conflicts

    # NOTE: Routes moved before generic {user_alias} route to avoid path conflicts

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

    @app.get("/api/repos/golden/{alias}/branches")
    async def list_golden_repository_branches(
        alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List all branches for a golden repository.

        Args:
            alias: Repository alias to list branches for
            current_user: Current authenticated user

        Returns:
            GoldenRepositoryBranchesResponse with branch information

        Raises:
            HTTPException: 404 if repository not found, 403 if access denied, 500 for errors
        """
        try:
            # Check if golden repository exists
            if not golden_repo_manager.golden_repo_exists(alias):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Golden repository '{alias}' not found",
                )

            # Check user permissions
            if not golden_repo_manager.user_can_access_golden_repo(alias, current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: Cannot access golden repository '{alias}'",
                )

            # Get branch information
            branches = await golden_repo_manager.get_golden_repo_branches(alias)

            # Find default branch
            default_branch = None
            for branch in branches:
                if branch.is_default:
                    default_branch = branch.name
                    break

            # Create response
            from code_indexer.server.models.golden_repo_branch_models import (
                GoldenRepositoryBranchesResponse,
            )

            response = GoldenRepositoryBranchesResponse(
                repository_alias=alias,
                total_branches=len(branches),
                default_branch=default_branch,
                branches=branches,
                retrieved_at=datetime.now(timezone.utc),
            )

            return response

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except GitOperationError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Git operation failed: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list repository branches: {str(e)}",
            )

    @app.post("/api/query")
    async def semantic_query(
        request: SemanticQueryRequest,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Unified search endpoint supporting semantic, FTS, and hybrid modes (Story 5).

        Args:
            request: Search request with mode selection and parameters
            current_user: Current authenticated user

        Returns:
            UnifiedSearchResponse for FTS/hybrid modes, or
            SemanticQueryResponse for backward compatibility with semantic mode

        Raises:
            HTTPException: If query fails, index missing, or invalid parameters
        """
        import time
        from pathlib import Path as PathLib

        start_time = time.time()

        try:
            # Handle background job submission (semantic mode only)
            if request.async_query:
                if request.search_mode != "semantic":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Async query only supported for semantic search mode",
                    )

                job_id = semantic_query_manager.submit_query_job(
                    username=current_user.username,
                    query_text=request.query_text,
                    repository_alias=request.repository_alias,
                    limit=request.limit,
                    min_score=request.min_score,
                    file_extensions=request.file_extensions,
                )
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "job_id": job_id,
                        "message": "Semantic query submitted as background job",
                    },
                )

            # Story 5: Handle FTS and Hybrid modes
            if request.search_mode in ["fts", "hybrid"]:
                # Get user's activated repositories
                activated_repos = activated_repo_manager.list_activated_repositories(
                    current_user.username
                )

                if not activated_repos:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No activated repositories found for user",
                    )

                # Filter to specific repository if requested
                if request.repository_alias:
                    activated_repos = [
                        repo
                        for repo in activated_repos
                        if repo["user_alias"] == request.repository_alias
                    ]
                    if not activated_repos:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Repository '{request.repository_alias}' not found",
                        )

                # Check FTS index availability for each repository
                fts_available = False
                repo_path = None
                for repo in activated_repos:
                    # Construct path from activated_repos_dir + username + user_alias
                    repo_path = (
                        PathLib(activated_repo_manager.activated_repos_dir)
                        / current_user.username
                        / repo["user_alias"]
                    )
                    fts_index_dir = repo_path / ".code-indexer" / "tantivy_index"
                    if fts_index_dir.exists():
                        fts_available = True
                        break

                # Validate search mode based on index availability
                search_mode_actual = request.search_mode
                if request.search_mode == "fts" and not fts_available:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "FTS index not available",
                            "suggestion": "Build FTS index with 'cidx index --fts' in the repository",
                            "available_modes": ["semantic"],
                        },
                    )

                if request.search_mode == "hybrid" and not fts_available:
                    # Graceful degradation for hybrid mode
                    logger.warning(
                        f"FTS index not available for user {current_user.username}, degrading hybrid to semantic-only"
                    )
                    search_mode_actual = "semantic"

                # Execute FTS or hybrid search
                fts_results = []
                semantic_results_list = []

                if search_mode_actual in ["fts", "hybrid"] and fts_available:
                    # Execute FTS search
                    from ..services.tantivy_index_manager import TantivyIndexManager

                    try:
                        # repo_path is guaranteed to be set if fts_available is True
                        if repo_path is None:
                            raise RuntimeError(
                                "repo_path is None despite FTS being available"
                            )

                        # Initialize Tantivy manager for first available repository
                        tantivy_manager = TantivyIndexManager(
                            repo_path / ".code-indexer" / "tantivy_index"
                        )
                        tantivy_manager.initialize_index(create_new=False)

                        # Handle fuzzy flag
                        edit_dist = request.edit_distance
                        if request.fuzzy and edit_dist == 0:
                            edit_dist = 1

                        # Execute FTS query
                        fts_raw_results = tantivy_manager.search(
                            query_text=request.query_text,
                            case_sensitive=request.case_sensitive,
                            edit_distance=edit_dist,
                            snippet_lines=request.snippet_lines,
                            limit=request.limit,
                            language_filter=request.language,
                            path_filter=request.path_filter,
                        )

                        # Convert to API response format
                        for result in fts_raw_results:
                            fts_results.append(
                                FTSResultItem(
                                    path=result.get("path", ""),
                                    line_start=result.get("line_start", 0),
                                    line_end=result.get("line_end", 0),
                                    snippet=result.get("snippet", ""),
                                    language=result.get("language", "unknown"),
                                    repository_alias=request.repository_alias
                                    or activated_repos[0]["user_alias"],
                                )
                            )

                    except Exception as e:
                        logger.error(f"FTS search failed: {e}")
                        if request.search_mode == "fts":
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"FTS search failed: {str(e)}",
                            )
                        # For hybrid mode, continue with semantic only
                        search_mode_actual = "semantic"

                # Execute semantic search for hybrid or degraded mode
                if search_mode_actual in ["semantic", "hybrid"]:
                    try:
                        semantic_results_raw = (
                            semantic_query_manager.query_user_repositories(
                                username=current_user.username,
                                query_text=request.query_text,
                                repository_alias=request.repository_alias,
                                limit=request.limit,
                                min_score=request.min_score,
                                file_extensions=request.file_extensions,
                            )
                        )
                        semantic_results_list = [
                            QueryResultItem(**result)
                            for result in semantic_results_raw["results"]
                        ]
                    except Exception as e:
                        logger.error(f"Semantic search failed: {e}")
                        if search_mode_actual == "semantic":
                            raise

                # Calculate execution time
                execution_time_ms = int((time.time() - start_time) * 1000)

                # Return unified response
                return UnifiedSearchResponse(
                    search_mode=search_mode_actual,
                    query=request.query_text,
                    fts_results=fts_results,
                    semantic_results=semantic_results_list,
                    metadata=UnifiedSearchMetadata(
                        query_text=request.query_text,
                        search_mode_requested=request.search_mode,
                        search_mode_actual=search_mode_actual,
                        execution_time_ms=execution_time_ms,
                        fts_available=fts_available,
                        semantic_available=True,  # Assuming semantic always available
                        repositories_searched=len(activated_repos),
                    ),
                )

            # Default semantic mode (backward compatibility)
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

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise

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
            logger.error(f"Unexpected error in unified search: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal search error: {str(e)}",
            )

    @app.get("/api/repositories/{repo_id}")
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
                    # Check if this is a composite repository (Story 3.2)
                    if repo.get("is_composite", False):
                        # Route to composite details handler
                        try:
                            # Convert dict to ActivatedRepository model
                            from datetime import datetime as dt

                            activated_repo_model = ActivatedRepository(
                                user_alias=repo["user_alias"],
                                username=repo["username"],
                                path=Path(repo["path"]),
                                activated_at=(
                                    dt.fromisoformat(repo["activated_at"])
                                    if isinstance(repo["activated_at"], str)
                                    else repo["activated_at"]
                                ),
                                last_accessed=(
                                    dt.fromisoformat(repo["last_accessed"])
                                    if isinstance(repo["last_accessed"], str)
                                    else repo["last_accessed"]
                                ),
                                is_composite=True,
                                golden_repo_aliases=repo.get("golden_repo_aliases", []),
                                discovered_repos=repo.get("discovered_repos", []),
                            )

                            composite_details = _get_composite_details(
                                activated_repo_model
                            )
                            # Return composite details as dict for JSON response
                            return composite_details.model_dump()

                        except Exception as e:
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"Failed to retrieve composite repository details: {str(e)}",
                            )

                    # Found activated repository (single repo) - build response from real data
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
                        # Construct path from activated_repos_dir + username + user_alias
                        repo_path = (
                            Path(activated_repo_manager.activated_repos_dir)
                            / current_user.username
                            / repo["user_alias"]
                        )
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

            # Validate it's not a composite repository
            CompositeRepoValidator.check_operation(repo_path, "branch_list")

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
    @app.get("/api/repositories/{repo_id}/files")
    async def list_repository_files(
        repo_id: str,
        page: int = 1,
        limit: int = 50,
        path_pattern: Optional[str] = None,
        language: Optional[str] = None,
        sort_by: str = "path",
        path: Optional[str] = None,
        recursive: bool = False,
        content: bool = False,
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        List files in repository with pagination and filtering.

        Supports both single and composite repository file listing.
        For composite repos, use path and recursive parameters.
        For single repos, use existing pagination and filtering.
        If content=True and path points to a single file, return file content.
        Uses real file system operations following CLAUDE.md Foundation #1.
        """
        # If content requested and path is a file, return content
        if content and path:
            repo_dict = activated_repo_manager.get_repository(
                current_user.username, repo_id
            )
            if not repo_dict:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Add missing fields required by ActivatedRepository model
            repo_dict["username"] = current_user.username
            repo_dict["path"] = activated_repo_manager.get_activated_repo_path(
                current_user.username, repo_id
            )

            repo = ActivatedRepository.from_dict(repo_dict)
            file_path = Path(repo.path) / path

            if not file_path.exists():
                raise HTTPException(status_code=404, detail=f"File '{path}' not found")

            if not file_path.is_file():
                raise HTTPException(status_code=400, detail=f"Path '{path}' is not a file")

            # Detect if binary
            try:
                with open(file_path, 'rb') as f:
                    chunk = f.read(8192)
                    is_binary = b'\x00' in chunk
                    if not is_binary:
                        try:
                            chunk.decode('utf-8')
                        except UnicodeDecodeError:
                            is_binary = True
            except Exception:
                is_binary = True

            if is_binary:
                return {
                    "path": path,
                    "is_binary": True,
                    "size": file_path.stat().st_size,
                    "content": None
                }
            else:
                try:
                    content_text = file_path.read_text(encoding='utf-8')
                    return {
                        "path": path,
                        "is_binary": False,
                        "size": file_path.stat().st_size,
                        "content": content_text
                    }
                except UnicodeDecodeError:
                    return {
                        "path": path,
                        "is_binary": True,
                        "size": file_path.stat().st_size,
                        "content": None
                    }

        # Check if this is a composite repository
        try:
            repo_dict = activated_repo_manager.get_repository(
                current_user.username, repo_id
            )
            if repo_dict and repo_dict.get("is_composite", False):
                # Composite repository - use simple file listing
                # Convert dict to ActivatedRepository object
                repo = ActivatedRepository.from_dict(repo_dict)
                files = _list_composite_files(
                    repo, path=path or "", recursive=recursive
                )
                return {"files": [f.model_dump() for f in files]}
        except Exception as e:
            logging.debug(f"Could not check composite status for {repo_id}: {e}")
            # Fall through to regular file listing

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

            file_list = file_service.list_files(repo_id, current_user.username, query_params)
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

    # Repository Available Endpoint - must be defined BEFORE generic {user_alias} route
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

    # Repository Status Endpoint - must be defined BEFORE generic {user_alias} route
    @app.get("/api/repos/status", response_model=RepositoryStatusSummary)
    async def get_repository_status_summary(
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get comprehensive repository status summary.

        Provides an overview of:
        - Activated repositories with sync status
        - Available repositories for activation
        - Recent activity and recommendations
        """
        try:
            # Get activated repository manager
            activated_manager = activated_repo_manager

            # Get golden repository manager
            golden_manager = golden_repo_manager

            # Get activated repositories for current user
            activated_repos = activated_manager.list_activated_repositories(
                current_user.username
            )

            # Calculate activated repository statistics
            total_activated = len(activated_repos)
            synced_count = 0
            needs_sync_count = 0
            conflict_count = 0
            recent_activations = []

            for repo in activated_repos:
                if repo.get("sync_status") == "synced":
                    synced_count += 1
                elif repo.get("sync_status") == "needs_sync":
                    needs_sync_count += 1
                elif repo.get("sync_status") == "conflict":
                    conflict_count += 1

                # Add to recent activations if activated within last 7 days
                from datetime import datetime, timezone, timedelta

                try:
                    activation_date_str = repo.get("activated_at")
                    if activation_date_str:
                        activation_date = datetime.fromisoformat(
                            activation_date_str.replace("Z", "+00:00")
                        )
                        if activation_date > datetime.now(timezone.utc) - timedelta(
                            days=7
                        ):
                            recent_activations.append(
                                {
                                    "alias": repo.get("user_alias"),
                                    "activation_date": activation_date_str,
                                }
                            )
                except (ValueError, AttributeError):
                    pass

            # Get available repositories (golden repositories)
            available_repos = golden_manager.list_golden_repos()
            total_available = len(available_repos)

            # Count not activated repositories
            activated_aliases = {
                repo.get("user_alias")
                for repo in activated_repos
                if repo.get("user_alias")
            }
            not_activated_count = sum(
                1
                for repo in available_repos
                if repo.get("alias") not in activated_aliases
            )

            # Get recent activity (recent syncs)
            recent_syncs = []
            for repo in activated_repos:
                try:
                    last_sync_str = repo.get("last_accessed")
                    if last_sync_str:
                        last_sync = datetime.fromisoformat(
                            last_sync_str.replace("Z", "+00:00")
                        )
                        if last_sync > datetime.now(timezone.utc) - timedelta(days=7):
                            sync_status = (
                                "success"
                                if repo.get("sync_status") == "synced"
                                else "failed"
                            )
                            recent_syncs.append(
                                {
                                    "alias": repo.get("user_alias"),
                                    "sync_date": last_sync_str,
                                    "status": sync_status,
                                }
                            )
                except (ValueError, AttributeError):
                    pass

            # Generate recommendations
            recommendations = []
            if total_activated == 0:
                recommendations.append(
                    "No repositories activated yet. Use 'cidx repos available' to browse and activate repositories."
                )
            else:
                if needs_sync_count > 0:
                    recommendations.append(
                        f"{needs_sync_count} repositories need synchronization. Use 'cidx repos sync' to update them."
                    )
                if conflict_count > 0:
                    recommendations.append(
                        f"{conflict_count} repositories have conflicts that need manual resolution."
                    )
                if not_activated_count > 0:
                    recommendations.append(
                        f"{not_activated_count} repositories are available for activation."
                    )

            # Create response
            return RepositoryStatusSummary(
                activated_repositories=ActivatedRepositorySummary(
                    total_count=total_activated,
                    synced_count=synced_count,
                    needs_sync_count=needs_sync_count,
                    conflict_count=conflict_count,
                    recent_activations=recent_activations[
                        -5:
                    ],  # Last 5 recent activations
                ),
                available_repositories=AvailableRepositorySummary(
                    total_count=total_available, not_activated_count=not_activated_count
                ),
                recent_activity=RecentActivity(
                    recent_syncs=recent_syncs[-10:]  # Last 10 recent syncs
                ),
                recommendations=recommendations,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get repository status: {str(e)}",
            )

    # Repository Information Endpoint (Story 6) - generic route MUST be last
    @app.get("/api/repos/{user_alias}")
    async def get_repository_info(
        user_alias: str,
        branches: Optional[bool] = Query(
            False, description="Include branch information"
        ),
        health: Optional[bool] = Query(False, description="Include health monitoring"),
        activity: Optional[bool] = Query(
            False, description="Include activity tracking"
        ),
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Get comprehensive repository information with optional detailed sections.

        Supports query parameters for selective information retrieval:
        - ?branches=true: Include detailed branch information
        - ?health=true: Include health monitoring information
        - ?activity=true: Include activity tracking information

        Following CLAUDE.md Foundation #1: No mocks - real repository data.
        """
        try:
            # Validate user_alias format
            if not user_alias or not user_alias.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Repository alias cannot be empty",
                )

            cleaned_alias = user_alias.strip()

            # Check if repository exists in user's activated repositories
            activated_repos = activated_repo_manager.list_activated_repositories(
                current_user.username
            )

            repo_found = None
            for repo in activated_repos:
                if repo["user_alias"] == cleaned_alias:
                    repo_found = repo
                    break

            if not repo_found:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Repository '{cleaned_alias}' not found or not activated",
                )

            # Get repository path
            repo_path = activated_repo_manager.get_activated_repo_path(
                current_user.username, cleaned_alias
            )

            # Build basic repository information
            result = {
                "alias": cleaned_alias,
                "git_url": repo_found.get("git_url", ""),
                "activation_date": repo_found.get("activation_date", ""),
                "sync_status": repo_found.get("sync_status", "unknown"),
                "last_sync": repo_found.get("last_sync"),
                "golden_repository": repo_found.get("golden_repository", ""),
            }

            # Get current branch
            try:
                current_branch = activated_repo_manager.get_current_branch(
                    current_user.username, cleaned_alias
                )
                result["current_branch"] = current_branch
            except Exception:
                result["current_branch"] = "unknown"

            # Add basic status information
            result["container_status"] = "unknown"
            result["index_status"] = "unknown"
            result["query_ready"] = False

            # Add storage information
            storage_info = {}
            if os.path.exists(repo_path):
                try:
                    # Calculate repository size
                    total_size = 0
                    for root, dirs, files in os.walk(repo_path):
                        if ".git" in dirs:
                            dirs.remove(".git")
                        for file in files:
                            if not file.startswith("."):
                                file_path = os.path.join(root, file)
                                try:
                                    total_size += os.path.getsize(file_path)
                                except (OSError, IOError):
                                    continue

                    storage_info["disk_usage_mb"] = round(total_size / (1024 * 1024), 2)

                    # Calculate index size if exists
                    index_path = os.path.join(repo_path, ".code-indexer")
                    if os.path.exists(index_path):
                        index_size = 0
                        for root, dirs, files in os.walk(index_path):
                            for file in files:
                                try:
                                    index_size += os.path.getsize(
                                        os.path.join(root, file)
                                    )
                                except (OSError, IOError):
                                    continue
                        storage_info["index_size_mb"] = round(
                            index_size / (1024 * 1024), 2
                        )
                except Exception:
                    storage_info["disk_usage_mb"] = 0
                    storage_info["index_size_mb"] = 0

            result["storage_info"] = storage_info

            # Add detailed sections based on query parameters
            if branches:
                try:
                    branch_info = activated_repo_manager.list_repository_branches(
                        current_user.username, cleaned_alias
                    )

                    # Format branches for client
                    formatted_branches = []
                    for branch_name in branch_info.get("branches", []):
                        is_current = branch_name == result.get("current_branch")
                        formatted_branches.append(
                            {
                                "name": branch_name,
                                "is_current": is_current,
                                "last_commit": {
                                    "message": "commit message unavailable",
                                    "timestamp": "unknown",
                                    "author": "unknown",
                                },
                            }
                        )

                    result["branches"] = formatted_branches
                except Exception:
                    result["branches"] = []

            if health:
                health_info: Dict[str, Any] = {
                    "container_status": "unknown",
                    "services": {},
                    "index_status": "unknown",
                    "query_ready": False,
                    "storage": storage_info,
                    "issues": [],
                    "recommendations": [],
                }

                # Try to get real container status
                try:
                    from ...services.docker_manager import DockerManager
                    from ...config import ConfigManager

                    config_manager = ConfigManager.create_with_backtrack(
                        Path(repo_path)
                    )
                    config = config_manager.get_config()

                    docker_manager = DockerManager(config_manager)
                    containers_running = docker_manager.are_containers_running()

                    if containers_running:
                        health_info["container_status"] = "running"
                        health_info["query_ready"] = True

                        # Check individual services
                        health_info["services"]["qdrant"] = {
                            "status": "healthy",
                            "port": config.qdrant.port,
                        }

                        if hasattr(config, "ollama"):
                            health_info["services"]["ollama"] = {
                                "status": "healthy",
                                "port": config.ollama.port,
                            }
                    else:
                        health_info["container_status"] = "stopped"
                        health_info["recommendations"].append(
                            "Containers are stopped. Query operations will auto-start them."
                        )

                except Exception:
                    health_info["issues"].append("Unable to determine container status")

                result["health"] = health_info

            if activity:
                activity_info: Dict[str, Any] = {
                    "recent_commits": [],
                    "sync_history": [],
                    "query_activity": {"recent_queries": 0, "last_query": None},
                    "branch_operations": [],
                }

                # Try to get real git commit history
                try:
                    import subprocess

                    git_log = subprocess.run(
                        ["git", "log", "--oneline", "-5"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    if git_log.returncode == 0:
                        for line in git_log.stdout.strip().split("\n"):
                            if line.strip():
                                parts = line.split(" ", 1)
                                if len(parts) >= 2:
                                    commit_hash = parts[0]
                                    message = parts[1]
                                    activity_info["recent_commits"].append(
                                        {
                                            "commit_hash": commit_hash,
                                            "message": message,
                                            "author": "unknown",
                                            "timestamp": "unknown",
                                        }
                                    )
                except Exception:
                    pass  # Git history unavailable

                # Add sync history from repository metadata
                if repo_found.get("last_sync"):
                    activity_info["sync_history"].append(
                        {
                            "timestamp": repo_found["last_sync"],
                            "status": "success",
                            "changes": "sync details unavailable",
                        }
                    )

                result["activity"] = activity_info

            return result

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Failed to get repository info for {user_alias}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve repository information: {str(e)}",
            )

    # Mount OAuth 2.1 routes
    app.include_router(oauth_router)
    app.include_router(mcp_router)

    # RFC 8414 compliance: OAuth discovery at root level for Claude.ai compatibility
    @app.get("/.well-known/oauth-authorization-server")
    async def root_oauth_discovery():
        """OAuth 2.1 discovery endpoint at root path (RFC 8414 compliance)."""
        from pathlib import Path
        from .auth.oauth.oauth_manager import OAuthManager

        # Use same configuration as /oauth/ routes for consistency
        oauth_db = Path.home() / ".cidx-server" / "oauth.db"
        manager = OAuthManager(db_path=str(oauth_db), issuer=None)
        return manager.get_discovery_metadata()

    return app


# Create app instance
app = create_app()  # ENABLED: Required for uvicorn to load the app
# Note: This was temporarily enabled for manual testing
