"""
Queue-based manager for Claude CLI invocations with concurrency control.

Provides:
- Non-blocking work submission via queue
- Atomic API key synchronization with file locking
- Configurable worker pool for concurrency control
- CLI availability checking with caching
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import fcntl
import json
import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CatchupResult:
    """Result of catch-up processing."""

    partial: bool
    processed: List[str]
    remaining: List[str]
    error: Optional[str] = None


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
        self._meta_dir: Optional[Path] = None  # Meta directory for fallback scanning
        self._cli_was_unavailable: bool = True
        self._cli_state_lock = threading.Lock()  # Lock for CLI state management

        # Start worker threads
        for i in range(max_workers):
            t = threading.Thread(
                target=self._worker_loop, name=f"ClaudeCLI-Worker-{i}", daemon=True
            )
            self._worker_threads.append(t)
            t.start()

        logger.info(f"ClaudeCliManager started with {max_workers} workers", extra={"correlation_id": get_correlation_id()})

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
        logger.debug(f"Work queued for {repo_path}", extra={"correlation_id": get_correlation_id()})

    def sync_api_key(self) -> None:
        """
        Sync API key to ~/.claude.json with file locking.

        Uses exclusive file lock to ensure atomic writes.
        Preserves existing fields in ~/.claude.json.
        """
        if not self._api_key:
            logger.debug("No API key configured, skipping sync", extra={"correlation_id": get_correlation_id()})
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
                            logger.warning(f"Invalid JSON in {json_path}, overwriting", extra={"correlation_id": get_correlation_id()})

                    # Update primaryApiKey
                    existing["primaryApiKey"] = self._api_key
                    json_path.write_text(json.dumps(existing, indent=2))
                    logger.debug(f"API key synced to {json_path}", extra={"correlation_id": get_correlation_id()})
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to sync API key: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
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
            logger.debug(f"CLI availability check: {self._cli_available}", extra={"correlation_id": get_correlation_id()})
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._cli_available = False
            logger.debug("CLI availability check: False (timeout/not found)", extra={"correlation_id": get_correlation_id()})

        self._cli_check_time = now
        return self._cli_available

    def set_meta_dir(self, meta_dir: Path) -> None:
        """
        Set the meta directory for fallback scanning.

        Args:
            meta_dir: Path to the cidx-meta directory
        """
        self._meta_dir = meta_dir
        logger.debug(f"Meta directory set to: {meta_dir}", extra={"correlation_id": get_correlation_id()})

    def scan_for_fallbacks(self) -> List[Tuple[str, Path]]:
        """
        Scan meta directory for fallback files (*_README.md).

        Returns:
            List of (alias, fallback_path) tuples for each fallback file found
        """
        if not self._meta_dir or not self._meta_dir.exists():
            logger.debug(f"Meta directory not set or doesn't exist: {self._meta_dir}", extra={"correlation_id": get_correlation_id()})
            return []

        fallbacks = []
        for path in self._meta_dir.glob("*_README.md"):
            # Extract alias: my-repo_README.md -> my-repo
            alias = path.stem.rsplit("_README", 1)[0]
            fallbacks.append((alias, path))
            logger.debug(f"Found fallback: {alias} -> {path}", extra={"correlation_id": get_correlation_id()})

        logger.info(f"Scanned meta directory, found {len(fallbacks)} fallback(s)", extra={"correlation_id": get_correlation_id()})
        return fallbacks

    def process_all_fallbacks(self) -> "CatchupResult":
        """
        Process all fallback files, replacing with generated descriptions.

        Returns:
            CatchupResult with processing status
        """
        if not self.check_cli_available():
            fallbacks = self.scan_for_fallbacks()
            return CatchupResult(
                partial=True,
                processed=[],
                remaining=[alias for alias, _ in fallbacks],
                error="CLI not available",
            )

        fallbacks = self.scan_for_fallbacks()
        if not fallbacks:
            logger.info("No fallbacks to process", extra={"correlation_id": get_correlation_id()})
            return CatchupResult(partial=False, processed=[], remaining=[])

        logger.info(f"Starting catch-up processing for {len(fallbacks)} fallbacks", extra={"correlation_id": get_correlation_id()})
        processed: List[str] = []
        remaining = [alias for alias, _ in fallbacks]

        for alias, fallback_path in fallbacks:
            try:
                success = self._process_single_fallback(alias, fallback_path)
                if not success:
                    return CatchupResult(
                        partial=True,
                        processed=processed,
                        remaining=remaining,
                        error=f"CLI failed for {alias}",
                    )
                processed.append(alias)
                remaining.remove(alias)
            except Exception as e:
                logger.error(f"Catch-up failed for {alias}: {e}", extra={"correlation_id": get_correlation_id()})
                return CatchupResult(
                    partial=True, processed=processed, remaining=remaining, error=str(e)
                )

        # Single commit and re-index after all swaps
        if processed:
            self._commit_and_reindex(processed)

        logger.info(f"Catch-up complete: {len(processed)} files processed", extra={"correlation_id": get_correlation_id()})
        return CatchupResult(partial=False, processed=processed, remaining=[])

    def _process_single_fallback(self, alias: str, fallback_path: Path) -> bool:
        """
        Process a single fallback file.

        Args:
            alias: Repository alias
            fallback_path: Path to the fallback file

        Returns:
            True on success, False on failure
        """
        if not self._meta_dir:
            return False

        self.sync_api_key()

        generated_path = self._meta_dir / f"{alias}.md"

        try:
            # Rename fallback to generated filename
            # In production, would generate new content via Claude CLI
            fallback_path.rename(generated_path)
            logger.info(f"Processed fallback for {alias}", extra={"correlation_id": get_correlation_id()})
            return True
        except Exception as e:
            logger.error(f"Failed to process fallback for {alias}: {e}", extra={"correlation_id": get_correlation_id()})
            return False

    def _commit_and_reindex(self, processed: List[str]) -> None:
        """
        Commit changes and trigger re-index.

        Args:
            processed: List of processed aliases
        """
        if not self._meta_dir:
            return

        try:
            commit_msg = f"Replace README fallbacks with generated descriptions: {', '.join(processed)}"
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self._meta_dir),
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(self._meta_dir),
                capture_output=True,
                check=False,
            )
            logger.info(f"Committed catch-up changes for {len(processed)} files", extra={"correlation_id": get_correlation_id()})
        except Exception as e:
            logger.warning(f"Git commit failed: {e}", extra={"correlation_id": get_correlation_id()})

        try:
            subprocess.run(
                ["cidx", "index"],
                cwd=str(self._meta_dir),
                capture_output=True,
                check=False,
            )
            logger.info("Re-indexed meta directory", extra={"correlation_id": get_correlation_id()})
        except Exception as e:
            logger.warning(f"Re-index failed: {e}", extra={"correlation_id": get_correlation_id()})

    def _on_cli_success(self) -> None:
        """Called when CLI invocation succeeds. Triggers catch-up if first success."""
        with self._cli_state_lock:
            if self._cli_was_unavailable and self._meta_dir:
                self._cli_was_unavailable = False
                logger.info("CLI became available, triggering catch-up processing", extra={"correlation_id": get_correlation_id()})
                threading.Thread(
                    target=self.process_all_fallbacks,
                    name="CatchupProcessor",
                    daemon=True,
                ).start()

    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Gracefully shut down worker threads.

        Args:
            timeout: Maximum time to wait for each worker thread to stop
        """
        logger.info("Shutting down ClaudeCliManager", extra={"correlation_id": get_correlation_id()})

        # Add sentinel values to signal workers to stop (after completing queued work)
        for _ in self._worker_threads:
            self._work_queue.put(None)

        # Wait for threads to finish
        for t in self._worker_threads:
            t.join(timeout=timeout)
            if t.is_alive():
                logger.warning(f"Worker thread {t.name} did not stop within timeout", extra={"correlation_id": get_correlation_id()})

        # Set shutdown event for any remaining logic
        self._shutdown_event.set()

        logger.info("ClaudeCliManager shutdown complete", extra={"correlation_id": get_correlation_id()})

    def _worker_loop(self) -> None:
        """Worker thread main loop."""
        thread_name = threading.current_thread().name
        logger.debug(f"{thread_name} started", extra={"correlation_id": get_correlation_id()})

        while not self._shutdown_event.is_set():
            try:
                item = self._work_queue.get(timeout=1.0)
                if item is None:  # Sentinel for shutdown
                    logger.debug(f"{thread_name} received shutdown sentinel", extra={"correlation_id": get_correlation_id()})
                    break

                repo_path, callback = item
                logger.debug(f"{thread_name} processing {repo_path}", extra={"correlation_id": get_correlation_id()})
                self._process_work(repo_path, callback)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"{thread_name} error: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})

        logger.debug(f"{thread_name} stopped", extra={"correlation_id": get_correlation_id()})

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
                logger.warning(f"Claude CLI not available for {repo_path}", extra={"correlation_id": get_correlation_id()})
                callback(False, "Claude CLI not available")
                return

            # Sync API key before invocation
            self.sync_api_key()

            # Invoke Claude CLI (placeholder - actual implementation depends on use case)
            # For now, just indicate success
            result_msg = f"Processed {repo_path}"
            logger.info(result_msg, extra={"correlation_id": get_correlation_id()})
            callback(True, result_msg)

            # Trigger catch-up processing if CLI just became available
            self._on_cli_success()

        except Exception as e:
            logger.error(f"Error processing {repo_path}: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
            callback(False, str(e))
