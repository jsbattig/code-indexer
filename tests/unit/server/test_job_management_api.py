"""
Unit tests for Job Management API endpoints.

Tests for the new job management API functionality including
job listing, cancellation, and enhanced status endpoints.
"""

from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = Mock()
    user.username = "testuser"
    user.is_admin = False
    return user


@pytest.fixture
def mock_admin_user():
    """Mock authenticated admin user."""
    user = Mock()
    user.username = "admin"
    user.is_admin = True
    return user


class TestJobManagementAPI:
    """Test job management API endpoints."""

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_get_job_status_with_user_isolation(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test GET /api/jobs/{job_id} with user isolation."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock job status for the user
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

        response = client.get(
            "/api/jobs/test-job-123",
            headers={"Authorization": "Bearer test-token"},
        )

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
    def test_get_job_status_not_found_or_unauthorized(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test GET /api/jobs/{job_id} when job not found or not authorized."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock job not found
        mock_bg_manager.get_job_status.return_value = None

        response = client.get(
            "/api/jobs/nonexistent-job",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_list_jobs_endpoint(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test GET /api/jobs endpoint for listing jobs."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

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
                    "result": {"status": "success"},
                    "error": None,
                    "username": "testuser",
                },
                {
                    "job_id": "job-2",
                    "operation_type": "test_op2",
                    "status": "running",
                    "created_at": "2023-01-01T00:01:00Z",
                    "started_at": "2023-01-01T00:01:30Z",
                    "completed_at": None,
                    "progress": 50,
                    "result": None,
                    "error": None,
                    "username": "testuser",
                },
            ],
            "total": 2,
            "limit": 10,
            "offset": 0,
        }

        response = client.get(
            "/api/jobs", headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["total"] == 2
        assert data["limit"] == 10
        assert data["offset"] == 0

        # Verify list_jobs was called with correct parameters
        mock_bg_manager.list_jobs.assert_called_once_with(
            username="testuser", status_filter=None, limit=10, offset=0
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_list_jobs_with_filters_and_pagination(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test GET /api/jobs with status filter and pagination."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

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
                    "result": {"status": "success"},
                    "error": None,
                    "username": "testuser",
                }
            ],
            "total": 5,
            "limit": 1,
            "offset": 2,
        }

        response = client.get(
            "/api/jobs?status=completed&limit=1&offset=2",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["limit"] == 1
        assert data["offset"] == 2

        # Verify filter and pagination parameters
        mock_bg_manager.list_jobs.assert_called_once_with(
            username="testuser", status_filter="completed", limit=1, offset=2
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_cancel_job_endpoint(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test DELETE /api/jobs/{job_id} for job cancellation."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock successful cancellation
        mock_bg_manager.cancel_job.return_value = {
            "success": True,
            "message": "Job cancelled successfully",
        }

        response = client.delete(
            "/api/jobs/test-job-123",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cancelled successfully" in data["message"]

        # Verify cancel_job was called with user isolation
        mock_bg_manager.cancel_job.assert_called_once_with("test-job-123", "testuser")

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_cancel_job_unauthorized(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test job cancellation when user not authorized."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock unauthorized cancellation
        mock_bg_manager.cancel_job.return_value = {
            "success": False,
            "message": "Job not found or not authorized",
        }

        response = client.delete(
            "/api/jobs/unauthorized-job",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_cancel_job_invalid_status(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test job cancellation for job in invalid status."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock cancellation failure due to status
        mock_bg_manager.cancel_job.return_value = {
            "success": False,
            "message": "Cannot cancel job in completed status",
        }

        response = client.delete(
            "/api/jobs/completed-job",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 400
        assert "Cannot cancel" in response.json()["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_enhanced_job_status_response_model(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test that job status response includes all new fields."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

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

        response = client.get(
            "/api/jobs/test-job-123",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = [
            "job_id",
            "operation_type",
            "status",
            "created_at",
            "started_at",
            "completed_at",
            "progress",
            "result",
            "error",
            "username",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_job_status_backward_compatibility(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test that existing job status functionality still works."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock job status in old format (for backward compatibility test)
        mock_bg_manager.get_job_status.return_value = {
            "job_id": "legacy-job",
            "operation_type": "legacy_op",
            "status": "running",
            "created_at": "2023-01-01T00:00:00Z",
            "started_at": "2023-01-01T00:01:00Z",
            "completed_at": None,
            "progress": 50,
            "result": None,
            "error": None,
            "username": "testuser",
        }

        response = client.get(
            "/api/jobs/legacy-job",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "legacy-job"
        assert data["operation_type"] == "legacy_op"
        assert data["status"] == "running"
        assert data["progress"] == 50

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    def test_job_cleanup_endpoint(
        self,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_admin_user,
    ):
        """Test admin endpoint for job cleanup."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
        }
        mock_dep_user_manager.get_user.return_value = mock_admin_user

        # Mock cleanup operation
        mock_bg_manager.cleanup_old_jobs.return_value = 5

        response = client.delete(
            "/api/admin/jobs/cleanup?max_age_hours=24",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "cleaned_count" in data
        assert data["cleaned_count"] == 5

        # Verify cleanup was called with correct parameter
        mock_bg_manager.cleanup_old_jobs.assert_called_once_with(max_age_hours=24)

    @patch("code_indexer.server.auth.dependencies.get_current_admin_user")
    def test_job_cleanup_admin_only(
        self, mock_get_current_admin_user, client, mock_user
    ):
        """Test that job cleanup is admin-only."""
        # Setup authentication to fail for non-admin user
        from fastapi import HTTPException, status

        mock_get_current_admin_user.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

        response = client.delete(
            "/api/admin/jobs/cleanup",
            headers={"Authorization": "Bearer test-token"},
        )

        # Should get 403 or similar auth error for non-admin
        assert response.status_code in [403, 401]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.background_job_manager")
    @patch("src.code_indexer.server.app.golden_repo_manager")
    def test_submit_job_with_username_enhancement(
        self,
        mock_golden_manager,
        mock_bg_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_admin_user,
    ):
        """Test that existing job submission now includes username."""
        # This test verifies that the existing golden repo endpoints
        # work with the enhanced job manager
        # Setup authentication as admin user
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
        }
        mock_dep_user_manager.get_user.return_value = mock_admin_user

        # Mock successful job submission
        mock_bg_manager.submit_job.return_value = "new-job-123"

        # Submit golden repo addition (admin endpoint)
        repo_data = {
            "repo_url": "https://github.com/test/repo.git",
            "alias": "test-repo",
            "default_branch": "main",
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=repo_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 202  # Admin golden repo endpoint returns 202
        data = response.json()
        assert data["job_id"] == "new-job-123"

        # Verify job was submitted with username
        mock_bg_manager.submit_job.assert_called_once()
        call_args = mock_bg_manager.submit_job.call_args
        assert "submitter_username" in call_args.kwargs
        assert call_args.kwargs["submitter_username"] == "admin"
