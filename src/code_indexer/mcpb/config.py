"""Configuration management for MCP Stdio Bridge.

This module handles loading and validating configuration from config files
and environment variables.
"""

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Default configuration values
DEFAULT_TIMEOUT = 30
DEFAULT_LOG_LEVEL = "info"
DEFAULT_CONFIG_PATH = Path.home() / ".mcpb" / "config.json"
VALID_LOG_LEVELS = ["debug", "info", "warning", "error"]
MIN_TIMEOUT = 1
MAX_TIMEOUT = 300

logger = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    """Configuration for the MCP Stdio Bridge.

    Args:
        server_url: Base URL of CIDX server (must use HTTPS)
        bearer_token: Bearer token for authentication
        timeout: Request timeout in seconds (1-300, default: 30)
        log_level: Logging level (debug/info/warning/error, default: info)
    """

    server_url: str
    bearer_token: str
    timeout: int = DEFAULT_TIMEOUT
    log_level: str = DEFAULT_LOG_LEVEL

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.server_url:
            raise ValueError("server_url cannot be empty")

        if not self.bearer_token:
            raise ValueError("bearer_token cannot be empty")

        # HTTPS validation (Story #517)
        # Allow localhost/127.0.0.1 for testing, but require HTTPS for all other URLs
        is_localhost = (
            "://localhost" in self.server_url or "://127.0.0.1" in self.server_url
        )
        if not self.server_url.startswith("https://") and not is_localhost:
            raise ValueError(
                "server_url must use HTTPS for security. "
                f"Got: {self.server_url[:20]}..."
            )

        # Timeout range validation (Story #517)
        if self.timeout < MIN_TIMEOUT or self.timeout > MAX_TIMEOUT:
            raise ValueError(
                f"timeout must be between {MIN_TIMEOUT} and {MAX_TIMEOUT} seconds. "
                f"Got: {self.timeout}"
            )

        # Log level validation (Story #517)
        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {VALID_LOG_LEVELS}. "
                f"Got: {self.log_level}"
            )

        # Strip trailing slash from server_url
        self.server_url = self.server_url.rstrip("/")


def load_config(
    config_path: Optional[str] = None, use_env: bool = False
) -> BridgeConfig:
    """Load configuration from file and/or environment variables.

    Args:
        config_path: Path to config JSON file (default: ~/.mcpb/config.json)
        use_env: Whether to use environment variables (overrides file config)

    Returns:
        BridgeConfig instance

    Raises:
        FileNotFoundError: If config file not found
        json.JSONDecodeError: If config file contains invalid JSON
        ValueError: If required fields are missing or invalid

    Environment Variables (Story #517 - CIDX_* takes precedence over MCPB_*):
        CIDX_SERVER_URL or MCPB_SERVER_URL: Server URL (overrides file)
        CIDX_TOKEN or MCPB_BEARER_TOKEN: Bearer token (overrides file)
        CIDX_TIMEOUT or MCPB_TIMEOUT: Timeout in seconds (overrides file)
        CIDX_LOG_LEVEL or MCPB_LOG_LEVEL: Log level (overrides file)
    """
    config_data = {}

    # Load from file if path provided or using default
    if config_path is not None or (not use_env):
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        path = path.expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        # Check file permissions (Story #517)
        file_stat = os.stat(path)
        file_mode = stat.filemode(file_stat.st_mode)
        # Get octal permissions (last 3 digits)
        file_perms = file_stat.st_mode & 0o777

        if file_perms != 0o600:
            logger.warning(
                f"Configuration file {path} has insecure permissions {oct(file_perms)}. "
                f"Recommend setting to 0600: chmod 0600 {path}"
            )

        import json

        with open(path) as f:
            config_data = json.load(f)

    # Override with environment variables if enabled (Story #517)
    # CIDX_* takes precedence over MCPB_* for backward compatibility
    if use_env:
        # Server URL: CIDX_SERVER_URL > MCPB_SERVER_URL
        if "CIDX_SERVER_URL" in os.environ:
            config_data["server_url"] = os.environ["CIDX_SERVER_URL"]
        elif "MCPB_SERVER_URL" in os.environ:
            config_data["server_url"] = os.environ["MCPB_SERVER_URL"]

        # Token: CIDX_TOKEN > MCPB_BEARER_TOKEN
        if "CIDX_TOKEN" in os.environ:
            config_data["bearer_token"] = os.environ["CIDX_TOKEN"]
        elif "MCPB_BEARER_TOKEN" in os.environ:
            config_data["bearer_token"] = os.environ["MCPB_BEARER_TOKEN"]

        # Timeout: CIDX_TIMEOUT > MCPB_TIMEOUT
        if "CIDX_TIMEOUT" in os.environ:
            config_data["timeout"] = int(os.environ["CIDX_TIMEOUT"])
        elif "MCPB_TIMEOUT" in os.environ:
            config_data["timeout"] = int(os.environ["MCPB_TIMEOUT"])

        # Log level: CIDX_LOG_LEVEL > MCPB_LOG_LEVEL (Story #517)
        if "CIDX_LOG_LEVEL" in os.environ:
            config_data["log_level"] = os.environ["CIDX_LOG_LEVEL"]
        elif "MCPB_LOG_LEVEL" in os.environ:
            config_data["log_level"] = os.environ["MCPB_LOG_LEVEL"]

    # Validate required fields with helpful error messages (Story #517)
    if "server_url" not in config_data:
        raise ValueError(
            "Missing required field: server_url\n"
            "  Fix: Set CIDX_SERVER_URL environment variable\n"
            "  Or: Add 'server_url' to ~/.mcpb/config.json"
        )
    if "bearer_token" not in config_data:
        raise ValueError(
            "Missing required field: bearer_token\n"
            "  Fix: Set CIDX_TOKEN environment variable\n"
            "  Or: Add 'bearer_token' to ~/.mcpb/config.json"
        )

    # Use defaults if not specified
    if "timeout" not in config_data:
        config_data["timeout"] = DEFAULT_TIMEOUT
    if "log_level" not in config_data:
        config_data["log_level"] = DEFAULT_LOG_LEVEL

    return BridgeConfig(**config_data)
