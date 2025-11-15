"""
Unit tests for OAuth 2.1 discovery endpoint.

Tests Acceptance Criterion 1: Discover OAuth endpoints
- Response contains authorization endpoint "/oauth/authorize"
"""

import pytest
from pathlib import Path
import tempfile
import shutil


class TestOAuthDiscovery:
    """Test suite for OAuth discovery endpoint (.well-known/oauth-authorization-server)."""

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

    def test_discovery_endpoint_returns_authorization_endpoint(self, oauth_manager):
        """Test that discovery response contains authorization endpoint."""
        discovery = oauth_manager.get_discovery_metadata()

        assert "authorization_endpoint" in discovery
        assert discovery["authorization_endpoint"] == "http://localhost:8000/oauth/authorize"

    def test_discovery_endpoint_returns_token_endpoint(self, oauth_manager):
        """Test that discovery response contains token endpoint."""
        discovery = oauth_manager.get_discovery_metadata()

        assert "token_endpoint" in discovery
        assert discovery["token_endpoint"] == "http://localhost:8000/oauth/token"

    def test_discovery_endpoint_returns_registration_endpoint(self, oauth_manager):
        """Test that discovery response contains registration endpoint."""
        discovery = oauth_manager.get_discovery_metadata()

        assert "registration_endpoint" in discovery
        assert discovery["registration_endpoint"] == "http://localhost:8000/oauth/register"

    def test_discovery_endpoint_indicates_pkce_required(self, oauth_manager):
        """Test that discovery response indicates PKCE is required."""
        discovery = oauth_manager.get_discovery_metadata()

        assert "code_challenge_methods_supported" in discovery
        assert "S256" in discovery["code_challenge_methods_supported"]
