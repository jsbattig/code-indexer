"""Unit tests for repository activation lifecycle commands.

Testing repository activation and deactivation functionality
according to TDD methodology with red-green-refactor cycles.

Tests the CLI command structure for:
- cidx repos activate <golden-alias> [--as <user-alias>] [--branch <branch>]
- cidx repos deactivate <user-alias> [--force]
"""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, patch, AsyncMock

from code_indexer.cli import cli
from code_indexer.api_clients.repos_client import APIClientError


class TestRepositoryActivationCommand:
    """Test repository activation command functionality."""

    def test_activation_command_exists(self):
        """Test that the activate command exists in repos command group."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "activate", "--help"])

        # Should not get "No such command" error
        assert result.exit_code == 0
        assert "Activate a golden repository for personal use" in result.output

    def test_activation_requires_golden_alias_argument(self):
        """Test that activation command requires golden_alias argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "activate"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Error" in result.output

    def test_activation_accepts_optional_user_alias(self):
        """Test that activation command accepts optional --as user_alias."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "activate", "--help"])

        # Should show --as option in help
        assert result.exit_code == 0
        assert "--as" in result.output
        assert "user_alias" in result.output or "alias" in result.output

    def test_activation_accepts_optional_branch(self):
        """Test that activation command accepts optional --branch."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "activate", "--help"])

        # Should show --branch option in help
        assert result.exit_code == 0
        assert "--branch" in result.output

    @patch("code_indexer.cli.execute_repository_activation")
    def test_activation_calls_execution_function_with_correct_params(
        self, mock_execute
    ):
        """Test that activation command calls execution function with correct parameters."""
        runner = CliRunner()
        mock_execute.return_value = None  # Simulate successful execution

        runner.invoke(
            cli,
            [
                "repos",
                "activate",
                "my-golden-repo",
                "--as",
                "my-repo",
                "--branch",
                "main",
            ],
        )

        # Should call execute function with correct parameters
        mock_execute.assert_called_once_with(
            golden_alias="my-golden-repo", user_alias="my-repo", target_branch="main"
        )

    @patch("code_indexer.cli.execute_repository_activation")
    def test_activation_defaults_user_alias_to_golden_alias(self, mock_execute):
        """Test that activation uses golden_alias as user_alias when not specified."""
        runner = CliRunner()
        mock_execute.return_value = None

        runner.invoke(cli, ["repos", "activate", "web-service"])

        # Should call execute function with golden_alias as user_alias
        mock_execute.assert_called_once_with(
            golden_alias="web-service", user_alias="web-service", target_branch=None
        )

    @patch("code_indexer.cli.execute_repository_activation")
    def test_activation_handles_execution_errors(self, mock_execute):
        """Test that activation command handles execution errors gracefully."""
        runner = CliRunner()
        mock_execute.side_effect = APIClientError("Repository not found")

        result = runner.invoke(cli, ["repos", "activate", "nonexistent-repo"])

        # Should handle error and provide user-friendly message
        assert result.exit_code != 0
        assert "Error" in result.output or "Failed" in result.output


class TestRepositoryDeactivationCommand:
    """Test repository deactivation command functionality."""

    def test_deactivation_command_exists(self):
        """Test that the deactivate command exists in repos command group."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "deactivate", "--help"])

        # Should not get "No such command" error
        assert result.exit_code == 0
        assert "Deactivate a personal repository" in result.output

    def test_deactivation_requires_user_alias_argument(self):
        """Test that deactivation command requires user_alias argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "deactivate"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Error" in result.output

    def test_deactivation_accepts_force_flag(self):
        """Test that deactivation command accepts --force flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "deactivate", "--help"])

        # Should show --force option in help
        assert result.exit_code == 0
        assert "--force" in result.output

    def test_deactivation_shows_confirmation_prompt(self):
        """Test that deactivation shows confirmation prompt by default."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "deactivate", "--help"])

        # Should mention confirmation in help text
        assert result.exit_code == 0
        assert "confirm" in result.output.lower() or "remove" in result.output.lower()

    @patch("code_indexer.cli.execute_repository_deactivation")
    def test_deactivation_calls_execution_function_with_correct_params(
        self, mock_execute
    ):
        """Test that deactivation command calls execution function with correct parameters."""
        runner = CliRunner()
        mock_execute.return_value = None

        # Auto-confirm with 'y' input
        runner.invoke(cli, ["repos", "deactivate", "my-repo", "--force"], input="y\n")

        # Should call execute function with correct parameters
        mock_execute.assert_called_once_with(
            user_alias="my-repo", force=True, confirmed=True
        )

    @patch("code_indexer.cli.execute_repository_deactivation")
    def test_deactivation_handles_execution_errors(self, mock_execute):
        """Test that deactivation command handles execution errors gracefully."""
        runner = CliRunner()
        mock_execute.side_effect = APIClientError("Repository not found")

        result = runner.invoke(
            cli, ["repos", "deactivate", "nonexistent-repo"], input="y\n"
        )

        # Should handle error and provide user-friendly message
        assert result.exit_code != 0
        assert "Error" in result.output or "Failed" in result.output

    @patch("code_indexer.cli.execute_repository_deactivation")
    def test_deactivation_aborts_on_no_confirmation(self, mock_execute):
        """Test that deactivation aborts when user declines confirmation."""
        runner = CliRunner()

        result = runner.invoke(cli, ["repos", "deactivate", "my-repo"], input="n\n")

        # Should abort without calling execute function
        mock_execute.assert_not_called()
        assert result.exit_code != 0


class TestRepositoryActivationExecution:
    """Test repository activation execution logic."""

    @pytest.fixture
    def mock_repos_client(self):
        """Mock ReposAPIClient for testing."""
        client = Mock()
        client.activate_repository = AsyncMock()
        return client

    @pytest.fixture
    def mock_progress_display(self):
        """Mock ActivationProgressDisplay for testing."""
        display = Mock()
        display.show_activation_progress = Mock()
        display.show_activation_complete = Mock()
        return display

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    @patch("code_indexer.cli.ActivationProgressDisplay")
    def test_execute_repository_activation_success(
        self, mock_display_class, mock_client_class, mock_load_creds, mock_find_root
    ):
        """Test successful repository activation execution."""
        # Setup path mocks
        from pathlib import Path

        mock_find_root.return_value = Path("/test/project")

        # Setup credential mocks
        mock_load_creds.return_value = {
            "server_url": "https://test-server.com",
            "username": "test",
            "password": "test",
        }

        # Setup client mocks
        mock_client = Mock()
        mock_client.activate_repository = AsyncMock(
            return_value={
                "status": "completed",
                "user_alias": "my-repo",
                "message": "Repository activated successfully",
            }
        )
        mock_client_class.return_value = mock_client

        # Setup display mocks
        mock_display = Mock()
        mock_display_class.return_value = mock_display

        # Import and test the function (which should exist)
        from code_indexer.cli import execute_repository_activation

        # Should not raise any exceptions
        execute_repository_activation(
            golden_alias="web-service", user_alias="my-repo", target_branch="main"
        )

        # Should call client activation method
        mock_client.activate_repository.assert_called_once()

        # Should show progress and completion
        mock_display.show_activation_progress.assert_called_once()
        mock_display.show_activation_complete.assert_called_once()

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    @patch("code_indexer.cli.ActivationProgressDisplay")
    def test_execute_repository_activation_api_error(
        self, mock_display_class, mock_client_class, mock_load_creds, mock_find_root
    ):
        """Test repository activation execution with API error."""
        # Setup path mocks
        from pathlib import Path

        mock_find_root.return_value = Path("/test/project")

        # Setup credential mocks
        mock_load_creds.return_value = {
            "server_url": "https://test-server.com",
            "username": "test",
            "password": "test",
        }

        # Setup client mock to raise API error
        mock_client = Mock()
        mock_client.activate_repository = AsyncMock(
            side_effect=APIClientError("Repository not found")
        )
        mock_client_class.return_value = mock_client

        # Setup display mocks
        mock_display = Mock()
        mock_display_class.return_value = mock_display

        from code_indexer.cli import execute_repository_activation

        # Should raise or handle the API error appropriately
        with pytest.raises(APIClientError):
            execute_repository_activation(
                golden_alias="nonexistent", user_alias="my-repo", target_branch=None
            )


class TestRepositoryDeactivationExecution:
    """Test repository deactivation execution logic."""

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_execute_repository_deactivation_success(
        self, mock_client_class, mock_load_creds, mock_find_root
    ):
        """Test successful repository deactivation execution."""
        # Setup path mocks
        from pathlib import Path

        mock_find_root.return_value = Path("/test/project")

        # Setup credential mocks
        mock_load_creds.return_value = {
            "server_url": "https://test-server.com",
            "username": "test",
            "password": "test",
        }

        # Setup client mock
        mock_client = Mock()
        mock_client.deactivate_repository = AsyncMock(
            return_value={
                "status": "completed",
                "message": "Repository deactivated successfully",
            }
        )
        mock_client_class.return_value = mock_client

        from code_indexer.cli import execute_repository_deactivation

        # Should not raise any exceptions
        execute_repository_deactivation(
            user_alias="my-repo", force=False, confirmed=True
        )

        # Should call client deactivation method
        mock_client.deactivate_repository.assert_called_once_with(
            user_alias="my-repo", force=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_execute_repository_deactivation_api_error(
        self, mock_client_class, mock_load_creds, mock_find_root
    ):
        """Test repository deactivation execution with API error."""
        # Setup path mocks
        from pathlib import Path

        mock_find_root.return_value = Path("/test/project")

        # Setup credential mocks
        mock_load_creds.return_value = {
            "server_url": "https://test-server.com",
            "username": "test",
            "password": "test",
        }

        # Setup mock to raise API error
        mock_client = Mock()
        mock_client.deactivate_repository = AsyncMock(
            side_effect=APIClientError("Repository not found")
        )
        mock_client_class.return_value = mock_client

        from code_indexer.cli import execute_repository_deactivation

        # Should raise or handle the API error appropriately
        with pytest.raises(APIClientError):
            execute_repository_deactivation(
                user_alias="nonexistent", force=False, confirmed=True
            )


class TestActivationProgressDisplay:
    """Test activation progress display functionality."""

    def test_activation_progress_display_class_exists(self):
        """Test that ActivationProgressDisplay class exists."""
        from code_indexer.cli import ActivationProgressDisplay

        # Should be able to instantiate
        display = ActivationProgressDisplay()
        assert display is not None

    def test_activation_progress_display_methods_exist(self):
        """Test that required progress display methods exist."""
        from code_indexer.cli import ActivationProgressDisplay

        display = ActivationProgressDisplay()

        # Should have required methods
        assert hasattr(display, "show_activation_progress")
        assert hasattr(display, "show_activation_complete")
        assert callable(display.show_activation_progress)
        assert callable(display.show_activation_complete)

    def test_show_activation_progress_accepts_required_parameters(self):
        """Test that show_activation_progress accepts required parameters."""
        from code_indexer.cli import ActivationProgressDisplay

        display = ActivationProgressDisplay()

        # Should accept parameters without error
        try:
            display.show_activation_progress(
                golden_alias="web-service", user_alias="my-repo"
            )
        except TypeError as e:
            pytest.fail(
                f"show_activation_progress should accept required parameters: {e}"
            )

    def test_show_activation_complete_accepts_required_parameters(self):
        """Test that show_activation_complete accepts required parameters."""
        from code_indexer.cli import ActivationProgressDisplay

        display = ActivationProgressDisplay()

        # Should accept parameters without error
        try:
            display.show_activation_complete(
                user_alias="my-repo",
                next_steps=["Use cidx query to search the repository"],
            )
        except TypeError as e:
            pytest.fail(
                f"show_activation_complete should accept required parameters: {e}"
            )
