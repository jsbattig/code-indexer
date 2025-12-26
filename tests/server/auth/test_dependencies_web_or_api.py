"""Tests for get_current_user_web_or_api() dual authentication dependency.

This dependency supports BOTH web UI session authentication AND API authentication:
- Priority 1: Web UI session cookie ("session") via SessionManager
- Priority 2: JWT cookie ("cidx_session") or Bearer token
- Returns 401 if neither present
"""

import os
import json
import tempfile
import pytest
from fastapi import Request
from typing import Optional
from fastapi.security import HTTPAuthorizationCredentials

import code_indexer.server.auth.dependencies as deps_module
from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.web.auth import init_session_manager, SessionManager
import sys


@pytest.fixture(autouse=True)
def fake_app_module(monkeypatch):
    """Provide a lightweight fake app module with token blacklist functions."""
    import types

    fake_app = types.ModuleType("code_indexer.server.app")
    token_blacklist = set()

    def blacklist_token(jti: str) -> None:
        token_blacklist.add(jti)

    def is_token_blacklisted(jti: str) -> bool:
        return jti in token_blacklist

    fake_app.blacklist_token = blacklist_token
    fake_app.is_token_blacklisted = is_token_blacklisted
    fake_app.token_blacklist = token_blacklist

    monkeypatch.setitem(sys.modules, "code_indexer.server.app", fake_app)
    try:
        yield
    finally:
        sys.modules.pop("code_indexer.server.app", None)


@pytest.fixture
def temp_users_file():
    """Create temporary users file."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump({}, f)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture
def user_manager(temp_users_file):
    """Create user manager with temp file."""
    return UserManager(users_file_path=temp_users_file)


@pytest.fixture
def session_manager():
    """Create session manager for web UI auth."""
    return init_session_manager(secret_key="test-web-session-secret")


@pytest.fixture
def setup_auth_env(user_manager, session_manager):
    """Set up authentication environment with both JWT and SessionManager."""
    # JWT manager for API auth
    jwt_secret = "test-dual-auth-secret-key"
    jwt_mgr = JWTManager(secret_key=jwt_secret)

    deps_module.jwt_manager = jwt_mgr
    deps_module.user_manager = user_manager
    deps_module.oauth_manager = None

    # Reset blacklist
    sys.modules["code_indexer.server.app"].token_blacklist.clear()

    yield jwt_mgr

    # Cleanup
    deps_module.jwt_manager = None
    deps_module.user_manager = None
    deps_module.oauth_manager = None
    sys.modules["code_indexer.server.app"].token_blacklist.clear()


def _make_request_with_cookies(
    web_session_cookie: Optional[str] = None,
    jwt_cookie: Optional[str] = None,
) -> Request:
    """Construct a Starlette/FastAPI Request with optional cookies."""
    headers = []
    cookies = []

    if web_session_cookie:
        cookies.append(f"session={web_session_cookie}")

    if jwt_cookie:
        cookies.append(f"cidx_session={jwt_cookie}")

    if cookies:
        cookie_header = "; ".join(cookies)
        headers.append((b"cookie", cookie_header.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/mcp-credentials",
        "headers": headers,
    }
    return Request(scope)


def _make_request_with_bearer(token: str) -> Request:
    """Construct a Request with Bearer token."""
    headers = [
        (b"authorization", f"Bearer {token}".encode("latin-1"))
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/mcp-credentials",
        "headers": headers,
    }
    return Request(scope)


class TestWebSessionAuthentication:
    """Test web UI session authentication (priority 1)."""

    def test_web_session_authenticates_user(
        self, setup_auth_env, user_manager, session_manager
    ):
        """Valid web session cookie authenticates user successfully."""
        # Create user
        user_manager.create_user("alice", "StrongP@ssw0rd-1", UserRole.ADMIN)

        # Create web session using SessionManager
        from fastapi import Response
        response = Response()
        session_manager.create_session(response, username="alice", role="admin")

        # Extract session cookie from response
        set_cookie_header = response.headers.get("set-cookie", "")
        session_cookie_value = None
        if set_cookie_header:
            parts = set_cookie_header.split(";")
            if parts:
                cookie_pair = parts[0].strip()
                if "=" in cookie_pair:
                    _, session_cookie_value = cookie_pair.split("=", 1)

        assert session_cookie_value is not None, "Session cookie should be set"

        # Make request with web session cookie
        request = _make_request_with_cookies(web_session_cookie=session_cookie_value)

        # Call get_current_user_web_or_api
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "alice"
        assert user.role == UserRole.ADMIN

    def test_web_session_for_normal_user(
        self, setup_auth_env, user_manager, session_manager
    ):
        """Web session works for non-admin users."""
        # Create normal user
        user_manager.create_user("bob", "StrongP@ssw0rd-2", UserRole.NORMAL_USER)

        # Create web session
        from fastapi import Response
        response = Response()
        session_manager.create_session(response, username="bob", role="normal_user")

        # Extract session cookie
        set_cookie_header = response.headers.get("set-cookie", "")
        session_cookie_value = None
        if set_cookie_header:
            parts = set_cookie_header.split(";")
            if parts:
                cookie_pair = parts[0].strip()
                if "=" in cookie_pair:
                    _, session_cookie_value = cookie_pair.split("=", 1)

        assert session_cookie_value is not None

        # Make request with web session cookie
        request = _make_request_with_cookies(web_session_cookie=session_cookie_value)

        # Call dependency
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "bob"
        assert user.role == UserRole.NORMAL_USER


class TestJWTFallbackAuthentication:
    """Test JWT/Bearer authentication (priority 2 - fallback)."""

    def test_jwt_cookie_when_no_web_session(
        self, setup_auth_env, user_manager
    ):
        """JWT cookie authenticates when web session absent."""
        jwt_mgr = setup_auth_env

        # Create user
        user_manager.create_user("carol", "StrongP@ssw0rd-3", UserRole.POWER_USER)

        # Create JWT token
        jwt_token = jwt_mgr.create_token(
            {"username": "carol", "role": "power_user"}
        )

        # Make request with JWT cookie (no web session cookie)
        request = _make_request_with_cookies(jwt_cookie=jwt_token)

        # Call dependency
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "carol"
        assert user.role == UserRole.POWER_USER

    def test_bearer_token_when_no_web_session(
        self, setup_auth_env, user_manager
    ):
        """Bearer token authenticates when web session absent."""
        jwt_mgr = setup_auth_env

        # Create user
        user_manager.create_user("dave", "StrongP@ssw0rd-4", UserRole.NORMAL_USER)

        # Create JWT token
        jwt_token = jwt_mgr.create_token(
            {"username": "dave", "role": "normal_user"}
        )

        # Make request with Bearer token
        request = _make_request_with_bearer(jwt_token)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=jwt_token
        )

        # Call dependency
        user = deps_module.get_current_user_web_or_api(request=request, credentials=credentials)

        assert user is not None
        assert user.username == "dave"
        assert user.role == UserRole.NORMAL_USER


class TestAuthenticationPriority:
    """Test priority order: web session > JWT/Bearer."""

    def test_web_session_takes_precedence_over_jwt_cookie(
        self, setup_auth_env, user_manager, session_manager
    ):
        """When both web session and JWT cookie present, web session takes precedence."""
        jwt_mgr = setup_auth_env

        # Create two users
        user_manager.create_user("web_user", "StrongP@ssw0rd-5", UserRole.ADMIN)
        user_manager.create_user("jwt_user", "StrongP@ssw0rd-6", UserRole.NORMAL_USER)

        # Create web session for web_user
        from fastapi import Response
        response = Response()
        session_manager.create_session(response, username="web_user", role="admin")

        set_cookie_header = response.headers.get("set-cookie", "")
        session_cookie_value = None
        if set_cookie_header:
            parts = set_cookie_header.split(";")
            if parts:
                cookie_pair = parts[0].strip()
                if "=" in cookie_pair:
                    _, session_cookie_value = cookie_pair.split("=", 1)

        # Create JWT token for jwt_user
        jwt_token = jwt_mgr.create_token(
            {"username": "jwt_user", "role": "normal_user"}
        )

        # Make request with BOTH cookies
        request = _make_request_with_cookies(
            web_session_cookie=session_cookie_value,
            jwt_cookie=jwt_token
        )

        # Call dependency - should authenticate as web_user (web session takes precedence)
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "web_user"  # Web session wins
        assert user.role == UserRole.ADMIN


class TestAuthenticationFailures:
    """Test 401 errors when authentication fails."""

    def test_no_credentials_returns_401(self, setup_auth_env):
        """No credentials returns 401 Unauthorized."""
        # Make request with no cookies, no Bearer token
        request = _make_request_with_cookies()

        from fastapi import HTTPException, status

        with pytest.raises(HTTPException) as exc:
            deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "www-authenticate" in {k.lower(): v for k, v in exc.value.headers.items()}

    def test_invalid_web_session_falls_back_to_jwt(
        self, setup_auth_env, user_manager
    ):
        """Invalid web session cookie falls back to JWT cookie."""
        jwt_mgr = setup_auth_env

        # Create user
        user_manager.create_user("eve", "StrongP@ssw0rd-7", UserRole.NORMAL_USER)

        # Create valid JWT token
        jwt_token = jwt_mgr.create_token(
            {"username": "eve", "role": "normal_user"}
        )

        # Make request with invalid web session + valid JWT
        request = _make_request_with_cookies(
            web_session_cookie="invalid-session-cookie",
            jwt_cookie=jwt_token
        )

        # Should fall back to JWT and succeed
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "eve"

    def test_expired_web_session_falls_back_to_jwt(
        self, setup_auth_env, user_manager
    ):
        """Expired web session falls back to JWT authentication."""
        jwt_mgr = setup_auth_env

        # Create user
        user_manager.create_user("frank", "StrongP@ssw0rd-8", UserRole.NORMAL_USER)

        # Create valid JWT token
        jwt_token = jwt_mgr.create_token(
            {"username": "frank", "role": "normal_user"}
        )

        # Create expired web session (simulate by using invalid signature)
        # This simulates what happens when session expires
        expired_session = "expired.session.cookie"

        # Make request with expired session + valid JWT
        request = _make_request_with_cookies(
            web_session_cookie=expired_session,
            jwt_cookie=jwt_token
        )

        # Should fall back to JWT and succeed
        user = deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert user is not None
        assert user.username == "frank"

    def test_both_invalid_credentials_returns_401(self, setup_auth_env):
        """Invalid web session AND invalid JWT returns 401."""
        # Make request with invalid credentials
        request = _make_request_with_cookies(
            web_session_cookie="invalid-session",
            jwt_cookie="invalid-jwt-token"
        )

        from fastapi import HTTPException, status

        with pytest.raises(HTTPException) as exc:
            deps_module.get_current_user_web_or_api(request=request, credentials=None)

        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
