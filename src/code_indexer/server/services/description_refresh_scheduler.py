"""
Description refresh scheduler for periodic regeneration of AI descriptions.

Operates independently of the 10-minute repository refresh cycle,
regenerating descriptions on a configurable cadence (default 24 hours).
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
import threading
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Dict, Optional, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from code_indexer.server.services.claude_cli_manager import ClaudeCliManager

logger = logging.getLogger(__name__)


class DescriptionRefreshScheduler:
    """
    Scheduler for periodic description regeneration.

    Features:
    - Hourly check for repos needing refresh
    - Configurable refresh interval (default 24 hours)
    - Skips fallback files (*_README.md)
    - Uses ClaudeCliManager queue for concurrency control
    - Independent of repo refresh cycle
    """

    def __init__(
        self,
        cli_manager: "ClaudeCliManager",
        meta_dir: Path,
        get_interval_hours: Callable[[], int],
        get_repo_path: Callable[[str], Optional[Path]],
    ):
        """
        Initialize the description refresh scheduler.

        Args:
            cli_manager: ClaudeCliManager for work submission
            meta_dir: Path to the cidx-meta directory
            get_interval_hours: Callable that returns current refresh interval from config
            get_repo_path: Callable that resolves alias to actual repository path
        """
        self._cli_manager = cli_manager
        self._meta_dir = meta_dir
        self._get_interval_hours = get_interval_hours
        self._get_repo_path = get_repo_path
        self._last_refresh: Dict[str, datetime] = {}
        self._refresh_lock = threading.Lock()
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._check_interval_seconds = 3600  # Check every hour

    def start(self) -> None:
        """Start the refresh scheduler background thread."""
        if self._timer_thread is not None and self._timer_thread.is_alive():
            logger.warning("Description refresh scheduler already running", extra={"correlation_id": get_correlation_id()})
            return

        self._stop_event.clear()
        self._timer_thread = threading.Thread(
            target=self._timer_loop, name="DescriptionRefreshScheduler", daemon=True
        )
        self._timer_thread.start()
        logger.info("Description refresh scheduler started", extra={"correlation_id": get_correlation_id()})

    def stop(self) -> None:
        """Stop the refresh scheduler."""
        self._stop_event.set()
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=5.0)
        logger.info("Description refresh scheduler stopped", extra={"correlation_id": get_correlation_id()})

    def _timer_loop(self) -> None:
        """Background thread loop that checks for needed refreshes."""
        while not self._stop_event.is_set():
            try:
                self._check_and_refresh()
            except Exception as e:
                logger.error(f"Error in description refresh check: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})

            # Wait for next check, but allow early exit via stop_event
            self._stop_event.wait(timeout=self._check_interval_seconds)

    def _check_and_refresh(self) -> None:
        """Check which repos need refresh and submit work."""
        interval_hours = self._get_interval_hours()
        if interval_hours < 1:
            interval_hours = 1  # Minimum 1 hour

        repos_needing_refresh = self._get_repos_needing_refresh(interval_hours)

        if not repos_needing_refresh:
            logger.debug("No repos need description refresh", extra={"correlation_id": get_correlation_id()})
            return

        logger.info(
            f"Scheduling description refresh for {len(repos_needing_refresh)} repos"
        , extra={"correlation_id": get_correlation_id()})

        for alias, meta_file in repos_needing_refresh:
            try:
                repo_path = self._get_repo_path(alias)
                if repo_path is None:
                    logger.warning(f"Could not resolve repo path for {alias}, skipping", extra={"correlation_id": get_correlation_id()})
                    continue
                self._cli_manager.submit_work(
                    repo_path,
                    partial(self._on_refresh_complete, alias),
                )
            except Exception as e:
                logger.error(
                    f"Failed to submit refresh work for {alias}: {e}", exc_info=True
                , extra={"correlation_id": get_correlation_id()})

    def _get_repos_needing_refresh(self, interval_hours: int) -> List[tuple]:
        """
        Get list of repos that need description refresh.

        Args:
            interval_hours: Refresh interval in hours

        Returns:
            List of (alias, meta_file_path) tuples needing refresh
        """
        if not self._meta_dir or not self._meta_dir.exists():
            return []

        repos_needing_refresh = []
        cutoff_time = datetime.now() - timedelta(hours=interval_hours)

        for meta_file in self._meta_dir.glob("*.md"):
            # Skip fallback files - they're handled by catch-up (Story #549)
            if meta_file.name.endswith("_README.md"):
                logger.debug(f"Skipping fallback file: {meta_file.name}", extra={"correlation_id": get_correlation_id()})
                continue

            alias = meta_file.stem  # e.g., "my-repo" from "my-repo.md"

            # Check last refresh time
            with self._refresh_lock:
                last_refresh = self._last_refresh.get(alias)
                if last_refresh is None:
                    # Use file modification time as initial timestamp
                    last_refresh = datetime.fromtimestamp(meta_file.stat().st_mtime)
                    self._last_refresh[alias] = last_refresh

            if last_refresh < cutoff_time:
                repos_needing_refresh.append((alias, meta_file))
                logger.debug(f"Repo {alias} needs refresh (last: {last_refresh})", extra={"correlation_id": get_correlation_id()})

        return repos_needing_refresh

    def _on_refresh_complete(self, alias: str, success: bool, result: str) -> None:
        """
        Callback when refresh completes.

        Args:
            alias: Repository alias
            success: Whether refresh succeeded
            result: Result message
        """
        if success:
            with self._refresh_lock:
                self._last_refresh[alias] = datetime.now()
            logger.info(f"Description refresh completed for {alias}", extra={"correlation_id": get_correlation_id()})
        else:
            logger.warning(f"Description refresh failed for {alias}: {result}", extra={"correlation_id": get_correlation_id()})
