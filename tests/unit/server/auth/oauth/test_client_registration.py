"""
Unit tests for OAuth 2.1 client registration.

Tests Acceptance Criterion 2: Dynamic client registration
"""

import pytest
from pathlib import Path
import tempfile
import shutil


class TestClientRegistration:
    """Test suite for OAuth client registration endpoint."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "oauth_test.db"
        yield str(db_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def oauth_manager(self, temp_db_path):
        """Create OAuth manager instance for testing."""
        from code_indexer.server.auth.oauth.oauth_manager import OAuthManager

        return OAuthManager(db_path=temp_db_path, issuer="http://localhost:8000")

    def test_register_client_generates_client_id(self, oauth_manager):
        """Test that client registration generates a unique client_id."""
        result = oauth_manager.register_client(
            client_name="Claude.ai MCP Client",
            redirect_uris=["https://claude.ai/oauth/callback"]
        )

        assert "client_id" in result
        assert isinstance(result["client_id"], str)
        assert len(result["client_id"]) > 0
