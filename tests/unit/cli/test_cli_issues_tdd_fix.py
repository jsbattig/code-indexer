"""TDD Tests for Fixing Critical CLI Issues.

Reproduces and fixes identified CLI command failures:
1. repos list - Pydantic validation error with RepositoryInfo model mismatch
2. admin repos list - ProjectCredentialManager type error in path operations
3. API client resource cleanup warnings

Following TDD methodology: Red-Green-Refactor cycles.
"""

from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner
from pathlib import Path
import sys

# Import CLI components
from src.code_indexer.cli import cli
from src.code_indexer.api_clients.repos_client import ActivatedRepository
from src.code_indexer.api_clients.base_client import APIClientError


class TestCLIIssuesFix:
    """Test class for reproducing and fixing critical CLI issues."""

    def setup_method(self):
        """Setup test environment for each test."""
        self.runner = CliRunner()
        # Ensure clean state for each test
        if sys.modules.get("code_indexer.cli"):
            # Force reload to ensure clean state
            import importlib

            importlib.reload(sys.modules["code_indexer.cli"])

    @patch("src.code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("src.code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("src.code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("src.code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_list_pydantic_validation_error_reproduction(
        self,
        mock_repos_client_class,
        mock_find_project_root,
        mock_load_credentials,
        mock_load_config,
    ):
        """Test that reproduces Pydantic validation error in repos list command.

        ISSUE: Server returns ActivatedRepositoryInfo but client expects ActivatedRepository.
        The field structures don't match, causing 17 validation errors.
        """
        # Setup mocks for CLI prerequisites
        mock_find_project_root.return_value = Path("/fake/project")
        mock_load_config.return_value = {"server_url": "http://localhost:8000"}
        mock_load_credentials.return_value = {
            "username": "test",
            "access_token": "fake",
        }

        # Create mock ReposAPIClient instance
        mock_client = Mock()
        mock_repos_client_class.return_value = mock_client

        # ISSUE: Mock server response that has different structure than expected
        # Server returns ActivatedRepositoryInfo with fields: user_alias, golden_repo_alias, current_branch, activated_at, last_accessed
        # But client expects ActivatedRepository with fields: alias, current_branch, sync_status, last_sync, activation_date, conflict_details
        mock_server_response_data = {
            "repositories": [
                {
                    "user_alias": "my-project",  # CLIENT EXPECTS: alias
                    "golden_repo_alias": "upstream-project",
                    "current_branch": "main",
                    "activated_at": "2024-01-15T10:30:00Z",  # CLIENT EXPECTS: activation_date
                    "last_accessed": "2024-01-16T08:15:00Z",  # CLIENT EXPECTS: last_sync
                    # MISSING FIELDS CLIENT EXPECTS: sync_status, conflict_details
                }
            ],
            "total": 1,
        }

        # Mock the client method to simulate server response parsing failure
        def simulate_pydantic_error(*args, **kwargs):
            # This simulates the Pydantic ValidationError that occurs when trying to parse
            # server response into ActivatedRepository objects
            try:
                repositories_data = mock_server_response_data["repositories"]
                # This will fail because field names and required fields don't match
                return [
                    ActivatedRepository(**repo_data) for repo_data in repositories_data
                ]
            except Exception as e:
                # Convert to the actual error pattern we see in production
                raise APIClientError(f"Invalid response format: {e}")

        mock_client.list_activated_repositories = AsyncMock(
            side_effect=simulate_pydantic_error
        )

        # Execute the command and expect it to fail with Pydantic validation error
        result = self.runner.invoke(cli, ["repos", "list"])

        # Test should FAIL with current code - reproducing the issue
        assert (
            result.exit_code != 0
        ), "Command should fail with Pydantic validation error"
        assert (
            "Invalid response format" in result.output
            or "validation error" in result.output.lower()
        )

        # Verify the client method was called
        mock_client.list_activated_repositories.assert_called_once()

    @patch("src.code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("src.code_indexer.remote.config.load_remote_configuration")
    @patch("src.code_indexer.remote.credential_manager.ProjectCredentialManager")
    @patch("src.code_indexer.remote.credential_manager.load_encrypted_credentials")
    @patch("src.code_indexer.api_clients.admin_client.AdminAPIClient")
    @patch("src.code_indexer.utils.async_helper.run_async")
    def test_admin_repos_list_credential_manager_type_error_reproduction(
        self,
        mock_run_async,
        mock_admin_client_class,
        mock_load_credentials,
        mock_credential_manager_class,
        mock_load_config,
        mock_find_project_root,
    ):
        """Test that reproduces ProjectCredentialManager type error in admin repos list.

        ISSUE: ProjectCredentialManager object being used in path operation where string expected.
        Error: "unsupported operand type(s) for /: 'ProjectCredentialManager' and 'str'"
        """
        # Setup basic mocks
        mock_find_project_root.return_value = Path("/fake/project")
        mock_load_config.return_value = {"server_url": "http://localhost:8000"}

        # ISSUE: Create scenario where ProjectCredentialManager object is incorrectly used
        mock_credential_manager = Mock()
        mock_credential_manager_class.return_value = mock_credential_manager
        mock_load_credentials.return_value = {
            "username": "admin",
            "access_token": "fake-admin-token",
        }

        # Mock AdminAPIClient
        mock_admin_client = Mock()
        mock_admin_client_class.return_value = mock_admin_client

        # Simulate the type error - this happens when credential_manager object
        # is used in a path operation instead of a string path
        def simulate_type_error(*args, **kwargs):
            # Simulate the error that occurs when ProjectCredentialManager object
            # is used with / operator (path division) instead of proper string path
            credential_manager = mock_credential_manager  # This is the object
            try:
                # This line would cause the type error in real code
                _ = credential_manager / "some_path"  # TypeError!
                return {"golden_repositories": [], "total": 0}
            except TypeError as e:
                if "unsupported operand type" in str(
                    e
                ) and "ProjectCredentialManager" in str(e):
                    raise e
                return {"golden_repositories": [], "total": 0}

        mock_run_async.side_effect = simulate_type_error

        # Execute the command and expect it to fail with TypeError
        result = self.runner.invoke(cli, ["admin", "repos", "list"])

        # Test should FAIL with current code - reproducing the issue
        assert (
            result.exit_code != 0
        ), "Command should fail with ProjectCredentialManager type error"
        assert (
            "TypeError" in result.output or "unsupported operand type" in result.output
        )

        # Verify the credential manager was instantiated
        mock_credential_manager_class.assert_called_once()

    @patch("src.code_indexer.cli.CommandModeDetector")
    @patch("src.code_indexer.cli.find_project_root")
    @patch("src.code_indexer.cli._load_remote_configuration")
    @patch("src.code_indexer.cli._load_and_decrypt_credentials")
    def test_api_client_resource_cleanup_warnings_reproduction(
        self,
        mock_load_credentials,
        mock_load_config,
        mock_find_project_root,
        mock_detector,
    ):
        """Test that reproduces API client resource cleanup warnings.

        ISSUE: "CIDXRemoteAPIClient was not properly closed" warnings appear
        after successful CLI operations due to missing async context management.
        """
        # Setup mocks for CLI prerequisites
        mock_find_project_root.return_value = Path("/fake/project")
        mock_load_config.return_value = {"server_url": "http://localhost:8000"}
        mock_load_credentials.return_value = {
            "username": "test",
            "access_token": "fake",
        }
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Capture warnings to detect resource cleanup issues
        import warnings

        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")

            # Create a real client instance to test resource management
            # This will help us detect actual resource cleanup warnings
            with patch(
                "src.code_indexer.api_clients.repos_client.ReposAPIClient"
            ) as mock_client_class:
                mock_client = Mock()

                # Simulate a client that has resources that need cleanup
                async def mock_list_repos(*args, **kwargs):
                    return []

                mock_client.list_activated_repositories = AsyncMock(return_value=[])
                mock_client.close = AsyncMock()  # Client should have close method
                mock_client_class.return_value = mock_client

                # Execute command
                result = self.runner.invoke(cli, ["repos", "list"])

                # The command might succeed but we expect resource warnings
                # Check if close() was called for proper cleanup
                if result.exit_code == 0:
                    # If command succeeded, check for missing cleanup
                    mock_client.close.assert_not_called()  # This indicates the problem

                # Check for resource-related warnings in captured warnings
                resource_warnings = [
                    w
                    for w in warning_list
                    if "not properly closed" in str(w.message)
                    or "ResourceWarning" in str(type(w.message))
                ]

                # Test should detect resource cleanup issues
                # Either warnings are captured OR close() method not called
                cleanup_issue_detected = (
                    len(resource_warnings) > 0 or not mock_client.close.called
                )

                assert (
                    cleanup_issue_detected
                ), "Should detect API client resource cleanup issues"

    def test_integration_repos_list_should_work_after_fix(self):
        """Integration test that should pass after fixing repos list Pydantic issues.

        This test will initially FAIL but should PASS after implementing the fix.
        Tests end-to-end data model alignment between server and client.
        """
        # This test is designed to pass after the fix is implemented
        # It will initially fail, serving as our "green" target for TDD

        with (
            patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "src.code_indexer.remote.sync_execution._load_remote_configuration"
            ) as mock_config,
            patch(
                "src.code_indexer.remote.sync_execution._load_and_decrypt_credentials"
            ) as mock_creds,
            patch(
                "src.code_indexer.api_clients.repos_client.ReposAPIClient"
            ) as mock_client_class,
        ):

            # Setup mocks
            mock_find_root.return_value = Path("/fake/project")
            mock_config.return_value = {"server_url": "http://localhost:8000"}
            mock_creds.return_value = {"username": "test", "access_token": "fake"}

            # Mock client with CORRECTED response format after fix
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # After fix: Server should return properly formatted ActivatedRepository objects
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

            # Execute command
            result = self.runner.invoke(cli, ["repos", "list"])

            # After fix: Command should succeed
            assert (
                result.exit_code == 0
            ), f"Command should succeed after fix, got: {result.output}"
            assert "my-project" in result.output
            assert "main" in result.output
            assert "✓" in result.output or "synced" in result.output

    def test_integration_admin_repos_list_should_work_after_fix(self):
        """Integration test that should pass after fixing admin repos list issues.

        This test will initially FAIL but should PASS after implementing the fix.
        Tests proper credential manager usage without type errors.
        """
        with (
            patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "src.code_indexer.remote.config.load_remote_configuration"
            ) as mock_config,
            patch(
                "src.code_indexer.remote.credential_manager.ProjectCredentialManager"
            ) as mock_cred_mgr,
            patch(
                "src.code_indexer.remote.credential_manager.load_encrypted_credentials"
            ) as mock_creds,
            patch(
                "src.code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_admin_class,
            patch("src.code_indexer.utils.async_helper.run_async") as mock_run_async,
        ):

            # Setup mocks
            mock_find_root.return_value = Path("/fake/project")
            mock_config.return_value = {"server_url": "http://localhost:8000"}
            mock_creds.return_value = {
                "username": "admin",
                "access_token": "fake-admin-token",
            }

            # After fix: Credential manager should be used correctly (no type errors)
            mock_credential_manager = Mock()
            mock_cred_mgr.return_value = mock_credential_manager

            mock_admin_client = Mock()
            mock_admin_class.return_value = mock_admin_client

            # After fix: No type errors, proper response
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

            # Execute command
            result = self.runner.invoke(cli, ["admin", "repos", "list"])

            # After fix: Command should succeed
            assert (
                result.exit_code == 0
            ), f"Admin repos list should succeed after fix, got: {result.output}"
            assert "test-repo" in result.output
            assert "Ready" in result.output or "ready" in result.output
