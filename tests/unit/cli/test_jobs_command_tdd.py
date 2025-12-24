"""
TDD tests for jobs CLI command implementation.

Following Test-Driven Development methodology to test the jobs command group
and list functionality with real CLI integration.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from code_indexer.cli import cli


class TestJobsCommandTDD:
    """Test-driven development for jobs CLI commands."""

    @pytest.fixture
    def cli_runner(self):
        """Provide CLI runner for testing."""
        return CliRunner()

    def test_jobs_command_group_exists(self, cli_runner):
        """Test that jobs command group is properly registered."""
        result = cli_runner.invoke(cli, ["jobs", "--help"])

        # Should not return error
        assert result.exit_code == 0

        # Should show jobs help text
        assert "Manage background jobs and monitor their status" in result.output

    def test_jobs_list_command_exists(self, cli_runner):
        """Test that jobs list command is properly registered."""
        result = cli_runner.invoke(cli, ["jobs", "list", "--help"])

        # Should not return error
        assert result.exit_code == 0

        # Should show list command help text
        assert "List background jobs with their current status" in result.output
        assert "--status" in result.output
        assert "--limit" in result.output

    def test_jobs_list_command_options(self, cli_runner):
        """Test that jobs list command has proper options."""
        result = cli_runner.invoke(cli, ["jobs", "list", "--help"])

        # Check status filter options
        assert "running" in result.output
        assert "completed" in result.output
        assert "failed" in result.output
        assert "cancelled" in result.output

        # Check limit option
        assert "Maximum number of jobs to display" in result.output

    def test_jobs_list_requires_remote_mode(self, cli_runner):
        """Test that jobs list command requires remote mode."""
        import tempfile
        from unittest.mock import patch

        # Run test in isolated directory to avoid picking up project config
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("os.getcwd", return_value=temp_dir):
                result = cli_runner.invoke(cli, ["jobs", "list"])

                # Should exit with error when not in remote mode
                assert result.exit_code != 0
                # Should indicate mode restriction
                assert "'remote'" in result.output.lower()

    @patch("code_indexer.cli.find_project_root")
    @patch("code_indexer.cli.ProjectCredentialManager")
    def test_jobs_list_error_handling_no_config(
        self, mock_credential_manager, mock_find_root, cli_runner
    ):
        """Test jobs list error handling when no config found."""
        # Mock no project root found
        mock_find_root.return_value = None

        result = cli_runner.invoke(cli, ["jobs", "list"])

        # Should exit with error
        assert result.exit_code == 1
        assert "No project configuration found" in result.output

    @patch("code_indexer.cli.find_project_root")
    @patch("code_indexer.remote.config.load_remote_configuration")
    @patch("code_indexer.remote.credential_manager.load_encrypted_credentials")
    def test_jobs_list_error_handling_no_credentials(
        self,
        mock_load_encrypted_creds,
        mock_load_remote_config,
        mock_find_root,
        cli_runner,
    ):
        """Test jobs list error handling when no credentials found."""
        from pathlib import Path

        # Mock project root found and remote config loads successfully
        mock_find_root.return_value = Path("/test/project")
        mock_load_remote_config.return_value = {
            "username": "testuser",
            "server_url": "http://test.example.com",
        }

        # Mock credential loading to fail
        mock_load_encrypted_creds.side_effect = FileNotFoundError("No credentials file")

        result = cli_runner.invoke(cli, ["jobs", "list"])

        # Should exit with error
        assert result.exit_code == 1
        assert "Failed to load credentials" in result.output

    def test_jobs_list_status_filter_validation(self, cli_runner):
        """Test that status filter only accepts valid values."""
        # Test invalid status value
        result = cli_runner.invoke(cli, ["jobs", "list", "--status", "invalid"])

        # Should fail with invalid choice error
        assert result.exit_code != 0
        assert (
            "Invalid value" in result.output
            or "invalid choice" in result.output.lower()
        )

    def test_jobs_list_limit_parameter_validation(self, cli_runner):
        """Test that limit parameter accepts integer values."""
        # Test non-integer limit
        result = cli_runner.invoke(cli, ["jobs", "list", "--limit", "not-a-number"])

        # Should fail with invalid value error
        assert result.exit_code != 0
        assert (
            "Invalid value" in result.output
            or "not a valid integer" in result.output.lower()
        )

    def test_jobs_command_help_examples(self, cli_runner):
        """Test that jobs list help shows usage examples."""
        result = cli_runner.invoke(cli, ["jobs", "list", "--help"])

        assert result.exit_code == 0

        # Should show examples
        assert "EXAMPLES:" in result.output
        assert "cidx jobs list" in result.output
        assert "--status running" in result.output
        assert "--limit 20" in result.output

    def test_main_cli_help_shows_jobs_group(self, cli_runner):
        """Test that main CLI help shows jobs command group."""
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0

        # Should list jobs as available command
        assert "jobs" in result.output
