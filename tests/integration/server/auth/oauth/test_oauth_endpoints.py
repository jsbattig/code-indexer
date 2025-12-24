"""Integration tests for OAuth 2.1 FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
import hashlib
import base64
import secrets
from pathlib import Path
import tempfile
import shutil


class TestOAuthEndpointsIntegration:
    """E2E integration tests for OAuth endpoints."""

    @pytest.fixture(autouse=True)
    def reset_rate_limiters(self):
        """Reset global rate limiters before each test to ensure test isolation."""
        from code_indexer.server.auth.oauth_rate_limiter import (
            oauth_token_rate_limiter,
            oauth_register_rate_limiter,
        )

        oauth_token_rate_limiter._attempts.clear()
        oauth_register_rate_limiter._attempts.clear()
        yield
        # Clean up after test as well
        oauth_token_rate_limiter._attempts.clear()
        oauth_register_rate_limiter._attempts.clear()

    @pytest.fixture
    def temp_oauth_db(self):
        """Create temporary OAuth database."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "oauth_test.db"
        yield str(db_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def oauth_manager(self, temp_oauth_db):
        """Create shared OAuth manager instance."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthManager

        return OAuthManager(db_path=temp_oauth_db, issuer="http://localhost:8000")

    @pytest.fixture
    def app(self, oauth_manager):
        """Create FastAPI test client with shared OAuth manager."""
        from fastapi import FastAPI
        from code_indexer.server.auth.oauth import routes

        # Use FastAPI dependency_overrides (NOT mocking)
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.get_oauth_manager] = lambda: oauth_manager
        return TestClient(app)

    @pytest.fixture
    def pkce_pair(self):
        """Generate PKCE code verifier and challenge."""
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return code_verifier, code_challenge

    def test_discovery_endpoint_returns_metadata(self, app):
        """Test OAuth discovery endpoint."""
        response = app.get("/oauth/.well-known/oauth-authorization-server")

        assert response.status_code == 200
        data = response.json()
        assert data["issuer"] == "http://localhost:8000"
        assert data["authorization_endpoint"] == "http://localhost:8000/oauth/authorize"
        assert data["token_endpoint"] == "http://localhost:8000/oauth/token"
        assert data["registration_endpoint"] == "http://localhost:8000/oauth/register"
        assert "S256" in data["code_challenge_methods_supported"]

    def test_client_registration(self, app):
        """Test dynamic client registration."""
        response = app.post(
            "/oauth/register",
            json={
                "client_name": "Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "client_id" in data
        assert data["client_name"] == "Test Client"
        assert data["redirect_uris"] == ["https://example.com/callback"]
        assert data["client_secret_expires_at"] == 0

    def test_complete_oauth_flow(self, app, oauth_manager, pkce_pair):
        """Test complete OAuth flow: register → authorize → exchange."""
        code_verifier, code_challenge = pkce_pair

        # Step 1: Register client
        reg_response = app.post(
            "/oauth/register",
            json={
                "client_name": "E2E Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        assert reg_response.status_code == 200
        client_id = reg_response.json()["client_id"]

        # Step 2: Generate authorization code
        auth_code = oauth_manager.generate_authorization_code(
            client_id=client_id,
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="state123",
        )

        # Step 3: Exchange code for token (OAuth 2.1 spec requires form data)
        token_response = app.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": code_verifier,
                "client_id": client_id,
            },
        )

        assert token_response.status_code == 200
        token_data = token_response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
        assert token_data["expires_in"] == 28800  # 8 hours
        assert "refresh_token" in token_data

    def test_token_exchange_with_invalid_pkce_fails(
        self, app, oauth_manager, pkce_pair
    ):
        """Test that invalid PKCE verifier fails token exchange."""
        code_verifier, code_challenge = pkce_pair

        # Register client
        reg_response = app.post(
            "/oauth/register",
            json={
                "client_name": "PKCE Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        client_id = reg_response.json()["client_id"]

        # Generate auth code
        auth_code = oauth_manager.generate_authorization_code(
            client_id=client_id,
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="state123",
        )

        # Try to exchange with wrong verifier
        token_response = app.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": "wrong_verifier",
                "client_id": client_id,
            },
        )

        assert token_response.status_code == 401
        assert "invalid_grant" in str(token_response.json())

    def test_refresh_token_grant_type(self, app, oauth_manager, pkce_pair):
        """Test refresh_token grant type exchanges for new tokens."""
        code_verifier, code_challenge = pkce_pair

        # Register client
        reg_response = app.post(
            "/oauth/register",
            json={
                "client_name": "Refresh Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        client_id = reg_response.json()["client_id"]

        # Get initial tokens
        auth_code = oauth_manager.generate_authorization_code(
            client_id=client_id,
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="state123",
        )

        token_response = app.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": code_verifier,
                "client_id": client_id,
            },
        )
        tokens = token_response.json()

        # Use refresh token
        refresh_response = app.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )

        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["access_token"] != tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]
        assert new_tokens["token_type"] == "Bearer"

    def test_token_endpoint_requires_refresh_token_for_refresh_grant(self, app):
        """Test that refresh_token grant requires refresh_token parameter."""
        response = app.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "test_client",
                # Missing refresh_token parameter
            },
        )

        assert response.status_code == 400
        assert "refresh_token required" in str(response.json())

    def test_token_endpoint_accepts_form_encoded_data_oauth21_compliance(
        self, app, oauth_manager, pkce_pair
    ):
        """Test that token endpoint accepts application/x-www-form-urlencoded (OAuth 2.1 spec).

        OAuth 2.1 specification mandates that the token endpoint MUST accept
        application/x-www-form-urlencoded data, not JSON.
        """
        code_verifier, code_challenge = pkce_pair

        # Register client
        reg_response = app.post(
            "/oauth/register",
            json={
                "client_name": "Form Data Test Client",
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        client_id = reg_response.json()["client_id"]

        # Generate auth code
        auth_code = oauth_manager.generate_authorization_code(
            client_id=client_id,
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="state123",
        )

        # Exchange code for token using form-encoded data
        # This is the OAuth 2.1 compliant way
        response = app.post(
            "/oauth/token",
            data={  # Using 'data' parameter sends application/x-www-form-urlencoded
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": code_verifier,
                "client_id": client_id,
            },
        )

        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
