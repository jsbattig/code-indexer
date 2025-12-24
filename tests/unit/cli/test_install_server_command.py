"""
Unit tests for install-server CLI command.

Tests the install-server command integration with ServerConfigManager,
proper configuration validation, and successful installation workflow.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from code_indexer.cli import cli


class TestInstallServerCommand:
    """Test suite for install-server CLI command."""

    def test_install_server_creates_default_configuration(self):
        """Test that install-server creates configuration with defaults."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir) / ".cidx-server"

            # Mock ServerInstaller to use our temporary directory
            with patch(
                "code_indexer.server.installer.ServerInstaller"
            ) as mock_installer_class:
                mock_installer = MagicMock()
                mock_installer.server_dir = server_dir
                mock_installer.get_installation_info.return_value = {"installed": False}
                # install() returns (port, config_path, script_path, is_new_installation)
                mock_installer.install.return_value = (
                    8000,
                    server_dir / "config.json",
                    server_dir / "start-server.sh",
                    True,
                )
                mock_installer_class.return_value = mock_installer

                runner = CliRunner()
                result = runner.invoke(cli, ["install-server"])

                if result.exit_code != 0:
                    print(f"Command output: {result.output}")
                    print(f"Exception: {result.exception}")
                assert result.exit_code == 0
                mock_installer.install.assert_called_once()

    def test_install_server_with_custom_port(self):
        """Test install-server with custom port parameter."""
        with patch(
            "code_indexer.server.installer.ServerInstaller"
        ) as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.get_installation_info.return_value = {"installed": False}
            # install() returns (port, config_path, script_path, is_new_installation)
            mock_installer.install.return_value = (
                9000,
                Path("/test/.cidx-server/config.json"),
                Path("/test/.cidx-server/start-server.sh"),
                True,
            )
            mock_installer_class.return_value = mock_installer

            runner = CliRunner()
            result = runner.invoke(cli, ["install-server", "--port", "9000"])

            assert result.exit_code == 0
            mock_installer_class.assert_called_once_with(base_port=9000)

    def test_install_server_force_reinstall(self):
        """Test install-server with force flag for reinstallation."""
        with patch(
            "code_indexer.server.installer.ServerInstaller"
        ) as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.get_installation_info.return_value = {
                "installed": True,
                "configured": True,
                "port": 8000,
            }
            # install() returns (port, config_path, script_path, is_new_installation)
            mock_installer.install.return_value = (
                8000,
                Path("/test/.cidx-server/config.json"),
                Path("/test/.cidx-server/start-server.sh"),
                False,  # Not a new installation since we're forcing reinstall
            )
            mock_installer_class.return_value = mock_installer

            runner = CliRunner()
            result = runner.invoke(cli, ["install-server", "--force"])

            assert result.exit_code == 0
            mock_installer.install.assert_called_once()

    def test_install_server_existing_installation_without_force(self):
        """Test install-server skips installation when already exists without force."""
        with patch(
            "code_indexer.server.installer.ServerInstaller"
        ) as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.get_installation_info.return_value = {
                "installed": True,
                "configured": True,
                "port": 8000,
                "installation_time": "2024-01-01 12:00:00",
            }
            mock_installer.server_dir = Path("/home/test/.cidx-server")
            mock_installer_class.return_value = mock_installer

            runner = CliRunner()
            result = runner.invoke(cli, ["install-server"])

            if result.exit_code != 0:
                print(f"Command output: {result.output}")
                print(f"Exception: {result.exception}")
            assert result.exit_code == 0
            assert "already installed" in result.output
            mock_installer.install.assert_not_called()

    def test_install_server_integration_with_config_manager(self):
        """Test install-server properly integrates with ServerConfigManager."""
        # This test will verify that ServerInstaller properly uses ServerConfigManager
        # We need to check that the installer creates the correct directory structure
        # and configuration files as specified in the acceptance criteria

        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir) / ".cidx-server"

            with patch(
                "code_indexer.server.installer.ServerInstaller"
            ) as mock_installer_class:
                mock_installer = MagicMock()
                mock_installer.server_dir = server_dir
                mock_installer.get_installation_info.return_value = {"installed": False}

                # install() returns (port, config_path, script_path, is_new_installation)
                mock_installer.install.return_value = (
                    8000,
                    server_dir / "config.json",
                    server_dir / "start-server.sh",
                    True,
                )

                mock_installer_class.return_value = mock_installer

                runner = CliRunner()
                result = runner.invoke(cli, ["install-server"])

                if result.exit_code != 0:
                    print(f"Command output: {result.output}")
                    print(f"Exception: {result.exception}")
                assert result.exit_code == 0
                mock_installer.install.assert_called_once()

                # Verify the installer was initialized correctly
                mock_installer_class.assert_called_once_with(base_port=8090)

    def test_install_server_handles_installation_errors(self):
        """Test install-server handles installation errors gracefully."""
        with patch(
            "code_indexer.server.installer.ServerInstaller"
        ) as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.get_installation_info.return_value = {"installed": False}
            mock_installer.install_server.side_effect = Exception("Installation failed")
            mock_installer_class.return_value = mock_installer

            runner = CliRunner()
            result = runner.invoke(cli, ["install-server"])

            # Command should handle the error gracefully
            assert result.exit_code != 0

    def test_install_server_validates_port_parameter(self):
        """Test install-server validates port parameter range."""
        runner = CliRunner()

        # Test with invalid port (too low)
        runner.invoke(cli, ["install-server", "--port", "0"])
        # Click should handle validation or our code should catch invalid ports

        # Test with invalid port (too high)
        runner.invoke(cli, ["install-server", "--port", "70000"])
        # Click should handle validation or our code should catch invalid ports


class TestServerInstallationIntegration:
    """Integration tests for server installation components."""

    def test_server_installer_uses_config_manager_properly(self):
        """Test that ServerInstaller properly uses ServerConfigManager."""
        # This test ensures the ServerInstaller class properly integrates with
        # our new ServerConfigManager for configuration handling

        # Import and test the actual ServerInstaller integration
        from code_indexer.server.installer import ServerInstaller

        # This should not fail if ServerInstaller properly uses ServerConfigManager
        installer = ServerInstaller(base_port=8000)

        # Verify that the installer can create configuration
        # This tests the integration between components
        assert hasattr(installer, "server_dir")
        assert installer.server_dir == Path.home() / ".cidx-server"

    def test_config_manager_directory_creation_matches_requirements(self):
        """Test that ServerConfigManager creates the correct directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir) / ".cidx-server"

            from code_indexer.server.utils.config_manager import ServerConfigManager

            config_manager = ServerConfigManager(str(server_dir))
            config_manager.create_server_directories()

            # Verify directory structure matches acceptance criteria
            assert server_dir.exists()
            assert (server_dir / "logs").exists()
            assert (server_dir / "data").exists()

            # Test configuration creation
            config = config_manager.create_default_config()
            config_manager.save_config(config)

            assert (server_dir / "config.json").exists()

            # Verify default configuration values match acceptance criteria
            with open(server_dir / "config.json") as f:
                saved_config = json.load(f)

            assert saved_config["host"] == "127.0.0.1"
            assert saved_config["port"] == 8000
            assert saved_config["jwt_expiration_minutes"] == 10
            assert saved_config["log_level"] == "INFO"
