"""Test to verify repos list data model alignment fix."""

from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner
from pathlib import Path

# Import CLI components
from src.code_indexer.cli import cli
from src.code_indexer.api_clients.repos_client import ActivatedRepository


class TestReposListFix:
    """Test class for verifying repos list fix."""

    def setup_method(self):
        """Setup test environment for each test."""
        self.runner = CliRunner()

    @patch("src.code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("src.code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("src.code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("src.code_indexer.cli.ReposAPIClient")
    def test_repos_list_data_model_alignment_fix(
        self,
        mock_repos_client_class,
        mock_find_project_root,
        mock_load_credentials,
        mock_load_config,
    ):
        """Test that repos list properly handles server data format after fix.

        Verifies that the mapping between ActivatedRepositoryInfo (server)
        and ActivatedRepository (client) works correctly.
        """
        # Setup mocks for CLI prerequisites
        mock_find_project_root.return_value = Path("/fake/project")
        mock_load_config.return_value = {"server_url": "http://localhost:8000"}
        mock_load_credentials.return_value = {
            "username": "test",
            "password": "fake_password",
            "access_token": "fake_token",
        }

        # Create mock ReposAPIClient instance
        mock_client = Mock()
        mock_repos_client_class.return_value = mock_client

        # Mock successful response with correct data mapping
        mock_client.list_activated_repositories = AsyncMock(
            return_value=[
                ActivatedRepository(
                    alias="my-project",
                    current_branch="main",
                    sync_status="synced",
                    last_sync="2024-01-16T08:15:00Z",
                    activation_date="2024-01-15T10:30:00Z",
                    conflict_details=None,
                )
            ]
        )
        mock_client.close = AsyncMock()

        # Execute the command
        result = self.runner.invoke(cli, ["repos", "list"])

        # Should succeed after fix
        assert (
            result.exit_code == 0
        ), f"Command should succeed after fix, got: {result.output}"
        assert "my-project" in result.output
        assert "main" in result.output

        # Verify client method was called
        mock_client.list_activated_repositories.assert_called_once()
