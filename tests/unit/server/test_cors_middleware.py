"""Unit tests for CORS middleware configuration.

Tests verify that CORS middleware is properly configured to allow
Claude.ai OAuth requests with appropriate headers and methods.
"""

import pytest
from fastapi.testclient import TestClient
from code_indexer.server.app import app


class TestCORSMiddleware:
    """Test suite for CORS middleware configuration."""

    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)

    def test_cors_allows_claude_ai_origin(self, client):
        """Test that CORS allows requests from claude.ai."""
        response = client.options(
            "/.well-known/oauth-authorization-server",
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert (
            response.status_code == 200
        ), "OPTIONS preflight request must return 200 OK"
        assert (
            "access-control-allow-origin" in response.headers
        ), "Missing Access-Control-Allow-Origin header"
        assert (
            response.headers["access-control-allow-origin"] == "https://claude.ai"
        ), "CORS must allow claude.ai origin"

    def test_cors_allows_credentials(self, client):
        """Test that CORS allows credentials for OAuth flows."""
        response = client.options(
            "/oauth/authorize",
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert (
            "access-control-allow-credentials" in response.headers
        ), "Missing Access-Control-Allow-Credentials header"
        assert (
            response.headers["access-control-allow-credentials"] == "true"
        ), "CORS must allow credentials for OAuth"

    def test_cors_allows_all_anthropic_origins(self, client):
        """Test that CORS allows all Anthropic-related origins."""
        allowed_origins = [
            "https://claude.ai",
            "https://claude.com",
            "https://www.anthropic.com",
            "https://api.anthropic.com",
        ]

        for origin in allowed_origins:
            response = client.options(
                "/.well-known/oauth-authorization-server",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert response.status_code == 200, f"Failed for origin {origin}"
            assert (
                response.headers.get("access-control-allow-origin") == origin
            ), f"CORS must allow {origin}"

    def test_cors_applies_to_actual_requests(self, client):
        """Test that actual OAuth requests include CORS headers, not just OPTIONS."""
        response = client.get(
            "/.well-known/oauth-authorization-server",
            headers={
                "Origin": "https://claude.ai",
            },
        )

        assert response.status_code == 200
        assert (
            "access-control-allow-origin" in response.headers
        ), "Actual requests must include CORS headers, not just OPTIONS"
        assert response.headers["access-control-allow-origin"] == "https://claude.ai"

    def test_cors_applies_to_token_endpoint(self, client):
        """Test that token endpoint includes CORS headers even on error responses."""
        response = client.post(
            "/oauth/token",
            headers={
                "Origin": "https://claude.ai",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": "invalid",
            },
        )

        # May return 400/401 due to invalid request, but CORS headers must be present
        assert (
            "access-control-allow-origin" in response.headers
        ), "Token endpoint must include CORS headers even on error responses"
        assert response.headers["access-control-allow-origin"] == "https://claude.ai"
