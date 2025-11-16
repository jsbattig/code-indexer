"""
Unit tests for OAuth token validation in FastAPI authentication dependencies.

Tests that get_current_user() correctly validates both OAuth tokens and JWT tokens,
with OAuth tokens being checked first.

Following CLAUDE.md principles: Real implementations, no mocks.
"""

import pytest
import hashlib
import base64
from pathlib import Path
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.oauth.oauth_manager import OAuthManager
import code_indexer.server.auth.dependencies as deps_module


class TestOAuthTokenValidationInDependencies:
    """Test OAuth token validation in get_current_user() dependency."""

    @pytest.fixture(autouse=True)
    def setup_auth_managers(self, tmp_path):
        """Set up real auth managers for testing."""
        # Create temporary directory for test databases
        test_dir = tmp_path / "test_oauth_deps"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Initialize real managers
        jwt_secret = "test-secret-key-for-oauth-deps-testing"
        self.jwt_manager = JWTManager(secret_key=jwt_secret)
        self.user_manager = UserManager(users_file_path=str(test_dir / "users.json"))
        self.oauth_manager = OAuthManager(
            db_path=str(test_dir / "oauth.db"),
            issuer="http://localhost:8000",
            user_manager=self.user_manager
        )

        # Set global instances in dependencies module
        deps_module.jwt_manager = self.jwt_manager
        deps_module.user_manager = self.user_manager
        deps_module.oauth_manager = self.oauth_manager

        # Create test user
        self.test_username = "testuser"
        self.test_password = "SecureP@ssw0rd!XyZ789"
        self.user_manager.create_user(
            username=self.test_username,
            password=self.test_password,
            role=UserRole.NORMAL_USER
        )

        # Create OAuth client for testing
        self.client_info = self.oauth_manager.register_client(
            client_name="Test Client",
            redirect_uris=["http://localhost/callback"]
        )
        self.client_id = self.client_info["client_id"]

        yield

        # Cleanup
        deps_module.jwt_manager = None
        deps_module.user_manager = None
        deps_module.oauth_manager = None

    def test_get_current_user_validates_oauth_access_token(self):
        """
        Test that get_current_user() successfully validates OAuth access tokens.

        CRITICAL BUG FIX: This test will FAIL initially because get_current_user()
        only validates JWT tokens, not OAuth tokens.
        """
        # Generate OAuth authorization code with PKCE
        code_verifier = "test-verifier-" + "x" * 43
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")

        auth_code = self.oauth_manager.generate_authorization_code(
            client_id=self.client_id,
            user_id=self.test_username,
            code_challenge=code_challenge,
            redirect_uri=self.client_info["redirect_uris"][0],
            state="test-state"
        )

        # Exchange code for OAuth tokens
        token_response = self.oauth_manager.exchange_code_for_token(
            code=auth_code,
            code_verifier=code_verifier,
            client_id=self.client_id
        )

        oauth_access_token = token_response["access_token"]

        # Create credentials with OAuth token
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=oauth_access_token
        )

        # This should validate the OAuth token and return the user
        user = get_current_user(credentials=credentials)

        assert user is not None
        assert user.username == self.test_username
        assert user.role.value == "normal_user"

    def test_get_current_user_falls_back_to_jwt_when_not_oauth(self):
        """
        Test that get_current_user() falls back to JWT validation when token is not OAuth.

        This ensures backward compatibility - existing JWT tokens continue to work.
        """
        # Generate JWT token
        jwt_token = self.jwt_manager.create_token(user_data={
            "username": self.test_username,
            "role": "normal_user"
        })

        # Create credentials with JWT token
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=jwt_token
        )

        # This should validate the JWT token and return the user
        user = get_current_user(credentials=credentials)

        assert user is not None
        assert user.username == self.test_username
        assert user.role.value == "normal_user"
