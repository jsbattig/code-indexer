"""
Simple unit tests for Job Management API endpoints.

Tests for the new job management API functionality following
the existing test patterns in this project.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


class TestJobManagementAPI:
    """Test job management API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_list_jobs_endpoint(
        self, mock_bg_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test GET /api/jobs endpoint for listing jobs."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "user",
            "exp": 9999999999,
        }

        test_user = User(
            username="testuser",
            password_hash="$2b$12$test_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = test_user

        # Mock job listing
        mock_bg_manager.list_jobs.return_value = {
            "jobs": [
                {
                    "job_id": "job-1",
                    "operation_type": "test_op",
                    "status": "completed",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": "2023-01-01T00:01:00Z",
                    "completed_at": "2023-01-01T00:02:00Z",
                    "progress": 100,
                    "result": None,
                    "error": None,
                    "username": "testuser",
                }
            ],
            "total": 1,
            "limit": 10,
            "offset": 0,
        }

        # Use authorization header
        headers = {"Authorization": "Bearer fake_token"}
        response = client.get("/api/jobs", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["total"] == 1

        # Verify that list_jobs was called with correct parameters
        mock_bg_manager.list_jobs.assert_called_once_with(
            username="testuser", status_filter=None, limit=10, offset=0
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_get_job_status_endpoint(
        self, mock_bg_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test GET /api/jobs/{job_id} endpoint."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "user",
            "exp": 9999999999,
        }

        test_user = User(
            username="testuser",
            password_hash="$2b$12$test_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = test_user

        # Mock job status
        mock_bg_manager.get_job_status.return_value = {
            "job_id": "test-job-123",
            "operation_type": "test_operation",
            "status": "completed",
            "created_at": "2023-01-01T00:00:00Z",
            "started_at": "2023-01-01T00:01:00Z",
            "completed_at": "2023-01-01T00:02:00Z",
            "progress": 100,
            "result": {"status": "success"},
            "error": None,
            "username": "testuser",
        }

        headers = {"Authorization": "Bearer fake_token"}
        response = client.get("/api/jobs/test-job-123", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert data["username"] == "testuser"

        # Verify that get_job_status was called with username for isolation
        mock_bg_manager.get_job_status.assert_called_once_with(
            "test-job-123", "testuser"
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_cancel_job_endpoint(
        self, mock_bg_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test DELETE /api/jobs/{job_id} for job cancellation."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "user",
            "exp": 9999999999,
        }

        test_user = User(
            username="testuser",
            password_hash="$2b$12$test_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = test_user

        # Mock successful cancellation
        mock_bg_manager.cancel_job.return_value = {
            "success": True,
            "message": "Job cancelled successfully",
        }

        headers = {"Authorization": "Bearer fake_token"}
        response = client.delete("/api/jobs/test-job-123", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cancelled successfully" in data["message"]

        # Verify cancel_job was called with user isolation
        mock_bg_manager.cancel_job.assert_called_once_with("test-job-123", "testuser")
