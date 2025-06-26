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
from typing import Dict, Any, Optional, List
from enum import Enum

from .embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


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


class ThrottlingStatus(Enum):
    """Throttling status indicators for progress display."""

    FULL_SPEED = "⚡"  # No throttling - operating at full speed
    CLIENT_THROTTLED = (
        "🟡"  # CIDX-initiated throttling (our rate limiter is slowing requests)
    )
    SERVER_THROTTLED = (
        "🔴"  # Server-side throttling detected (429 errors, API slowness)
    )


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
    client_wait_time: float = 0.0  # Time spent waiting due to CIDX rate limiting
    server_throttle_count: int = 0  # Number of server throttle events (429s, slowness)


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

        # Throttling detection
        self.throttling_detection_window = (
            10.0  # 10 second window for throttling detection
        )
        self.recent_wait_events: List[tuple] = (
            []
        )  # Track recent client wait events (timestamp, wait_time)
        self.recent_server_throttles: List[float] = (
            []
        )  # Track recent server throttles with timestamps
        self.total_requests_in_window = (
            0  # Track total requests for percentage calculation
        )

        # Set up throttling callback for VoyageAI
        self._setup_throttling_callback()

        logger.info(f"Initialized VectorCalculationManager with {thread_count} threads")

    def _setup_throttling_callback(self):
        """Set up throttling callback for supported embedding providers."""
        # Check if this is a VoyageAI provider and set up callback
        if hasattr(self.embedding_provider, "set_throttling_callback"):

            def throttling_callback(event_type: str, value: Optional[float]):
                if event_type == "client_wait" and value is not None:
                    self.record_client_wait_time(value)
                elif event_type == "server_throttle":
                    self.record_server_throttle()

            self.embedding_provider.set_throttling_callback(throttling_callback)

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
                self._update_rolling_window(
                    current_time, self.stats.total_tasks_completed
                )

            return VectorResult(
                task_id=task.task_id,
                embedding=embedding,
                metadata=task.metadata,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)

            # Update error stats
            with self.stats_lock:
                self.stats.total_tasks_failed += 1
                self.stats.total_tasks_completed += (
                    1  # Count as completed for queue tracking
                )

                # Update rolling window for failed tasks too
                current_time = time.time()
                self._update_rolling_window(
                    current_time, self.stats.total_tasks_completed
                )

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

            # Update throttling status before returning stats
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
                client_wait_time=self.stats.client_wait_time,
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

    def _update_rolling_window(self, current_time: float, total_completed: int):
        """
        Update rolling window for smoothed embeddings per second calculation.

        Args:
            current_time: Current timestamp
            total_completed: Total tasks completed so far
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
                    self.stats.embeddings_per_second = task_diff / time_diff
                else:
                    # Fall back to total average if window is too small
                    elapsed_total = current_time - self.start_time
                    if elapsed_total > 0:
                        self.stats.embeddings_per_second = (
                            total_completed / elapsed_total
                        )
            else:
                # Fall back to total average if not enough data points
                elapsed_total = current_time - self.start_time
                if elapsed_total > 0:
                    self.stats.embeddings_per_second = total_completed / elapsed_total

    def record_client_wait_time(self, wait_time: float):
        """Record CIDX-initiated wait time (our rate limiter slowing requests)."""
        if wait_time > 0:
            current_time = time.time()
            # Only record significant waits (> 0.1s) for throttling detection
            if wait_time > 0.1:
                self.recent_wait_events.append((current_time, wait_time))

            with self.stats_lock:
                self.stats.client_wait_time += wait_time

            # Clean old entries
            cutoff_time = current_time - self.throttling_detection_window
            self.recent_wait_events = [
                (t, w) for t, w in self.recent_wait_events if t >= cutoff_time
            ]

    def record_server_throttle(self):
        """Record server-side throttling (429 responses, API slowness)."""
        current_time = time.time()
        self.recent_server_throttles.append(current_time)

        with self.stats_lock:
            self.stats.server_throttle_count += 1

        # Clean old entries
        cutoff_time = current_time - self.throttling_detection_window
        self.recent_server_throttles = [
            t for t in self.recent_server_throttles if t >= cutoff_time
        ]

    def _update_throttling_status(self):
        """Update throttling status based on recent activity."""
        current_time = time.time()
        cutoff_time = current_time - self.throttling_detection_window

        # Clean old entries
        self.recent_wait_events = [
            (t, w) for t, w in self.recent_wait_events if t >= cutoff_time
        ]
        self.recent_server_throttles = [
            t for t in self.recent_server_throttles if t >= cutoff_time
        ]

        # Determine throttling status
        server_throttles_recent = len(self.recent_server_throttles)

        if server_throttles_recent > 0:
            # Server-side throttling detected (429s, API issues) - takes priority
            self.stats.throttling_status = ThrottlingStatus.SERVER_THROTTLED
        elif self.recent_wait_events:
            # Analyze client throttling more intelligently
            total_wait_time = sum(wait_time for _, wait_time in self.recent_wait_events)
            avg_wait_time = total_wait_time / len(self.recent_wait_events)

            # Only show as throttled if:
            # 1. More than 5 significant waits (> 0.1s) in 10 seconds, AND
            # 2. Average wait time is > 0.5s (indicating real throttling)
            if len(self.recent_wait_events) > 5 and avg_wait_time > 0.5:
                self.stats.throttling_status = ThrottlingStatus.CLIENT_THROTTLED
            else:
                # Occasional small waits are normal, not real throttling
                self.stats.throttling_status = ThrottlingStatus.FULL_SPEED
        else:
            # No significant waits detected
            self.stats.throttling_status = ThrottlingStatus.FULL_SPEED


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
