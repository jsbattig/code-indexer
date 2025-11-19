"""
FastAPI authentication dependencies.

Provides dependency injection for JWT authentication and role-based access control.
"""

from typing import Optional, TYPE_CHECKING
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import wraps

from .jwt_manager import JWTManager, TokenExpiredError, InvalidTokenError
from .user_manager import UserManager, User

if TYPE_CHECKING:
    from .oauth.oauth_manager import OAuthManager


# Global instances (will be initialized by app)
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None
oauth_manager: Optional["OAuthManager"] = (
    None  # Forward reference to avoid circular dependency
)

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


def get_current_user(
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
    try:
        # Validate JWT token
        payload = jwt_manager.validate_token(token)
        username = payload.get("username")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing username",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

        # Check if token is blacklisted
        from src.code_indexer.server.app import is_token_blacklisted

        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": _build_www_authenticate_header()},
            )

        # Get user from storage
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
