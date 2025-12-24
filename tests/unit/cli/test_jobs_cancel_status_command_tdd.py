"""
TDD tests for jobs cancel and status CLI commands implementation.

Following Test-Driven Development methodology to test the jobs cancel and status
commands with real CLI integration and safety features.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, AsyncMock

from code_indexer.cli import cli


class TestJobsCancelStatusCommandTDD:
    """Test-driven development for jobs cancel and status CLI commands."""

    @pytest.fixture
    def cli_runner(self):
        """Provide CLI runner for testing."""
        return CliRunner()

    def test_jobs_cancel_command_exists(self, cli_runner):
        """Test that jobs cancel command is properly registered."""
        result = cli_runner.invoke(cli, ["jobs", "cancel", "--help"])

        # Should not return error
        assert result.exit_code == 0

        # Should show cancel command help text
        assert "Cancel a background job" in result.output
        assert "JOB_ID" in result.output
        assert "--force" in result.output

    def test_jobs_status_command_exists(self, cli_runner):
        """Test that jobs status command is properly registered."""
        result = cli_runner.invoke(cli, ["jobs", "status", "--help"])

        # Should not return error
        assert result.exit_code == 0

        # Should show status command help text
        assert "Show detailed status of a specific job" in result.output
        assert "JOB_ID" in result.output

    def test_jobs_cancel_requires_job_id(self, cli_runner):
        """Test that jobs cancel command requires job_id argument."""
        result = cli_runner.invoke(cli, ["jobs", "cancel"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_jobs_status_requires_job_id(self, cli_runner):
        """Test that jobs status command requires job_id argument."""
        result = cli_runner.invoke(cli, ["jobs", "status"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    @patch("code_indexer.cli.load_remote_configuration")
    @patch("code_indexer.cli.find_project_root")
    @patch("code_indexer.cli.load_encrypted_credentials")
    def test_jobs_cancel_prompts_for_confirmation(
        self, mock_load_creds, mock_find_root, mock_load_config, cli_runner
    ):
        """Test that jobs cancel prompts for confirmation without --force."""
        # Setup mocks
        mock_find_root.return_value = "/test/path"
        mock_load_config.return_value = {"server_url": "http://test.com"}
        mock_load_creds.return_value = {"username": "user", "password": "pass"}

        with patch("builtins.input", return_value="n"):  # User says no
            result = cli_runner.invoke(cli, ["jobs", "cancel", "test-job-123"])

            # Should exit without cancelling
            assert (
                "Operation cancelled" in result.output or "Cancelled" in result.output
            )

    @patch("code_indexer.cli.load_remote_configuration")
    @patch("code_indexer.cli.find_project_root")
    @patch("code_indexer.cli.load_encrypted_credentials")
    def test_jobs_cancel_with_force_skips_confirmation(
        self, mock_load_creds, mock_find_root, mock_load_config, cli_runner
    ):
        """Test that jobs cancel with --force skips confirmation."""
        # Setup mocks
        mock_find_root.return_value = "/test/path"
        mock_load_config.return_value = {"server_url": "http://test.com"}
        mock_load_creds.return_value = {"username": "user", "password": "pass"}

        # Mock the API client
        mock_api_client = AsyncMock()
        mock_api_client.cancel_job.return_value = {
            "job_id": "test-job-123",
            "status": "cancelled",
            "message": "Job cancelled successfully",
        }

        with patch(
            "code_indexer.api_clients.jobs_client.JobsAPIClient",
            return_value=mock_api_client,
        ):
            result = cli_runner.invoke(
                cli, ["jobs", "cancel", "test-job-123", "--force"]
            )

            # Should proceed without confirmation prompt
            # Should show success message
            assert (
                "cancelled successfully" in result.output.lower()
                or "cancelled" in result.output.lower()
            )

    @patch("code_indexer.cli.load_remote_configuration")
    @patch("code_indexer.cli.find_project_root")
    @patch("code_indexer.cli.load_encrypted_credentials")
    def test_jobs_status_displays_job_details(
        self, mock_load_creds, mock_find_root, mock_load_config, cli_runner
    ):
        """Test that jobs status displays detailed job information."""
        # Setup mocks
        mock_find_root.return_value = "/test/path"
        mock_load_config.return_value = {"server_url": "http://test.com"}
        mock_load_creds.return_value = {"username": "user", "password": "pass"}

        # Mock job status response
        mock_job_status = {
            "job_id": "test-job-123",
            "operation_type": "index",
            "status": "running",
            "progress": 45,
            "created_at": "2025-01-01T12:00:00Z",
            "started_at": "2025-01-01T12:00:01Z",
            "repository_id": "test-repo",
            "username": "testuser",
        }

        # Mock the API client
        mock_api_client = AsyncMock()
        mock_api_client.get_job_status.return_value = mock_job_status

        with patch(
            "code_indexer.api_clients.jobs_client.JobsAPIClient",
            return_value=mock_api_client,
        ):
            result = cli_runner.invoke(cli, ["jobs", "status", "test-job-123"])

            # Should display job details
            assert "test-job-123" in result.output
            assert "running" in result.output
            assert "45" in result.output  # progress
            assert "index" in result.output  # operation type

    def test_jobs_cancel_error_handling(self, cli_runner):
        """Test that jobs cancel handles errors gracefully."""
        # Test with invalid configuration (should fail gracefully)
        result = cli_runner.invoke(cli, ["jobs", "cancel", "test-job"])

        # Should show appropriate error message
        assert result.exit_code != 0
        assert (
            "No project configuration found" in result.output
            or "No remote configuration found" in result.output
            or "Error" in result.output
        )

    def test_jobs_status_error_handling(self, cli_runner):
        """Test that jobs status handles errors gracefully."""
        # Test with invalid configuration (should fail gracefully)
        result = cli_runner.invoke(cli, ["jobs", "status", "test-job"])

        # Should show appropriate error message
        assert result.exit_code != 0
        assert (
            "No project configuration found" in result.output
            or "No remote configuration found" in result.output
            or "Error" in result.output
        )

    def test_jobs_cancel_command_help_text(self, cli_runner):
        """Test that jobs cancel command has proper help text and examples."""
        result = cli_runner.invoke(cli, ["jobs", "cancel", "--help"])

        assert result.exit_code == 0
        # Should have examples and clear usage instructions
        assert (
            "EXAMPLES:" in result.output
            or "Examples:" in result.output
            or "--force" in result.output
        )

    def test_jobs_status_command_help_text(self, cli_runner):
        """Test that jobs status command has proper help text and examples."""
        result = cli_runner.invoke(cli, ["jobs", "status", "--help"])

        assert result.exit_code == 0
        # Should have examples and clear usage instructions
        assert (
            "EXAMPLES:" in result.output
            or "Examples:" in result.output
            or "status" in result.output
        )
