"""
Test module for improved error handling in DELETE and refresh operations.

This module contains tests to verify that the fixes properly handle
recoverable errors and return appropriate HTTP status codes.
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


class TestImprovedDeleteErrorHandling:
    """Test improved DELETE endpoint error handling."""

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

    def test_cleanup_returns_bool_for_success(self, golden_repo_manager, temp_dir):
        """
        Test that _cleanup_repository_files returns True for successful cleanup.
        """
        # Arrange: Create a simple repository directory
        repo_path = os.path.join(temp_dir, "test-repo")
        os.makedirs(repo_path)
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # Act: Cleanup should succeed
        result = golden_repo_manager._cleanup_repository_files(repo_path)

        # Assert: Should return True and directory should be removed
        assert result is True
        assert not os.path.exists(repo_path)

    def test_cleanup_returns_false_for_non_critical_failures(
        self, golden_repo_manager, temp_dir
    ):
        """
        Test that _cleanup_repository_files returns False for non-critical failures.
        """
        # Arrange: Create repository directory
        repo_path = os.path.join(temp_dir, "test-repo")
        os.makedirs(repo_path)

        # Mock shutil.rmtree to simulate non-critical permission error
        with patch("shutil.rmtree", side_effect=PermissionError("Permission denied")):
            # Act: Cleanup should handle non-critical error gracefully
            result = golden_repo_manager._cleanup_repository_files(repo_path)

        # Assert: Should return False but not raise exception
        assert result is False

    def test_cleanup_raises_error_for_critical_failures(
        self, golden_repo_manager, temp_dir
    ):
        """
        Test that _cleanup_repository_files raises GitOperationError for critical failures.
        """
        # Arrange: Create repository directory
        repo_path = os.path.join(temp_dir, "test-repo")
        os.makedirs(repo_path)

        # Mock Path to simulate a critical system error that's not caught by specific handlers
        with patch(
            "pathlib.Path", side_effect=RuntimeError("permission denied system failure")
        ):
            # Act & Assert: Should raise GitOperationError for critical failure
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager._cleanup_repository_files(repo_path)

            assert "Critical cleanup failure" in str(exc_info.value)

    def test_remove_golden_repo_succeeds_despite_cleanup_warnings(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that remove_golden_repo succeeds even when cleanup has non-critical issues.

        This verifies the main fix: repository deletion should succeed from a business
        perspective even if some cleanup files remain.
        """
        # Arrange: Mock cleanup to return False (non-critical issues)
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files", return_value=False
        ):
            # Act: Remove repository
            result = golden_repo_manager.remove_golden_repo("test-repo")

        # Assert: Should succeed with warning message
        assert result["success"] is True
        assert "some cleanup issues occurred" in result["message"]
        assert "test-repo" not in golden_repo_manager.golden_repos

    def test_remove_golden_repo_succeeds_with_successful_cleanup(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that remove_golden_repo succeeds with clean message when cleanup is successful.
        """
        # Arrange: Mock cleanup to return True (successful)
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files", return_value=True
        ):
            # Act: Remove repository
            result = golden_repo_manager.remove_golden_repo("test-repo")

        # Assert: Should succeed with clean message
        assert result["success"] is True
        assert "removed successfully" in result["message"]
        assert "cleanup issues" not in result["message"]
        assert "test-repo" not in golden_repo_manager.golden_repos

    def test_remove_golden_repo_still_fails_for_critical_cleanup_errors(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that remove_golden_repo still fails for critical cleanup errors.

        This ensures we didn't make the error handling TOO permissive.
        """
        # Arrange: Mock cleanup to raise critical GitOperationError
        with patch.object(
            golden_repo_manager,
            "_cleanup_repository_files",
            side_effect=GitOperationError("Critical system failure"),
        ):
            # Act & Assert: Should still fail for critical errors
            with pytest.raises(GitOperationError) as exc_info:
                golden_repo_manager.remove_golden_repo("test-repo")

            assert "Critical system failure" in str(exc_info.value)


class TestImprovedRefreshErrorHandling:
    """Test improved repository refresh error handling."""

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

    def test_is_recoverable_init_error_detects_conflicts(self, golden_repo_manager):
        """
        Test that _is_recoverable_init_error correctly identifies recoverable errors.
        """
        # Test recoverable patterns
        recoverable_errors = [
            "Configuration conflict detected",
            "Error: Already initialized in this directory",
            "Error: config file exists",
            "Port 6333 already in use",
            "Service already running on port 8000",
        ]

        for error in recoverable_errors:
            assert golden_repo_manager._is_recoverable_init_error(error) is True

        # Test non-recoverable patterns
        non_recoverable_errors = [
            "Invalid embedding provider",
            "Network connection failed",
            "Disk space full",
            "Permission denied to create config",
        ]

        for error in non_recoverable_errors:
            assert golden_repo_manager._is_recoverable_init_error(error) is False

    def test_is_recoverable_service_error_detects_conflicts(self, golden_repo_manager):
        """
        Test that _is_recoverable_service_error correctly identifies recoverable errors.
        """
        # Test recoverable patterns
        recoverable_errors = [
            "Port 6333 already in use",
            "Service already running",
            "Container qdrant already exists",
            "bind: address already in use",
        ]

        for error in recoverable_errors:
            assert golden_repo_manager._is_recoverable_service_error(error) is True

        # Test non-recoverable patterns
        non_recoverable_errors = [
            "Docker daemon not running",
            "Insufficient memory",
            "Image not found",
            "Network unreachable",
        ]

        for error in non_recoverable_errors:
            assert golden_repo_manager._is_recoverable_service_error(error) is False

    def test_workflow_handles_recoverable_init_conflicts(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that the workflow can recover from init configuration conflicts.
        """
        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                if call_count == 2:  # First init call fails
                    mock_result = Mock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    mock_result.stderr = "Configuration conflict detected"
                    return mock_result
                else:  # Conflict resolution succeeds
                    mock_result = Mock()
                    mock_result.returncode = 0
                    return mock_result
            else:
                # Other commands succeed
                mock_result = Mock()
                mock_result.returncode = 0
                return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Act: Should succeed despite initial init conflict
            result = golden_repo_manager.refresh_golden_repo("test-repo")

        # Assert: Should succeed
        assert result["success"] is True
        assert "refreshed successfully" in result["message"]

    def test_workflow_handles_recoverable_service_conflicts(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that the workflow can recover from service start conflicts.
        """
        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            command = args[0]

            if command[0] == "git" and command[1] == "pull":
                # Git pull succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result
            elif command[0] == "cidx" and command[1] == "init":
                # Init succeeds
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result
            elif command[0] == "cidx" and command[1] == "start":
                if call_count == 3:  # First start call fails
                    mock_result = Mock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    mock_result.stderr = "Port already in use"
                    return mock_result
                else:  # Conflict resolution succeeds
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
            elif command[0] == "cidx" and command[1] == "stop":
                # Stop commands succeed
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
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
            # Act: Should succeed despite initial service conflict
            result = golden_repo_manager.refresh_golden_repo("test-repo")

        # Assert: Should succeed
        assert result["success"] is True
        assert "refreshed successfully" in result["message"]

    def test_workflow_still_fails_for_unrecoverable_errors(
        self, golden_repo_manager, sample_golden_repo
    ):
        """
        Test that the workflow still fails for truly unrecoverable errors.
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
                mock_result.stderr = "Invalid embedding provider specified"
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
