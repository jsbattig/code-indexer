"""Unit tests for temporal status REST API endpoint.

Story #669 AC6: Web UI temporal status display
Tests the /api/v1/repos/{alias}/temporal-status endpoint
"""

import pytest
from unittest.mock import patch
from datetime import datetime
from fastapi import HTTPException
from fastapi.testclient import TestClient

from code_indexer.server.app import app
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return User(
        username="testuser",
        email="test@example.com",
        role=UserRole.ADMIN,
        password_hash="fake_hash",
        created_at=datetime.now()
    )


@pytest.fixture
def client(mock_user):
    """Create test client with mocked authentication."""

    def mock_get_current_user_dep():
        return mock_user

    # Override get_current_user dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user_dep

    client = TestClient(app)
    yield client

    # Clean up after tests
    app.dependency_overrides.clear()


class TestTemporalStatusEndpoint:
    """Test suite for GET /api/v1/repos/{alias}/temporal-status endpoint."""

    def test_temporal_status_v2_format_returns_active(self, client):
        """Test temporal status endpoint returns v2 format with active status."""
        # Arrange
        repo_alias = "test-repo"

        # Mock at source module
        with patch("code_indexer.server.services.dashboard_service.DashboardService") as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.get_temporal_index_status.return_value = {
                "format": "v2",
                "file_count": 150,
                "needs_reindex": False,
                "message": "Temporal indexing active (v2 format) - 150 files indexed"
            }

            # Act
            response = client.get(f"/api/v1/repos/{repo_alias}/temporal-status")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["format"] == "v2"
            assert data["file_count"] == 150
            assert data["needs_reindex"] is False
            assert "active" in data["message"].lower()
            assert "150" in data["message"]

    def test_temporal_status_v1_format_returns_warning(self, client):
        """Test temporal status endpoint returns v1 format with reindex warning."""
        # Arrange
        repo_alias = "test-repo"

        # Mock at source module
        with patch("code_indexer.server.services.dashboard_service.DashboardService") as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.get_temporal_index_status.return_value = {
                "format": "v1",
                "file_count": 85,
                "needs_reindex": True,
                "message": "Legacy temporal index format (v1) detected - Re-index required: cidx index --index-commits --reconcile"
            }

            # Act
            response = client.get(f"/api/v1/repos/{repo_alias}/temporal-status")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["format"] == "v1"
            assert data["file_count"] == 85
            assert data["needs_reindex"] is True
            assert "legacy" in data["message"].lower() or "v1" in data["message"].lower()
            assert "re-index" in data["message"].lower()

    def test_temporal_status_no_index_returns_none(self, client):
        """Test temporal status endpoint returns none when no temporal index exists."""
        # Arrange
        repo_alias = "test-repo"

        # Mock at source module
        with patch("code_indexer.server.services.dashboard_service.DashboardService") as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.get_temporal_index_status.return_value = {
                "format": "none",
                "file_count": 0,
                "needs_reindex": False,
                "message": "No temporal index (git history not indexed)"
            }

            # Act
            response = client.get(f"/api/v1/repos/{repo_alias}/temporal-status")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["format"] == "none"
            assert data["file_count"] == 0
            assert data["needs_reindex"] is False
            assert "no temporal" in data["message"].lower()

    def test_temporal_status_requires_authentication(self):
        """Test temporal status endpoint requires authentication."""
        # Arrange
        repo_alias = "test-repo"

        # Create client without auth override
        test_client = TestClient(app)

        # Act - No authentication, should return 401
        response = test_client.get(f"/api/v1/repos/{repo_alias}/temporal-status")

        # Assert
        assert response.status_code == 401

    def test_temporal_status_invalid_repo_returns_404(self, client):
        """Test temporal status endpoint returns 404 for invalid repository."""
        # Arrange
        repo_alias = "nonexistent-repo"

        # Mock at source module
        with patch("code_indexer.server.services.dashboard_service.DashboardService") as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.get_temporal_index_status.side_effect = FileNotFoundError(
                f"Repository not found: {repo_alias}"
            )

            # Act
            response = client.get(f"/api/v1/repos/{repo_alias}/temporal-status")

            # Assert
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
