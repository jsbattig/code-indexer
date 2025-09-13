"""
Test suite verifying all endpoints require proper authentication.

Following CLAUDE.md Foundation #1: Real security, no mock bypasses.
"""

import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app


class TestEndpointAuthenticationRequirements:
    """Test that all API endpoints require authentication."""

    @pytest.fixture
    def client(self):
        """Create test client for API endpoints."""
        app = create_app()
        return TestClient(app)

    def test_health_endpoint_requires_authentication(self, client):
        """Health endpoint must require authentication - CRITICAL security fix."""
        # Request without authentication should fail
        response = client.get("/api/system/health")

        assert response.status_code in [
            401,
            403,
        ], "Health endpoint must require authentication"
        assert "detail" in response.json(), "Should return authentication error"

    def test_repository_stats_endpoint_requires_authentication(self, client):
        """Repository stats endpoint must require authentication."""
        # Request without authentication should fail
        response = client.get("/api/repositories/test_repo/stats")

        assert response.status_code in [
            401,
            403,
        ], "Stats endpoint must require authentication"
        assert "detail" in response.json(), "Should return authentication error"

    def test_semantic_search_endpoint_requires_authentication(self, client):
        """Semantic search endpoint must require authentication."""
        # Request without authentication should fail
        search_data = {"query": "test query", "limit": 10, "include_source": False}
        response = client.post("/api/repositories/test_repo/search", json=search_data)

        assert response.status_code in [
            401,
            403,
        ], "Search endpoint must require authentication"
        assert "detail" in response.json(), "Should return authentication error"

    def test_repository_files_endpoint_requires_authentication(self, client):
        """Repository files endpoint must require authentication."""
        # Request without authentication should fail
        response = client.get("/api/repositories/test_repo/files")

        assert response.status_code in [
            401,
            403,
        ], "Files endpoint must require authentication"
        assert "detail" in response.json(), "Should return authentication error"

    def test_all_protected_endpoints_require_auth(self, client):
        """Verify comprehensive list of protected endpoints."""
        protected_endpoints = [
            ("GET", "/api/system/health"),
            ("GET", "/api/repositories/test_repo/stats"),
            ("POST", "/api/repositories/test_repo/search"),
            ("GET", "/api/repositories/test_repo/files"),
            ("GET", "/api/repositories/test_repo/branches"),
            ("POST", "/api/repositories/test_repo/sync"),
            ("GET", "/api/repositories/test_repo"),
        ]

        for method, endpoint in protected_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                # Provide minimal valid JSON for POST requests
                response = client.post(endpoint, json={})
            else:
                continue

            assert response.status_code in [
                401,
                403,
            ], f"{method} {endpoint} must require authentication"

    def test_no_authentication_bypass_possible(self, client):
        """Ensure no authentication bypass mechanisms exist."""
        # Try various bypass attempts
        bypass_attempts = [
            # Headers that might bypass auth
            {"headers": {"X-Skip-Auth": "true"}},
            {"headers": {"Authorization": "Bearer invalid"}},
            {"headers": {"Authorization": "Basic invalid"}},
            # Query parameters that might bypass auth
            {"params": {"skip_auth": "true"}},
            {"params": {"admin": "true"}},
            {"params": {"test": "true"}},
        ]

        for attempt in bypass_attempts:
            response = client.get("/api/system/health", **attempt)
            assert response.status_code in [
                401,
                403,
            ], f"Auth bypass attempt should fail: {attempt}"
