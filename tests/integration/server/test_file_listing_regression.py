"""
Regression test for Story #494 file listing signature mismatch.

Tests that the file listing endpoint properly passes username parameter
to FileListingService.list_files() method.

CRITICAL REGRESSION: Story #494 changed FileListingService.list_files() signature
to require username parameter, but the call site in app.py was not updated.
"""

import pytest
from fastapi.testclient import TestClient
from src.code_indexer.server.app import app


class TestFileListingSignatureRegression:
    """Test that file listing endpoint doesn't crash with signature errors."""

    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(scope="class")
    def auth_token(self, client):
        """Login and get authentication token."""
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "MySecurePass2024_Word"}
        )
        assert response.status_code == 200, f"Login failed: {response.json()}"
        return response.json()["access_token"]

    def test_file_listing_endpoint_does_not_crash(self, client, auth_token):
        """
        REGRESSION TEST: File listing should not crash with missing positional argument.

        Before fix: TypeError: list_files() missing 1 required positional argument: 'query_params'
        After fix: Should return 200 or 404, but NEVER 500
        """
        response = client.get(
            "/api/repositories/tries-test/files",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should not crash with 500 error
        assert (
            response.status_code != 500
        ), f"Server crashed with signature error: {response.json()}"

        # Should return either 200 (repo exists) or 404 (repo doesn't exist)
        # but not 500 (server error)
        assert response.status_code in [
            200,
            404,
        ], f"Unexpected status code: {response.status_code}, body: {response.json()}"
