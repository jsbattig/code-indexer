"""Unit tests for sliding expiration helper functions.

TDD Step 1 (RED): Verify _should_refresh_token and _refresh_jwt_cookie behavior.
"""

from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from typing import Optional

from fastapi import Response

import code_indexer.server.auth.dependencies as deps
from code_indexer.server.auth.jwt_manager import JWTManager


def _make_payload(iat: float, exp: float, extra: Optional[dict] = None) -> dict:
    payload = {"iat": iat, "exp": exp}
    if extra:
        payload.update(extra)
    return payload


class TestShouldRefreshToken:
    def test_should_refresh_token_at_50_percent_elapsed(self):
        """If elapsed > 50% of lifetime, returns True."""
        now = datetime.now(timezone.utc).timestamp()
        # Lifetime 1000s, elapsed 600s (>50%)
        iat = now - 600
        exp = iat + 1000
        payload = _make_payload(iat, exp)

        assert deps._should_refresh_token(payload) is True

    def test_should_not_refresh_fresh_token(self):
        """If elapsed < 50% of lifetime, returns False."""
        now = datetime.now(timezone.utc).timestamp()
        # Lifetime 1000s, elapsed 400s (<50%)
        iat = now - 400
        exp = iat + 1000
        payload = _make_payload(iat, exp)

        assert deps._should_refresh_token(payload) is False

    def test_should_refresh_at_exactly_50_percent(self):
        """
        Exactly 50% threshold is treated as refresh due to time drift.
        A negligible clock tick makes elapsed slightly > 50%.
        """
        now = datetime.now(timezone.utc).timestamp()
        # Lifetime 1000s, elapsed 500s (==50%)
        iat = now - 500
        exp = iat + 1000
        payload = _make_payload(iat, exp)

        assert deps._should_refresh_token(payload) is True


class TestRefreshCookie:
    def test_refresh_jwt_cookie_creates_new_token(self, monkeypatch):
        """Calling _refresh_jwt_cookie sets a secure Set-Cookie with new JWT."""
        # Setup a deterministic JWTManager on module under test
        jwt_mgr = JWTManager(secret_key="unit-test-secret", token_expiration_minutes=10)
        deps.jwt_manager = jwt_mgr

        response = Response()
        payload = {
            "username": "alice",
            "role": "normal_user",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "iat": datetime.now(timezone.utc).timestamp(),
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
            "jti": "original-jti",
        }

        deps._refresh_jwt_cookie(response, payload)

        # Validate Set-Cookie header
        set_cookie = response.headers.get("set-cookie", "")
        assert "cidx_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie
        assert "SameSite=Lax" in set_cookie or "samesite=lax" in set_cookie.lower()
        assert "Path=/" in set_cookie

    def test_refresh_preserves_claims_and_rotates_jti(self):
        """Refreshed token keeps claims and generates a new jti."""
        jwt_mgr = JWTManager(
            secret_key="unit-test-secret-2", token_expiration_minutes=10
        )
        deps.jwt_manager = jwt_mgr

        response = Response()
        original_payload = {
            "username": "bob",
            "role": "admin",
            "created_at": "2024-01-01T00:00:00+00:00",
            "iat": datetime.now(timezone.utc).timestamp() - 100,
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
            "jti": "old-jti-123",
        }

        deps._refresh_jwt_cookie(response, original_payload)

        # Extract the cookie value (JWT)
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])  # type: ignore[index]
        token = cookie["cidx_session"].value

        decoded = jwt_mgr.validate_token(token)
        assert decoded["username"] == original_payload["username"]
        assert decoded.get("role") == original_payload["role"]
        assert decoded.get("created_at") == original_payload["created_at"]

        # New jti should be present and different from original payload's jti
        assert decoded.get("jti") is not None
        assert decoded.get("jti") != original_payload["jti"]
