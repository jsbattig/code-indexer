"""
Refresh Scheduler for timer-triggered global repo updates.

Orchestrates the complete refresh cycle: timer triggers git pull,
change detection, index creation, alias swap, and cleanup scheduling.
"""

import logging
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union, TYPE_CHECKING, cast

from code_indexer.config import ConfigManager
from .alias_manager import AliasManager
from .git_pull_updater import GitPullUpdater
from .query_tracker import QueryTracker
from .cleanup_manager import CleanupManager
from .shared_operations import GlobalRepoOperations

if TYPE_CHECKING:
    from code_indexer.server.utils.config_manager import ServerResourceConfig
    from code_indexer.server.repositories.background_jobs import BackgroundJobManager

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
        resource_config: Optional["ServerResourceConfig"] = None,
        background_job_manager: Optional["BackgroundJobManager"] = None,
    ):
        """
        Initialize the refresh scheduler.

        Args:
            golden_repos_dir: Path to golden repos directory
            config_source: Configuration source (ConfigManager for CLI, GlobalRepoOperations for server)
            query_tracker: Query tracker for reference counting
            cleanup_manager: Cleanup manager for old index removal
            resource_config: Optional resource configuration for timeouts (server mode)
            background_job_manager: Optional job manager for dashboard visibility (server mode)
        """
        # Lazy import to avoid circular dependency (Story #713)
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        self.golden_repos_dir = Path(golden_repos_dir)
        self.config_source = config_source
        self.query_tracker = query_tracker
        self.cleanup_manager = cleanup_manager
        self.resource_config = resource_config
        self.background_job_manager = background_job_manager

        # Initialize managers
        self.alias_manager = AliasManager(str(self.golden_repos_dir / "aliases"))
        self.registry = get_server_global_registry(str(self.golden_repos_dir))

        # Thread management
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()  # Event-based signaling for efficient stop

        # Per-repo locking for concurrent refresh serialization
        self._repo_locks: dict[str, threading.Lock] = {}
        self._repo_locks_lock = threading.Lock()  # Protects _repo_locks dict

    def _get_repo_lock(self, alias_name: str) -> threading.Lock:
        """
        Get or create a lock for a specific repository.

        Thread-safe method to retrieve existing lock or create new one.

        Args:
            alias_name: Repository alias name

        Returns:
            Lock instance for the specified repository
        """
        with self._repo_locks_lock:
            if alias_name not in self._repo_locks:
                self._repo_locks[alias_name] = threading.Lock()
            return self._repo_locks[alias_name]

    def get_refresh_interval(self) -> int:
        """
        Get the configured refresh interval.

        Returns:
            Refresh interval in seconds
        """
        # Support both ConfigManager (CLI) and GlobalRepoOperations (server)
        if isinstance(self.config_source, GlobalRepoOperations):
            config = self.config_source.get_config()
            return cast(int, config["refresh_interval"])
        else:
            # ConfigManager (CLI)
            return cast(int, self.config_source.get_global_refresh_interval())

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
        self._stop_event.clear()  # Reset event for new start
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
        self._stop_event.set()  # Signal scheduler loop to exit immediately

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
                            self._submit_refresh_job(alias_name)
                        except Exception as e:
                            logger.error(
                                f"Refresh failed for {alias_name}: {e}", exc_info=True
                            )

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            # Wait using Event.wait() for interruptible sleep
            # Event.wait() returns True if event is set, False on timeout
            interval = self.get_refresh_interval()
            self._stop_event.wait(timeout=interval)

        logger.debug("Refresh scheduler loop exited")

    def _submit_refresh_job(self, alias_name: str) -> Optional[str]:
        """
        Submit a refresh job to BackgroundJobManager.

        If no BackgroundJobManager is configured (CLI mode), falls back to
        direct execution via _execute_refresh().

        Args:
            alias_name: Global alias name (e.g., "my-repo-global")

        Returns:
            Job ID if submitted to BackgroundJobManager, None if executed directly
        """
        if not self.background_job_manager:
            # Fallback to direct execution if no job manager (CLI mode)
            self._execute_refresh(alias_name)
            return None

        job_id: str = self.background_job_manager.submit_job(
            operation_type="global_repo_refresh",
            func=lambda: self._execute_refresh(alias_name),
            submitter_username="system",
            is_admin=True,
            repo_alias=alias_name,
        )
        logger.info(f"Submitted refresh job {job_id} for {alias_name}")
        return job_id

    def refresh_repo(self, alias_name: str) -> None:
        """
        Public API for manual refresh (backwards compatibility).

        Delegates to _execute_refresh() for the actual work.

        Args:
            alias_name: Global alias name (e.g., "my-repo-global")
        """
        self._execute_refresh(alias_name)

    def _execute_refresh(self, alias_name: str) -> Dict[str, Any]:
        """
        Execute refresh for a repository (called by BackgroundJobManager).

        Orchestrates the complete refresh cycle:
        1. Git pull (via updater)
        2. Change detection
        3. New index creation (if changes)
        4. Alias swap
        5. Cleanup scheduling

        Per-repo locking ensures concurrent refresh attempts on the same repo
        are serialized, while different repos can refresh in parallel.

        Args:
            alias_name: Global alias name (e.g., "my-repo-global")

        Returns:
            Dict with success status and details for BackgroundJobManager tracking
        """
        # Acquire per-repo lock to serialize concurrent refresh attempts
        repo_lock = self._get_repo_lock(alias_name)

        with repo_lock:
            try:
                logger.info(f"Starting refresh for {alias_name}")

                # Get current alias target
                current_target = self.alias_manager.read_alias(alias_name)
                if not current_target:
                    logger.warning(f"Alias {alias_name} not found, skipping refresh")
                    return {
                        "success": True,
                        "alias": alias_name,
                        "message": "Alias not found, skipped",
                    }

                # Get repo info from registry
                repo_info = self.registry.get_global_repo(alias_name)
                if not repo_info:
                    logger.warning(
                        f"Repo {alias_name} not in registry, skipping refresh"
                    )
                    return {
                        "success": True,
                        "alias": alias_name,
                        "message": "Repo not in registry, skipped",
                    }

                # Get golden repo path from alias (registry path becomes stale after refresh)
                golden_repo_path = current_target

                # Skip refresh for local:// repos (no remote = no refresh = no versioning)
                repo_url = repo_info.get("repo_url")
                if repo_url and repo_url.startswith("local://"):
                    logger.info(
                        f"Skipping refresh for local repo: {alias_name} ({repo_url})"
                    )
                    return {
                        "success": True,
                        "alias": alias_name,
                        "message": "Local repo, skipped",
                    }

                # Create updater for this repo
                updater = GitPullUpdater(golden_repo_path)

                # Check for changes
                has_changes = updater.has_changes()

                if not has_changes:
                    logger.info(
                        f"No changes detected for {alias_name}, skipping refresh"
                    )
                    return {
                        "success": True,
                        "alias": alias_name,
                        "message": "No changes detected",
                    }

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
                return {
                    "success": True,
                    "alias": alias_name,
                    "message": "Refresh complete",
                }

            except Exception as e:
                logger.error(f"Refresh failed for {alias_name}: {e}", exc_info=True)
                # Return failure result instead of raising
                return {
                    "success": False,
                    "alias": alias_name,
                    "message": f"Refresh failed: {e}",
                    "error": str(e),
                }

    def _create_new_index(self, alias_name: str, source_path: str) -> str:
        """
        Create a new versioned index directory with CoW clone and indexing.

        Complete workflow:
        1. Create .versioned/{repo_name}/v_{timestamp}/ directory structure
        2. Perform CoW clone using cp --reflink=auto -r
        3. Fix git status (git update-index --refresh, git restore .)
        4. Run cidx fix-config --force
        5. Run cidx index to create indexes
        6. Validate index exists before returning
        7. Return path only if validation passes

        Args:
            alias_name: Global alias name (e.g., "my-repo-global")
            source_path: Path to source repository (golden repo)

        Returns:
            Path to new index directory (only if validation passes)

        Raises:
            RuntimeError: If any step fails (with cleanup of partial artifacts)
        """
        # Get timeouts from resource config or use defaults
        cow_timeout = 600  # Default: 10 minutes
        git_update_timeout = 300  # Default: 5 minutes
        git_restore_timeout = 300  # Default: 5 minutes
        cidx_fix_timeout = 60  # Default: 1 minute
        cidx_index_timeout = 3600  # Default: 1 hour

        if self.resource_config:
            cow_timeout = self.resource_config.cow_clone_timeout
            git_update_timeout = self.resource_config.git_update_index_timeout
            git_restore_timeout = self.resource_config.git_restore_timeout
            cidx_fix_timeout = self.resource_config.cidx_fix_config_timeout
            cidx_index_timeout = self.resource_config.cidx_index_timeout

        # Generate version timestamp
        timestamp = int(datetime.utcnow().timestamp())
        version = f"v_{timestamp}"

        # Create versioned directory path
        repo_name = alias_name.replace("-global", "")
        versioned_base = self.golden_repos_dir / ".versioned" / repo_name
        versioned_path = versioned_base / version

        logger.info(f"Creating new versioned index at: {versioned_path}")

        try:
            # Step 1: Create versioned directory structure
            versioned_base.mkdir(parents=True, exist_ok=True)

            # Step 2: Perform CoW clone
            logger.info(f"CoW cloning from {source_path} to {versioned_path}")
            try:
                result = subprocess.run(
                    [
                        "cp",
                        "--reflink=auto",
                        "-r",
                        str(source_path),
                        str(versioned_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=cow_timeout,
                    check=True,
                )
                logger.info("CoW clone completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"CoW clone failed: {e.stderr}")
                raise RuntimeError(f"CoW clone failed: {e.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(f"CoW clone timed out after {cow_timeout} seconds")
                raise RuntimeError(f"CoW clone timed out after {cow_timeout} seconds")

            # Step 3: Fix git status (only if .git exists)
            git_dir = versioned_path / ".git"
            if git_dir.exists():
                # Step 3a: git update-index --refresh
                logger.info("Running git update-index --refresh to fix CoW timestamps")
                try:
                    result = subprocess.run(
                        ["git", "update-index", "--refresh"],
                        cwd=str(versioned_path),
                        capture_output=True,
                        text=True,
                        timeout=git_update_timeout,
                        check=False,  # Non-fatal - may show modified files
                    )
                    if result.returncode != 0:
                        logger.debug(f"git update-index output: {result.stderr}")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"git update-index timed out after {git_update_timeout} seconds"
                    )

                # Step 3b: git restore .
                logger.info("Running git restore . to clean up timestamp changes")
                try:
                    result = subprocess.run(
                        ["git", "restore", "."],
                        cwd=str(versioned_path),
                        capture_output=True,
                        text=True,
                        timeout=git_restore_timeout,
                        check=False,  # Non-fatal
                    )
                    if result.returncode != 0:
                        logger.debug(f"git restore output: {result.stderr}")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"git restore timed out after {git_restore_timeout} seconds"
                    )

            # Step 4: Run cidx fix-config --force
            logger.info("Running cidx fix-config --force to update paths")
            try:
                result = subprocess.run(
                    ["cidx", "fix-config", "--force"],
                    cwd=str(versioned_path),
                    capture_output=True,
                    text=True,
                    timeout=cidx_fix_timeout,
                    check=True,
                )
                logger.info("cidx fix-config completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"cidx fix-config failed: {e.stderr}")
                raise RuntimeError(f"cidx fix-config failed: {e.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(
                    f"cidx fix-config timed out after {cidx_fix_timeout} seconds"
                )
                raise RuntimeError(
                    f"cidx fix-config timed out after {cidx_fix_timeout} seconds"
                )

            # Step 5: Run cidx index for semantic + FTS (always required)
            # Note: --index-commits ONLY does temporal indexing, not semantic+FTS
            # So we need two separate cidx index calls: one for semantic+FTS, one for temporal
            index_command = ["cidx", "index", "--fts"]

            logger.info(
                f"Running cidx index for semantic+FTS: {' '.join(index_command)}"
            )
            try:
                result = subprocess.run(
                    index_command,
                    cwd=str(versioned_path),
                    capture_output=True,
                    text=True,
                    timeout=cidx_index_timeout,
                    check=True,
                )
                logger.info("cidx index (semantic+FTS) completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"Indexing (semantic+FTS) failed: {e.stderr}")
                raise RuntimeError(f"Indexing (semantic+FTS) failed: {e.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(
                    f"Indexing (semantic+FTS) timed out after {cidx_index_timeout} seconds"
                )
                raise RuntimeError(
                    f"Indexing (semantic+FTS) timed out after {cidx_index_timeout} seconds"
                )

            # Step 5b: Run cidx index --index-commits for temporal indexing (if enabled)
            # Read temporal settings from registry
            repo_info = self.registry.get_global_repo(alias_name)
            enable_temporal = (
                repo_info.get("enable_temporal", False) if repo_info else False
            )
            temporal_options = repo_info.get("temporal_options") if repo_info else None

            if enable_temporal:
                temporal_command = ["cidx", "index", "--index-commits"]
                logger.info(f"Temporal indexing enabled for {alias_name}")

                if temporal_options:
                    if temporal_options.get("max_commits"):
                        temporal_command.extend(
                            ["--max-commits", str(temporal_options["max_commits"])]
                        )
                    if temporal_options.get("since_date"):
                        temporal_command.extend(
                            ["--since-date", temporal_options["since_date"]]
                        )
                    if temporal_options.get("diff_context"):
                        temporal_command.extend(
                            ["--diff-context", str(temporal_options["diff_context"])]
                        )

                logger.info(
                    f"Running cidx index for temporal: {' '.join(temporal_command)}"
                )
                try:
                    result = subprocess.run(
                        temporal_command,
                        cwd=str(versioned_path),
                        capture_output=True,
                        text=True,
                        timeout=cidx_index_timeout,
                        check=True,
                    )
                    logger.info("cidx index (temporal) completed successfully")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Temporal indexing failed: {e.stderr}")
                    raise RuntimeError(f"Temporal indexing failed: {e.stderr}")
                except subprocess.TimeoutExpired:
                    logger.error(
                        f"Temporal indexing timed out after {cidx_index_timeout} seconds"
                    )
                    raise RuntimeError(
                        f"Temporal indexing timed out after {cidx_index_timeout} seconds"
                    )

            # Step 6: Validate index exists
            index_dir = versioned_path / ".code-indexer" / "index"
            if not index_dir.exists():
                logger.error(f"Index validation failed: {index_dir} does not exist")
                raise RuntimeError(
                    "Index validation failed: index directory not created"
                )

            logger.info(
                f"New versioned index created successfully at: {versioned_path}"
            )
            return str(versioned_path)

        except Exception as e:
            # Step 7: Cleanup partial artifacts on failure
            logger.error(f"Failed to create new index, cleaning up: {e}")
            if versioned_path.exists():
                try:
                    shutil.rmtree(versioned_path)
                    logger.info(f"Cleaned up partial index at: {versioned_path}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup partial index: {cleanup_error}")

            # Re-raise with context
            raise RuntimeError(f"Failed to create new index: {e}")
