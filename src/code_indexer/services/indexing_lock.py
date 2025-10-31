"""
Indexing lock mechanism with heartbeat to prevent concurrent indexing operations.

This module provides a heartbeat-based locking mechanism to ensure that only one
indexing operation can run per project at a time, while handling crashed processes
gracefully through heartbeat timeouts.
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class IndexingLockError(Exception):
    """Raised when indexing cannot proceed due to lock conflicts."""

    pass


class IndexingLock:
    """
    Heartbeat-based locking mechanism for indexing operations.

    This class ensures that only one indexing operation can run per project at a time,
    while providing graceful handling of crashed processes through heartbeat timeouts.
    """

    def __init__(
        self,
        metadata_dir: Path,
        heartbeat_interval: float = 30.0,
        timeout: float = 300.0,
    ):
        """
        Initialize the indexing lock.

        Args:
            metadata_dir: Directory where lock files are stored (usually .code-indexer)
            heartbeat_interval: How often to update heartbeat in seconds
            timeout: How long to wait before considering a heartbeat stale in seconds
        """
        self.metadata_dir = metadata_dir
        self.heartbeat_interval = heartbeat_interval
        self.timeout = timeout
        self.heartbeat_path = metadata_dir / "indexing_heartbeat.json"
        self.lock_acquired = False
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_heartbeat = threading.Event()
        self.current_pid = os.getpid()

    def acquire(self, project_path: str) -> None:
        """
        Acquire the indexing lock for a project.

        Args:
            project_path: Path to the project being indexed

        Raises:
            IndexingLockError: If another indexing operation is already running
        """
        try:
            # Check if there's an existing lock
            if self.heartbeat_path.exists():
                existing_lock = self._read_heartbeat()
                if existing_lock and self._is_heartbeat_active(existing_lock):
                    # There's an active indexing operation
                    pid = existing_lock.get("pid", "unknown")
                    started_at = existing_lock.get("started_at", 0)
                    duration = time.time() - started_at

                    raise IndexingLockError(
                        f"Indexing already in progress (PID: {pid}, running for {duration:.1f}s). "
                        f"Please wait for the current operation to complete or use 'cidx status' to check progress."
                    )
                else:
                    # Stale heartbeat - remove it
                    logger.info("Removing stale indexing heartbeat")
                    self._cleanup_heartbeat()

            # Create new heartbeat
            self._create_heartbeat(project_path)
            self.lock_acquired = True

            # Start heartbeat thread
            self._start_heartbeat_thread()

            logger.info(f"Acquired indexing lock for project: {project_path}")

        except IndexingLockError:
            raise
        except Exception as e:
            logger.error(f"Failed to acquire indexing lock: {e}")
            raise IndexingLockError(f"Failed to acquire indexing lock: {e}")

    def release(self) -> None:
        """Release the indexing lock and clean up heartbeat."""
        if not self.lock_acquired:
            return

        try:
            # Stop heartbeat thread
            self._stop_heartbeat_thread()

            # Clean up heartbeat file
            self._cleanup_heartbeat()

            self.lock_acquired = False
            logger.info("Released indexing lock")

        except Exception as e:
            logger.error(f"Error releasing indexing lock: {e}")

    def _create_heartbeat(self, project_path: str) -> None:
        """Create initial heartbeat file."""
        heartbeat_data = {
            "pid": self.current_pid,
            "project_path": project_path,
            "started_at": time.time(),
            "last_heartbeat": time.time(),
        }

        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        with open(self.heartbeat_path, "w") as f:
            json.dump(heartbeat_data, f, indent=2)

    def _update_heartbeat(self) -> None:
        """Update the heartbeat timestamp."""
        try:
            if self.heartbeat_path.exists():
                heartbeat_data = self._read_heartbeat()
                if heartbeat_data:
                    heartbeat_data["last_heartbeat"] = time.time()
                    with open(self.heartbeat_path, "w") as f:
                        json.dump(heartbeat_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to update heartbeat: {e}")

    def _read_heartbeat(self) -> Optional[Dict[str, Any]]:
        """Read heartbeat data from file."""
        try:
            if self.heartbeat_path.exists():
                with open(self.heartbeat_path, "r") as f:
                    data = json.load(f)
                    # Ensure we return a Dict[str, Any] or None
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.warning(f"Failed to read heartbeat file: {e}")
        return None

    def _is_heartbeat_active(self, heartbeat_data: Dict[str, Any]) -> bool:
        """Check if a heartbeat is still active (not stale)."""
        if not heartbeat_data:
            return False

        # Check if process is still running FIRST (primary check)
        pid = heartbeat_data.get("pid")
        if pid and isinstance(pid, int):
            try:
                # On Unix systems, sending signal 0 checks if process exists
                os.kill(pid, 0)
                # Process exists, now check heartbeat freshness
                last_heartbeat = heartbeat_data.get("last_heartbeat", 0)
                age = time.time() - last_heartbeat
                return age <= self.timeout
            except (OSError, ProcessLookupError):
                # Process doesn't exist - heartbeat is stale regardless of timestamp
                return False

        # If we can't check process (no PID), rely on heartbeat timeout
        last_heartbeat = heartbeat_data.get("last_heartbeat", 0)
        age = time.time() - last_heartbeat
        return bool(age <= self.timeout)

    def _cleanup_heartbeat(self) -> None:
        """Remove heartbeat file."""
        try:
            if self.heartbeat_path.exists():
                self.heartbeat_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove heartbeat file: {e}")

    def _start_heartbeat_thread(self) -> None:
        """Start background thread to update heartbeat."""
        self.stop_heartbeat.clear()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker,
            daemon=True,  # Dies when main thread dies
            name="IndexingHeartbeat",
        )
        self.heartbeat_thread.start()

    def _stop_heartbeat_thread(self) -> None:
        """Stop heartbeat background thread."""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.stop_heartbeat.set()
            self.heartbeat_thread.join(timeout=5.0)  # Wait up to 5 seconds

    def _heartbeat_worker(self) -> None:
        """Background worker that updates heartbeat periodically."""
        while not self.stop_heartbeat.wait(self.heartbeat_interval):
            self._update_heartbeat()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always clean up."""
        self.release()


def create_indexing_lock(metadata_dir: Path) -> IndexingLock:
    """
    Factory function to create an IndexingLock with sensible defaults.

    Args:
        metadata_dir: Directory where lock files are stored

    Returns:
        Configured IndexingLock instance
    """
    return IndexingLock(
        metadata_dir=metadata_dir,
        heartbeat_interval=30.0,  # Update every 30 seconds
        timeout=300.0,  # 5 minute timeout
    )
