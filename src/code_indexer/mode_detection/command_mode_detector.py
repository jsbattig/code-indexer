"""Command Mode Detection for CIDX CLI.

Automatically detects whether commands should run in local, remote, or uninitialized mode
based on configuration file presence and validation.
"""

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


class ModeDetectionError(Exception):
    """Exception raised when mode detection fails."""

    pass


def find_project_root(start_path: Path) -> Path:
    """Find project root by walking up directory tree to find .code-indexer directory.

    Args:
        start_path: Directory to start searching from

    Returns:
        Path to project root containing .code-indexer directory, or start_path if none found
    """
    current = start_path.resolve()

    try:
        # Walk up the directory tree looking for .code-indexer directory
        # Limit search to reasonable depth to avoid going too far up
        search_paths = [current] + list(current.parents)[:10]  # Limit to 10 levels up
        for path in search_paths:
            try:
                config_dir = path / ".code-indexer"
                if config_dir.exists() and config_dir.is_dir():
                    return path
            except (PermissionError, OSError):
                # Continue searching if we can't access this directory
                continue
    except (PermissionError, OSError) as e:
        logger.warning(f"Permission error during project root discovery: {e}")

    # Return start path if no .code-indexer directory found
    return start_path


class CommandModeDetector:
    """Detects the operational mode for CIDX commands based on configuration files."""

    def __init__(self, project_root: Path):
        """Initialize mode detector with project root path.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = project_root
        self.config_dir = project_root / ".code-indexer"

    def detect_mode(self) -> Literal["local", "remote", "uninitialized"]:
        """Detect current operational mode based on configuration files.

        Detection priority:
        1. Remote config (.remote-config) takes precedence if valid
        2. Local config (config.json) if valid
        3. Uninitialized if no valid configuration found

        Returns:
            Mode string: "local", "remote", or "uninitialized"
        """
        # Check if .code-indexer directory exists
        if not self.config_dir.exists():
            return "uninitialized"

        # Check for remote configuration first (higher priority)
        remote_config_path = self.config_dir / ".remote-config"
        if remote_config_path.exists():
            if self._validate_remote_config(remote_config_path):
                return "remote"

        # Check for local configuration
        local_config_path = self.config_dir / "config.json"
        if local_config_path.exists():
            if self._validate_local_config(local_config_path):
                return "local"

        # No valid configuration found
        return "uninitialized"

    def _validate_remote_config(self, config_path: Path) -> bool:
        """Validate remote configuration integrity.

        Args:
            config_path: Path to .remote-config file

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)

            # Check for required fields
            required_fields = ["server_url", "encrypted_credentials"]

            for field in required_fields:
                if field not in config_data:
                    logger.debug(f"Remote config missing required field: {field}")
                    return False

                # Check that required fields are not empty
                if not config_data[field]:
                    logger.debug(f"Remote config field is empty: {field}")
                    return False

            # Validate server_url format
            server_url = config_data["server_url"]
            if not isinstance(server_url, str) or not server_url.startswith(
                ("http://", "https://")
            ):
                logger.debug(f"Invalid server_url format: {server_url}")
                return False

            return True

        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.debug(f"Failed to validate remote config: {e}")
            return False

    def _validate_local_config(self, config_path: Path) -> bool:
        """Validate local configuration integrity.

        Args:
            config_path: Path to config.json file

        Returns:
            True if configuration is valid JSON, False otherwise
        """
        try:
            with open(config_path, "r") as f:
                json.load(f)  # Just check if it's valid JSON

            return True

        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.debug(f"Failed to validate local config: {e}")
            return False
