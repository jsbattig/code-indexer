"""
Unit tests for browser-based OAuth authorization flow.

Tests for GET /oauth/authorize (HTML form) and POST /oauth/authorize (Form data with redirect).

Following TDD: Write failing tests first, then implement to make them pass.
Following CLAUDE.md: Zero mocking - real UserManager, real OAuthManager.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import hashlib
import base64
import secrets
from fastapi.testclient import TestClient
from fastapi import FastAPI

from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.oauth.oauth_manager import OAuthManager


class TestBrowserBasedOAuthFlow:
    """Test suite for browser-based OAuth flow (GET authorize + POST with Form data)."""

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
    def test_app(self, temp_dirs):
        """Create test FastAPI app with OAuth routes and dependency overrides."""
        from code_indexer.server.auth.oauth.routes import (
            router as oauth_router,
            get_user_manager,
            get_oauth_manager,
        )

        # Create test instances
        test_user_manager = UserManager(users_file_path=temp_dirs["users_file"])
        test_user_manager.create_user(
            "testuser", "ValidPassword123!", UserRole.NORMAL_USER
        )

        test_oauth_manager = OAuthManager(db_path=temp_dirs["oauth_db"])

        app = FastAPI()
        app.include_router(oauth_router)

        # Override dependencies
        app.dependency_overrides[get_user_manager] = lambda: test_user_manager
        app.dependency_overrides[get_oauth_manager] = lambda: test_oauth_manager

        return TestClient(app)

    @pytest.fixture
    def registered_client(self, test_app):
        """Register a test client and return client details."""
        response = test_app.post(
            "/oauth/register",
            json={
                "client_name": "Test MCP Client",
                "redirect_uris": ["https://claude.ai/oauth/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            },
        )
        assert response.status_code == 200
        return response.json()

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

    # ============================================================================
    # TEST 1: GET /oauth/authorize returns HTML form with proper structure
    # ============================================================================
    def test_get_authorize_returns_html_form(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that GET /oauth/authorize returns HTML login form with hidden fields."""
        code_verifier, code_challenge = pkce_pair
        client_id = registered_client["client_id"]

        # GET request to /oauth/authorize with query parameters
        response = test_app.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/oauth/callback",
                "code_challenge": code_challenge,
                "response_type": "code",
                "state": "random_state_123",
            },
        )

        # Should return HTML (200 OK)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # HTML should contain form that POSTs to /oauth/authorize
        html = response.text
        assert "<form" in html
        assert 'method="post"' in html.lower() or "method=post" in html.lower()
        assert 'action="/oauth/authorize"' in html or "action=/oauth/authorize" in html

        # Form should have hidden fields for OAuth parameters
        assert 'name="client_id"' in html
        assert f'value="{client_id}"' in html
        assert 'name="redirect_uri"' in html
        assert 'value="https://claude.ai/oauth/callback"' in html
        assert 'name="code_challenge"' in html
        assert f'value="{code_challenge}"' in html
        assert 'name="response_type"' in html
        assert 'value="code"' in html
        assert 'name="state"' in html
        assert 'value="random_state_123"' in html

        # Form should have username and password input fields
        assert 'name="username"' in html
        assert 'name="password"' in html
        assert 'type="password"' in html

        # CRITICAL: Form must have submit button
        assert "<button" in html.lower(), "HTML missing button tag"
        assert 'type="submit"' in html.lower(), "Button missing type=submit"
        assert "Authorize" in html, "Button missing 'Authorize' text"

    # ============================================================================
    # TEST 2: POST /oauth/authorize with Form data returns redirect
    # ============================================================================
    def test_post_authorize_with_form_data_returns_redirect(
        self, test_app, registered_client, pkce_pair
    ):
        """Test that POST /oauth/authorize with Form data returns 302 redirect to callback URL."""
        code_verifier, code_challenge = pkce_pair
        client_id = registered_client["client_id"]

        # POST form data to /oauth/authorize
        response = test_app.post(
            "/oauth/authorize",
            data={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/oauth/callback",
                "code_challenge": code_challenge,
                "response_type": "code",
                "state": "random_state_123",
                "username": "testuser",
                "password": "ValidPassword123!",
            },
            follow_redirects=False,
        )

        # Should return 302 redirect
        assert response.status_code == 302

        # Should have Location header with callback URL
        assert "Location" in response.headers
        location = response.headers["Location"]

        # Location should start with redirect_uri
        assert location.startswith("https://claude.ai/oauth/callback")

        # Location should contain code and state query parameters
        assert "?code=" in location or "&code=" in location
        assert "state=random_state_123" in location
