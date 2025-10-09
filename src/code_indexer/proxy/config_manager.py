"""Proxy configuration management for Code Indexer.

This module provides the ProxyConfigManager class for managing proxy mode
configurations, including loading, validating, and manipulating repository lists.
"""

import logging
from pathlib import Path
from typing import List, Union

from ..config import Config, ConfigManager
from .proxy_initializer import ProxyInitializer

logger = logging.getLogger(__name__)


class ProxyConfigError(Exception):
    """Raised when proxy configuration operations fail."""

    pass


class InvalidRepositoryError(Exception):
    """Raised when repository validation fails."""

    pass


class ProxyConfigManager:
    """Manages proxy mode configurations and repository lists.

    Provides methods for:
    - Loading and validating proxy configurations
    - Adding/removing repositories
    - Refreshing repository discovery
    - Validating repository paths
    """

    def __init__(self, proxy_root: Union[str, Path]):
        """Initialize ProxyConfigManager with proxy root directory.

        Args:
            proxy_root: Root directory of the proxy configuration.
                       Can be string or Path object.
        """
        if isinstance(proxy_root, str):
            self.proxy_root = Path(proxy_root)
        else:
            self.proxy_root = proxy_root

        self.config_path = self.proxy_root / ".code-indexer" / "config.json"
        self._config_manager = ConfigManager(self.config_path)

    def load_config(self) -> Config:
        """Load proxy configuration from disk.

        Returns:
            Config object with proxy_mode and discovered_repos

        Raises:
            ProxyConfigError: If config not found or not in proxy mode
        """
        if not self.config_path.exists():
            raise ProxyConfigError(
                f"Proxy configuration not found at {self.config_path}"
            )

        config = self._config_manager.load()

        if not config.proxy_mode:
            raise ProxyConfigError(
                f"Directory at {self.proxy_root} is not a proxy configuration. "
                f"proxy_mode must be True."
            )

        return config

    def validate_repositories(self, config: Config) -> None:
        """Validate all repositories in discovered_repos list.

        Checks that:
        - Each repository path exists
        - Each has a .code-indexer directory
        - Paths don't escape proxy root

        Args:
            config: Config object to validate

        Raises:
            InvalidRepositoryError: If validation fails for any repository
        """
        for repo_path_str in config.discovered_repos:
            repo_path = self.proxy_root / repo_path_str

            # Check if path escapes proxy root
            try:
                resolved_repo = repo_path.resolve()
                resolved_root = self.proxy_root.resolve()

                if not str(resolved_repo).startswith(str(resolved_root)):
                    raise InvalidRepositoryError(
                        f"Repository path '{repo_path_str}' escapes outside proxy root"
                    )
            except (OSError, RuntimeError) as e:
                raise InvalidRepositoryError(
                    f"Failed to resolve repository path '{repo_path_str}': {e}"
                )

            # Check repository exists
            if not repo_path.exists():
                raise InvalidRepositoryError(
                    f"Repository path does not exist: {repo_path_str}"
                )

            # Check .code-indexer directory exists
            code_indexer_dir = repo_path / ".code-indexer"
            if not code_indexer_dir.exists():
                raise InvalidRepositoryError(
                    f"Repository '{repo_path_str}' missing .code-indexer directory"
                )

    def add_repository(self, repo_path: str) -> None:
        """Add repository to discovered_repos list.

        Validates repository before adding and prevents duplicates.

        Args:
            repo_path: Relative path to repository from proxy root

        Raises:
            InvalidRepositoryError: If validation fails or duplicate
        """
        config = self.load_config()

        # Check for duplicate
        if repo_path in config.discovered_repos:
            raise InvalidRepositoryError(
                f"Repository '{repo_path}' already exists in discovered_repos"
            )

        # Validate repository exists and has .code-indexer
        full_path = self.proxy_root / repo_path

        if not full_path.exists():
            raise InvalidRepositoryError(
                f"Repository path does not exist: {repo_path}"
            )

        code_indexer_dir = full_path / ".code-indexer"
        if not code_indexer_dir.exists():
            raise InvalidRepositoryError(
                f"Repository '{repo_path}' missing .code-indexer directory"
            )

        # Add to list and save
        config.discovered_repos.append(repo_path)
        self._config_manager.save(config)

        logger.info(f"Added repository to proxy: {repo_path}")

    def remove_repository(self, repo_path: str) -> None:
        """Remove repository from discovered_repos list.

        Args:
            repo_path: Relative path to repository to remove

        Raises:
            InvalidRepositoryError: If repository not in list
        """
        config = self.load_config()

        if repo_path not in config.discovered_repos:
            raise InvalidRepositoryError(
                f"Repository '{repo_path}' not found in discovered_repos"
            )

        # Remove from list and save
        config.discovered_repos.remove(repo_path)
        self._config_manager.save(config)

        logger.info(f"Removed repository from proxy: {repo_path}")

    def refresh_repositories(self) -> None:
        """Refresh discovered_repos list by rediscovering all repositories.

        Uses ProxyInitializer discovery logic to find all repositories
        recursively and updates the configuration.
        """
        config = self.load_config()

        # Use ProxyInitializer to discover repositories
        initializer = ProxyInitializer(self.proxy_root)
        discovered_repos = initializer.discover_repositories()

        # Update config with fresh discovery
        config.discovered_repos = discovered_repos
        self._config_manager.save(config)

        logger.info(
            f"Refreshed proxy repositories: {len(discovered_repos)} repositories found"
        )

    def get_repositories(self) -> List[str]:
        """Get current list of discovered repositories.

        Returns:
            Copy of discovered_repos list (prevents external modification)
        """
        config = self.load_config()
        return config.discovered_repos.copy()
