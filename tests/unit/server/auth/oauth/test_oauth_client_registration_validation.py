"""Test client registration validation in OAuthManager."""

import pytest
import tempfile
from pathlib import Path

from code_indexer.server.auth.oauth.oauth_manager import OAuthManager, OAuthError


class TestClientRegistrationValidation:
    """Test that client registration validates required fields."""

    @pytest.fixture
    def oauth_manager(self):
        """Create OAuthManager with temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "oauth.db"
            manager = OAuthManager(db_path=str(db_path))
            yield manager

    def test_register_client_rejects_empty_client_name(self, oauth_manager):
        """Test that register_client rejects empty client_name."""
        with pytest.raises(OAuthError, match="client_name cannot be empty"):
            oauth_manager.register_client(client_name="", redirect_uris=["https://example.com"])
