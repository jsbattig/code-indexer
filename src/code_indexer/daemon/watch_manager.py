"""DaemonWatchManager - Story #472.

Manages watch mode lifecycle within the daemon process, enabling
non-blocking RPC operations and concurrent query handling.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class _WatchStarting:
    """Sentinel for watch starting state."""

    def is_watching(self) -> bool:
        """Return False as watch is still starting."""
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return starting status."""
        return {"status": "starting"}


class _WatchError:
    """Sentinel for watch error state."""

    def __init__(self, error: str):
        """Initialize with error message."""
        self.error = error

    def is_watching(self) -> bool:
        """Return False as watch failed."""
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return error status."""
        return {"status": "error", "error": self.error}


# Global sentinel instances
WATCH_STARTING = _WatchStarting()


class DaemonWatchManager:
    """Manages watch mode in daemon with non-blocking background threads.

    This component solves the critical issue where watch mode blocked the
    daemon's RPC thread, preventing concurrent operations. It manages the
    watch lifecycle in a background thread, allowing the daemon to remain
    responsive to queries and other operations.
    """

    def __init__(self):
        """Initialize the watch manager."""
        self.watch_thread: Optional[threading.Thread] = None
        self.watch_handler: Optional[Any] = None  # GitAwareWatchHandler instance
        self.project_path: Optional[str] = None
        self.start_time: Optional[float] = None
        self._lock = threading.Lock()  # Thread safety for state management
        self._stop_event = threading.Event()  # Signal to stop watch thread

    def is_running(self) -> bool:
        """Check if watch is currently running.

        Returns:
            True if watch thread is active and alive, False otherwise
        """
        with self._lock:
            return self._is_running_unsafe()

    def _is_running_unsafe(self) -> bool:
        """Internal version of is_running without lock (must be called with lock held)."""
        return (
            self.watch_thread is not None
            and self.watch_thread.is_alive()
            and self.watch_handler is not None
        )

    def start_watch(self, project_path: str, config: Any, **kwargs) -> Dict[str, Any]:
        """Start watch mode in background thread (non-blocking).

        Args:
            project_path: Path to the project to watch
            config: Configuration for the watch handler
            **kwargs: Additional arguments for watch handler

        Returns:
            Status dictionary with success/error status and message
        """
        with self._lock:
            # Check if already running
            if self._is_running_unsafe():
                logger.warning(f"Watch already running for project: {self.project_path}")
                return {
                    "status": "error",
                    "message": f"Watch already running for {self.project_path}"
                }

            # Reset stop event
            self._stop_event.clear()

            # Store configuration
            self.project_path = project_path
            self.start_time = time.time()

            # Set placeholder handler to indicate watch is starting
            # This prevents race condition where multiple starts can happen
            # before the thread sets the real handler
            self.watch_handler = WATCH_STARTING

            # Start watch in background thread
            self.watch_thread = threading.Thread(
                target=self._watch_thread_worker,
                args=(project_path, config),
                kwargs=kwargs,
                name="DaemonWatchThread",
                daemon=True  # Daemon thread will exit when main process exits
            )

            self.watch_thread.start()

            logger.info(f"Watch started in background for project: {project_path}")
            return {
                "status": "success",
                "message": "Watch started in background"
            }

    def stop_watch(self) -> Dict[str, Any]:
        """Stop watch mode gracefully.

        Returns:
            Status dictionary with success/error status, message, and statistics
        """
        with self._lock:
            # Check if running
            if not self.watch_handler and not self.watch_thread:
                logger.warning("No watch running to stop")
                return {
                    "status": "error",
                    "message": "Watch not running"
                }

            stats = {}

            # Get statistics before stopping
            if (
                self.watch_handler
                and not isinstance(self.watch_handler, _WatchStarting)
                and hasattr(self.watch_handler, "get_stats")
            ):
                try:
                    stats = self.watch_handler.get_stats()
                except Exception as e:
                    logger.error(f"Failed to get watch stats: {e}")

            # Signal stop
            self._stop_event.set()

            # Stop the watch handler
            if self.watch_handler and not isinstance(self.watch_handler, _WatchStarting):
                try:
                    self.watch_handler.stop_watching()
                except Exception as e:
                    logger.error(f"Error stopping watch handler: {e}")

            # Wait for thread to finish (max 5 seconds)
            if self.watch_thread and self.watch_thread.is_alive():
                self.watch_thread.join(timeout=5.0)

                if self.watch_thread.is_alive():
                    logger.warning("Watch thread did not stop within 5 seconds")

            # Clean up state
            self.watch_thread = None
            self.watch_handler = None
            project = self.project_path
            self.project_path = None
            self.start_time = None

            logger.info(f"Watch stopped for project: {project}")
            return {
                "status": "success",
                "message": "Watch stopped",
                "stats": stats
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get current watch statistics.

        Returns:
            Dictionary with watch status and statistics
        """
        with self._lock:
            if not self._is_running_unsafe():
                return {
                    "status": "idle",
                    "project_path": None,
                    "uptime_seconds": 0,
                    "files_processed": 0
                }

            uptime = time.time() - self.start_time if self.start_time else 0

            # Get handler statistics
            handler_stats = {}
            if (
                self.watch_handler
                and not isinstance(self.watch_handler, _WatchStarting)
                and hasattr(self.watch_handler, "get_stats")
            ):
                try:
                    handler_stats = self.watch_handler.get_stats()
                except Exception as e:
                    logger.error(f"Failed to get handler stats: {e}")

            return {
                "status": "running",
                "project_path": self.project_path,
                "uptime_seconds": uptime,
                "files_processed": handler_stats.get("files_processed", 0),
                "indexing_cycles": handler_stats.get("indexing_cycles", 0),
                **handler_stats  # Include all handler stats
            }

    def _watch_thread_worker(self, project_path: str, config: Any, **kwargs):
        """Worker method for watch thread.

        This runs in the background thread and manages the watch handler lifecycle.

        Args:
            project_path: Path to the project to watch
            config: Configuration for the watch handler
            **kwargs: Additional arguments for watch handler
        """
        try:
            logger.info(f"Watch thread starting for {project_path}")

            # Create watch handler
            handler = self._create_watch_handler(project_path, config, **kwargs)

            # Store handler reference
            with self._lock:
                self.watch_handler = handler

            # Start watching
            handler.start_watching()

            # Keep thread alive while watch is active and not stopped
            # Use efficient wait with timeout instead of busy waiting
            while True:
                # Check for stop event
                if self._stop_event.wait(timeout=1.0):
                    logger.info("Stop event received, exiting watch thread")
                    break

                # Check if handler is still alive
                if hasattr(handler, "is_watching") and not handler.is_watching():
                    logger.info("Watch handler stopped internally")
                    break

        except Exception as e:
            logger.error(f"Watch thread error: {e}", exc_info=True)
            with self._lock:
                # Store error in handler for status reporting
                self.watch_handler = _WatchError(str(e))
        finally:
            # Clean up on exit
            logger.info(f"Watch thread exiting for {project_path}")
            with self._lock:
                self.watch_thread = None
                self.watch_handler = None
                self.project_path = None
                self.start_time = None

    def _create_watch_handler(self, project_path: str, config: Any, **kwargs) -> Any:
        """Create and configure a GitAwareWatchHandler instance.

        Args:
            project_path: Path to the project to watch
            config: Configuration for the watch handler
            **kwargs: Additional arguments for watch handler

        Returns:
            Configured GitAwareWatchHandler instance

        Raises:
            Exception: If handler creation fails
        """
        # Import here to avoid circular dependencies and lazy loading
        from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler
        from code_indexer.config import ConfigManager
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.services.embedding_factory import EmbeddingProviderFactory
        from code_indexer.services.smart_indexer import SmartIndexer
        from code_indexer.services.git_topology_service import GitTopologyService
        from code_indexer.services.watch_metadata import WatchMetadata

        try:
            # Initialize configuration if not provided
            if config is None:
                config_manager = ConfigManager.create_with_backtrack(Path(project_path))
                config = config_manager.get_config()
            else:
                config_manager = ConfigManager.create_with_backtrack(Path(project_path))

            # Create embedding provider and vector store
            embedding_provider = EmbeddingProviderFactory.create(config=config)
            backend = BackendFactory.create(config, Path(project_path))
            vector_store_client = backend.get_vector_store_client()

            # Initialize SmartIndexer
            metadata_path = config_manager.config_path.parent / "metadata.json"
            smart_indexer = SmartIndexer(
                config, embedding_provider, vector_store_client, metadata_path
            )

            # Initialize git topology service
            git_topology_service = GitTopologyService(config.codebase_dir)

            # Initialize watch metadata
            watch_metadata_path = config_manager.config_path.parent / "watch_metadata.json"
            watch_metadata = WatchMetadata.load_from_disk(watch_metadata_path)

            # Create watch handler
            debounce_seconds = kwargs.get("debounce_seconds", 2.0)
            watch_handler = GitAwareWatchHandler(
                config=config,
                smart_indexer=smart_indexer,
                git_topology_service=git_topology_service,
                watch_metadata=watch_metadata,
                debounce_seconds=debounce_seconds,
            )

            logger.info(f"Watch handler created successfully for {project_path}")
            return watch_handler

        except Exception as e:
            logger.error(f"Failed to create watch handler: {e}", exc_info=True)
            raise