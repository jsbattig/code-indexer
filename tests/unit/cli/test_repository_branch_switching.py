"""TDD tests for repository branch switching command implementation.

Tests the `cidx repos switch-branch` command with branch switching operations,
local/remote branch handling, and container configuration updates.
Following TDD methodology: Red -> Green -> Refactor
"""

from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner
from pathlib import Path

from code_indexer.cli import cli
from code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestRepositoryBranchSwitching:
    """TDD tests for cidx repos switch-branch command implementation."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.runner = CliRunner()
        self.mock_project_root = Path("/test/project")
        self.mock_credentials = {"username": "test_user", "token": "test_token"}
        self.mock_remote_config = {"server_url": "https://cidx.example.com"}

    def test_repos_switch_branch_command_exists(self):
        """Test that repos switch-branch command exists and is accessible."""
        # RED: This test should fail initially since command doesn't exist
        result = self.runner.invoke(cli, ["repos", "switch-branch", "--help"])

        # Should show help for the switch-branch command
        assert result.exit_code == 0
        assert "Switch branch in activated repository" in result.output

    def test_repos_switch_branch_requires_arguments(self):
        """Test that repos switch-branch command requires user alias and branch name arguments."""
        # RED: This test should fail initially
        result = self.runner.invoke(cli, ["repos", "switch-branch"])

        # Should require user alias and branch name arguments
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_repos_switch_branch_requires_branch_name(self):
        """Test that repos switch-branch command requires branch name argument."""
        # RED: This test should fail initially
        result = self.runner.invoke(cli, ["repos", "switch-branch", "my-project"])

        # Should require branch name argument
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_successful_local_branch(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test successful branch switching to existing local branch."""
        # RED: This test should fail initially since functionality doesn't exist

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock successful branch switch response
        mock_switch_result = {
            "status": "success",
            "previous_branch": "main",
            "new_branch": "develop",
            "message": "Switched to branch 'develop' in repository 'my-project'",
            "container_updated": True,
            "uncommitted_changes_preserved": False,
        }

        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            return_value=mock_switch_result
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should succeed and display success message
        assert result.exit_code == 0
        assert (
            "Switched to branch 'develop' in repository 'my-project'" in result.output
        )
        assert "✅" in result.output  # Success indicator

        # Verify API client was called correctly
        mock_client.switch_repository_branch.assert_called_once_with(
            user_alias="my-project", branch_name="develop", create=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_with_create_flag(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching with --create flag for new branches."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock successful branch creation and switch
        mock_switch_result = {
            "status": "success",
            "previous_branch": "main",
            "new_branch": "feature/new-feature",
            "message": "Created and switched to new branch 'feature/new-feature'",
            "branch_created": True,
            "container_updated": True,
        }

        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            return_value=mock_switch_result
        )
        mock_client_class.return_value = mock_client

        # Execute command with --create flag
        result = self.runner.invoke(
            cli,
            ["repos", "switch-branch", "my-project", "feature/new-feature", "--create"],
        )

        # Should succeed and display creation message
        assert result.exit_code == 0
        assert (
            "Created and switched to new branch 'feature/new-feature'" in result.output
        )
        assert "✅" in result.output  # Success indicator

        # Verify API client was called with create=True
        mock_client.switch_repository_branch.assert_called_once_with(
            user_alias="my-project", branch_name="feature/new-feature", create=True
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_remote_tracking_branch(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test switching to a branch that exists remotely but not locally."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock remote branch tracking response
        mock_switch_result = {
            "status": "success",
            "previous_branch": "main",
            "new_branch": "origin/feature/remote-feature",
            "message": "Created local tracking branch for 'origin/feature/remote-feature'",
            "tracking_branch_created": True,
            "remote_origin": "origin/feature/remote-feature",
        }

        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            return_value=mock_switch_result
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "feature/remote-feature"]
        )

        # Should succeed and display tracking branch message
        assert result.exit_code == 0
        assert "Created local tracking branch" in result.output
        assert "feature/remote-feature" in result.output

        # Verify API client was called correctly
        mock_client.switch_repository_branch.assert_called_once_with(
            user_alias="my-project", branch_name="feature/remote-feature", create=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_with_uncommitted_changes(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching when there are uncommitted changes."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock response with uncommitted changes preserved
        mock_switch_result = {
            "status": "success",
            "previous_branch": "main",
            "new_branch": "develop",
            "message": "Switched to branch 'develop' with uncommitted changes preserved",
            "uncommitted_changes_preserved": True,
            "preserved_files": ["src/main.py", "tests/test_feature.py"],
        }

        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            return_value=mock_switch_result
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should succeed and show preservation message
        assert result.exit_code == 0
        assert "uncommitted changes preserved" in result.output
        assert "src/main.py" in result.output
        assert "tests/test_feature.py" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_handles_branch_not_found(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching handles branch not found error."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock branch not found error
        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            side_effect=APIClientError("Branch 'nonexistent' not found", 404)
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "nonexistent"]
        )

        # Should handle error gracefully
        assert result.exit_code != 0
        assert (
            "Branch 'nonexistent' not found" in result.output
            or "not found" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_handles_repository_not_found(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching handles repository not found error."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock repository not found error
        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            side_effect=APIClientError("Repository 'nonexistent' not found", 404)
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "nonexistent", "main"]
        )

        # Should handle error gracefully
        assert result.exit_code != 0
        assert (
            "Repository 'nonexistent' not found" in result.output
            or "not found" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_handles_merge_conflicts(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching handles merge conflicts."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock merge conflict error
        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            side_effect=APIClientError(
                "Cannot switch branches due to merge conflicts. Please resolve conflicts first.",
                409,
            )
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should handle merge conflict error
        assert result.exit_code != 0
        assert "merge conflicts" in result.output or "conflicts" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_handles_authentication_errors(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test branch switching handles authentication errors."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock authentication error
        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            side_effect=AuthenticationError("Invalid credentials")
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should handle authentication error
        assert result.exit_code != 0
        assert (
            "Authentication failed" in result.output
            or "Invalid credentials" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    def test_repos_switch_branch_requires_project_root(self, mock_find_root):
        """Test that repos switch-branch requires being in a CIDX project directory."""
        # Mock no project root found
        mock_find_root.return_value = None

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should fail with project directory error
        assert result.exit_code != 0
        assert "Not in a CIDX project directory" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    def test_repos_switch_branch_requires_remote_configuration(
        self, mock_load_config, mock_find_root
    ):
        """Test that repos switch-branch requires remote configuration."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.side_effect = Exception("No remote configuration found")

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should fail with configuration error
        assert result.exit_code != 0
        assert (
            "Failed to load credentials" in result.output
            or "No remote configuration" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_switch_branch_container_update_notification(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test that branch switching shows container update notifications."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock response with container configuration update
        mock_switch_result = {
            "status": "success",
            "previous_branch": "main",
            "new_branch": "develop",
            "message": "Switched to branch 'develop' in repository 'my-project'",
            "container_updated": True,
            "container_restart_required": True,
        }

        mock_client = Mock()
        mock_client.switch_repository_branch = AsyncMock(
            return_value=mock_switch_result
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(
            cli, ["repos", "switch-branch", "my-project", "develop"]
        )

        # Should succeed and show container update information
        assert result.exit_code == 0
        assert (
            "Container configuration updated" in result.output
            or "container" in result.output
        )
