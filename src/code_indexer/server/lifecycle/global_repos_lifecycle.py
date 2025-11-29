"""
Global Repos Lifecycle Manager for CIDX Server.

Manages the lifecycle of all global repository background services:
- QueryTracker: Reference counting for active queries
- CleanupManager: Automatic deletion of old index versions
- RefreshScheduler: Periodic repository refresh scheduling

Coordinates startup, shutdown, and graceful cleanup of these services.
"""

import logging
from pathlib import Path

from ...global_repos.query_tracker import QueryTracker
from ...global_repos.cleanup_manager import CleanupManager
from ...global_repos.refresh_scheduler import RefreshScheduler
from ...global_repos.shared_operations import GlobalRepoOperations


logger = logging.getLogger(__name__)


class GlobalReposLifecycleManager:
    """
    Lifecycle manager for global repository background services.

    Coordinates the startup and shutdown of:
    - QueryTracker (singleton)
    - CleanupManager (depends on QueryTracker)
    - RefreshScheduler (depends on QueryTracker and CleanupManager)

    Ensures proper initialization order and graceful shutdown.
    """

    def __init__(self, golden_repos_dir: str):
        """
        Initialize the lifecycle manager.

        Args:
            golden_repos_dir: Path to golden repos directory
        """
        self.golden_repos_dir = Path(golden_repos_dir)

        # Ensure directory structure exists
        self.golden_repos_dir.mkdir(parents=True, exist_ok=True)

        # Create singleton QueryTracker
        self.query_tracker = QueryTracker()

        # Create CleanupManager with QueryTracker dependency
        self.cleanup_manager = CleanupManager(
            query_tracker=self.query_tracker,
            check_interval=1.0,  # Check every second
        )

        # Create GlobalRepoOperations for config access
        self.global_ops = GlobalRepoOperations(str(self.golden_repos_dir))

        # Create RefreshScheduler with all dependencies
        self.refresh_scheduler = RefreshScheduler(
            golden_repos_dir=str(self.golden_repos_dir),
            config_source=self.global_ops,
            query_tracker=self.query_tracker,
            cleanup_manager=self.cleanup_manager,
        )

        # Track running state
        self._running = False

        logger.debug(
            f"GlobalReposLifecycleManager initialized for {self.golden_repos_dir}"
        )

    def is_running(self) -> bool:
        """
        Check if lifecycle manager is running.

        Returns:
            True if background services are active
        """
        return self._running

    def start(self) -> None:
        """
        Start all background services.

        Startup order:
        1. CleanupManager (depends on QueryTracker)
        2. RefreshScheduler (depends on QueryTracker and CleanupManager)

        Idempotent: Safe to call multiple times
        """
        if self._running:
            logger.debug("GlobalReposLifecycleManager already running")
            return

        logger.info("Starting global repos background services")

        # Start CleanupManager first
        self.cleanup_manager.start()
        logger.debug("CleanupManager started")

        # Start RefreshScheduler
        self.refresh_scheduler.start()
        logger.debug("RefreshScheduler started")

        self._running = True
        logger.info("Global repos background services started successfully")

    def stop(self) -> None:
        """
        Stop all background services gracefully.

        Shutdown order (reverse of startup):
        1. RefreshScheduler
        2. CleanupManager

        Waits for threads to exit gracefully.

        Idempotent: Safe to call multiple times
        """
        if not self._running:
            logger.debug("GlobalReposLifecycleManager already stopped")
            return

        logger.info("Stopping global repos background services")

        # Stop RefreshScheduler first (reverse order)
        self.refresh_scheduler.stop()
        logger.debug("RefreshScheduler stopped")

        # Stop CleanupManager
        self.cleanup_manager.stop()
        logger.debug("CleanupManager stopped")

        self._running = False
        logger.info("Global repos background services stopped successfully")
