"""
Multi-threaded vector calculation manager for parallel embedding computation.

Provides thread pool management for calculating embeddings in parallel while keeping
file I/O, chunking, and Qdrant operations in the main thread.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List

from .embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class ThrottlingStatus(Enum):
    """Throttling status indicators for display."""

    FULL_SPEED = "⚡"  # No throttling detected
    SERVER_THROTTLED = "🔴"  # Server-side throttling detected


@dataclass
class VectorTask:
    """Task for vector calculation in worker thread."""

    task_id: str
    chunk_text: str
    metadata: Dict[str, Any]
    created_at: float


@dataclass
class VectorResult:
    """Result from vector calculation."""

    task_id: str
    embedding: List[float]
    metadata: Dict[str, Any]
    processing_time: float
    error: Optional[str] = None


@dataclass
class VectorCalculationStats:
    """Statistics for vector calculation performance."""

    total_tasks_submitted: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_processing_time: float = 0.0
    active_threads: int = 0
    queue_size: int = 0
    average_processing_time: float = 0.0
    embeddings_per_second: float = 0.0
    throttling_status: ThrottlingStatus = ThrottlingStatus.FULL_SPEED
    server_throttle_count: int = 0


@dataclass
class RollingWindowEntry:
    """Entry in rolling window for smoothed statistics."""

    timestamp: float
    completed_tasks: int


class VectorCalculationManager:
    """Manages parallel vector calculation using thread pool."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        thread_count: int,
        max_queue_size: int = 1000,
    ):
        """
        Initialize vector calculation manager.

        Args:
            embedding_provider: Provider for generating embeddings
            thread_count: Number of worker threads
            max_queue_size: Maximum size of task queue
        """
        self.embedding_provider = embedding_provider
        self.thread_count = thread_count
        self.max_queue_size = max_queue_size

        # Thread pool for vector calculations
        self.executor: Optional[ThreadPoolExecutor] = None
        self.is_running = False

        # Cancellation support
        self.cancellation_event = threading.Event()

        # Statistics tracking
        self.stats = VectorCalculationStats()
        self.stats_lock = threading.Lock()
        self.start_time = time.time()

        # Task tracking
        self.task_counter = 0
        self.task_counter_lock = threading.Lock()

        # Rolling window for smoothed embeddings per second calculation (30 second window)
        self.rolling_window_seconds = 30.0
        self.rolling_window: List[RollingWindowEntry] = []
        self.rolling_window_lock = threading.Lock()

        # Server throttling detection (track recent 429s and server errors)
        self.recent_server_throttles: List[float] = []
        self.server_throttle_window_seconds = 60.0  # 1 minute window

        logger.info(f"Initialized VectorCalculationManager with {thread_count} threads")

    def start(self):
        """Start the thread pool."""
        if self.is_running:
            return

        self.executor = ThreadPoolExecutor(
            max_workers=self.thread_count, thread_name_prefix="VectorCalc"
        )
        self.is_running = True
        self.start_time = time.time()

        logger.info(
            f"Started vector calculation thread pool with {self.thread_count} workers"
        )

    def request_cancellation(self):
        """Request cancellation of all pending and new vector calculations."""
        self.cancellation_event.set()
        logger.info("Vector calculation cancellation requested")

    def submit_chunk(
        self, chunk_text: str, metadata: Dict[str, Any]
    ) -> "Future[VectorResult]":
        """
        Submit a text chunk for vector calculation.

        Args:
            chunk_text: Text to calculate embedding for
            metadata: Associated metadata for the chunk

        Returns:
            Future that will contain VectorResult when complete
        """
        if not self.is_running:
            self.start()

        # Check for cancellation before submitting new tasks
        if self.cancellation_event.is_set():
            # Return a completed future with cancellation error
            cancelled_future: Future[VectorResult] = Future()
            cancelled_result = VectorResult(
                task_id="cancelled",
                embedding=[],
                metadata=metadata.copy(),
                processing_time=0.0,
                error="Cancelled",
            )
            cancelled_future.set_result(cancelled_result)
            return cancelled_future

        # Generate unique task ID
        with self.task_counter_lock:
            self.task_counter += 1
            task_id = f"task_{self.task_counter}"

        # Create task
        task = VectorTask(
            task_id=task_id,
            chunk_text=chunk_text,
            metadata=metadata.copy(),
            created_at=time.time(),
        )

        # Submit to thread pool
        if not self.executor:
            raise RuntimeError("Thread pool not started")
        future = self.executor.submit(self._calculate_vector, task)

        # Update stats
        with self.stats_lock:
            self.stats.total_tasks_submitted += 1
            self.stats.active_threads = min(
                self.stats.total_tasks_submitted - self.stats.total_tasks_completed,
                self.thread_count,
            )

        return future

    def _calculate_vector(self, task: VectorTask) -> VectorResult:
        """
        Calculate vector embedding for a task (runs in worker thread).

        Args:
            task: VectorTask to process

        Returns:
            VectorResult with embedding or error
        """
        start_time = time.time()

        # Check for cancellation before processing
        if self.cancellation_event.is_set():
            return VectorResult(
                task_id=task.task_id,
                embedding=[],
                metadata=task.metadata,
                processing_time=time.time() - start_time,
                error="Cancelled",
            )

        try:
            # Calculate embedding using the provider
            embedding = self.embedding_provider.get_embedding(task.chunk_text)

            processing_time = time.time() - start_time

            # Update stats
            with self.stats_lock:
                self.stats.total_tasks_completed += 1
                self.stats.total_processing_time += processing_time
                self.stats.average_processing_time = (
                    self.stats.total_processing_time / self.stats.total_tasks_completed
                )

                # Update rolling window for smoothed embeddings per second
                current_time = time.time()
                embeddings_per_second = self._update_rolling_window(
                    current_time, self.stats.total_tasks_completed
                )
                self.stats.embeddings_per_second = embeddings_per_second

            return VectorResult(
                task_id=task.task_id,
                embedding=embedding,
                metadata=task.metadata,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)

            # Check if this is a server throttling error
            if self._is_server_throttling_error(e):
                self.record_server_throttle()

            # Update error stats
            with self.stats_lock:
                self.stats.total_tasks_failed += 1
                self.stats.total_tasks_completed += (
                    1  # Count as completed for queue tracking
                )

                # Update rolling window for failed tasks too
                current_time = time.time()
                embeddings_per_second = self._update_rolling_window(
                    current_time, self.stats.total_tasks_completed
                )
                self.stats.embeddings_per_second = embeddings_per_second

            logger.error(
                f"Vector calculation failed for task {task.task_id}: {error_msg}"
            )

            return VectorResult(
                task_id=task.task_id,
                embedding=[],
                metadata=task.metadata,
                processing_time=processing_time,
                error=error_msg,
            )

    def get_stats(self) -> VectorCalculationStats:
        """Get current performance statistics."""
        with self.stats_lock:
            # Update active threads count
            self.stats.active_threads = min(
                self.stats.total_tasks_submitted - self.stats.total_tasks_completed,
                self.thread_count,
            )
            self.stats.queue_size = (
                self.stats.total_tasks_submitted - self.stats.total_tasks_completed
            )

            # Update throttling status based on recent server throttles
            self._update_throttling_status()

            # Return copy of stats
            return VectorCalculationStats(
                total_tasks_submitted=self.stats.total_tasks_submitted,
                total_tasks_completed=self.stats.total_tasks_completed,
                total_tasks_failed=self.stats.total_tasks_failed,
                total_processing_time=self.stats.total_processing_time,
                active_threads=self.stats.active_threads,
                queue_size=self.stats.queue_size,
                average_processing_time=self.stats.average_processing_time,
                embeddings_per_second=self.stats.embeddings_per_second,
                throttling_status=self.stats.throttling_status,
                server_throttle_count=self.stats.server_throttle_count,
            )

    def wait_for_all_tasks(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all submitted tasks to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if all tasks completed, False if timeout occurred
        """
        if not self.executor:
            return True

        # Wait for all tasks to complete
        start_wait = time.time()
        while True:
            current_stats = self.get_stats()
            if current_stats.queue_size == 0:
                break
            if timeout and (time.time() - start_wait) > timeout:
                return False
            time.sleep(0.1)

        return True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None):
        """
        Shutdown the thread pool.

        Args:
            wait: Whether to wait for completion of running tasks
            timeout: Maximum time to wait for shutdown
        """
        if not self.is_running or not self.executor:
            return

        self.is_running = False

        try:
            self.executor.shutdown(wait=wait)
            logger.info("Vector calculation thread pool shut down successfully")
        except Exception as e:
            logger.error(f"Error during thread pool shutdown: {e}")
        finally:
            self.executor = None

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown(wait=True, timeout=30.0)

    def get_resolved_thread_count(self, config) -> int:
        """
        Get resolved thread count respecting configuration hierarchy.

        Args:
            config: Configuration object containing config.json settings

        Returns:
            Resolved thread count from configuration hierarchy
        """
        thread_info = resolve_thread_count_with_precedence(
            self.embedding_provider, cli_thread_count=None, config=config
        )
        return int(thread_info["count"])

    def resolve_thread_count_with_precedence(
        self, cli_thread_count: Optional[int] = None, config=None
    ) -> Dict[str, Any]:
        """
        Resolve thread count using configuration hierarchy: CLI → config.json → provider defaults.

        Args:
            cli_thread_count: Thread count specified via CLI option (highest priority)
            config: Configuration object containing config.json settings

        Returns:
            Dictionary with resolved thread count and source information
        """
        return resolve_thread_count_with_precedence(
            self.embedding_provider, cli_thread_count, config
        )

    def get_thread_count_with_source(self, config) -> Dict[str, Any]:
        """
        Get thread count with accurate source messaging (replaces misleading 'auto-detected').

        Args:
            config: Configuration object containing config.json settings

        Returns:
            Dictionary with thread count and source information for display
        """
        return resolve_thread_count_with_precedence(
            self.embedding_provider, cli_thread_count=None, config=config
        )

    def get_unified_thread_count(self, config) -> int:
        """
        Get unified thread count that matches HTTP component configuration.

        Args:
            config: Configuration object containing config.json settings

        Returns:
            Thread count that ensures consistency across HTTP and vector components
        """
        return self.get_resolved_thread_count(config)

    def _update_rolling_window(
        self, current_time: float, total_completed: int
    ) -> float:
        """
        Update rolling window for smoothed embeddings per second calculation.

        Args:
            current_time: Current timestamp
            total_completed: Total tasks completed so far

        Returns:
            Calculated embeddings per second value
        """
        with self.rolling_window_lock:
            # Add current entry
            entry = RollingWindowEntry(
                timestamp=current_time, completed_tasks=total_completed
            )
            self.rolling_window.append(entry)

            # Remove entries older than rolling window
            cutoff_time = current_time - self.rolling_window_seconds
            self.rolling_window = [
                e for e in self.rolling_window if e.timestamp >= cutoff_time
            ]

            # Calculate smoothed embeddings per second
            if len(self.rolling_window) >= 2:
                # Get oldest and newest entries in window
                oldest = self.rolling_window[0]
                newest = self.rolling_window[-1]

                time_diff = newest.timestamp - oldest.timestamp
                task_diff = newest.completed_tasks - oldest.completed_tasks

                if time_diff > 0:
                    return task_diff / time_diff
                else:
                    # Fall back to total average if window is too small
                    elapsed_total = current_time - self.start_time
                    if elapsed_total > 0:
                        return total_completed / elapsed_total
                    else:
                        return 0.0
            else:
                # Fall back to total average if not enough data points
                elapsed_total = current_time - self.start_time
                if elapsed_total > 0:
                    return total_completed / elapsed_total
                else:
                    return 0.0

    def record_server_throttle(self):
        """Record a server throttling event (429, API slowness, etc.)."""
        current_time = time.time()
        with self.stats_lock:
            self.recent_server_throttles.append(current_time)
            self.stats.server_throttle_count += 1

            # Clean up old entries outside the window
            cutoff_time = current_time - self.server_throttle_window_seconds
            self.recent_server_throttles = [
                t for t in self.recent_server_throttles if t >= cutoff_time
            ]

    def _update_throttling_status(self):
        """Update throttling status based on recent server throttling events."""
        current_time = time.time()

        # Clean up old server throttle entries
        cutoff_time = current_time - self.server_throttle_window_seconds
        self.recent_server_throttles = [
            t for t in self.recent_server_throttles if t >= cutoff_time
        ]

        # Determine throttling status based on recent server throttles
        # If we've had 3+ server throttles in the last minute, show as server throttled
        if len(self.recent_server_throttles) >= 3:
            self.stats.throttling_status = ThrottlingStatus.SERVER_THROTTLED
        else:
            self.stats.throttling_status = ThrottlingStatus.FULL_SPEED

    def _is_server_throttling_error(self, exception: Exception) -> bool:
        """Check if an exception indicates server-side throttling."""
        error_msg = str(exception).lower()

        # Look for common server throttling indicators
        throttling_indicators = [
            "429",  # HTTP 429 Too Many Requests
            "rate limit",
            "rate_limit",
            "too many requests",
            "quota exceeded",
            "throttle",
            "throttling",
            "timeout",
            "slow response",
            "server overload",
        ]

        return any(indicator in error_msg for indicator in throttling_indicators)


def get_default_thread_count(embedding_provider: EmbeddingProvider) -> int:
    """
    Get default thread count based on embedding provider.

    Args:
        embedding_provider: The embedding provider being used

    Returns:
        Recommended thread count for the provider
    """
    provider_name = embedding_provider.get_provider_name().lower()

    if provider_name == "voyage-ai":
        # VoyageAI can handle parallel requests efficiently
        return 8
    elif provider_name == "ollama":
        # Ollama runs locally, avoid resource contention
        return 1
    else:
        # Conservative default for unknown providers
        return 2


def resolve_thread_count_with_precedence(
    embedding_provider: EmbeddingProvider,
    cli_thread_count: Optional[int] = None,
    config=None,
) -> Dict[str, Any]:
    """
    Resolve thread count using configuration hierarchy: CLI → config.json → provider defaults.

    Args:
        embedding_provider: The embedding provider being used
        cli_thread_count: Thread count specified via CLI option (highest priority)
        config: Configuration object containing config.json settings

    Returns:
        Dictionary with resolved thread count and source information:
        {
            "count": int,           # Resolved thread count
            "source": str,          # Source: "cli", "config.json", or "provider_default"
            "message": str          # Human-readable message for display
        }
    """
    provider_name = embedding_provider.get_provider_name().lower()

    # Priority 1: CLI option (highest)
    if cli_thread_count is not None:
        return {
            "count": cli_thread_count,
            "source": "cli",
            "message": f"{cli_thread_count} (from CLI option)",
        }

    # Priority 2: config.json setting (medium)
    if config is not None:
        config_thread_count = None

        if (
            provider_name == "voyage-ai"
            and hasattr(config, "voyage_ai")
            and config.voyage_ai
        ):
            config_thread_count = config.voyage_ai.parallel_requests
        elif provider_name == "ollama" and hasattr(config, "ollama") and config.ollama:
            config_thread_count = config.ollama.num_parallel

        if config_thread_count is not None:
            return {
                "count": config_thread_count,
                "source": "config.json",
                "message": f"{config_thread_count} (from config.json)",
            }

    # Priority 3: Provider defaults (fallback)
    default_count = get_default_thread_count(embedding_provider)
    return {
        "count": default_count,
        "source": "provider_default",
        "message": f"{default_count} (provider default for {provider_name})",
    }
