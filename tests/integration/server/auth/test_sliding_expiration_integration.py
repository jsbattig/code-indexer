"""Integration tests for sliding expiration behavior on JWT cookies.

Covers both /mcp and /mcp-public endpoints and ensures Bearer auth is unaffected.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, cast

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt


def _make_cookie_token(secret: str, algorithm: str, claims: Dict[str, Any]) -> str:
    return cast(str, jose_jwt.encode(claims, secret, algorithm=algorithm))


@pytest.fixture
def client():
    from code_indexer.server.app import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def jwt_env():
    import code_indexer.server.auth.dependencies as deps

    assert deps.jwt_manager is not None
    return deps.jwt_manager


def test_sliding_expiration_refreshes_old_cookie(client: TestClient, jwt_env):
    """Old (>50% lifetime elapsed) cookie triggers Set-Cookie refresh on /mcp."""
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=jwt_env.token_expiration_minutes)

    iat = (now - lifetime * 0.6).timestamp()  # 60% elapsed
    exp = (now + lifetime * 0.4).timestamp()  # still valid

    claims = {
        "username": "admin",
        "role": "admin",
        "created_at": now.isoformat(),
        "iat": iat,
        "exp": exp,
        "jti": "old-jti-1",
    }
    token = _make_cookie_token(jwt_env.secret_key, jwt_env.algorithm, claims)

    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Cookie": f"cidx_session={token}"},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie")
    assert set_cookie is not None and "cidx_session=" in set_cookie


def test_sliding_expiration_no_refresh_fresh_cookie(client: TestClient, jwt_env):
    """Fresh (<50% elapsed) cookie does not trigger Set-Cookie on /mcp."""
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=jwt_env.token_expiration_minutes)

    iat = (now - lifetime * 0.2).timestamp()  # 20% elapsed
    exp = (now + lifetime * 0.8).timestamp()

    claims = {
        "username": "admin",
        "role": "admin",
        "created_at": now.isoformat(),
        "iat": iat,
        "exp": exp,
        "jti": "old-jti-2",
    }
    token = _make_cookie_token(jwt_env.secret_key, jwt_env.algorithm, claims)

    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "initialize"},
        headers={"Cookie": f"cidx_session={token}"},
    )

    assert resp.status_code == 200
    assert resp.headers.get("set-cookie") is None


def test_sliding_expiration_bearer_not_affected(client: TestClient, jwt_env):
    """Bearer auth should not trigger any cookie refresh even if cookie exists."""
    # Create an old cookie
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=jwt_env.token_expiration_minutes)
    iat = (now - lifetime * 0.7).timestamp()
    exp = (now + lifetime * 0.3).timestamp()
    cookie_claims = {
        "username": "admin",
        "role": "admin",
        "created_at": now.isoformat(),
        "iat": iat,
        "exp": exp,
        "jti": "old-jti-3",
    }
    cookie_token = _make_cookie_token(
        jwt_env.secret_key, jwt_env.algorithm, cookie_claims
    )

    # Create a Bearer token (fresh)
    bearer_token = jwt_env.create_token(
        {"username": "admin", "role": "admin", "created_at": now.isoformat()}
    )

    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "initialize"},
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Cookie": f"cidx_session={cookie_token}",
        },
    )

    assert resp.status_code == 200
    # No cookie refresh should occur because Bearer auth took precedence
    assert resp.headers.get("set-cookie") is None


def test_sliding_expiration_works_on_mcp_public(client: TestClient, jwt_env):
    """/mcp-public should also refresh old cookies."""
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=jwt_env.token_expiration_minutes)
    iat = (now - lifetime * 0.6).timestamp()
    exp = (now + lifetime * 0.4).timestamp()
    claims = {
        "username": "admin",
        "role": "admin",
        "created_at": now.isoformat(),
        "iat": iat,
        "exp": exp,
        "jti": "old-jti-4",
    }
    token = _make_cookie_token(jwt_env.secret_key, jwt_env.algorithm, claims)

    resp = client.post(
        "/mcp-public",
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        headers={"Cookie": f"cidx_session={token}"},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie")
    assert set_cookie is not None and "cidx_session=" in set_cookie
