"""
Web Admin UI Module.

Provides web-based administration interface for CIDX server.
"""

from .routes import web_router, user_router
from .auth import (
    SessionManager,
    SessionData,
    get_session_manager,
    init_session_manager,
    require_admin_session,
    SESSION_COOKIE_NAME,
    SESSION_TIMEOUT_SECONDS,
)

__all__ = [
    "web_router",
    "user_router",
    "SessionManager",
    "SessionData",
    "get_session_manager",
    "init_session_manager",
    "require_admin_session",
    "SESSION_COOKIE_NAME",
    "SESSION_TIMEOUT_SECONDS",
]
