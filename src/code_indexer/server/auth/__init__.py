"""
Authentication and authorization module for CIDX Server.

Provides JWT-based authentication, role-based access control,
user management, and session impersonation functionality.
"""

from .mcp_session_state import MCPSessionState, ImpersonationResult

__all__ = [
    "JWTManager",
    "UserManager",
    "PasswordManager",
    "User",
    "UserRole",
    "MCPSessionState",
    "ImpersonationResult",
]
