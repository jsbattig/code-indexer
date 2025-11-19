"""
Complete end-to-end OAuth 2.1 flow test for Story #478.

Tests all acceptance criteria with real integrations.
Following CLAUDE.md: Zero mocking - real UserManager, real OAuth manager, real database.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import hashlib
import base64
import secrets
from fastapi.testclient import TestClient

from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.oauth.oauth_manager import OAuthManager


class TestOAuthCompleteFlowStory478:
    """Complete OAuth 2.1 flow testing all Story #478 acceptance criteria."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        temp_base = Path(tempfile.mkdtemp())
        db_dir = temp_base / "db"
        users_dir = temp_base / "users"
        db_dir.mkdir()
        users_dir.mkdir()

        paths = {
            "oauth_db": str(db_dir / "oauth.db"),
            "users_file": str(users_dir / "users.json"),
        }

        yield paths
        shutil.rmtree(temp_base, ignore_errors=True)

    @pytest.fixture
    def test_app(self, temp_dirs, test_user):
        """Create test FastAPI app with OAuth routes and dependency overrides."""
        from fastapi import FastAPI
        from code_indexer.server.auth.oauth.routes import (
            router as oauth_router,
            get_user_manager,
            get_oauth_manager,
        )

        # Create custom UserManager and OAuthManager with test paths
        test_user_manager = UserManager(users_file_path=temp_dirs["users_file"])
        test_oauth_manager = OAuthManager(db_path=temp_dirs["oauth_db"])

        app = FastAPI()
        app.include_router(oauth_router)

        # Override dependencies to use test instances
        app.dependency_overrides[get_user_manager] = lambda: test_user_manager
        app.dependency_overrides[get_oauth_manager] = lambda: test_oauth_manager

        return TestClient(app)

    @pytest.fixture
    def test_user(self, temp_dirs):
        """Create test user."""
        um = UserManager(users_file_path=temp_dirs["users_file"])
        um.create_user("testuser", "ValidPassword123!", UserRole.NORMAL_USER)
        return {"username": "testuser", "password": "ValidPassword123!"}

    def test_complete_oauth_flow_all_endpoints(self, test_app, test_user):
        """
        Test complete OAuth flow: Register → Authorize → Token → Use → Refresh → Revoke

        This tests ALL acceptance criteria from Story #478.
        """
        # Step 1: Discover OAuth endpoints (AC: Discovery)
        response = test_app.get("/oauth/.well-known/oauth-authorization-server")
        assert response.status_code == 200
        discovery = response.json()
        assert (
            discovery["authorization_endpoint"]
            == "http://localhost:8000/oauth/authorize"
        )
        assert discovery["token_endpoint"] == "http://localhost:8000/oauth/token"
        assert (
            discovery["registration_endpoint"] == "http://localhost:8000/oauth/register"
        )
        assert "S256" in discovery["code_challenge_methods_supported"]

        # Step 2: Register client (AC: Dynamic client registration)
        response = test_app.post(
            "/oauth/register",
            json={
                "client_name": "Test MCP Client",
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            },
        )
        assert response.status_code == 200
        client = response.json()
        assert "client_id" in client
        client_id = client["client_id"]

        # Step 3: Generate PKCE pair
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # Step 4: Authorize with user credentials (AC: Authorization code flow with PKCE)
        response = test_app.post(
            "/oauth/authorize",
            json={
                "client_id": client_id,
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "code_challenge": code_challenge,
                "state": "random_state_123",
                "username": test_user["username"],
                "password": test_user["password"],
            },
        )
        assert response.status_code == 200
        auth_data = response.json()
        assert "code" in auth_data
        assert auth_data["state"] == "random_state_123"
        auth_code = auth_data["code"]

        # Step 5: Exchange authorization code for tokens (AC: Token exchange with PKCE)
        # OAuth 2.1 spec requires form-encoded data, not JSON
        response = test_app.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": code_verifier,
                "client_id": client_id,
            },
        )
        assert response.status_code == 200
        tokens = response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "Bearer"
        assert "expires_in" in tokens

        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Step 6: Refresh tokens (AC: Token refresh)
        response = test_app.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )
        assert response.status_code == 200
        new_tokens = response.json()
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != access_token  # New token
        assert "refresh_token" in new_tokens

        # Step 7: Revoke token (AC: Token revocation)
        response = test_app.post(
            "/oauth/revoke",
            json={
                "token": new_tokens["access_token"],
                "token_type_hint": "access_token",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_authorization_with_invalid_credentials_fails(self, test_app, test_user):
        """Test that authorization fails with invalid credentials."""
        # Register client first
        response = test_app.post(
            "/oauth/register",
            json={
                "client_name": "Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        client_id = response.json()["client_id"]

        # Generate PKCE
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # Try to authorize with wrong password
        response = test_app.post(
            "/oauth/authorize",
            json={
                "client_id": client_id,
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "code_challenge": code_challenge,
                "state": "state123",
                "username": test_user["username"],
                "password": "WrongPassword123!",
            },
        )
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

    def test_authorization_requires_pkce(self, test_app, test_user):
        """Test that authorization requires PKCE code_challenge."""
        # Register client
        response = test_app.post(
            "/oauth/register",
            json={
                "client_name": "Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        client_id = response.json()["client_id"]

        # Try to authorize without code_challenge
        response = test_app.post(
            "/oauth/authorize",
            json={
                "client_id": client_id,
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "code_challenge": "",  # Empty challenge
                "state": "state123",
                "username": test_user["username"],
                "password": test_user["password"],
            },
        )
        assert response.status_code == 400
        assert "code_challenge required" in response.json()["detail"]

    def test_rate_limiting_on_register_endpoint(self, test_app):
        """Test that register endpoint enforces rate limiting (5 attempts, 15 min lockout)."""
        # Make 5 failed registration attempts (invalid JSON will cause failure)
        for i in range(5):
            response = test_app.post(
                "/oauth/register",
                json={
                    "client_name": "",  # Invalid - empty name will fail
                    "redirect_uris": [],
                },
            )
            # Should get 400 for invalid request
            assert response.status_code == 400

        # 6th attempt should be rate limited
        response = test_app.post(
            "/oauth/register",
            json={
                "client_name": "Valid Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        assert response.status_code == 429
        assert "Try again in" in response.json()["detail"]

    def test_rate_limiting_on_token_endpoint(self, test_app):
        """Test that token endpoint enforces rate limiting (10 attempts, 5 min lockout)."""
        client_id = "test_client_for_rate_limit"

        # Make 10 failed token attempts
        for i in range(10):
            response = test_app.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "invalid_code",
                    "code_verifier": "invalid_verifier",
                    "client_id": client_id,
                },
            )
            # Should get 400 for invalid request
            assert response.status_code in [400, 401]

        # 11th attempt should be rate limited
        response = test_app.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "invalid_code",
                "code_verifier": "invalid_verifier",
                "client_id": client_id,
            },
        )
        assert response.status_code == 429
        assert "Try again in" in response.json()["detail"]
