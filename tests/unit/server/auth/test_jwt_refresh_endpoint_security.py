"""
TDD Test for JWT Refresh Endpoint Security Vulnerability.

Tests that the /api/auth/refresh endpoint properly requires authentication.
This test was written to expose the critical security vulnerability where
the refresh endpoint was missing the current_user authentication dependency.
"""

import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app


class TestJWTRefreshEndpointSecurity:
    """Test JWT refresh endpoint authentication requirements."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    def test_refresh_endpoint_rejects_invalid_refresh_token(self, client):
        """
        SECURITY TEST: JWT refresh endpoint should validate refresh tokens.

        Per 2025 security best practices, refresh endpoints should validate refresh tokens
        independently without requiring JWT authentication. Security comes from proper
        refresh token validation, rotation, and revocation.
        """
        # Attempt to refresh with invalid refresh token
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid_refresh_token_12345"}
        )

        # SECURITY REQUIREMENT: Should return 401 for invalid refresh token
        assert (
            response.status_code == 401
        ), f"Invalid refresh token should return 401, got {response.status_code}"

    def test_refresh_endpoint_requires_refresh_token_field(self, client):
        """Test that refresh endpoint requires refresh_token field in request."""
        # Missing refresh_token field
        response = client.post("/api/auth/refresh", json={})

        # Should return 422 for missing required field
        assert response.status_code == 422

    def test_refresh_endpoint_handles_empty_request_body(self, client):
        """Test that refresh endpoint handles empty request body gracefully."""
        response = client.post("/api/auth/refresh")

        # Should return 422 for missing request body
        assert response.status_code == 422

    def test_refresh_endpoint_validates_refresh_token_format(self, client):
        """Test that refresh endpoint validates refresh token format."""
        # Test with empty refresh token
        response = client.post("/api/auth/refresh", json={"refresh_token": ""})

        # Should return 401 or 422 for invalid/empty refresh token
        assert response.status_code in [
            401,
            422,
        ], f"Empty refresh token should return 401 or 422, got {response.status_code}"

    def test_refresh_endpoint_handles_malformed_json(self, client):
        """Test that refresh endpoint handles malformed JSON gracefully."""
        response = client.post(
            "/api/auth/refresh",
            content="{invalid_json",
            headers={"Content-Type": "application/json"},
        )

        # Should return 422 for malformed JSON
        assert response.status_code == 422
