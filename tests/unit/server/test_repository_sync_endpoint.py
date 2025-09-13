"""
Test suite for POST /api/repositories/{repo_id}/sync endpoint.

Tests the repository synchronization endpoint that supports background job processing,
progress tracking, conflict detection, and various sync options.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.dependencies import get_current_user


class TestRepositorySyncEndpoint:
    """Test cases for repository sync endpoint implementation."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.app = create_app()

        # Create mock user
        self.mock_user = Mock()
        self.mock_user.username = "testuser"
        self.mock_user.role.value = "normal_user"

        # Override the dependency
        self.app.dependency_overrides[get_current_user] = lambda: self.mock_user

        self.client = TestClient(self.app)

    def _mock_repository_exists(self, mock_repo_manager, repo_id):
        """Helper to mock repository existence."""
        mock_repo_manager.list_activated_repositories.return_value = [
            {"user_alias": repo_id, "golden_repo_alias": repo_id}
        ]

    def test_sync_endpoint_returns_202_accepted_with_job_details(self):
        """Test that POST /api/repositories/{repo_id}/sync returns 202 Accepted with sync job details."""
        repo_id = "repo-123"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.submit_job.return_value = "sync-job-uuid-123"
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []

            response = self.client.post(
                f"/api/repositories/{repo_id}/sync",
                json={
                    "force": False,
                    "full_reindex": False,
                    "incremental": True,
                    "pull_remote": False,
                },
            )

        assert response.status_code == 202
        data = response.json()

        # Verify response structure matches story requirements
        assert "job_id" in data
        assert data["job_id"] == "sync-job-uuid-123"
        assert data["status"] == "queued"
        assert data["repository_id"] == repo_id
        assert "created_at" in data
        assert "progress" in data
        assert data["progress"]["percentage"] == 0
        assert data["progress"]["files_processed"] == 0
        assert data["progress"]["files_total"] == 0
        assert data["progress"]["current_file"] is None
        assert "options" in data
        assert data["options"]["force"] is False
        assert data["options"]["full_reindex"] is False
        assert data["options"]["incremental"] is True

    def test_sync_endpoint_background_job_executes_successfully(self):
        """Test that background sync job executes successfully with progress tracking."""
        repo_id = "repo-456"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            job_id = "sync-job-uuid-456"
            mock_job_manager.submit_job.return_value = job_id
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []

            response = self.client.post(f"/api/repositories/{repo_id}/sync")

            assert response.status_code == 202
            assert response.json()["job_id"] == job_id

            # Verify job was submitted with correct parameters
            mock_job_manager.submit_job.assert_called_once()
            call_args = mock_job_manager.submit_job.call_args
            assert call_args[0][0] == "sync_repository"  # operation_type
            assert call_args[1]["submitter_username"] == "testuser"

    def test_sync_returns_409_conflict_when_sync_in_progress(self):
        """Test that sync returns 409 Conflict if sync already in progress (unless force=true)."""
        repo_id = "repo-789"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.get_jobs_by_operation_and_params.return_value = [
                {
                    "job_id": "existing-sync-job",
                    "operation_type": "sync_repository",
                    "status": "running",
                    "username": "testuser",
                }
            ]

            response = self.client.post(
                f"/api/repositories/{repo_id}/sync", json={"force": False}
            )

            assert response.status_code == 409
            data = response.json()
            assert "already in progress" in data["detail"]

    def test_sync_with_force_flag_cancels_existing_jobs(self):
        """Test that sync with force=true cancels existing sync jobs."""
        repo_id = "repo-force"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.get_jobs_by_operation_and_params.return_value = [
                {
                    "job_id": "existing-sync-job",
                    "operation_type": "sync_repository",
                    "status": "running",
                    "username": "testuser",
                }
            ]
            mock_job_manager.cancel_job.return_value = {"success": True}
            mock_job_manager.submit_job.return_value = "new-sync-job-uuid"

            response = self.client.post(
                f"/api/repositories/{repo_id}/sync", json={"force": True}
            )

            assert response.status_code == 202

            # Verify existing job was cancelled
            mock_job_manager.cancel_job.assert_called_once_with(
                "existing-sync-job", "testuser"
            )

            # Verify new job was submitted
            mock_job_manager.submit_job.assert_called_once()

    def test_sync_supports_incremental_sync_for_changed_files_only(self):
        """Test that sync supports incremental sync for changed files only."""
        repo_id = "repo-inc"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.submit_job.return_value = "incremental-sync-job"
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []

            response = self.client.post(
                f"/api/repositories/{repo_id}/sync",
                json={"incremental": True, "full_reindex": False},
            )

            assert response.status_code == 202
            data = response.json()
            assert data["options"]["incremental"] is True
            assert data["options"]["full_reindex"] is False

            # Verify job was submitted (options are captured in closure)
            mock_job_manager.submit_job.assert_called_once()
            call_args = mock_job_manager.submit_job.call_args
            assert call_args[0][0] == "sync_repository"  # operation_type

    def test_sync_supports_git_pull_integration(self):
        """Test that sync supports git pull integration for remote repositories."""
        repo_id = "repo-git"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.submit_job.return_value = "git-pull-sync-job"
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []

            response = self.client.post(
                f"/api/repositories/{repo_id}/sync",
                json={
                    "pull_remote": True,
                    "remote": "origin",
                    "branches": ["main", "develop"],
                },
            )

            assert response.status_code == 202

            # Verify job was submitted (options are captured in closure)
            mock_job_manager.submit_job.assert_called_once()
            call_args = mock_job_manager.submit_job.call_args
            assert call_args[0][0] == "sync_repository"  # operation_type

    def test_sync_provides_real_time_progress_updates(self):
        """Test that sync execution provides real-time progress updates."""
        repo_id = "repo-progress"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            job_id = "progress-sync-job"
            mock_job_manager.submit_job.return_value = job_id
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []

            # Submit sync job
            response = self.client.post(f"/api/repositories/{repo_id}/sync")
            assert response.status_code == 202

            # Verify initial progress is zero
            data = response.json()
            assert data["progress"]["percentage"] == 0

    def test_sync_endpoint_validates_repository_exists(self):
        """Test that sync endpoint validates repository exists and user has access."""
        repo_id = "nonexistent-repo"

        with (
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
            patch(
                "code_indexer.server.app.repository_listing_manager"
            ) as mock_listing_manager,
        ):

            # Mock repository not found
            mock_repo_manager.list_activated_repositories.return_value = []
            from code_indexer.server.repositories.repository_listing_manager import (
                RepositoryListingError,
            )

            mock_listing_manager.get_repository_details.side_effect = (
                RepositoryListingError("Not found")
            )

            response = self.client.post(f"/api/repositories/{repo_id}/sync")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_sync_endpoint_requires_authentication(self):
        """Test that sync endpoint requires valid authentication."""
        # Create a new app without dependency overrides
        app = create_app()
        client = TestClient(app)

        repo_id = "auth-test-repo"
        response = client.post(f"/api/repositories/{repo_id}/sync")
        assert response.status_code == 403  # Should be 403 for missing auth

    def test_sync_endpoint_validates_request_body(self):
        """Test that sync endpoint validates request body parameters."""
        repo_id = "validation-repo"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []
            mock_job_manager.submit_job.return_value = "validation-job"

            # Test with valid parameters
            response = self.client.post(
                f"/api/repositories/{repo_id}/sync",
                json={"force": True, "branches": ["main", "develop"]},
            )

            assert response.status_code == 202

    def test_sync_handles_background_job_submission_errors(self):
        """Test that sync endpoint handles background job submission errors properly."""
        repo_id = "error-repo"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []
            mock_job_manager.submit_job.side_effect = Exception("Job queue full")

            response = self.client.post(f"/api/repositories/{repo_id}/sync")

            assert response.status_code == 500
            assert "Job queue full" in response.json()["detail"]

    def test_sync_job_execution_with_progress_tracking(self):
        """Test the actual sync job execution with progress tracking."""
        with patch(
            "code_indexer.server.app.activated_repo_manager"
        ) as mock_repo_manager:
            mock_repo_manager.list_activated_repositories.return_value = [
                {"user_alias": "test-repo", "golden_repo_alias": "test-repo"}
            ]
            mock_repo_manager.sync_with_golden_repository.return_value = {
                "success": True,
                "message": "Sync completed",
                "changes_applied": True,
                "files_changed": 3,
            }

            # Import the sync function that will be used in background jobs
            from code_indexer.server.app import _execute_repository_sync

            # Test sync function directly
            result = _execute_repository_sync(
                repo_id="test-repo",
                username="testuser",
                options={"incremental": True, "force": False, "pull_remote": True},
                progress_callback=Mock(),
            )

            assert result["success"] is True
            assert (
                "completed" in result["message"] or "synchronized" in result["message"]
            )

    def test_sync_job_handles_git_conflicts_gracefully(self):
        """Test that sync job handles git conflicts gracefully."""
        with patch(
            "code_indexer.server.app.activated_repo_manager"
        ) as mock_repo_manager:
            from code_indexer.server.repositories.activated_repo_manager import (
                GitOperationError,
            )

            mock_repo_manager.list_activated_repositories.return_value = [
                {"user_alias": "conflict-repo", "golden_repo_alias": "conflict-repo"}
            ]
            mock_repo_manager.sync_with_golden_repository.side_effect = (
                GitOperationError("Merge conflict detected")
            )

            # Test that sync function handles conflicts
            from code_indexer.server.app import _execute_repository_sync

            with pytest.raises(GitOperationError):
                _execute_repository_sync(
                    repo_id="conflict-repo",
                    username="testuser",
                    options={},
                    progress_callback=Mock(),
                )

    def test_sync_endpoint_request_body_defaults(self):
        """Test that sync endpoint uses correct defaults for optional request body."""
        repo_id = "defaults-repo"

        with (
            patch("code_indexer.server.app.background_job_manager") as mock_job_manager,
            patch(
                "code_indexer.server.app.activated_repo_manager"
            ) as mock_repo_manager,
        ):

            self._mock_repository_exists(mock_repo_manager, repo_id)
            mock_job_manager.get_jobs_by_operation_and_params.return_value = []
            mock_job_manager.submit_job.return_value = "defaults-job"

            # Submit with no body (should use defaults)
            response = self.client.post(f"/api/repositories/{repo_id}/sync")

            assert response.status_code == 202
            data = response.json()

            # Verify default options are applied
            assert data["options"]["force"] is False
            assert data["options"]["full_reindex"] is False
            assert data["options"]["incremental"] is True
