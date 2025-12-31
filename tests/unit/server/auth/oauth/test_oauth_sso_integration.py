"""Unit tests for OAuth SSO integration.

Tests the integration between OAuth authorization flow and OIDC authentication,
including the SSO button on authorization form and the /oauth/authorize/sso endpoint.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import hashlib
import base64
import secrets
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


class TestOAuthAuthorizeViaSSO:
    """Test suite for /oauth/authorize/sso endpoint."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        temp_base = Path(tempfile.mkdtemp())
        db_dir = temp_base / "db"
        db_dir.mkdir()

        paths = {
            "oauth_db": str(db_dir / "oauth.db"),
        }

        yield paths
        shutil.rmtree(temp_base, ignore_errors=True)

    @pytest.fixture
    def test_app(self, temp_dirs):
        """Create test FastAPI app with OAuth routes and OIDC mocking."""
        from code_indexer.server.auth.oauth.routes import (
            router as oauth_router,
            get_oauth_manager,
        )
        from code_indexer.server.auth.oauth.oauth_manager import OAuthManager

        # Create test OAuth manager
        test_oauth_manager = OAuthManager(
            db_path=temp_dirs["oauth_db"], issuer="http://localhost:8000"
        )

        app = FastAPI()
        app.include_router(oauth_router)

        # Override dependencies
        app.dependency_overrides[get_oauth_manager] = lambda: test_oauth_manager

        return TestClient(app), test_oauth_manager

    @pytest.fixture
    def registered_client(self, test_app):
        """Register a test client."""
        _, oauth_manager = test_app
        return oauth_manager.register_client(
            client_name="Test Client",
            redirect_uris=["http://localhost:3000/callback"],
        )

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

    def test_authorize_sso_requires_oidc_enabled(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that /oauth/authorize/sso returns 404 when OIDC is disabled."""
        from code_indexer.server.auth.oidc import routes as oidc_routes

        client, _ = test_app
        _, code_challenge = pkce_pair

        # Mock OIDC as disabled
        original_oidc_manager = oidc_routes.oidc_manager
        try:
            oidc_routes.oidc_manager = None

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://localhost:3000/callback",
                    "response_type": "code",
                    "code_challenge": code_challenge,
                    "state": "test_state",
                },
            )

            assert response.status_code == 404
            assert "SSO authentication not configured" in response.text

        finally:
            oidc_routes.oidc_manager = original_oidc_manager

    def test_authorize_sso_validates_client_id(self, test_app, pkce_pair):
        """Test that /oauth/authorize/sso validates client_id exists."""
        from code_indexer.server.auth.oidc import routes as oidc_routes

        client, _ = test_app
        _, code_challenge = pkce_pair

        # Mock OIDC as enabled
        mock_oidc_manager = MagicMock()
        mock_oidc_manager.is_enabled.return_value = True
        mock_oidc_manager.ensure_provider_initialized = AsyncMock()

        original_oidc_manager = oidc_routes.oidc_manager
        try:
            oidc_routes.oidc_manager = mock_oidc_manager

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": "invalid-client-id",
                    "redirect_uri": "http://localhost:3000/callback",
                    "response_type": "code",
                    "code_challenge": code_challenge,
                    "state": "test_state",
                },
            )

            assert response.status_code == 401

        finally:
            oidc_routes.oidc_manager = original_oidc_manager

    def test_authorize_sso_validates_redirect_uri(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that /oauth/authorize/sso validates redirect_uri matches registered URIs."""
        from code_indexer.server.auth.oidc import routes as oidc_routes

        client, _ = test_app
        _, code_challenge = pkce_pair

        # Mock OIDC as enabled
        mock_oidc_manager = MagicMock()
        mock_oidc_manager.is_enabled.return_value = True
        mock_oidc_manager.ensure_provider_initialized = AsyncMock()

        original_oidc_manager = oidc_routes.oidc_manager
        try:
            oidc_routes.oidc_manager = mock_oidc_manager

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://evil.com/callback",  # Not registered
                    "response_type": "code",
                    "code_challenge": code_challenge,
                    "state": "test_state",
                },
            )

            assert response.status_code == 400
            assert "Invalid redirect_uri" in response.text

        finally:
            oidc_routes.oidc_manager = original_oidc_manager

    def test_authorize_sso_requires_pkce(self, test_app, registered_client):
        """Test that /oauth/authorize/sso requires PKCE code_challenge."""
        from code_indexer.server.auth.oidc import routes as oidc_routes

        client, _ = test_app

        # Mock OIDC as enabled
        mock_oidc_manager = MagicMock()
        mock_oidc_manager.is_enabled.return_value = True
        mock_oidc_manager.ensure_provider_initialized = AsyncMock()

        original_oidc_manager = oidc_routes.oidc_manager
        try:
            oidc_routes.oidc_manager = mock_oidc_manager

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://localhost:3000/callback",
                    "response_type": "code",
                    "state": "test_state",
                    # No code_challenge
                },
            )

            # FastAPI returns 422 for missing required query parameters
            assert response.status_code == 422

        finally:
            oidc_routes.oidc_manager = original_oidc_manager

    def test_authorize_sso_initializes_oidc_provider(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that /oauth/authorize/sso initializes OIDC provider before use."""
        from code_indexer.server.auth.oidc import routes as oidc_routes
        from code_indexer.server.auth.oidc.state_manager import StateManager

        client, _ = test_app
        _, code_challenge = pkce_pair

        # Mock OIDC manager with provider
        mock_oidc_manager = MagicMock()
        mock_oidc_manager.is_enabled.return_value = True
        mock_oidc_manager.ensure_provider_initialized = AsyncMock()

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.get_authorization_url.return_value = (
            "http://oidc.example.com/authorize?state=abc"
        )
        mock_oidc_manager.provider = mock_provider

        original_oidc_manager = oidc_routes.oidc_manager
        original_state_manager = oidc_routes.state_manager
        try:
            oidc_routes.oidc_manager = mock_oidc_manager
            oidc_routes.state_manager = (
                StateManager()
            )  # Need real state manager for state creation

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://localhost:3000/callback",
                    "response_type": "code",
                    "code_challenge": code_challenge,
                    "state": "test_state",
                },
                follow_redirects=False,  # Don't follow redirects
            )

            # Should have called ensure_provider_initialized
            mock_oidc_manager.ensure_provider_initialized.assert_called_once()

            # Should redirect to OIDC provider (302 or 307)
            assert response.status_code in [302, 307]
            assert "oidc.example.com" in response.headers["location"]

        finally:
            oidc_routes.oidc_manager = original_oidc_manager
            oidc_routes.state_manager = original_state_manager

    def test_authorize_sso_handles_provider_initialization_error(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that /oauth/authorize/sso handles OIDC provider initialization errors."""
        from code_indexer.server.auth.oidc import routes as oidc_routes

        client, _ = test_app
        _, code_challenge = pkce_pair

        # Mock OIDC manager that fails to initialize
        mock_oidc_manager = MagicMock()
        mock_oidc_manager.is_enabled.return_value = True
        mock_oidc_manager.ensure_provider_initialized = AsyncMock(
            side_effect=Exception("Failed to connect to OIDC provider")
        )

        original_oidc_manager = oidc_routes.oidc_manager
        try:
            oidc_routes.oidc_manager = mock_oidc_manager

            response = client.get(
                "/oauth/authorize/sso",
                params={
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://localhost:3000/callback",
                    "response_type": "code",
                    "code_challenge": code_challenge,
                    "state": "test_state",
                },
            )

            assert response.status_code == 503
            assert "SSO provider is currently unavailable" in response.text

        finally:
            oidc_routes.oidc_manager = original_oidc_manager
