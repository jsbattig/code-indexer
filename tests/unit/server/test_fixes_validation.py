"""
Test module to validate that the DELETE and refresh fixes work correctly.

This module tests the actual fixes that resolve the critical issues:
1. DELETE operations return HTTP 204 instead of HTTP 500 for non-critical cleanup issues
2. Repository refresh handles configuration conflicts gracefully
"""

import os
import shutil
import tempfile
import pytest
from unittest.mock import Mock, patch

from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GitOperationError,
    GoldenRepo,
)


class TestDeleteFixesValidation:
    """Test that DELETE fixes work correctly."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
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

        repo_alias = "test-repo"
        repo_path = os.path.join(temp_dir, "golden-repos", repo_alias)
        os.makedirs(repo_path, exist_ok=True)

        golden_repo = GoldenRepo(
            alias=repo_alias,
            repo_url="/tmp/test-repo",
            default_branch="main",
            clone_path=repo_path,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager.golden_repos[repo_alias] = golden_repo
        return golden_repo

    def test_delete_succeeds_with_partial_cleanup_failure(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that DELETE operations succeed even when cleanup has partial failures.

        This validates the main fix: repository deletion should be considered successful
        from a business perspective even if some cleanup files remain.
        """
        # Arrange: Mock cleanup to fail non-critically (filesystem permission issue)
        with patch("shutil.rmtree", side_effect=PermissionError("Permission denied")):
            # Act: Remove repository should succeed despite cleanup issue
            result = golden_repo_manager.remove_golden_repo("test-repo")

        # Assert: Deletion succeeds with warning message
        assert result["success"] is True
        assert "some cleanup issues occurred" in result["message"]

        # Verify repository is removed from metadata
        assert "test-repo" not in golden_repo_manager.golden_repos

    def test_delete_succeeds_with_docker_cleanup_failure(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that DELETE operations succeed even when Docker cleanup fails.

        This validates that Docker cleanup failures don't prevent repository deletion.
        """
        # Arrange: Create .code-indexer directory to trigger Docker cleanup path
        code_indexer_dir = os.path.join(sample_golden_repo.clone_path, ".code-indexer")
        os.makedirs(code_indexer_dir, exist_ok=True)

        # Mock DockerManager to fail during cleanup
        with patch(
            "code_indexer.services.docker_manager.DockerManager"
        ) as mock_docker_manager:
            mock_instance = Mock()
            mock_instance.cleanup.side_effect = RuntimeError(
                "Docker daemon not responding"
            )
            mock_docker_manager.return_value = mock_instance

            # Act: Remove repository should succeed despite Docker cleanup failure
            result = golden_repo_manager.remove_golden_repo("test-repo")

        # Assert: Deletion succeeds (Docker failure is handled gracefully)
        assert result["success"] is True
        # Note: Message may or may not mention cleanup issues depending on final cleanup success

        # Verify repository is removed from metadata
        assert "test-repo" not in golden_repo_manager.golden_repos

    def test_delete_still_fails_for_truly_critical_errors(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that DELETE operations still fail for truly critical system errors.

        This ensures the fix didn't make error handling TOO permissive.
        """
        # Arrange: Mock a critical system error during cleanup
        with patch.object(
            golden_repo_manager,
            "_cleanup_repository_files",
            side_effect=GitOperationError("Critical system failure"),
        ):
            # Act & Assert: Should still fail for critical errors
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.remove_golden_repo("test-repo")

            assert "Critical system failure" in str(exc_info.value)

    def test_delete_cleans_up_metadata_even_with_file_issues(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that repository metadata is cleaned up even when file cleanup fails.

        This validates that the core business operation (removing from the system)
        succeeds even when auxiliary operations (file cleanup) have issues.
        """
        # Arrange: Mock cleanup to return False (partial failure)
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files", return_value=False
        ):
            # Verify repository exists initially
            assert "test-repo" in golden_repo_manager.golden_repos

            # Act: Remove repository
            result = golden_repo_manager.remove_golden_repo("test-repo")

        # Assert: Metadata is cleaned up successfully
        assert result["success"] is True
        assert "test-repo" not in golden_repo_manager.golden_repos

        # Verify metadata file is updated
        golden_repo_manager._save_metadata()
        golden_repo_manager._load_metadata()
        assert "test-repo" not in golden_repo_manager.golden_repos


class TestRefreshFixesValidation:
    """Test that repository refresh fixes work correctly."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
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

        repo_alias = "test-repo"
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

    def test_refresh_recovers_from_init_conflicts(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh operations can recover from init configuration conflicts.

        This validates the main refresh fix: configuration conflicts should be recoverable.
        """
        attempt_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                if attempt_count == 2:  # First init call fails with recoverable error
                    mock_result = Mock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    mock_result.stderr = (
                        "Error: config file exists and conflicts detected"
                    )
                    return mock_result
                else:  # Recovery attempt succeeds
                    mock_result = Mock()
                    mock_result.returncode = 0
                    return mock_result
            else:
                # Other commands succeed
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act: Refresh should succeed despite initial configuration conflict
            result = golden_repo_manager.refresh_golden_repo("test-repo")

        # Assert: Refresh succeeds after conflict resolution
        assert result["success"] is True
        assert "refreshed successfully" in result["message"]

    def test_refresh_recovers_from_service_conflicts(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh operations can recover from service start conflicts.

        This validates that port conflicts and service issues are recoverable.
        """
        attempt_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                # Init succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "start":
                if attempt_count == 3:  # First start call fails with recoverable error
                    mock_result = Mock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    mock_result.stderr = "Error: Port 6333 already in use"
                    return mock_result
                else:  # Recovery attempt succeeds
                    mock_result = Mock()
                    mock_result.returncode = 0
                    return mock_result
            elif command[0] == "cidx" and command[1] == "stop":
                # Stop commands succeed (used in conflict resolution)
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result
            elif command[0] == "cidx" and command[1] == "status":
                # Status commands should succeed after conflict resolution
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "services running"
                mock_result.stderr = ""
                return mock_result
            else:
                # Other commands succeed
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act: Refresh should succeed despite initial service conflict
            result = golden_repo_manager.refresh_golden_repo("test-repo")

        # Assert: Refresh succeeds after conflict resolution
        assert result["success"] is True
        assert "refreshed successfully" in result["message"]

    def test_refresh_still_fails_for_unrecoverable_errors(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh operations still fail for truly unrecoverable errors.

        This ensures the fix didn't make error handling TOO permissive.
        """

        def mock_subprocess_run(*args, **kwargs):
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                # Init fails with unrecoverable error
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stdout = ""
                mock_result.stderr = "Fatal: Invalid embedding provider configuration"
                return mock_result
            else:
                # Other commands
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act & Assert: Should still fail for unrecoverable errors
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.refresh_golden_repo("test-repo")

            assert "Invalid embedding provider" in str(exc_info.value)

    def test_refresh_handles_no_indexable_files_gracefully(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that refresh operations handle 'no indexable files' condition gracefully.

        This validates that the existing special case handling still works.
        """

        def mock_subprocess_run(*args, **kwargs):
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "index":
                # Index command reports no files found
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stdout = "No files found to index"
                mock_result.stderr = ""
                return mock_result
            else:
                # Other commands succeed
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act: Refresh should succeed despite no indexable files
            result = golden_repo_manager.refresh_golden_repo("test-repo")

        # Assert: Refresh succeeds
        assert result["success"] is True
        assert "refreshed successfully" in result["message"]
