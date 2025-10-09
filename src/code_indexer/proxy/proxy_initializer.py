"""Proxy mode initialization for managing multiple indexed repositories.

This module implements the ProxyInitializer class that creates and manages
proxy mode configurations. A proxy directory serves as a parent container
for multiple indexed repositories, allowing unified management and querying.
"""

import json
import logging
from pathlib import Path
from typing import List, Union

logger = logging.getLogger(__name__)


class ProxyInitializationError(Exception):
    """Raised when proxy initialization fails."""

    pass


class NestedProxyError(Exception):
    """Raised when attempting to create nested proxy configurations."""

    pass


class ProxyInitializer:
    """Handles initialization of proxy mode configurations.

    A proxy configuration creates a parent directory that manages multiple
    indexed repositories. The proxy configuration:
    - Creates .code-indexer/ directory with proxy_mode flag
    - Discovers all subdirectories with .code-indexer/ configurations
    - Stores relative paths to discovered repositories
    - Prevents nested proxy configurations
    """

    def __init__(self, target_dir: Union[str, Path]):
        """Initialize ProxyInitializer with target directory.

        Args:
            target_dir: Directory where proxy configuration will be created.
                       Can be string or Path object.
        """
        if isinstance(target_dir, str):
            self.target_dir = Path(target_dir)
        else:
            self.target_dir = target_dir

    def create_proxy_config(self) -> None:
        """Create proxy configuration directory and config file.

        Creates:
        - .code-indexer/ directory at target location
        - config.json with proxy_mode flag and discovered_repos list

        Raises:
            ProxyInitializationError: If directory already initialized
        """
        config_dir = self.target_dir / ".code-indexer"

        # Check if already initialized
        if config_dir.exists() and (config_dir / "config.json").exists():
            raise ProxyInitializationError(
                f"Directory already initialized as proxy at {self.target_dir}"
            )

        # Create .code-indexer directory
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create initial config with proxy_mode flag
        config_data = {
            "proxy_mode": True,
            "discovered_repos": [],
        }

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Created proxy configuration at {config_dir}")

    def check_nested_proxy(self) -> None:
        """Check for parent proxy configurations to prevent nesting.

        Walks up the directory tree looking for parent directories with
        proxy mode configurations. Nested proxies are prohibited.

        Raises:
            NestedProxyError: If a parent proxy configuration is found
        """
        current = self.target_dir.parent

        # Walk up directory tree checking for proxy configs
        for parent in [current] + list(current.parents):
            config_path = parent / ".code-indexer" / "config.json"

            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config_data = json.load(f)

                    # Check if parent has proxy_mode enabled
                    if config_data.get("proxy_mode") is True:
                        raise NestedProxyError(
                            f"Cannot create nested proxy configuration. "
                            f"Parent proxy found at: {parent}"
                        )
                except json.JSONDecodeError:
                    # Ignore malformed configs
                    logger.warning(f"Malformed config found at {config_path}")
                    continue

    def discover_repositories(self) -> List[str]:
        """Discover all repositories recursively in all subdirectories.

        Searches recursively through all subdirectory levels for .code-indexer/
        directories, indicating indexed repositories. Handles symlinks safely
        to prevent circular reference loops.

        Returns:
            List of relative paths to discovered repositories, sorted alphabetically
        """
        discovered: List[str] = []

        if not self.target_dir.exists():
            return discovered

        # Proxy's own config directory to exclude
        proxy_config_dir = self.target_dir / ".code-indexer"

        # Track visited paths (resolved) to prevent circular symlink loops
        visited_resolved_paths = set()

        # Use rglob to recursively find all .code-indexer directories
        for code_indexer_path in self.target_dir.rglob(".code-indexer"):
            # Skip if not a directory
            if not code_indexer_path.is_dir():
                continue

            # Exclude proxy's own .code-indexer directory
            if code_indexer_path == proxy_config_dir:
                logger.debug(f"Skipping proxy's own config: {code_indexer_path}")
                continue

            # Get the repository directory (parent of .code-indexer)
            repo_dir = code_indexer_path.parent

            # Resolve symlinks to detect circular references
            try:
                resolved_repo_dir = repo_dir.resolve()

                # Check if we've already visited this resolved path
                if resolved_repo_dir in visited_resolved_paths:
                    logger.debug(
                        f"Skipping already visited path (circular symlink): {repo_dir}"
                    )
                    continue

                visited_resolved_paths.add(resolved_repo_dir)

            except (OSError, RuntimeError) as e:
                # Handle broken symlinks or resolution errors
                logger.warning(f"Could not resolve path {repo_dir}: {e}")
                continue

            # Calculate relative path from target_dir to repository
            try:
                relative_path = repo_dir.relative_to(self.target_dir)
                relative_path_str = str(relative_path)

                discovered.append(relative_path_str)
                logger.debug(f"Discovered repository: {relative_path_str}")

            except ValueError:
                # Path is not relative to target_dir (shouldn't happen with rglob)
                logger.warning(f"Path {repo_dir} not relative to {self.target_dir}")
                continue

        logger.info(f"Discovered {len(discovered)} repositories in {self.target_dir}")
        return sorted(discovered)

    def initialize(self, force: bool = False) -> None:
        """Complete proxy initialization workflow.

        Performs the full initialization process:
        1. Check for nested proxy configurations
        2. Create proxy configuration (or overwrite if force=True)
        3. Discover existing repositories
        4. Update config with discovered repositories

        Args:
            force: If True, overwrite existing configuration

        Raises:
            NestedProxyError: If parent proxy exists
            ProxyInitializationError: If already initialized and force=False
        """
        # Step 1: Check for nested proxy (always performed)
        self.check_nested_proxy()

        # Step 2: Create or overwrite config
        config_dir = self.target_dir / ".code-indexer"
        config_file = config_dir / "config.json"

        if config_file.exists() and not force:
            raise ProxyInitializationError(
                f"Directory already initialized as proxy at {self.target_dir}. "
                f"Use force=True to overwrite."
            )

        # Step 3: Create config directory structure
        config_dir.mkdir(parents=True, exist_ok=True)

        # Step 4: Discover repositories
        discovered_repos = self.discover_repositories()

        # Step 5: Write config with discovered repositories
        config_data = {
            "proxy_mode": True,
            "discovered_repos": discovered_repos,
        }

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(
            f"Initialized proxy mode at {self.target_dir} "
            f"with {len(discovered_repos)} repositories"
        )
