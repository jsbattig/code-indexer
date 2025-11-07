"""TemporalWatchHandler for git commit detection without hooks.

This module provides:
1. Git refs file inotify monitoring for commit detection
2. Polling fallback for filesystems without inotify support
3. Branch switch detection via .git/HEAD monitoring
4. Incremental temporal indexing on commit detection

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
"""

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


class TemporalWatchHandler(FileSystemEventHandler):
    """Watch git refs file for commit detection without hooks.

    This handler monitors .git/refs/heads/<branch> for commits using either:
    1. Inotify (fast, <100ms detection) when refs file exists
    2. Polling fallback (5s interval) for detached HEAD or unsupported filesystems

    It also monitors .git/HEAD for branch switch detection (Story 3.1).
    """

    def __init__(
        self, project_root: Path, temporal_indexer=None, progressive_metadata=None
    ):
        """Initialize temporal watch handler.

        Args:
            project_root: Path to project root directory
            temporal_indexer: Optional TemporalIndexer instance (injected for testing)
            progressive_metadata: Optional TemporalProgressiveMetadata instance (injected for testing)
        """
        self.project_root = project_root
        self.current_branch = self._get_current_branch()
        self.git_refs_file = (
            project_root / ".git" / "refs" / "heads" / self.current_branch
        )
        self.git_head_file = project_root / ".git" / "HEAD"
        self.last_commit_hash = self._get_last_commit_hash()

        # Initialize or use injected dependencies
        self.temporal_indexer = temporal_indexer
        self.progressive_metadata = progressive_metadata

        # Verify git refs file exists
        if not self.git_refs_file.exists():
            logger.warning(f"Git refs file not found: {self.git_refs_file}")
            logger.warning("Falling back to polling (5s interval)")
            self.use_polling = True
        else:
            logger.info(f"Watching git refs file: {self.git_refs_file}")
            self.use_polling = False

        # Start polling thread if inotify unavailable
        if self.use_polling:
            self._start_polling_thread()

    def _get_current_branch(self) -> str:
        """Get current git branch name.

        Returns:
            Branch name, or "HEAD" if detached HEAD state
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get current branch: {e}")
            return "HEAD"  # Detached HEAD state

    def _get_last_commit_hash(self) -> str:
        """Get last commit hash from git.

        Returns:
            Commit hash, or empty string if git command fails
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get commit hash: {e}")
            return ""

    def on_modified(self, event):
        """Handle file modification events (inotify).

        Args:
            event: Watchdog file system event
        """
        # Git commit detection
        if event.src_path == str(self.git_refs_file):
            logger.info(f"Git commit detected via inotify: {self.git_refs_file}")
            self._handle_commit_detected()

        # Branch switch detection (Story 3.1)
        elif event.src_path == str(self.git_head_file):
            logger.info(f"Git HEAD changed: {self.git_head_file}")
            self._handle_branch_switch()

    def _start_polling_thread(self):
        """Fallback: Poll git refs file every 5 seconds."""

        def polling_worker():
            while True:
                time.sleep(5)

                current_hash = self._get_last_commit_hash()

                if current_hash != self.last_commit_hash:
                    logger.info(f"Git commit detected via polling: {current_hash}")
                    self.last_commit_hash = current_hash
                    self._handle_commit_detected()

        thread = threading.Thread(target=polling_worker, daemon=True)
        thread.start()
        logger.info("Polling thread started (5s interval)")

    def _handle_commit_detected(self):
        """Index new commits incrementally when git commit detected.

        This method:
        1. Loads completed commits from temporal_progress.json
        2. Filters new commits (O(1) with in-memory set)
        3. Calls TemporalIndexer._process_commits_parallel() for new commits
        4. Updates progress metadata
        5. Invalidates daemon cache if daemon is running

        Uses RichLiveProgressManager for identical UX to standalone mode.
        """
        try:
            # Load completed commits from temporal_progress.json (returns set)
            completed_commits = self.progressive_metadata.load_completed()

            # Get all commits in current branch
            result = subprocess.run(
                ["git", "rev-list", self.current_branch],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=True,
            )
            all_commits = result.stdout.strip().split("\n")

            # Filter out already indexed commits (O(1) lookup with set)
            new_commits = [c for c in all_commits if c not in completed_commits]

            if not new_commits:
                logger.info("No new commits to index")
                return

            logger.info(f"Indexing {len(new_commits)} new commit(s)")

            # Use RichLiveProgressManager for identical UX to standalone mode
            from code_indexer.progress.progress_display import RichLiveProgressManager
            from rich.console import Console

            console = Console()
            progress_manager = RichLiveProgressManager(console)
            progress_manager.start_bottom_display()

            try:
                # Create progress callback
                def progress_callback(
                    current: int, total: int, file_path: Path, info: str = ""
                ):
                    progress_manager.update_display(info)

                # Index new commits using TemporalIndexer
                result = self.temporal_indexer.index_commits_list(
                    commit_hashes=new_commits,
                    progress_callback=progress_callback,
                )

                logger.info(
                    f"Indexed {result.new_blobs_indexed} new blobs "
                    f"(dedup: {result.deduplication_ratio:.1%})"
                )
            finally:
                progress_manager.stop_display()

            # Update temporal_progress.json with newly indexed commits
            self.progressive_metadata.mark_completed(new_commits)

            # Update in-memory set for O(1) future lookups
            completed_commits.update(new_commits)

            # Invalidate daemon temporal cache (if daemon running)
            self._invalidate_daemon_cache()

            logger.info("Temporal index updated successfully")

        except Exception as e:
            logger.error(f"Failed to index new commits: {e}", exc_info=True)

    def _invalidate_daemon_cache(self):
        """Invalidate daemon temporal cache after indexing.

        Connects to daemon (if running) and calls exposed_clear_cache() to
        invalidate in-memory caches. Non-critical operation - failures are logged
        but don't prevent indexing completion.
        """
        try:
            # Check if daemon is running
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager(self.project_root)
            daemon_config = config_manager.get_daemon_config()

            if not daemon_config or not daemon_config.get("enabled"):
                return  # Daemon not enabled

            # Try to connect to daemon
            from code_indexer.cli_daemon_delegation import _connect_to_daemon

            daemon_client = _connect_to_daemon(daemon_config)

            if daemon_client is None:
                return  # Daemon not running

            # Call invalidate RPC method
            daemon_client.root.exposed_clear_cache()
            logger.info("Daemon temporal cache invalidated")

        except Exception as e:
            logger.debug(f"Failed to invalidate daemon cache: {e}")
            # Non-critical error - daemon might not be running

    def _handle_branch_switch(self):
        """Handle branch switch - catch up temporal index (Story 3.1).

        This is a placeholder for Story 3.1 implementation.
        """
        # Story 3.1: Branch switch catch-up
        pass
