"""
End-to-End tests for Story 4: Server Installation and Configuration.

Tests the complete server installation workflow without mocking,
ensuring the install-server command creates proper directory structure,
configuration files, and integrates with ServerConfigManager correctly.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path


class TestStory4ServerInstallationE2E:
    """E2E test suite for server installation functionality."""

    def test_install_server_creates_proper_directory_structure(self):
        """Test that install-server creates correct directory structure as per acceptance criteria."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set HOME to temporary directory to isolate the test
            original_home = os.environ.get("HOME")
            temp_home = Path(temp_dir) / "test_home"
            temp_home.mkdir()
            os.environ["HOME"] = str(temp_home)

            try:
                # Run the actual install-server command
                result = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server", "--force"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Should succeed
                assert result.returncode == 0, f"install-server failed: {result.stderr}"

                # Verify directory structure exists as per acceptance criteria
                server_dir = temp_home / ".cidx-server"
                assert server_dir.exists(), "Server directory not created"
                assert server_dir.is_dir(), "Server directory is not a directory"

                # Check required files and directories
                assert (server_dir / "config.json").exists(), "config.json not created"
                assert (server_dir / ".jwt_secret").exists(), "JWT secret not created"
                assert (server_dir / "users.json").exists(), "users.json not created"
                assert (server_dir / "logs").exists(), "logs directory not created"
                assert (server_dir / "logs").is_dir(), "logs is not a directory"
                assert (server_dir / "data").exists(), "data directory not created"
                assert (server_dir / "data").is_dir(), "data is not a directory"

            finally:
                # Restore original HOME
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)

    def test_install_server_creates_valid_configuration(self):
        """Test that install-server creates valid configuration with default values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_home = os.environ.get("HOME")
            temp_home = Path(temp_dir) / "test_home"
            temp_home.mkdir()
            os.environ["HOME"] = str(temp_home)

            try:
                # Run install-server
                result = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server", "--force"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert result.returncode == 0, f"install-server failed: {result.stderr}"

                # Read and validate configuration
                config_file = temp_home / ".cidx-server" / "config.json"
                assert config_file.exists(), "Configuration file not created"

                with open(config_file) as f:
                    config_data = json.load(f)

                # Verify configuration structure and default values as per acceptance criteria
                # Note: The current ServerInstaller uses a different structure than our ServerConfigManager
                # This test validates the current implementation, but shows the need for integration
                assert "server" in config_data, "Server section missing from config"
                server_config = config_data["server"]

                assert (
                    server_config["host"] == "127.0.0.1"
                ), f"Expected host 127.0.0.1, got {server_config['host']}"
                assert isinstance(server_config["port"], int), "Port should be integer"
                assert (
                    1 <= server_config["port"] <= 65535
                ), f"Port {server_config['port']} out of valid range"
                assert (
                    server_config["jwt_expiration_minutes"] == 10
                ), f"Expected JWT expiration 10, got {server_config['jwt_expiration_minutes']}"

            finally:
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)

    def test_install_server_with_custom_port(self):
        """Test install-server with custom port parameter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_home = os.environ.get("HOME")
            temp_home = Path(temp_dir) / "test_home"
            temp_home.mkdir()
            os.environ["HOME"] = str(temp_home)

            try:
                # Run install-server with custom port
                result = subprocess.run(
                    [
                        "python3",
                        "-m",
                        "code_indexer.cli",
                        "install-server",
                        "--port",
                        "9999",
                        "--force",
                    ],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert (
                    result.returncode == 0
                ), f"install-server with custom port failed: {result.stderr}"

                # Verify the port was used (or next available port was found)
                config_file = temp_home / ".cidx-server" / "config.json"
                with open(config_file) as f:
                    config_data = json.load(f)

                # Should either use the requested port or find next available
                actual_port = config_data["server"]["port"]
                assert (
                    actual_port >= 9999
                ), f"Port {actual_port} should be >= requested port 9999"

            finally:
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)

    def test_install_server_jwt_secret_persistence(self):
        """Test that JWT secret is created and persists across multiple runs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_home = os.environ.get("HOME")
            temp_home = Path(temp_dir) / "test_home"
            temp_home.mkdir()
            os.environ["HOME"] = str(temp_home)

            try:
                # First installation
                result1 = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server", "--force"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert (
                    result1.returncode == 0
                ), f"First install-server failed: {result1.stderr}"

                jwt_secret_file = temp_home / ".cidx-server" / ".jwt_secret"
                assert jwt_secret_file.exists(), "JWT secret file not created"

                # Read the secret
                with open(jwt_secret_file) as f:
                    first_secret = f.read().strip()

                assert len(first_secret) > 0, "JWT secret is empty"

                # Check file permissions are secure (readable by owner only)
                file_mode = jwt_secret_file.stat().st_mode & 0o777
                assert (
                    file_mode == 0o600
                ), f"JWT secret file permissions {oct(file_mode)} not secure (expected 0o600)"

                # Second installation (reinstall)
                result2 = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server", "--force"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert (
                    result2.returncode == 0
                ), f"Second install-server failed: {result2.stderr}"

                # JWT secret should persist (not change)
                with open(jwt_secret_file) as f:
                    second_secret = f.read().strip()

                assert (
                    first_secret == second_secret
                ), "JWT secret changed during reinstallation"

            finally:
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)

    def test_install_server_existing_installation_detection(self):
        """Test that install-server detects existing installations correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_home = os.environ.get("HOME")
            temp_home = Path(temp_dir) / "test_home"
            temp_home.mkdir()
            os.environ["HOME"] = str(temp_home)

            try:
                # First installation
                result1 = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert (
                    result1.returncode == 0
                ), f"First install-server failed: {result1.stderr}"
                assert (
                    "Installing CIDX Server" in result1.stdout
                    or "installed successfully" in result1.stdout
                )

                # Second installation without force should detect existing
                result2 = subprocess.run(
                    ["python3", "-m", "code_indexer.cli", "install-server"],
                    cwd="/home/jsbattig/Dev/code-indexer",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                assert (
                    result2.returncode == 0
                ), f"Second install-server failed: {result2.stderr}"
                assert (
                    "already installed" in result2.stdout
                ), "Should detect existing installation"

            finally:
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)

    def test_server_config_manager_integration(self):
        """Test that ServerConfigManager integrates properly with the installation process."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test ServerConfigManager directly
            from code_indexer.server.utils.config_manager import ServerConfigManager

            server_dir = Path(temp_dir) / ".cidx-server"
            config_manager = ServerConfigManager(str(server_dir))

            # Create configuration using ServerConfigManager
            config = config_manager.create_default_config()

            # Verify default values match acceptance criteria
            assert config.host == "127.0.0.1"
            assert config.port == 8000
            assert config.jwt_expiration_minutes == 10
            assert config.log_level == "INFO"

            # Test environment overrides
            original_env = {}
            for key in [
                "CIDX_SERVER_HOST",
                "CIDX_SERVER_PORT",
                "CIDX_JWT_EXPIRATION_MINUTES",
                "CIDX_LOG_LEVEL",
            ]:
                original_env[key] = os.environ.get(key)

            try:
                # Set environment overrides
                os.environ["CIDX_SERVER_HOST"] = "0.0.0.0"
                os.environ["CIDX_SERVER_PORT"] = "7000"
                os.environ["CIDX_JWT_EXPIRATION_MINUTES"] = "15"
                os.environ["CIDX_LOG_LEVEL"] = "DEBUG"

                # Apply environment overrides
                config_with_env = config_manager.apply_env_overrides(config)

                # Verify overrides applied
                assert config_with_env.host == "0.0.0.0"
                assert config_with_env.port == 7000
                assert config_with_env.jwt_expiration_minutes == 15
                assert config_with_env.log_level == "DEBUG"

                # Test configuration validation
                config_manager.validate_config(config_with_env)  # Should not raise

                # Test directory creation
                config_manager.create_server_directories()
                assert server_dir.exists()
                assert (server_dir / "logs").exists()
                assert (server_dir / "data").exists()

                # Test configuration persistence
                config_manager.save_config(config_with_env)
                assert (server_dir / "config.json").exists()

                # Test configuration loading
                loaded_config = config_manager.load_config()
                assert loaded_config is not None
                assert loaded_config.host == "0.0.0.0"
                assert loaded_config.port == 7000
                assert loaded_config.jwt_expiration_minutes == 15
                assert loaded_config.log_level == "DEBUG"

            finally:
                # Restore environment
                for key, value in original_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
