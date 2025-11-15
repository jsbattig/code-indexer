"""
Unit tests for the 'cidx admin repos refresh' command.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposRefreshCommand:
    """Unit tests for the admin repos refresh command."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_remote_project(self, tmp_path):
        """Create a mock project with remote configuration."""
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        code_indexer_dir = project_root / ".code-indexer"
        code_indexer_dir.mkdir()

        # Create remote config to enable remote mode
        remote_config = {"mode": "remote", "server_url": "https://test-server.com"}
        config_file = code_indexer_dir / "remote-config.json"
        config_file.write_text(json.dumps(remote_config))

        return project_root

    @patch("code_indexer.disabled_commands.detect_current_mode")
    def test_admin_repos_refresh_command_exists(self, mock_detect_mode, runner):
        """Test that the 'admin repos refresh' command exists."""
        # Mock to return remote mode directly
        mock_detect_mode.return_value = "remote"

        result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output
        assert "Refresh a golden repository" in result.output
