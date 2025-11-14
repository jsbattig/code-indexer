"""
FastAPI authentication dependencies.

Provides dependency injection for JWT authentication and role-based access control.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import wraps

from .jwt_manager import JWTManager, TokenExpiredError, InvalidTokenError
from .user_manager import UserManager, User


# Global instances (will be initialized by app)
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None

# Security scheme for bearer token authentication
security = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Get current authenticated user from JWT token.

    Args:
        credentials: JWT token from Authorization header

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

    try:
        # Validate JWT token
        payload = jwt_manager.validate_token(credentials.credentials)
        username = payload.get("username")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing username",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token is blacklisted
        from src.code_indexer.server.app import is_token_blacklisted
        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from storage
        user = user_manager.get_user(username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
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
