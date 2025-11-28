"""
Startup Meta-Directory Populator for CIDX Server.

Automatically populates the meta-directory with repository descriptions
on server startup, ensuring users can immediately query for repositories.
"""

import logging
from pathlib import Path
from typing import Dict, Any

from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.global_repos.meta_directory_updater import MetaDirectoryUpdater


logger = logging.getLogger(__name__)


class StartupMetaPopulationError(Exception):
    """Exception raised during startup meta-directory population."""

    pass


class StartupMetaPopulator:
    """
    Populates meta-directory on server startup.

    Ensures that all registered repositories have description files
    generated in the meta-directory for semantic search discovery.
    """

    def __init__(
        self, meta_dir: str, golden_repos_dir: str, registry: GlobalRegistry
    ):
        """
        Initialize the startup meta populator.

        Args:
            meta_dir: Path to meta-directory where descriptions are stored
            golden_repos_dir: Path to golden repos directory
            registry: GlobalRegistry instance for accessing repo metadata
        """
        self.meta_dir = Path(meta_dir)
        self.golden_repos_dir = Path(golden_repos_dir)
        self.registry = registry

    def populate_on_startup(self) -> Dict[str, Any]:
        """
        Populate meta-directory on server startup.

        Checks for registered repositories and generates missing description
        files. Handles errors gracefully to avoid blocking server startup.

        Returns:
            Dictionary with population results:
            - populated: bool - Whether population was performed
            - repos_processed: int - Number of repos processed
            - message: str - Status message
            - error: str (optional) - Error message if population failed
        """
        try:
            # Ensure meta-directory exists
            self.meta_dir.mkdir(parents=True, exist_ok=True)

            # Get all registered repos (excluding meta-directory itself)
            all_repos = self.registry.list_global_repos()
            non_meta_repos = [r for r in all_repos if r.get("repo_url") is not None]

            # If no repos registered, skip population
            if not non_meta_repos:
                logger.info("No repositories registered, skipping meta-directory population")
                return {
                    "populated": False,
                    "repos_processed": 0,
                    "message": "No repositories to populate",
                }

            # Create updater instance
            updater = MetaDirectoryUpdater(
                meta_dir=str(self.meta_dir), registry=self.registry
            )

            # Check if there are changes that need updating
            if not updater.has_changes():
                logger.info("Meta-directory is up to date, no population needed")
                return {
                    "populated": False,
                    "repos_processed": 0,
                    "message": "Meta-directory is up to date",
                }

            # Perform update (generates/updates description files)
            logger.info(
                f"Populating meta-directory with {len(non_meta_repos)} repositories"
            )
            updater.update()

            logger.info(
                f"Meta-directory population complete: {len(non_meta_repos)} repos processed"
            )

            return {
                "populated": True,
                "repos_processed": len(non_meta_repos),
                "message": f"Meta-directory populated with {len(non_meta_repos)} repositories",
            }

        except Exception as e:
            # Log error but don't block server startup
            error_msg = f"Failed to populate meta-directory: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return {
                "populated": False,
                "repos_processed": 0,
                "message": "Meta-directory population failed",
                "error": str(e),
            }
