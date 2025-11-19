"""Integration tests for root-level OAuth discovery endpoint.

RFC 8414 compliance test: OAuth discovery must be available at root path
/.well-known/oauth-authorization-server for Claude.ai compatibility.
"""

import pytest
from fastapi.testclient import TestClient
from code_indexer.server.app import app


class TestRootOAuthDiscovery:
    """Test suite for root-level OAuth discovery endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)

    def test_root_discovery_endpoint_exists(self, client):
        """Test that /.well-known/oauth-authorization-server exists at root level."""
        response = client.get("/.well-known/oauth-authorization-server")
        assert (
            response.status_code == 200
        ), "Root-level OAuth discovery endpoint must return 200 OK for RFC 8414 compliance"

    def test_root_discovery_returns_valid_metadata(self, client):
        """Test that root discovery endpoint returns valid OAuth 2.1 metadata."""
        response = client.get("/.well-known/oauth-authorization-server")

        assert response.status_code == 200
        data = response.json()

        # Verify required OAuth 2.1 discovery fields
        assert "issuer" in data, "Missing required field: issuer"
        assert (
            "authorization_endpoint" in data
        ), "Missing required field: authorization_endpoint"
        assert "token_endpoint" in data, "Missing required field: token_endpoint"
        assert "code_challenge_methods_supported" in data
        assert (
            "S256" in data["code_challenge_methods_supported"]
        ), "Must support PKCE S256"

    def test_root_discovery_matches_oauth_prefixed_endpoint(self, client):
        """Test that root discovery returns same metadata as /oauth/ prefixed endpoint."""
        root_response = client.get("/.well-known/oauth-authorization-server")
        oauth_response = client.get("/oauth/.well-known/oauth-authorization-server")

        assert root_response.status_code == 200
        assert oauth_response.status_code == 200

        # Both endpoints should return identical metadata
        root_data = root_response.json()
        oauth_data = oauth_response.json()

        assert (
            root_data == oauth_data
        ), "Root and /oauth/ discovery endpoints must return identical metadata"
