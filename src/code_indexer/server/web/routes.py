from code_indexer.server.middleware.correlation import get_correlation_id
"""
Web Admin UI Routes.

Provides admin web interface routes for CIDX server administration.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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
from ..services.ci_token_manager import CITokenManager, TokenValidationError

logger = logging.getLogger(__name__)


# Get templates directory path
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Create router
web_router = APIRouter()
# Create user router for non-admin user routes
user_router = APIRouter()
# Create login router for unified authentication (root level /login)
login_router = APIRouter()

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


def set_csrf_cookie(response: Response, token: str, path: str = "/") -> None:
    """
    Set a signed CSRF token cookie.

    Args:
        response: FastAPI Response object
        token: CSRF token to sign and store
        path: Cookie path (default: "/" for unified login)
    """
    serializer = _get_csrf_serializer()
    signed_value = serializer.dumps(token, salt="csrf-login")

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=signed_value,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",  # Changed from strict to allow HTMX partial requests
        max_age=CSRF_MAX_AGE_SECONDS,
        path=path,  # Cookie path (default "/" for unified login)
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
    logger.debug(
        "CSRF validation: submitted_token=%s, has_csrf_cookie=%s, all_cookies=%s",
        submitted_token[:20] + "..." if submitted_token else None,
        CSRF_COOKIE_NAME in request.cookies,
        list(request.cookies.keys()),
        extra={"correlation_id": get_correlation_id()},
    )

    if not submitted_token:
        logger.debug("CSRF validation failed: no submitted_token", extra={"correlation_id": get_correlation_id()})
        return False

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_cookie:
        logger.debug("CSRF validation failed: no csrf_cookie in request", extra={"correlation_id": get_correlation_id()})
        return False

    try:
        serializer = _get_csrf_serializer()
        stored_token = serializer.loads(
            csrf_cookie,
            salt="csrf-login",
            max_age=CSRF_MAX_AGE_SECONDS,
        )
        result = secrets.compare_digest(stored_token, submitted_token)
        logger.debug(
            "CSRF validation result: %s (stored=%s, submitted=%s)",
            result,
            stored_token[:20] + "..." if stored_token else None,
            submitted_token[:20] + "..." if submitted_token else None,
            extra={"correlation_id": get_correlation_id()},
        )
        return result
    except (SignatureExpired, BadSignature) as e:
        logger.debug("CSRF validation failed: %s", type(e).__name__, extra={"correlation_id": get_correlation_id()})
        return False


def get_csrf_token_from_cookie(request: Request) -> Optional[str]:
    """
    Retrieve existing CSRF token from cookie.

    Args:
        request: FastAPI Request object

    Returns:
        CSRF token if valid cookie exists, None otherwise
    """
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_cookie:
        return None

    try:
        serializer = _get_csrf_serializer()
        token = serializer.loads(
            csrf_cookie,
            salt="csrf-login",
            max_age=CSRF_MAX_AGE_SECONDS,
        )
        return token
    except (SignatureExpired, BadSignature):
        return None


# Old /admin/login routes removed - replaced by unified login at root level
# See login_router below for unified login implementation


@web_router.get("/logout")
async def logout(request: Request):
    """
    Logout and clear session.

    Redirects to unified login page after clearing session.
    """
    session_manager = get_session_manager()
    response = RedirectResponse(
        url="/login",
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
        # Not authenticated - redirect to unified login
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
async def dashboard_stats_partial(
    request: Request,
    time_filter: str = "24h",
    recent_filter: str = "30d",
):
    """
    Partial refresh endpoint for dashboard statistics section.

    Story #541 AC3/AC5: Support time filtering for job stats and recent activity.

    Args:
        request: HTTP request
        time_filter: Time filter for job stats ("24h", "7d", "30d")
        recent_filter: Time filter for recent activity ("24h", "7d", "30d")

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    dashboard_service = _get_dashboard_service()
    stats_data = dashboard_service.get_stats_partial(
        session.username, time_filter=time_filter, recent_filter=recent_filter
    )

    return templates.TemplateResponse(
        "partials/dashboard_stats.html",
        {
            "request": request,
            "job_counts": stats_data["job_counts"],
            "repo_counts": stats_data["repo_counts"],
            "recent_jobs": stats_data["recent_jobs"],
            "time_filter": time_filter,
            "recent_filter": recent_filter,
        },
    )


# Placeholder routes for other admin pages
# These will redirect to login if not authenticated


def _create_login_redirect(request: Request) -> RedirectResponse:
    """Create redirect to unified login with redirect_to parameter."""
    from urllib.parse import quote

    current_path = str(request.url.path)
    if request.url.query:
        current_path += f"?{request.url.query}"

    redirect_url = f"/login?redirect_to={quote(current_path)}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


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
                    "created_at": (
                        u.created_at.strftime("%Y-%m-%d %H:%M")
                        if u.created_at
                        else "N/A"
                    ),
                    "email": u.email,
                }
                for u in users
            ],
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token, path="/")
    return response


@web_router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    """Users management page - list all users with CRUD operations."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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


@web_router.post("/users/{username}/email", response_class=HTMLResponse)
async def update_user_email(
    request: Request,
    username: str,
    new_email: str = Form(""),
    csrf_token: Optional[str] = Form(None),
):
    """Update a user's email (admin only). Empty string clears the email."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_users_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Update email
    user_manager = dependencies.user_manager
    if not user_manager:
        return _create_users_page_response(
            request, session, error_message="User manager not available"
        )

    try:
        # Allow empty email to clear it
        email_value = new_email.strip() if new_email else None
        user_manager.update_user(
            username, new_email=email_value if email_value else None
        )

        return _create_users_page_response(
            request,
            session,
            success_message=f"Email for '{username}' updated successfully",
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
        return _create_login_redirect(request)

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

        # Clean up OIDC identity link if OIDC manager exists
        from ..auth.oidc import routes as oidc_routes

        if oidc_routes.oidc_manager:
            import aiosqlite

            async with aiosqlite.connect(oidc_routes.oidc_manager.db_path) as db:
                await db.execute(
                    "DELETE FROM oidc_identity_links WHERE username = ?", (username,)
                )
                await db.commit()

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
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie instead of generating new one
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        # Fallback: generate new token if cookie missing/invalid
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
                    "created_at": (
                        u.created_at.strftime("%Y-%m-%d %H:%M")
                        if u.created_at
                        else "N/A"
                    ),
                    "email": u.email,
                }
                for u in users
            ],
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


def _get_golden_repo_manager():
    """Get golden repository manager from app state."""
    from code_indexer.server import app as app_module

    manager = getattr(app_module.app.state, "golden_repo_manager", None)
    if manager is None:
        raise RuntimeError(
            "golden_repo_manager not initialized. "
            "Server must set app.state.golden_repo_manager during startup."
        )
    return manager


def _get_golden_repos_list():
    """Get list of all golden repositories with global alias, version, and index info."""
    try:
        import os
        import json
        from pathlib import Path

        manager = _get_golden_repo_manager()
        repos = manager.list_golden_repos()

        server_data_dir = os.environ.get(
            "CIDX_SERVER_DATA_DIR",
            os.path.expanduser("~/.cidx-server"),
        )
        golden_repos_dir = Path(server_data_dir) / "data" / "golden-repos"

        # Get global registry to check global activation status
        try:
            from code_indexer.global_repos.global_registry import GlobalRegistry

            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = {r["repo_name"]: r for r in registry.list_global_repos()}
        except Exception as e:
            logger.warning("Could not load global registry: %s", e, extra={"correlation_id": get_correlation_id()})
            global_repos = {}

        # Get alias info for version and target path
        aliases_dir = golden_repos_dir / "aliases"

        # Add status, global alias, version, and index information for display
        for repo in repos:
            # Default status to 'ready' if not set
            if "status" not in repo:
                repo["status"] = "ready"
            # Format last_indexed date if available
            if "created_at" in repo and repo["created_at"]:
                repo["last_indexed"] = repo["created_at"][:10]  # Just the date part
            else:
                repo["last_indexed"] = None

            # Add global alias info if globally activated
            alias = repo.get("alias", "")
            global_alias_name = f"{alias}-global"
            index_path = None
            version = None

            if alias in global_repos:
                repo["global_alias"] = global_repos[alias]["alias_name"]
                repo["globally_queryable"] = True

                # Read alias file to get actual target path and version
                alias_file = aliases_dir / f"{global_alias_name}.json"
                if alias_file.exists():
                    try:
                        with open(alias_file, "r") as f:
                            alias_data = json.load(f)
                        index_path = alias_data.get("target_path")
                        # Extract version from path (e.g., v_1764703630)
                        if index_path and ".versioned" in index_path:
                            version = Path(index_path).name
                        repo["version"] = version
                        repo["last_refresh"] = (
                            alias_data.get("last_refresh", "")[:19]
                            if alias_data.get("last_refresh")
                            else None
                        )
                    except Exception as e:
                        logger.warning(
                            "Could not read alias file %s: %s", alias_file, e,
                            extra={"correlation_id": get_correlation_id()},
                        )
                        repo["version"] = None
                        repo["last_refresh"] = None
                else:
                    repo["version"] = None
                    repo["last_refresh"] = None
            else:
                repo["global_alias"] = None
                repo["globally_queryable"] = False
                repo["version"] = None
                repo["last_refresh"] = None
                # Use clone_path for non-global repos
                index_path = repo.get("clone_path")

            # Fetch temporal status for globally activated repos
            if repo.get("global_alias"):
                try:
                    from code_indexer.server.services.dashboard_service import (
                        DashboardService,
                    )

                    dashboard = DashboardService()
                    temporal_status = dashboard.get_temporal_index_status(
                        username="_global", repo_alias=repo["global_alias"]
                    )
                    repo["temporal_status"] = temporal_status
                except Exception as e:
                    logger.warning(
                        "Failed to get temporal status for %s: %s",
                        repo.get("alias"),
                        e,
                        extra={"correlation_id": get_correlation_id()},
                    )
                    repo["temporal_status"] = {"format": "error", "message": str(e)}
            else:
                repo["temporal_status"] = {"format": "none"}

            # Check available indexes (factual check of filesystem)
            repo["has_semantic"] = False
            repo["has_fts"] = False
            repo["has_temporal"] = False
            repo["has_scip"] = False

            if index_path:
                index_base = Path(index_path) / ".code-indexer"
                if index_base.exists():
                    # Check semantic index (any model directory with hnsw_index.bin)
                    index_dir = index_base / "index"
                    if index_dir.exists():
                        for model_dir in index_dir.iterdir():
                            if (
                                model_dir.is_dir()
                                and (model_dir / "hnsw_index.bin").exists()
                            ):
                                repo["has_semantic"] = True
                                break

                    # Check FTS index (tantivy_index with files)
                    tantivy_dir = index_base / "tantivy_index"
                    if tantivy_dir.exists() and any(tantivy_dir.iterdir()):
                        repo["has_fts"] = True

                    # Check temporal index (code-indexer-temporal collection)
                    temporal_dir = (
                        index_dir / "code-indexer-temporal"
                        if index_dir.exists()
                        else None
                    )
                    if (
                        temporal_dir
                        and temporal_dir.exists()
                        and (temporal_dir / "hnsw_index.bin").exists()
                    ):
                        repo["has_temporal"] = True

                    # Check SCIP index (.code-indexer/scip/ with .scip.db files)
                    # CRITICAL: .scip protobuf files are DELETED after database conversion
                    # Only .scip.db (SQLite) files persist after 'cidx scip generate'
                    scip_dir = index_base / "scip"
                    if scip_dir.exists():
                        # Check for any .scip.db files in scip directory or subdirectories
                        scip_files = list(scip_dir.glob("**/*.scip.db"))
                        if scip_files:
                            repo["has_scip"] = True

        return repos
    except Exception as e:
        logger.error("Failed to get golden repos list: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
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
    users = _get_users_list()

    response = templates.TemplateResponse(
        "golden_repos.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "golden-repos",
            "show_nav": True,
            "csrf_token": csrf_token,
            "repos": repos,
            "users": [{"username": u.username} for u in users],
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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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


@web_router.post("/golden-repos/activate", response_class=HTMLResponse)
async def activate_golden_repo(
    request: Request,
    golden_alias: str = Form(...),
    username: str = Form(...),
    user_alias: str = Form(""),
    csrf_token: Optional[str] = Form(None),
):
    """Activate a golden repository for a user."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_golden_repos_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate inputs
    if not golden_alias or not golden_alias.strip():
        return _create_golden_repos_page_response(
            request, session, error_message="Golden repository alias is required"
        )

    if not username or not username.strip():
        return _create_golden_repos_page_response(
            request, session, error_message="Username is required"
        )

    # Use golden_alias as user_alias if not provided
    effective_user_alias = (
        user_alias.strip() if user_alias.strip() else golden_alias.strip()
    )

    # Try to activate the repository
    try:
        activated_manager = _get_activated_repo_manager()
        job_id = activated_manager.activate_repository(
            username=username.strip(),
            golden_repo_alias=golden_alias.strip(),
            user_alias=effective_user_alias,
        )
        return _create_golden_repos_page_response(
            request,
            session,
            success_message=f"Repository '{golden_alias}' activation for user '{username}' submitted (Job ID: {job_id})",
        )
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            error_msg = f"Golden repository '{golden_alias}' not found"
        elif "already" in error_msg.lower():
            error_msg = f"User '{username}' already has this repository activated"
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
        return _create_login_redirect(request)

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
        logger.error(
            "Failed to get golden repo details for '%s': %s", alias, e, exc_info=True,
            extra={"correlation_id": get_correlation_id()},
        )
        raise HTTPException(status_code=404, detail=f"Repository '{alias}' not found")


@web_router.get("/partials/golden-repos-list", response_class=HTMLResponse)
async def golden_repos_list_partial(request: Request):
    """
    Partial refresh endpoint for golden repos list section.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie instead of generating new one
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        # Fallback: generate new token if cookie missing/invalid
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
        List of activated repository dictionaries with username added and temporal_status
    """
    import os
    from ..services.dashboard_service import DashboardService

    try:
        manager = _get_activated_repo_manager()
        dashboard_service = DashboardService()
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

                    # Fetch temporal status for this repository
                    try:
                        temporal_status = dashboard_service.get_temporal_index_status(
                            username=username,
                            repo_alias=repo.get("user_alias", "")
                        )
                        repo["temporal_status"] = temporal_status
                    except Exception as e:
                        # Honest error handling - indicate failure clearly
                        logger.error(
                            "Failed to get temporal status for repo %s/%s: %s",
                            username,
                            repo.get("user_alias", "unknown"),
                            e,
                            exc_info=True,
                            extra={"correlation_id": get_correlation_id()},
                        )
                        # Provide error temporal_status with honest error format
                        repo["temporal_status"] = {
                            "error": str(e),
                            "format": "error",
                            "file_count": 0,
                            "needs_reindex": False,
                            "message": f"Unable to determine temporal index status: {str(e)}"
                        }

                    all_repos.append(repo)

        # Sort by activation date (newest first)
        all_repos.sort(key=lambda r: r.get("activated_at", ""), reverse=True)
        return all_repos

    except Exception as e:
        logger.error("Failed to get activated repos: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie instead of generating new one
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        # Fallback: generate new token if cookie missing/invalid
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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

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
        logger.error("Failed to get background job manager: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
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
                "status": (
                    job.status.value
                    if hasattr(job.status, "value")
                    else str(job.status)
                ),
                "progress": job.progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "error_message": job.error,
                "username": job.username,
                "user_alias": getattr(job, "user_alias", None),
                "repository_name": (
                    getattr(job.result, "alias", None)
                    if job.result and isinstance(job.result, dict)
                    else None
                ),
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
        return _create_login_redirect(request)

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
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie instead of generating new one
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        # Fallback: generate new token if cookie missing/invalid
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
        return _create_login_redirect(request)

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

    Returns list of repos with user_alias, username, and is_global flag.
    Includes both user-activated repos and globally activated repos.
    """
    import os
    from pathlib import Path

    repos = []

    # Add globally activated repos first
    try:
        server_data_dir = os.environ.get(
            "CIDX_SERVER_DATA_DIR",
            os.path.expanduser("~/.cidx-server"),
        )
        golden_repos_dir = Path(server_data_dir) / "data" / "golden-repos"

        from code_indexer.global_repos.global_registry import GlobalRegistry

        registry = GlobalRegistry(str(golden_repos_dir))
        global_repos = registry.list_global_repos()

        for global_repo in global_repos:
            repos.append(
                {
                    "user_alias": global_repo["alias_name"],
                    "username": "global",
                    "is_global": True,
                    "repo_name": global_repo.get("repo_name", ""),
                    "path": global_repo.get("index_path"),
                }
            )
    except Exception as e:
        logger.warning("Could not load global repos for query: %s", e, extra={"correlation_id": get_correlation_id()})

    # Add user-activated repos
    user_repos = _get_all_activated_repos()
    for repo in user_repos:
        repo["is_global"] = False
        repos.append(repo)

    return repos


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
    time_range_all: bool = False,
    time_range: str = "",
    at_commit: str = "",
    include_removed: bool = False,
    case_sensitive: bool = False,
    fuzzy: bool = False,
    regex: bool = False,
    scip_query_type: str = "definition",
    scip_exact: bool = False,
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
            "time_range_all": time_range_all,
            "time_range": time_range,
            "at_commit": at_commit,
            "include_removed": include_removed,
            "case_sensitive": case_sensitive,
            "fuzzy": fuzzy,
            "regex": regex,
            "scip_query_type": scip_query_type,
            "scip_exact": scip_exact,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    """Query testing interface page."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

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
    time_range_all: bool = Form(False),
    time_range: str = Form(""),
    at_commit: str = Form(""),
    include_removed: bool = Form(False),
    case_sensitive: bool = Form(False),
    fuzzy: bool = Form(False),
    regex: bool = Form(False),
    scip_query_type: str = Form("definition"),
    scip_exact: bool = Form(False),
):
    """Process query form submission."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

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
            time_range_all=time_range_all,
            time_range=time_range,
            at_commit=at_commit,
            include_removed=include_removed,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            regex=regex,
            scip_query_type=scip_query_type,
            scip_exact=scip_exact,
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
            time_range_all=time_range_all,
            time_range=time_range,
            at_commit=at_commit,
            include_removed=include_removed,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            regex=regex,
            scip_query_type=scip_query_type,
            scip_exact=scip_exact,
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
            time_range_all=time_range_all,
            time_range=time_range,
            at_commit=at_commit,
            include_removed=include_removed,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            regex=regex,
            scip_query_type=scip_query_type,
            scip_exact=scip_exact,
        )

    # Add to query history
    _add_to_query_history(session.username, query_text.strip(), repository, search_mode)

    # Handle temporal search mode - default to time_range_all if no specific temporal params
    if search_mode == "temporal":
        if not time_range and not at_commit and not time_range_all:
            time_range_all = True

    # Parse min_score
    parsed_min_score = None
    if min_score and min_score.strip():
        try:
            parsed_min_score = float(min_score)
        except ValueError:
            pass

    # Execute actual query
    results = []
    query_executed = True
    error_message = None

    try:
        # Handle SCIP query mode
        if search_mode == "scip":
            from code_indexer.scip.query.primitives import SCIPQueryEngine
            import glob

            # Find the username for this repository
            repo_parts = repository.split(" (")
            user_alias = repo_parts[0] if repo_parts else repository

            # Get the repository from all available repos
            all_repos = _get_all_activated_repos_for_query()
            target_repo = None
            for repo in all_repos:
                if repo.get("user_alias") == user_alias:
                    target_repo = repo
                    break

            if not target_repo:
                error_message = f"Repository '{user_alias}' not found"
            else:
                # Determine repository path
                repo_path = target_repo.get("path")

                # For global repos, resolve path from GlobalRegistry
                if not repo_path and target_repo.get("is_global"):
                    try:
                        import os
                        from code_indexer.global_repos.global_registry import (
                            GlobalRegistry,
                        )

                        server_data_dir = os.environ.get(
                            "CIDX_SERVER_DATA_DIR",
                            os.path.expanduser("~/.cidx-server"),
                        )
                        golden_repos_dir = (
                            Path(server_data_dir) / "data" / "golden-repos"
                        )
                        registry = GlobalRegistry(str(golden_repos_dir))
                        global_repo_meta = registry.get_global_repo(user_alias)
                        if global_repo_meta:
                            repo_path = global_repo_meta.get("index_path")
                    except Exception as e:
                        logger.warning(
                            f"Failed to resolve global repo path for '{user_alias}': {e}",
                            extra={"correlation_id": get_correlation_id()},
                        )

                if not repo_path:
                    error_message = f"Repository '{user_alias}' path not found"
                else:
                    # Find SCIP index files
                    scip_pattern = str(
                        Path(repo_path) / ".code-indexer" / "scip" / "**" / "*.scip"
                    )
                    scip_files = glob.glob(scip_pattern, recursive=True)

                    if not scip_files:
                        error_message = f"No SCIP index found for repository '{user_alias}'. Run 'cidx scip index' first."
                    else:
                        try:
                            # Execute query based on type
                            query_results = []
                            if scip_query_type == "impact":
                                from code_indexer.scip.query.composites import (
                                    analyze_impact,
                                )
                                from code_indexer.scip.query.primitives import (
                                    QueryResult,
                                )

                                scip_dir = Path(repo_path) / ".code-indexer" / "scip"
                                # Use depth=2 (lower than CLI default of 3) to balance coverage vs Web UI response time
                                impact_result = analyze_impact(
                                    query_text.strip(),
                                    scip_dir,
                                    depth=2,
                                    project=str(repo_path),
                                )
                                # Convert affected_symbols to QueryResult format
                                for affected in impact_result.affected_symbols:
                                    query_results.append(
                                        QueryResult(
                                            symbol=affected.symbol,
                                            project=str(repo_path),
                                            file_path=str(affected.file_path),
                                            line=affected.line,
                                            column=affected.column,
                                            kind="impact",
                                            relationship=affected.relationship,
                                            context=None,
                                        )
                                    )
                            elif scip_query_type == "callchain":
                                from code_indexer.scip.query.primitives import (
                                    QueryResult,
                                )

                                parts = query_text.strip().split(maxsplit=1)
                                if len(parts) != 2:
                                    raise ValueError(
                                        "Call chain requires two symbols: 'from_symbol to_symbol'"
                                    )
                                scip_file = Path(scip_files[0])
                                engine = SCIPQueryEngine(scip_file)
                                chains = engine.trace_call_chain(
                                    parts[0], parts[1], max_depth=5
                                )
                                for chain in chains:
                                    query_results.append(
                                        QueryResult(
                                            symbol=" -> ".join(chain.path),
                                            project=str(repo_path),
                                            file_path="(call chain)",
                                            line=0,
                                            column=0,
                                            kind="callchain",
                                            relationship=f"length={chain.length}",
                                            context=None,
                                        )
                                    )
                            elif scip_query_type == "context":
                                from code_indexer.scip.query.composites import (
                                    get_smart_context,
                                )
                                from code_indexer.scip.query.primitives import (
                                    QueryResult,
                                )

                                scip_dir = Path(repo_path) / ".code-indexer" / "scip"
                                context_result = get_smart_context(
                                    query_text.strip(),
                                    scip_dir,
                                    limit=limit,
                                    min_score=float(min_score) if min_score else 0.0,
                                    project=str(repo_path),
                                )
                                for ctx_file in context_result.files:
                                    query_results.append(
                                        QueryResult(
                                            symbol=query_text.strip(),
                                            project=str(repo_path),
                                            file_path=str(ctx_file.path),
                                            line=0,
                                            column=0,
                                            kind="context",
                                            relationship=f"score={ctx_file.relevance_score:.2f}, symbols={len(ctx_file.symbols)}",
                                            context=None,
                                        )
                                    )
                            else:
                                # For definition/references/dependencies/dependents, use engine
                                scip_file = Path(scip_files[0])
                                engine = SCIPQueryEngine(scip_file)

                                if scip_query_type == "definition":
                                    query_results = engine.find_definition(
                                        query_text.strip(), exact=scip_exact
                                    )
                                elif scip_query_type == "references":
                                    query_results = engine.find_references(
                                        query_text.strip(),
                                        limit=limit,
                                        exact=scip_exact,
                                    )
                                elif scip_query_type == "dependencies":
                                    query_results = engine.get_dependencies(
                                        query_text.strip(), exact=scip_exact
                                    )
                                elif scip_query_type == "dependents":
                                    query_results = engine.get_dependents(
                                        query_text.strip(), exact=scip_exact
                                    )

                            # Format results for template
                            for result in query_results:
                                results.append(
                                    {
                                        "file_path": result.file_path,
                                        "line_numbers": str(result.line),
                                        "content": f"{result.kind}: {result.symbol}",
                                        "score": 1.0,  # SCIP results don't have similarity scores
                                        "language": _detect_language_from_path(
                                            result.file_path
                                        ),
                                        "repository_alias": user_alias,
                                        "scip_symbol": result.symbol,
                                        "scip_kind": result.kind,
                                    }
                                )
                        except FileNotFoundError as e:
                            logger.error(
                                "SCIP query failed - file not found: %s",
                                e,
                                exc_info=True,
                                extra={"correlation_id": get_correlation_id()},
                            )
                            error_message = f"SCIP index not found or corrupted for repository '{user_alias}'. Generate an index with: `cidx scip generate`"
                        except Exception as e:
                            logger.error(
                                "SCIP query execution failed: %s", e, exc_info=True,
                                extra={"correlation_id": get_correlation_id()},
                            )
                            error_message = f"SCIP query failed for repository '{user_alias}': {str(e)}. Try regenerating the index with: `cidx scip generate`"

        else:
            # Handle semantic/FTS/temporal queries
            query_manager = _get_semantic_query_manager()
            if not query_manager:
                error_message = "Query service not available"
            else:
                # Find the username for this repository
                # Repository format is "user_alias (username)"
                repo_parts = repository.split(" (")
                user_alias = repo_parts[0] if repo_parts else repository

            # Get the repository from all available repos (including global)
            all_repos = _get_all_activated_repos_for_query()
            target_repo = None
            for repo in all_repos:
                if repo.get("user_alias") == user_alias:
                    target_repo = repo
                    break

            if not target_repo:
                error_message = f"Repository '{user_alias}' not found"
            elif target_repo.get("is_global"):
                # Handle global repository query
                import os
                from code_indexer.global_repos.alias_manager import AliasManager
                from ..services.search_service import (
                    SemanticSearchService,
                    SemanticSearchRequest,
                )

                server_data_dir = os.environ.get(
                    "CIDX_SERVER_DATA_DIR",
                    os.path.expanduser("~/.cidx-server"),
                )
                aliases_dir = (
                    Path(server_data_dir) / "data" / "golden-repos" / "aliases"
                )
                alias_manager = AliasManager(str(aliases_dir))

                # Resolve alias to target path
                target_path = alias_manager.read_alias(user_alias)
                if not target_path:
                    error_message = f"Global repository '{user_alias}' alias not found"
                else:
                    # Use SemanticSearchService for direct path query
                    search_service = SemanticSearchService()
                    search_request = SemanticSearchRequest(
                        query=query_text.strip(),
                        limit=limit,
                        include_source=True,
                    )

                    try:
                        search_response = search_service.search_repository_path(
                            target_path, search_request
                        )

                        # Convert results to template format
                        for result in search_response.results:
                            results.append(
                                {
                                    "file_path": result.file_path,
                                    "line_numbers": str(result.line_start or 1),
                                    "content": result.content or "",
                                    "score": result.score,
                                    "language": _detect_language_from_path(
                                        result.file_path
                                    ),
                                }
                            )
                    except Exception as e:
                        logger.error("Global repo query failed: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
                        error_message = f"Query failed: {str(e)}"
            else:
                repo_username = target_repo.get("username", session.username)

                # Execute query for user-activated repositories
                query_response = query_manager.query_user_repositories(
                    username=repo_username,
                    query_text=query_text.strip(),
                    repository_alias=user_alias,
                    limit=limit,
                    min_score=parsed_min_score,
                    language=language if language else None,
                    path_filter=path_pattern if path_pattern else None,
                    search_mode=search_mode,
                    time_range=time_range if time_range else None,
                    time_range_all=time_range_all,
                    at_commit=at_commit if at_commit else None,
                    include_removed=include_removed,
                    case_sensitive=case_sensitive,
                    fuzzy=fuzzy,
                    regex=regex,
                )

                # Convert results to template format with full metadata
                for result in query_response.get("results", []):
                    results.append(
                        {
                            "file_path": result.get("file_path", ""),
                            "line_numbers": f"{result.get('line_number', 1)}",
                            "content": result.get("code_snippet", ""),
                            "score": result.get("similarity_score", 0.0),
                            "language": _detect_language_from_path(
                                result.get("file_path", "")
                            ),
                            "repository_alias": result.get("repository_alias", ""),
                            "source_repo": result.get("source_repo"),
                            "metadata": result.get("metadata"),
                            "temporal_context": result.get("temporal_context"),
                        }
                    )

    except Exception as e:
        logger.error("Query execution failed: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
        error_message = f"Query failed: {str(e)}"

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
        results=results if not error_message else None,
        query_executed=query_executed,
        error_message=error_message,
        time_range_all=time_range_all,
        time_range=time_range,
        at_commit=at_commit,
        include_removed=include_removed,
        case_sensitive=case_sensitive,
        fuzzy=fuzzy,
        regex=regex,
        scip_query_type=scip_query_type,
        scip_exact=scip_exact,
    )


@web_router.get("/partials/query-results", response_class=HTMLResponse)
async def query_results_partial(request: Request):
    """
    Partial refresh endpoint for query results.

    Returns HTML fragment for htmx partial updates.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

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


def _get_semantic_query_manager():
    """Get the semantic query manager instance."""
    try:
        from ..app import semantic_query_manager

        return semantic_query_manager
    except Exception as e:
        logger.error("Failed to get semantic query manager: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
        return None


def _execute_scip_query(
    target_repo: dict,
    user_alias: str,
    query_text: str,
    scip_query_type: str,
    scip_exact: bool,
    limit: int,
    min_score: str,
) -> tuple[list, Optional[str]]:
    """
    Execute SCIP query for repository. Supports all 7 SCIP query types.

    Returns tuple of (results_list, error_message).
    """
    from code_indexer.scip.query.primitives import SCIPQueryEngine, QueryResult
    import glob

    results = []
    repo_path = target_repo.get("path")

    # For global repos, resolve path from GlobalRegistry
    if not repo_path and target_repo.get("is_global"):
        try:
            from code_indexer.global_repos.global_registry import GlobalRegistry
            import os

            server_data_dir = os.environ.get(
                "CIDX_SERVER_DATA_DIR",
                os.path.expanduser("~/.cidx-server"),
            )
            golden_repos_dir = Path(server_data_dir) / "data" / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repo_meta = registry.get_global_repo(user_alias)
            if global_repo_meta:
                repo_path = global_repo_meta.get("index_path")
        except Exception as e:
            logger.warning(
                f"Failed to resolve global repo path for '{user_alias}': {e}",
                extra={"correlation_id": get_correlation_id()},
            )

    if not repo_path:
        return results, f"Repository '{user_alias}' path not found"

    scip_pattern = str(Path(repo_path) / ".code-indexer" / "scip" / "**" / "*.scip")
    scip_files = glob.glob(scip_pattern, recursive=True)
    if not scip_files:
        return (
            results,
            f"No SCIP index found for repository '{user_alias}'. Run 'cidx scip index' first.",
        )

    try:
        query_results = []
        scip_dir = Path(repo_path) / ".code-indexer" / "scip"

        if scip_query_type == "impact":
            from code_indexer.scip.query.composites import analyze_impact

            res = analyze_impact(
                query_text.strip(), scip_dir, depth=2, project=str(repo_path)
            )
            query_results = [
                QueryResult(
                    symbol=a.symbol,
                    project=str(repo_path),
                    file_path=str(a.file_path),
                    line=a.line,
                    column=a.column,
                    kind="impact",
                    relationship=a.relationship,
                    context=None,
                )
                for a in res.affected_symbols
            ]
        elif scip_query_type == "callchain":
            parts = query_text.strip().split(maxsplit=1)
            if len(parts) != 2:
                raise ValueError(
                    "Call chain requires two symbols: 'from_symbol to_symbol'"
                )
            engine = SCIPQueryEngine(Path(scip_files[0]))
            chains = engine.trace_call_chain(parts[0], parts[1], max_depth=5)
            query_results = [
                QueryResult(
                    symbol=" -> ".join(c.path),
                    project=str(repo_path),
                    file_path="(call chain)",
                    line=0,
                    column=0,
                    kind="callchain",
                    relationship=f"length={c.length}",
                    context=None,
                )
                for c in chains
            ]
        elif scip_query_type == "context":
            from code_indexer.scip.query.composites import get_smart_context

            res = get_smart_context(
                query_text.strip(),
                scip_dir,
                limit=limit,
                min_score=float(min_score) if min_score else 0.0,
                project=str(repo_path),
            )
            query_results = [
                QueryResult(
                    symbol=query_text.strip(),
                    project=str(repo_path),
                    file_path=str(f.path),
                    line=0,
                    column=0,
                    kind="context",
                    relationship=f"score={f.relevance_score:.2f}, symbols={len(f.symbols)}",
                    context=None,
                )
                for f in res.files
            ]
        else:
            engine = SCIPQueryEngine(Path(scip_files[0]))
            if scip_query_type == "definition":
                query_results = engine.find_definition(
                    query_text.strip(), exact=scip_exact
                )
            elif scip_query_type == "references":
                query_results = engine.find_references(
                    query_text.strip(), limit=limit, exact=scip_exact
                )
            elif scip_query_type == "dependencies":
                query_results = engine.get_dependencies(
                    query_text.strip(), exact=scip_exact
                )
            elif scip_query_type == "dependents":
                query_results = engine.get_dependents(
                    query_text.strip(), exact=scip_exact
                )

        # Format results for template
        for result in query_results:
            results.append(
                {
                    "file_path": result.file_path,
                    "line_numbers": str(result.line),
                    "content": f"{result.kind}: {result.symbol}",
                    "score": 1.0,  # SCIP results don't have similarity scores
                    "language": _detect_language_from_path(result.file_path),
                    "repository_alias": user_alias,
                    "scip_symbol": result.symbol,
                    "scip_kind": result.kind,
                }
            )
    except FileNotFoundError as e:
        logger.error("SCIP query failed - file not found: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
        return (
            results,
            f"SCIP index not found or corrupted for repository '{user_alias}'. Generate an index with: `cidx scip generate`",
        )
    except Exception as e:
        logger.error("SCIP query execution failed: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
        return (
            results,
            f"SCIP query failed for repository '{user_alias}': {str(e)}. Try regenerating the index with: `cidx scip generate`",
        )

    return results, None


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
    time_range_all: bool = Form(False),
    time_range: str = Form(""),
    at_commit: str = Form(""),
    include_removed: bool = Form(False),
    case_sensitive: bool = Form(False),
    fuzzy: bool = Form(False),
    regex: bool = Form(False),
    scip_query_type: str = Form("definition"),
    scip_exact: bool = Form(False),
):
    """
    Execute query and return results partial via htmx.

    Returns HTML fragment for htmx partial updates.

    Note: CSRF validation is intentionally not performed for this endpoint because:
    1. Session authentication already protects against unauthorized access
    2. HTMX requests are same-origin (browser enforces this)
    3. HTMX adds specific headers (HX-Request) that indicate the request origin
    4. The main form submission route (/admin/query) retains CSRF protection
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Note: csrf_token parameter is accepted but not validated for HTMX partials
    # See docstring above for security rationale

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

    if not repository:
        return templates.TemplateResponse(
            "partials/query_results.html",
            {
                "request": request,
                "results": None,
                "query_executed": False,
                "query_text": query_text,
                "error_message": "Please select a repository",
            },
        )

    # Add to query history
    _add_to_query_history(session.username, query_text.strip(), repository, search_mode)

    # Handle temporal search mode - default to time_range_all if no specific temporal params
    if search_mode == "temporal":
        if not time_range and not at_commit and not time_range_all:
            time_range_all = True

    # Parse min_score
    parsed_min_score = None
    if min_score and min_score.strip():
        try:
            parsed_min_score = float(min_score)
        except ValueError:
            pass

    # Execute actual query
    results = []
    query_executed = True
    error_message = None

    try:
        query_manager = _get_semantic_query_manager()
        if not query_manager:
            error_message = "Query service not available"
        else:
            # Find the username for this repository
            # Repository format is "user_alias (username)"
            repo_parts = repository.split(" (")
            user_alias = repo_parts[0] if repo_parts else repository

            # Get the repository owner from activated repos
            all_repos = _get_all_activated_repos_for_query()
            target_repo = None
            for repo in all_repos:
                if repo.get("user_alias") == user_alias:
                    target_repo = repo
                    break

            if not target_repo:
                error_message = f"Repository '{user_alias}' not found"
            elif search_mode == "scip":
                # Execute SCIP query using helper function
                scip_results, scip_error = _execute_scip_query(
                    target_repo,
                    user_alias,
                    query_text,
                    scip_query_type,
                    scip_exact,
                    limit,
                    min_score,
                )
                results.extend(scip_results)
                if scip_error:
                    error_message = scip_error
            elif target_repo.get("is_global"):
                # Handle global repository query
                import os
                from code_indexer.global_repos.alias_manager import AliasManager
                from ..services.search_service import (
                    SemanticSearchService,
                    SemanticSearchRequest,
                )

                server_data_dir = os.environ.get(
                    "CIDX_SERVER_DATA_DIR",
                    os.path.expanduser("~/.cidx-server"),
                )
                aliases_dir = (
                    Path(server_data_dir) / "data" / "golden-repos" / "aliases"
                )
                alias_manager = AliasManager(str(aliases_dir))

                # Resolve alias to target path
                target_path = alias_manager.read_alias(user_alias)
                if not target_path:
                    error_message = f"Global repository '{user_alias}' alias not found"
                else:
                    # Use SemanticSearchService for direct path query
                    search_service = SemanticSearchService()
                    search_request = SemanticSearchRequest(
                        query=query_text.strip(),
                        limit=limit,
                        include_source=True,
                    )

                    try:
                        search_response = search_service.search_repository_path(
                            target_path, search_request
                        )

                        # Convert results to template format
                        for result in search_response.results:
                            results.append(
                                {
                                    "file_path": result.file_path,
                                    "line_numbers": str(result.line_start or 1),
                                    "content": result.content or "",
                                    "score": result.score,
                                    "language": _detect_language_from_path(
                                        result.file_path
                                    ),
                                }
                            )
                    except Exception as e:
                        logger.error("Global repo query failed: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
                        error_message = f"Query failed: {str(e)}"
            else:
                # Execute query for user-activated repositories
                repo_username = target_repo.get("username", session.username)

                query_response = query_manager.query_user_repositories(
                    username=repo_username,
                    query_text=query_text.strip(),
                    repository_alias=user_alias,
                    limit=limit,
                    min_score=parsed_min_score,
                    language=language if language else None,
                    path_filter=path_pattern if path_pattern else None,
                    search_mode=search_mode,
                    time_range=time_range if time_range else None,
                    time_range_all=time_range_all,
                    at_commit=at_commit if at_commit else None,
                    include_removed=include_removed,
                    case_sensitive=case_sensitive,
                    fuzzy=fuzzy,
                    regex=regex,
                )

                # Convert results to template format with full metadata
                for result in query_response.get("results", []):
                    results.append(
                        {
                            "file_path": result.get("file_path", ""),
                            "line_numbers": f"{result.get('line_number', 1)}",
                            "content": result.get("code_snippet", ""),
                            "score": result.get("similarity_score", 0.0),
                            "language": _detect_language_from_path(
                                result.get("file_path", "")
                            ),
                            "repository_alias": result.get("repository_alias", ""),
                            "source_repo": result.get("source_repo"),
                            "metadata": result.get("metadata"),
                            "temporal_context": result.get("temporal_context"),
                        }
                    )

    except Exception as e:
        logger.error("Query execution failed: %s", e, exc_info=True, extra={"correlation_id": get_correlation_id()})
        error_message = f"Query failed: {str(e)}"

    csrf_token_new = generate_csrf_token()
    response = templates.TemplateResponse(
        "partials/query_results.html",
        {
            "request": request,
            "results": results if not error_message else None,
            "query_executed": query_executed,
            "query_text": query_text,
            "error_message": error_message,
            "search_mode": search_mode,
        },
    )

    set_csrf_cookie(response, csrf_token_new)
    return response


def _detect_language_from_path(file_path: str) -> str:
    """Detect programming language from file path extension."""
    ext_to_lang = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
        ".sh": "bash",
        ".bash": "bash",
    }
    from pathlib import Path

    ext = Path(file_path).suffix.lower()
    return ext_to_lang.get(ext, "plaintext")


async def _reload_oidc_configuration():
    """Reload OIDC configuration without server restart."""
    from ..auth.oidc import routes as oidc_routes
    from ..auth.oidc.oidc_manager import OIDCManager
    from ..auth.oidc.state_manager import StateManager
    from ..services.config_service import get_config_service

    config_service = get_config_service()
    config = config_service.get_config()

    # Only reload if OIDC is enabled
    if not config.oidc_provider_config.enabled:
        logger.info("OIDC is disabled, skipping reload", extra={"correlation_id": get_correlation_id()})
        # Clear the existing OIDC manager
        oidc_routes.oidc_manager = None
        oidc_routes.state_manager = None
        return

    # Create new OIDC manager with updated configuration
    # Reuse existing user_manager and jwt_manager from module level
    from .. import app as app_module

    logger.info(
        f"Creating new OIDC manager with config: email_claim={config.oidc_provider_config.email_claim}, username_claim={config.oidc_provider_config.username_claim}",
        extra={"correlation_id": get_correlation_id()},
    )

    state_manager = StateManager()
    oidc_manager = OIDCManager(
        config=config.oidc_provider_config,
        user_manager=app_module.user_manager,
        jwt_manager=app_module.jwt_manager,
    )

    # Initialize OIDC database schema (no network calls)
    # Provider metadata will be discovered lazily on next SSO login attempt
    await oidc_manager.initialize()

    # Replace the old managers with new ones
    oidc_routes.oidc_manager = oidc_manager
    oidc_routes.state_manager = state_manager
    oidc_routes.server_config = config

    logger.info(
        f"OIDC configuration reloaded for provider: {config.oidc_provider_config.provider_name} (will initialize on next login)",
        extra={"correlation_id": get_correlation_id()},
    )
    logger.info(
        f"New OIDC manager config - email_claim: {oidc_manager.config.email_claim}, username_claim: {oidc_manager.config.username_claim}",
        extra={"correlation_id": get_correlation_id()},
    )


def _get_current_config() -> dict:
    """Get current configuration from ConfigService (persisted to ~/.cidx-server/config.json)."""
    from ..services.config_service import get_config_service
    from ..utils.config_manager import OIDCProviderConfig
    from dataclasses import asdict

    config_service = get_config_service()
    settings = config_service.get_all_settings()

    # Ensure OIDC config has all required fields with defaults
    oidc_config = settings.get("oidc")
    if not oidc_config:
        # Provide defaults if OIDC config is missing
        oidc_config = asdict(OIDCProviderConfig())

    # Convert to template-friendly format
    return {
        "server": settings["server"],
        "cache": settings["cache"],
        "reindexing": settings["reindexing"],
        "timeouts": settings["timeouts"],
        "password_security": settings["password_security"],
        "oidc": oidc_config,
    }


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

        # Validate log_level - must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_level = data.get("log_level")
        if log_level is not None:
            valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if log_level.upper() not in valid_log_levels:
                return f"Log level must be one of: {', '.join(valid_log_levels)}"

        jwt_expiration = data.get("jwt_expiration_minutes")
        if jwt_expiration is not None:
            try:
                jwt_int = int(jwt_expiration)
                if jwt_int < 1:
                    return "JWT expiration must be a positive number"
            except (ValueError, TypeError):
                return "JWT expiration must be a valid number"

    elif section == "cache":
        # Validate cache TTL values
        for field in ["index_cache_ttl_minutes", "fts_cache_ttl_minutes"]:
            value = data.get(field)
            if value is not None:
                try:
                    val_float = float(value)
                    if val_float <= 0:
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
                    return f"{field_name} must be a valid number"

        # Validate cleanup intervals
        for field in ["index_cache_cleanup_interval", "fts_cache_cleanup_interval"]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 1:
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
                    return f"{field_name} must be a valid number"

    elif section == "reindexing":
        # Validate thresholds (0-100 for percentage, 0-1 for accuracy)
        change_threshold = data.get("change_percentage_threshold")
        if change_threshold is not None:
            try:
                val = float(change_threshold)
                if val < 0 or val > 100:
                    return "Change percentage threshold must be between 0 and 100"
            except (ValueError, TypeError):
                return "Change percentage threshold must be a valid number"

        accuracy = data.get("accuracy_threshold")
        if accuracy is not None:
            try:
                val = float(accuracy)
                if val < 0 or val > 1:
                    return "Accuracy threshold must be between 0 and 1"
            except (ValueError, TypeError):
                return "Accuracy threshold must be a valid number"

        # Validate positive integers
        for field in [
            "max_index_age_days",
            "batch_size",
            "max_analysis_time_seconds",
            "max_memory_usage_mb",
        ]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 1:
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
                    return f"{field_name} must be a valid number"

    elif section == "timeouts":
        # Validate timeout values (must be positive integers)
        for field in [
            "git_clone_timeout",
            "git_pull_timeout",
            "git_refresh_timeout",
            "cidx_index_timeout",
        ]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 1:
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
                    return f"{field_name} must be a valid number"

    elif section == "password_security":
        # Validate password length settings
        min_length = data.get("min_length")
        max_length = data.get("max_length")

        if min_length is not None:
            try:
                min_int = int(min_length)
                if min_int < 1:
                    return "Minimum password length must be at least 1"
            except (ValueError, TypeError):
                return "Minimum password length must be a valid number"

        if max_length is not None:
            try:
                max_int = int(max_length)
                if max_int < 1:
                    return "Maximum password length must be at least 1"
            except (ValueError, TypeError):
                return "Maximum password length must be a valid number"

        # Validate required char classes (1-4)
        char_classes = data.get("required_char_classes")
        if char_classes is not None:
            try:
                cc_int = int(char_classes)
                if cc_int < 1 or cc_int > 4:
                    return "Required character classes must be between 1 and 4"
            except (ValueError, TypeError):
                return "Required character classes must be a valid number"

    # Old sections kept for backwards compatibility during transition
    elif section == "indexing":
        batch_size = data.get("batch_size")
        if batch_size is not None:
            try:
                batch_int = int(batch_size)
                if batch_int < 1:
                    return "Batch size must be a positive number"
            except (ValueError, TypeError):
                return "Batch size must be a valid number"

    elif section == "query":
        for field in ["default_limit", "max_limit", "timeout"]:
            value = data.get(field)
            if value is not None:
                try:
                    val_int = int(value)
                    if val_int < 1:
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be a positive number"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
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
                        field_name = field.replace("_", " ").title()
                        return f"{field_name} must be at least 60 seconds"
                except (ValueError, TypeError):
                    field_name = field.replace("_", " ").title()
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

    # Load API keys status - use same server_dir as config service
    from ..services.config_service import get_config_service
    config_service = get_config_service()
    server_dir = str(config_service.config_manager.server_dir)

    token_manager = CITokenManager(server_dir_path=server_dir)
    api_keys_status = token_manager.list_tokens()

    # Get token data for masking in template
    github_token_data = token_manager.get_token('github')
    gitlab_token_data = token_manager.get_token('gitlab')

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
            "api_keys_status": api_keys_status,
            "github_token_data": github_token_data,
            "gitlab_token_data": gitlab_token_data,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration management page - view and edit CIDX configuration."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    return _create_config_page_response(request, session)


@web_router.post("/config/{section}", response_class=HTMLResponse)
async def update_config_section(
    request: Request,
    section: str,
    csrf_token: Optional[str] = Form(None),
):
    """Update configuration for a specific section."""
    from ..services.config_service import get_config_service

    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_config_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate section
    valid_sections = [
        "server",
        "cache",
        "reindexing",
        "timeouts",
        "password_security",
        "oidc",
    ]
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

    # Save configuration using ConfigService
    try:
        config_service = get_config_service()

        # Update all settings without validating (batch update)
        for key, value in data.items():
            config_service.update_setting(section, key, value, skip_validation=True)

        # Validate configuration
        config = config_service.get_config()
        config_service.config_manager.validate_config(config)

        # For OIDC: test reload BEFORE saving to file
        if section == "oidc":
            try:
                # Try to reload with new config (don't save yet)
                await _reload_oidc_configuration()
                logger.info("OIDC configuration validated and reloaded successfully", extra={"correlation_id": get_correlation_id()})
            except Exception as e:
                # Reload failed - reload original config from file to restore working state
                logger.error(f"Failed to reload OIDC configuration: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
                config_service.load_config()  # Reload from file to undo in-memory changes
                return _create_config_page_response(
                    request,
                    session,
                    error_message=f"Invalid OIDC configuration: {str(e)}. Changes not saved.",
                )

        # Only save to file after validation and OIDC test (if applicable)
        config_service.config_manager.save_config(config)
        logger.info(f"Saved {section} configuration with {len(data)} settings", extra={"correlation_id": get_correlation_id()})

        return _create_config_page_response(
            request,
            session,
            success_message=f"{section.title()} configuration saved successfully",
        )
    except ValueError as e:
        return _create_config_page_response(
            request,
            session,
            error_message=f"Failed to save configuration: {str(e)}",
        )
    except Exception as e:
        logger.error("Failed to save config section %s: %s", section, e, extra={"correlation_id": get_correlation_id()})
        return _create_config_page_response(
            request,
            session,
            error_message=f"Failed to save configuration: {str(e)}",
        )


@web_router.post("/config/reset", response_class=HTMLResponse)
async def reset_config(
    request: Request,
    csrf_token: Optional[str] = Form(None),
):
    """Reset configuration to defaults."""
    from ..services.config_service import get_config_service

    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_config_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Reset to defaults using ConfigService
    try:
        config_service = get_config_service()
        # Create a fresh default config and save it
        default_config = config_service.config_manager.create_default_config()
        config_service.config_manager.save_config(default_config)
        config_service._config = default_config  # Update cached config

        return _create_config_page_response(
            request,
            session,
            success_message="Configuration reset to defaults successfully",
        )
    except Exception as e:
        logger.error("Failed to reset config: %s", e, extra={"correlation_id": get_correlation_id()})
        return _create_config_page_response(
            request,
            session,
            error_message=f"Failed to reset configuration: {str(e)}",
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
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie instead of generating new one
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        # Fallback: generate new token if cookie missing/invalid
        csrf_token = generate_csrf_token()
    config = _get_current_config()

    # Load API keys status - use same server_dir as config service
    from ..services.config_service import get_config_service
    config_service = get_config_service()
    server_dir = str(config_service.config_manager.server_dir)

    token_manager = CITokenManager(server_dir_path=server_dir)
    api_keys_status = token_manager.list_tokens()
    github_token_data = token_manager.get_token('github')
    gitlab_token_data = token_manager.get_token('gitlab')

    response = templates.TemplateResponse(
        "partials/config_section.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "config": config,
            "validation_errors": {},
            "api_keys_status": api_keys_status,
            "github_token_data": github_token_data,
            "gitlab_token_data": gitlab_token_data,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


# =============================================================================
# API Keys Management
# =============================================================================


@web_router.post("/config/api-keys/{platform}", response_class=HTMLResponse)
async def save_api_key(
    request: Request,
    platform: str,
    csrf_token: Optional[str] = Form(None),
    token: str = Form(...),
    api_url: Optional[str] = Form(None),
):
    """Save API key for CI/CD platform (GitHub or GitLab)."""
    # Require admin authentication
    session = _require_admin_session(request)
    if not session:
        return RedirectResponse(
            url="/user/login", status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_config_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate platform
    if platform not in ['github', 'gitlab']:
        return _create_config_page_response(
            request, session, error_message=f"Invalid platform: {platform}"
        )

    # Save token using CITokenManager - use same server_dir as config service
    try:
        from ..services.config_service import get_config_service
        config_service = get_config_service()
        server_dir = str(config_service.config_manager.server_dir)

        token_manager = CITokenManager(server_dir_path=server_dir)
        token_manager.save_token(platform, token, base_url=api_url)

        platform_name = "GitHub" if platform == 'github' else "GitLab"
        return _create_config_page_response(
            request,
            session,
            success_message=f"{platform_name} API key saved successfully",
        )
    except TokenValidationError as e:
        return _create_config_page_response(
            request,
            session,
            error_message=f"Invalid token format: {str(e)}",
            validation_errors={'api_keys': str(e)},
        )
    except Exception as e:
        logger.error("Failed to save %s API key: %s", platform, e, extra={"correlation_id": get_correlation_id()})
        return _create_config_page_response(
            request,
            session,
            error_message=f"Failed to save API key: {str(e)}",
        )


@web_router.delete("/config/api-keys/{platform}", response_class=HTMLResponse)
async def delete_api_key(
    request: Request,
    platform: str,
):
    """Delete API key for CI/CD platform."""
    # Require admin authentication
    session = _require_admin_session(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    # Validate CSRF token from header (HTMX sends it as X-CSRF-Token)
    csrf_from_header = request.headers.get('X-CSRF-Token')
    if not validate_login_csrf_token(request, csrf_from_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )

    # Validate platform
    if platform not in ['github', 'gitlab']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform: {platform}"
        )

    # Delete token using CITokenManager - use same server_dir as config service
    try:
        from ..services.config_service import get_config_service
        config_service = get_config_service()
        server_dir = str(config_service.config_manager.server_dir)

        token_manager = CITokenManager(server_dir_path=server_dir)
        token_manager.delete_token(platform)

        platform_name = "GitHub" if platform == 'github' else "GitLab"
        logger.info(f"{platform_name} API key deleted successfully", extra={"correlation_id": get_correlation_id()})

        # Return success HTML fragment (HTMX expects HTML response)
        return HTMLResponse(
            content=f'<div class="alert success">{platform_name} API key deleted</div>',
            status_code=200
        )
    except Exception as e:
        logger.error("Failed to delete %s API key: %s", platform, e, extra={"correlation_id": get_correlation_id()})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


# =============================================================================
# Git Settings
# =============================================================================


@web_router.get("/settings/git", response_class=HTMLResponse)
async def git_settings_page(request: Request):
    """
    Git settings page - view and edit git service configuration.

    Admin-only page for configuring git committer settings.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    from code_indexer.config import ConfigManager

    # Get current configuration
    config_manager = ConfigManager()
    config = config_manager.load()
    git_config = config.git_service

    # Generate CSRF token
    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        request,
        "git_settings.html",
        {
            "username": session.username,
            "current_page": "git-settings",
            "show_nav": True,
            "csrf_token": csrf_token,
            "config": git_config,
        },
    )

    # Set CSRF cookie
    set_csrf_cookie(response, csrf_token)

    return response


# =============================================================================
# File Content Limits Settings
# =============================================================================


@web_router.get("/settings/file-content-limits", response_class=HTMLResponse)
async def file_content_limits_page(request: Request):
    """
    File content limits settings page - view and edit token limits configuration.

    Admin-only page for configuring file content token limits.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    from ..services.file_content_limits_config_manager import (
        FileContentLimitsConfigManager,
    )

    # Get current configuration
    config_manager = FileContentLimitsConfigManager.get_instance()
    config = config_manager.get_config()

    # Generate CSRF token
    csrf_token = generate_csrf_token()

    # Calculate derived values
    max_chars = config.max_chars_per_request
    estimated_lines = max_chars // 80  # Typical code line length

    response = templates.TemplateResponse(
        "file_content_limits.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "file-content-limits",
            "show_nav": True,
            "csrf_token": csrf_token,
            "config": config,
            "max_chars": max_chars,
            "estimated_lines": estimated_lines,
            "success_message": None,
            "error_message": None,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.post("/settings/file-content-limits", response_class=HTMLResponse)
async def update_file_content_limits(
    request: Request,
    max_tokens_per_request: int = Form(...),
    chars_per_token: int = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """
    Update file content limits configuration.

    Validates input and persists changes to database.
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_file_content_limits_response(
            request, session, error_message="Invalid CSRF token"
        )

    # Validate max_tokens_per_request range
    if max_tokens_per_request < 1000 or max_tokens_per_request > 20000:
        return _create_file_content_limits_response(
            request,
            session,
            error_message="Max tokens per request must be between 1000 and 20000",
        )

    # Validate chars_per_token range
    if chars_per_token < 3 or chars_per_token > 5:
        return _create_file_content_limits_response(
            request,
            session,
            error_message="Chars per token must be between 3 and 5",
        )

    # Update configuration
    try:
        from ..models.file_content_limits_config import FileContentLimitsConfig
        from ..services.file_content_limits_config_manager import (
            FileContentLimitsConfigManager,
        )

        new_config = FileContentLimitsConfig(
            max_tokens_per_request=max_tokens_per_request,
            chars_per_token=chars_per_token,
        )

        config_manager = FileContentLimitsConfigManager.get_instance()
        config_manager.update_config(new_config)

        return _create_file_content_limits_response(
            request,
            session,
            success_message="File content limits updated successfully",
        )
    except Exception as e:
        logger.error("Failed to update file content limits: %s", e, extra={"correlation_id": get_correlation_id()})
        return _create_file_content_limits_response(
            request,
            session,
            error_message=f"Failed to update configuration: {str(e)}",
        )


def _create_file_content_limits_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create file content limits page response with messages."""
    from ..services.file_content_limits_config_manager import (
        FileContentLimitsConfigManager,
    )

    config_manager = FileContentLimitsConfigManager.get_instance()
    config = config_manager.get_config()

    csrf_token = generate_csrf_token()

    # Calculate derived values
    max_chars = config.max_chars_per_request
    estimated_lines = max_chars // 80

    response = templates.TemplateResponse(
        "file_content_limits.html",
        {
            "request": request,
            "username": session.username,
            "current_page": "file-content-limits",
            "show_nav": True,
            "csrf_token": csrf_token,
            "config": config,
            "max_chars": max_chars,
            "estimated_lines": estimated_lines,
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


# =============================================================================
# API Keys Management
# =============================================================================


@web_router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request):
    """API Keys management page - manage personal API keys."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    return _create_api_keys_page_response(request, session)


def _create_api_keys_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create API keys page response."""
    username = session.username
    keys = dependencies.user_manager.get_api_keys(username)

    response = templates.TemplateResponse(
        request,
        "api_keys.html",
        {
            "show_nav": True,
            "current_page": "api-keys",
            "username": username,
            "api_keys": keys,
            "success_message": success_message,
            "error_message": error_message,
            "csrf_token": session.csrf_token,
        },
    )
    return response


@web_router.get("/partials/api-keys-list", response_class=HTMLResponse)
async def api_keys_list_partial(request: Request):
    """Partial for API keys list (HTMX refresh)."""
    session = _require_admin_session(request)
    if not session:
        return HTMLResponse(
            content="<p>Session expired. Please refresh the page.</p>", status_code=401
        )

    username = session.username
    keys = dependencies.user_manager.get_api_keys(username)

    response = templates.TemplateResponse(
        request,
        "partials/api_keys_list.html",
        {"api_keys": keys},
    )
    return response


@web_router.get("/mcp-credentials", response_class=HTMLResponse)
async def admin_mcp_credentials_page(request: Request):
    """Admin MCP Credentials management page - manage personal MCP credentials."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    return _create_admin_mcp_credentials_page_response(request, session)


def _create_admin_mcp_credentials_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create admin MCP credentials page response."""
    username = session.username
    credentials = dependencies.user_manager.get_mcp_credentials(username)

    response = templates.TemplateResponse(
        request,
        "admin_mcp_credentials.html",
        {
            "show_nav": True,
            "current_page": "mcp-credentials",
            "username": username,
            "mcp_credentials": credentials,
            "success_message": success_message,
            "error_message": error_message,
        },
    )
    return response


@web_router.get("/partials/mcp-credentials-list", response_class=HTMLResponse)
async def admin_mcp_credentials_list_partial(request: Request):
    """Partial for admin MCP credentials list (HTMX refresh)."""
    session = _require_admin_session(request)
    if not session:
        return HTMLResponse(
            content="<p>Session expired. Please refresh the page.</p>", status_code=401
        )

    username = session.username
    credentials = dependencies.user_manager.get_mcp_credentials(username)

    response = templates.TemplateResponse(
        request,
        "partials/mcp_credentials_list.html",
        {"mcp_credentials": credentials},
    )
    return response


# =============================================================================
# User Self-Service Routes (Any Authenticated User)
# =============================================================================


def _require_authenticated_session(request: Request) -> Optional[SessionData]:
    """Check for valid authenticated session (any role), return None if not authenticated."""
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        return None

    return session


# Old /user/login routes removed - replaced by unified login at root level
# See login_router for unified login implementation


@user_router.get("/api-keys", response_class=HTMLResponse)
async def user_api_keys_page(request: Request):
    """User API Keys management page - any authenticated user can manage their own API keys."""
    session = _require_authenticated_session(request)
    if not session:
        return _create_login_redirect(request)

    return _create_user_api_keys_page_response(request, session)


def _create_user_api_keys_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create user API keys page response."""
    username = session.username
    keys = dependencies.user_manager.get_api_keys(username)

    response = templates.TemplateResponse(
        request,
        "user_api_keys.html",
        {
            "show_nav": True,
            "current_page": "api-keys",
            "username": username,
            "api_keys": keys,
            "success_message": success_message,
            "error_message": error_message,
            "csrf_token": session.csrf_token,
        },
    )
    return response


@user_router.get("/partials/api-keys-list", response_class=HTMLResponse)
async def user_api_keys_list_partial(request: Request):
    """Partial for user API keys list (HTMX refresh)."""
    session = _require_authenticated_session(request)
    if not session:
        return HTMLResponse(
            content="<p>Session expired. Please refresh the page.</p>", status_code=401
        )

    username = session.username
    keys = dependencies.user_manager.get_api_keys(username)

    response = templates.TemplateResponse(
        request,
        "partials/api_keys_list.html",
        {"api_keys": keys},
    )
    return response


@user_router.get("/mcp-credentials", response_class=HTMLResponse)
async def user_mcp_credentials_page(request: Request):
    """User MCP Credentials management page - any authenticated user can manage their own MCP credentials."""
    session = _require_authenticated_session(request)
    if not session:
        return _create_login_redirect(request)

    return _create_user_mcp_credentials_page_response(request, session)


def _create_user_mcp_credentials_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> HTMLResponse:
    """Create user MCP credentials page response."""
    username = session.username
    credentials = dependencies.user_manager.get_mcp_credentials(username)

    response = templates.TemplateResponse(
        request,
        "user_mcp_credentials.html",
        {
            "show_nav": True,
            "current_page": "mcp-credentials",
            "username": username,
            "mcp_credentials": credentials,
            "success_message": success_message,
            "error_message": error_message,
            "csrf_token": session.csrf_token,
        },
    )
    return response


@user_router.get("/partials/mcp-credentials-list", response_class=HTMLResponse)
async def user_mcp_credentials_list_partial(request: Request):
    """Partial for user MCP credentials list (HTMX refresh)."""
    session = _require_authenticated_session(request)
    if not session:
        return HTMLResponse(
            content="<p>Session expired. Please refresh the page.</p>", status_code=401
        )

    username = session.username
    credentials = dependencies.user_manager.get_mcp_credentials(username)

    response = templates.TemplateResponse(
        request,
        "partials/mcp_credentials_list.html",
        {"mcp_credentials": credentials},
    )
    return response


@user_router.get("/logout")
async def user_logout(request: Request):
    """
    Logout and clear session for user portal.

    Redirects to unified login page after clearing session.
    """
    session_manager = get_session_manager()
    response = RedirectResponse(
        url="/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )

    # Clear the session cookie
    session_manager.clear_session(response)

    return response


# SSH Keys Management Page
@web_router.get("/ssh-keys", response_class=HTMLResponse)
async def ssh_keys_page(request: Request):
    """SSH Keys management page - view migration status and manage SSH keys."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Generate fresh CSRF token
    csrf_token = generate_csrf_token()

    # Get migration result from app state (set during server startup)
    migration_result = getattr(request.app.state, "ssh_migration_result", None)

    # Get SSH keys list
    managed_keys = []
    unmanaged_keys = []
    try:
        from ..services.ssh_key_manager import SSHKeyManager

        manager = SSHKeyManager()
        key_list = manager.list_keys()
        managed_keys = key_list.managed
        unmanaged_keys = key_list.unmanaged
    except Exception as e:
        logger.error(f"Failed to list SSH keys: {e}", extra={"correlation_id": get_correlation_id()})

    response = templates.TemplateResponse(
        request,
        "ssh_keys.html",
        {
            "show_nav": True,
            "current_page": "ssh-keys",
            "username": session.username,
            "migration_result": migration_result,
            "managed_keys": managed_keys,
            "unmanaged_keys": unmanaged_keys,
            "csrf_token": csrf_token,
        },
    )

    # Set CSRF cookie
    set_csrf_cookie(response, csrf_token)

    return response


def _create_ssh_keys_page_response(
    request: Request,
    session: SessionData,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Response:
    """Helper to create SSH keys page response with messages."""
    # Generate fresh CSRF token
    csrf_token = generate_csrf_token()

    migration_result = getattr(request.app.state, "ssh_migration_result", None)

    managed_keys = []
    unmanaged_keys = []
    try:
        from ..services.ssh_key_manager import SSHKeyManager

        manager = SSHKeyManager()
        key_list = manager.list_keys()
        managed_keys = key_list.managed
        unmanaged_keys = key_list.unmanaged
    except Exception as e:
        logger.error(f"Failed to list SSH keys: {e}", extra={"correlation_id": get_correlation_id()})

    response = templates.TemplateResponse(
        request,
        "ssh_keys.html",
        {
            "show_nav": True,
            "current_page": "ssh-keys",
            "username": session.username,
            "migration_result": migration_result,
            "managed_keys": managed_keys,
            "unmanaged_keys": unmanaged_keys,
            "csrf_token": csrf_token,
            "success_message": success_message,
            "error_message": error_message,
        },
    )

    # Set CSRF cookie
    set_csrf_cookie(response, csrf_token)

    return response


@web_router.post("/ssh-keys/create", response_class=HTMLResponse)
async def create_ssh_key(
    request: Request,
    key_name: str = Form(...),
    key_type: str = Form(...),
    email: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
):
    """Create a new SSH key."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_ssh_keys_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    try:
        from ..services.ssh_key_manager import SSHKeyManager
        from ..services.ssh_key_generator import (
            InvalidKeyNameError,
            KeyAlreadyExistsError,
        )

        manager = SSHKeyManager()
        manager.create_key(
            name=key_name,
            key_type=key_type,
            email=email if email else None,
            description=description if description else None,
        )

        return _create_ssh_keys_page_response(
            request,
            session,
            success_message=f"SSH key '{key_name}' created successfully. Public key is ready to copy.",
        )
    except InvalidKeyNameError as e:
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Invalid key name: {e}"
        )
    except KeyAlreadyExistsError as e:
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Key already exists: {e}"
        )
    except Exception as e:
        logger.error(f"Failed to create SSH key: {e}", extra={"correlation_id": get_correlation_id()})
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Failed to create key: {e}"
        )


@web_router.post("/ssh-keys/delete", response_class=HTMLResponse)
async def delete_ssh_key(
    request: Request,
    key_name: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """Delete an SSH key."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_ssh_keys_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    try:
        from ..services.ssh_key_manager import SSHKeyManager

        manager = SSHKeyManager()
        manager.delete_key(key_name)

        return _create_ssh_keys_page_response(
            request,
            session,
            success_message=f"SSH key '{key_name}' deleted successfully.",
        )
    except Exception as e:
        logger.error(f"Failed to delete SSH key: {e}", extra={"correlation_id": get_correlation_id()})
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Failed to delete key: {e}"
        )


@web_router.post("/ssh-keys/assign-host", response_class=HTMLResponse)
async def assign_host_to_key(
    request: Request,
    key_name: str = Form(...),
    hostname: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """Assign a host to an SSH key."""
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate CSRF token
    if not validate_login_csrf_token(request, csrf_token):
        return _create_ssh_keys_page_response(
            request, session, error_message="Invalid CSRF token"
        )

    try:
        from ..services.ssh_key_manager import SSHKeyManager, HostConflictError

        manager = SSHKeyManager()
        manager.assign_key_to_host(key_name, hostname)

        return _create_ssh_keys_page_response(
            request,
            session,
            success_message=f"Host '{hostname}' assigned to key '{key_name}' successfully.",
        )
    except HostConflictError as e:
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Host conflict: {e}"
        )
    except Exception as e:
        logger.error(f"Failed to assign host to SSH key: {e}", extra={"correlation_id": get_correlation_id()})
        return _create_ssh_keys_page_response(
            request, session, error_message=f"Failed to assign host: {e}"
        )


# ============================================================================
# Logs Management Routes (Story #664, #665, #667)
# ============================================================================


@web_router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    level: Optional[str] = None,
    logger: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
):
    """
    Logs page - view and filter system logs (Story #664 AC1).

    Args:
        request: FastAPI request object
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger: Filter by logger name
        search: Search by message text
        page: Page number for pagination
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Generate CSRF token for forms
    csrf_token = generate_csrf_token()

    # Get log database path from app state
    log_db_path = request.app.state.log_db_path

    # Create LogAggregatorService instance
    from ..services.log_aggregator_service import LogAggregatorService
    service = LogAggregatorService(log_db_path)

    # Parse level parameter
    levels = None
    if level:
        levels = [level]

    # Query logs with pagination
    result = service.query(
        page=page,
        page_size=50,
        sort_order="desc",
        search=search,
        levels=levels,
    )

    # Convert to template format
    logs = result["logs"]
    pagination = result["pagination"]

    # Render template
    response = templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "username": session.username,
            "show_nav": True,
            "current_page": "logs",
            "logs": logs,
            "level": level,
            "logger": logger,
            "search": search,
            "page": page,
            "total_count": pagination["total"],
            "total_pages": pagination["total_pages"],
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/partials/logs-list", response_class=HTMLResponse)
async def logs_list_partial(
    request: Request,
    level: Optional[str] = None,
    logger: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
):
    """
    Partial endpoint for logs list - used by HTMX for dynamic updates (Story #664 AC2).

    Args:
        request: FastAPI request object
        level: Filter by log level
        logger: Filter by logger name
        search: Search by message text
        page: Page number for pagination
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Reuse existing CSRF token from cookie
    csrf_token = get_csrf_token_from_cookie(request)
    if not csrf_token:
        csrf_token = generate_csrf_token()

    # Get log database path from app state
    log_db_path = request.app.state.log_db_path

    # Create LogAggregatorService instance
    from ..services.log_aggregator_service import LogAggregatorService
    service = LogAggregatorService(log_db_path)

    # Parse level parameter
    levels = None
    if level:
        levels = [level]

    # Query logs with pagination
    result = service.query(
        page=page,
        page_size=50,
        sort_order="desc",
        search=search,
        levels=levels,
    )

    # Convert to template format
    logs = result["logs"]
    pagination = result["pagination"]

    # Render partial template
    response = templates.TemplateResponse(
        "partials/logs_list.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "logs": logs,
            "level": level,
            "logger": logger,
            "search": search,
            "page": page,
            "total_count": pagination["total"],
            "total_pages": pagination["total_pages"],
        },
    )

    set_csrf_cookie(response, csrf_token)
    return response


@web_router.get("/logs/export")
async def export_logs_web(
    request: Request,
    format: str = "json",
    search: Optional[str] = None,
    level: Optional[str] = None,
):
    """
    Export logs to file in JSON or CSV format (Story #667 AC1).

    Web UI endpoint that triggers browser download of log export file.

    Args:
        request: FastAPI request object
        format: Export format - "json" or "csv" (default: json)
        search: Text search filter
        level: Log level filter
    """
    session = _require_admin_session(request)
    if not session:
        return _create_login_redirect(request)

    # Validate format parameter
    if format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail="Invalid format. Must be 'json' or 'csv'")

    # Get log database path from app state
    log_db_path = request.app.state.log_db_path

    # Create LogAggregatorService instance
    from ..services.log_aggregator_service import LogAggregatorService
    service = LogAggregatorService(log_db_path)

    # Parse level parameter
    levels = None
    if level:
        levels = [lv.strip() for lv in level.split(",") if lv.strip()]

    # Query all logs (no pagination for export)
    logs = service.query_all(
        search=search,
        levels=levels,
        correlation_id=None,
    )

    # Format output based on requested format
    from ..services.log_export_formatter import LogExportFormatter
    from datetime import datetime, timezone

    formatter = LogExportFormatter()

    if format == "json":
        # JSON export with metadata
        filters = {
            "search": search,
            "level": level,
            "correlation_id": None,
        }
        content = formatter.to_json(logs, filters)
        media_type = "application/json"
    else:
        # CSV export
        content = formatter.to_csv(logs)
        media_type = "text/csv"

    # Generate filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"logs_{timestamp}.{format}"

    # Return response with file download headers
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


# ============================================================================
# Unified Login Routes (Phase 2: Login Consolidation)
# ============================================================================


@login_router.get("/login", response_class=HTMLResponse)
async def unified_login_page(
    request: Request,
    redirect_to: Optional[str] = None,
    error: Optional[str] = None,
    info: Optional[str] = None,
):
    """
    Unified login page for all contexts (admin, user, OAuth).

    Supports:
    - SSO via OIDC (if enabled)
    - Username/password authentication
    - Smart redirect after login based on redirect_to parameter or user role

    Args:
        request: FastAPI Request object
        redirect_to: Optional URL to redirect after successful login
        error: Optional error message to display
        info: Optional info message to display
    """
    # Generate CSRF token for the form
    csrf_token = generate_csrf_token()

    # Check if there's an expired session
    session_manager = get_session_manager()
    if not info and session_manager.is_session_expired(request):
        info = "Session expired, please login again"

    # Check if OIDC is enabled
    from ..auth.oidc import routes as oidc_routes

    sso_enabled = False
    if oidc_routes.oidc_manager and hasattr(oidc_routes.oidc_manager, "is_enabled"):
        sso_enabled = oidc_routes.oidc_manager.is_enabled()

    # Create response with CSRF token in signed cookie
    response = templates.TemplateResponse(
        "unified_login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "redirect_to": redirect_to,
            "error": error,
            "info": info,
            "sso_enabled": sso_enabled,
        },
    )

    # Set CSRF token in signed cookie for validation on POST
    set_csrf_cookie(response, csrf_token, path="/")

    return response


@login_router.post("/login", response_class=HTMLResponse)
async def unified_login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """
    Process unified login form submission.

    Validates credentials and creates session on success.
    Accepts ANY role (normal_user, power_user, admin).
    Redirects based on redirect_to parameter or user role.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        username: Username from form
        password: Password from form
        csrf_token: CSRF token from form
        redirect_to: Optional redirect URL from form
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

    # Authenticate user (any role accepted)
    user = user_manager.authenticate_user(username, password)

    if user is None:
        # Invalid credentials - show error with new CSRF token
        new_csrf_token = generate_csrf_token()

        # Check if OIDC is enabled
        from ..auth.oidc import routes as oidc_routes

        sso_enabled = False
        if oidc_routes.oidc_manager and hasattr(oidc_routes.oidc_manager, "is_enabled"):
            sso_enabled = oidc_routes.oidc_manager.is_enabled()

        error_response = templates.TemplateResponse(
            "unified_login.html",
            {
                "request": request,
                "csrf_token": new_csrf_token,
                "redirect_to": redirect_to,
                "error": "Invalid username or password",
                "sso_enabled": sso_enabled,
            },
            status_code=200,
        )
        set_csrf_cookie(error_response, new_csrf_token, path="/")
        return error_response

    # Validate redirect_to URL (prevent open redirect)
    safe_redirect = None
    if redirect_to:
        # Only allow relative URLs starting with /
        if redirect_to.startswith("/") and not redirect_to.startswith("//"):
            safe_redirect = redirect_to

    # Smart redirect logic
    if safe_redirect:
        # Explicit redirect_to parameter takes precedence
        redirect_url = safe_redirect
    elif user.role.value == "admin":
        # Admin users go to admin dashboard
        redirect_url = "/admin/"
    else:
        # Non-admin users go to user interface
        redirect_url = "/user/api-keys"

    # Create session for authenticated user
    session_manager = get_session_manager()
    redirect_response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_manager.create_session(
        redirect_response,
        username=user.username,
        role=user.role.value,
    )

    return redirect_response


@login_router.get("/login/sso")
async def unified_login_sso(
    request: Request,
    redirect_to: Optional[str] = None,
):
    """
    Initiate OIDC SSO flow from unified login page.

    Preserves redirect_to parameter through OIDC flow by storing
    it in the OIDC state parameter.

    Args:
        request: FastAPI Request object
        redirect_to: Optional URL to redirect after SSO completes
    """
    from ..auth.oidc import routes as oidc_routes

    # Check if OIDC is enabled
    if not oidc_routes.oidc_manager or not oidc_routes.oidc_manager.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not enabled on this server",
        )

    # Ensure OIDC provider is initialized
    try:
        await oidc_routes.oidc_manager.ensure_provider_initialized()
    except Exception as e:
        logger.error(f"Failed to initialize OIDC provider: {e}", extra={"correlation_id": get_correlation_id()})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO provider is currently unavailable",
        )

    # Generate PKCE code verifier and challenge for OAuth 2.1 security
    import hashlib
    import base64

    code_verifier = secrets.token_urlsafe(32)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    # Validate redirect_to parameter (prevent open redirect)
    # Note: redirect_to is URL-encoded by JavaScript's encodeURIComponent, decode it
    from urllib.parse import unquote

    safe_redirect = None
    if redirect_to:
        # URL-decode (JavaScript's encodeURIComponent encoding)
        decoded_redirect = unquote(redirect_to)
        if decoded_redirect.startswith("/") and not decoded_redirect.startswith("//"):
            safe_redirect = decoded_redirect

    # Store state with code_verifier and redirect_to using OIDC state manager
    state_data = {
        "code_verifier": code_verifier,
    }
    # Only include redirect_to if explicitly provided (let callback determine based on role otherwise)
    if safe_redirect:
        state_data["redirect_to"] = safe_redirect
    state_token = oidc_routes.state_manager.create_state(state_data)

    # Build OIDC authorization URL
    # Use CIDX_ISSUER_URL if set (for reverse proxy scenarios), otherwise use request.base_url
    issuer_url = os.getenv("CIDX_ISSUER_URL")
    if issuer_url:
        callback_url = f"{issuer_url.rstrip('/')}/auth/sso/callback"
    else:
        callback_url = str(request.base_url).rstrip("/") + "/auth/sso/callback"
    oidc_auth_url = oidc_routes.oidc_manager.provider.get_authorization_url(
        state=state_token, redirect_uri=callback_url, code_challenge=code_challenge
    )

    return RedirectResponse(url=oidc_auth_url)


# ==============================================================================
# Backwards Compatibility Redirects (Phase 8: Login Consolidation)
# ==============================================================================


@login_router.get("/admin/login")
async def redirect_admin_login(redirect_to: Optional[str] = None):
    """
    Backwards compatibility redirect: /admin/login → /login.

    301 Permanent Redirect to inform clients to update their URLs.
    """
    if redirect_to:
        return RedirectResponse(
            url=f"/login?redirect_to={quote(redirect_to)}",
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
        )
    return RedirectResponse(url="/login", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@login_router.get("/user/login")
async def redirect_user_login(redirect_to: Optional[str] = None):
    """
    Backwards compatibility redirect: /user/login → /login.

    301 Permanent Redirect to inform clients to update their URLs.
    """
    if redirect_to:
        return RedirectResponse(
            url=f"/login?redirect_to={quote(redirect_to)}",
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
        )
    return RedirectResponse(url="/login", status_code=status.HTTP_301_MOVED_PERMANENTLY)
