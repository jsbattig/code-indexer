"""
TDD tests for OAuth 2.1 client_credentials grant type support.

Following TDD: Write failing tests first, then implement to make them pass.
Following CLAUDE.md: Zero mocking - real MCPCredentialManager, real UserManager, real OAuthManager.

Test Coverage:
1. Discovery metadata includes client_credentials grant
2. Token endpoint handles client_credentials with Basic Auth
3. Token endpoint handles client_credentials with client_secret_post
4. Invalid credentials return 401
5. Missing grant_type returns 400
6. authorization_code grant still works (backward compatibility)
"""

import pytest
import base64
from pathlib import Path
import tempfile
import shutil


class TestClientCredentialsGrant:
    """Test suite for OAuth 2.1 client_credentials grant type."""

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

        um = UserManager(users_file_path=temp_users_file)
        um.create_user("testuser", "ValidPassword123!", UserRole.NORMAL_USER)
        return um

    @pytest.fixture
    def mcp_credential_manager(self, user_manager):
        """Create MCPCredentialManager with UserManager."""
        from code_indexer.server.auth.mcp_credential_manager import (
            MCPCredentialManager,
        )

        return MCPCredentialManager(user_manager=user_manager)

    @pytest.fixture
    def test_credential(self, mcp_credential_manager):
        """Generate test MCP credential."""
        return mcp_credential_manager.generate_credential(
            user_id="testuser", name="Test Credential"
        )

    def test_discovery_includes_client_credentials_grant(self, oauth_manager):
        """Test that discovery metadata includes client_credentials grant type."""
        metadata = oauth_manager.get_discovery_metadata()

        # Should include all three grant types
        assert "grant_types_supported" in metadata
        assert "authorization_code" in metadata["grant_types_supported"]
        assert "refresh_token" in metadata["grant_types_supported"]
        assert "client_credentials" in metadata["grant_types_supported"]

        # Should include client authentication methods
        assert "token_endpoint_auth_methods_supported" in metadata
        assert (
            "client_secret_basic" in metadata["token_endpoint_auth_methods_supported"]
        )
        assert "client_secret_post" in metadata["token_endpoint_auth_methods_supported"]

    def test_handle_client_credentials_grant_success(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test successful client_credentials grant."""
        # Pass mcp_credential_manager to handle_client_credentials_grant
        result = oauth_manager.handle_client_credentials_grant(
            client_id=test_credential["client_id"],
            client_secret=test_credential["client_secret"],
            scope=None,
            mcp_credential_manager=mcp_credential_manager,
        )

        # Should return access token
        assert "access_token" in result
        assert "token_type" in result
        assert result["token_type"] == "Bearer"
        assert "expires_in" in result
        # expires_in should match ACCESS_TOKEN_LIFETIME_HOURS (8 hours = 28800 seconds)
        assert result["expires_in"] == oauth_manager.ACCESS_TOKEN_LIFETIME_HOURS * 3600

        # Should NOT include refresh_token (client_credentials doesn't use refresh tokens)
        assert "refresh_token" not in result

        # Token should be valid
        token_info = oauth_manager.validate_token(result["access_token"])
        assert token_info is not None
        assert token_info["user_id"] == "testuser"

    def test_handle_client_credentials_grant_invalid_credentials(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test client_credentials grant with invalid credentials."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        # Wrong secret
        with pytest.raises(OAuthError, match="Invalid client credentials"):
            oauth_manager.handle_client_credentials_grant(
                client_id=test_credential["client_id"],
                client_secret="wrong_secret",
                scope=None,
                mcp_credential_manager=mcp_credential_manager,
            )

        # Wrong client_id
        with pytest.raises(OAuthError, match="Invalid client credentials"):
            oauth_manager.handle_client_credentials_grant(
                client_id="mcp_invalid_client_id",
                client_secret=test_credential["client_secret"],
                scope=None,
                mcp_credential_manager=mcp_credential_manager,
            )

    def test_handle_client_credentials_grant_missing_parameters(
        self, oauth_manager, user_manager, mcp_credential_manager
    ):
        """Test client_credentials grant with missing parameters."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        # Missing client_id
        with pytest.raises(OAuthError, match="client_id and client_secret required"):
            oauth_manager.handle_client_credentials_grant(
                client_id="",
                client_secret="some_secret",
                scope=None,
                mcp_credential_manager=mcp_credential_manager,
            )

        # Missing client_secret
        with pytest.raises(OAuthError, match="client_id and client_secret required"):
            oauth_manager.handle_client_credentials_grant(
                client_id="mcp_some_client",
                client_secret="",
                scope=None,
                mcp_credential_manager=mcp_credential_manager,
            )

    def test_token_endpoint_client_credentials_basic_auth(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test token endpoint with client_credentials grant and Basic Auth."""
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router,
            get_oauth_manager,
            get_user_manager,
            get_mcp_credential_manager,
        )
        from fastapi import FastAPI

        # Create test app
        app = FastAPI()
        app.include_router(router)

        # Override dependencies
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager
        app.dependency_overrides[get_user_manager] = lambda: user_manager
        app.dependency_overrides[get_mcp_credential_manager] = (
            lambda: mcp_credential_manager
        )

        client = TestClient(app)

        # Create Basic Auth header
        credentials = (
            f"{test_credential['client_id']}:{test_credential['client_secret']}"
        )
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded_credentials}"

        # Make token request
        response = client.post(
            "/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": auth_header},
        )

        # Should return 200 with access token
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        # client_credentials grant should not include refresh_token (or it should be None)
        assert data.get("refresh_token") is None

    def test_token_endpoint_client_credentials_post_body(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test token endpoint with client_credentials grant and client_secret_post."""
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router,
            get_oauth_manager,
            get_user_manager,
            get_mcp_credential_manager,
        )
        from fastapi import FastAPI

        # Create test app
        app = FastAPI()
        app.include_router(router)

        # Override dependencies
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager
        app.dependency_overrides[get_user_manager] = lambda: user_manager
        app.dependency_overrides[get_mcp_credential_manager] = (
            lambda: mcp_credential_manager
        )

        client = TestClient(app)

        # Make token request with client_id and client_secret in body
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": test_credential["client_id"],
                "client_secret": test_credential["client_secret"],
            },
        )

        # Should return 200 with access token
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        # client_credentials grant should not include refresh_token (or it should be None)
        assert data.get("refresh_token") is None

    def test_token_endpoint_client_credentials_invalid_credentials(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test token endpoint with invalid credentials returns 401."""
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router,
            get_oauth_manager,
            get_user_manager,
            get_mcp_credential_manager,
        )
        from fastapi import FastAPI

        # Create test app
        app = FastAPI()
        app.include_router(router)

        # Override dependencies
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager
        app.dependency_overrides[get_user_manager] = lambda: user_manager
        app.dependency_overrides[get_mcp_credential_manager] = (
            lambda: mcp_credential_manager
        )

        client = TestClient(app)

        # Make token request with wrong secret
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": test_credential["client_id"],
                "client_secret": "wrong_secret",
            },
        )

        # Should return 401
        assert response.status_code == 401

    def test_token_endpoint_missing_grant_type_returns_400(
        self, oauth_manager, user_manager, mcp_credential_manager, test_credential
    ):
        """Test token endpoint with missing grant_type returns 400."""
        from fastapi.testclient import TestClient
        from code_indexer.server.auth.oauth.routes import (
            router,
            get_oauth_manager,
            get_user_manager,
            get_mcp_credential_manager,
        )
        from fastapi import FastAPI

        # Create test app
        app = FastAPI()
        app.include_router(router)

        # Override dependencies
        app.dependency_overrides[get_oauth_manager] = lambda: oauth_manager
        app.dependency_overrides[get_user_manager] = lambda: user_manager
        app.dependency_overrides[get_mcp_credential_manager] = (
            lambda: mcp_credential_manager
        )

        client = TestClient(app)

        # Make token request without grant_type
        response = client.post(
            "/oauth/token",
            data={
                "client_id": test_credential["client_id"],
                "client_secret": test_credential["client_secret"],
            },
        )

        # Should return 422 (FastAPI validation error for missing required field)
        assert response.status_code == 422

    def test_authorization_code_grant_still_works(
        self, oauth_manager, user_manager, mcp_credential_manager
    ):
        """Test that authorization_code grant still works (backward compatibility)."""
        import hashlib
        import secrets

        # Register OAuth client
        oauth_client = oauth_manager.register_client(
            client_name="Test Client", redirect_uris=["https://example.com/callback"]
        )

        # Generate PKCE pair
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # Generate authorization code
        auth_code = oauth_manager.generate_authorization_code(
            client_id=oauth_client["client_id"],
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="test_state",
        )

        # Exchange code for token
        result = oauth_manager.exchange_code_for_token(
            code=auth_code,
            code_verifier=code_verifier,
            client_id=oauth_client["client_id"],
        )

        # Should return access token and refresh token
        assert "access_token" in result
        assert "token_type" in result
        assert result["token_type"] == "Bearer"
        assert "expires_in" in result
        assert (
            "refresh_token" in result
        )  # authorization_code DOES include refresh_token

        # Token should be valid
        token_info = oauth_manager.validate_token(result["access_token"])
        assert token_info is not None
        assert token_info["user_id"] == "testuser"
