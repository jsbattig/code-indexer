"""
Test OAuth token revocation functionality.

Following TDD and CLAUDE.md: Zero mocking - real database operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import hashlib
import base64
import secrets

from code_indexer.server.auth.oauth.oauth_manager import OAuthManager


class TestOAuthRevoke:
    """Test OAuth token revocation."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "oauth_test.db"
        yield str(db_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def oauth_manager(self, temp_db_path):
        """Create OAuth manager instance."""
        return OAuthManager(db_path=temp_db_path, issuer="http://localhost:8000")

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

    @pytest.fixture
    def valid_token(self, oauth_manager, registered_client, pkce_pair):
        """Get a valid access and refresh token."""
        code_verifier, code_challenge = pkce_pair

        auth_code = oauth_manager.generate_authorization_code(
            client_id=registered_client["client_id"],
            user_id="testuser",
            code_challenge=code_challenge,
            redirect_uri="https://example.com/callback",
            state="test",
        )

        tokens = oauth_manager.exchange_code_for_token(
            code=auth_code,
            code_verifier=code_verifier,
            client_id=registered_client["client_id"],
        )

        return tokens

    def test_revoke_access_token_removes_from_database(
        self, oauth_manager, valid_token
    ):
        """Test that revoking access token removes it from database."""
        access_token = valid_token["access_token"]

        # Verify token is valid before revocation
        token_info = oauth_manager.validate_token(access_token)
        assert token_info is not None

        # Revoke token
        result = oauth_manager.revoke_token(
            access_token, token_type_hint="access_token"
        )
        assert result["username"] == "testuser"
        assert result["token_type"] == "access_token"

        # Verify token is no longer valid
        token_info = oauth_manager.validate_token(access_token)
        assert token_info is None

    def test_revoke_refresh_token_removes_from_database(
        self, oauth_manager, valid_token
    ):
        """Test that revoking refresh token removes it from database."""
        refresh_token = valid_token["refresh_token"]

        # Revoke token
        result = oauth_manager.revoke_token(
            refresh_token, token_type_hint="refresh_token"
        )
        assert result["username"] == "testuser"
        assert result["token_type"] == "refresh_token"

        # Verify refresh token no longer works
        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        with pytest.raises(OAuthError, match="Invalid refresh token"):
            oauth_manager.refresh_access_token(
                refresh_token=refresh_token,
                client_id=valid_token.get("client_id", "test_client"),
            )

    def test_revoke_token_without_hint_finds_token(self, oauth_manager, valid_token):
        """Test that revoke works without token_type_hint."""
        access_token = valid_token["access_token"]

        result = oauth_manager.revoke_token(access_token)
        assert result["username"] == "testuser"
        assert result["token_type"] in ["access_token", "refresh_token"]

    def test_revoke_non_existent_token_returns_none(self, oauth_manager):
        """Test that revoking non-existent token returns None values."""
        result = oauth_manager.revoke_token("invalid_token_12345")
        assert result["username"] is None
        assert result["token_type"] is None

    def test_revoke_access_token_also_removes_refresh_token(
        self, oauth_manager, valid_token
    ):
        """Test that revoking access token removes entire token record (including refresh)."""
        access_token = valid_token["access_token"]
        refresh_token = valid_token["refresh_token"]

        # Revoke access token
        oauth_manager.revoke_token(access_token, token_type_hint="access_token")

        # Both tokens should be invalid
        assert oauth_manager.validate_token(access_token) is None

        from code_indexer.server.auth.oauth.oauth_manager import OAuthError

        with pytest.raises(OAuthError):
            oauth_manager.refresh_access_token(
                refresh_token=refresh_token, client_id="test_client"
            )
