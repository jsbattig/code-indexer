"""Unit tests for admin jobs CLI commands."""

from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from src.code_indexer.cli import cli


class TestAdminJobsCleanupCommand:
    """Tests for the admin jobs cleanup command."""

    def test_admin_jobs_cleanup_requires_remote_mode(self):
        """Test that admin jobs cleanup requires remote mode."""
        runner = CliRunner()

        # Run without --remote flag
        result = runner.invoke(cli, ["admin", "jobs", "cleanup"])

        assert result.exit_code != 0
        # The admin group itself requires remote mode
        assert (
            "requires: 'remote' mode" in result.output.lower()
            or "requires remote mode" in result.output.lower()
        )

    def test_admin_jobs_cleanup_command_exists(self):
        """Test that the cleanup command exists under admin jobs."""
        # We can't actually invoke it without remote mode, but we can test
        # that when we try to invoke it, we get the mode error not "no such command"
        runner = CliRunner()

        # Try to invoke cleanup - should fail with mode error, not command missing
        result = runner.invoke(cli, ["admin", "jobs", "cleanup"])

        # The error should be about remote mode, not about missing command
        # If command doesn't exist, we'd see "No such command 'cleanup'"
        assert "no such command 'cleanup'" not in result.output.lower()

    def test_admin_jobs_has_cleanup_subcommand(self):
        """Test that cleanup subcommand is registered under admin jobs."""
        # Import the admin_jobs_group directly to check its commands
        from src.code_indexer.cli import admin_jobs_group

        # Get the commands registered under admin_jobs_group
        commands = admin_jobs_group.commands

        # Check that 'cleanup' is one of the registered commands
        assert (
            "cleanup" in commands
        ), f"cleanup not found in commands: {list(commands.keys())}"

    def test_admin_jobs_cleanup_has_options(self):
        """Test that cleanup command has the required options."""
        from src.code_indexer.cli import admin_jobs_group

        cleanup_cmd = admin_jobs_group.commands["cleanup"]

        # Get option names
        option_names = [param.name for param in cleanup_cmd.params]

        # Check required options exist
        assert (
            "older_than" in option_names
        ), f"older_than option not found. Available: {option_names}"
        assert (
            "status" in option_names
        ), f"status option not found. Available: {option_names}"
        assert (
            "dry_run" in option_names
        ), f"dry_run option not found. Available: {option_names}"

    @patch("requests.delete")
    def test_cleanup_status_parameter_sent_to_api(self, mock_delete):
        """Test that --status parameter is sent to the API."""
        import tempfile
        import os
        from pathlib import Path
        from src.code_indexer.cli import admin_jobs_group

        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cleaned_count": 5,
            "message": "Cleaned up 5 jobs",
        }
        mock_delete.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()

            # Create remote config
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')

            # Create credentials
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(
                    admin_jobs_group, ["cleanup", "--status", "failed"]
                )
            finally:
                os.chdir(old_cwd)

        # Verify the command executed
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify requests.delete was called with status parameter
        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args.kwargs

        assert "params" in call_kwargs, f"params not passed. Call kwargs: {call_kwargs}"
        params = call_kwargs["params"]
        assert "status" in params, f"status parameter not sent. Params: {params}"
        assert params["status"] == "failed", f"status value incorrect. Params: {params}"

    @patch("requests.delete")
    def test_cleanup_dry_run_parameter_sent_to_api(self, mock_delete):
        """Test that --dry-run parameter is sent to the API."""
        import tempfile
        import os
        from pathlib import Path
        from src.code_indexer.cli import admin_jobs_group

        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cleaned_count": 10,
            "message": "Would clean up 10 jobs",
        }
        mock_delete.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()

            # Create remote config
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')

            # Create credentials
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["cleanup", "--dry-run"])
            finally:
                os.chdir(old_cwd)

        # Verify the command executed
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify requests.delete was called with dry_run parameter
        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args.kwargs

        assert "params" in call_kwargs, f"params not passed. Call kwargs: {call_kwargs}"
        params = call_kwargs["params"]
        assert "dry_run" in params, f"dry_run parameter not sent. Params: {params}"
        assert params["dry_run"] == "true", f"dry_run value incorrect. Params: {params}"
