"""
Server Configuration Management for CIDX Server.

Handles server configuration creation, validation, environment variable overrides,
and directory structure setup for the CIDX server installation.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class PasswordSecurityConfig:
    """Password strength validation configuration."""

    min_length: int = 12
    max_length: int = 128
    required_char_classes: int = 4
    min_entropy_bits: int = 50
    check_common_passwords: bool = True
    check_personal_info: bool = True
    check_keyboard_patterns: bool = True
    check_sequential_chars: bool = True


@dataclass
class ServerResourceConfig:
    """
    Resource limits and timeout configuration for CIDX server.

    All previously hardcoded magic numbers are now externalized here.
    All limits are disabled (set to very high values) to remove constraints.
    """

    # Git operation timeouts (in seconds) - lenient values
    git_clone_timeout: int = 3600  # 1 hour for git clone validation
    git_pull_timeout: int = 3600  # 1 hour for git pull
    git_refresh_timeout: int = 3600  # 1 hour for git refresh
    git_init_conflict_timeout: int = 1800  # 30 minutes for init conflict resolution
    git_service_conflict_timeout: int = (
        1800  # 30 minutes for service conflict resolution
    )
    git_service_cleanup_timeout: int = 300  # 5 minutes for service cleanup
    git_service_wait_timeout: int = 180  # 3 minutes for service cleanup wait
    git_process_check_timeout: int = 30  # 30 seconds for process check
    git_untracked_file_timeout: int = 60  # 1 minute for untracked file check

    # Resource limits - effectively unlimited (removed constraints)
    max_golden_repos: Optional[int] = None  # No limit
    max_repo_size_bytes: Optional[int] = None  # No limit
    max_jobs_per_user: Optional[int] = None  # No limit


@dataclass
class ServerConfig:
    """
    Server configuration data structure.

    Contains all configurable server settings including networking,
    authentication, logging, and resource configurations.
    """

    server_dir: str
    host: str = "127.0.0.1"
    port: int = 8000
    jwt_expiration_minutes: int = 10
    log_level: str = "INFO"
    password_security: Optional[PasswordSecurityConfig] = None
    resource_config: Optional[ServerResourceConfig] = None

    def __post_init__(self):
        """Initialize nested config objects if not provided."""
        if self.password_security is None:
            self.password_security = PasswordSecurityConfig()
        if self.resource_config is None:
            self.resource_config = ServerResourceConfig()


class ServerConfigManager:
    """
    Manages CIDX server configuration.

    Handles configuration creation, validation, file persistence,
    environment variable overrides, and server directory setup.
    """

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize server configuration manager.

        Args:
            server_dir_path: Path to server directory (defaults to ~/.cidx-server)
        """
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        self.config_file_path = self.server_dir / "config.json"

    def create_default_config(self) -> ServerConfig:
        """
        Create default server configuration.

        Returns:
            ServerConfig with default values
        """
        return ServerConfig(server_dir=str(self.server_dir))

    def save_config(self, config: ServerConfig) -> None:
        """
        Save configuration to file.

        Args:
            config: ServerConfig object to save
        """
        # Ensure server directory exists
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Convert config to dictionary and save as JSON
        config_dict = asdict(config)

        with open(self.config_file_path, "w") as f:
            json.dump(config_dict, f, indent=2)

    def load_config(self) -> Optional[ServerConfig]:
        """
        Load configuration from file.

        Returns:
            ServerConfig if file exists and is valid, None otherwise

        Raises:
            ValueError: If configuration file is malformed
        """
        if not self.config_file_path.exists():
            return None

        try:
            with open(self.config_file_path, "r") as f:
                config_dict = json.load(f)

            # Ensure server_dir is set if missing from file
            if "server_dir" not in config_dict:
                config_dict["server_dir"] = str(self.server_dir)

            # Convert nested password_security dict to PasswordSecurityConfig
            if "password_security" in config_dict and isinstance(
                config_dict["password_security"], dict
            ):
                config_dict["password_security"] = PasswordSecurityConfig(
                    **config_dict["password_security"]
                )

            # Convert nested resource_config dict to ServerResourceConfig
            if "resource_config" in config_dict and isinstance(
                config_dict["resource_config"], dict
            ):
                config_dict["resource_config"] = ServerResourceConfig(
                    **config_dict["resource_config"]
                )

            return ServerConfig(**config_dict)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse configuration file: {e}")
        except TypeError as e:
            raise ValueError(f"Invalid configuration format: {e}")

    def apply_env_overrides(self, config: ServerConfig) -> ServerConfig:
        """
        Apply environment variable overrides to configuration.

        Supported environment variables:
        - CIDX_SERVER_HOST: Override host setting
        - CIDX_SERVER_PORT: Override port setting
        - CIDX_JWT_EXPIRATION_MINUTES: Override JWT expiration
        - CIDX_LOG_LEVEL: Override log level

        Args:
            config: Base configuration to apply overrides to

        Returns:
            Updated configuration with environment overrides
        """
        # Host override
        if host_env := os.environ.get("CIDX_SERVER_HOST"):
            config.host = host_env

        # Port override
        if port_env := os.environ.get("CIDX_SERVER_PORT"):
            try:
                config.port = int(port_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_SERVER_PORT environment variable value '{port_env}'. Using default port {config.port}"
                )

        # JWT expiration override
        if jwt_exp_env := os.environ.get("CIDX_JWT_EXPIRATION_MINUTES"):
            try:
                config.jwt_expiration_minutes = int(jwt_exp_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_JWT_EXPIRATION_MINUTES environment variable value '{jwt_exp_env}'. Using default {config.jwt_expiration_minutes} minutes"
                )

        # Log level override
        if log_level_env := os.environ.get("CIDX_LOG_LEVEL"):
            config.log_level = log_level_env.upper()

        return config

    def validate_config(self, config: ServerConfig) -> None:
        """
        Validate configuration settings.

        Args:
            config: Configuration to validate

        Raises:
            ValueError: If any configuration value is invalid
        """
        # Validate port range
        if not (1 <= config.port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {config.port}")

        # Validate JWT expiration
        if config.jwt_expiration_minutes <= 0:
            raise ValueError(
                f"JWT expiration must be greater than 0, got {config.jwt_expiration_minutes}"
            )

        # Validate log level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if config.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Log level must be one of {valid_log_levels}, got {config.log_level}"
            )

    def create_server_directories(self) -> None:
        """
        Create necessary server directories.

        Creates:
        - Main server directory
        - logs/ subdirectory
        - data/ subdirectory
        """
        # Create main server directory
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Create logs directory
        logs_dir = self.server_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Create data directory
        data_dir = self.server_dir / "data"
        data_dir.mkdir(exist_ok=True)
