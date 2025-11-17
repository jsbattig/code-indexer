"""Test MCP endpoint 401 authentication requirement per MCP spec.

This test file verifies the MCP endpoint returns HTTP 401 for unauthenticated
requests as required by the MCP Authorization Specification (RFC 9728).
"""

import pytest


class TestMCP401Authentication:
    """Test MCP endpoint authentication requirements."""

    def test_get_mcp_returns_401_for_unauthenticated_request(self):
        """Test GET /mcp returns 401 Unauthorized without authentication.

        Per MCP specification (RFC 9728), servers MUST return HTTP 401 for
        requests requiring authorization, with WWW-Authenticate header.
        """
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from starlette.testclient import TestClient as StarletteTestClient

        app = create_app()

        # Use Starlette TestClient with stream=True to avoid reading body
        with StarletteTestClient(app) as client:
            # Send GET request without authentication
            with client.stream("GET", "/mcp") as response:
                # Check status code immediately without reading stream
                # MUST return 401 per MCP spec
                assert response.status_code == 401, (
                    f"Expected HTTP 401 Unauthorized per MCP spec (RFC 9728), "
                    f"got {response.status_code}"
                )

                # MUST include WWW-Authenticate header
                assert "www-authenticate" in response.headers, (
                    "Expected WWW-Authenticate header per RFC 9728, "
                    f"got headers: {list(response.headers.keys())}"
                )

                www_auth = response.headers["www-authenticate"]

                # Must use Bearer scheme
                assert www_auth.startswith("Bearer"), (
                    f"Expected Bearer scheme, got: {www_auth}"
                )

                # Must include realm="mcp"
                assert 'realm="mcp"' in www_auth, (
                    f"Expected realm='mcp', got: {www_auth}"
                )

                # Must include resource_metadata with OAuth discovery URL
                assert "resource_metadata=" in www_auth, (
                    f"Expected resource_metadata parameter, got: {www_auth}"
                )

                assert "/.well-known/oauth-authorization-server" in www_auth, (
                    f"Expected OAuth discovery URL, got: {www_auth}"
                )
