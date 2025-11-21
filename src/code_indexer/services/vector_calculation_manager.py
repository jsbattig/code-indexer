"""
Multi-threaded vector calculation manager for parallel embedding computation.

Provides thread pool management for calculating embeddings in parallel while keeping
file I/O, chunking, and Filesystem operations in the main thread.
"""

import logging
import threading
import time
from pathlib import Path

# import concurrent.futures - not needed
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
import copy

from .embedding_provider import EmbeddingProvider
from ..utils.log_path_helper import get_debug_log_path

logger = logging.getLogger(__name__)


class ThrottlingStatus(Enum):
    """Throttling status indicators for display."""

    FULL_SPEED = "⚡"  # No throttling detected
    SERVER_THROTTLED = "🔴"  # Server-side throttling detected


@dataclass(frozen=True)
class VectorTask:
    """Task for vector calculation in worker thread."""

    task_id: str
    chunk_texts: Tuple[str, ...]  # Changed from List to Tuple for immutability
    metadata: Dict[str, Any]
    created_at: float

    def __post_init__(self):
        """Protect from external mutation by converting to immutable types."""
        # Use object.__setattr__ to modify frozen dataclass during initialization
        if not isinstance(self.chunk_texts, tuple):
            object.__setattr__(self, "chunk_texts", tuple(self.chunk_texts))
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @classmethod
    def create_immutable(
        cls, task_id: str, chunk_texts, metadata: Dict[str, Any], created_at: float
    ) -> "VectorTask":
        """
        Factory method for creating immutable VectorTask instances.

        Simplifies construction by handling type conversion explicitly.
        """
        return cls(
            task_id=task_id,
            chunk_texts=(
                tuple(chunk_texts)
                if not isinstance(chunk_texts, tuple)
                else chunk_texts
            ),
            metadata=copy.deepcopy(metadata),
            created_at=created_at,
        )

    @property
    def batch_size(self) -> int:
        """Return the number of chunks in this batch."""
        return len(self.chunk_texts)

    @property
    def chunk_text(self) -> str:
        """Property for single chunk access."""
        # Fixed: Use early returns to eliminate deep nesting (CLAUDE.md Foundation #8)
        if len(self.chunk_texts) == 0:
            return ""

        if len(self.chunk_texts) == 1:
            return self.chunk_texts[0]

        raise ValueError(
            f"Cannot access chunk_text on batch with {len(self.chunk_texts)} chunks. Use chunk_texts instead."
        )


@dataclass(frozen=True)
class VectorResult:
    """Result from vector calculation."""

    task_id: str
    embeddings: Tuple[
        Tuple[float, ...], ...
    ]  # Changed from List to Tuple for immutability
    metadata: Dict[str, Any]
    processing_time: float
    error: Optional[str] = None

    def __post_init__(self):
        """Protect from external mutation by converting to immutable types."""
        # Use object.__setattr__ to modify frozen dataclass during initialization
        if not isinstance(self.embeddings, tuple):
            # Convert nested lists to tuples
            immutable_embeddings = tuple(
                tuple(embedding) if isinstance(embedding, list) else embedding
                for embedding in self.embeddings
            )
            object.__setattr__(self, "embeddings", immutable_embeddings)
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @classmethod
    def create_immutable(
        cls,
        task_id: str,
        embeddings,
        metadata: Dict[str, Any],
        processing_time: float,
        error: Optional[str] = None,
    ) -> "VectorResult":
        """
        Factory method for creating immutable VectorResult instances.

        Simplifies construction by handling type conversion explicitly.
        """
        # Convert nested lists to immutable tuples
        if isinstance(embeddings, (list, tuple)):
            immutable_embeddings = tuple(
                tuple(embedding) if isinstance(embedding, list) else embedding
                for embedding in embeddings
            )
        else:
            immutable_embeddings = ()

        return cls(
            task_id=task_id,
            embeddings=immutable_embeddings,
            metadata=copy.deepcopy(metadata),
            processing_time=processing_time,
            error=error,
        )

    @property
    def batch_size(self) -> int:
        """Return the number of embeddings in this batch."""
        return len(self.embeddings)

    @property
    def embedding(self) -> List[float]:
        """Property for single embedding access."""
        # Fixed: Use early returns to eliminate deep nesting (CLAUDE.md Foundation #8)
        if len(self.embeddings) == 0:
            return []

        if len(self.embeddings) == 1:
            return list(self.embeddings[0])  # Convert tuple to list format

        raise ValueError(
            f"Cannot access embedding on batch with {len(self.embeddings)} embeddings. Use embeddings instead."
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
    server_throttle_count: int = 0
    total_embeddings_processed: int = 0  # CRITICAL FIX: Track actual embedding counts


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
        config_dir: Optional[Path] = None,
    ):
        """
        Initialize vector calculation manager.

        Args:
            embedding_provider: Provider for generating embeddings
            thread_count: Number of worker threads
            max_queue_size: Maximum size of task queue
            config_dir: Path to .code-indexer directory for debug logs
        """
        self.embedding_provider = embedding_provider
        self.thread_count = thread_count
        self.max_queue_size = max_queue_size
        self.config_dir = config_dir

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
                embeddings=(),  # Updated for immutable batch structure
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

        # Create task (convert single chunk to batch format)
        task = VectorTask(
            task_id=task_id,
            chunk_texts=(chunk_text,),  # Convert single chunk to immutable batch format
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

    def submit_task(
        self, chunk_text: str, metadata: Dict[str, Any]
    ) -> "Future[VectorResult]":
        """
        Submit a single text chunk for vector calculation.

        Wraps single chunks for efficient batch processing while preserving
        the original API interface and behavior patterns.

        Args:
            chunk_text: Text to calculate embedding for
            metadata: Associated metadata for the chunk

        Returns:
            Future that will contain VectorResult with single embedding when complete
        """
        # Convert single chunk to array for batch processing
        chunk_texts = [chunk_text]

        # Use batch processing infrastructure
        batch_future = self.submit_batch_task(chunk_texts, metadata)

        # Create wrapper future that extracts single result
        single_future: Future[VectorResult] = Future()

        def extract_single_result():
            """Extract single embedding from batch result in background thread."""
            try:
                batch_result = batch_future.result()

                # Check if single_future is already done (cancelled, etc.)
                if single_future.done():
                    return

                # Extract single result from batch
                if batch_result.error is not None:
                    # Preserve error handling - same error types and messages
                    single_result = VectorResult.create_immutable(
                        task_id=batch_result.task_id,
                        embeddings=(),  # Empty on error
                        metadata=batch_result.metadata,
                        processing_time=batch_result.processing_time,
                        error=batch_result.error,
                    )
                else:
                    # Extract single embedding from batch result
                    single_result = VectorResult.create_immutable(
                        task_id=batch_result.task_id,
                        embeddings=batch_result.embeddings,  # Preserve batch structure for .embedding property
                        metadata=batch_result.metadata,
                        processing_time=batch_result.processing_time,
                        error=None,
                    )

                # Only set result if future is not already done
                if not single_future.done():
                    single_future.set_result(single_result)

            except Exception as e:
                # Only set exception if future is not already done
                if not single_future.done():
                    single_future.set_exception(e)

        # Process extraction in background thread
        extraction_thread = threading.Thread(target=extract_single_result, daemon=True)
        extraction_thread.start()

        return single_future

    def submit_batch_task(
        self, chunk_texts: List[str], metadata: Dict[str, Any]
    ) -> "Future[VectorResult]":
        """
        Submit a batch of text chunks for vector calculation.

        Args:
            chunk_texts: List of text chunks to calculate embeddings for
            metadata: Associated metadata for the batch

        Returns:
            Future that will contain VectorResult when complete

        Raises:
            RuntimeError: If thread pool is not available
            TypeError: If chunk_texts is None or metadata is None
        """
        # Validate inputs early
        if chunk_texts is None:
            raise TypeError("chunk_texts cannot be None")
        if metadata is None:
            raise TypeError("metadata cannot be None")

        if not self.is_running:
            self.start()

        # Check for cancellation before submitting new tasks
        if self.cancellation_event.is_set():
            # Return a completed future with cancellation error
            cancelled_future: Future[VectorResult] = Future()
            cancelled_result = VectorResult(
                task_id="cancelled",
                embeddings=(),
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

        # Create batch task using factory method
        task = VectorTask.create_immutable(
            task_id=task_id,
            chunk_texts=chunk_texts,
            metadata=metadata,
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
        Calculate vector embedding for a task using batch processing (runs in worker thread).

        Args:
            task: VectorTask to process (contains multiple chunks)

        Returns:
            VectorResult with embeddings array or error
        """
        start_time = time.time()

        # Check for cancellation before processing
        if self.cancellation_event.is_set():
            return VectorResult(
                task_id=task.task_id,
                embeddings=(),  # Updated for immutable batch structure
                metadata=task.metadata,
                processing_time=time.time() - start_time,
                error="Cancelled",
            )

        try:
            # Check for cancellation again before making API call
            if self.cancellation_event.is_set():
                return VectorResult(
                    task_id=task.task_id,
                    embeddings=(),
                    metadata=task.metadata,
                    processing_time=time.time() - start_time,
                    error="Cancelled",
                )

            # CRITICAL FIX: Check for empty batch before making API call
            if len(task.chunk_texts) == 0:
                # Return early for empty batch - no API call needed
                return VectorResult(
                    task_id=task.task_id,
                    embeddings=(),
                    metadata=task.metadata,
                    processing_time=time.time() - start_time,
                    error=None,
                )

            # Calculate embeddings using batch processing API
            chunk_texts_list = list(task.chunk_texts)  # Convert tuple to list for API

            # DEBUG: Log batch processing start (only if config_dir available)
            if self.config_dir:
                debug_log_path = get_debug_log_path(
                    self.config_dir, "cidx_vectorcalc_debug.log"
                )
                with open(debug_log_path, "a") as f:
                    f.write(
                        f"VectorCalc: Processing batch {task.task_id} with {len(chunk_texts_list)} chunks - STARTING API call\n"
                    )
                    f.flush()

            embeddings_list = self.embedding_provider.get_embeddings_batch(
                chunk_texts_list
            )

            processing_time = time.time() - start_time

            # DEBUG: Log batch processing complete (only if config_dir available)
            if self.config_dir:
                debug_log_path = get_debug_log_path(
                    self.config_dir, "cidx_vectorcalc_debug.log"
                )
                with open(debug_log_path, "a") as f:
                    f.write(
                        f"VectorCalc: Batch {task.task_id} COMPLETED in {processing_time:.2f}s - returned {len(embeddings_list)} embeddings\n"
                    )
                    f.flush()

            # Convert embeddings to immutable tuple format
            immutable_embeddings = tuple(tuple(emb) for emb in embeddings_list)

            # CRITICAL FIX: Count actual embeddings processed
            embeddings_count = len(immutable_embeddings)

            # Update stats
            with self.stats_lock:
                self.stats.total_tasks_completed += 1
                self.stats.total_embeddings_processed += (
                    embeddings_count  # Track actual embeddings
                )
                self.stats.total_processing_time += processing_time
                self.stats.average_processing_time = (
                    self.stats.total_processing_time / self.stats.total_tasks_completed
                )

                # CRITICAL FIX: Update rolling window using embedding count, not task count
                current_time = time.time()
                embeddings_per_second = self._update_rolling_window(
                    current_time,
                    self.stats.total_embeddings_processed,  # Use embedding count
                )
                self.stats.embeddings_per_second = embeddings_per_second

            return VectorResult(
                task_id=task.task_id,
                embeddings=immutable_embeddings,
                metadata=task.metadata,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)

            # TIMEOUT ARCHITECTURE FIX: Check for API timeout and trigger global cancellation
            # Import httpx for timeout detection
            import httpx

            if isinstance(
                e, (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout)
            ):
                logger.error(
                    f"VoyageAI API timeout for batch {task.task_id} - triggering global cancellation"
                )
                # Signal global cancellation to all workers
                self.request_cancellation()
                error_msg = f"VoyageAI API timeout - cancelling all work: {error_msg}"

            # Check if this is a server throttling error
            if self._is_server_throttling_error(e):
                self.record_server_throttle()

            # Update error stats
            with self.stats_lock:
                self.stats.total_tasks_failed += 1
                self.stats.total_tasks_completed += (
                    1  # Count as completed for queue tracking
                )
                # Note: No embeddings processed on error, so don't increment total_embeddings_processed

                # CRITICAL FIX: Update rolling window using embedding count, not task count
                current_time = time.time()
                embeddings_per_second = self._update_rolling_window(
                    current_time,
                    self.stats.total_embeddings_processed,  # Use embedding count
                )
                self.stats.embeddings_per_second = embeddings_per_second

            logger.error(
                f"Vector calculation failed for task {task.task_id}: {error_msg}"
            )

            return VectorResult(
                task_id=task.task_id,
                embeddings=(),  # Updated for immutable batch structure
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
                total_embeddings_processed=self.stats.total_embeddings_processed,  # Include new field
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
        Shutdown the thread pool with proper cleanup.

        Args:
            wait: Whether to wait for completion of running tasks
            timeout: Maximum time to wait for shutdown (default 30s)
        """
        if not self.is_running or not self.executor:
            return

        self.is_running = False

        # Set cancellation event to signal all threads
        self.cancellation_event.set()

        try:
            # Use reasonable timeout if not specified
            shutdown_timeout = timeout if timeout is not None else 30.0

            if wait and shutdown_timeout:
                # Implement timeout using thread since Python < 3.9 doesn't support timeout parameter
                import threading

                shutdown_complete = threading.Event()

                def shutdown_thread():
                    try:
                        if self.executor is not None:
                            self.executor.shutdown(wait=True)
                        shutdown_complete.set()
                    except Exception as e:
                        logger.error(f"Error in shutdown thread: {e}")
                        shutdown_complete.set()

                shutdown_worker = threading.Thread(target=shutdown_thread, daemon=True)
                shutdown_worker.start()

                # Wait for shutdown with timeout
                if shutdown_complete.wait(timeout=shutdown_timeout):
                    logger.info("Vector calculation thread pool shut down successfully")
                else:
                    logger.warning(
                        f"Vector calculation shutdown timeout after {shutdown_timeout}s - forcing shutdown"
                    )
                    # Force shutdown without wait
                    self.executor.shutdown(wait=False)
            else:
                # No timeout needed, just shutdown
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
        """Context manager exit with proper cleanup."""
        # CRITICAL FIX: Use graduated timeout based on exception status
        if exc_type is not None:
            # Exception occurred - quick shutdown to avoid delays
            self.shutdown(wait=True, timeout=5.0)
        else:
            # Normal exit - allow more time for clean shutdown
            self.shutdown(wait=True, timeout=30.0)

    def get_resolved_thread_count(self, config) -> int:
        """
        Get thread count from config.json setting directly.

        Args:
            config: Configuration object containing config.json settings

        Returns:
            Thread count from config.voyage_ai.parallel_requests
        """
        return int(config.voyage_ai.parallel_requests)

    def resolve_thread_count_with_precedence(
        self, cli_thread_count: Optional[int] = None, config=None
    ) -> Dict[str, Any]:
        """
        Get thread count from config.json setting directly.

        Args:
            cli_thread_count: Not used (removed CLI option)
            config: Configuration object containing config.json settings

        Returns:
            Dictionary with thread count and source information
        """
        count = config.voyage_ai.parallel_requests if config else 8
        return {
            "count": count,
            "source": "config.json" if config else "default",
            "message": (
                f"{count} (from config.json)" if config else f"{count} (default)"
            ),
        }

    def get_thread_count_with_source(self, config) -> Dict[str, Any]:
        """
        Get thread count from config.json setting directly.

        Args:
            config: Configuration object containing config.json settings

        Returns:
            Dictionary with thread count and source information for display
        """
        count = config.voyage_ai.parallel_requests
        return {
            "count": count,
            "source": "config.json",
            "message": f"{count} (from config.json)",
        }

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
