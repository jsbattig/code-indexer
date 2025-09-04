"""
FastAPI application for CIDX Server.

Multi-user semantic code search server with JWT authentication and role-based access control.
"""

from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, List
import psutil
from datetime import datetime, timezone

from .auth.jwt_manager import JWTManager
from .auth.user_manager import UserManager, UserRole
from .auth import dependencies
from .auth.password_validator import (
    validate_password_complexity,
    get_password_complexity_error_message,
)
from .utils.jwt_secret_manager import JWTSecretManager
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

    new_password: str = Field(
        ..., min_length=1, max_length=1000, description="New password"
    )

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


# Global managers (initialized in create_app)
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None
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


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    global jwt_manager, user_manager, golden_repo_manager, background_job_manager, activated_repo_manager, repository_listing_manager, semantic_query_manager, _server_start_time

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

    # Initialize authentication managers with persistent JWT secret
    jwt_secret_manager = JWTSecretManager()
    secret_key = jwt_secret_manager.get_or_create_secret()
    jwt_manager = JWTManager(
        secret_key=secret_key, token_expiration_minutes=10, algorithm="HS256"
    )
    user_manager = UserManager()
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

    # Public endpoints (no authentication required)
    @app.get("/health")
    async def health_check():
        """
        Enhanced health check endpoint.

        Provides detailed server status including uptime, job queue health,
        system resource usage, and recent error information. No authentication
        required for monitoring systems.
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
    async def login(login_data: LoginRequest):
        """
        Authenticate user and return JWT token.

        Args:
            login_data: Username and password

        Returns:
            JWT token and user information

        Raises:
            HTTPException: If authentication fails
        """
        # Authenticate user
        user = user_manager.authenticate_user(login_data.username, login_data.password)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create JWT token
        user_data = {
            "username": user.username,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
        }
        access_token = jwt_manager.create_token(user_data)

        return LoginResponse(
            access_token=access_token, token_type="bearer", user=user.to_dict()
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
        current_user: dependencies.User = Depends(dependencies.get_current_user),
    ):
        """
        Change current user's password.

        Args:
            password_data: New password data
            current_user: Current authenticated user

        Returns:
            Success message
        """
        success = user_manager.change_password(
            current_user.username, password_data.new_password
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {current_user.username}",
            )

        return MessageResponse(message="Password changed successfully")

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

    @app.delete("/api/admin/golden-repos/{alias}", response_model=MessageResponse)
    async def remove_golden_repo(
        alias: str,
        current_user: dependencies.User = Depends(dependencies.get_current_admin_user),
    ):
        """
        Remove a golden repository (admin only).

        Args:
            alias: Alias of the repository to remove
            current_user: Current authenticated admin user

        Returns:
            Success message

        Raises:
            HTTPException: If repository not found or removal fails
        """
        try:
            result = golden_repo_manager.remove_golden_repo(alias)
            return MessageResponse(message=result["message"])

        except GitOperationError as e:
            # Cleanup/filesystem errors - return 500 (must be before GoldenRepoError since GitOperationError inherits from it)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )
        except GoldenRepoError as e:
            # Repository not found - return 404
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except Exception as e:
            # Unexpected errors - return 500
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to remove repository: {str(e)}",
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

    return app


# Create app instance
app = create_app()
