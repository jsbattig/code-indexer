"""
Unit tests for 'cidx admin repos branches' command implementation.

These tests verify the branches command:
- Fetches branch data from the API
- Displays branches in a Rich table
- Handles error cases (404, 403, network errors)
"""

import json
from unittest.mock import patch
import pytest
from click.testing import CliRunner
from code_indexer.cli import cli


class TestAdminReposBranchesCommand:
    """Unit tests for the admin repos branches command."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_remote_project(self, tmp_path):
        """Create a mock project with remote configuration and credentials."""
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        code_indexer_dir = project_root / ".code-indexer"
        code_indexer_dir.mkdir()

        # Create remote config
        remote_config = {
            "mode": "remote",
            "server_url": "https://test-server.com",
            "username": "testuser",
        }
        config_file = code_indexer_dir / ".remote-config"
        config_file.write_text(json.dumps(remote_config))

        # Create credentials file
        creds = {"username": "testuser", "token": "test-token-123"}
        creds_file = code_indexer_dir / ".credentials"
        creds_file.write_text(json.dumps(creds))

        return project_root

    @patch("code_indexer.disabled_commands.detect_current_mode")
    def test_branches_command_exists(self, mock_detect_mode, runner):
        """Test that the 'admin repos branches' command exists."""
        mock_detect_mode.return_value = "remote"

        result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert result.exit_code == 0
        assert "branches" in result.output
        assert "List branches in a golden repository" in result.output
