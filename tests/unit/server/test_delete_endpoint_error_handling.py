"""
Unit tests for DELETE endpoint error handling in FastAPI app.

Tests the HTTP status code behavior for different error scenarios when
deleting golden repositories through the API endpoints.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoError,
    GitOperationError,
)


class TestDeleteEndpointErrorHandling:
    """Test suite for DELETE endpoint HTTP status code behavior."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        """Create authentication headers for admin user."""
        login_data = {"username": "admin", "password": "admin"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_delete_nonexistent_repository_returns_404(
        self, client, auth_headers, monkeypatch
    ):
        """Test DELETE of non-existent repository returns HTTP 404."""
        mock_manager = MagicMock()
        # Mock GoldenRepoError (repository not found)
        mock_manager.remove_golden_repo.side_effect = GoldenRepoError(
            "Golden repository 'nonexistent' not found"
        )
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/nonexistent", headers=auth_headers
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_permission_error_returns_500(
        self, client, auth_headers, monkeypatch
    ):
        """Test DELETE with permission error returns HTTP 500, not 404."""
        mock_manager = MagicMock()
        # Mock GitOperationError (permission/cleanup failure)
        mock_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to clean up repository files: Permission denied: /root/.local/share/qdrant"
        )
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/permission-repo", headers=auth_headers
        )

        # Should return 500 for filesystem/permission errors, not 404
        assert response.status_code == 500
        assert "Failed to clean up repository files" in response.json()["detail"]
        assert "Permission denied" in response.json()["detail"]

    def test_delete_filesystem_error_returns_500(
        self, client, auth_headers, monkeypatch
    ):
        """Test DELETE with filesystem error returns HTTP 500, not 404."""
        mock_manager = MagicMock()
        # Mock GitOperationError (filesystem failure)
        mock_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to clean up repository files: OSError: No such file or directory"
        )
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/filesystem-repo", headers=auth_headers
        )

        # Should return 500 for filesystem errors, not 404
        assert response.status_code == 500
        assert "Failed to clean up repository files" in response.json()["detail"]
        assert "No such file or directory" in response.json()["detail"]

    def test_delete_successful_returns_204(self, client, auth_headers, monkeypatch):
        """Test successful DELETE returns HTTP 204 No Content."""
        mock_manager = MagicMock()
        # Mock successful removal
        mock_manager.remove_golden_repo.return_value = {
            "success": True,
            "message": "Golden repository 'test-repo' removed successfully",
        }
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/test-repo", headers=auth_headers
        )

        assert response.status_code == 204
        # 204 No Content should have no response body
        assert response.content == b""

    def test_delete_generic_error_returns_500(self, client, auth_headers, monkeypatch):
        """Test DELETE with generic error returns HTTP 500."""
        mock_manager = MagicMock()
        # Mock unexpected error
        mock_manager.remove_golden_repo.side_effect = RuntimeError(
            "Unexpected server error"
        )
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/error-repo", headers=auth_headers
        )

        # Should return 500 for unexpected errors
        assert response.status_code == 500
        assert "Failed to remove repository" in response.json()["detail"]
        assert "Unexpected server error" in response.json()["detail"]

    def test_delete_unauthorized_returns_401(self, client):
        """Test DELETE without authentication returns HTTP 401."""
        response = client.delete("/api/admin/golden-repos/test-repo")

        # Should return 401/403 for missing authentication
        assert response.status_code in [401, 403]

    def test_delete_error_categorization_scenarios(
        self, client, auth_headers, monkeypatch
    ):
        """Test various error scenarios return appropriate HTTP status codes."""
        test_cases = [
            # (exception, expected_status, expected_error_text)
            (
                GoldenRepoError("Golden repository 'missing' not found"),
                404,
                "not found",
            ),
            (
                GitOperationError(
                    "Failed to clean up repository files: PermissionError: Permission denied"
                ),
                500,
                "Failed to clean up",
            ),
            (
                GitOperationError(
                    "Failed to clean up repository files: OSError: Device or resource busy"
                ),
                500,
                "Failed to clean up",
            ),
            (
                ValueError("Invalid repository alias"),
                500,
                "Failed to remove repository",
            ),
        ]

        for exception, expected_status, expected_text in test_cases:
            mock_manager = MagicMock()
            mock_manager.remove_golden_repo.side_effect = exception
            monkeypatch.setattr(
                "src.code_indexer.server.app.golden_repo_manager", mock_manager
            )

            response = client.delete(
                "/api/admin/golden-repos/test-alias", headers=auth_headers
            )

            assert response.status_code == expected_status, (
                f"Expected {expected_status} for {exception.__class__.__name__}, "
                f"got {response.status_code}"
            )
            assert expected_text in response.json()["detail"], (
                f"Expected '{expected_text}' in error message, "
                f"got '{response.json()['detail']}'"
            )
