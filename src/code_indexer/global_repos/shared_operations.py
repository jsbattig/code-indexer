"""
Shared business logic for global repo operations across all protocols.

Provides consistent operations for CLI, REST, and MCP protocols to ensure
feature parity and eliminate code duplication.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# Default configuration values
DEFAULT_REFRESH_INTERVAL = 3600  # 1 hour in seconds
MINIMUM_REFRESH_INTERVAL = 60  # Minimum 60 seconds


class GlobalRepoOperations:
    """
    Shared business logic for global repository operations.

    Provides consistent operations used by all protocol handlers (CLI, REST, MCP):
    - List global repos
    - Get repo status
    - Get/set global configuration

    Ensures feature parity across all protocols by centralizing business logic.
    """

    def __init__(self, golden_repos_dir: str):
        """
        Initialize global repo operations.

        Args:
            golden_repos_dir: Path to golden repos directory
        """
        # Lazy import to avoid circular dependency (Story #713)
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        self.golden_repos_dir = Path(golden_repos_dir)
        self.config_file = self.golden_repos_dir / "global_config.json"

        # Ensure directory structure exists
        self.golden_repos_dir.mkdir(parents=True, exist_ok=True)

        # Initialize GlobalRegistry for accessing repo data (Story #713 - SQLite backend)
        self.registry = get_server_global_registry(str(self.golden_repos_dir))

    def list_repos(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List all global repositories with API-normalized field names.

        Reuses GlobalRegistry.list_global_repos() to avoid code duplication.
        Normalizes field names for protocol parity (CLI/REST/MCP).

        Args:
            filters: Optional filters for future use (not currently implemented)

        Returns:
            List of repository metadata dicts with fields:
            - repo_name: Repository name
            - alias: Global alias name (normalized from alias_name)
            - url: Git repository URL or None for meta-directory (normalized from repo_url)
            - last_refresh: ISO timestamp of last refresh
        """
        # Get repos from registry
        repos = self.registry.list_global_repos()

        # Apply filters if provided (placeholder for future functionality)
        if filters:
            # Future: Apply filtering logic here
            pass

        # Normalize field names for protocol parity
        normalized = []
        for repo in repos:
            normalized.append(
                {
                    "alias": repo.get("alias_name"),  # alias_name → alias
                    "repo_name": repo.get("repo_name"),
                    "url": repo.get("repo_url"),  # repo_url → url
                    "last_refresh": repo.get("last_refresh"),
                }
            )

        return normalized

    def get_status(self, alias: str) -> Dict[str, Any]:
        """
        Get detailed status of a specific global repository with API-normalized field names.

        Args:
            alias: Global repository alias name

        Returns:
            Repository status dict with fields:
            - alias: Global alias name (normalized from alias_name)
            - repo_name: Repository name
            - url: Git repository URL (normalized from repo_url)
            - last_refresh: ISO timestamp of last refresh
            - enable_temporal: Whether temporal indexing is enabled

        Raises:
            ValueError: If repository alias not found
        """
        # Get repo from registry
        repo = self.registry.get_global_repo(alias)

        if repo is None:
            raise ValueError(
                f"Global repo '{alias}' not found. "
                f"Run 'cidx global list' to see available repos."
            )

        # Normalize field names for protocol parity
        return {
            "alias": repo.get("alias_name"),  # alias_name → alias
            "repo_name": repo.get("repo_name"),
            "url": repo.get("repo_url"),  # repo_url → url
            "last_refresh": repo.get("last_refresh"),
            "enable_temporal": repo.get(
                "enable_temporal", False
            ),  # Default to False for legacy repos
        }

    def get_config(self) -> Dict[str, Any]:
        """
        Get global configuration.

        Returns:
            Configuration dict with fields:
            - refresh_interval: Refresh interval in seconds

        Creates default config file if it doesn't exist.
        Handles corrupted config files by returning defaults.
        """
        # Check if config file exists
        if not self.config_file.exists():
            # Create default config
            default_config = {"refresh_interval": DEFAULT_REFRESH_INTERVAL}
            self._save_config(default_config)
            return default_config

        # Load config from file
        try:
            with open(self.config_file, "r") as f:
                config = json.load(f)

            # Validate config has required fields
            if "refresh_interval" not in config:
                logger.warning("Config missing refresh_interval, using default")
                config["refresh_interval"] = DEFAULT_REFRESH_INTERVAL

            return dict(config)

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load config file, using defaults: {e}")
            # Return default config
            return {"refresh_interval": DEFAULT_REFRESH_INTERVAL}

    def set_config(self, refresh_interval: int) -> None:
        """
        Update global configuration.

        Args:
            refresh_interval: Refresh interval in seconds (minimum 60)

        Raises:
            ValueError: If refresh_interval < 60 seconds

        Uses atomic write pattern to prevent corruption:
        1. Write to temporary file
        2. Sync to disk
        3. Atomic rename over existing file
        """
        # Validate refresh interval
        if refresh_interval < MINIMUM_REFRESH_INTERVAL:
            raise ValueError(
                f"Refresh interval must be at least {MINIMUM_REFRESH_INTERVAL} seconds. "
                f"Got: {refresh_interval} seconds."
            )

        # Create config dict
        config = {"refresh_interval": refresh_interval}

        # Save with atomic write
        self._save_config(config)

        logger.info(f"Updated global config: refresh_interval={refresh_interval}s")

    def _save_config(self, config: Dict[str, Any]) -> None:
        """
        Save configuration with atomic write.

        Uses atomic write pattern to prevent corruption:
        1. Write to temporary file
        2. Sync to disk
        3. Atomic rename over existing file

        Args:
            config: Configuration dict to save

        Raises:
            RuntimeError: If save fails
        """
        # Write to temporary file first
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.golden_repos_dir), prefix=".global_config_", suffix=".tmp"
        )

        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            os.replace(tmp_path, str(self.config_file))
            logger.debug("Global config saved atomically")

        except Exception as e:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise RuntimeError(f"Failed to save global config: {e}")
