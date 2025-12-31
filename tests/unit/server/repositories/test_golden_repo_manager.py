"""
Unit tests for GoldenRepoManager.

Tests the core functionality of golden repository management including:
- Adding golden repositories
- Listing golden repositories
- Removing golden repositories
- Validation and error handling
"""

import json
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
    GoldenRepoError,
    GitOperationError,
)
from src.code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestGoldenRepoManager:
    """Test suite for GoldenRepoManager functionality."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temp directory and mocked background job manager."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)
        # Inject mock BackgroundJobManager
        mock_bg_manager = MagicMock(spec=BackgroundJobManager)
        mock_bg_manager.submit_job.return_value = "test-job-id-12345"
        manager.background_job_manager = mock_bg_manager
        return manager

    @pytest.fixture
    def valid_git_repo_url(self):
        """Valid git repository URL for testing."""
        return "https://github.com/octocat/Hello-World.git"

    def test_initialization_creates_data_directory(self, temp_data_dir):
        """Test that GoldenRepoManager creates data directory on initialization."""
        # Remove the directory to test creation
        shutil.rmtree(temp_data_dir)
        assert not os.path.exists(temp_data_dir)

        manager = GoldenRepoManager(data_dir=temp_data_dir)

        assert os.path.exists(temp_data_dir)
        assert os.path.exists(manager.golden_repos_dir)
        assert os.path.exists(manager.metadata_file)

    def test_initialization_loads_existing_metadata(self, temp_data_dir):
        """Test that GoldenRepoManager loads existing metadata on initialization."""
        # Create metadata file with test data
        metadata_file = os.path.join(temp_data_dir, "golden-repos", "metadata.json")
        os.makedirs(os.path.dirname(metadata_file), exist_ok=True)

        test_data = {
            "test-repo": {
                "alias": "test-repo",
                "repo_url": "https://github.com/test/repo.git",
                "default_branch": "main",
                "clone_path": "/path/to/clone",
                "created_at": "2023-01-01T00:00:00Z",
            }
        }

        with open(metadata_file, "w") as f:
            json.dump(test_data, f)

        manager = GoldenRepoManager(data_dir=temp_data_dir)

        assert len(manager.golden_repos) == 1
        assert "test-repo" in manager.golden_repos
        assert manager.golden_repos["test-repo"].alias == "test-repo"

    def test_add_golden_repo_success(self, golden_repo_manager, valid_git_repo_url):
        """Test successfully adding a golden repository."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            result = golden_repo_manager.add_golden_repo(
                repo_url=valid_git_repo_url,
                alias="hello-world",
                default_branch="main",
            )

            # Should return job_id string
            assert isinstance(result, str)
            assert result == "test-job-id-12345"

            # Verify job was submitted
            golden_repo_manager.background_job_manager.submit_job.assert_called_once()

            # Note: The repo won't be in golden_repos immediately since it's async
            # The background worker would add it, but we're not testing that here

    def test_add_golden_repo_duplicate_alias(
        self, golden_repo_manager, valid_git_repo_url
    ):
        """Test adding golden repository with duplicate alias fails."""
        # Manually add a repo to test duplicate alias validation
        from datetime import datetime, timezone

        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url=valid_git_repo_url,
            default_branch="main",
            clone_path="/path/to/repo1",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Try to add second repository with same alias - should fail validation
        with pytest.raises(GoldenRepoError, match="alias 'test-repo' already exists"):
            golden_repo_manager.add_golden_repo(
                repo_url="https://github.com/other/repo.git",
                alias="test-repo",
                default_branch="main",
            )

    def test_add_golden_repo_invalid_git_url(self, golden_repo_manager):
        """Test adding golden repository with invalid git URL fails."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = False

            with pytest.raises(
                GitOperationError, match="Invalid or inaccessible git repository"
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://invalid-url.com/not-a-repo.git",
                    alias="invalid-repo",
                    default_branch="main",
                )

    def test_list_golden_repos_empty(self, golden_repo_manager):
        """Test listing golden repositories when none exist."""
        result = golden_repo_manager.list_golden_repos()

        assert result == []

    def test_list_golden_repos_with_data(self, golden_repo_manager):
        """Test listing golden repositories with existing data."""
        # Add test repositories
        test_repos = {
            "repo-1": GoldenRepo(
                alias="repo-1",
                repo_url="https://github.com/test/repo-1.git",
                default_branch="main",
                clone_path="/path/to/repo-1",
                created_at="2023-01-01T00:00:00Z",
            ),
            "repo-2": GoldenRepo(
                alias="repo-2",
                repo_url="https://github.com/test/repo-2.git",
                default_branch="develop",
                clone_path="/path/to/repo-2",
                created_at="2023-01-02T00:00:00Z",
            ),
        }
        golden_repo_manager.golden_repos = test_repos

        result = golden_repo_manager.list_golden_repos()

        assert len(result) == 2
        assert result[0]["alias"] == "repo-1"
        assert result[0]["repo_url"] == "https://github.com/test/repo-1.git"
        assert result[1]["alias"] == "repo-2"
        assert result[1]["default_branch"] == "develop"

    def test_remove_golden_repo_success(self, golden_repo_manager):
        """Test successfully removing a golden repository."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        with patch.object(golden_repo_manager, "_cleanup_repository_files"):
            result = golden_repo_manager.remove_golden_repo("test-repo")

            # Should return job_id string
            assert isinstance(result, str)
            assert result == "test-job-id-12345"

            # Verify job was submitted
            golden_repo_manager.background_job_manager.submit_job.assert_called_once()

            # Note: The repo won't be removed from golden_repos immediately since it's async
            # The background worker would remove it, but we're not testing that here

    def test_remove_golden_repo_not_found(self, golden_repo_manager):
        """Test removing non-existent golden repository fails."""
        with pytest.raises(
            GoldenRepoError, match="Golden repository 'nonexistent' not found"
        ):
            golden_repo_manager.remove_golden_repo("nonexistent")

    def test_validate_git_repository_success(self, golden_repo_manager):
        """Test git repository validation with valid repository."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = golden_repo_manager._validate_git_repository(
                "https://github.com/test/repo.git"
            )

            assert result is True
            mock_run.assert_called_once()

    def test_validate_git_repository_failure(self, golden_repo_manager):
        """Test git repository validation with invalid repository."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128)  # Git error code

            result = golden_repo_manager._validate_git_repository(
                "https://invalid.com/repo.git"
            )

            assert result is False

    def test_clone_repository_success(self, golden_repo_manager):
        """Test successful repository cloning."""
        repo_url = "https://github.com/test/repo.git"
        alias = "test-repo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = golden_repo_manager._clone_repository(repo_url, alias, "main")

            expected_path = os.path.join(golden_repo_manager.golden_repos_dir, alias)
            assert result == expected_path

            # Verify git clone was called with correct parameters
            mock_run.assert_called()
            call_args = mock_run.call_args[0][0]
            assert "git" in call_args
            assert "clone" in call_args
            assert repo_url in call_args

    def test_clone_repository_failure(self, golden_repo_manager):
        """Test repository cloning failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr="Clone failed")

            with pytest.raises(GitOperationError, match="Git clone failed with code"):
                golden_repo_manager._clone_repository(
                    "https://invalid.com/repo.git", "invalid-repo", "main"
                )

    def test_cleanup_repository_files(self, golden_repo_manager, temp_data_dir):
        """Test cleanup of repository files."""
        # Create test directory structure
        test_repo_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(test_repo_path, exist_ok=True)
        test_file = os.path.join(test_repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        assert os.path.exists(test_repo_path)
        assert os.path.exists(test_file)

        golden_repo_manager._cleanup_repository_files(test_repo_path)

        assert not os.path.exists(test_repo_path)

    def test_save_metadata(self, golden_repo_manager):
        """Test saving metadata to file."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        golden_repo_manager._save_metadata()

        # Verify metadata file exists and contains correct data
        assert os.path.exists(golden_repo_manager.metadata_file)

        with open(golden_repo_manager.metadata_file, "r") as f:
            data = json.load(f)

        assert "test-repo" in data
        assert data["test-repo"]["alias"] == "test-repo"
        assert data["test-repo"]["repo_url"] == "https://github.com/test/repo.git"

    def test_remove_golden_repo_cleanup_permission_error(self, golden_repo_manager):
        """Test removal when cleanup fails due to permission errors (async refactored version)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="permission-test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/permission-test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["permission-test-repo"] = test_repo

        # Mock cleanup to raise PermissionError (which gets wrapped in GitOperationError)
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files"
        ) as mock_cleanup:
            permission_error = PermissionError(
                "Permission denied: /root/.local/share/filesystem"
            )
            mock_cleanup.side_effect = GitOperationError(
                f"Failed to clean up repository files: {str(permission_error)}"
            )

            # After async refactoring, remove_golden_repo returns job_id
            # The exception is raised when background worker executes
            job_id = golden_repo_manager.remove_golden_repo("permission-test-repo")

            # Verify job_id was returned
            assert isinstance(job_id, str)

            # Execute the background worker to trigger the exception
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            with pytest.raises(
                GitOperationError,
                match="Failed to clean up repository files.*Permission denied",
            ):
                background_worker()

            # Repository should still exist in metadata since cleanup failed
            assert "permission-test-repo" in golden_repo_manager.golden_repos
            mock_cleanup.assert_called_once_with("/path/to/permission-test-repo")

    def test_remove_golden_repo_cleanup_filesystem_error(self, golden_repo_manager):
        """Test removal when cleanup fails due to filesystem errors (async refactored version)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="filesystem-test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/filesystem-test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["filesystem-test-repo"] = test_repo

        # Mock cleanup to raise OSError (which gets wrapped in GitOperationError)
        with patch.object(
            golden_repo_manager, "_cleanup_repository_files"
        ) as mock_cleanup:
            os_error = OSError("No such file or directory")
            mock_cleanup.side_effect = GitOperationError(
                f"Failed to clean up repository files: {str(os_error)}"
            )

            # After async refactoring, remove_golden_repo returns job_id
            # The exception is raised when background worker executes
            job_id = golden_repo_manager.remove_golden_repo("filesystem-test-repo")

            # Verify job_id was returned
            assert isinstance(job_id, str)

            # Execute the background worker to trigger the exception
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            with pytest.raises(
                GitOperationError,
                match="Failed to clean up repository files.*No such file or directory",
            ):
                background_worker()

            # Repository should still exist in metadata since cleanup failed
            assert "filesystem-test-repo" in golden_repo_manager.golden_repos
            mock_cleanup.assert_called_once_with("/path/to/filesystem-test-repo")

    def test_regular_copy_always_used_for_local_repos(self, golden_repo_manager):
        """Test that regular copying is always used for local repository registration."""
        # Create a temporary directory to simulate /tmp (different filesystem)
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_source:
            # Create a test repository in the temp directory
            test_repo_path = os.path.join(tmp_source, "test-repo")
            os.makedirs(test_repo_path)

            # Create a test file
            test_file = os.path.join(test_repo_path, "README.md")
            with open(test_file, "w") as f:
                f.write("# Test Repository")

            dest_path = os.path.join(golden_repo_manager.golden_repos_dir, "test-dest")

            # Test the new behavior - always uses regular copy
            with patch("shutil.copytree") as mock_copytree:
                result_path = (
                    golden_repo_manager._clone_local_repository_with_regular_copy(
                        test_repo_path, dest_path
                    )
                )

                # Verify regular copy was used (no CoW attempts)
                mock_copytree.assert_called_once_with(
                    test_repo_path, dest_path, symlinks=True
                )
                assert result_path == dest_path

    def test_fixed_tmp_to_golden_repo_registration(self, golden_repo_manager):
        """
        Test that registering local repositories from /tmp now works correctly.

        This test verifies the FIXED behavior that uses regular copying
        instead of CoW for cross-device operations.
        """
        # Simulate registering a local repository from /tmp
        tmp_repo_url = "/tmp/test-repo"

        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True
            with patch.object(
                golden_repo_manager, "_execute_post_clone_workflow"
            ) as mock_workflow:
                mock_workflow.return_value = None
                with patch.object(
                    golden_repo_manager, "_is_local_path"
                ) as mock_is_local:
                    mock_is_local.return_value = True  # It's a local path
                    with patch.object(
                        golden_repo_manager, "_clone_local_repository_with_regular_copy"
                    ) as mock_regular_copy:
                        mock_regular_copy.return_value = "/path/to/cloned/repo"

                        # This should now succeed with regular copying (no more cross-device link errors)
                        # After async refactoring, add_golden_repo returns job_id
                        job_id = golden_repo_manager.add_golden_repo(
                            repo_url=tmp_repo_url,
                            alias="tmp-test-repo",
                            default_branch="main",
                        )

                        # Verify job_id was returned
                        assert isinstance(job_id, str)
                        assert len(job_id) > 0

                        # Verify the fixed regular copy method was called
                        # (Execution happens in background worker, but validation already passed)
                        assert (
                            golden_repo_manager.background_job_manager.submit_job.called
                        )

    def test_should_not_use_cow_for_golden_repo_registration(self, golden_repo_manager):
        """
        Test that Golden Repository registration should NOT use CoW cloning.

        This test verifies the FIXED behavior: Golden repo registration should
        use regular copying, not CoW cloning, regardless of filesystem support.
        """
        # Create a temporary source repository
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_source:
            test_repo_path = os.path.join(tmp_source, "test-repo")
            os.makedirs(test_repo_path)

            # Create test content
            with open(os.path.join(test_repo_path, "test.txt"), "w") as f:
                f.write("test content")

            dest_path = os.path.join(
                golden_repo_manager.golden_repos_dir, "correct-repo"
            )

            # Test the corrected behavior - should use regular copy, not CoW
            with patch("shutil.copytree") as mock_copytree:
                # This now uses the FIXED implementation
                result_path = (
                    golden_repo_manager._clone_local_repository_with_regular_copy(
                        test_repo_path, dest_path
                    )
                )

                # Verify regular copy was used
                mock_copytree.assert_called_once_with(
                    test_repo_path, dest_path, symlinks=True
                )
                assert result_path == dest_path

    def test_fixed_local_repository_cloning_no_cow(self, golden_repo_manager):
        """
        Test that local repository cloning now uses regular copy instead of CoW.

        This test verifies the fix by ensuring that _clone_repository calls
        the regular copy method for local paths, not the CoW method.
        """
        with patch.object(golden_repo_manager, "_is_local_path") as mock_is_local:
            mock_is_local.return_value = True
            with patch.object(
                golden_repo_manager, "_clone_local_repository_with_regular_copy"
            ) as mock_regular_copy:
                mock_regular_copy.return_value = "/path/to/dest"

                result = golden_repo_manager._clone_repository(
                    "/tmp/source", "test-alias", "main"
                )

                # Verify that regular copy method was called, not CoW
                mock_regular_copy.assert_called_once_with(
                    "/tmp/source",
                    os.path.join(golden_repo_manager.golden_repos_dir, "test-alias"),
                )
                assert result == "/path/to/dest"

    def test_cow_methods_removed_from_golden_repo_manager(self, golden_repo_manager):
        """
        Test that CoW-specific methods have been removed from GoldenRepoManager.

        These methods are inappropriate for golden repository registration
        and should only exist in ActivatedRepoManager.
        """
        # Verify CoW methods are removed from golden repo manager
        assert not hasattr(golden_repo_manager, "_supports_cow")
        assert not hasattr(golden_repo_manager, "_cow_clone")
        assert not hasattr(golden_repo_manager, "_clone_local_repository_with_cow")

        # Verify the new regular copy method exists
        assert hasattr(golden_repo_manager, "_clone_local_repository_with_regular_copy")

    def test_initialization_requires_data_dir(self):
        """Test that GoldenRepoManager raises ValueError when data_dir is None."""
        with pytest.raises(
            ValueError, match="data_dir is required and cannot be None or empty"
        ):
            GoldenRepoManager(data_dir=None)

    def test_initialization_rejects_empty_data_dir(self):
        """Test that GoldenRepoManager raises ValueError when data_dir is empty string."""
        with pytest.raises(
            ValueError, match="data_dir is required and cannot be None or empty"
        ):
            GoldenRepoManager(data_dir="")

    def test_initialization_rejects_whitespace_data_dir(self):
        """Test that GoldenRepoManager raises ValueError when data_dir is only whitespace."""
        with pytest.raises(
            ValueError, match="data_dir is required and cannot be None or empty"
        ):
            GoldenRepoManager(data_dir="   ")

    def test_initialization_accepts_valid_data_dir(self, temp_data_dir):
        """Test that GoldenRepoManager initializes successfully with valid data_dir."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)
        assert manager.data_dir == temp_data_dir
        assert os.path.exists(manager.golden_repos_dir)

    def test_add_index_to_golden_repo_success(self, golden_repo_manager):
        """Test successfully adding an index type to an existing golden repository (AC1)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Mock index existence check to return False (no existing index)
        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            result = golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="temporal", submitter_username="admin"
            )

            # Should return job_id string
            assert isinstance(result, str)
            assert result == "test-job-id-12345"

            # Verify job was submitted with correct parameters
            golden_repo_manager.background_job_manager.submit_job.assert_called_once()
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            assert call_args[1]["operation_type"] == "add_index"
            assert call_args[1]["submitter_username"] == "admin"
            assert call_args[1]["is_admin"] is True

    def test_add_index_to_golden_repo_invalid_index_type(self, golden_repo_manager):
        """Test adding index with invalid index_type raises ValueError (AC2)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        with pytest.raises(
            ValueError,
            match="Invalid index_type: invalid_type. Must be one of: semantic_fts, temporal, scip",
        ):
            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="invalid_type", submitter_username="admin"
            )

        # No job should be created on validation failure
        golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    def test_add_index_to_golden_repo_nonexistent_alias(self, golden_repo_manager):
        """Test adding index to non-existent alias raises ValueError (AC4)."""
        with pytest.raises(
            ValueError, match="Golden repository 'nonexistent' not found"
        ):
            golden_repo_manager.add_index_to_golden_repo(
                alias="nonexistent", index_type="temporal", submitter_username="admin"
            )

        # No job should be created on validation failure
        golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    def test_add_index_to_golden_repo_index_already_exists(self, golden_repo_manager):
        """Test adding index when it already exists raises ValueError (AC3)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Mock index existence check to return True (index already exists)
        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = True

            with pytest.raises(
                ValueError,
                match="Index type 'temporal' already exists for golden repo 'test-repo'",
            ):
                golden_repo_manager.add_index_to_golden_repo(
                    alias="test-repo", index_type="temporal", submitter_username="admin"
                )

            # No job should be created when index already exists
            golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    def test_background_worker_semantic_fts_execution(self, golden_repo_manager):
        """Test background worker executes correct command for semantic_fts index (AC5)."""
        # Add test repository with actual path
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Mock index existence check
        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            # Call add_index_to_golden_repo
            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="semantic_fts", submitter_username="admin"
            )

            # Get the background worker function
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            # Execute the background worker and verify command
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                result = background_worker()

                # Verify cidx index --fts was called with correct cwd
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                command = call_args[0][0]
                cwd = call_args[1]["cwd"]

                assert command == ["cidx", "index", "--fts"]
                assert cwd == test_repo.clone_path
                assert result["success"] is True

    def test_background_worker_temporal_execution(self, golden_repo_manager):
        """Test background worker executes correct command for temporal index (AC6)."""
        # Add test repository with temporal options
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
            enable_temporal=True,
            temporal_options={
                "max_commits": 500,
                "since_date": "2024-01-01",
                "diff_context": 10,
            },
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Mock index existence check
        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            # Call add_index_to_golden_repo
            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="temporal", submitter_username="admin"
            )

            # Get the background worker function
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            # Execute the background worker and verify command
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                result = background_worker()

                # Verify cidx index --index-commits was called with options
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                command = call_args[0][0]
                cwd = call_args[1]["cwd"]

                assert "cidx" in command
                assert "index" in command
                assert "--index-commits" in command
                assert "--max-commits" in command
                assert "500" in command
                assert "--since-date" in command
                assert "2024-01-01" in command
                assert "--diff-context" in command
                assert "10" in command
                assert cwd == test_repo.clone_path
                assert result["success"] is True

    def test_background_worker_scip_execution(self, golden_repo_manager):
        """Test background worker executes correct command for SCIP index (AC7)."""
        # Add test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Mock index existence check
        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            # Call add_index_to_golden_repo
            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="scip", submitter_username="admin"
            )

            # Get the background worker function
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            # Execute the background worker and verify command
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                result = background_worker()

                # Verify cidx scip generate was called with correct cwd
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                command = call_args[0][0]
                cwd = call_args[1]["cwd"]

                assert command == ["cidx", "scip", "generate"]
                assert cwd == test_repo.clone_path
                assert result["success"] is True

    def test_background_worker_no_timeout_for_long_operations(
        self, golden_repo_manager
    ):
        """Test that subprocess calls do NOT include timeout parameter for long-running operations.

        Background jobs should run without timeout limits:
        - semantic_fts indexing: 10-30 minutes for medium repos
        - temporal indexing: 30-60 minutes for large repos
        - SCIP generation: can take HOURS for large repos
        """
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            for index_type in ["semantic_fts", "temporal", "scip"]:
                golden_repo_manager.add_index_to_golden_repo(
                    alias="test-repo", index_type=index_type, submitter_username="admin"
                )

                # Get the background worker function
                call_args = (
                    golden_repo_manager.background_job_manager.submit_job.call_args
                )
                background_worker = call_args[1]["func"]

                # Execute and verify NO timeout parameter
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0, stdout="", stderr=""
                    )
                    background_worker()

                    # Verify timeout parameter is NOT present or is None
                    call_kwargs = mock_run.call_args[1]
                    timeout_value = call_kwargs.get("timeout")
                    assert timeout_value is None, (
                        f"timeout should be None for {index_type}, but was {timeout_value}. "
                        f"Background jobs should run without timeout limits."
                    )

    def test_background_worker_captures_stdout_stderr(self, golden_repo_manager):
        """Test that background worker captures and returns stdout/stderr (CRITICAL ISSUE #3)."""
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="semantic_fts", submitter_username="admin"
            )

            # Get the background worker function
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            # Execute and verify stdout/stderr capture
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="Index created successfully",
                    stderr="Processing 100 files...",
                )

                result = background_worker()

                # Verify result contains stdout and stderr
                assert result["success"] is True
                assert "stdout" in result, "Missing stdout in result"
                assert "stderr" in result, "Missing stderr in result"
                assert result["stdout"] == "Index created successfully"
                assert result["stderr"] == "Processing 100 files..."

    def test_background_worker_temporal_default_options(self, golden_repo_manager):
        """Test that temporal index uses correct default options (AC6)."""
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(golden_repo_manager.golden_repos_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
            enable_temporal=False,
            temporal_options=None,  # No options provided
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        with patch.object(golden_repo_manager, "_index_exists") as mock_index_exists:
            mock_index_exists.return_value = False

            golden_repo_manager.add_index_to_golden_repo(
                alias="test-repo", index_type="temporal", submitter_username="admin"
            )

            # Get the background worker function
            call_args = golden_repo_manager.background_job_manager.submit_job.call_args
            background_worker = call_args[1]["func"]

            # Execute and verify default options are in command
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                background_worker()

                call_args = mock_run.call_args
                command = call_args[0][0]

                # Verify required base flags
                assert "cidx" in command
                assert "index" in command
                assert "--index-commits" in command
                # Verify default max-commits (1000)
                assert "--max-commits" in command
                assert "1000" in command
                # Verify default diff-context (5)
                assert "--diff-context" in command
                assert "5" in command

    def test_index_exists_semantic_fts_validates_actual_files(
        self, golden_repo_manager, temp_data_dir
    ):
        """Test that _index_exists checks for actual index files, not just directories (CRITICAL ISSUE #9)."""
        # Create test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=os.path.join(temp_data_dir, "test-repo"),
            created_at="2023-01-01T00:00:00Z",
        )

        # Create directories but no actual index files
        index_dir = os.path.join(test_repo.clone_path, ".code-indexer", "index")
        fts_dir = os.path.join(test_repo.clone_path, ".code-indexer", "tantivy_index")
        os.makedirs(index_dir, exist_ok=True)
        os.makedirs(fts_dir, exist_ok=True)

        # Should return False because directories are empty
        assert golden_repo_manager._index_exists(test_repo, "semantic_fts") is False

        # Create actual index files
        collection_dir = os.path.join(index_dir, "test_collection")
        os.makedirs(collection_dir, exist_ok=True)
        with open(os.path.join(collection_dir, "vector_1.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(fts_dir, "meta.json"), "w") as f:
            f.write("{}")

        # Now should return True
        assert golden_repo_manager._index_exists(test_repo, "semantic_fts") is True


class TestGoldenRepo:
    """Test suite for GoldenRepo model."""

    def test_golden_repo_creation(self):
        """Test GoldenRepo model creation and validation."""
        repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/repo",
            created_at="2023-01-01T00:00:00Z",
        )

        assert repo.alias == "test-repo"
        assert repo.repo_url == "https://github.com/test/repo.git"
        assert repo.default_branch == "main"
        assert repo.clone_path == "/path/to/repo"
        assert repo.created_at == "2023-01-01T00:00:00Z"

    def test_golden_repo_to_dict(self):
        """Test GoldenRepo model serialization to dictionary."""
        repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/repo",
            created_at="2023-01-01T00:00:00Z",
        )

        result = repo.to_dict()

        expected = {
            "alias": "test-repo",
            "repo_url": "https://github.com/test/repo.git",
            "default_branch": "main",
            "clone_path": "/path/to/repo",
            "created_at": "2023-01-01T00:00:00Z",
            "enable_temporal": False,
            "temporal_options": None,
        }

        assert result == expected
