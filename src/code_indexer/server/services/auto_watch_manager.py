"""
AutoWatchManager - Story #640.

Manages auto-watch lifecycle for server file operations, enabling automatic
watch mode activation during file modifications with timeout-based auto-stop.
"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from code_indexer.daemon.watch_manager import DaemonWatchManager
from code_indexer.config import ConfigManager

logger = logging.getLogger(__name__)


class AutoWatchManager:
    """
    Manages auto-watch lifecycle for server file operations.

    In server context, ALL watch mode is auto-watch (no manual watch exists).
    Automatically starts watch on file operations and stops after inactivity timeout.
    """

    # Timeout checker runs every 30 seconds
    TIMEOUT_CHECK_INTERVAL_SECONDS = 30
    # Thread join timeout during shutdown
    SHUTDOWN_THREAD_JOIN_TIMEOUT_SECONDS = 5

    def __init__(
        self,
        auto_watch_enabled: bool = True,
        default_timeout: int = 300,
    ):
        """
        Initialize AutoWatchManager.

        Args:
            auto_watch_enabled: Enable/disable auto-watch functionality
            default_timeout: Default timeout in seconds for auto-stop (default: 300)
        """
        self.auto_watch_enabled = auto_watch_enabled
        self.default_timeout = default_timeout
        self._watch_state: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()  # Use RLock to allow reentrant calls
        self._shutdown_event = threading.Event()

        # Start background timeout checker thread
        self._timeout_thread = threading.Thread(
            target=self._timeout_checker_loop,
            daemon=True,
            name="AutoWatchTimeoutChecker",
        )
        self._timeout_thread.start()
        logger.info("AutoWatchManager timeout checker thread started")

    def is_watching(self, repo_path: str) -> bool:
        """
        Check if watch is currently active for repository.

        Args:
            repo_path: Repository path

        Returns:
            True if watch is running, False otherwise
        """
        with self._lock:
            if repo_path not in self._watch_state:
                return False
            watch_running: bool = self._watch_state[repo_path].get("watch_running", False)
            return watch_running

    def start_watch(
        self,
        repo_path: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Start watch mode with auto-stop timer.

        If watch already running for this repo, reset timeout instead of creating new instance.

        Args:
            repo_path: Path to repository to watch
            timeout: Timeout in seconds for auto-stop (uses default_timeout if not specified)

        Returns:
            Status dictionary with success/error/disabled status and message
        """
        # Check if auto-watch is enabled
        if not self.auto_watch_enabled:
            logger.info(f"Auto-watch disabled, not starting watch for {repo_path}")
            return {
                "status": "disabled",
                "message": "Auto-watch is disabled",
            }

        timeout_seconds = timeout if timeout is not None else self.default_timeout

        with self._lock:
            # Check if watch already running - if so, just reset timeout
            if self.is_watching(repo_path):  # RLock allows this reentrant call
                self._watch_state[repo_path]["last_activity"] = datetime.now()
                self._watch_state[repo_path]["timeout_seconds"] = timeout_seconds
                logger.info(
                    f"Watch already running for {repo_path}, timeout reset to {timeout_seconds}s"
                )
                return {
                    "status": "success",
                    "message": "Timeout reset",
                }

            # Create new watch instance
            try:
                # Initialize configuration
                config_manager = ConfigManager.create_with_backtrack(Path(repo_path))
                config = config_manager.get_config()

                # Create daemon watch manager
                watch_instance = DaemonWatchManager()

                # Start watch
                result = watch_instance.start_watch(
                    project_path=repo_path,
                    config=config,
                )

                if result.get("status") != "success":
                    logger.error(f"Failed to start watch for {repo_path}: {result}")
                    return result

                # Track watch state
                self._watch_state[repo_path] = {
                    "watch_running": True,
                    "last_activity": datetime.now(),
                    "timeout_seconds": timeout_seconds,
                    "watch_instance": watch_instance,
                }

                logger.info(
                    f"Auto-watch started for {repo_path} with {timeout_seconds}s timeout"
                )
                return {
                    "status": "success",
                    "message": f"Watch started with {timeout_seconds}s timeout",
                }

            except Exception as e:
                logger.exception(f"Error starting auto-watch for {repo_path}: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to start watch: {str(e)}",
                }

    def stop_watch(self, repo_path: str) -> Dict[str, Any]:
        """
        Stop auto-watch for repository.

        Args:
            repo_path: Repository path

        Returns:
            Status dictionary with success/error status and message
        """
        with self._lock:
            # Check if watch exists
            if repo_path not in self._watch_state or not self._watch_state[repo_path].get(
                "watch_running", False
            ):
                logger.warning(f"No watch running for {repo_path}")
                return {
                    "status": "error",
                    "message": "Watch not running",
                }

            try:
                # Stop watch instance
                watch_instance = self._watch_state[repo_path]["watch_instance"]
                result = watch_instance.stop_watch()

                # Clear state
                del self._watch_state[repo_path]

                logger.info(f"Auto-watch stopped for {repo_path}")
                return {
                    "status": "success",
                    "message": "Watch stopped",
                    "stats": result.get("stats", {}),
                }

            except Exception as e:
                logger.exception(f"Error stopping auto-watch for {repo_path}: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to stop watch: {str(e)}",
                }

    def reset_timeout(self, repo_path: str) -> Dict[str, Any]:
        """
        Reset auto-stop timer on file activity.

        Args:
            repo_path: Repository path

        Returns:
            Status dictionary with success/error status
        """
        with self._lock:
            if repo_path not in self._watch_state or not self._watch_state[repo_path].get(
                "watch_running", False
            ):
                logger.warning(f"No watch running for {repo_path}, cannot reset timeout")
                return {
                    "status": "error",
                    "message": "Watch not running",
                }

            # Update last activity timestamp
            self._watch_state[repo_path]["last_activity"] = datetime.now()
            logger.debug(f"Timeout reset for {repo_path}")

            return {
                "status": "success",
                "message": "Timeout reset",
            }

    def _timeout_checker_loop(self) -> None:
        """
        Background thread loop that checks for timeout expiration every 30 seconds.

        Runs until shutdown event is set.
        """
        logger.info("Timeout checker loop started")
        while not self._shutdown_event.is_set():
            # Wait for check interval or until shutdown event
            if self._shutdown_event.wait(timeout=self.TIMEOUT_CHECK_INTERVAL_SECONDS):
                break  # Shutdown requested

            # Check for expired timeouts
            try:
                self._check_timeouts()
            except Exception as e:
                logger.exception(f"Error in timeout checker loop: {e}")

        logger.info("Timeout checker loop stopped")

    def _check_timeouts(self) -> None:
        """
        Check all watches for timeout expiration and stop expired ones.

        Called periodically by background thread (every 30 seconds) to enforce auto-stop.
        """
        with self._lock:
            repos_to_stop = []

            for repo_path, state in self._watch_state.items():
                if not state.get("watch_running", False):
                    continue

                last_activity = state["last_activity"]
                timeout_seconds = state["timeout_seconds"]
                elapsed = (datetime.now() - last_activity).total_seconds()

                if elapsed > timeout_seconds:
                    logger.info(
                        f"Watch timeout expired for {repo_path} "
                        f"({elapsed:.1f}s > {timeout_seconds}s)"
                    )
                    repos_to_stop.append(repo_path)

            # Stop expired watches (outside iteration to avoid dict modification during iteration)
            for repo_path in repos_to_stop:
                try:
                    watch_instance = self._watch_state[repo_path]["watch_instance"]
                    watch_instance.stop_watch()
                    del self._watch_state[repo_path]
                    logger.info(f"Auto-stopped watch for {repo_path} due to timeout")
                except Exception as e:
                    logger.exception(f"Error auto-stopping watch for {repo_path}: {e}")

    def shutdown(self) -> None:
        """
        Shutdown AutoWatchManager and stop background timeout checker thread.

        Should be called when server is shutting down to ensure clean resource cleanup.
        """
        logger.info("Shutting down AutoWatchManager...")

        # Signal background thread to stop
        self._shutdown_event.set()

        # Wait for thread to terminate (with timeout)
        if self._timeout_thread.is_alive():
            self._timeout_thread.join(timeout=self.SHUTDOWN_THREAD_JOIN_TIMEOUT_SECONDS)
            if self._timeout_thread.is_alive():
                logger.warning(
                    f"Timeout checker thread did not stop within "
                    f"{self.SHUTDOWN_THREAD_JOIN_TIMEOUT_SECONDS} seconds"
                )
            else:
                logger.info("Timeout checker thread stopped successfully")

        # Stop all active watches
        with self._lock:
            repos_to_stop = list(self._watch_state.keys())

        for repo_path in repos_to_stop:
            try:
                self.stop_watch(repo_path)
            except Exception as e:
                logger.exception(f"Error stopping watch during shutdown for {repo_path}: {e}")

        logger.info("AutoWatchManager shutdown complete")

    def get_state(self, repo_path: str) -> Optional[Dict[str, Any]]:
        """
        Get current watch state for repository.

        Args:
            repo_path: Repository path

        Returns:
            Watch state dictionary or None if no watch running
        """
        with self._lock:
            if repo_path not in self._watch_state:
                return None

            state = self._watch_state[repo_path]
            return {
                "watch_running": state.get("watch_running", False),
                "last_activity": state.get("last_activity"),
                "timeout_seconds": state.get("timeout_seconds"),
            }


# Singleton instance
auto_watch_manager = AutoWatchManager()
