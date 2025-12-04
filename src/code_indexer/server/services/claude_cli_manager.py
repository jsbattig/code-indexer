"""
Queue-based manager for Claude CLI invocations with concurrency control.

Provides:
- Non-blocking work submission via queue
- Atomic API key synchronization with file locking
- Configurable worker pool for concurrency control
- CLI availability checking with caching
"""

import fcntl
import json
import logging
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional, List, Tuple

logger = logging.getLogger(__name__)


class ClaudeCliManager:
    """
    Queue-based manager for Claude CLI invocations with:
    - Non-blocking work submission
    - Atomic API key synchronization with file locking
    - Configurable worker pool for concurrency control
    """

    def __init__(self, api_key: Optional[str] = None, max_workers: int = 4):
        """
        Initialize ClaudeCliManager with worker pool.

        Args:
            api_key: Anthropic API key to sync to ~/.claude.json
            max_workers: Number of worker threads (default 4)
        """
        self._api_key = api_key
        self._max_workers = max_workers
        self._work_queue: (
            "queue.Queue[Optional[Tuple[Path, Callable[[bool, str], None]]]]"
        ) = queue.Queue()
        self._worker_threads: List[threading.Thread] = []
        self._shutdown_event = threading.Event()
        self._cli_available: Optional[bool] = None
        self._cli_check_time: float = 0
        self._cli_check_ttl: float = 300  # 5 minutes TTL

        # Start worker threads
        for i in range(max_workers):
            t = threading.Thread(
                target=self._worker_loop, name=f"ClaudeCLI-Worker-{i}", daemon=True
            )
            self._worker_threads.append(t)
            t.start()

        logger.info(f"ClaudeCliManager started with {max_workers} workers")

    def submit_work(
        self, repo_path: Path, callback: Callable[[bool, str], None]
    ) -> None:
        """
        Submit work to the queue. Returns immediately (non-blocking).

        Args:
            repo_path: Repository path to process
            callback: Callback function(success: bool, result: str) invoked on completion
        """
        self._work_queue.put((repo_path, callback))
        logger.debug(f"Work queued for {repo_path}")

    def sync_api_key(self) -> None:
        """
        Sync API key to ~/.claude.json with file locking.

        Uses exclusive file lock to ensure atomic writes.
        Preserves existing fields in ~/.claude.json.
        """
        if not self._api_key:
            logger.debug("No API key configured, skipping sync")
            return

        lock_path = Path.home() / ".claude.json.lock"
        json_path = Path.home() / ".claude.json"

        try:
            with open(lock_path, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    # Read existing config or create new
                    existing = {}
                    if json_path.exists():
                        try:
                            existing = json.loads(json_path.read_text())
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in {json_path}, overwriting")

                    # Update primaryApiKey
                    existing["primaryApiKey"] = self._api_key
                    json_path.write_text(json.dumps(existing, indent=2))
                    logger.debug(f"API key synced to {json_path}")
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to sync API key: {e}", exc_info=True)
            raise

    def check_cli_available(self) -> bool:
        """
        Check if Claude CLI is installed. Caches result with TTL.

        Returns:
            True if Claude CLI is available, False otherwise
        """
        now = time.time()
        if (
            self._cli_available is not None
            and (now - self._cli_check_time) < self._cli_check_ttl
        ):
            return self._cli_available

        try:
            result = subprocess.run(
                ["which", "claude"], capture_output=True, text=True, timeout=5
            )
            self._cli_available = result.returncode == 0
            logger.debug(f"CLI availability check: {self._cli_available}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._cli_available = False
            logger.debug("CLI availability check: False (timeout/not found)")

        self._cli_check_time = now
        return self._cli_available

    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Gracefully shut down worker threads.

        Args:
            timeout: Maximum time to wait for each worker thread to stop
        """
        logger.info("Shutting down ClaudeCliManager")

        # Add sentinel values to signal workers to stop (after completing queued work)
        for _ in self._worker_threads:
            self._work_queue.put(None)

        # Wait for threads to finish
        for t in self._worker_threads:
            t.join(timeout=timeout)
            if t.is_alive():
                logger.warning(f"Worker thread {t.name} did not stop within timeout")

        # Set shutdown event for any remaining logic
        self._shutdown_event.set()

        logger.info("ClaudeCliManager shutdown complete")

    def _worker_loop(self) -> None:
        """Worker thread main loop."""
        thread_name = threading.current_thread().name
        logger.debug(f"{thread_name} started")

        while not self._shutdown_event.is_set():
            try:
                item = self._work_queue.get(timeout=1.0)
                if item is None:  # Sentinel for shutdown
                    logger.debug(f"{thread_name} received shutdown sentinel")
                    break

                repo_path, callback = item
                logger.debug(f"{thread_name} processing {repo_path}")
                self._process_work(repo_path, callback)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"{thread_name} error: {e}", exc_info=True)

        logger.debug(f"{thread_name} stopped")

    def _process_work(
        self, repo_path: Path, callback: Callable[[bool, str], None]
    ) -> None:
        """
        Process a single work item.

        Args:
            repo_path: Repository path to process
            callback: Callback function to invoke with result
        """
        try:
            # Check CLI availability
            if not self.check_cli_available():
                logger.warning(f"Claude CLI not available for {repo_path}")
                callback(False, "Claude CLI not available")
                return

            # Sync API key before invocation
            self.sync_api_key()

            # Invoke Claude CLI (placeholder - actual implementation depends on use case)
            # For now, just indicate success
            result_msg = f"Processed {repo_path}"
            logger.info(result_msg)
            callback(True, result_msg)

        except Exception as e:
            logger.error(f"Error processing {repo_path}: {e}", exc_info=True)
            callback(False, str(e))
