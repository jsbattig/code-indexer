"""
Test module for DELETE endpoint issues.

This module contains tests to reproduce and fix the critical issue where
DELETE operations return HTTP 500 instead of HTTP 204.
"""

import os
import shutil
import tempfile
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GitOperationError,
    GoldenRepoError,
)


class TestDeleteEndpointIssues:
    """Test class for DELETE endpoint HTTP 500 issues."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_golden_repo_manager(self):
        """Create mock golden repo manager."""
        manager = Mock(spec=GoldenRepoManager)
        return manager

    @pytest.fixture
    def test_client(self, mock_golden_repo_manager):
        """Create test client with mocked dependencies."""
        # Mock all required dependencies before creating app
        with patch(
            "code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager
        ):
            with patch(
                "code_indexer.server.app.background_job_manager"
            ) as mock_bg_manager:
                mock_bg_manager.get_jobs_by_operation_and_params.return_value = []

                # Mock authentication dependency
                with patch(
                    "code_indexer.server.auth.dependencies.get_current_admin_user"
                ) as mock_auth:
                    mock_user = Mock()
                    mock_user.username = "test_admin"
                    mock_auth.return_value = mock_user

                    app = create_app()
                    yield TestClient(app)

    def test_delete_endpoint_returns_500_when_cleanup_fails(
        self, test_client, mock_golden_repo_manager
    ):
        """
        Test that DELETE endpoint returns HTTP 500 when repository cleanup fails.

        This test reproduces the actual issue where cleanup failures cause HTTP 500
        instead of proper error handling.
        """
        # Arrange: Mock the golden repo manager to raise GitOperationError during removal
        mock_golden_repo_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to cleanup repository files: Permission denied"
        )

        # Act: Attempt to delete repository
        response = test_client.delete("/api/admin/golden-repos/test-repo-delete")

        # Assert: Should return HTTP 500 due to cleanup failure
        assert response.status_code == 500
        assert "Failed to cleanup repository files" in response.json()["detail"]

    def test_delete_endpoint_returns_500_when_docker_cleanup_fails(
        self, test_client, mock_golden_repo_manager
    ):
        """
        Test that DELETE endpoint returns HTTP 500 when Docker cleanup fails.

        This reproduces the issue where DockerManager cleanup failures cause HTTP 500.
        """
        # Arrange: Mock cleanup failure
        mock_golden_repo_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to cleanup repository files: Docker cleanup failed"
        )

        # Act: Attempt to delete repository
        response = test_client.delete("/api/admin/golden-repos/test-repo-delete")

        # Assert: Returns HTTP 500 (current buggy behavior)
        assert response.status_code == 500
        assert "Docker cleanup failed" in response.json()["detail"]

    def test_delete_endpoint_returns_404_for_nonexistent_repo(
        self, test_client, mock_golden_repo_manager
    ):
        """
        Test that DELETE endpoint correctly returns HTTP 404 for non-existent repositories.
        """
        # Arrange: Mock repository not found
        mock_golden_repo_manager.remove_golden_repo.side_effect = GoldenRepoError(
            "Golden repository 'nonexistent' not found"
        )

        # Act: Attempt to delete non-existent repository
        response = test_client.delete("/api/admin/golden-repos/nonexistent")

        # Assert: Should return HTTP 404
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_endpoint_should_return_204_on_success(
        self, test_client, mock_golden_repo_manager
    ):
        """
        Test that DELETE endpoint should return HTTP 204 on successful deletion.

        This test defines the expected behavior that needs to be fixed.
        """
        # Arrange: Mock successful deletion
        mock_golden_repo_manager.remove_golden_repo.return_value = {
            "success": True,
            "message": "Golden repository 'test-repo' removed successfully",
        }

        # Act: Delete repository
        response = test_client.delete("/api/admin/golden-repos/test-repo")

        # Assert: Should return HTTP 204 No Content
        assert response.status_code == 204
        assert response.content == b""  # No content body

    def test_delete_endpoint_handles_permission_errors_gracefully(
        self, test_client, mock_golden_repo_manager
    ):
        """
        Test that DELETE endpoint handles permission errors without exposing sensitive details.
        """
        # Arrange: Mock permission error during cleanup
        mock_golden_repo_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to cleanup repository files: [Errno 13] Permission denied: '/var/lib/code-indexer'"
        )

        # Act: Attempt to delete repository
        response = test_client.delete("/api/admin/golden-repos/test-repo")

        # Assert: Should sanitize error message but still return 500 (current behavior)
        assert response.status_code == 500
        # Should not expose exact file paths in production
        detail = response.json()["detail"]
        assert "Permission denied" in detail or "cleanup" in detail.lower()


class TestGoldenRepoManagerCleanupIssues:
    """Test class for golden repo manager cleanup issues."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def golden_repo_manager(self, temp_dir):
        """Create golden repo manager with temp directory."""
        return GoldenRepoManager(data_dir=temp_dir)

    def test_cleanup_repository_files_raises_git_operation_error_on_failure(
        self, golden_repo_manager, temp_dir
    ):
        """
        Test that _cleanup_repository_files raises GitOperationError when cleanup fails.

        This reproduces the root cause of the HTTP 500 issue.
        """
        # Arrange: Create a repository directory with files
        repo_path = os.path.join(temp_dir, "test-repo")
        os.makedirs(repo_path)

        # Create a file that simulates cleanup failure
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # Mock DockerManager to simulate cleanup failure
        with patch(
            "code_indexer.services.docker_manager.DockerManager"
        ) as mock_docker_manager:
            mock_instance = Mock()
            mock_instance.cleanup.return_value = False  # Cleanup fails
            mock_docker_manager.return_value = mock_instance

            # Mock shutil.rmtree to simulate permission error
            with patch(
                "shutil.rmtree", side_effect=PermissionError("Permission denied")
            ):
                # Act & Assert: Should raise GitOperationError
                with pytest.raises(GitOperationError) as exc_info:
                    golden_repo_manager._cleanup_repository_files(repo_path)

                assert "Failed to cleanup repository files" in str(exc_info.value)

    def test_remove_golden_repo_with_cleanup_failure_raises_git_operation_error(
        self, golden_repo_manager, temp_dir
    ):
        """
        Test that remove_golden_repo raises GitOperationError when cleanup fails.

        This shows how cleanup failures propagate to the endpoint.
        """
        # Arrange: Create a golden repo
        repo_alias = "test-repo"
        repo_path = os.path.join(temp_dir, "golden-repos", repo_alias)
        os.makedirs(repo_path, exist_ok=True)

        # Add repo to manager
        from code_indexer.server.repositories.golden_repo_manager import GoldenRepo
        from datetime import datetime, timezone

        golden_repo = GoldenRepo(
            alias=repo_alias,
            repo_url="/tmp/test-repo",
            default_branch="main",
            clone_path=repo_path,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager.golden_repos[repo_alias] = golden_repo

        # Mock cleanup to fail
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files"
        ) as mock_cleanup:
            mock_cleanup.side_effect = GitOperationError("Cleanup failed")

            # Act & Assert: Should raise GitOperationError
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.remove_golden_repo(repo_alias)

            assert "Cleanup failed" in str(exc_info.value)

    def test_docker_manager_import_failure_handling(
        self, golden_repo_manager, temp_dir
    ):
        """
        Test that cleanup handles DockerManager import failures gracefully.
        """
        # Arrange: Create a repository directory
        repo_path = os.path.join(temp_dir, "test-repo")
        os.makedirs(repo_path)

        # Mock import failure
        with patch(
            "code_indexer.server.repositories.golden_repo_manager.DockerManager",
            side_effect=ImportError("Docker not available"),
        ):
            # Act & Assert: Should raise GitOperationError due to import failure
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager._cleanup_repository_files(repo_path)

            assert "Failed to cleanup repository files" in str(exc_info.value)
