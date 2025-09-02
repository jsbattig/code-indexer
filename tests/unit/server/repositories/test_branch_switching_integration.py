"""
Integration tests for branch switching workflow with fixed CoW repositories.

Tests the complete branch switching flow including:
- Repository activation with proper git structure
- Branch listing and switching operations
- Verification of git state consistency
- Integration between activated repo manager and golden repo manager
"""

import json
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


class TestBranchSwitchingIntegration:
    """Integration tests for branch switching workflow."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def test_git_repo(self, temp_data_dir):
        """Create a real git repository for integration testing."""
        repo_path = os.path.join(temp_data_dir, "integration_test_repo")
        os.makedirs(repo_path)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Integration Test"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@integration.com"],
            cwd=repo_path,
            check=True,
        )

        # Create initial content on master
        with open(os.path.join(repo_path, "app.py"), "w") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "def main():\n"
                '    print("Master branch version")\n'
                "\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )

        with open(os.path.join(repo_path, "config.yaml"), "w") as f:
            f.write("version: '1.0'\nenv: production\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit on master"],
            cwd=repo_path,
            check=True,
        )

        # Create develop branch with different content
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=repo_path, check=True)

        with open(os.path.join(repo_path, "app.py"), "w") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "def main():\n"
                '    print("Develop branch version - new features!")\n'
                '    print("Additional functionality here")\n'
                "\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )

        with open(os.path.join(repo_path, "dev_config.yaml"), "w") as f:
            f.write("version: '1.1'\nenv: development\ndebug: true\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add develop branch features"],
            cwd=repo_path,
            check=True,
        )

        # Create feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/user-auth"], cwd=repo_path, check=True
        )

        with open(os.path.join(repo_path, "auth.py"), "w") as f:
            f.write(
                "def authenticate(username, password):\n"
                '    """User authentication logic."""\n'
                "    # Placeholder for authentication\n"
                "    return username == 'admin' and password == 'secret'\n"
            )

        subprocess.run(["git", "add", "auth.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add user authentication feature"],
            cwd=repo_path,
            check=True,
        )

        # Switch back to master as default
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir, test_git_repo):
        """Create golden repo manager with test repository."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add test repository as golden repo
        golden_repo = GoldenRepo(
            alias="test-integration-repo",
            repo_url=test_git_repo,
            default_branch="master",
            clone_path=test_git_repo,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manager.golden_repos["test-integration-repo"] = golden_repo

        return manager

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager for testing."""
        mock = MagicMock()
        mock.submit_job.return_value = "integration-job-123"
        return mock

    @pytest.fixture
    def activated_repo_manager(
        self, temp_data_dir, golden_repo_manager, background_job_manager_mock
    ):
        """Create activated repo manager for integration testing."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager,
            background_job_manager=background_job_manager_mock,
        )

    def test_complete_repository_activation_and_branch_switching_workflow(
        self, activated_repo_manager, temp_data_dir, test_git_repo
    ):
        """
        Test the complete workflow from repository activation to branch switching.

        This integration test verifies:
        1. Repository activation with proper CoW and git setup
        2. Branch switching to different branches
        3. File content verification across branches
        4. Git state consistency throughout the workflow
        """
        username = "integration_user"
        user_alias = "my-project"
        golden_repo_alias = "test-integration-repo"

        # Step 1: Perform repository activation (simulate the background job)
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True
        assert user_alias in result["message"]

        # Verify activated repository structure
        user_dir = os.path.join(temp_data_dir, "activated-repos", username)
        activated_repo_path = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        assert os.path.exists(activated_repo_path)
        assert os.path.exists(metadata_file)

        # Step 2: Verify initial git state and content
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "master"

        # Verify master branch content
        app_py_path = os.path.join(activated_repo_path, "app.py")
        assert os.path.exists(app_py_path)
        with open(app_py_path, "r") as f:
            content = f.read()
        assert "Master branch version" in content
        assert "Additional functionality here" not in content

        # Step 3: Switch to develop branch
        branch_result = activated_repo_manager.switch_branch(
            username, user_alias, "develop"
        )

        assert branch_result["success"] is True
        assert "develop" in branch_result["message"]

        # Verify branch switch in git
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "develop"

        # Verify develop branch content
        with open(app_py_path, "r") as f:
            content = f.read()
        assert "Develop branch version - new features!" in content
        assert "Additional functionality here" in content

        # Verify develop-specific files exist
        dev_config_path = os.path.join(activated_repo_path, "dev_config.yaml")
        assert os.path.exists(dev_config_path)

        # Verify metadata was updated
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
        assert metadata["current_branch"] == "develop"

        # Step 4: Switch to feature branch
        branch_result = activated_repo_manager.switch_branch(
            username, user_alias, "feature/user-auth"
        )

        assert branch_result["success"] is True
        assert "feature/user-auth" in branch_result["message"]

        # Verify feature branch state
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "feature/user-auth"

        # Verify feature-specific files exist
        auth_py_path = os.path.join(activated_repo_path, "auth.py")
        assert os.path.exists(auth_py_path)
        with open(auth_py_path, "r") as f:
            content = f.read()
        assert "authenticate" in content
        assert "User authentication logic" in content

        # Step 5: Switch back to master and verify state
        branch_result = activated_repo_manager.switch_branch(
            username, user_alias, "master"
        )

        assert branch_result["success"] is True
        assert "master" in branch_result["message"]

        # Verify we're back to master state
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "master"

        # Verify master content is restored
        with open(app_py_path, "r") as f:
            content = f.read()
        assert "Master branch version" in content
        assert "Additional functionality here" not in content

        # Verify feature files don't exist on master
        assert not os.path.exists(auth_py_path)
        assert not os.path.exists(dev_config_path)

    def test_branch_switching_with_nonexistent_branch_fails_gracefully(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that switching to a nonexistent branch fails gracefully."""
        username = "test_user"
        user_alias = "test-project"
        golden_repo_alias = "test-integration-repo"

        # Activate repository
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Try to switch to nonexistent branch
        from src.code_indexer.server.repositories.activated_repo_manager import (
            GitOperationError,
        )

        with pytest.raises(GitOperationError) as exc_info:
            activated_repo_manager.switch_branch(
                username, user_alias, "nonexistent-branch"
            )

        error_message = str(exc_info.value)
        # With our improved error handling, the error message is more specific
        assert "not found" in error_message and "nonexistent-branch" in error_message

    def test_git_remote_configuration_in_activated_repository(
        self, activated_repo_manager, temp_data_dir, test_git_repo
    ):
        """Test that activated repositories have proper git remote configuration."""
        username = "remote_test_user"
        user_alias = "remote-test-project"
        golden_repo_alias = "test-integration-repo"

        # Activate repository
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Check remote configuration
        activated_repo_path = os.path.join(
            temp_data_dir, "activated-repos", username, user_alias
        )

        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        remotes = result.stdout
        assert "origin" in remotes
        assert test_git_repo in remotes

        # Test that fetch operations work
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_multiple_users_branch_switching_isolation(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that multiple users can switch branches independently."""
        golden_repo_alias = "test-integration-repo"

        # User 1 activates and switches to develop
        user1 = "user1"
        activated_repo_manager._do_activate_repository(
            username=user1,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias="project1",
        )

        activated_repo_manager.switch_branch(user1, "project1", "develop")

        # User 2 activates and switches to feature branch
        user2 = "user2"
        activated_repo_manager._do_activate_repository(
            username=user2,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias="project2",
        )

        activated_repo_manager.switch_branch(user2, "project2", "feature/user-auth")

        # Verify both users have independent branch states
        user1_path = os.path.join(temp_data_dir, "activated-repos", user1, "project1")
        user2_path = os.path.join(temp_data_dir, "activated-repos", user2, "project2")

        # Check user1 is on develop
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=user1_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "develop"

        # Check user2 is on feature branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=user2_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "feature/user-auth"

        # Verify content isolation
        user1_app = os.path.join(user1_path, "app.py")
        user2_app = os.path.join(user2_path, "app.py")
        user2_auth = os.path.join(user2_path, "auth.py")

        with open(user1_app, "r") as f:
            user1_content = f.read()

        with open(user2_app, "r") as f:
            user2_content = f.read()

        # User1 should have develop branch content
        assert "Develop branch version - new features!" in user1_content

        # User2 should have feature branch content (based on develop)
        assert "Develop branch version - new features!" in user2_content
        assert os.path.exists(user2_auth)  # Feature-specific file

        # User1 should not have feature-specific files
        assert not os.path.exists(os.path.join(user1_path, "auth.py"))
