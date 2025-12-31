"""
Web UI Session Management using itsdangerous.

Provides secure session management with signed cookies for the admin web interface.
"""

import secrets
import time
from typing import Optional, Tuple
from dataclasses import dataclass

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from fastapi import Request, Response, HTTPException, status


# Session timeout in seconds (8 hours)
SESSION_TIMEOUT_SECONDS = 8 * 60 * 60

# Cookie settings
SESSION_COOKIE_NAME = "session"


def should_use_secure_cookies(config) -> bool:
    """Determine if secure cookies should be used based on server configuration."""
    localhost_hosts = ("127.0.0.1", "localhost", "::1")
    return config.host not in localhost_hosts


CSRF_COOKIE_NAME = "csrf_token"


@dataclass
class SessionData:
    """Data stored in a session."""

    username: str
    role: str
    csrf_token: str
    created_at: float


class SessionManager:
    """
    Manages web UI sessions using itsdangerous signed cookies.

    Features:
    - Signed session cookies using URLSafeTimedSerializer
    - CSRF token per session
    - 8-hour session timeout
    - httpOnly cookies
    """

    def __init__(self, secret_key: str, config):
        """
        Initialize session manager.

        Args:
            secret_key: Secret key for signing cookies
            config: Server configuration for cookie security settings
        """
        self._serializer = URLSafeTimedSerializer(secret_key)
        self._salt = "web-session"
        self._config = config

    def create_session(
        self,
        response: Response,
        username: str,
        role: str,
    ) -> str:
        """
        Create a new session and set the session cookie.

        Args:
            response: FastAPI Response object
            username: User's username
            role: User's role

        Returns:
            CSRF token for the session
        """
        csrf_token = secrets.token_urlsafe(32)
        created_at = time.time()

        session_data = {
            "username": username,
            "role": role,
            "csrf_token": csrf_token,
            "created_at": created_at,
        }

        # Sign the session data
        signed_value = self._serializer.dumps(session_data, salt=self._salt)

        # Set the session cookie
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=signed_value,
            httponly=True,
            secure=should_use_secure_cookies(self._config),
            samesite="lax",
            max_age=SESSION_TIMEOUT_SECONDS,
        )

        return csrf_token

    def get_session(self, request: Request) -> Optional[SessionData]:
        """
        Get and validate session from request cookies.

        Args:
            request: FastAPI Request object

        Returns:
            SessionData if valid session exists, None otherwise
        """
        session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_cookie:
            return None

        try:
            # Verify signature and check expiration
            data = self._serializer.loads(
                session_cookie,
                salt=self._salt,
                max_age=SESSION_TIMEOUT_SECONDS,
            )

            return SessionData(
                username=data["username"],
                role=data["role"],
                csrf_token=data["csrf_token"],
                created_at=data["created_at"],
            )

        except SignatureExpired:
            # Session has expired
            return None
        except BadSignature:
            # Invalid signature - tampered cookie
            return None
        except (KeyError, TypeError):
            # Invalid session data structure
            return None

    def is_session_expired(self, request: Request) -> bool:
        """
        Check if the session cookie exists but is expired.

        Args:
            request: FastAPI Request object

        Returns:
            True if session cookie exists but is expired, False otherwise
        """
        session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_cookie:
            return False

        try:
            self._serializer.loads(
                session_cookie,
                salt=self._salt,
                max_age=SESSION_TIMEOUT_SECONDS,
            )
            return False  # Not expired
        except SignatureExpired:
            return True  # Expired
        except BadSignature:
            return False  # Invalid, not expired

    def clear_session(self, response: Response) -> None:
        """
        Clear the session cookie.

        Args:
            response: FastAPI Response object
        """
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            httponly=True,
            secure=should_use_secure_cookies(self._config),
            samesite="lax",
        )

    def validate_csrf_token(
        self,
        request: Request,
        submitted_token: Optional[str],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate CSRF token against session.

        Args:
            request: FastAPI Request object
            submitted_token: CSRF token from form submission

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not submitted_token:
            return False, "CSRF token missing"

        session = self.get_session(request)
        if not session:
            return False, "No valid session"

        if not secrets.compare_digest(session.csrf_token, submitted_token):
            return False, "Invalid CSRF token"

        return True, None


# Global session manager instance - will be initialized with secret key
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        raise RuntimeError(
            "Session manager not initialized. Call init_session_manager first."
        )
    return _session_manager


def init_session_manager(secret_key: str, config) -> SessionManager:
    """
    Initialize the global session manager.

    Args:
        secret_key: Secret key for signing cookies
        config: Server configuration

    Returns:
        Initialized SessionManager
    """
    global _session_manager
    _session_manager = SessionManager(secret_key, config)
    return _session_manager


def require_admin_session(request: Request) -> SessionData:
    """
    Dependency to require valid admin session.

    Args:
        request: FastAPI Request object

    Returns:
        SessionData for authenticated admin

    Raises:
        HTTPException: If not authenticated or not admin
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )

    if session.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return session
