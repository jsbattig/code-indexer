"""
Refresh Scheduler for timer-triggered global repo updates.

Orchestrates the complete refresh cycle: timer triggers git pull,
change detection, index creation, alias swap, and cleanup scheduling.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from code_indexer.config import ConfigManager
from .alias_manager import AliasManager
from .global_registry import GlobalRegistry
from .git_pull_updater import GitPullUpdater
from .meta_directory_updater import MetaDirectoryUpdater
from .query_tracker import QueryTracker
from .cleanup_manager import CleanupManager
from .shared_operations import GlobalRepoOperations


logger = logging.getLogger(__name__)


class RefreshScheduler:
    """
    Timer-based scheduler for refreshing global repositories.

    Manages periodic refresh cycles for all registered global repos,
    coordinating git pulls, indexing, alias swaps, and cleanup.
    """

    def __init__(
        self,
        golden_repos_dir: str,
        config_source: Union[ConfigManager, GlobalRepoOperations],
        query_tracker: QueryTracker,
        cleanup_manager: CleanupManager,
    ):
        """
        Initialize the refresh scheduler.

        Args:
            golden_repos_dir: Path to golden repos directory
            config_source: Configuration source (ConfigManager for CLI, GlobalRepoOperations for server)
            query_tracker: Query tracker for reference counting
            cleanup_manager: Cleanup manager for old index removal
        """
        self.golden_repos_dir = Path(golden_repos_dir)
        self.config_source = config_source
        self.query_tracker = query_tracker
        self.cleanup_manager = cleanup_manager

        # Initialize managers
        self.alias_manager = AliasManager(str(self.golden_repos_dir / "aliases"))
        self.registry = GlobalRegistry(str(self.golden_repos_dir))

        # Thread management
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def get_refresh_interval(self) -> int:
        """
        Get the configured refresh interval.

        Returns:
            Refresh interval in seconds
        """
        # Support both ConfigManager (CLI) and GlobalRepoOperations (server)
        if isinstance(self.config_source, GlobalRepoOperations):
            config = self.config_source.get_config()
            return config["refresh_interval"]
        else:
            # ConfigManager (CLI)
            return self.config_source.get_global_refresh_interval()

    def is_running(self) -> bool:
        """
        Check if scheduler is running.

        Returns:
            True if background thread is active
        """
        return self._running

    def start(self) -> None:
        """
        Start the refresh scheduler background thread.

        Idempotent: Safe to call multiple times
        """
        if self._running:
            logger.debug("Refresh scheduler already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("Refresh scheduler started")

    def stop(self) -> None:
        """
        Stop the refresh scheduler background thread.

        Waits for thread to exit gracefully.

        Idempotent: Safe to call multiple times
        """
        if not self._running:
            logger.debug("Refresh scheduler already stopped")
            return

        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Refresh scheduler stopped")

    def _scheduler_loop(self) -> None:
        """
        Background thread loop for scheduled refreshes.

        Checks all registered global repos at configured interval
        and triggers refreshes.
        """
        logger.debug("Refresh scheduler loop started")

        while self._running:
            try:
                # Get all registered global repos
                repos = self.registry.list_global_repos()

                for repo in repos:
                    if not self._running:
                        break

                    alias_name = repo.get("alias_name")
                    if alias_name:
                        try:
                            self.refresh_repo(alias_name)
                        except Exception as e:
                            logger.error(
                                f"Refresh failed for {alias_name}: {e}", exc_info=True
                            )

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            # Sleep in small increments to allow faster shutdown
            interval = self.get_refresh_interval()
            sleep_remaining = interval
            while sleep_remaining > 0 and self._running:
                sleep_chunk = min(1.0, sleep_remaining)
                time.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk

        logger.debug("Refresh scheduler loop exited")

    def refresh_repo(self, alias_name: str) -> None:
        """
        Refresh a single global repository.

        Orchestrates the complete refresh cycle:
        1. Git pull (via updater)
        2. Change detection
        3. New index creation (if changes)
        4. Alias swap
        5. Cleanup scheduling

        Args:
            alias_name: Global alias name (e.g., "my-repo-global")

        Raises:
            Exception: If refresh fails (logged, not propagated by scheduler loop)
        """
        try:
            logger.info(f"Starting refresh for {alias_name}")

            # Get current alias target
            current_target = self.alias_manager.read_alias(alias_name)
            if not current_target:
                logger.warning(f"Alias {alias_name} not found, skipping refresh")
                return

            # Get repo info from registry
            repo_info = self.registry.get_global_repo(alias_name)
            if not repo_info:
                logger.warning(f"Repo {alias_name} not in registry, skipping refresh")
                return

            # Get source path (golden repo clone)
            # For now, use current_target as source path
            # (In full implementation, this would be the golden repo path)
            source_path = current_target

            # Create updater for this repo
            # Meta-directory (repo_url=None) uses MetaDirectoryUpdater
            # Normal repos use GitPullUpdater
            if repo_info.get("repo_url") is None:
                updater = MetaDirectoryUpdater(source_path, self.registry)
            else:
                updater = GitPullUpdater(source_path)

            # Check for changes
            has_changes = updater.has_changes()

            if not has_changes:
                logger.info(f"No changes detected for {alias_name}, skipping refresh")
                return

            # Pull latest changes
            logger.info(f"Pulling latest changes for {alias_name}")
            updater.update()

            # Create new versioned index
            new_index_path = self._create_new_index(
                alias_name=alias_name, source_path=updater.get_source_path()
            )

            # Swap alias to new index
            logger.info(f"Swapping alias {alias_name} to new index")
            self.alias_manager.swap_alias(
                alias_name=alias_name,
                new_target=new_index_path,
                old_target=current_target,
            )

            # Schedule cleanup of old index
            logger.info(f"Scheduling cleanup of old index: {current_target}")
            self.cleanup_manager.schedule_cleanup(current_target)

            # Update registry timestamp
            self.registry.update_refresh_timestamp(alias_name)

            logger.info(f"Refresh complete for {alias_name}")

        except Exception as e:
            logger.error(f"Refresh failed for {alias_name}: {e}", exc_info=True)
            # Don't re-raise - scheduler loop should continue

    def _create_new_index(self, alias_name: str, source_path: str) -> str:
        """
        Create a new versioned index directory.

        In full implementation, this would:
        1. Create v_TIMESTAMP directory
        2. Clone from source using CoW
        3. Run indexing

        For now, this is a placeholder that returns a path.

        Args:
            alias_name: Global alias name
            source_path: Path to source repository

        Returns:
            Path to new index directory
        """
        # Generate version timestamp
        timestamp = int(datetime.utcnow().timestamp())
        version = f"v_{timestamp}"

        # Create versioned directory path
        repo_name = alias_name.replace("-global", "")
        versioned_path = self.golden_repos_dir / repo_name / version

        # In full implementation, this would:
        # - Create directory
        # - CoW clone from source
        # - Run indexing
        # For now, just return the path
        logger.info(
            f"Would create new index at: {versioned_path} "
            f"(placeholder - full implementation needed)"
        )

        return str(versioned_path)
