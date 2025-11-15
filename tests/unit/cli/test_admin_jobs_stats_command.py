"""Unit tests for admin jobs stats CLI command."""

from unittest.mock import patch, Mock
from click.testing import CliRunner
import os
import tempfile
from pathlib import Path

from src.code_indexer.cli import admin_jobs_group


class TestAdminJobsStatsCommand:
    """Tests for the admin jobs stats command."""

    def test_admin_jobs_stats_command_exists(self):
        """Test that the stats command exists under admin jobs."""
        # Check that 'stats' is registered as a command under admin_jobs_group
        assert (
            "stats" in admin_jobs_group.commands
        ), f"stats not found in commands: {list(admin_jobs_group.commands.keys())}"

    @patch("requests.get")
    def test_stats_basic_operation(self, mock_get):
        """Test basic stats operation without filters."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 100,
            "by_status": {
                "pending": 5,
                "queued": 3,
                "running": 2,
                "completed": 80,
                "failed": 8,
                "cancelled": 2,
            },
            "by_type": {
                "repository_sync": 50,
                "repository_activation": 30,
                "repository_deactivation": 20,
            },
            "success_rate": 90.9,
            "average_duration": 45.5,
        }
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create .code-indexer directory
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()

            # Create remote config
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')

            # Create credentials
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()

            # Change to project directory and run command
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0
        assert "Job Statistics" in result.output or "Total Jobs: 100" in result.output

        # Verify API call
        mock_get.assert_called_once_with(
            "http://test-server/api/admin/jobs/stats",
            params={},
            headers={"Authorization": "Bearer test-token"},
            timeout=30,
        )

    @patch("requests.get")
    def test_stats_handles_401_unauthorized(self, mock_get):
        """Test stats handles 401 unauthorized error."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()

            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')

            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "invalid-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    @patch("requests.get")
    def test_stats_handles_403_forbidden(self, mock_get):
        """Test stats handles 403 forbidden error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "non-admin-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Admin privileges required" in result.output

    @patch("requests.get")
    def test_stats_displays_by_status_table(self, mock_get):
        """Test that stats displays the by_status breakdown as a table."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 100,
            "by_status": {
                "pending": 5,
                "queued": 3,
                "running": 2,
                "completed": 80,
                "failed": 8,
                "cancelled": 2,
            },
            "by_type": {
                "repository_sync": 50,
                "repository_activation": 30,
                "repository_deactivation": 20,
            },
            "success_rate": 90.9,
            "average_duration": 45.5,
        }
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0

        # Check that all status types appear in output
        assert "Pending" in result.output or "pending" in result.output
        assert "Completed" in result.output or "completed" in result.output
        assert "Failed" in result.output or "failed" in result.output

        # Check that counts appear
        assert "80" in result.output  # completed count
        assert "8" in result.output  # failed count
        assert "5" in result.output  # pending count

    @patch("requests.get")
    def test_stats_displays_by_type_breakdown(self, mock_get):
        """Test that stats displays the by_type breakdown."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 100,
            "by_status": {"completed": 80, "failed": 20},
            "by_type": {
                "repository_sync": 50,
                "repository_activation": 30,
                "repository_deactivation": 20,
            },
            "success_rate": 80.0,
            "average_duration": 45.5,
        }
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0

        # Check that job types appear in output
        assert "sync" in result.output.lower() or "Repository Sync" in result.output
        assert (
            "activation" in result.output.lower()
            or "Repository Activation" in result.output
        )

        # Check that type counts appear
        assert "50" in result.output
        assert "30" in result.output
        assert "20" in result.output

    @patch("requests.get")
    def test_stats_displays_success_rate(self, mock_get):
        """Test that stats displays the success rate."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 100,
            "by_status": {"completed": 85, "failed": 15},
            "by_type": {"repository_sync": 100},
            "success_rate": 85.0,
            "average_duration": 42.3,
        }
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0

        # Check that success rate appears
        assert "success" in result.output.lower() or "Success Rate" in result.output
        assert "85" in result.output  # The success rate value

    @patch("requests.get")
    def test_stats_displays_average_duration(self, mock_get):
        """Test that stats displays the average duration."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 100,
            "by_status": {"completed": 100},
            "by_type": {"repository_sync": 100},
            "success_rate": 100.0,
            "average_duration": 42.7,
        }
        mock_get.return_value = mock_response

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            remote_config = config_dir / ".remote-config"
            remote_config.write_text('{"server_url": "http://test-server"}')
            credentials_file = config_dir / ".credentials"
            credentials_file.write_text('{"token": "test-token"}')

            runner = CliRunner()
            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_path))
                result = runner.invoke(admin_jobs_group, ["stats"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0

        # Check that average duration appears
        assert (
            "duration" in result.output.lower() or "Average Duration" in result.output
        )
        assert "42.7" in result.output  # The duration value
