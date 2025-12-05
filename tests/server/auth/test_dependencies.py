"""Tests for cookie-based authentication in get_current_user()."""

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
import sys


@pytest.fixture(autouse=True)
def fake_app_module(monkeypatch):
    """Provide a lightweight fake app module with token blacklist functions.

    This avoids importing the full FastAPI app during these unit tests while
    preserving the blacklist behavior expected by dependencies.get_current_user.
    """
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
def setup_auth_env(tmp_path, user_manager):
    """Set real managers on dependencies module and ensure OAuth disabled."""
    # Use a deterministic secret for tests
    jwt_secret = "test-cookie-auth-secret-key"
    jwt_mgr = JWTManager(secret_key=jwt_secret)

    deps_module.jwt_manager = jwt_mgr
    deps_module.user_manager = user_manager
    deps_module.oauth_manager = None  # Ensure OAuth does not interfere

    # Reset blacklist between tests
    # Reset blacklist between tests
    sys.modules["code_indexer.server.app"].token_blacklist.clear()

    yield jwt_mgr

    # Cleanup globals
    deps_module.jwt_manager = None
    deps_module.user_manager = None
    deps_module.oauth_manager = None
    sys.modules["code_indexer.server.app"].token_blacklist.clear()


def _make_request_with_cookie(token: Optional[str]) -> Request:
    """Construct a Starlette/FastAPI Request with optional cookie header."""
    headers = []
    if token is not None:
        cookie_header = f"cidx_session={token}"
        headers.append((b"cookie", cookie_header.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    return Request(scope)


def test_get_current_user_from_cookie(setup_auth_env, user_manager):
    """Valid cookie JWT authenticates user."""
    jwt_mgr = setup_auth_env

    # Create user and token
    user_manager.create_user("alice", "StrongP@ssw0rd-1", UserRole.NORMAL_USER)
    token = jwt_mgr.create_token({"username": "alice", "role": "normal_user"})

    # Build request containing cookie
    request = _make_request_with_cookie(token)

    user = deps_module.get_current_user(request=request, credentials=None)
    assert user is not None
    assert user.username == "alice"


def test_get_current_user_bearer_takes_precedence(setup_auth_env, user_manager):
    """Bearer auth is used when both Authorization and cookie are present."""
    jwt_mgr = setup_auth_env

    # Create two users
    user_manager.create_user("cookie_user", "StrongP@ssw0rd-2", UserRole.NORMAL_USER)
    user_manager.create_user("bearer_user", "StrongP@ssw0rd-3", UserRole.NORMAL_USER)

    cookie_token = jwt_mgr.create_token(
        {"username": "cookie_user", "role": "normal_user"}
    )
    bearer_token = jwt_mgr.create_token(
        {"username": "bearer_user", "role": "normal_user"}
    )

    request = _make_request_with_cookie(cookie_token)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=bearer_token
    )

    user = deps_module.get_current_user(request=request, credentials=credentials)
    assert user.username == "bearer_user"  # Bearer takes precedence over cookie


def test_get_current_user_expired_cookie_401(user_manager):
    """Expired cookie returns 401 Unauthorized."""
    # Use a JWT manager that creates already-expired tokens
    jwt_mgr = JWTManager(
        secret_key="expired-cookie-secret", token_expiration_minutes=-1
    )

    deps_module.jwt_manager = jwt_mgr
    deps_module.user_manager = user_manager
    deps_module.oauth_manager = None
    sys.modules["code_indexer.server.app"].token_blacklist.clear()

    user_manager.create_user("bob", "StrongP@ssw0rd-4", UserRole.NORMAL_USER)
    token = jwt_mgr.create_token({"username": "bob", "role": "normal_user"})
    request = _make_request_with_cookie(token)

    with pytest.raises(Exception) as exc:
        deps_module.get_current_user(request=request, credentials=None)

    from fastapi import HTTPException, status

    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in exc.value.detail.lower()


def test_get_current_user_no_auth_401(setup_auth_env):
    """No cookie and no Bearer returns 401 Unauthorized with WWW-Authenticate header."""
    request = _make_request_with_cookie(None)

    with pytest.raises(Exception) as exc:
        deps_module.get_current_user(request=request, credentials=None)

    from fastapi import HTTPException, status

    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "www-authenticate" in {k.lower(): v for k, v in exc.value.headers.items()}


def test_get_current_user_invalid_cookie_401(setup_auth_env):
    """Invalid/malformed cookie returns 401 Unauthorized."""
    request = _make_request_with_cookie("not-a-real-jwt")

    with pytest.raises(Exception) as exc:
        deps_module.get_current_user(request=request, credentials=None)

    from fastapi import HTTPException, status

    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid token" in exc.value.detail.lower()


def test_get_current_user_blacklisted_cookie_401(setup_auth_env, user_manager):
    """Blacklisted cookie token returns 401 Unauthorized."""
    jwt_mgr = setup_auth_env

    user_manager.create_user("carol", "StrongP@ssw0rd-5", UserRole.NORMAL_USER)
    token = jwt_mgr.create_token({"username": "carol", "role": "normal_user"})

    # Blacklist the token by its JTI
    payload = jwt_mgr.validate_token(token)
    jti = payload.get("jti")
    assert jti
    sys.modules["code_indexer.server.app"].blacklist_token(jti)

    request = _make_request_with_cookie(token)

    with pytest.raises(Exception) as exc:
        deps_module.get_current_user(request=request, credentials=None)

    from fastapi import HTTPException, status

    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "revoked" in exc.value.detail.lower()
