"""
Meta-Directory Updater - Update strategy for meta-directory.

Implements UpdateStrategy interface for the special meta-directory
that contains AI-generated descriptions of all registered repositories.
"""

import logging
from pathlib import Path
from typing import Set

from .update_strategy import UpdateStrategy
from .global_registry import GlobalRegistry
from .repo_analyzer import RepoAnalyzer
from .description_generator import DescriptionGenerator


logger = logging.getLogger(__name__)


class MetaDirectoryUpdater(UpdateStrategy):
    """
    Update strategy for meta-directory.

    Scans registered repos and generates/updates description files
    for semantic search discovery. Handles incremental updates by
    detecting new, modified, and deleted repositories.
    """

    def __init__(self, meta_dir: str, registry: GlobalRegistry):
        """
        Initialize the meta-directory updater.

        Args:
            meta_dir: Path to meta-directory where descriptions are stored
            registry: GlobalRegistry instance for accessing repo metadata
        """
        self.meta_dir = Path(meta_dir)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.generator = DescriptionGenerator(str(meta_dir))

    def has_changes(self) -> bool:
        """
        Check if there are changes requiring update.

        Detects:
        - New repos (registered but no description file)
        - Deleted repos (description file but no registration)
        - Modified repos (repo modified after description file)

        Returns:
            True if changes detected, False otherwise
        """
        current_repos = self._get_current_repo_names()
        described_repos = self._get_described_repo_names()

        # New repos or deleted repos
        if current_repos != described_repos:
            logger.debug(
                f"Changes detected: current={len(current_repos)}, "
                f"described={len(described_repos)}"
            )
            return True

        # Check for modified repos (timestamp comparison)
        for repo_name in current_repos:
            if self._is_repo_modified(repo_name):
                logger.debug(f"Modified repo detected: {repo_name}")
                return True

        return False

    def update(self) -> None:
        """
        Update the meta-directory.

        Creates/updates description files for all registered repos
        and removes orphaned description files.
        """
        current_repos = self._get_current_repo_names()
        described_repos = self._get_described_repo_names()

        # Remove orphaned descriptions
        orphaned = described_repos - current_repos
        for repo_name in orphaned:
            desc_file = self.meta_dir / f"{repo_name}.md"
            if desc_file.exists():
                desc_file.unlink()
                logger.info(f"Removed orphaned description: {repo_name}.md")

        # Create/update descriptions for current repos
        for repo_name in current_repos:
            self._create_or_update_description(repo_name)

        logger.info(f"Meta-directory update complete: {len(current_repos)} repos")

    def get_source_path(self) -> str:
        """
        Get the path to the meta-directory.

        Returns:
            Absolute path to meta-directory
        """
        return str(self.meta_dir)

    def _get_current_repo_names(self) -> Set[str]:
        """
        Get names of all currently registered repos.

        Excludes the meta-directory itself (repo_url=None).

        Returns:
            Set of repository names
        """
        repo_names = set()
        for repo in self.registry.list_global_repos():
            # Skip meta-directory itself
            if repo.get("repo_url") is None:
                continue

            repo_names.add(repo["repo_name"])

        return repo_names

    def _get_described_repo_names(self) -> Set[str]:
        """
        Get names of repos with description files.

        Returns:
            Set of repository names
        """
        if not self.meta_dir.exists():
            return set()

        repo_names = set()
        for desc_file in self.meta_dir.glob("*.md"):
            repo_names.add(desc_file.stem)

        return repo_names

    def _create_or_update_description(self, repo_name: str) -> None:
        """
        Create or update description file for a repository.

        Args:
            repo_name: Name of the repository
        """
        # Find repo in registry
        repo = self._find_repo_by_name(repo_name)
        if not repo:
            logger.warning(f"Repository not found in registry: {repo_name}")
            return

        # Get index_path and extract source directory
        index_path = repo.get("index_path")
        if not index_path:
            logger.warning(f"No index_path for repo: {repo_name}")
            return

        # index_path contains the repository root directly
        repo_path = Path(index_path)

        try:
            analyzer = RepoAnalyzer(str(repo_path))
            info = analyzer.extract_info()

            # Generate description file
            self.generator.create_description(
                repo_name=repo_name,
                repo_url=repo.get("repo_url", ""),
                description=info.summary,
                technologies=info.technologies,
                purpose=info.purpose,
                features=info.features,
                use_cases=info.use_cases,
            )

            logger.debug(f"Generated description for: {repo_name}")

        except Exception as e:
            logger.error(f"Failed to generate description for {repo_name}: {e}")

    def _find_repo_by_name(self, repo_name: str):
        """
        Find repository metadata by name.

        Args:
            repo_name: Name of the repository

        Returns:
            Repository metadata dict or None if not found
        """
        for repo in self.registry.list_global_repos():
            if repo.get("repo_name") == repo_name:
                return repo
        return None

    def _is_repo_modified(self, repo_name: str) -> bool:
        """
        Check if repository has been modified since description was generated.

        Compares modification times of the repository directory and its
        description file.

        Args:
            repo_name: Name of the repository

        Returns:
            True if repo modified after description, False otherwise
        """
        # Get description file
        desc_file = self.meta_dir / f"{repo_name}.md"
        if not desc_file.exists():
            # No description file means it's a new repo (handled elsewhere)
            return False

        # Get repository metadata
        repo = self._find_repo_by_name(repo_name)
        if not repo:
            return False

        index_path = repo.get("index_path", "")
        if not index_path:
            return False

        # index_path contains the repository root directly
        repo_path = Path(index_path)
        if not repo_path.exists():
            return False

        # Get modification times
        desc_mtime = desc_file.stat().st_mtime
        repo_mtime = self._get_repo_mtime(repo_path)

        # Repo is modified if any file in it is newer than description
        return repo_mtime > desc_mtime

    def _get_repo_mtime(self, repo_path: Path) -> float:
        """
        Get the most recent modification time in a repository.

        Args:
            repo_path: Path to repository directory

        Returns:
            Most recent modification timestamp
        """
        if not repo_path.is_dir():
            return repo_path.stat().st_mtime

        max_mtime = repo_path.stat().st_mtime

        # Check all files recursively
        for item in repo_path.rglob("*"):
            try:
                item_mtime = item.stat().st_mtime
                if item_mtime > max_mtime:
                    max_mtime = item_mtime
            except (OSError, PermissionError):
                # Skip files we can't access
                continue

        return max_mtime
