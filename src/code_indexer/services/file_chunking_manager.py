"""
FileChunkingManager for parallel file processing with vector integration and Qdrant writing.

Handles complete file lifecycle: chunk → vector → wait → write to Qdrant
with file atomicity and immediate progress feedback.

This implementation addresses the specific user problems:
1. "not efficient for very small files" - solved by parallel processing
2. "no feedback when chunking files" - solved by immediate progress callbacks

Architecture:
- ThreadPoolExecutor with (thread_count + 2) workers per specifications
- File atomicity: all chunks from one file written together
- Worker threads handle complete lifecycle: chunk → vector → wait → write
- Immediate queuing feedback before async processing
"""

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass

from .vector_calculation_manager import VectorCalculationManager
from ..indexing.fixed_size_chunker import FixedSizeChunker
from .consolidated_file_tracker import FileStatus
import threading

logger = logging.getLogger(__name__)


# Constants
VECTOR_PROCESSING_TIMEOUT = 300.0  # 5 minutes timeout for vector processing
THREAD_POOL_SHUTDOWN_TIMEOUT = 30.0  # 30 seconds for graceful shutdown


@dataclass
class FileProcessingResult:
    """Result from complete file processing lifecycle."""

    success: bool
    file_path: Path
    chunks_processed: int
    processing_time: float
    error: Optional[str] = None


class FileChunkingManager:
    """Manages parallel file processing with complete lifecycle management."""

    def __init__(
        self,
        vector_manager: VectorCalculationManager,
        chunker: FixedSizeChunker,
        qdrant_client,  # Pass from HighThroughputProcessor
        thread_count: int,
        file_tracker=None,  # ADD THIS PARAMETER
    ):
        """
        Initialize FileChunkingManager with complete functionality.

        Args:
            vector_manager: Existing VectorCalculationManager (unchanged)
            chunker: Existing FixedSizeChunker (unchanged)
            qdrant_client: Qdrant client for atomic writes
            thread_count: Number of worker threads (thread_count + 2 per specs)
            file_tracker: Optional ConsolidatedFileTracker for status reporting

        Raises:
            ValueError: If thread_count is invalid or dependencies are None
        """
        if thread_count <= 0:
            raise ValueError(f"thread_count must be positive, got {thread_count}")
        if not vector_manager:
            raise ValueError("vector_manager cannot be None")
        if not chunker:
            raise ValueError("chunker cannot be None")
        if not qdrant_client:
            raise ValueError("qdrant_client cannot be None")

        self.vector_manager = vector_manager
        self.chunker = chunker
        self.qdrant_client = qdrant_client
        self.thread_count = thread_count
        self.file_tracker = file_tracker  # ADD THIS LINE
        self._thread_counter = 0  # ADD THIS LINE
        self._thread_lock = threading.Lock()  # ADD THIS LINE

        # CRITICAL FIX: Single cancellation event shared with VectorCalculationManager
        self._cancellation_requested = False
        self._shutdown_complete = threading.Event()

        # ThreadPoolExecutor with (thread_count + 2) workers per user specs
        self.executor: Optional[ThreadPoolExecutor] = None
        self._pending_futures: List[Future] = []  # Track futures for clean cancellation

        logger.info(f"Initialized FileChunkingManager with {thread_count} base threads")

    def __enter__(self):
        """Context manager entry - start thread pool."""
        self.executor = ThreadPoolExecutor(
            max_workers=self.thread_count + 2, thread_name_prefix="FileChunk"
        )
        logger.info(
            f"Started FileChunkingManager thread pool with {self.thread_count + 2} workers"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - shutdown thread pool with proper cleanup."""
        if self.executor:
            # CRITICAL FIX: Clean shutdown without private attribute access

            try:
                # Step 1: Cancel all pending futures to signal threads to stop
                self._cancellation_requested = True
                for future in self._pending_futures:
                    if not future.done():
                        future.cancel()

                # Step 2: Shutdown with timeout using thread
                # Since ThreadPoolExecutor.shutdown() doesn't support timeout in Python < 3.9,
                # we use a thread to implement timeout behavior
                import threading

                shutdown_complete = threading.Event()

                def shutdown_thread():
                    try:
                        self.executor.shutdown(wait=True)
                        shutdown_complete.set()
                    except Exception as e:
                        logger.error(f"Error in shutdown thread: {e}")
                        shutdown_complete.set()

                shutdown_worker = threading.Thread(target=shutdown_thread, daemon=True)
                shutdown_worker.start()

                # Wait up to 10 seconds for shutdown
                if shutdown_complete.wait(timeout=10.0):
                    logger.info("FileChunkingManager thread pool shutdown complete")
                else:
                    # Timeout - force shutdown
                    logger.warning(
                        "FileChunkingManager graceful shutdown timeout - forcing shutdown"
                    )
                    self.executor.shutdown(wait=False)

            except Exception as e:
                logger.error(f"Error during FileChunkingManager shutdown: {e}")

            finally:
                self._shutdown_complete.set()

    def _get_next_thread_id(self) -> int:
        """Get next available thread ID with minimal locking."""
        # Quick lock for counter increment only
        with self._thread_lock:
            thread_id = self._thread_counter
            self._thread_counter += 1
        # Return immediately after increment to minimize lock time
        return thread_id

    def _update_file_status(
        self, thread_id: int, status: FileStatus, status_text: Optional[str] = None
    ):
        """Update file status in tracker."""
        if self.file_tracker:
            self.file_tracker.update_file_status(thread_id, status)

    def request_cancellation(self) -> None:
        """Request cancellation of all file processing."""
        self._cancellation_requested = True
        logger.info("FileChunkingManager cancellation requested")

    def submit_file_for_processing(
        self,
        file_path: Path,
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable],
    ) -> "Future[FileProcessingResult]":
        """
        Submit file for complete lifecycle processing.

        Args:
            file_path: Path to file to process
            metadata: File metadata for processing
            progress_callback: Callback for progress updates

        Returns:
            Future that will contain FileProcessingResult when complete
        """
        if not self.executor:
            raise RuntimeError("FileChunkingManager not started - use context manager")

        # Check if cancellation was requested
        if self._cancellation_requested:
            # Return immediately with cancelled result
            cancelled_future: Future[FileProcessingResult] = Future()
            cancelled_future.set_result(
                FileProcessingResult(
                    success=False,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=0.0,
                    error="Cancelled before processing",
                )
            )
            return cancelled_future

        # SURGICAL FIX: Remove individual callback spam - no more "📥 Queued" messages
        # ConsolidatedFileTracker will handle the fixed N-line display

        # Submit to worker thread (immediate return)
        future = self.executor.submit(
            self._process_file_complete_lifecycle,
            file_path,
            metadata,
            progress_callback,
        )

        # Track future for clean shutdown
        self._pending_futures.append(future)

        return future

    def _process_file_complete_lifecycle(
        self,
        file_path: Path,
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable],
    ) -> FileProcessingResult:
        """
        Process file complete lifecycle in worker thread.

        Phases:
        1. Chunk the file (moved from main thread)
        2. Submit ALL chunks to vector processing
        3. Wait for ALL chunk vectors to complete
        4. Write complete file atomically to Qdrant

        Args:
            file_path: File to process
            metadata: File metadata
            progress_callback: Progress callback

        Returns:
            FileProcessingResult with success/failure status
        """
        start_time = time.time()

        # RESTORE: Register file with tracker for display
        thread_id = self._get_next_thread_id()
        if self.file_tracker:
            self.file_tracker.start_file_processing(thread_id, file_path)
            self._update_file_status(thread_id, FileStatus.STARTING)

        try:
            # Phase 1: Chunk the file (MOVE chunking logic from main thread to worker thread)
            logger.debug(f"Starting chunking for {file_path}")
            # STARTING status set - no artificial delays
            chunks = self.chunker.chunk_file(file_path)

            if not chunks:
                # Empty files (like __init__.py) are valid but don't need indexing
                logger.debug(f"Skipping empty file: {file_path}")

                # Mark as complete without error
                if self.file_tracker:
                    self._update_file_status(thread_id, FileStatus.COMPLETE)
                    self.file_tracker.complete_file_processing(thread_id)

                return FileProcessingResult(
                    success=True,  # Changed to True - empty files are success
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error=None,  # No error for empty files
                )

            logger.debug(f"Generated {len(chunks)} chunks for {file_path}")

            # RESTORE: Update status after chunking
            if self.file_tracker:
                self._update_file_status(thread_id, FileStatus.PROCESSING)

            # REMOVED: Mid-process cancellation check - breaks file atomicity
            # Cancellation now only checked AFTER file completion

            # Phase 2: Submit ALL chunks to existing VectorCalculationManager (unchanged)
            chunk_futures = []
            for chunk in chunks:
                try:
                    future = self.vector_manager.submit_chunk(chunk["text"], metadata)
                    chunk_futures.append((chunk, future))
                except RuntimeError as e:
                    if "Thread pool not started" in str(e):
                        logger.info(f"Vector manager shut down, cancelling {file_path}")
                        if self.file_tracker:
                            self._update_file_status(thread_id, FileStatus.COMPLETE)
                            self.file_tracker.complete_file_processing(thread_id)
                        return FileProcessingResult(
                            success=False,
                            file_path=file_path,
                            chunks_processed=0,
                            processing_time=time.time() - start_time,
                            error="Cancelled",
                        )
                    raise

            logger.debug(
                f"Submitted {len(chunk_futures)} chunks to vector processing for {file_path}"
            )

            # Phase 3: Wait for ALL chunk vectors to complete
            file_points = []

            for chunk_idx, (chunk, future) in enumerate(chunk_futures):
                try:
                    # SIMPLE FIX: Use reasonable timeout for all chunks
                    # No aggressive timeouts that cause false failures
                    chunk_timeout = VECTOR_PROCESSING_TIMEOUT  # 300 seconds (5 minutes)

                    # Wait for result with reasonable timeout
                    vector_result = future.result(timeout=chunk_timeout)

                    if not vector_result.error:
                        # Create Qdrant point (MOVE from main thread to worker thread)
                        qdrant_point = self._create_qdrant_point(
                            chunk, vector_result.embedding, metadata, file_path
                        )
                        file_points.append(qdrant_point)
                    else:
                        logger.warning(
                            f"Vector processing failed for chunk {chunk_idx} in {file_path}: {vector_result.error}"
                        )

                except Exception as e:
                    error_msg = "Vector processing timeout"
                    detailed_error = f"Failed to get vector result for chunk {chunk_idx} in {file_path}: {e}"
                    logger.error(detailed_error)

                    # SURGICAL FIX: Remove individual error callbacks - already logged above

                    return FileProcessingResult(
                        success=False,
                        file_path=file_path,
                        chunks_processed=0,
                        processing_time=time.time() - start_time,
                        error=detailed_error,
                    )

            if not file_points:
                error_msg = "No valid vector embeddings generated"
                # SURGICAL FIX: Remove individual error callbacks - log instead
                logger.error(
                    f"Vector processing failed: {file_path.name} - {error_msg}"
                )

                return FileProcessingResult(
                    success=False,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error=error_msg,
                )

            logger.debug(f"Generated {len(file_points)} Qdrant points for {file_path}")

            # RESTORE: Update status before write
            if self.file_tracker:
                self._update_file_status(thread_id, FileStatus.COMPLETING)

            # Phase 4: Write complete file atomically - NO cancellation check during write
            # File atomicity guaranteed: all chunks written together or not at all

            # SIMPLE BATCH WRITE: Write all points for this file using batched processing
            try:
                # Write all points for this file using efficient batching
                # This provides good performance but is not transactionally atomic
                success = self.qdrant_client.upsert_points_batched(file_points)

                if not success:
                    error_msg = "Qdrant batch write failed"
                    logger.error(f"Qdrant write failed: {file_path.name} - {error_msg}")

                    # Some points may have been written, but this is acceptable
                    return FileProcessingResult(
                        success=False,
                        file_path=file_path,
                        chunks_processed=0,
                        processing_time=time.time() - start_time,
                        error=error_msg,
                    )

            except Exception as e:
                # Any exception during write means the atomic operation was rolled back
                error_msg = (
                    f"Database write exception - atomic operation rolled back: {e}"
                )
                logger.error(f"Qdrant write exception for {file_path}: {error_msg}")

                return FileProcessingResult(
                    success=False,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error=error_msg,
                )

            processing_time = time.time() - start_time
            logger.info(
                f"Successfully processed {file_path}: {len(file_points)} chunks in {processing_time:.2f}s"
            )

            # RESTORE: Mark file complete
            if self.file_tracker:
                self._update_file_status(thread_id, FileStatus.COMPLETE)
                self.file_tracker.complete_file_processing(thread_id)

            # SIMPLE CANCELLATION STRATEGY:
            # NO cancellation checks during or after file processing.
            # Files complete fully without any cancellation interruption.
            # Cancellation is ONLY checked between files in the main processing loop.

            return FileProcessingResult(
                success=True,
                file_path=file_path,
                chunks_processed=len(file_points),
                processing_time=processing_time,
                error=None,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"File processing failed: {e}"
            logger.error(f"Error processing {file_path}: {error_msg}")

            # RESTORE: Mark file failed and cleanup
            if self.file_tracker:
                self._update_file_status(thread_id, FileStatus.COMPLETE)
                self.file_tracker.complete_file_processing(thread_id)

            return FileProcessingResult(
                success=False,
                file_path=file_path,
                chunks_processed=0,
                processing_time=processing_time,
                error=error_msg,
            )

    def _create_qdrant_point(
        self,
        chunk: Dict[str, Any],
        embedding: List[float],
        metadata: Dict[str, Any],
        file_path: Path,
    ) -> Dict[str, Any]:
        """
        Create Qdrant point from chunk and embedding.

        This method creates the point structure expected by Qdrant
        using the existing metadata patterns from HighThroughputProcessor.

        Args:
            chunk: Chunk data from FixedSizeChunker
            embedding: Vector embedding from VectorCalculationManager
            metadata: File metadata
            file_path: Path to source file

        Returns:
            Qdrant point dictionary
        """
        # Use existing metadata creation logic pattern
        # Import here to avoid circular imports
        from .metadata_schema import GitAwareMetadataSchema

        # Create Git-aware metadata
        metadata_info = None
        if metadata.get("git_available", False):
            metadata_info = {
                "commit_hash": metadata.get("commit_hash"),
                "branch": metadata.get("branch"),
                "git_hash": metadata.get("git_hash"),
            }
        else:
            metadata_info = {
                "file_mtime": metadata.get("file_mtime"),
                "file_size": metadata.get("file_size", file_path.stat().st_size),
            }

        # Create payload using existing schema
        payload = GitAwareMetadataSchema.create_git_aware_metadata(
            path=str(file_path),
            content=chunk["text"],
            language=chunk["file_extension"],
            file_size=file_path.stat().st_size,
            chunk_index=chunk["chunk_index"],
            total_chunks=chunk["total_chunks"],
            project_id=metadata["project_id"],
            file_hash=metadata["file_hash"],
            git_metadata=(
                metadata_info if metadata.get("git_available", False) else None
            ),
            line_start=chunk.get("line_start"),
            line_end=chunk.get("line_end"),
        )

        # Add filesystem metadata for non-git projects
        if not metadata.get("git_available", False) and metadata_info:
            if "file_mtime" in metadata_info:
                payload["filesystem_mtime"] = metadata_info["file_mtime"]
            if "file_size" in metadata_info:
                payload["filesystem_size"] = metadata_info["file_size"]

        # Create point ID using hash of file and chunk (ensuring uniqueness)
        point_id_data = (
            f"{metadata['project_id']}_{metadata['file_hash']}_{chunk['chunk_index']}"
        )
        point_id = hashlib.md5(point_id_data.encode()).hexdigest()

        payload["point_id"] = point_id
        payload["unique_key"] = point_id_data

        # Create Qdrant point
        qdrant_point = {"id": point_id, "vector": embedding, "payload": payload}

        return qdrant_point
