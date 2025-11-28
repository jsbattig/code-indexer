"""
Meta-Directory Initializer for first-time setup and migration.

Handles creation of meta-directory and batch generation of
descriptions for all existing repositories.
"""

import logging
from pathlib import Path

from .global_registry import GlobalRegistry
from .meta_directory_updater import MetaDirectoryUpdater


logger = logging.getLogger(__name__)


class MetaDirectoryInitializer:
    """
    Initializes meta-directory and performs migration.

    Creates the meta-directory, registers it as a special global repo,
    and generates descriptions for all existing repositories.
    """

    META_DIR_NAME = "cidx-meta"
    META_ALIAS_NAME = "cidx-meta-global"

    def __init__(self, golden_repos_dir: str, registry: GlobalRegistry):
        """
        Initialize the meta-directory initializer.

        Args:
            golden_repos_dir: Path to golden repos directory
            registry: GlobalRegistry instance
        """
        self.golden_repos_dir = Path(golden_repos_dir)
        self.registry = registry
        self.meta_dir = self.golden_repos_dir / self.META_DIR_NAME

    def initialize(self) -> Path:
        """
        Initialize meta-directory and perform migration.

        Creates meta-directory, registers it, and generates descriptions
        for all existing repositories.

        Returns:
            Path to the created meta-directory
        """
        # Create meta-directory
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Meta-directory created: {self.meta_dir}")

        # Register meta-directory as special global repo
        self._register_meta_directory()

        # Perform migration - generate descriptions for all existing repos
        self._migrate_existing_repos()

        logger.info(f"Meta-directory initialization complete: {self.meta_dir}")

        return self.meta_dir

    def _register_meta_directory(self) -> None:
        """
        Register meta-directory as a special global repo.

        Uses repo_url=None as marker for special handling.
        Creates alias pointer for query resolution.
        """
        # Check if already registered
        existing = self.registry.get_global_repo(self.META_ALIAS_NAME)
        if existing:
            logger.debug("Meta-directory already registered")
            return

        # Create alias pointer file (for --repo flag resolution)
        from .alias_manager import AliasManager

        aliases_dir = self.golden_repos_dir / "aliases"
        alias_manager = AliasManager(str(aliases_dir))

        alias_manager.create_alias(
            alias_name=self.META_ALIAS_NAME,
            target_path=str(self.meta_dir),
            repo_name=self.META_DIR_NAME,
        )

        # Register with repo_url=None marker and allow_reserved=True
        self.registry.register_global_repo(
            repo_name=self.META_DIR_NAME,
            alias_name=self.META_ALIAS_NAME,
            repo_url=None,  # Special marker
            index_path=str(self.meta_dir),
            allow_reserved=True,  # Meta-directory can use reserved name
        )

        logger.info(f"Registered meta-directory: {self.META_ALIAS_NAME}")

    def _migrate_existing_repos(self) -> None:
        """
        Migrate existing repos by generating descriptions.

        Uses MetaDirectoryUpdater to batch-generate descriptions
        for all currently registered repositories.
        """
        # Create updater
        updater = MetaDirectoryUpdater(
            meta_dir=str(self.meta_dir), registry=self.registry
        )

        # Count existing repos (excluding meta-directory)
        all_repos = self.registry.list_global_repos()
        non_meta_repos = [r for r in all_repos if r.get("repo_url") is not None]

        if not non_meta_repos:
            logger.info("No existing repos to migrate")
            return

        logger.info(f"Migrating {len(non_meta_repos)} existing repos to meta-directory")

        # Run update to generate descriptions
        updater.update()

        logger.info(f"Migration complete: {len(non_meta_repos)} repos processed")
