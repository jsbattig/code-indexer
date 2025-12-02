"""
Web Admin UI Routes.

Provides admin web interface routes for CIDX server administration.
"""

import logging
import secrets
from pathlib import Path
from typing import Optional

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.user_manager import UserRole
from ..auth import dependencies
from .auth import (
    get_session_manager,
    SessionData,
)

logger = logging.getLogger(__name__)


# Get templates directory path
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Create router
web_router = APIRouter()

# CSRF cookie name and settings
CSRF_COOKIE_NAME = "_csrf"
CSRF_MAX_AGE_SECONDS = 600  # 10 minutes


def _get_csrf_serializer() -> URLSafeTimedSerializer:
    """Get the CSRF token serializer using session manager's secret key."""
    session_manager = get_session_manager()
    # Access the secret key from the serializer
    return URLSafeTimedSerializer(session_manager._serializer.secret_key)


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """
    Set a signed CSRF token cookie.

    Args:
        response: FastAPI Response object
        token: CSRF token to sign and store
    """
    serializer = _get_csrf_serializer()
    signed_value = serializer.dumps(token, salt="csrf-login")

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=signed_value,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="strict",
        max_age=CSRF_MAX_AGE_SECONDS,
    )


def validate_login_csrf_token(request: Request, submitted_token: Optional[str]) -> bool:
    """
    Validate CSRF token for login form using signed cookie.

    Args:
        request: FastAPI Request object
        submitted_token: CSRF token from form submission

    Returns:
        True if valid, False otherwise
    """
    if not submitted_token:
        return False

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_cookie:
        return False

    try:
        serializer = _get_csrf_serializer()
        stored_token = serializer.loads(
            csrf_cookie,
            salt="csrf-login",
            max_age=CSRF_MAX_AGE_SECONDS,
        )
        return secrets.compare_digest(stored_token, submitted_token)
    except (SignatureExpired, BadSignature):
        return False


@web_router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    info: Optional[str] = None,
):
    """
    Render login page.

    Shows login form with CSRF protection using signed cookies.
    """
    # Generate CSRF token for the form
    csrf_token = generate_csrf_token()

    # Check if there's an expired session
    session_manager = get_session_manager()
    if session_manager.is_session_expired(request):
        info = "Session expired, please login again"

    # Create response with CSRF token in signed cookie
    response = templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "error": error,
            "info": info,
            "show_nav": False,
        },
    )

    # Set CSRF token in signed cookie for validation on POST
    set_csrf_cookie(response, csrf_token)

    return response


@web_router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """
    Process login form submission.

    Validates credentials and creates session on success.
    CSRF protection uses signed cookies for pre-session validation.
    """
    # CSRF validation - validate token against signed cookie
    if not validate_login_csrf_token(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )

    # Get user manager from dependencies
    user_manager = dependencies.user_manager
    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User manager not available",
        )

    # Authenticate user
    user = user_manager.authenticate_user(username, password)

    if user is None:
        # Invalid credentials - show error with new CSRF token
        new_csrf_token = generate_csrf_token()
        error_response = templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "csrf_token": new_csrf_token,
                "error": "Invalid username or password",
                "show_nav": False,
            },
            status_code=200,
        )
        set_csrf_cookie(error_response, new_csrf_token)
        return error_response

    # Check if user is admin
    if user.role != UserRole.ADMIN:
        # Non-admin - show error with new CSRF token
        new_csrf_token = generate_csrf_token()
        error_response = templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "csrf_token": new_csrf_token,
                "error": "Admin access required",
                "show_nav": False,
            },
            status_code=200,
        )
        set_csrf_cookie(error_response, new_csrf_token)
        return error_response

    # Create session
    session_manager = get_session_manager()
    redirect_response = RedirectResponse(
        url="/admin/",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_manager.create_session(
        redirect_response,
        username=user.username,
        role=user.role.value,
    )

    return redirect_response


@web_router.get("/logout")
async def logout(request: Request):
    """
    Logout and clear session.

    Redirects to login page after clearing session.
    """
    session_manager = get_session_manager()
    response = RedirectResponse(
        url="/admin/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_manager.clear_session(response)
    return response


def _get_dashboard_service():
    """Get dashboard service, handling import lazily to avoid circular imports."""
    from ..services.dashboard_service import dashboard_service

    return dashboard_service


@web_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Dashboard page - main admin landing page.

    Requires authenticated admin session.
    Displays system health, job statistics, repository counts, and recent activity.
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # Not authenticated - redirect to login
        return RedirectResponse(
            url="/admin/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if session.role != "admin":
        # Not admin - forbidden
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    # Get aggregated dashboard data
    dashboard_service = _get_dashboard_service()
    dashboard_data = dashboard_service.get_dashboard_data(session.username)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "dashboard",
            "show_nav": True,
            "health": dashboard_data.health,
            "job_counts": dashboard_data.job_counts,
            "repo_counts": dashboard_data.repo_counts,
            "recent_jobs": dashboard_data.recent_jobs,
        },
    )


@web_router.get("/partials/dashboard-health", response_class=HTMLResponse)
async def dashboard_health_partial(request: Request):
    """
    Partial refresh endpoint for dashboard health section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    dashboard_service = _get_dashboard_service()
    health_data = dashboard_service.get_health_partial()

    return templates.TemplateResponse(
        "partials/dashboard_health.html",
        {
            "request": request,
            "health": health_data,
        },
    )


@web_router.get("/partials/dashboard-stats", response_class=HTMLResponse)
async def dashboard_stats_partial(request: Request):
    """
    Partial refresh endpoint for dashboard statistics section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    dashboard_service = _get_dashboard_service()
    stats_data = dashboard_service.get_stats_partial(session.username)

    return templates.TemplateResponse(
        "partials/dashboard_stats.html",
        {
            "request": request,
            "job_counts": stats_data["job_counts"],
            "repo_counts": stats_data["repo_counts"],
            "recent_jobs": stats_data["recent_jobs"],
        },
    )


# Placeholder routes for other admin pages
# These will redirect to login if not authenticated


def _require_admin_session(request: Request) -> Optional[SessionData]:
    """Check for valid admin session, return None if not authenticated."""
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session or session.role != "admin":
        return None

    return session


def _get_users_list():
    """Get list of all users from user manager."""
    user_manager = dependencies.user_manager
    if not user_manager:
        return []
    users = user_manager.get_all_users()
    return sorted(users, key=lambda u: u.username.lower())


def _create_users_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create users page response with all necessary context."""
    csrf_token = generate_csrf_token()
    users = _get_users_list()

    response = templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "username": session.username,
            "current_username": session.username,
            "current_page": "users",
            "show_nav": True,
            "csrf_token": csrf_token,
            "users": [
                {
                    "username": u.username,
                    "role": u.role.value,
                    "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
                    if u.created_at
                    else "N/A",
                }
                for u in users
            ],
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    """Users management page - list all users with CRUD operations."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_users_page_response(request, session)


@web_router.post("/users/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    new_username: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """Create a new user."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_users_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate password match
    if new_password != confirm_password:
        return _create_users_page_response(
            request, session, error_message="Passwords do not match"
        )

    # Validate role
    try:
        role_enum = UserRole(role)
    except ValueError:
        return _create_users_page_response(
            request, session, error_message=f"Invalid role: {role}"
        )

    # Create user
    user_manager = dependencies.user_manager
    if not user_manager:
        return _create_users_page_response(
            request, session, error_message="User manager not available"
        )

    try:
        user_manager.create_user(new_username, new_password, role_enum)
        return _create_users_page_response(
            request,
            session,
            success_message=f"User '{new_username}' created successfully",
        )
    except ValueError as e:
        return _create_users_page_response(request, session, error_message=str(e))


@web_router.post("/users/{username}/role", response_class=HTMLResponse)
async def update_user_role(
    request: Request,
    username: str,
    role: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """Update a user's role."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_users_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Prevent demoting self
    if username == session.username and role != "admin":
        return _create_users_page_response(
            request, session, error_message="Cannot demote your own admin account"
        )

    # Validate role
    try:
        role_enum = UserRole(role)
    except ValueError:
        return _create_users_page_response(
            request, session, error_message=f"Invalid role: {role}"
        )

    # Update user
    user_manager = dependencies.user_manager
    if not user_manager:
        return _create_users_page_response(
            request, session, error_message="User manager not available"
        )

    try:
        user_manager.update_user_role(username, role_enum)
        return _create_users_page_response(
            request,
            session,
            success_message=f"User '{username}' role updated successfully",
        )
    except ValueError as e:
        return _create_users_page_response(request, session, error_message=str(e))


@web_router.post("/users/{username}/password", response_class=HTMLResponse)
async def change_user_password(
    request: Request,
    username: str,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """Change a user's password (admin only)."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_users_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate password match
    if new_password != confirm_password:
        return _create_users_page_response(
            request, session, error_message="Passwords do not match"
        )

    # Change password
    user_manager = dependencies.user_manager
    if not user_manager:
        return _create_users_page_response(
            request, session, error_message="User manager not available"
        )

    try:
        user_manager.change_password(username, new_password)
        return _create_users_page_response(
            request,
            session,
            success_message=f"Password for '{username}' changed successfully",
        )
    except ValueError as e:
        return _create_users_page_response(request, session, error_message=str(e))


@web_router.post("/users/{username}/delete", response_class=HTMLResponse)
async def delete_user(
    request: Request,
    username: str,
    csrf_token: Optional[str] = Form(None),
):
    """Delete a user."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_users_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Prevent deleting self
    if username == session.username:
        return _create_users_page_response(
            request, session, error_message="Cannot delete your own account"
        )

    # Delete user
    user_manager = dependencies.user_manager
    if not user_manager:
        return _create_users_page_response(
            request, session, error_message="User manager not available"
        )

    try:
        user_manager.delete_user(username)
        return _create_users_page_response(
            request, session, success_message=f"User '{username}' deleted successfully"
        )
    except ValueError as e:
        return _create_users_page_response(request, session, error_message=str(e))


@web_router.get("/partials/users-list", response_class=HTMLResponse)
async def users_list_partial(request: Request):
    """
    Partial refresh endpoint for users list section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    csrf_token = generate_csrf_token()
    users = _get_users_list()

    response = templates.TemplateResponse(
        "partials/users_list.html",
        {
            "request": request,
            "current_username": session.username,
            "csrf_token": csrf_token,
            "users": [
                {
                    "username": u.username,
                    "role": u.role.value,
                    "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
                    if u.created_at
                    else "N/A",
                }
                for u in users
            ],
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


def _get_golden_repo_manager():
    """Get golden repository manager, handling import lazily to avoid circular imports."""
    from ..repositories.golden_repo_manager import GoldenRepoManager
    import os
    from pathlib import Path

    # Get data directory from environment or use default
    # Must match app.py: data_dir = server_data_dir / "data"
    server_data_dir = os.environ.get(
        "CIDX_SERVER_DATA_DIR", os.path.expanduser("~/.cidx-server")
    )
    data_dir = str(Path(server_data_dir) / "data")
    return GoldenRepoManager(data_dir=data_dir)


def _get_golden_repos_list():
    """Get list of all golden repositories from manager."""
    try:
        manager = _get_golden_repo_manager()
        repos = manager.list_golden_repos()
        # Add status information for display
        for repo in repos:
            # Default status to 'ready' if not set
            if "status" not in repo:
                repo["status"] = "ready"
            # Format last_indexed date if available
            if "created_at" in repo and repo["created_at"]:
                repo["last_indexed"] = repo["created_at"][:10]  # Just the date part
            else:
                repo["last_indexed"] = None
        return repos
    except Exception as e:
        logger.error("Failed to get golden repos list: %s", e, exc_info=True)
        return []


def _create_golden_repos_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create golden repos page response with all necessary context."""
    csrf_token = generate_csrf_token()
    repos = _get_golden_repos_list()

    response = templates.TemplateResponse(
        "golden_repos.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "golden-repos",
            "show_nav": True,
            "csrf_token": csrf_token,
            "repos": repos,
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/golden-repos", response_class=HTMLResponse)
async def golden_repos_page(request: Request):
    """Golden repositories management page - list all golden repos with CRUD operations."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_golden_repos_page_response(request, session)


@web_router.post("/golden-repos/add", response_class=HTMLResponse)
async def add_golden_repo(
    request: Request,
    alias: str = Form(...),
    repo_url: str = Form(...),
    default_branch: str = Form("main"),
    csrf_token: Optional[str] = Form(None),
):
    """Add a new golden repository."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_golden_repos_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate inputs
    if not alias or not alias.strip():
        return _create_golden_repos_page_response(
            request, session, error_message="Repository name is required"
        )

    if not repo_url or not repo_url.strip():
        return _create_golden_repos_page_response(
            request, session, error_message="Repository path/URL is required"
        )

    # Try to add the repository
    try:
        manager = _get_golden_repo_manager()
        job_id = manager.add_golden_repo(
            repo_url=repo_url.strip(),
            alias=alias.strip(),
            default_branch=default_branch.strip() or "main",
            submitter_username=session.username,
        )
        return _create_golden_repos_page_response(
            request,
            session,
            success_message=f"Repository '{alias}' add job submitted (Job ID: {job_id})",
        )
    except Exception as e:
        error_msg = str(e)
        # Handle common error cases
        if "already exists" in error_msg.lower():
            error_msg = f"Repository alias '{alias}' already exists"
        elif "invalid" in error_msg.lower() or "inaccessible" in error_msg.lower():
            error_msg = f"Invalid or inaccessible repository: {repo_url}"
        return _create_golden_repos_page_response(
            request, session, error_message=error_msg
        )


@web_router.post("/golden-repos/{alias}/delete", response_class=HTMLResponse)
async def delete_golden_repo(
    request: Request,
    alias: str,
    csrf_token: Optional[str] = Form(None),
):
    """Delete a golden repository."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_golden_repos_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Try to delete the repository
    try:
        manager = _get_golden_repo_manager()
        job_id = manager.remove_golden_repo(
            alias=alias,
            submitter_username=session.username,
        )
        return _create_golden_repos_page_response(
            request,
            session,
            success_message=f"Repository '{alias}' deletion job submitted (Job ID: {job_id})",
        )
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            error_msg = f"Repository '{alias}' not found"
        return _create_golden_repos_page_response(
            request, session, error_message=error_msg
        )


@web_router.post("/golden-repos/{alias}/refresh", response_class=HTMLResponse)
async def refresh_golden_repo(
    request: Request,
    alias: str,
    csrf_token: Optional[str] = Form(None),
):
    """Refresh (re-index) a golden repository."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_golden_repos_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Try to refresh the repository
    try:
        manager = _get_golden_repo_manager()
        job_id = manager.refresh_golden_repo(
            alias=alias,
            submitter_username=session.username,
        )
        return _create_golden_repos_page_response(
            request,
            session,
            success_message=f"Repository '{alias}' refresh job submitted (Job ID: {job_id})",
        )
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            error_msg = f"Repository '{alias}' not found"
        return _create_golden_repos_page_response(
            request, session, error_message=error_msg
        )


@web_router.get("/golden-repos/{alias}/details", response_class=HTMLResponse)
async def golden_repo_details(
    request: Request,
    alias: str,
):
    """Get details for a specific golden repository."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        manager = _get_golden_repo_manager()
        repo = manager.get_golden_repo(alias)
        if not repo:
            raise HTTPException(
                status_code=404, detail=f"Repository '{alias}' not found"
            )

        # Return repository details as JSON-like HTML response
        return templates.TemplateResponse(
            "partials/golden_repos_list.html",
            {
                "request": request,
                "csrf_token": generate_csrf_token(),
                "repos": [repo.to_dict()],
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get golden repo details for '%s': %s", alias, e, exc_info=True)
        raise HTTPException(status_code=404, detail=f"Repository '{alias}' not found")


@web_router.get("/partials/golden-repos-list", response_class=HTMLResponse)
async def golden_repos_list_partial(request: Request):
    """
    Partial refresh endpoint for golden repos list section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    csrf_token = generate_csrf_token()
    repos = _get_golden_repos_list()

    response = templates.TemplateResponse(
        "partials/golden_repos_list.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "repos": repos,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


def _get_activated_repo_manager():
    """Get activated repository manager, handling import lazily to avoid circular imports."""
    from ..repositories.activated_repo_manager import ActivatedRepoManager
    import os
    from pathlib import Path

    # Get data directory from environment or use default
    # Must match app.py: data_dir = server_data_dir / "data"
    server_data_dir = os.environ.get(
        "CIDX_SERVER_DATA_DIR", os.path.expanduser("~/.cidx-server")
    )
    data_dir = str(Path(server_data_dir) / "data")
    return ActivatedRepoManager(data_dir=data_dir)


def _get_all_activated_repos() -> list:
    """
    Get all activated repositories across all users.

    Returns:
        List of activated repository dictionaries with username added
    """
    import os

    try:
        manager = _get_activated_repo_manager()
        all_repos = []

        # Get base activated-repos directory
        activated_repos_dir = manager.activated_repos_dir

        if not os.path.exists(activated_repos_dir):
            return []

        # Iterate over all user directories
        for username in os.listdir(activated_repos_dir):
            user_dir = os.path.join(activated_repos_dir, username)
            if os.path.isdir(user_dir):
                # Get repositories for this user
                user_repos = manager.list_activated_repositories(username)
                for repo in user_repos:
                    # Add username to repo data
                    repo["username"] = username
                    # Set default status if not present
                    if "status" not in repo:
                        repo["status"] = "active"
                    all_repos.append(repo)

        # Sort by activation date (newest first)
        all_repos.sort(key=lambda r: r.get("activated_at", ""), reverse=True)
        return all_repos

    except Exception as e:
        logger.error("Failed to get activated repos: %s", e, exc_info=True)
        return []


def _get_unique_golden_repos(repos: list) -> list:
    """Get list of unique golden repo aliases from activated repos."""
    golden_repos = set()
    for repo in repos:
        golden_alias = repo.get("golden_repo_alias")
        if golden_alias:
            golden_repos.add(golden_alias)
    return sorted(list(golden_repos))


def _get_unique_users(repos: list) -> list:
    """Get list of unique usernames from activated repos."""
    users = set()
    for repo in repos:
        username = repo.get("username")
        if username:
            users.add(username)
    return sorted(list(users))


def _filter_repos(
    repos: list,
    search: Optional[str] = None,
    golden_repo: Optional[str] = None,
    user: Optional[str] = None,
) -> list:
    """Filter repositories based on search criteria."""
    filtered = repos

    if search:
        search_lower = search.lower()
        filtered = [
            r
            for r in filtered
            if search_lower in r.get("user_alias", "").lower()
            or search_lower in r.get("username", "").lower()
            or search_lower in r.get("golden_repo_alias", "").lower()
        ]

    if golden_repo:
        filtered = [r for r in filtered if r.get("golden_repo_alias") == golden_repo]

    if user:
        filtered = [r for r in filtered if r.get("username") == user]

    return filtered


def _paginate_repos(repos: list, page: int = 1, per_page: int = 25) -> tuple:
    """Paginate repositories list.

    Returns:
        Tuple of (paginated_repos, total_pages, current_page)
    """
    total = len(repos)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated = repos[start_idx:end_idx]

    return paginated, total_pages, page


def _create_repos_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
    search: Optional[str] = None,
    golden_repo_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    page: int = 1,
) -> HTMLResponse:
    """Create repos page response with all necessary context."""
    csrf_token = generate_csrf_token()

    # Get all activated repos
    all_repos = _get_all_activated_repos()

    # Get unique values for filter dropdowns
    golden_repos = _get_unique_golden_repos(all_repos)
    users = _get_unique_users(all_repos)

    # Apply filters
    filtered_repos = _filter_repos(all_repos, search, golden_repo_filter, user_filter)

    # Paginate
    paginated_repos, total_pages, current_page = _paginate_repos(filtered_repos, page)

    response = templates.TemplateResponse(
        "repos.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "repos",
            "show_nav": True,
            "csrf_token": csrf_token,
            "repos": paginated_repos,
            "golden_repos": golden_repos,
            "users": users,
            "search": search,
            "golden_repo_filter": golden_repo_filter,
            "user_filter": user_filter,
            "page": current_page,
            "total_pages": total_pages,
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/repos", response_class=HTMLResponse)
async def repos_page(
    request: Request,
    search: Optional[str] = None,
    golden_repo: Optional[str] = None,
    user: Optional[str] = None,
    page: int = 1,
):
    """
    Activated repositories management page.

    Displays all activated repositories with filtering and pagination.
    Sorted by activation date (newest first).
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_repos_page_response(
        request,
        session,
        search=search,
        golden_repo_filter=golden_repo,
        user_filter=user,
        page=page,
    )


@web_router.get("/partials/repos-list", response_class=HTMLResponse)
async def repos_list_partial(
    request: Request,
    search: Optional[str] = None,
    golden_repo: Optional[str] = None,
    user: Optional[str] = None,
    page: int = 1,
):
    """
    Partial refresh endpoint for repos list section.

    Returns HTML fragment for htmx partial updates.
    Supports filtering and pagination parameters.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    csrf_token = generate_csrf_token()

    # Get all activated repos
    all_repos = _get_all_activated_repos()

    # Apply filters
    filtered_repos = _filter_repos(all_repos, search, golden_repo, user)

    # Paginate
    paginated_repos, total_pages, current_page = _paginate_repos(filtered_repos, page)

    response = templates.TemplateResponse(
        "partials/repos_list.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "repos": paginated_repos,
            "search": search,
            "golden_repo_filter": golden_repo,
            "user_filter": user,
            "page": current_page,
            "total_pages": total_pages,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/repos/{username}/{user_alias}/details", response_class=HTMLResponse)
async def repo_details(
    request: Request,
    username: str,
    user_alias: str,
):
    """
    Get details for a specific activated repository.

    Returns detailed information about the repository.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        manager = _get_activated_repo_manager()
        repo = manager.get_repository(username, user_alias)

        if not repo:
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{user_alias}' not found for user '{username}'",
            )

        # Add username to repo data
        repo["username"] = username

        # Return repository details as HTML partial
        return templates.TemplateResponse(
            "partials/repos_list.html",
            {
                "request": request,
                "csrf_token": generate_csrf_token(),
                "repos": [repo],
            },
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{user_alias}' not found for user '{username}'",
        )


@web_router.post(
    "/repos/{username}/{user_alias}/deactivate", response_class=HTMLResponse
)
async def deactivate_repo(
    request: Request,
    username: str,
    user_alias: str,
    csrf_token: Optional[str] = Form(None),
):
    """
    Deactivate an activated repository.

    Removes the activated repository for the specified user.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_repos_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Try to deactivate the repository
    try:
        manager = _get_activated_repo_manager()
        job_id = manager.deactivate_repository(
            username=username,
            user_alias=user_alias,
        )
        return _create_repos_page_response(
            request,
            session,
            success_message=f"Repository '{user_alias}' deactivation job submitted (Job ID: {job_id})",
        )
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            error_msg = f"Repository '{user_alias}' not found for user '{username}'"
        return _create_repos_page_response(request, session, error_message=error_msg)


def _get_background_job_manager():
    """Get the background job manager instance."""
    try:
        from ..app import background_job_manager

        return background_job_manager
    except Exception as e:
        logger.error("Failed to get background job manager: %s", e, exc_info=True)
        return None


def _get_all_jobs(
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """
    Get all jobs with filters and pagination.

    Returns jobs from background job manager with optional filtering.
    """
    job_manager = _get_background_job_manager()
    if not job_manager:
        return [], 0, 0

    # Get all jobs from manager
    all_jobs = []
    with job_manager._lock:
        for job in job_manager.jobs.values():
            job_dict = {
                "job_id": job.job_id,
                "job_type": job.operation_type,
                "operation_type": job.operation_type,
                "status": job.status.value
                if hasattr(job.status, "value")
                else str(job.status),
                "progress": job.progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat()
                if job.completed_at
                else None,
                "error_message": job.error,
                "username": job.username,
                "user_alias": getattr(job, "user_alias", None),
                "repository_name": getattr(job.result, "alias", None)
                if job.result and isinstance(job.result, dict)
                else None,
                "repository_url": getattr(job, "repository_url", None),
                "progress_info": getattr(job, "progress_info", None),
            }
            # Try to get repository name from result
            if job.result and isinstance(job.result, dict):
                job_dict["repository_name"] = job.result.get("alias") or job.result.get(
                    "repository"
                )
            all_jobs.append(job_dict)

    # Apply filters
    if status_filter:
        all_jobs = [j for j in all_jobs if j["status"] == status_filter]

    if type_filter:
        all_jobs = [
            j
            for j in all_jobs
            if j["job_type"] == type_filter or j["operation_type"] == type_filter
        ]

    if search:
        search_lower = search.lower()
        all_jobs = [
            j
            for j in all_jobs
            if (
                j.get("repository_name")
                and search_lower in j["repository_name"].lower()
            )
            or (j.get("repository_url") and search_lower in j["repository_url"].lower())
            or (j.get("user_alias") and search_lower in j["user_alias"].lower())
        ]

    # Sort by created_at (newest first)
    all_jobs.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    # Pagination
    total_count = len(all_jobs)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    offset = (page - 1) * page_size
    paginated_jobs = all_jobs[offset : offset + page_size]

    return paginated_jobs, total_count, total_pages


def _create_jobs_page_response(
    request: Request,
    session: SessionData,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """Create jobs page response with filters and pagination."""
    # Generate CSRF token
    csrf_token = generate_csrf_token()

    # Get jobs
    jobs, total_count, total_pages = _get_all_jobs(
        status_filter=status_filter,
        type_filter=type_filter,
        search=search,
        page=page,
    )

    response = templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "jobs",
            "show_nav": True,
            "csrf_token": csrf_token,
            "jobs": jobs,
            "total_count": total_count,
            "total_pages": total_pages,
            "page": page,
            "status_filter": status_filter,
            "type_filter": type_filter,
            "search": search,
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(
    request: Request,
    status_filter: Optional[str] = None,
    job_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
):
    """Jobs monitoring page - view and manage background jobs."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_jobs_page_response(
        request,
        session,
        status_filter=status_filter,
        type_filter=job_type,
        search=search,
        page=page,
    )


@web_router.get("/partials/jobs-list", response_class=HTMLResponse)
async def jobs_list_partial(
    request: Request,
    status_filter: Optional[str] = None,
    job_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
):
    """Partial endpoint for jobs list - used by htmx for dynamic updates."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Generate CSRF token for cancel forms
    csrf_token = generate_csrf_token()

    # Get jobs
    jobs, total_count, total_pages = _get_all_jobs(
        status_filter=status_filter,
        type_filter=job_type,
        search=search,
        page=page,
    )

    response = templates.TemplateResponse(
        "partials/jobs_list.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "jobs": jobs,
            "total_count": total_count,
            "total_pages": total_pages,
            "page": page,
            "status_filter": status_filter,
            "type_filter": job_type,
            "search": search,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.post("/jobs/{job_id}/cancel", response_class=HTMLResponse)
async def cancel_job(
    request: Request,
    job_id: str,
    csrf_token: Optional[str] = Form(None),
):
    """Cancel a running or pending job."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    # Get job manager
    job_manager = _get_background_job_manager()
    if not job_manager:
        return _create_jobs_page_response(
            request, session, error_message="Job manager not available"
        )

    # Cancel job
    try:
        result = job_manager.cancel_job(job_id, session.username)
        if result.get("success"):
            return _create_jobs_page_response(
                request,
                session,
                success_message=f"Job {job_id[:8]}... cancelled successfully",
            )
        else:
            return _create_jobs_page_response(
                request,
                session,
                error_message=result.get("message", "Failed to cancel job"),
            )
    except Exception as e:
        return _create_jobs_page_response(
            request, session, error_message=f"Error cancelling job: {str(e)}"
        )


# Session-based query history storage (in-memory, per session)
# Key: session_id, Value: list of query dicts
_query_history: dict = {}
MAX_QUERY_HISTORY = 10


def _get_session_query_history(session_username: str) -> list:
    """Get query history for a session."""
    return _query_history.get(session_username, [])


def _add_to_query_history(
    session_username: str, query_text: str, repository: str, search_mode: str
) -> None:
    """Add a query to session history."""
    if session_username not in _query_history:
        _query_history[session_username] = []

    history = _query_history[session_username]

    # Add new query at the beginning
    history.insert(
        0,
        {
            "query_text": query_text,
            "repository": repository,
            "search_mode": search_mode,
        },
    )

    # Keep only MAX_QUERY_HISTORY items
    if len(history) > MAX_QUERY_HISTORY:
        _query_history[session_username] = history[:MAX_QUERY_HISTORY]


def _get_all_activated_repos_for_query() -> list:
    """
    Get all activated repositories for query dropdown.

    Returns list of repos with user_alias and username.
    """
    return _get_all_activated_repos()


def _create_query_page_response(
    request: Request,
    session: SessionData,
    query_text: str = "",
    selected_repository: str = "",
    search_mode: str = "semantic",
    limit: int = 10,
    language: str = "",
    path_pattern: str = "",
    min_score: str = "",
    results: Optional[list] = None,
    query_executed: bool = False,
    error_message: Optional[str] = None,
    success_message: Optional[str] = None,
) -> HTMLResponse:
    """Create query page response with all necessary context."""
    csrf_token = generate_csrf_token()
    repositories = _get_all_activated_repos_for_query()
    query_history = _get_session_query_history(session.username)

    response = templates.TemplateResponse(
        "query.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "query",
            "show_nav": True,
            "csrf_token": csrf_token,
            "repositories": repositories,
            "query_history": query_history,
            "query_text": query_text,
            "selected_repository": selected_repository,
            "search_mode": search_mode,
            "limit": limit,
            "language": language,
            "path_pattern": path_pattern,
            "min_score": min_score,
            "results": results,
            "query_executed": query_executed,
            "error_message": error_message,
            "success_message": success_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    """Query testing interface page."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_query_page_response(request, session)


@web_router.post("/query", response_class=HTMLResponse)
async def query_submit(
    request: Request,
    query_text: str = Form(""),
    repository: str = Form(""),
    search_mode: str = Form("semantic"),
    limit: int = Form(10),
    language: str = Form(""),
    path_pattern: str = Form(""),
    min_score: str = Form(""),
    csrf_token: Optional[str] = Form(None),
):
    """Process query form submission."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_query_page_response(
            request,
            session,
            query_text=query_text,
            selected_repository=repository,
            search_mode=search_mode,
            limit=limit,
            language=language,
            path_pattern=path_pattern,
            min_score=min_score,
            error_message="Invalid CSRF token",
        )

    # Validate required fields
    if not query_text or not query_text.strip():
        return _create_query_page_response(
            request,
            session,
            query_text=query_text,
            selected_repository=repository,
            search_mode=search_mode,
            limit=limit,
            language=language,
            path_pattern=path_pattern,
            min_score=min_score,
            error_message="Query text is required",
        )

    if not repository:
        return _create_query_page_response(
            request,
            session,
            query_text=query_text,
            selected_repository=repository,
            search_mode=search_mode,
            limit=limit,
            language=language,
            path_pattern=path_pattern,
            min_score=min_score,
            error_message="Please select a repository",
        )

    # Add to query history
    _add_to_query_history(session.username, query_text.strip(), repository, search_mode)

    # Execute query (placeholder - in real implementation, call query API)
    results = []
    query_executed = True

    # TODO: Implement actual query execution via API
    # For now, return empty results since we don't have real query implementation
    # In production, this would call the query API endpoint

    return _create_query_page_response(
        request,
        session,
        query_text=query_text,
        selected_repository=repository,
        search_mode=search_mode,
        limit=limit,
        language=language,
        path_pattern=path_pattern,
        min_score=min_score,
        results=results,
        query_executed=query_executed,
    )


@web_router.get("/partials/query-results", response_class=HTMLResponse)
async def query_results_partial(request: Request):
    """
    Partial refresh endpoint for query results.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        "partials/query_results.html",
        {
            "request": request,
            "results": None,
            "query_executed": False,
            "query_text": "",
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.post("/partials/query-results", response_class=HTMLResponse)
async def query_results_partial_post(
    request: Request,
    query_text: str = Form(""),
    repository: str = Form(""),
    search_mode: str = Form("semantic"),
    limit: int = Form(10),
    language: str = Form(""),
    path_pattern: str = Form(""),
    min_score: str = Form(""),
    csrf_token: Optional[str] = Form(None),
):
    """
    Execute query and return results partial via htmx.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return templates.TemplateResponse(
            "partials/query_results.html",
            {
                "request": request,
                "results": None,
                "query_executed": False,
                "query_text": query_text,
                "error_message": "Invalid CSRF token",
            },
        )

    # Validate required fields
    if not query_text or not query_text.strip():
        return templates.TemplateResponse(
            "partials/query_results.html",
            {
                "request": request,
                "results": None,
                "query_executed": False,
                "query_text": query_text,
                "error_message": "Query text is required",
            },
        )

    # Add to query history if repository selected
    if repository:
        _add_to_query_history(
            session.username, query_text.strip(), repository, search_mode
        )

    # Execute query (placeholder - in real implementation, call query API)
    results = []
    query_executed = True

    # TODO: Implement actual query execution via API
    # For now, return empty results since we don't have real query implementation

    csrf_token_new = generate_csrf_token()
    response = templates.TemplateResponse(
        "partials/query_results.html",
        {
            "request": request,
            "results": results,
            "query_executed": query_executed,
            "query_text": query_text,
        },
    )

    set_csrf_cookie(response, csrf_token_new)
    return response


def _get_default_config() -> dict:
    """Get default configuration values."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 4,
            "log_level": "INFO",
        },
        "indexing": {
            "batch_size": 100,
            "max_file_size": 1048576,  # 1MB
            "excluded_patterns": ["*.pyc", "__pycache__", ".git", "node_modules"],
        },
        "query": {
            "default_limit": 10,
            "max_limit": 100,
            "timeout": 30,
            "min_score": 0.5,
        },
        "storage": {
            "data_directory": "~/.cidx-server/data",
            "vector_store_path": "~/.cidx-server/vectors",
        },
        "security": {
            "session_timeout": 28800,  # 8 hours
            "token_expiration": 3600,  # 1 hour
        },
    }


def _get_current_config() -> dict:
    """Get current configuration from environment or defaults."""
    import os

    default_config = _get_default_config()

    # Server settings from environment
    server_data_dir = os.environ.get(
        "CIDX_SERVER_DATA_DIR", os.path.expanduser("~/.cidx-server")
    )

    # Override with environment values if available
    config = {
        "server": {
            "host": os.environ.get("CIDX_HOST", default_config["server"]["host"]),
            "port": int(os.environ.get("CIDX_PORT", default_config["server"]["port"])),
            "workers": int(
                os.environ.get("CIDX_WORKERS", default_config["server"]["workers"])
            ),
            "log_level": os.environ.get(
                "CIDX_LOG_LEVEL", default_config["server"]["log_level"]
            ),
        },
        "indexing": default_config["indexing"].copy(),
        "query": default_config["query"].copy(),
        "storage": {
            "data_directory": server_data_dir,
            "vector_store_path": os.path.join(server_data_dir, "vectors"),
        },
        "security": default_config["security"].copy(),
    }

    return config


def _validate_config_section(section: str, data: dict) -> Optional[str]:
    """Validate configuration for a section, return error message if invalid."""
    if section == "server":
        # Validate host - cannot be empty
        host = data.get("host")
        if host is not None:
            host_str = str(host).strip()
            if not host_str:
                return "Host cannot be empty"

        port = data.get("port")
        if port is not None:
            try:
                port_int = int(port)
                if port_int < 1 or port_int > 65535:
                    return "Port must be between 1 and 65535"
            except (ValueError, TypeError):
                return "Port must be a valid number"

        workers = data.get("workers")
        if workers is not None:
            try:
                workers_int = int(workers)
                if workers_int < 1:
                    return "Workers must be a positive number"
            except (ValueError, TypeError):
                return "Workers must be a valid number"

        # Validate log_level - must be one of DEBUG, INFO, WARNING, ERROR
        log_level = data.get("log_level")
        if log_level is not None:
            valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
            if log_level.upper() not in valid_log_levels:
                return f"Log level must be one of: {', '.join(valid_log_levels)}"

    elif section == "indexing":
        batch_size = data.get("batch_size")
        if batch_size is not None:
            try:
                batch_int = int(batch_size)
                if batch_int < 1:
                    return "Batch size must be a positive number"
            except (ValueError, TypeError):
                return "Batch size must be a valid number"

        max_file_size = data.get("max_file_size")
        if max_file_size is not None:
            try:
                size_int = int(max_file_size)
                if size_int < 1:
                    return "Max file size must be a positive number"
            except (ValueError, TypeError):
                return "Max file size must be a valid number"

        # Validate excluded_patterns - basic format check
        excluded_patterns = data.get("excluded_patterns")
        if excluded_patterns is not None:
            patterns_str = str(excluded_patterns).strip()
            if patterns_str:
                # Split by newlines and check each pattern
                patterns = [p.strip() for p in patterns_str.split('\n') if p.strip()]
                for pattern in patterns:
                    # Check for invalid characters that could cause issues
                    if '\0' in pattern:
                        return "Excluded patterns cannot contain null characters"
                    # Patterns should not be excessively long
                    if len(pattern) > 500:
                        return "Individual excluded patterns cannot exceed 500 characters"

    elif section == "query":
        for field in ["default_limit", "max_limit", "timeout"]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 1:
                        field_name = field.replace('_', ' ').title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace('_', ' ').title()
                    return f"{field_name} must be a valid number"

        min_score = data.get("min_score")
        if min_score is not None:
            try:
                score_float = float(min_score)
                if score_float < 0 or score_float > 1:
                    return "Min score must be between 0 and 1"
            except (ValueError, TypeError):
                return "Min score must be a valid number"

    elif section == "security":
        for field in ["session_timeout", "token_expiration"]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 60:
                        field_name = field.replace('_', ' ').title()
                        return f"{field_name} must be at least 60 seconds"
                except (ValueError, TypeError):
                    field_name = field.replace('_', ' ').title()
                    return f"{field_name} must be a valid number"

    return None


def _create_config_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
    validation_errors: Optional[dict] = None,
) -> HTMLResponse:
    """Create config page response with all necessary context."""
    csrf_token = generate_csrf_token()
    config = _get_current_config()

    response = templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "config",
            "show_nav": True,
            "csrf_token": csrf_token,
            "config": config,
            "success_message": success_message,
            "error_message": error_message,
            "validation_errors": validation_errors or {},
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration management page - view and edit CIDX configuration."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    return _create_config_page_response(request, session)


@web_router.post("/config/{section}", response_class=HTMLResponse)
async def update_config_section(
    request: Request,
    section: str,
    csrf_token: Optional[str] = Form(None),
):
    """Update configuration for a specific section."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_config_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate section
    valid_sections = ["server", "indexing", "query", "storage", "security"]
    if section not in valid_sections:
        return _create_config_page_response(
            request, session, error_message=f"Invalid section: {section}"
        )

    # Get form data
    form_data = await request.form()
    data = {k: v for k, v in form_data.items() if k != "csrf_token"}

    # Validate configuration
    error = _validate_config_section(section, data)
    if error:
        return _create_config_page_response(
            request,
            session,
            error_message=error,
            validation_errors={section: error},
        )

    # Configuration preview only - backend API doesn't support persistence yet
    return _create_config_page_response(
        request,
        session,
        success_message=f"{section.title()} configuration preview updated (changes not persisted - requires API implementation)",
    )


@web_router.post("/config/reset", response_class=HTMLResponse)
async def reset_config(
    request: Request,
    csrf_token: Optional[str] = Form(None),
):
    """Reset configuration to defaults."""
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_config_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Configuration preview only - backend API doesn't support persistence yet
    return _create_config_page_response(
        request,
        session,
        success_message="Configuration preview reset to defaults (changes not persisted)",
    )


@web_router.get("/partials/config-section", response_class=HTMLResponse)
async def config_section_partial(
    request: Request,
    section: Optional[str] = None,
):
    """
    Partial refresh endpoint for config section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/admin/login", status_code=status.HTTP_303_SEE_OTHER
        )

    csrf_token = generate_csrf_token()
    config = _get_current_config()

    response = templates.TemplateResponse(
        "partials/config_section.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "config": config,
            "validation_errors": {},
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response
