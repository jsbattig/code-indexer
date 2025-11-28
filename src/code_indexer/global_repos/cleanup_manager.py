"""
Cleanup Manager for automatic deletion of old index versions.

Monitors reference counts and deletes old index directories when
no active queries remain. Runs as a background thread with configurable
check interval.
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Set

from .query_tracker import QueryTracker


logger = logging.getLogger(__name__)


class CleanupManager:
    """
    Background manager for cleaning up old index versions.

    Monitors the reference counts from QueryTracker and deletes
    index directories when their ref count reaches zero and they
    are scheduled for cleanup.
    """

    def __init__(self, query_tracker: QueryTracker, check_interval: float = 1.0):
        """
        Initialize the cleanup manager.

        Args:
            query_tracker: QueryTracker instance for ref count monitoring
            check_interval: How often to check for cleanups (seconds)
        """
        self._query_tracker = query_tracker
        self._check_interval = check_interval
        self._cleanup_queue: Set[str] = set()
        self._queue_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def schedule_cleanup(self, index_path: str) -> None:
        """
        Schedule an index path for cleanup.

        The path will be deleted once its reference count reaches zero.

        Args:
            index_path: Path to index directory to clean up
        """
        with self._queue_lock:
            self._cleanup_queue.add(index_path)
            logger.info(f"Scheduled cleanup for: {index_path}")

    def get_pending_cleanups(self) -> Set[str]:
        """
        Get set of paths currently scheduled for cleanup.

        Returns:
            Set of index paths in cleanup queue
        """
        with self._queue_lock:
            return set(self._cleanup_queue)

    def is_running(self) -> bool:
        """
        Check if cleanup manager is running.

        Returns:
            True if background thread is active
        """
        return self._running

    def start(self) -> None:
        """
        Start the cleanup manager background thread.

        Idempotent: Safe to call multiple times
        """
        if self._running:
            logger.debug("Cleanup manager already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info("Cleanup manager started")

    def stop(self) -> None:
        """
        Stop the cleanup manager background thread.

        Waits for thread to exit gracefully.

        Idempotent: Safe to call multiple times
        """
        if not self._running:
            logger.debug("Cleanup manager already stopped")
            return

        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Cleanup manager stopped")

    def _cleanup_loop(self) -> None:
        """
        Background thread loop for cleanup monitoring.

        Checks cleanup queue at regular intervals and deletes
        directories when ref count reaches zero.
        """
        logger.debug("Cleanup loop started")

        while self._running:
            try:
                self._process_cleanup_queue()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

            # Sleep in small increments to allow faster shutdown
            sleep_remaining = self._check_interval
            while sleep_remaining > 0 and self._running:
                sleep_chunk = min(0.1, sleep_remaining)
                time.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk

        logger.debug("Cleanup loop exited")

    def _process_cleanup_queue(self) -> None:
        """
        Process the cleanup queue and delete eligible paths.

        Deletes paths that have zero reference count.
        """
        # Get snapshot of queue
        with self._queue_lock:
            paths_to_check = list(self._cleanup_queue)

        for path in paths_to_check:
            try:
                # Check reference count
                ref_count = self._query_tracker.get_ref_count(path)

                if ref_count == 0:
                    # Safe to delete
                    self._delete_index(path)

                    # Remove from queue
                    with self._queue_lock:
                        self._cleanup_queue.discard(path)

                    logger.info(f"Deleted old index: {path}")
                else:
                    logger.debug(
                        f"Skipping cleanup for {path}: " f"{ref_count} active queries"
                    )

            except Exception as e:
                logger.error(f"Failed to clean up {path}: {e}", exc_info=True)
                # Keep in queue for retry

    def _delete_index(self, index_path: str) -> None:
        """
        Delete an index directory.

        Args:
            index_path: Path to index directory

        Raises:
            OSError: If deletion fails
        """
        path = Path(index_path)

        if not path.exists():
            logger.debug(f"Index path already deleted: {index_path}")
            return

        if not path.is_dir():
            logger.warning(f"Index path is not a directory: {index_path}")
            return

        # Recursively delete directory
        shutil.rmtree(path)
        logger.debug(f"Removed directory: {index_path}")
