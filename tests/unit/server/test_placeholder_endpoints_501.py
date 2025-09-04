"""
Test placeholder endpoints return proper 501 (Not Implemented) status codes.

These tests verify that placeholder endpoints return the correct HTTP status
to indicate functionality is not yet implemented.
"""

from fastapi.testclient import TestClient
from fastapi import status

from src.code_indexer.server.app import create_app


class TestPlaceholderEndpoints501:
    """Test placeholder endpoints return 501 Not Implemented."""

    def setup_method(self):
        """Setup test client and get auth token for each test."""
        self.app = create_app()
        self.client = TestClient(self.app)

        # Login to get valid token for protected endpoints
        login_response = self.client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == status.HTTP_200_OK

        token_data = login_response.json()
        self.auth_token = token_data["access_token"]
        self.headers = {"Authorization": f"Bearer {self.auth_token}"}

    def test_list_repositories_is_implemented(self):
        """Test /api/repos is implemented (no longer returns 501)."""
        response = self.client.get("/api/repos", headers=self.headers)
        assert response.status_code == status.HTTP_200_OK

        response_data = response.json()
        assert isinstance(
            response_data, list
        )  # Should return list of activated repositories

    def test_list_golden_repos_is_implemented(self):
        """Test /api/admin/golden-repos is implemented (no longer returns 501)."""
        response = self.client.get("/api/admin/golden-repos", headers=self.headers)
        assert response.status_code == status.HTTP_200_OK

        response_data = response.json()
        assert "golden_repositories" in response_data
        assert "total" in response_data

    def test_activate_repository_validation_error(self):
        """Test /api/repos/activate validates input (no longer returns 501)."""
        response = self.client.post(
            "/api/repos/activate", headers=self.headers, json={}
        )
        # Should return 422 for validation error (missing required fields)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_semantic_query_returns_422_for_invalid_data(self):
        """Test /api/query returns 422 for invalid request data (endpoint is now implemented)."""
        response = self.client.post("/api/query", headers=self.headers, json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        response_data = response.json()
        assert "detail" in response_data
        # Should have validation errors for missing required fields

    def test_placeholder_responses_maintain_consistent_structure(self):
        """Test remaining placeholder endpoints return consistent response structure."""
        endpoints: list[tuple[str, str]] = [
            # No endpoints currently return 501 - all major endpoints have been implemented
        ]  # /api/query endpoint is now implemented

        # If no endpoints return 501 anymore, this test passes by design
        if not endpoints:
            assert True  # All major endpoints have been implemented
            return

        for method, endpoint in endpoints:
            if method == "GET":
                response = self.client.get(endpoint, headers=self.headers)
            else:  # POST
                response = self.client.post(endpoint, headers=self.headers, json={})

            assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
            response_data = response.json()

            # All responses should have a detail field with message
            assert "detail" in response_data
            assert "message" in response_data["detail"]
            assert isinstance(response_data["detail"]["message"], str)
            assert len(response_data["detail"]["message"]) > 0

            # Message should indicate not implemented
            assert "not yet implemented" in response_data["detail"]["message"].lower()

    def test_implemented_endpoints_do_not_return_501(self):
        """Test that implemented endpoints don't return 501 status."""
        # Health endpoint (public)
        response = self.client.get("/health")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Login endpoint (public)
        response = self.client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # List users endpoint (admin only, implemented)
        response = self.client.get("/api/admin/users", headers=self.headers)
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        assert response.status_code == status.HTTP_200_OK
