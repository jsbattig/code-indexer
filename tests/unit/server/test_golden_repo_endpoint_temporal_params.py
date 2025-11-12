"""
Unit tests for POST /api/admin/golden-repos endpoint with temporal parameters.

Tests that the endpoint properly passes enable_temporal and temporal_options
to the background job manager when registering golden repositories.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from datetime import datetime, timezone


class TestGoldenRepoEndpointTemporalParams:
    """Test that POST endpoint passes temporal parameters to background job."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        from code_indexer.server.app import create_app

        return TestClient(create_app())

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_endpoint_passes_enable_temporal_to_background_job(
        self, mock_background_job_manager, mock_user_manager, mock_jwt_manager, client
    ):
        """Test that enable_temporal is passed to background job."""
        # Setup authentication
        from code_indexer.server.auth.user_manager import User, UserRole

        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.get_user.return_value = admin_user

        # Mock background job manager
        mock_background_job_manager.submit_job.return_value = "test-job-id-123"

        # Arrange
        request_data = {
            "repo_url": "https://github.com/test/repo.git",
            "alias": "test-repo",
            "enable_temporal": True,
        }

        # Act
        response = client.post(
            "/api/admin/golden-repos",
            json=request_data,
            headers={"Authorization": "Bearer admin.jwt.token"},
        )

        # Assert
        assert response.status_code == 202
        mock_background_job_manager.submit_job.assert_called_once()

        # Verify that enable_temporal was passed to the job
        call_args = mock_background_job_manager.submit_job.call_args
        assert call_args is not None
        kwargs = call_args[1]
        assert "enable_temporal" in kwargs
        assert kwargs["enable_temporal"] is True
