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
            client_name="Test Client",
            redirect_uris=["https://example.com/callback"]
        )

    @pytest.fixture
    def pkce_pair(self):
        """Generate PKCE code verifier and challenge."""
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        return code_verifier, code_challenge

    # TEST 1: PKCE code_challenge validation
    def test_authorization_requires_pkce_challenge(self, oauth_manager, registered_client):
        """Test that authorization requires non-empty PKCE code_challenge."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        with pytest.raises(OAuthError, match="code_challenge required"):
            oauth_manager.generate_authorization_code(
                client_id=registered_client["client_id"],
                user_id="testuser",
                code_challenge="",  # Empty challenge
                redirect_uri="https://example.com/callback",
                state="state123"
            )
