"""
Session Registry for MCP Protocol - Manages MCPSessionState instances.

Story #722: Session Impersonation for Delegated Queries - Critical fixes

This module provides a thread-safe singleton registry that maps MCP session IDs
to MCPSessionState instances. This allows impersonation state to persist across
multiple tool calls within the same session.

The registry is accessed at the protocol layer in protocol.py and passed to
handlers that require session state (like set_session_impersonation).

Usage:
    from code_indexer.server.mcp.session_registry import get_session_registry

    registry = get_session_registry()
    session = registry.get_or_create_session(session_id, authenticated_user)

    # Later, in another tool call within the same session:
    session = registry.get_session(session_id)
    if session and session.is_impersonating:
        effective_user = session.effective_user
"""

from threading import Lock
from typing import Dict, Optional

from code_indexer.server.auth.user_manager import User
from code_indexer.server.auth.mcp_session_state import MCPSessionState


class SessionRegistry:
    """
    Thread-safe singleton registry for MCP session states.

    Manages MCPSessionState instances keyed by session ID. This enables
    impersonation and other session-scoped state to persist across multiple
    tool calls within the same MCP session.

    Thread Safety:
        All operations are protected by a threading lock to ensure safe
        concurrent access from multiple request handlers.

    Attributes:
        _sessions: Dictionary mapping session IDs to MCPSessionState instances
        _lock: Threading lock for thread-safe operations
    """

    _instance: Optional["SessionRegistry"] = None
    _init_lock: Lock = Lock()

    def __new__(cls) -> "SessionRegistry":
        """Create or return singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._init_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._sessions: Dict[str, MCPSessionState] = {}
                    instance._lock = Lock()
                    cls._instance = instance
        return cls._instance

    def get_or_create_session(
        self, session_id: str, authenticated_user: User
    ) -> MCPSessionState:
        """
        Get existing session or create new one.

        If a session with the given ID already exists, returns it (preserving
        any existing impersonation state). Otherwise, creates a new session
        with the authenticated user.

        Args:
            session_id: Unique MCP session identifier
            authenticated_user: The user who authenticated for this session

        Returns:
            MCPSessionState for the session (existing or newly created)
        """
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            session = MCPSessionState(
                session_id=session_id,
                authenticated_user=authenticated_user,
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[MCPSessionState]:
        """
        Get existing session by ID.

        Args:
            session_id: Unique MCP session identifier

        Returns:
            MCPSessionState if session exists, None otherwise
        """
        with self._lock:
            return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """
        Remove session from registry.

        Should be called when an MCP session ends (e.g., DELETE /mcp).

        Args:
            session_id: Unique MCP session identifier

        Returns:
            True if session was removed, False if it didn't exist
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def session_count(self) -> int:
        """
        Get count of active sessions.

        Returns:
            Number of sessions currently in registry
        """
        with self._lock:
            return len(self._sessions)

    def clear_all(self) -> None:
        """
        Remove all sessions from registry.

        Primarily used for testing and server shutdown.
        """
        with self._lock:
            self._sessions.clear()


# Module-level singleton accessor
_registry: Optional[SessionRegistry] = None
_registry_lock: Lock = Lock()


def get_session_registry() -> SessionRegistry:
    """
    Get the global SessionRegistry singleton.

    Returns:
        The SessionRegistry singleton instance
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = SessionRegistry()
    return _registry
