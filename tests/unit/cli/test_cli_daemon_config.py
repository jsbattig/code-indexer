"""Unit tests for CLI daemon configuration commands.

This module tests the CLI commands for managing daemon configuration:
- cidx init --daemon
- cidx config --show
- cidx config --daemon
- cidx config --daemon-ttl

Tests follow TDD methodology - written before implementation.
"""

import pytest
from click.testing import CliRunner
from code_indexer.cli import cli
from code_indexer.config import ConfigManager


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def isolated_project(tmp_path):
    """Create an isolated project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


class TestInitWithDaemon:
    """Test cidx init command with --daemon flag."""

    def test_init_without_daemon_flag(self, runner, isolated_project):
        """Init without --daemon should not enable daemon mode."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            result = runner.invoke(cli, ["init", str(isolated_project)])
            assert result.exit_code == 0

            # Check config file
            config_path = isolated_project / ".code-indexer" / "config.json"
            assert config_path.exists()

            # Daemon should not be enabled by default
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            # daemon field should be None (not configured) or disabled
            assert config.daemon is None or config.daemon.enabled is False

    def test_init_with_daemon_flag(self, runner, isolated_project):
        """Init with --daemon should enable daemon mode."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            result = runner.invoke(cli, ["init", str(isolated_project), "--daemon"])
            assert result.exit_code == 0
            assert "Daemon mode enabled" in result.output or "daemon" in result.output.lower()

            # Check config file
            config_path = isolated_project / ".code-indexer" / "config.json"
            assert config_path.exists()

            # Daemon should be enabled with default TTL
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.enabled is True
            assert config.daemon.ttl_minutes == 10

    def test_init_with_daemon_and_custom_ttl(self, runner, isolated_project):
        """Init with --daemon and --daemon-ttl should set custom TTL."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            result = runner.invoke(
                cli, ["init", str(isolated_project), "--daemon", "--daemon-ttl", "20"]
            )
            assert result.exit_code == 0

            # Check config file
            config_path = isolated_project / ".code-indexer" / "config.json"
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.enabled is True
            assert config.daemon.ttl_minutes == 20

    def test_init_daemon_ttl_without_daemon_flag(self, runner, isolated_project):
        """Using --daemon-ttl without --daemon should show warning or be ignored."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            result = runner.invoke(cli, ["init", str(isolated_project), "--daemon-ttl", "15"])
            # Should either warn user or just ignore the TTL flag
            assert result.exit_code == 0


class TestConfigShow:
    """Test cidx config --show command."""

    def test_config_show_no_daemon(self, runner, isolated_project):
        """Show config when daemon is not configured."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create basic config without daemon
            runner.invoke(cli, ["init", str(isolated_project)])

            # Show config (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--show"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "Daemon Mode" in result.output or "daemon" in result.output.lower()
                assert "Disabled" in result.output or "disabled" in result.output.lower()
            finally:
                os.chdir(original_cwd)

    def test_config_show_with_daemon_enabled(self, runner, isolated_project):
        """Show config when daemon is enabled."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config with daemon
            runner.invoke(cli, ["init", str(isolated_project), "--daemon", "--daemon-ttl", "15"])

            # Show config (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--show"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "Daemon Mode" in result.output or "daemon" in result.output.lower()
                assert "Enabled" in result.output or "enabled" in result.output.lower()
                assert "15" in result.output  # TTL value
            finally:
                os.chdir(original_cwd)


class TestConfigDaemonToggle:
    """Test cidx config --daemon/--no-daemon command."""

    def test_config_enable_daemon(self, runner, isolated_project):
        """Enable daemon mode via config command."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config without daemon
            runner.invoke(cli, ["init", str(isolated_project)])

            # Enable daemon (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--daemon"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "enabled" in result.output.lower()
            finally:
                os.chdir(original_cwd)

            # Verify it's enabled
            config_path = isolated_project / ".code-indexer" / "config.json"
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.enabled is True

    def test_config_disable_daemon(self, runner, isolated_project):
        """Disable daemon mode via config command."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config with daemon
            runner.invoke(cli, ["init", str(isolated_project), "--daemon"])

            # Disable daemon (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--no-daemon"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "disabled" in result.output.lower()
            finally:
                os.chdir(original_cwd)

            # Verify it's disabled
            config_path = isolated_project / ".code-indexer" / "config.json"
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.enabled is False


class TestConfigDaemonTTL:
    """Test cidx config --daemon-ttl command."""

    def test_config_update_ttl(self, runner, isolated_project):
        """Update daemon TTL via config command."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config with daemon
            runner.invoke(cli, ["init", str(isolated_project), "--daemon"])

            # Update TTL (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--daemon-ttl", "30"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "30" in result.output
            finally:
                os.chdir(original_cwd)

            # Verify TTL is updated
            config_path = isolated_project / ".code-indexer" / "config.json"
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.ttl_minutes == 30

    def test_config_update_ttl_without_daemon(self, runner, isolated_project):
        """Update daemon TTL when daemon not yet configured."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config without daemon
            runner.invoke(cli, ["init", str(isolated_project)])

            # Update TTL (should create daemon config) (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--daemon-ttl", "25"], catch_exceptions=False)
                assert result.exit_code == 0
            finally:
                os.chdir(original_cwd)

            # Verify daemon config created with TTL
            config_path = isolated_project / ".code-indexer" / "config.json"
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert config.daemon is not None
            assert config.daemon.ttl_minutes == 25


class TestConfigValidation:
    """Test validation in CLI config commands."""

    def test_config_invalid_ttl_negative(self, runner, isolated_project):
        """Negative TTL should be rejected."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            runner.invoke(cli, ["init", str(isolated_project)])

            # Test with negative TTL (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--daemon-ttl", "-1"], catch_exceptions=False)
                # Should fail or show error
                assert result.exit_code != 0 or "error" in result.output.lower()
            finally:
                os.chdir(original_cwd)

    def test_config_invalid_ttl_too_large(self, runner, isolated_project):
        """TTL > 10080 should be rejected."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            runner.invoke(cli, ["init", str(isolated_project)])

            # Test with too large TTL (from within project directory)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(isolated_project))
                result = runner.invoke(cli, ["config", "--daemon-ttl", "10081"], catch_exceptions=False)
                # Should fail or show error
                assert result.exit_code != 0 or "error" in result.output.lower()
            finally:
                os.chdir(original_cwd)

    def test_init_invalid_daemon_ttl(self, runner, isolated_project):
        """Invalid TTL in init should be rejected."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            result = runner.invoke(
                cli, ["init", str(isolated_project), "--daemon", "--daemon-ttl", "0"],
                catch_exceptions=False
            )
            # Should fail or show error
            assert result.exit_code != 0 or "error" in result.output.lower()


class TestConfigWithBacktracking:
    """Test config command with backtracking to find config."""

    def test_config_from_subdirectory(self, runner, isolated_project):
        """Config command should work from subdirectory."""
        with runner.isolated_filesystem(temp_dir=isolated_project.parent):
            # Create config
            runner.invoke(cli, ["init", str(isolated_project), "--daemon"])

            # Create subdirectory
            subdir = isolated_project / "src" / "module"
            subdir.mkdir(parents=True)

            # Run config from subdirectory (should backtrack and find config)
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(subdir))
                result = runner.invoke(cli, ["config", "--show"], catch_exceptions=False)
                assert result.exit_code == 0
                assert "Daemon Mode" in result.output or "daemon" in result.output.lower()
            finally:
                os.chdir(original_cwd)
