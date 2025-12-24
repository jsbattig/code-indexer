"""
Integration tests for the 'cidx admin repos branches' command.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposBranchesIntegration:
    """Integration tests for admin repos branches command."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_project_setup(self, tmp_path):
        """Create a complete mock project setup."""
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
        config_file = code_indexer_dir / "remote-config.json"
        config_file.write_text(json.dumps(remote_config))

        # Create mock encrypted credentials
        creds_file = code_indexer_dir / ".credentials.enc"
        creds_file.write_bytes(b"fake_encrypted_data")

        return project_root

    @patch("code_indexer.disabled_commands.detect_current_mode")
    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.config.load_remote_configuration")
    def test_branches_command_handles_no_config(
        self,
        mock_load_config,
        mock_find_root,
        mock_detect_mode,
        runner,
        mock_project_setup,
    ):
        """Test that branches command handles missing configuration."""
        mock_detect_mode.return_value = "remote"
        mock_find_root.return_value = mock_project_setup
        mock_load_config.return_value = None

        result = runner.invoke(cli, ["admin", "repos", "branches", "test-repo"])

        assert result.exit_code != 0
        assert "No remote configuration found" in result.output
