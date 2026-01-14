"""
MCP Session State Management for Delegated Queries.

Story #722: Implements session-scoped impersonation for MCP sessions, allowing
authenticated ADMIN users to assume another user's identity for the duration
of their session.

This module provides:
- MCPSessionState: Per-session state container with impersonation support
- ImpersonationResult: Result type for impersonation attempts

Thread Safety:
    MCPSessionState uses a threading Lock to ensure thread-safe access to
    session state, which is important when the same session may be accessed
    from multiple concurrent requests.
"""

from dataclasses import dataclass
from threading import Lock
from typing import Optional, Dict, Any

from .user_manager import User, UserRole


@dataclass
class ImpersonationResult:
    """Result of an impersonation attempt.

    Attributes:
        success: True if impersonation was set successfully, False otherwise
        error: Error message if impersonation failed, None otherwise
    """

    success: bool
    error: Optional[str] = None


class MCPSessionState:
    """
    Manages per-session state including impersonation for MCP sessions.

    This class handles session-scoped impersonation for delegated queries,
    allowing authenticated ADMIN users to assume another user's identity
    for the duration of their session.

    Attributes:
        session_id: Unique identifier for the MCP session
        authenticated_user: The originally authenticated user (never changes)
        impersonated_user: The user being impersonated, if any

    Usage:
        session = MCPSessionState(session_id="abc-123", authenticated_user=admin)

        # Check if impersonation is allowed
        if session.can_impersonate():
            result = session.try_set_impersonation(target_user)
            if result.success:
                # effective_user now returns target_user
                pass

        # Get the effective user (impersonated or authenticated)
        user = session.effective_user

        # Clear impersonation
        session.clear_impersonation()
    """

    def __init__(self, session_id: str, authenticated_user: User):
        """
        Initialize MCP session state.

        Args:
            session_id: Unique identifier for the MCP session
            authenticated_user: The originally authenticated user
        """
        self._lock = Lock()
        self._session_id = session_id
        self._authenticated_user = authenticated_user
        self._impersonated_user: Optional[User] = None

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    @property
    def authenticated_user(self) -> User:
        """Get the originally authenticated user."""
        return self._authenticated_user

    @property
    def impersonated_user(self) -> Optional[User]:
        """Get the impersonated user, if any."""
        return self._impersonated_user

    @property
    def effective_user(self) -> User:
        """
        Get the effective user for permission checks and operations.

        Returns the impersonated user if impersonation is active,
        otherwise returns the authenticated user.

        Returns:
            The effective user for this session
        """
        if self._impersonated_user is not None:
            return self._impersonated_user
        return self._authenticated_user

    @property
    def is_impersonating(self) -> bool:
        """Check if impersonation is currently active."""
        return self._impersonated_user is not None

    def can_impersonate(self) -> bool:
        """
        Check if the authenticated user is allowed to impersonate others.

        Only ADMIN role users can impersonate other users.

        Returns:
            True if impersonation is allowed, False otherwise
        """
        return self._authenticated_user.role == UserRole.ADMIN

    def set_impersonation(self, target_user: User) -> None:
        """
        Set the impersonated user (admin check done by caller).

        This method directly sets the impersonated user without checking
        permissions. Use try_set_impersonation() for permission-checked
        impersonation.

        Thread-safe: Protected by internal lock.

        Args:
            target_user: The user to impersonate
        """
        with self._lock:
            self._impersonated_user = target_user

    def clear_impersonation(self) -> None:
        """Clear any active impersonation.

        Thread-safe: Protected by internal lock.
        """
        with self._lock:
            self._impersonated_user = None

    def try_set_impersonation(self, target_user: User) -> ImpersonationResult:
        """
        Attempt to set impersonation with permission checking.

        Only ADMIN role users can impersonate other users. Non-admin users
        will receive an error message explaining the requirement.

        Args:
            target_user: The user to impersonate

        Returns:
            ImpersonationResult with success=True if impersonation was set,
            or success=False with error message if not allowed
        """
        if not self.can_impersonate():
            return ImpersonationResult(
                success=False,
                error="Impersonation requires ADMIN role",
            )

        self.set_impersonation(target_user)
        return ImpersonationResult(success=True)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize session state to dictionary.

        Returns:
            Dictionary with session state information (excludes sensitive data).
            Includes effective_user for clarity on which user's permissions apply.
        """
        with self._lock:
            impersonated = self._impersonated_user
        return {
            "session_id": self._session_id,
            "authenticated_user": self._authenticated_user.username,
            "impersonated_user": (
                impersonated.username if impersonated is not None else None
            ),
            "is_impersonating": impersonated is not None,
            "effective_user": (
                impersonated.username
                if impersonated is not None
                else self._authenticated_user.username
            ),
        }
