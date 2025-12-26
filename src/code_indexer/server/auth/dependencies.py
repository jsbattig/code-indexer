"""
FastAPI authentication dependencies.

Provides dependency injection for JWT authentication and role-based access control.
"""

from typing import Optional, TYPE_CHECKING, Dict, Any
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import wraps
from datetime import datetime, timezone
import base64

from .jwt_manager import JWTManager, TokenExpiredError, InvalidTokenError
from .user_manager import UserManager, User

if TYPE_CHECKING:
    from .oauth.oauth_manager import OAuthManager
    from .mcp_credential_manager import MCPCredentialManager


# Global instances (will be initialized by app)
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None
oauth_manager: Optional["OAuthManager"] = (
    None  # Forward reference to avoid circular dependency
)
mcp_credential_manager: Optional["MCPCredentialManager"] = None

# Security scheme for bearer token authentication
# auto_error=False allows us to handle missing credentials manually and return 401 per MCP spec
security = HTTPBearer(auto_error=False)


def _build_www_authenticate_header() -> str:
    """
    Build RFC 9728 compliant WWW-Authenticate header value.

    Per RFC 9728 Section 5.1, the header must include:
    - realm="mcp" - Protection space identifier
    - resource_metadata - OAuth authorization server discovery endpoint

    This enables Claude.ai and other MCP clients to discover OAuth endpoints.

    Returns:
        WWW-Authenticate header value with realm and resource_metadata parameters
    """
    # Build discovery URL from oauth_manager's issuer
    if oauth_manager:
        discovery_url = f"{oauth_manager.issuer}/.well-known/oauth-authorization-server"
        return f'Bearer realm="mcp", resource_metadata="{discovery_url}"'
    else:
        # Fallback to basic Bearer with realm if oauth_manager not initialized
        return 'Bearer realm="mcp"'


def _validate_jwt_and_get_user(token: str) -> User:
    """Validate JWT token and return User object or raise HTTPException 401."""
    if not jwt_manager or not user_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not properly initialized",
        )

    try:
        payload = jwt_manager.validate_token(token)
        username = payload.get("username")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing username",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

        # Check if token is blacklisted
        from code_indexer.server.app import is_token_blacklisted

        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

        user = user_manager.get_user(username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

        return user

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )


def _should_refresh_token(payload: Dict[str, Any]) -> bool:
    """Check if token has passed 50% of its lifetime."""
    try:
        iat = float(payload.get("iat", 0))
        exp = float(payload.get("exp", 0))
    except Exception:
        return False

    if exp <= iat:
        return False

    now = datetime.now(timezone.utc).timestamp()
    lifetime = exp - iat
    elapsed = now - iat
    return elapsed > (lifetime * 0.5)


def _refresh_jwt_cookie(response: Response, payload: Dict[str, Any]) -> None:
    """Create new JWT with preserved claims and set as secure cookie.

    The old token's JTI is blacklisted to prevent token reuse and ensure
    that only the most recent token remains valid.
    """
    import logging

    if not jwt_manager:
        logging.getLogger(__name__).error(
            "JWT manager not initialized - cannot refresh cookie"
        )
        return

    # Blacklist old token BEFORE creating new one to prevent reuse
    old_jti = payload.get("jti")
    if old_jti:
        from code_indexer.server.app import blacklist_token

        blacklist_token(old_jti)

    new_token = jwt_manager.create_token(
        {
            "username": payload.get("username"),
            "role": payload.get("role"),
            "created_at": payload.get("created_at"),
        }
    )

    response.set_cookie(
        key="cidx_session",
        value=new_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=jwt_manager.token_expiration_minutes * 60,
    )


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Get current authenticated user from OAuth or JWT token.

    Validates OAuth tokens first (if oauth_manager is available), then falls back to JWT.
    This allows both OAuth 2.1 tokens and legacy JWT tokens to work.

    Args:
        credentials: Bearer token from Authorization header

    Returns:
        Current User object

    Raises:
        HTTPException: If authentication fails
    """
    if not jwt_manager or not user_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not properly initialized",
        )

    # Handle missing credentials (per MCP spec RFC 9728, return 401 not 403)
    if credentials is None:
        # No Authorization header - check for JWT cookie
        token = request.cookies.get("cidx_session")
        if token:
            # Validate cookie JWT using same logic as Bearer
            return _validate_jwt_and_get_user(token)
        # No auth method available
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )

    token = credentials.credentials

    # Try OAuth token validation first (if oauth_manager is available)
    if oauth_manager:
        oauth_result = oauth_manager.validate_token(token)
        if oauth_result:
            # Valid OAuth token - get user
            username = oauth_result.get("user_id")
            if username:
                user = user_manager.get_user(username)
                if user is None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found",
                        headers={"WWW-Authenticate": _build_www_authenticate_header()},
                    )
                return user

    # Fallback to JWT validation
    return _validate_jwt_and_get_user(token)


def require_permission(permission: str):
    """
    Decorator factory for requiring specific permissions.

    Args:
        permission: Required permission string

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(current_user: User = Depends(get_current_user), *args, **kwargs):
            if not current_user.has_permission(permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions: {permission} required",
                )
            return func(current_user, *args, **kwargs)

        return wrapper

    return decorator


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current user and ensure they have admin role.

    Args:
        current_user: Current authenticated user

    Returns:
        User with admin role

    Raises:
        HTTPException: If user is not admin
    """
    if not current_user.has_permission("manage_users"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


def get_current_power_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current user and ensure they have power user or admin role.

    Args:
        current_user: Current authenticated user

    Returns:
        User with power user or admin role

    Raises:
        HTTPException: If user doesn't have sufficient permissions
    """
    if not current_user.has_permission("activate_repos"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Power user or admin access required",
        )
    return current_user


async def get_mcp_user_from_credentials(request: Request) -> Optional[User]:
    """
    Authenticate using MCP client credentials.

    Checks Basic auth header, then client_secret_post body.
    Returns User if authenticated, None if no credentials present.
    Raises HTTPException(401) if credentials present but invalid.

    Per Story #616 AC1-AC2:
    - Basic auth: Authorization header with "Basic base64(client_id:client_secret)"
    - client_secret_post: POST body with client_id and client_secret fields

    Args:
        request: FastAPI Request object

    Returns:
        User object if MCP credentials valid, None if no MCP credentials present

    Raises:
        HTTPException: 401 if credentials present but invalid
    """
    if not mcp_credential_manager or not user_manager:
        return None

    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    # Check Basic auth header (AC1)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            # Decode base64 credentials
            encoded = auth_header[6:]  # Remove "Basic " prefix
            decoded = base64.b64decode(encoded).decode("utf-8")

            # Split on first colon only (client_secret may contain colons)
            if ":" in decoded:
                client_id, client_secret = decoded.split(":", 1)
        except Exception:
            # Invalid Basic auth format - return 401
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

    # Check client_secret_post in body (AC2)
    if not client_id and request.method == "POST":
        try:
            # Check if body has already been parsed and cached
            if hasattr(request.state, "_json"):
                body = request.state._json
            else:
                # Try to parse JSON body
                body = await request.json()

            if isinstance(body, dict):
                body_client_id = body.get("client_id")
                body_client_secret = body.get("client_secret")

                if body_client_id and body_client_secret:
                    client_id = body_client_id
                    client_secret = body_client_secret
        except Exception:
            # Body not JSON, already consumed, or parse error - no client_secret_post present
            pass

    # If no MCP credentials found, return None (no error)
    if not client_id or not client_secret:
        return None

    # Verify credentials using MCPCredentialManager (AC3-AC5)
    user_id = mcp_credential_manager.verify_credential(client_id, client_secret)

    if not user_id:
        # Invalid credentials - return 401 (AC3)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )

    # Get User object
    user = user_manager.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )

    # Success - verify_credential() already updated last_used_at (AC5)
    return user


def get_current_user_web_or_api(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Get current authenticated user from web UI session OR API credentials.

    Authentication priority:
    1. Web UI session cookie ("session") via SessionManager
    2. JWT cookie ("cidx_session") or Bearer token (existing API auth)
    3. 401 Unauthorized if neither present

    This enables the same endpoint to be accessed from both:
    - Web UI (using itsdangerous session cookies)
    - API clients (using JWT tokens or Bearer auth)

    Args:
        request: FastAPI Request object
        credentials: Optional Bearer token from Authorization header

    Returns:
        Authenticated User object

    Raises:
        HTTPException: 401 if authentication fails
    """
    import logging

    logger = logging.getLogger(__name__)

    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not properly initialized",
        )

    # Priority 1: Try web UI session cookie
    session_cookie = request.cookies.get("session")
    if session_cookie:
        try:
            from code_indexer.server.web.auth import get_session_manager

            session_manager = get_session_manager()
            session_data = session_manager.get_session(request)

            if session_data:
                # Valid web session - get User object
                user = user_manager.get_user(session_data.username)
                if user:
                    return user
        except Exception as e:
            # Web session validation failed - fall through to JWT/Bearer auth
            logger.debug(
                "Web session validation failed, falling back to JWT/Bearer: %s", e
            )

    # Priority 2: Fall back to JWT/Bearer authentication
    try:
        return get_current_user(request, credentials)
    except HTTPException:
        # Re-raise with proper WWW-Authenticate header
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )


async def get_current_user_for_mcp(request: Request) -> User:
    """
    Get authenticated user for /mcp endpoint.

    Authentication priority per Story #616 AC6:
    1. MCP credentials (Basic auth or client_secret_post)
    2. OAuth/JWT tokens (existing authentication)
    3. 401 Unauthorized if none present

    Args:
        request: FastAPI Request object

    Returns:
        Authenticated User object

    Raises:
        HTTPException: 401 if authentication fails
    """
    # Priority 1: Try MCP credentials
    user = await get_mcp_user_from_credentials(request)
    if user:
        return user

    # Priority 2: Fall back to OAuth/JWT (existing auth)
    # Extract credentials from request for get_current_user
    credentials: Optional[HTTPAuthorizationCredentials] = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    try:
        return get_current_user(request, credentials)
    except HTTPException:
        # Re-raise with proper WWW-Authenticate header
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": _build_www_authenticate_header()},
        )
