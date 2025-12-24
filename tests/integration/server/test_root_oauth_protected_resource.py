"""Integration tests for root-level OAuth Protected Resource Metadata endpoint.

RFC 9728 compliance test: OAuth Protected Resource Metadata must be available at
/.well-known/oauth-protected-resource for MCP draft specification compatibility.
"""

import os
import pytest
from fastapi.testclient import TestClient
from code_indexer.server.app import app


class TestRootOAuthProtectedResource:
    """Test suite for root-level OAuth Protected Resource Metadata endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)

    def test_protected_resource_endpoint_exists(self, client):
        """Test that /.well-known/oauth-protected-resource exists at root level."""
        response = client.get("/.well-known/oauth-protected-resource")
        assert (
            response.status_code == 200
        ), "Root-level OAuth Protected Resource Metadata endpoint must return 200 OK for RFC 9728 compliance"

    def test_protected_resource_returns_valid_metadata(self, client):
        """Test that protected resource endpoint returns valid RFC 9728 metadata."""
        response = client.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 200
        data = response.json()

        # Verify required RFC 9728 fields
        assert "resource" in data, "Missing required field: resource"
        assert (
            "authorization_servers" in data
        ), "Missing required field: authorization_servers"
        assert (
            "bearer_methods_supported" in data
        ), "Missing required field: bearer_methods_supported"
        assert "scopes_supported" in data, "Missing required field: scopes_supported"

        # Verify authorization_servers is a list
        assert isinstance(
            data["authorization_servers"], list
        ), "authorization_servers must be a list"
        assert (
            len(data["authorization_servers"]) > 0
        ), "authorization_servers must not be empty"

        # Verify bearer_methods_supported includes "header"
        assert (
            "header" in data["bearer_methods_supported"]
        ), "Must support header bearer method"

        # Verify scopes_supported includes MCP scopes
        assert "mcp:read" in data["scopes_supported"], "Must support mcp:read scope"
        assert "mcp:write" in data["scopes_supported"], "Must support mcp:write scope"

    def test_protected_resource_uses_cidx_issuer_url(self, client):
        """Test that protected resource metadata uses CIDX_ISSUER_URL environment variable."""
        # Get current value or default
        expected_issuer = os.getenv("CIDX_ISSUER_URL", "http://localhost:8000")

        response = client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200
        data = response.json()

        # Verify resource and authorization_servers use the issuer URL
        assert (
            data["resource"] == expected_issuer
        ), f"resource should be {expected_issuer}"
        assert (
            expected_issuer in data["authorization_servers"]
        ), f"authorization_servers should include {expected_issuer}"

    def test_protected_resource_documentation_link(self, client):
        """Test that protected resource metadata includes resource_documentation."""
        response = client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200
        data = response.json()

        assert (
            "resource_documentation" in data
        ), "Missing optional field: resource_documentation"
        assert (
            data["resource_documentation"] == "https://github.com/jsbattig/code-indexer"
        ), "resource_documentation should point to GitHub repository"
