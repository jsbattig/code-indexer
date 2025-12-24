"""Unit tests for admin jobs cleanup CLI command implementation."""

from unittest.mock import patch, Mock
from click.testing import CliRunner
import os
import tempfile
from pathlib import Path

from src.code_indexer.cli import admin_jobs_group


class TestAdminJobsCleanupImplementation:
    """Tests for the implemented admin jobs cleanup command."""

    @patch("requests.delete")
    def test_cleanup_basic_operation(self, mock_delete):
        """Test basic cleanup operation without filters."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cleaned_count": 42,
            "message": "Cleaned up 42 old background jobs",
        }
        mock_delete.return_value = mock_response

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 0
        assert "Cleaned up 42 jobs" in result.output

        # Verify API call
        mock_delete.assert_called_once_with(
            "http://test-server/api/admin/jobs/cleanup",
            params={"max_age_hours": 720},  # 30 days * 24 hours
            headers={"Authorization": "Bearer test-token"},
            timeout=30,
        )

    @patch("requests.delete")
    def test_cleanup_handles_401_unauthorized(self, mock_delete):
        """Test cleanup handles 401 unauthorized error."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 401
        mock_delete.return_value = mock_response

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    @patch("requests.delete")
    def test_cleanup_handles_403_forbidden(self, mock_delete):
        """Test cleanup handles 403 forbidden error."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 403
        mock_delete.return_value = mock_response

        # Create temporary project directory with config
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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Admin privileges required" in result.output

    @patch("requests.delete")
    def test_cleanup_handles_network_error(self, mock_delete):
        """Test cleanup handles network connection errors."""
        import requests

        # Setup - simulate network error
        mock_delete.side_effect = requests.exceptions.RequestException(
            "Connection refused"
        )

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Network error" in result.output

    @patch("requests.delete")
    def test_cleanup_handles_timeout(self, mock_delete):
        """Test cleanup handles request timeout errors."""
        import requests

        # Setup - simulate timeout
        mock_delete.side_effect = requests.exceptions.Timeout("Request timed out")

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "timed out" in result.output.lower()

    @patch("requests.delete")
    def test_cleanup_handles_invalid_json_response(self, mock_delete):
        """Test cleanup handles invalid JSON response from server."""
        import json as json_module

        # Setup - response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json_module.JSONDecodeError(
            "Invalid JSON", "", 0
        )
        mock_delete.return_value = mock_response

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Invalid response" in result.output or "JSON" in result.output

    @patch("requests.delete")
    def test_cleanup_handles_500_server_error(self, mock_delete):
        """Test cleanup handles 500 internal server error."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 500
        mock_delete.return_value = mock_response

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
                result = runner.invoke(admin_jobs_group, ["cleanup"])
            finally:
                os.chdir(old_cwd)

        # Assert
        assert result.exit_code == 1
        assert "Server error" in result.output or "HTTP 500" in result.output
