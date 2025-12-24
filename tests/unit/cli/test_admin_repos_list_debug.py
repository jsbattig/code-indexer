"""Debug test for admin repos list to identify the exact error."""

from unittest.mock import Mock, patch
from click.testing import CliRunner
from pathlib import Path

# Import CLI components
from src.code_indexer.cli import cli


class TestAdminReposListDebug:
    """Test class for debugging admin repos list issues."""

    def setup_method(self):
        """Setup test environment for each test."""
        self.runner = CliRunner()

    @patch("src.code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("src.code_indexer.remote.config.load_remote_configuration")
    @patch("src.code_indexer.remote.credential_manager.ProjectCredentialManager")
    @patch("src.code_indexer.remote.credential_manager.load_encrypted_credentials")
    @patch("src.code_indexer.cli.AdminAPIClient")
    @patch("src.code_indexer.cli.run_async")
    def test_admin_repos_list_debug_error(
        self,
        mock_run_async,
        mock_admin_client_class,
        mock_load_credentials,
        mock_credential_manager_class,
        mock_load_config,
        mock_find_project_root,
    ):
        """Debug test to see what the actual error is."""
        # Setup basic mocks
        mock_find_project_root.return_value = Path("/fake/project")
        mock_load_config.return_value = {"server_url": "http://localhost:8000"}

        # Create credential manager mock
        mock_credential_manager = Mock()
        mock_credential_manager_class.return_value = mock_credential_manager
        mock_load_credentials.return_value = {
            "username": "admin",
            "password": "admin_password",
            "access_token": "fake-admin-token",
        }

        # Mock AdminAPIClient
        mock_admin_client = Mock()
        mock_admin_client_class.return_value = mock_admin_client

        # Mock successful response
        mock_run_async.return_value = {
            "golden_repositories": [
                {
                    "alias": "test-repo",
                    "repo_url": "https://github.com/test/repo.git",
                    "last_refresh": "2024-01-16T10:00:00Z",
                    "status": "ready",
                }
            ],
            "total": 1,
        }

        # Execute command and capture any errors
        result = self.runner.invoke(cli, ["admin", "repos", "list"])

        # Print output for debugging
        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        print(f"Exception: {result.exception}")

        # If there's an exception, print the traceback
        if result.exception:
            import traceback

            print("Traceback:")
            traceback.print_exception(
                type(result.exception), result.exception, result.exception.__traceback__
            )

        # For now, let's see what happens
        # We'll determine success/failure criteria after seeing the actual error
