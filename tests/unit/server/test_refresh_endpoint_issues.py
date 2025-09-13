"""
Test module for repository refresh endpoint issues.

This module contains tests to reproduce and fix the critical issue where
repository refresh background jobs fail due to configuration conflicts.
"""

import os
import shutil
import tempfile
import subprocess
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GitOperationError,
    GoldenRepoError,
    GoldenRepo,
)


class TestRefreshEndpointIssues:
    """Test class for repository refresh endpoint issues."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_background_job_manager(self):
        """Create mock background job manager."""
        manager = Mock()
        manager.submit_job.return_value = "job-123"
        return manager

    @pytest.fixture
    def mock_golden_repo_manager(self):
        """Create mock golden repo manager."""
        manager = Mock(spec=GoldenRepoManager)
        return manager

    @pytest.fixture
    def test_client(self, mock_background_job_manager, mock_golden_repo_manager):
        """Create test client with mocked dependencies."""
        app = create_app()

        # Patch the managers
        with patch(
            "code_indexer.server.app.background_job_manager",
            mock_background_job_manager,
        ):
            with patch(
                "code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager
            ):
                # Mock authentication
                with patch(
                    "code_indexer.server.auth.dependencies.get_current_admin_user"
                ) as mock_auth:
                    mock_user = Mock()
                    mock_user.username = "test_admin"
                    mock_auth.return_value = mock_user

                    yield TestClient(app)

    def test_refresh_endpoint_submits_background_job_successfully(
        self, test_client, mock_background_job_manager
    ):
        """
        Test that refresh endpoint successfully submits background job.

        This verifies the endpoint layer works correctly.
        """
        # Arrange: Mock successful job submission
        mock_background_job_manager.submit_job.return_value = "job-123"

        # Act: Submit refresh request
        response = test_client.post("/api/admin/golden-repos/sample-repo/refresh")

        # Assert: Should return HTTP 202 with job ID
        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-123"
        assert "refresh started" in data["message"]

        # Verify job submission
        mock_background_job_manager.submit_job.assert_called_once()
        call_args = mock_background_job_manager.submit_job.call_args
        assert call_args[0][0] == "refresh_golden_repo"
        assert call_args[1]["alias"] == "sample-repo"

    def test_refresh_endpoint_returns_500_when_job_submission_fails(
        self, test_client, mock_background_job_manager
    ):
        """
        Test that refresh endpoint returns HTTP 500 when job submission fails.
        """
        # Arrange: Mock job submission failure
        mock_background_job_manager.submit_job.side_effect = Exception(
            "Job queue is full"
        )

        # Act: Submit refresh request
        response = test_client.post("/api/admin/golden-repos/sample-repo/refresh")

        # Assert: Should return HTTP 500
        assert response.status_code == 500
        assert "Failed to submit refresh job" in response.json()["detail"]


class TestRefreshGoldenRepoIssues:
    """Test class for golden repo refresh implementation issues."""

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

    @pytest.fixture
    def sample_golden_repo(self, golden_repo_manager, temp_dir):
        """Create a sample golden repo for testing."""
        from datetime import datetime, timezone

        repo_alias = "sample-repo"
        repo_path = os.path.join(temp_dir, "golden-repos", repo_alias)
        os.makedirs(repo_path, exist_ok=True)

        # Create a git repository structure
        git_dir = os.path.join(repo_path, ".git")
        os.makedirs(git_dir, exist_ok=True)

        golden_repo = GoldenRepo(
            alias=repo_alias,
            repo_url="https://github.com/example/repo.git",
            default_branch="main",
            clone_path=repo_path,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager.golden_repos[repo_alias] = golden_repo
        return golden_repo

    def test_refresh_golden_repo_not_found_raises_error(self, golden_repo_manager):
        """
        Test that refresh raises GoldenRepoError for non-existent repositories.
        """
        # Act & Assert: Should raise GoldenRepoError
        with pytest.raises(GoldenRepoError) as exc_info:
            golden_repo_manager.refresh_golden_repo("nonexistent-repo")

        assert "not found" in str(exc_info.value)

    def test_refresh_remote_repo_git_pull_failure_raises_error(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh raises GitOperationError when git pull fails.

        This reproduces one of the background job failure scenarios.
        """
        # Arrange: Mock subprocess.run to simulate git pull failure
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "fatal: repository does not exist"
            mock_run.return_value = mock_result

            # Act & Assert: Should raise GitOperationError
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.refresh_golden_repo("sample-repo")

            assert "Git pull failed" in str(exc_info.value)

    def test_refresh_workflow_cidx_init_failure_raises_error(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh raises GitOperationError when cidx init fails.

        This reproduces the configuration conflict issue.
        """

        # Arrange: Mock git pull success but cidx init failure
        def mock_subprocess_run(*args, **kwargs):
            command = args[0]
            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                # cidx init fails
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stdout = ""
                mock_result.stderr = "Error: Configuration conflict detected"
                return mock_result
            else:
                # Other commands
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act & Assert: Should raise GitOperationError
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.refresh_golden_repo("sample-repo")

            assert "Workflow step 1 failed" in str(exc_info.value)
            assert "Configuration conflict detected" in str(exc_info.value)

    def test_refresh_workflow_cidx_start_failure_raises_error(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh raises GitOperationError when cidx start fails.

        This reproduces service unavailability issues during refresh.
        """

        # Arrange: Mock git pull and init success, but start failure
        def mock_subprocess_run(*args, **kwargs):
            command = args[0]
            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                # cidx init succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "start":
                # cidx start fails
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stdout = ""
                mock_result.stderr = "Error: Port already in use"
                return mock_result
            else:
                # Other commands
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act & Assert: Should raise GitOperationError
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.refresh_golden_repo("sample-repo")

            assert "Workflow step 2 failed" in str(exc_info.value)
            assert "Port already in use" in str(exc_info.value)

    def test_refresh_workflow_timeout_raises_error(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh raises GitOperationError when workflow times out.
        """
        # Arrange: Mock subprocess timeout
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("cidx", 300)
        ):
            # Act & Assert: Should raise GitOperationError
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.refresh_golden_repo("sample-repo")

            assert "timed out" in str(exc_info.value).lower()

    def test_refresh_local_repo_skips_git_pull(self, golden_repo_manager, temp_dir):
        """
        Test that refresh for local repositories skips git pull and goes straight to workflow.
        """
        # Arrange: Create local repository
        from datetime import datetime, timezone

        repo_alias = "local-repo"
        repo_path = os.path.join(temp_dir, "golden-repos", repo_alias)
        os.makedirs(repo_path, exist_ok=True)

        golden_repo = GoldenRepo(
            alias=repo_alias,
            repo_url="/tmp/local-repo",  # Local path
            default_branch="main",
            clone_path=repo_path,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager.golden_repos[repo_alias] = golden_repo

        # Mock workflow to succeed
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            # Act: Refresh local repository
            result = golden_repo_manager.refresh_golden_repo("local-repo")

            # Assert: Should succeed without git pull
            assert result["success"] is True
            assert "refreshed successfully" in result["message"]

            # Verify git pull was not called
            git_pull_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0][0] == "git" and call[0][0][1] == "pull"
            ]
            assert len(git_pull_calls) == 0

            # Verify cidx commands were called
            cidx_calls = [
                call for call in mock_run.call_args_list if call[0][0][0] == "cidx"
            ]
            assert len(cidx_calls) > 0

    def test_refresh_successful_execution(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh works successfully when all steps complete.

        This defines the expected working behavior.
        """
        # Arrange: Mock all subprocess calls to succeed
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Success"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Act: Refresh repository
            result = golden_repo_manager.refresh_golden_repo("sample-repo")

            # Assert: Should succeed
            assert result["success"] is True
            assert "refreshed successfully" in result["message"]

            # Verify expected commands were called
            expected_commands = [
                ["git", "pull", "origin", "main"],  # Git pull
                [
                    "cidx",
                    "init",
                    "--embedding-provider",
                    "voyage-ai",
                    "--force",
                ],  # Init with force
                ["cidx", "start", "--force-docker"],  # Start
                ["cidx", "status", "--force-docker"],  # Status
                ["cidx", "index"],  # Index
                ["cidx", "stop", "--force-docker"],  # Stop
            ]

            assert mock_run.call_count == len(expected_commands)
            for i, expected_cmd in enumerate(expected_commands):
                actual_call = mock_run.call_args_list[i]
                assert actual_call[0][0] == expected_cmd
