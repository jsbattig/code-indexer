"""
Test WWW-Authenticate header on MCP endpoint per RFC 9728.

RFC 9728 Section 5.1 requires that 401 responses include a WWW-Authenticate header
with resource_metadata parameter pointing to OAuth discovery endpoint.

This enables Claude.ai to discover OAuth endpoints for authentication.
"""

import pytest
from fastapi.testclient import TestClient
from src.code_indexer.server.app import create_app


class TestMCPWWWAuthenticateHeader:
    """Test suite for RFC 9728 compliant WWW-Authenticate header on MCP endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with server app."""
        app = create_app()
        return TestClient(app)

    def test_mcp_endpoint_returns_www_authenticate_on_401(self, client):
        """
        Test that POST /mcp returns WWW-Authenticate header with resource_metadata on 401.

        Per RFC 9728 Section 5.1, the header format should be:
        WWW-Authenticate: Bearer resource_metadata="https://server/.well-known/oauth-authorization-server"

        This test verifies:
        1. 401 status when invalid token provided
        2. WWW-Authenticate header is present
        3. Header contains resource_metadata parameter
        4. resource_metadata points to correct OAuth discovery URL
        """
        # Attempt to call MCP endpoint with INVALID authentication token
        # (HTTPBearer with auto_error=True returns 403 for missing auth, but 401 for invalid tokens)
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={"Authorization": "Bearer invalid_token_xyz"}
        )

        # Should return 401 Unauthorized for invalid token
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

        # Should have WWW-Authenticate header
        assert "www-authenticate" in response.headers, "Missing WWW-Authenticate header"

        www_auth = response.headers["www-authenticate"]

        # Should contain resource_metadata parameter
        assert "resource_metadata" in www_auth.lower(), \
            f"WWW-Authenticate header missing resource_metadata: {www_auth}"

        # Should point to OAuth discovery endpoint (/.well-known/oauth-authorization-server)
        assert ".well-known/oauth-authorization-server" in www_auth, \
            f"resource_metadata doesn't point to OAuth discovery: {www_auth}"

        # Verify format matches RFC 9728 pattern
        # Expected: Bearer resource_metadata="https://server/.well-known/oauth-authorization-server"
        assert www_auth.lower().startswith("bearer"), \
            f"WWW-Authenticate should start with 'Bearer': {www_auth}"
