"""
Unit tests for ActivatedRepoManager.

Tests the core functionality of activated repository management including:
- Activating repositories for users
- Listing user's activated repositories
- Deactivating repositories
- Branch management
- Copy-on-write cloning from golden repositories
- Integration with background job system
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepo,
    ActivatedRepoError,
    GitOperationError,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo


class TestActivatedRepoManager:
    """Test suite for ActivatedRepoManager functionality."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager_mock(self):
        """Mock golden repo manager."""
        mock = MagicMock()

        # Mock golden repo data
        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/example/test-repo.git",
            default_branch="main",
            clone_path="/path/to/golden/test-repo",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        mock.golden_repos = {"test-repo": golden_repo}
        return mock

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager."""
        mock = MagicMock()
        mock.submit_job.return_value = "job-123"
        return mock

    @pytest.fixture
    def activated_repo_manager(
        self, temp_data_dir, golden_repo_manager_mock, background_job_manager_mock
    ):
        """Create ActivatedRepoManager instance with temp directory."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_initialization_creates_activated_repos_directory(self, temp_data_dir):
        """Test that ActivatedRepoManager creates activated repos directory on initialization."""
        # Remove the directory to test creation
        activated_dir = os.path.join(temp_data_dir, "activated-repos")
        if os.path.exists(activated_dir):
            shutil.rmtree(activated_dir)

        ActivatedRepoManager(data_dir=temp_data_dir)

        # Check directory is created
        assert os.path.exists(activated_dir)
        assert os.path.isdir(activated_dir)

    def test_initialization_with_default_data_dir(self):
        """Test initialization with default data directory."""
        with patch("pathlib.Path.home") as mock_home:
            import tempfile

            mock_home.return_value = Path(tempfile.gettempdir()) / "test_user"

            with patch("os.makedirs") as mock_makedirs:
                with patch(
                    "src.code_indexer.server.repositories.activated_repo_manager.GoldenRepoManager"
                ):
                    with patch(
                        "src.code_indexer.server.repositories.activated_repo_manager.BackgroundJobManager"
                    ):
                        ActivatedRepoManager()

                        expected_activated_dir = str(
                            Path(tempfile.gettempdir())
                            / "test_user"
                            / ".cidx-server"
                            / "data"
                            / "activated-repos"
                        )
                        mock_makedirs.assert_called_with(
                            expected_activated_dir, exist_ok=True
                        )

    def test_activate_repository_success(
        self, activated_repo_manager, background_job_manager_mock
    ):
        """Test successful repository activation."""
        username = "testuser"
        golden_repo_alias = "test-repo"
        branch_name = "main"
        user_alias = "my-repo"

        # Test activation
        job_id = activated_repo_manager.activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name=branch_name,
            user_alias=user_alias,
        )

        # Verify job was submitted
        assert job_id == "job-123"
        background_job_manager_mock.submit_job.assert_called_once()

        # Verify job was submitted with correct parameters
        call_args = background_job_manager_mock.submit_job.call_args
        assert call_args[0][0] == "activate_repository"  # operation_type

    def test_activate_repository_golden_repo_not_found(self, activated_repo_manager):
        """Test activation fails when golden repo doesn't exist."""
        username = "testuser"
        golden_repo_alias = "nonexistent-repo"

        with pytest.raises(
            ActivatedRepoError, match="Golden repository 'nonexistent-repo' not found"
        ):
            activated_repo_manager.activate_repository(
                username=username, golden_repo_alias=golden_repo_alias
            )

    def test_activate_repository_already_activated(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test activation fails when repository already activated for user."""
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Create user directory and existing activation
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        os.makedirs(user_dir, exist_ok=True)

        existing_activation = {
            "user_alias": user_alias,
            "golden_repo_alias": golden_repo_alias,
            "current_branch": "main",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(existing_activation, f)

        # Create corresponding repo directory
        repo_dir = os.path.join(user_dir, user_alias)
        os.makedirs(repo_dir, exist_ok=True)

        # Test activation fails
        with pytest.raises(
            ActivatedRepoError, match="Repository 'my-repo' already activated"
        ):
            activated_repo_manager.activate_repository(
                username=username,
                golden_repo_alias=golden_repo_alias,
                user_alias=user_alias,
            )

    def test_list_activated_repositories_empty(self, activated_repo_manager):
        """Test listing activated repositories when none exist."""
        username = "testuser"

        result = activated_repo_manager.list_activated_repositories(username)

        assert result == []

    def test_list_activated_repositories_with_data(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test listing activated repositories with existing data."""
        username = "testuser"

        # Create user directory with activated repos
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        os.makedirs(user_dir, exist_ok=True)

        # Create two activated repos
        repo1_data = {
            "user_alias": "repo1",
            "golden_repo_alias": "golden1",
            "current_branch": "main",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        repo2_data = {
            "user_alias": "repo2",
            "golden_repo_alias": "golden2",
            "current_branch": "develop",
            "activated_at": "2024-01-02T12:00:00Z",
            "last_accessed": "2024-01-02T13:00:00Z",
        }

        # Write metadata files
        with open(os.path.join(user_dir, "repo1_metadata.json"), "w") as f:
            json.dump(repo1_data, f)

        with open(os.path.join(user_dir, "repo2_metadata.json"), "w") as f:
            json.dump(repo2_data, f)

        # Create corresponding directories
        os.makedirs(os.path.join(user_dir, "repo1"))
        os.makedirs(os.path.join(user_dir, "repo2"))

        # Test listing
        result = activated_repo_manager.list_activated_repositories(username)

        assert len(result) == 2
        assert any(repo["user_alias"] == "repo1" for repo in result)
        assert any(repo["user_alias"] == "repo2" for repo in result)

    def test_deactivate_repository_success(
        self, activated_repo_manager, temp_data_dir, background_job_manager_mock
    ):
        """Test successful repository deactivation."""
        username = "testuser"
        user_alias = "repo1"

        # Create user directory with activated repo
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        os.makedirs(user_dir, exist_ok=True)

        repo_data = {
            "user_alias": user_alias,
            "golden_repo_alias": "golden1",
            "current_branch": "main",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        # Write metadata file and create repo directory
        with open(os.path.join(user_dir, f"{user_alias}_metadata.json"), "w") as f:
            json.dump(repo_data, f)
        os.makedirs(os.path.join(user_dir, user_alias))

        # Test deactivation
        job_id = activated_repo_manager.deactivate_repository(username, user_alias)

        # Verify job was submitted
        assert job_id == "job-123"
        background_job_manager_mock.submit_job.assert_called_once()

    def test_deactivate_repository_not_found(self, activated_repo_manager):
        """Test deactivation fails when repository not found."""
        username = "testuser"
        user_alias = "nonexistent"

        with pytest.raises(
            ActivatedRepoError, match="Activated repository 'nonexistent' not found"
        ):
            activated_repo_manager.deactivate_repository(username, user_alias)

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_clone_with_copy_on_write_success_git_repo(
        self, mock_subprocess, mock_exists, activated_repo_manager
    ):
        """Test successful git clone for git repositories."""
        golden_path = "/path/to/golden/repo"
        activated_path = "/path/to/activated/repo"

        # Mock that source is a git repository
        mock_exists.return_value = True

        # Mock all subprocess calls to return success
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "origin\t/path/to/golden/repo\t(fetch)\n"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = activated_repo_manager._clone_with_copy_on_write(
            golden_path, activated_path
        )

        assert result is True

        # Verify CoW clone workflow (Issue #500 fix):
        # 1. cp --reflink=auto -r
        # 2. git update-index --refresh
        # 3. git restore .
        # 4. cidx fix-config --force
        # 5. git remote add origin
        # 6. git fetch origin
        # 7. git status (verification)
        expected_calls = [
            call(
                ["cp", "--reflink=auto", "-r", golden_path, activated_path],
                capture_output=True,
                text=True,
                timeout=120,
            ),
            call(
                ["git", "update-index", "--refresh"],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=60,
            ),
            call(
                ["git", "restore", "."],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=60,
            ),
            call(
                ["cidx", "fix-config", "--force"],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=60,
            ),
            call(
                ["git", "remote", "add", "origin", golden_path],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=30,
            ),
            call(
                ["git", "fetch", "origin"],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=60,
            ),
            call(
                ["git", "status"],
                cwd=activated_path,
                capture_output=True,
                text=True,
                timeout=30,
            ),
        ]

        mock_subprocess.assert_has_calls(expected_calls)

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_clone_with_copy_on_write_success_non_git_repo(
        self, mock_subprocess, mock_exists, activated_repo_manager
    ):
        """Test successful CoW clone for non-git directories."""
        golden_path = "/path/to/golden/repo"
        activated_path = "/path/to/activated/repo"

        # Mock that source is NOT a git repository
        mock_exists.return_value = False

        # Mock all subprocess calls to return success
        mock_subprocess.return_value.returncode = 0

        result = activated_repo_manager._clone_with_copy_on_write(
            golden_path, activated_path
        )

        assert result is True

        # Verify CoW clone is used for non-git directories (Issue #500 fix)
        # For non-git repos, only cp --reflink=auto is called (no git operations)
        expected_calls = [
            call(
                ["cp", "--reflink=auto", "-r", golden_path, activated_path],
                capture_output=True,
                text=True,
                timeout=120,
            ),
        ]

        mock_subprocess.assert_has_calls(expected_calls)

    @patch("subprocess.run")
    def test_clone_with_copy_on_write_failure_raises_exception(
        self, mock_subprocess, activated_repo_manager
    ):
        """Test that CoW failure raises ActivatedRepoError (no fallback)."""
        golden_path = "/path/to/golden/repo"
        activated_path = "/path/to/activated/repo"

        # Mock cp --reflink=always failing
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Copy-on-write not supported"

        # Should raise ActivatedRepoError instead of falling back
        with pytest.raises(ActivatedRepoError, match="CoW clone failed"):
            activated_repo_manager._clone_with_copy_on_write(
                golden_path, activated_path
            )

    @patch("subprocess.run")
    def test_switch_branch_success(
        self, mock_subprocess, activated_repo_manager, temp_data_dir
    ):
        """Test successful branch switching with our improved logic."""
        username = "testuser"
        user_alias = "repo1"
        new_branch = "feature-branch"

        # Create user directory with activated repo
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        repo_dir = os.path.join(user_dir, user_alias)
        os.makedirs(repo_dir, exist_ok=True)

        repo_data = {
            "user_alias": user_alias,
            "golden_repo_alias": "golden1",
            "current_branch": "main",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        with open(os.path.join(user_dir, f"{user_alias}_metadata.json"), "w") as f:
            json.dump(repo_data, f)

        # Mock git operations for our improved branch switching logic
        def mock_subprocess_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if cmd == ["git", "remote", "get-url", "origin"]:
                # Mock remote URL check - return a remote URL to trigger fetch attempt
                mock_result.returncode = 0
                mock_result.stdout = "https://github.com/test/repo.git"
                return mock_result
            elif cmd == ["git", "fetch", "origin"]:
                # Mock successful fetch
                mock_result.returncode = 0
                return mock_result
            elif cmd == ["git", "checkout", "-B", new_branch, f"origin/{new_branch}"]:
                # Mock successful remote branch checkout
                mock_result.returncode = 0
                return mock_result
            else:
                # Default success for other commands
                mock_result.returncode = 0
                return mock_result

        mock_subprocess.side_effect = mock_subprocess_side_effect

        result = activated_repo_manager.switch_branch(username, user_alias, new_branch)

        assert result["success"] is True
        assert new_branch in result["message"]

        # With our new logic, successful remote fetch should indicate remote sync
        assert "remote sync" in result["message"] or "local branch" in result["message"]

    @patch("subprocess.run")
    def test_switch_branch_git_operation_fails(
        self, mock_subprocess, activated_repo_manager, temp_data_dir
    ):
        """Test branch switching fails when branch doesn't exist in any form."""
        username = "testuser"
        user_alias = "repo1"
        new_branch = "nonexistent-branch"

        # Create user directory with activated repo
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        repo_dir = os.path.join(user_dir, user_alias)
        os.makedirs(repo_dir, exist_ok=True)

        repo_data = {
            "user_alias": user_alias,
            "golden_repo_alias": "golden1",
            "current_branch": "main",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        with open(os.path.join(user_dir, f"{user_alias}_metadata.json"), "w") as f:
            json.dump(repo_data, f)

        # Mock git operations that simulate branch not existing anywhere
        def mock_subprocess_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if cmd == ["git", "remote", "get-url", "origin"]:
                # Mock remote URL check
                mock_result.returncode = 0
                mock_result.stdout = "https://github.com/test/repo.git"
                return mock_result
            elif cmd == ["git", "fetch", "origin"]:
                # Mock successful fetch
                mock_result.returncode = 0
                return mock_result
            elif cmd == ["git", "checkout", "-B", new_branch, f"origin/{new_branch}"]:
                # Mock remote branch checkout failure (branch doesn't exist on remote)
                mock_result.returncode = 1
                mock_result.stderr = (
                    "error: pathspec 'nonexistent-branch' did not match"
                )
                return mock_result
            elif cmd == ["git", "checkout", new_branch]:
                # Mock local branch checkout failure (branch doesn't exist locally)
                mock_result.returncode = 1
                mock_result.stderr = (
                    "error: pathspec 'nonexistent-branch' did not match"
                )
                return mock_result
            elif cmd == [
                "git",
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/remotes/origin/{new_branch}",
            ]:
                # Mock: no origin branch exists locally
                mock_result.returncode = 1
                return mock_result
            elif cmd == ["git", "show-ref", new_branch]:
                # Mock: branch doesn't exist in any form
                mock_result.returncode = 1
                return mock_result
            else:
                # Default success for other commands
                mock_result.returncode = 0
                return mock_result

        mock_subprocess.side_effect = mock_subprocess_side_effect

        # Our improved error message is more specific
        with pytest.raises(GitOperationError, match="not found in repository"):
            activated_repo_manager.switch_branch(username, user_alias, new_branch)

    def test_branch_name_validation_valid_names(self, activated_repo_manager):
        """Test that valid branch names pass validation."""
        valid_names = [
            "main",
            "feature-branch",
            "feature/new-feature",
            "bugfix_123",
            "release-2.1.0",
            "hotfix/urgent-fix",
            "develop",
            "feature.with.dots",
        ]

        for branch_name in valid_names:
            # Should not raise any exception
            activated_repo_manager._validate_branch_name(branch_name)

    def test_branch_name_validation_invalid_names(self, activated_repo_manager):
        """Test that invalid branch names raise GitOperationError."""
        invalid_names = [
            "",  # empty string
            None,  # None value
            "branch with spaces",  # spaces not allowed
            "branch@symbol",  # @ not allowed
            "branch$money",  # $ not allowed
            "-starts-with-dash",  # cannot start with dash
            "ends.lock",  # cannot end with .lock
            "has..double.dots",  # cannot contain ..
            "branch;injection",  # semicolon not allowed
            "branch|pipe",  # pipe not allowed
        ]

        for branch_name in invalid_names:
            with pytest.raises(GitOperationError):
                activated_repo_manager._validate_branch_name(branch_name)

    def test_get_activated_repo_path(self, activated_repo_manager, temp_data_dir):
        """Test getting activated repository path."""
        username = "testuser"
        user_alias = "repo1"

        expected_path = os.path.join(
            temp_data_dir, "activated-repos", username, user_alias
        )
        actual_path = activated_repo_manager.get_activated_repo_path(
            username, user_alias
        )

        assert actual_path == expected_path

    def test_activated_repo_model_to_dict(self):
        """Test ActivatedRepo model to_dict method."""
        repo = ActivatedRepo(
            user_alias="test-repo",
            golden_repo_alias="golden-test",
            current_branch="main",
            activated_at="2024-01-01T12:00:00Z",
            last_accessed="2024-01-01T13:00:00Z",
        )

        result = repo.to_dict()

        expected = {
            "user_alias": "test-repo",
            "golden_repo_alias": "golden-test",
            "current_branch": "main",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        assert result == expected
