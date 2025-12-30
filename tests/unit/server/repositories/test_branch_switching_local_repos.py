"""
Tests for branch switching with local repositories (no remote origins).

This test suite specifically addresses the issue where branch switching fails
for local repositories that don't have remote origins or don't need fetching.
The API should gracefully handle both local and remote repository scenarios.
"""

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepo,
    GoldenRepoManager,
)


@pytest.mark.e2e
class TestBranchSwitchingLocalRepos:
    """Test branch switching with local repositories without remote origins."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def local_git_repo_no_remote(self, temp_data_dir):
        """Create a local git repository without remote origins."""
        # Create repo INSIDE golden-repos/ to respect security sandbox
        golden_repos_dir = os.path.join(temp_data_dir, "golden-repos")
        os.makedirs(golden_repos_dir, exist_ok=True)
        repo_path = os.path.join(golden_repos_dir, "local_repo_no_remote")
        os.makedirs(repo_path)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create initial content on master branch
        with open(os.path.join(repo_path, "master_file.py"), "w") as f:
            f.write("print('Main branch content')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
        )

        # Create develop branch
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=repo_path, check=True)

        with open(os.path.join(repo_path, "develop_file.py"), "w") as f:
            f.write("print('Develop branch content')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add develop content"],
            cwd=repo_path,
            check=True,
        )

        # Switch back to master
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture
    def local_git_repo_with_invalid_remote(self, temp_data_dir):
        """Create a local git repository with invalid remote origin."""
        # Create repo INSIDE golden-repos/ to respect security sandbox
        golden_repos_dir = os.path.join(temp_data_dir, "golden-repos")
        os.makedirs(golden_repos_dir, exist_ok=True)
        repo_path = os.path.join(golden_repos_dir, "local_repo_invalid_remote")
        os.makedirs(repo_path)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create initial content
        with open(os.path.join(repo_path, "master_file.py"), "w") as f:
            f.write("print('Main branch content')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
        )

        # Add invalid remote origin that will fail on fetch
        subprocess.run(
            ["git", "remote", "add", "origin", "/nonexistent/path"],
            cwd=repo_path,
            check=True,
        )

        # Create feature branch locally
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo_path, check=True)

        with open(os.path.join(repo_path, "feature_file.py"), "w") as f:
            f.write("print('Feature branch content')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature content"],
            cwd=repo_path,
            check=True,
        )

        # Switch back to master
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture
    def golden_repo_manager_local(self, temp_data_dir, local_git_repo_no_remote):
        """Create golden repo manager with local repository."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add test repository as golden repo
        golden_repo = GoldenRepo(
            alias="local-test-repo",
            repo_url=local_git_repo_no_remote,
            default_branch="master",
            clone_path=local_git_repo_no_remote,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manager.golden_repos["local-test-repo"] = golden_repo

        return manager

    @pytest.fixture
    def golden_repo_manager_invalid_remote(
        self, temp_data_dir, local_git_repo_with_invalid_remote
    ):
        """Create golden repo manager with invalid remote repository."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add test repository as golden repo
        golden_repo = GoldenRepo(
            alias="invalid-remote-repo",
            repo_url=local_git_repo_with_invalid_remote,
            default_branch="master",
            clone_path=local_git_repo_with_invalid_remote,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manager.golden_repos["invalid-remote-repo"] = golden_repo

        return manager

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager for testing."""
        mock = MagicMock()
        mock.submit_job.return_value = "local-job-123"
        return mock

    @pytest.fixture
    def activated_repo_manager_local(
        self, temp_data_dir, golden_repo_manager_local, background_job_manager_mock
    ):
        """Create activated repo manager for local testing."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager_local,
            background_job_manager=background_job_manager_mock,
        )

    @pytest.fixture
    def activated_repo_manager_invalid_remote(
        self,
        temp_data_dir,
        golden_repo_manager_invalid_remote,
        background_job_manager_mock,
    ):
        """Create activated repo manager for invalid remote testing."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager_invalid_remote,
            background_job_manager=background_job_manager_mock,
        )

    def test_branch_switching_with_local_repo_now_works(
        self, activated_repo_manager_local, temp_data_dir
    ):
        """
        Test that verifies our fix: branch switching now works for local repos.

        This was previously a failing test that reproduced the issue described
        in the problem statement. After the fix, it should now work.
        """
        username = "local_user_fixed"
        user_alias = "local-project-fixed"
        golden_repo_alias = "local-test-repo"

        # Step 1: Activate repository
        result = activated_repo_manager_local._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Step 2: Branch switching should now work (this was previously failing)
        branch_result = activated_repo_manager_local.switch_branch(
            username, user_alias, "develop"
        )

        assert branch_result["success"] is True
        assert "develop" in branch_result["message"]

    def test_branch_switching_with_invalid_remote_now_works_with_fallback(
        self, activated_repo_manager_invalid_remote, temp_data_dir
    ):
        """
        Test that verifies our fix: branch switching with fallback for invalid remotes.

        This was previously a failing test that reproduced the API 404 error.
        After the fix, it should gracefully fall back to local branch switching.
        """
        username = "invalid_remote_user_fixed"
        user_alias = "invalid-remote-project-fixed"
        golden_repo_alias = "invalid-remote-repo"

        # Step 1: Activate repository
        result = activated_repo_manager_invalid_remote._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Step 2: Branch switching should now work with fallback (this was previously failing)
        branch_result = activated_repo_manager_invalid_remote.switch_branch(
            username, user_alias, "feature"
        )

        assert branch_result["success"] is True
        assert "feature" in branch_result["message"]

    def test_local_branch_switching_works_without_fetch(
        self, activated_repo_manager_local, temp_data_dir
    ):
        """
        Test that local branch switching works without requiring fetch operations.

        This test verifies the fix allows local repositories to switch branches
        even when they don't have accessible remote origins.
        """
        username = "local_user"
        user_alias = "local-project"
        golden_repo_alias = "local-test-repo"

        # Step 1: Activate repository
        result = activated_repo_manager_local._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Step 2: Branch switching should now work
        branch_result = activated_repo_manager_local.switch_branch(
            username, user_alias, "develop"
        )

        assert branch_result["success"] is True
        assert "develop" in branch_result["message"]
        assert "local branch" in branch_result["message"]

        # Step 3: Verify the branch switch actually worked
        activated_repo_path = os.path.join(
            temp_data_dir, "activated-repos", username, user_alias
        )

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "develop"

        # Step 4: Verify branch-specific content exists
        develop_file_path = os.path.join(activated_repo_path, "develop_file.py")
        assert os.path.exists(develop_file_path)

    def test_invalid_remote_branch_switching_fallback_gracefully(
        self, activated_repo_manager_invalid_remote, temp_data_dir
    ):
        """
        Test that branch switching gracefully falls back when fetch fails.

        This test verifies that repositories with invalid remote origins
        can still switch branches using local branches as fallback.
        """
        username = "invalid_remote_user"
        user_alias = "invalid-remote-project"
        golden_repo_alias = "invalid-remote-repo"

        # Step 1: Activate repository
        result = activated_repo_manager_invalid_remote._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Step 2: Branch switching should now work with graceful fallback
        branch_result = activated_repo_manager_invalid_remote.switch_branch(
            username, user_alias, "feature"
        )

        assert branch_result["success"] is True
        assert "feature" in branch_result["message"]
        # Should indicate fallback was used
        assert (
            "local branch" in branch_result["message"]
            or "remote fetch failed" in branch_result["message"]
        )

        # Step 3: Verify the branch switch actually worked
        activated_repo_path = os.path.join(
            temp_data_dir, "activated-repos", username, user_alias
        )

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "feature"

        # Step 4: Verify branch-specific content exists
        feature_file_path = os.path.join(activated_repo_path, "feature_file.py")
        assert os.path.exists(feature_file_path)

    def test_manual_git_checkout_works_in_activated_repo(
        self, activated_repo_manager_local, temp_data_dir
    ):
        """
        Verify that manual git checkout works in the activated repository.

        This confirms the underlying git structure is correct and the issue
        is specifically with the fetch operation in the API.
        """
        username = "manual_test_user"
        user_alias = "manual-project"
        golden_repo_alias = "local-test-repo"

        # Activate repository
        result = activated_repo_manager_local._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Get the activated repo path
        activated_repo_path = os.path.join(
            temp_data_dir, "activated-repos", username, user_alias
        )

        # Manual git checkout should work
        result = subprocess.run(
            ["git", "checkout", "develop"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify we're on develop branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "develop"

        # Verify develop-specific content exists
        develop_file_path = os.path.join(activated_repo_path, "develop_file.py")
        assert os.path.exists(develop_file_path)
