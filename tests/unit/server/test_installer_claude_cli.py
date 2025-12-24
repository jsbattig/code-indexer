"""
Unit tests for Claude CLI installation in ServerInstaller.

Tests the automatic Claude CLI installation feature that ensures
Claude CLI is available without manual npm commands.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from code_indexer.server.installer import ServerInstaller


class TestIsClaudeCliInstalled:
    """Tests for _is_claude_cli_installed method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_claude_installed(self, installer):
        """Test returns True when claude --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_claude_cli_installed()

        assert result is True
        mock_run.assert_called_once_with(
            ["claude", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_claude_not_found(self, installer):
        """Test returns False when claude command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_claude_cli_installed()

        assert result is False

    def test_returns_false_when_claude_returns_nonzero(self, installer):
        """Test returns False when claude returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_claude_cli_installed()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 10)
        ):
            result = installer._is_claude_cli_installed()

        assert result is False


class TestIsNpmAvailable:
    """Tests for _is_npm_available method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_npm_installed(self, installer):
        """Test returns True when npm --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_npm_available()

        assert result is True
        mock_run.assert_called_once_with(
            ["npm", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_npm_not_found(self, installer):
        """Test returns False when npm command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_npm_available()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when npm times out."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npm", 10)):
            result = installer._is_npm_available()

        assert result is False

    def test_returns_false_when_npm_returns_nonzero(self, installer):
        """Test returns False when npm returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 127

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_npm_available()

        assert result is False


class TestInstallClaudeCli:
    """Tests for install_claude_cli method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_skips_installation_when_already_installed(self, installer):
        """Test skips npm install when Claude CLI already present."""
        with patch.object(
            installer, "_is_claude_cli_installed", return_value=True
        ) as mock_check:
            with patch.object(installer, "_is_npm_available") as mock_npm:
                result = installer.install_claude_cli()

        assert result is True
        mock_check.assert_called_once()
        mock_npm.assert_not_called()  # Should not check npm if already installed

    def test_skips_installation_when_npm_not_available(self, installer):
        """Test skips installation and logs warning when npm not found."""
        with patch.object(installer, "_is_claude_cli_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=False):
                result = installer.install_claude_cli()

        assert result is False

    def test_installs_via_npm_when_not_installed(self, installer):
        """Test runs npm install when Claude CLI not present."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        # First check returns False (not installed), after install returns True
        install_check_results = [False, True]

        with patch.object(
            installer, "_is_claude_cli_installed", side_effect=install_check_results
        ):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch("subprocess.run", return_value=mock_npm_result) as mock_run:
                    result = installer.install_claude_cli()

        assert result is True
        mock_run.assert_called_once_with(
            ["npm", "install", "-g", "@anthropic-ai/claude-code"],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_returns_false_when_npm_install_fails(self, installer):
        """Test returns False when npm install returns non-zero."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 1
        mock_npm_result.stderr = "npm ERR! code EACCES"

        with patch.object(installer, "_is_claude_cli_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch("subprocess.run", return_value=mock_npm_result):
                    result = installer.install_claude_cli()

        assert result is False

    def test_returns_false_when_verification_fails(self, installer):
        """Test returns False when post-install verification fails."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        # Both checks return False (verification fails)
        with patch.object(installer, "_is_claude_cli_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch("subprocess.run", return_value=mock_npm_result):
                    result = installer.install_claude_cli()

        assert result is False

    def test_handles_npm_timeout(self, installer):
        """Test returns False when npm install times out."""
        with patch.object(installer, "_is_claude_cli_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("npm", 120),
                ):
                    result = installer.install_claude_cli()

        assert result is False

    def test_handles_generic_exception(self, installer):
        """Test returns False when npm install raises unexpected exception."""
        with patch.object(installer, "_is_claude_cli_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=RuntimeError("unexpected error"),
                ):
                    result = installer.install_claude_cli()

        assert result is False


class TestInstallMethodIntegration:
    """Tests for install() method integration with Claude CLI installation."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with mocked dependencies."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            inst.home_dir = tmp_path
            inst.base_port = 8090
            inst.config_manager = Mock()
            inst.jwt_manager = Mock()
            return inst

    def test_install_calls_install_claude_cli(self, installer):
        """Test that install() method calls install_claude_cli()."""
        # Setup mocks for all install() dependencies
        installer.config_manager.create_server_directories = Mock()
        installer.config_manager.create_default_config = Mock(
            return_value=Mock(port=8090)
        )
        installer.config_manager.apply_env_overrides = Mock(
            return_value=Mock(port=8090)
        )
        installer.config_manager.validate_config = Mock()
        installer.config_manager.save_config = Mock()
        installer.config_manager.config_file_path = installer.server_dir / "config.json"
        installer.jwt_manager.get_or_create_secret = Mock()

        with patch.object(installer, "find_available_port", return_value=8090):
            with patch.object(installer, "create_server_directory_structure"):
                with patch.object(
                    installer,
                    "create_startup_script",
                    return_value=installer.server_dir / "start.sh",
                ):
                    with patch.object(installer, "seed_initial_admin_user"):
                        with patch.object(
                            installer, "install_claude_cli"
                        ) as mock_install_cli:
                            installer.install()

        mock_install_cli.assert_called_once()
