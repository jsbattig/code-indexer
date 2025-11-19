"""
Comprehensive unit tests for OAuth 2.1 routes and features.

Following TDD: ONE test at a time, watch it fail, make it pass, then next test.
Following CLAUDE.md: Zero mocking - real UserManager, real audit_logger, real rate_limiter.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import hashlib
import base64
import secrets


class TestAuthorizeEndpoint:
    """Test suite for GET /oauth/authorize endpoint."""

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
        um.create_user("adminuser", "AdminPassword123!", UserRole.ADMIN)
        return um

    @pytest.fixture
    def registered_client(self, oauth_manager):
        """Register a test client."""
        return oauth_manager.register_client(
            client_name="Test Client",
            redirect_uris=[
                "https://example.com/callback",
                "https://app.example.com/oauth/callback",
            ],
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

    def test_authorize_success_valid_client(
        self, oauth_manager, user_manager, registered_client, pkce_pair
    ):
        """Test successful authorization with valid client and user."""
        code_verifier, code_challenge = pkce_pair

        # Generate authorization code
        auth_code = oauth_manager.generate_authorization_code(
            client_id=registered_client["client_id"],
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="random_state_123",
        )

        assert auth_code is not None
        assert len(auth_code) > 20  # Secure token length
