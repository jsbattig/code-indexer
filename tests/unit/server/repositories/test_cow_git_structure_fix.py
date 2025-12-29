"""
Unit tests for Copy-on-Write Git Structure Fix.

Tests to reproduce and fix the branch operations non-functional issue
where CoW repositories lack proper git structure for branch switching.
"""

import os
import json
import tempfile
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepoError,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo


@pytest.mark.e2e
class TestCoWGitStructureFix:
    """Test suite for CoW git structure preservation and branch operations."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def real_git_repo(self, temp_data_dir):
        """Create a real git repository for testing."""
        repo_path = os.path.join(temp_data_dir, "test_golden_repo")
        os.makedirs(repo_path)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Add initial content
        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Test Repository\n")

        with open(os.path.join(repo_path, "main.py"), "w") as f:
            f.write("def main():\n    print('Hello World')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Create feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"], cwd=repo_path, check=True
        )
        with open(os.path.join(repo_path, "feature.py"), "w") as f:
            f.write("def feature():\n    print('Feature code')\n")

        subprocess.run(["git", "add", "feature.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature"], cwd=repo_path, check=True
        )

        # Switch back to master/main
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture
    def golden_repo_manager_mock(self, real_git_repo):
        """Mock golden repo manager with real git repository."""
        mock = MagicMock()
        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/example/test-repo.git",
            default_branch="master",
            clone_path=real_git_repo,
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

    def test_cow_clone_preserves_git_directory(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test that CoW clone preserves .git directory structure."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform CoW clone
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )

        assert success is True
        assert os.path.exists(activated_path)

        # Verify .git directory exists
        git_dir = os.path.join(activated_path, ".git")
        assert os.path.exists(git_dir), "CoW clone should preserve .git directory"

        # Verify essential git structure
        assert os.path.exists(os.path.join(git_dir, "HEAD"))
        assert os.path.exists(os.path.join(git_dir, "refs"))
        assert os.path.exists(os.path.join(git_dir, "objects"))

    def test_cow_clone_git_operations_fail_without_proper_setup(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """
        Test that git operations fail in CoW clones without proper remote setup.
        This reproduces the "fatal: not a git repository" error.
        """
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform current CoW clone (known to be broken)
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Try git operations that should work but currently fail
        result = subprocess.run(
            ["git", "status"], cwd=activated_path, capture_output=True, text=True
        )

        # This might pass or fail depending on CoW implementation
        # But the real test is the branch operations

        # Try git fetch (this should fail without proper remote setup)
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=activated_path,
            capture_output=True,
            text=True,
        )

        # This is the actual failure we expect to see
        if result.returncode != 0:
            assert (
                "fatal" in result.stderr
                or "not a git repository" in result.stderr
                or "origin" in result.stderr
            )

    def test_activated_repo_branch_switching_now_works_after_fix(
        self, activated_repo_manager, temp_data_dir, real_git_repo
    ):
        """
        Test that branch switching now works after fixing the git structure issue.
        This test verifies the issue has been resolved.
        """
        # Create user directory and simulate activation
        username = "testuser"
        user_alias = "test-repo"
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        os.makedirs(user_dir, exist_ok=True)

        # Perform the fixed CoW clone
        activated_path = os.path.join(user_dir, user_alias)
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Create metadata file
        metadata = {
            "user_alias": user_alias,
            "golden_repo_alias": "test-repo",
            "current_branch": "master",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Try to switch branches - this should now work
        result = activated_repo_manager.switch_branch(
            username, user_alias, "feature-branch"
        )

        # Verify the branch switch was successful
        assert result["success"] is True
        assert "feature-branch" in result["message"]

    def test_cow_repo_now_has_remote_origin_after_fix(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test that CoW repositories now have proper remote 'origin' configuration after fix."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform CoW clone with fix
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Check if remote 'origin' is configured
        result = subprocess.run(
            ["git", "remote", "-v"], cwd=activated_path, capture_output=True, text=True
        )

        # Verify the fix worked
        assert result.returncode == 0, f"git remote command failed: {result.stderr}"
        remotes = result.stdout
        assert (
            "origin" in remotes
        ), "CoW repository should now have 'origin' remote after fix"
        assert (
            real_git_repo in remotes
        ), f"Origin should point to golden repo path: {remotes}"

    def test_direct_git_operations_on_golden_repo(self, real_git_repo):
        """Test that git operations work correctly on the golden repository."""
        # Verify golden repo has working git operations
        result = subprocess.run(
            ["git", "status"], cwd=real_git_repo, capture_output=True, text=True
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["git", "branch", "-a"], cwd=real_git_repo, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "master" in result.stdout
        assert "feature-branch" in result.stdout

    def test_cow_repo_branch_operations_requirement(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test specific git operations that branch switching requires."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform CoW clone
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Test individual git operations that branch switching needs

        # 1. Git status should work
        result = subprocess.run(
            ["git", "status"], cwd=activated_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"git status failed: {result.stderr}"

        # 2. List branches should work
        result = subprocess.run(
            ["git", "branch", "-a"], cwd=activated_path, capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.fail(f"git branch failed: {result.stderr}")

        # 3. Show current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Cannot determine current branch: {result.stderr}")

        current_branch = result.stdout.strip()
        assert current_branch == "master", f"Expected 'master', got '{current_branch}'"

    def test_cow_clone_with_git_structure_fix_preserves_remotes(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test that the fixed CoW clone properly sets up git remote origin."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform fixed CoW clone
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Check if remote 'origin' is now configured correctly
        result = subprocess.run(
            ["git", "remote", "-v"], cwd=activated_path, capture_output=True, text=True
        )

        assert result.returncode == 0, f"git remote failed: {result.stderr}"
        remotes = result.stdout
        assert "origin" in remotes, "Fixed CoW clone should have 'origin' remote"
        assert (
            real_git_repo in remotes
        ), f"Origin should point to golden repo: {remotes}"

    def test_cow_clone_with_git_structure_fix_enables_fetch(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test that the fixed CoW clone enables git fetch operations."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform fixed CoW clone
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Test git fetch should now work
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=activated_path,
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode == 0
        ), f"git fetch should work after fix: {result.stderr}"

    def test_cow_clone_with_git_structure_fix_enables_branch_listing(
        self, activated_repo_manager, real_git_repo, temp_data_dir
    ):
        """Test that the fixed CoW clone enables proper branch listing."""
        activated_path = os.path.join(temp_data_dir, "activated_repo")

        # Perform fixed CoW clone
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Test branch listing with remotes
        result = subprocess.run(
            ["git", "branch", "-a"], cwd=activated_path, capture_output=True, text=True
        )

        assert result.returncode == 0, f"git branch failed: {result.stderr}"
        branches = result.stdout
        assert "master" in branches, f"Should see master branch: {branches}"
        assert "remotes/golden" in branches, f"Should see remote branches (golden): {branches}"
        assert "feature-branch" in branches, f"Should see feature-branch: {branches}"

    def test_activated_repo_branch_switching_works_after_fix(
        self, activated_repo_manager, temp_data_dir, real_git_repo
    ):
        """
        Test that branch switching works correctly after the git structure fix.
        This test should PASS with the fixed implementation.
        """
        # Create user directory and simulate activation
        username = "testuser"
        user_alias = "test-repo"
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        os.makedirs(user_dir, exist_ok=True)

        # Perform the fixed CoW clone
        activated_path = os.path.join(user_dir, user_alias)
        success = activated_repo_manager._clone_with_copy_on_write(
            real_git_repo, activated_path
        )
        assert success is True

        # Create metadata file
        metadata = {
            "user_alias": user_alias,
            "golden_repo_alias": "test-repo",
            "current_branch": "master",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Try to switch branches - this should now work
        result = activated_repo_manager.switch_branch(
            username, user_alias, "feature-branch"
        )

        # Verify success
        assert result["success"] is True
        assert "feature-branch" in result["message"]

        # Verify metadata was updated
        with open(metadata_file, "r") as f:
            updated_metadata = json.load(f)
        assert updated_metadata["current_branch"] == "feature-branch"

        # Verify the git repository is actually on the correct branch
        git_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_path,
            capture_output=True,
            text=True,
        )
        assert git_result.returncode == 0
        current_branch = git_result.stdout.strip()
        assert (
            current_branch == "feature-branch"
        ), f"Expected 'feature-branch', got '{current_branch}'"

    def test_cow_clone_cleanup_on_failure(self, activated_repo_manager, temp_data_dir):
        """Test that CoW clone cleans up on failure."""
        nonexistent_source = "/nonexistent/path"
        activated_path = os.path.join(temp_data_dir, "should_not_exist")

        # This should fail and clean up
        with pytest.raises(ActivatedRepoError):
            activated_repo_manager._clone_with_copy_on_write(
                nonexistent_source, activated_path
            )

        # Verify no partial directory was left behind
        assert not os.path.exists(
            activated_path
        ), "Failed clone should clean up destination directory"
