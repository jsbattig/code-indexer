"""
Unit tests for ServerConfigManager.

Tests configuration management functionality including creation, validation,
environment variable overrides, and default configuration handling.
"""

import json
import os
from unittest.mock import patch

import pytest

from code_indexer.server.utils.config_manager import ServerConfigManager, ServerConfig


class TestServerConfigManager:
    """Test suite for ServerConfigManager."""

    def test_default_configuration_creation(self, tmp_path):
        """Test creating configuration with default values."""
        config_manager = ServerConfigManager(str(tmp_path))

        config = config_manager.create_default_config()

        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.jwt_expiration_minutes == 10
        assert config.log_level == "INFO"
        assert config.server_dir == str(tmp_path)

    def test_configuration_file_creation(self, tmp_path):
        """Test configuration file creation with proper structure."""
        config_manager = ServerConfigManager(str(tmp_path))

        config = config_manager.create_default_config()
        config_manager.save_config(config)

        config_file = tmp_path / "config.json"
        assert config_file.exists()

        with open(config_file) as f:
            saved_config = json.load(f)

        assert saved_config["host"] == "127.0.0.1"
        assert saved_config["port"] == 8000
        assert saved_config["jwt_expiration_minutes"] == 10
        assert saved_config["log_level"] == "INFO"

    def test_configuration_loading_from_file(self, tmp_path):
        """Test loading configuration from existing file."""
        # Create config file manually
        config_data = {
            "host": "0.0.0.0",
            "port": 8080,
            "jwt_expiration_minutes": 15,
            "log_level": "DEBUG",
        }

        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.load_config()

        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.jwt_expiration_minutes == 15
        assert config.log_level == "DEBUG"

    def test_environment_variable_overrides(self, tmp_path):
        """Test environment variable configuration overrides."""
        with patch.dict(
            os.environ,
            {
                "CIDX_SERVER_HOST": "192.168.1.100",
                "CIDX_SERVER_PORT": "9000",
                "CIDX_JWT_EXPIRATION_MINUTES": "30",
                "CIDX_LOG_LEVEL": "WARNING",
            },
        ):
            config_manager = ServerConfigManager(str(tmp_path))
            config = config_manager.create_default_config()
            config = config_manager.apply_env_overrides(config)

            assert config.host == "192.168.1.100"
            assert config.port == 9000
            assert config.jwt_expiration_minutes == 30
            assert config.log_level == "WARNING"

    def test_partial_environment_overrides(self, tmp_path):
        """Test partial environment variable overrides."""
        with patch.dict(
            os.environ, {"CIDX_SERVER_PORT": "7000", "CIDX_LOG_LEVEL": "ERROR"}
        ):
            config_manager = ServerConfigManager(str(tmp_path))
            config = config_manager.create_default_config()
            config = config_manager.apply_env_overrides(config)

            # Overridden values
            assert config.port == 7000
            assert config.log_level == "ERROR"

            # Default values maintained
            assert config.host == "127.0.0.1"
            assert config.jwt_expiration_minutes == 10

    def test_configuration_validation_success(self, tmp_path):
        """Test successful configuration validation."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.create_default_config()

        # Should not raise any exception
        config_manager.validate_config(config)

    def test_configuration_validation_invalid_port(self, tmp_path):
        """Test configuration validation with invalid port."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.create_default_config()
        config.port = -1  # Invalid port

        with pytest.raises(ValueError, match="Port must be between"):
            config_manager.validate_config(config)

    def test_configuration_validation_invalid_jwt_expiration(self, tmp_path):
        """Test configuration validation with invalid JWT expiration."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.create_default_config()
        config.jwt_expiration_minutes = 0  # Invalid expiration

        with pytest.raises(ValueError, match="JWT expiration must be greater than 0"):
            config_manager.validate_config(config)

    def test_configuration_validation_invalid_log_level(self, tmp_path):
        """Test configuration validation with invalid log level."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.create_default_config()
        config.log_level = "INVALID"  # Invalid log level

        with pytest.raises(ValueError, match="Log level must be one of"):
            config_manager.validate_config(config)

    def test_directory_structure_creation(self, tmp_path):
        """Test server directory structure creation."""
        config_manager = ServerConfigManager(str(tmp_path))
        config_manager.create_server_directories()

        # Check main directories
        assert (tmp_path / "logs").exists()
        assert (tmp_path / "logs").is_dir()
        assert (tmp_path / "data").exists()
        assert (tmp_path / "data").is_dir()

    def test_configuration_file_not_exists_returns_none(self, tmp_path):
        """Test loading configuration when file doesn't exist returns None."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.load_config()

        assert config is None

    def test_malformed_configuration_file_raises_error(self, tmp_path):
        """Test loading malformed configuration file raises error."""
        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            f.write("invalid json content")

        config_manager = ServerConfigManager(str(tmp_path))

        with pytest.raises(ValueError, match="Failed to parse configuration"):
            config_manager.load_config()

    def test_server_config_dataclass_defaults(self):
        """Test ServerConfig dataclass has proper defaults."""
        config = ServerConfig(server_dir="/test/path")

        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.jwt_expiration_minutes == 10
        assert config.log_level == "INFO"
        assert config.server_dir == "/test/path"

    def test_integration_with_jwt_secret_manager(self, tmp_path):
        """Test that ServerConfigManager integrates properly with JWTSecretManager."""
        config_manager = ServerConfigManager(str(tmp_path))

        # Create config and directories
        config = config_manager.create_default_config()
        config_manager.save_config(config)
        config_manager.create_server_directories()

        # JWT secret manager should work with the same directory
        from code_indexer.server.utils.jwt_secret_manager import JWTSecretManager

        jwt_manager = JWTSecretManager(str(tmp_path))
        secret = jwt_manager.get_or_create_secret()

        assert secret is not None
        assert len(secret) > 0
        assert (tmp_path / ".jwt_secret").exists()
