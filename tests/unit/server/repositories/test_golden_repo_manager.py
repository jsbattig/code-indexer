"""
Unit tests for GoldenRepoManager.

Tests the core functionality of golden repository management including:
- Adding golden repositories
- Listing golden repositories
- Removing golden repositories
- Validation and error handling
- Resource limits
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
    ResourceLimitError,
    GitOperationError,
)


class TestGoldenRepoManager:
    """Test suite for GoldenRepoManager functionality."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temp directory."""
        return GoldenRepoManager(data_dir=temp_data_dir)

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
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(
                    golden_repo_manager, "_execute_post_clone_workflow"
                ) as mock_workflow:
                    mock_workflow.return_value = None

                    result = golden_repo_manager.add_golden_repo(
                        repo_url=valid_git_repo_url,
                        alias="hello-world",
                        default_branch="main",
                    )

                    assert result["success"] is True
                    assert (
                        result["message"]
                        == "Golden repository 'hello-world' added successfully"
                    )
                    assert "hello-world" in golden_repo_manager.golden_repos

                    repo = golden_repo_manager.golden_repos["hello-world"]
                    assert repo.repo_url == valid_git_repo_url
                    assert repo.alias == "hello-world"
                    assert repo.default_branch == "main"

                    # Verify workflow was called with force_init=False for initial setup
                    mock_workflow.assert_called_once_with(
                        "/path/to/cloned/repo", force_init=False
                    )

    def test_add_golden_repo_duplicate_alias(
        self, golden_repo_manager, valid_git_repo_url
    ):
        """Test adding golden repository with duplicate alias fails."""
        # Add first repository
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/repo1"
                with patch.object(
                    golden_repo_manager, "_execute_post_clone_workflow"
                ) as mock_workflow:
                    mock_workflow.return_value = None

                    golden_repo_manager.add_golden_repo(
                        repo_url=valid_git_repo_url,
                        alias="test-repo",
                        default_branch="main",
                    )

        # Try to add second repository with same alias
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

    def test_add_golden_repo_exceeds_limit(self, golden_repo_manager):
        """Test adding golden repository exceeds maximum limit."""
        # Mock having 20 existing repos (at limit)
        golden_repo_manager.golden_repos = {
            f"repo-{i}": GoldenRepo(
                alias=f"repo-{i}",
                repo_url=f"https://github.com/test/repo-{i}.git",
                default_branch="main",
                clone_path=f"/path/to/repo-{i}",
                created_at="2023-01-01T00:00:00Z",
            )
            for i in range(20)
        }

        with pytest.raises(
            ResourceLimitError, match="Maximum of 20 golden repositories"
        ):
            golden_repo_manager.add_golden_repo(
                repo_url="https://github.com/test/new-repo.git",
                alias="new-repo",
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

        with patch.object(
            golden_repo_manager, "_cleanup_repository_files"
        ) as mock_cleanup:
            result = golden_repo_manager.remove_golden_repo("test-repo")

            assert result["success"] is True
            assert (
                result["message"]
                == "Golden repository 'test-repo' removed successfully"
            )
            assert "test-repo" not in golden_repo_manager.golden_repos
            mock_cleanup.assert_called_once_with("/path/to/test-repo")

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

    def test_repository_size_validation(self, golden_repo_manager):
        """Test repository size validation during cloning."""
        with patch.object(golden_repo_manager, "_get_repository_size") as mock_size:
            mock_size.return_value = 2 * 1024 * 1024 * 1024  # 2GB (exceeds 1GB limit)
            with patch.object(
                golden_repo_manager, "_validate_git_repository"
            ) as mock_validate:
                mock_validate.return_value = True
                with patch.object(
                    golden_repo_manager, "_clone_repository"
                ) as mock_clone:
                    mock_clone.return_value = "/path/to/large-repo"
                    with patch.object(
                        golden_repo_manager, "_execute_post_clone_workflow"
                    ) as mock_workflow:
                        mock_workflow.return_value = None

                        with pytest.raises(
                            ResourceLimitError,
                            match="Repository size \\(.*\\) exceeds limit",
                        ):
                            golden_repo_manager.add_golden_repo(
                                repo_url="https://github.com/test/large-repo.git",
                                alias="large-repo",
                                default_branch="main",
                            )

    def test_get_repository_size(self, golden_repo_manager, temp_data_dir):
        """Test getting repository size calculation."""
        # Create test directory with files
        test_repo_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(test_repo_path, exist_ok=True)

        # Create test files with known sizes
        test_file1 = os.path.join(test_repo_path, "file1.txt")
        test_file2 = os.path.join(test_repo_path, "file2.txt")

        with open(test_file1, "w") as f:
            f.write("x" * 1000)  # 1000 bytes
        with open(test_file2, "w") as f:
            f.write("y" * 2000)  # 2000 bytes

        size = golden_repo_manager._get_repository_size(test_repo_path)

        # Should be approximately 3000 bytes plus directory overhead
        assert size >= 3000
        assert size < 10000  # Should not be too large

    def test_remove_golden_repo_cleanup_permission_error(self, golden_repo_manager):
        """Test removal when cleanup fails due to permission errors."""
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
                "Permission denied: /root/.local/share/qdrant"
            )
            mock_cleanup.side_effect = GitOperationError(
                f"Failed to clean up repository files: {str(permission_error)}"
            )

            with pytest.raises(
                GitOperationError,
                match="Failed to clean up repository files.*Permission denied",
            ):
                golden_repo_manager.remove_golden_repo("permission-test-repo")

            # Repository should still exist in metadata since cleanup failed
            assert "permission-test-repo" in golden_repo_manager.golden_repos
            mock_cleanup.assert_called_once_with("/path/to/permission-test-repo")

    def test_remove_golden_repo_cleanup_filesystem_error(self, golden_repo_manager):
        """Test removal when cleanup fails due to filesystem errors."""
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

            with pytest.raises(
                GitOperationError,
                match="Failed to clean up repository files.*No such file or directory",
            ):
                golden_repo_manager.remove_golden_repo("filesystem-test-repo")

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
                        result = golden_repo_manager.add_golden_repo(
                            repo_url=tmp_repo_url,
                            alias="tmp-test-repo",
                            default_branch="main",
                        )

                        # Verify success
                        assert result["success"] is True
                        assert "tmp-test-repo" in result["message"]

                        # Verify the fixed regular copy method was called
                        mock_regular_copy.assert_called_once()

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
        }

        assert result == expected
