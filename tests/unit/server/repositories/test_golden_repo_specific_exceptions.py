"""
Test specific exception handling in GoldenRepoManager.

Tests verify that GoldenRepoManager handles specific exceptions correctly
instead of using generic Exception handlers that violate CLAUDE.md Foundation #8.
"""

import os
import subprocess
import tempfile
from unittest import mock
import pytest

from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GitOperationError,
)


class TestGoldenRepoManagerSpecificExceptions:
    """Test specific exception handling in GoldenRepoManager."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temporary data directory."""
        return GoldenRepoManager(data_dir=temp_data_dir)

    def test_clone_operation_subprocess_error_line_167(self, manager):
        """Test that line 167 handles subprocess.CalledProcessError specifically."""
        # Test the add_golden_repo method where line 167 exception occurs
        with mock.patch.object(manager, "_validate_git_repository", return_value=True):
            with mock.patch.object(manager, "_clone_repository") as mock_clone:
                # Simulate subprocess.CalledProcessError from clone operation
                mock_clone.side_effect = subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "clone"], stderr="Authentication failed"
                )

                with pytest.raises(GitOperationError) as exc_info:
                    manager.add_golden_repo(
                        "https://github.com/invalid/repo.git", "test-alias", "main"
                    )

                assert "Failed to clone repository" in str(exc_info.value)
                assert "Git process failed with exit code 128" in str(exc_info.value)

    def test_clone_operation_timeout_error_line_167(self, manager):
        """Test that line 167 handles subprocess.TimeoutExpired specifically."""
        # Test the add_golden_repo method where line 167 exception occurs
        with mock.patch.object(manager, "_validate_git_repository", return_value=True):
            with mock.patch.object(manager, "_clone_repository") as mock_clone:
                # Simulate subprocess.TimeoutExpired from clone operation
                mock_clone.side_effect = subprocess.TimeoutExpired(
                    cmd=["git", "clone"], timeout=300
                )

                with pytest.raises(GitOperationError) as exc_info:
                    manager.add_golden_repo(
                        "https://github.com/slow/repo.git", "test-alias", "main"
                    )

                assert "Failed to clone repository" in str(exc_info.value)
                assert "Git operation timed out after 300 seconds" in str(
                    exc_info.value
                )

    def test_local_copy_permission_error_line_342(self, manager):
        """Test that line 342 handles PermissionError specifically."""
        # Test the _clone_local_repository_with_regular_copy method
        source_path = "/tmp/nonexistent"
        clone_path = "/tmp/destination"

        with mock.patch("shutil.copytree") as mock_copy:
            # Simulate PermissionError
            mock_copy.side_effect = PermissionError("Permission denied")

            with pytest.raises(GitOperationError) as exc_info:
                manager._clone_local_repository_with_regular_copy(
                    source_path, clone_path
                )

            assert "Failed to copy local repository" in str(exc_info.value)
            assert "Permission denied" in str(exc_info.value)

    def test_local_copy_file_not_found_error_line_342(self, manager):
        """Test that line 342 handles FileNotFoundError specifically."""
        source_path = "/tmp/nonexistent"
        clone_path = "/tmp/destination"

        with mock.patch("shutil.copytree") as mock_copy:
            # Simulate FileNotFoundError
            mock_copy.side_effect = FileNotFoundError("Source directory not found")

            with pytest.raises(GitOperationError) as exc_info:
                manager._clone_local_repository_with_regular_copy(
                    source_path, clone_path
                )

            assert "Failed to copy local repository" in str(exc_info.value)
            assert "Source directory not found" in str(exc_info.value)

    def test_workflow_subprocess_error_line_671(self, manager, temp_data_dir):
        """Test that line 671 handles subprocess.CalledProcessError specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError in workflow execution
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["cidx", "init"], stderr="Init failed"
            )

            with pytest.raises(GitOperationError) as exc_info:
                manager._execute_post_clone_workflow(clone_path)

            assert "Post-clone workflow failed" in str(exc_info.value)

    def test_workflow_timeout_error_line_671(self, manager, temp_data_dir):
        """Test that line 671 handles subprocess.TimeoutExpired specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.TimeoutExpired in workflow execution
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["cidx", "init"], timeout=300
            )

            with pytest.raises(GitOperationError) as exc_info:
                manager._execute_post_clone_workflow(clone_path)

            assert "Post-clone workflow timed out" in str(exc_info.value)

    def test_refresh_subprocess_error_line_725(self, manager, temp_data_dir):
        """Test that line 725 handles subprocess.CalledProcessError specifically."""
        # Create a golden repo in manager
        golden_repo_data = {
            "alias": "test-repo",
            "repo_url": "https://github.com/test/repo.git",
            "default_branch": "main",
            "clone_path": os.path.join(temp_data_dir, "test-repo"),
            "created_at": "2024-01-01T00:00:00Z",
        }

        from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo

        manager.golden_repos["test-repo"] = GoldenRepo(**golden_repo_data)

        # Create clone directory
        os.makedirs(golden_repo_data["clone_path"])

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError in git pull
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["git", "pull"], stderr="Pull failed"
            )

            with pytest.raises(GitOperationError) as exc_info:
                manager.refresh_golden_repo("test-repo")

            assert "Failed to refresh repository" in str(exc_info.value)

    def test_init_conflict_resolution_subprocess_error_line_812(
        self, manager, temp_data_dir
    ):
        """Test that line 812 handles subprocess.CalledProcessError specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError in init conflict resolution
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["cidx", "init"], stderr="Init conflict"
            )

            result = manager._attempt_init_conflict_resolution(clone_path, False)

            # Should return False when subprocess fails
            assert result is False

    def test_init_conflict_resolution_timeout_error_line_812(
        self, manager, temp_data_dir
    ):
        """Test that line 812 handles subprocess.TimeoutExpired specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.TimeoutExpired in init conflict resolution
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["cidx", "init"], timeout=300
            )

            result = manager._attempt_init_conflict_resolution(clone_path, False)

            # Should return False when subprocess times out
            assert result is False

    def test_service_conflict_resolution_subprocess_error_line_855(
        self, manager, temp_data_dir
    ):
        """Test that line 855 handles subprocess.CalledProcessError specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError in service conflict resolution
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["cidx", "start"], stderr="Service conflict"
            )

            result = manager._attempt_service_conflict_resolution(clone_path)

            # Should return False when subprocess fails
            assert result is False

    def test_service_conflict_resolution_timeout_error_line_855(
        self, manager, temp_data_dir
    ):
        """Test that line 855 handles subprocess.TimeoutExpired specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.TimeoutExpired in service conflict resolution
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["cidx", "start"], timeout=300
            )

            result = manager._attempt_service_conflict_resolution(clone_path)

            # Should return False when subprocess times out
            assert result is False

    def test_status_check_subprocess_error_line_884(self, manager, temp_data_dir):
        """Test that line 884 handles subprocess.CalledProcessError specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError in status check
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["cidx", "status"], stderr="Status check failed"
            )

            # Should return True (assume services are down) when subprocess fails
            result = manager._wait_for_service_cleanup(clone_path, timeout=1)
            assert result is True

    def test_status_check_timeout_error_line_884(self, manager, temp_data_dir):
        """Test that line 884 handles subprocess.TimeoutExpired specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate subprocess.TimeoutExpired in status check
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["cidx", "status"], timeout=5
            )

            # Should return True (assume services are down) when subprocess times out
            result = manager._wait_for_service_cleanup(clone_path, timeout=1)
            assert result is True

    def test_status_check_permission_error_line_884(self, manager, temp_data_dir):
        """Test that line 884 handles PermissionError specifically."""
        clone_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(clone_path)

        with mock.patch("subprocess.run") as mock_run:
            # Simulate PermissionError in status check
            mock_run.side_effect = PermissionError("Permission denied")

            # Should return True (assume services are down) when permission denied
            result = manager._wait_for_service_cleanup(clone_path, timeout=1)
            assert result is True
