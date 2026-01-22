"""
Session Registry for MCP Protocol - Manages MCPSessionState instances.

Story #722: Session Impersonation for Delegated Queries - Critical fixes
Story #731: TTL-Based Session Cleanup - Prevents memory leaks from accumulated sessions

This module provides a thread-safe singleton registry that maps MCP session IDs
to MCPSessionState instances. This allows impersonation state to persist across
multiple tool calls within the same session.

The registry includes TTL-based cleanup to automatically remove sessions that have
been idle for longer than the configured TTL (default: 1 hour). A background task
runs periodically (default: every 15 minutes) to clean up stale sessions.

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

    # Start background cleanup (typically in app startup):
    registry.start_background_cleanup(ttl_seconds=3600, cleanup_interval_seconds=900)

    # Stop background cleanup (typically in app shutdown):
    registry.stop_background_cleanup()
"""

import asyncio
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional

from code_indexer.server.auth.user_manager import User
from code_indexer.server.auth.mcp_session_state import MCPSessionState


logger = logging.getLogger(__name__)

# Default TTL settings (Story #731)
DEFAULT_SESSION_TTL_SECONDS = 3600  # 1 hour
DEFAULT_CLEANUP_INTERVAL_SECONDS = 900  # 15 minutes


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
                    # TTL cleanup attributes (Story #731)
                    instance._cleanup_task: Optional[asyncio.Task] = None
                    instance._ttl_seconds = DEFAULT_SESSION_TTL_SECONDS
                    instance._cleanup_interval_seconds = (
                        DEFAULT_CLEANUP_INTERVAL_SECONDS
                    )
                    cls._instance = instance
        return cls._instance

    def get_or_create_session(
        self, session_id: str, authenticated_user: User
    ) -> MCPSessionState:
        """
        Get existing session or create new one.

        If a session with the given ID already exists, returns it (preserving
        any existing impersonation state) and updates the last activity timestamp.
        Otherwise, creates a new session with the authenticated user.

        Args:
            session_id: Unique MCP session identifier
            authenticated_user: The user who authenticated for this session

        Returns:
            MCPSessionState for the session (existing or newly created)
        """
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.touch()  # Update activity timestamp (Story #731)
                return session

            session = MCPSessionState(
                session_id=session_id,
                authenticated_user=authenticated_user,
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[MCPSessionState]:
        """
        Get existing session by ID.

        Updates the last activity timestamp if session exists (Story #731).

        Args:
            session_id: Unique MCP session identifier

        Returns:
            MCPSessionState if session exists, None otherwise
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()  # Update activity timestamp (Story #731)
            return session

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

    # TTL-based cleanup methods (Story #731)

    def cleanup_stale_sessions(self) -> int:
        """
        Remove sessions idle for more than TTL seconds.

        Scans all sessions and removes those whose last_activity timestamp
        is older than the configured TTL.

        Returns:
            Number of sessions removed
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            stale_ids = [
                sid
                for sid, session in self._sessions.items()
                if (now - session.last_activity).total_seconds() > self._ttl_seconds
            ]
            for sid in stale_ids:
                del self._sessions[sid]

        if stale_ids:
            logger.info(f"Cleaned up {len(stale_ids)} stale MCP sessions")
        return len(stale_ids)

    async def _cleanup_loop(self) -> None:
        """
        Background cleanup loop.

        Runs cleanup_stale_sessions() at the configured interval until cancelled.
        """
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                try:
                    self.cleanup_stale_sessions()
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
        except asyncio.CancelledError:
            # Normal shutdown, don't log as error
            pass

    def start_background_cleanup(
        self,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        cleanup_interval_seconds: int = DEFAULT_CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        """
        Start background cleanup task.

        Creates an asyncio task that periodically removes stale sessions.
        Safe to call multiple times - will not create duplicate tasks.

        Args:
            ttl_seconds: Session TTL in seconds (default: 1 hour)
            cleanup_interval_seconds: Cleanup interval in seconds (default: 15 minutes)
        """
        self._ttl_seconds = ttl_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info(
                f"Session cleanup started: TTL={ttl_seconds}s, interval={cleanup_interval_seconds}s"
            )

    def stop_background_cleanup(self) -> None:
        """
        Stop background cleanup task.

        Cancels the cleanup task if running. Safe to call even if not running.
        """
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Session cleanup stopped")


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
