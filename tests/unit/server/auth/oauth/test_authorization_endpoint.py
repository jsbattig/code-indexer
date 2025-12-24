"""
Unit tests for /oauth/authorize endpoint.

Following TDD: tests FIRST, then implementation.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import hashlib
import base64
import secrets


class TestAuthorizationEndpoint:
    """Test suite for /oauth/authorize endpoint functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "oauth_test.db"
        yield str(db_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def temp_users_file(self):
        """Create temporary users file for UserManager."""
        temp_dir = Path(tempfile.mkdtemp())
        users_file = temp_dir / "users.json"
        yield str(users_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def oauth_manager(self, temp_db_path):
        """Create OAuth manager instance for testing."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthManager

        return OAuthManager(db_path=temp_db_path, issuer="http://localhost:8000")

    @pytest.fixture
    def user_manager(self, temp_users_file):
        """Create UserManager instance with test user."""
        from code_indexer.server.auth.user_manager import UserManager, UserRole

        um = UserManager(users_file=temp_users_file)
        um.create_user("testuser", "ValidPassword123!", UserRole.NORMAL_USER)
        return um

    @pytest.fixture
    def registered_client(self, oauth_manager):
        """Register a test client."""
        return oauth_manager.register_client(
            client_name="Test Client", redirect_uris=["https://example.com/callback"]
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

    # TEST 1: PKCE code_challenge validation
    def test_authorization_requires_pkce_challenge(
        self, oauth_manager, registered_client
    ):
        """Test that authorization requires non-empty PKCE code_challenge."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        with pytest.raises(OAuthError, match="code_challenge required"):
            oauth_manager.generate_authorization_code(
                client_id=registered_client["client_id"],
                user_id="testuser",
                code_challenge="",  # Empty challenge
                redirect_uri="https://example.com/callback",
                state="state123",
            )

    # TEST 2: NEW - Invalid client_id in GET /oauth/authorize should return 401 with invalid_client error
    def test_get_authorize_invalid_client_id_returns_401(self, oauth_manager):
        """Test GET /oauth/authorize with invalid client_id returns HTTP 401 with invalid_client error.

        Per OAuth 2.1 spec, when client_id is not found, server MUST return:
        - HTTP 401 Unauthorized
        - JSON body with error="invalid_client" and error_description

        This triggers Claude.ai to re-register via Dynamic Client Registration.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router as oauth_router,
            get_oauth_manager,
        )

        # Create test FastAPI app
        app = FastAPI()
        app.include_router(oauth_router)

        # Override OAuth manager dependency
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager

        client = TestClient(app)

        # Make GET request with unregistered client_id
        response = client.get(
            "/oauth/authorize",
            params={
                "client_id": "invalid_client_123",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "challenge123",
                "response_type": "code",
                "state": "state123",
            },
        )

        # Assert HTTP 401
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

        # Assert JSON error response (FastAPI wraps in 'detail' field)
        response_data = response.json()
        assert "detail" in response_data, "Response must contain 'detail' field"
        error_data = response_data["detail"]
        assert "error" in error_data, "Detail must contain 'error' field"
        assert (
            error_data["error"] == "invalid_client"
        ), f"Expected error='invalid_client', got {error_data['error']}"
        assert (
            "error_description" in error_data
        ), "Detail must contain 'error_description' field"
        assert (
            "not found" in error_data["error_description"].lower()
        ), "Error description should mention 'not found'"

    # TEST 3: NEW - Valid client_id in GET /oauth/authorize should return HTML form
    def test_get_authorize_valid_client_id_returns_form(
        self, oauth_manager, registered_client
    ):
        """Test GET /oauth/authorize with valid client_id returns HTML login form."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router as oauth_router,
            get_oauth_manager,
        )

        # Create test FastAPI app
        app = FastAPI()
        app.include_router(oauth_router)

        # Override OAuth manager dependency
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager

        client = TestClient(app)

        # Make GET request with valid client_id
        response = client.get(
            "/oauth/authorize",
            params={
                "client_id": registered_client["client_id"],
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "challenge123",
                "response_type": "code",
                "state": "state123",
            },
        )

        # Assert HTTP 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Assert HTML response
        assert "text/html" in response.headers["content-type"], "Expected HTML response"
        assert "<form" in response.text, "Expected HTML form in response"
        assert (
            registered_client["client_id"] in response.text
        ), "Form should contain client_id"
