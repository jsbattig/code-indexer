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
from .clean_slot_tracker import CleanSlotTracker, FileData, FileStatus
import threading

# Token counting for large file handling - MANDATORY dependency
import voyageai

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
        slot_tracker: CleanSlotTracker,
    ):
        """
        Initialize FileChunkingManager with complete functionality.

        Args:
            vector_manager: Existing VectorCalculationManager (unchanged)
            chunker: Existing FixedSizeChunker (unchanged)
            qdrant_client: Qdrant client for atomic writes
            thread_count: Number of worker threads (thread_count + 2 per specs)
            slot_tracker: CleanSlotTracker for progress tracking and slot management

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
        if not slot_tracker:
            raise ValueError("slot_tracker cannot be None")

        self.vector_manager = vector_manager
        self.chunker = chunker
        self.qdrant_client = qdrant_client
        self.thread_count = thread_count
        self.slot_tracker = slot_tracker

        # CRITICAL FIX: Single cancellation event shared with VectorCalculationManager
        self._cancellation_requested = False
        self._shutdown_complete = threading.Event()

        # ThreadPoolExecutor with (thread_count + 2) workers per user specs
        self.executor: Optional[ThreadPoolExecutor] = None
        self._pending_futures: List[Future] = []  # Track futures for clean cancellation

        # Initialize VoyageAI client for accurate token counting
        self.voyage_client = voyageai.Client()

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
                        if self.executor is not None:
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

    def request_cancellation(self) -> None:
        """Request cancellation of all file processing."""
        self._cancellation_requested = True
        logger.info("FileChunkingManager cancellation requested")

    def _count_tokens(self, text: str) -> int:
        """Count tokens using VoyageAI's official count_tokens function."""
        # Get the model name from the embedding provider
        model = self.vector_manager.embedding_provider.get_current_model()
        return self.voyage_client.count_tokens([text], model=model)  # type: ignore[no-any-return]

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
        # Always use clean implementation
        process_method = self._process_file_clean_lifecycle

        future = self.executor.submit(
            process_method,
            file_path,
            metadata,
            progress_callback,
            self.slot_tracker,
        )

        # Track future for clean shutdown
        self._pending_futures.append(future)

        return future

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

    def _process_file_clean_lifecycle(
        self,
        file_path: Path,
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable],
        slot_tracker: CleanSlotTracker,
    ) -> FileProcessingResult:
        """
        CLEAN IMPLEMENTATION: Process file with proper resource management.

        DESIGN PRINCIPLES:
        1. Single acquire at start
        2. All work in try block
        3. Single release in finally block
        4. Direct slot_id usage throughout
        5. No thread_id tracking
        6. Call progress_callback to trigger display updates
        """
        start_time = time.time()
        file_size = file_path.stat().st_size
        filename = file_path.name

        # Single acquire at start - create clean FileData
        file_data = FileData(
            filename=filename,
            file_size=file_size,
            status=FileStatus.STARTING,
            start_time=start_time,
        )

        # Single acquire using CleanSlotTracker
        slot_id = slot_tracker.acquire_slot(file_data)

        # PROGRESS REPORTING ADJUSTMENT: Remove initial callback
        # HighThroughputProcessor handles file-level progress counting
        # We only call progress_callback when the file actually completes

        try:
            # ALL work in try block
            slot_tracker.update_slot(slot_id, FileStatus.CHUNKING)

            # Phase 1: Chunk the file
            logger.debug(f"Starting chunking for {file_path}")
            chunks = self.chunker.chunk_file(file_path)

            if not chunks:
                # Empty files are valid but don't need indexing
                logger.debug(f"Skipping empty file: {file_path}")

                slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)

                # PROGRESS REPORTING ADJUSTMENT: Empty file completion callback
                if progress_callback:
                    concurrent_files = slot_tracker.get_concurrent_files_data()
                    progress_callback(
                        None,  # current - HighThroughputProcessor manages file counts
                        None,  # total - HighThroughputProcessor manages file counts
                        file_path,
                        concurrent_files=concurrent_files,
                    )

                return FileProcessingResult(
                    success=True,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error=None,
                )

            logger.debug(f"Generated {len(chunks)} chunks for {file_path}")

            # Update status after chunking
            slot_tracker.update_slot(slot_id, FileStatus.VECTORIZING)

            # PROGRESS REPORTING ADJUSTMENT: Remove intermediate callback
            # Status updates are tracked by CleanSlotTracker for display
            # HighThroughputProcessor handles file-level progress reporting

            # Phase 2: TOKEN-AWARE BATCHING - Count tokens as we chunk, submit when limit reached
            # Get token limit from VoyageAI client configuration (with safety margin from YAML)
            model_limit = (
                self.vector_manager.embedding_provider._get_model_token_limit()  # type: ignore[attr-defined]
            )
            TOKEN_LIMIT = int(
                model_limit * 0.9
            )  # Apply same 90% safety margin as VoyageAI client

            current_batch: List[str] = []
            current_tokens = 0
            batch_futures = []

            for chunk in chunks:
                chunk_text = chunk["text"]
                chunk_tokens = self._count_tokens(chunk_text)

                # If this chunk would exceed limit, submit current batch
                if current_tokens + chunk_tokens > TOKEN_LIMIT and current_batch:
                    try:
                        batch_future = self.vector_manager.submit_batch_task(
                            current_batch, metadata
                        )
                        batch_futures.append(batch_future)
                        logger.debug(
                            f"Submitted batch of {len(current_batch)} chunks ({current_tokens} tokens) for {file_path}"
                        )
                    except RuntimeError as e:
                        if "Thread pool not started" in str(e):
                            logger.info(
                                f"Vector manager shut down, cancelling {file_path}"
                            )
                            return FileProcessingResult(
                                success=False,
                                file_path=file_path,
                                chunks_processed=0,
                                processing_time=time.time() - start_time,
                                error="Cancelled",
                            )
                        raise

                    # Reset for next batch
                    current_batch = []
                    current_tokens = 0

                # Add chunk to current batch
                current_batch.append(chunk_text)
                current_tokens += chunk_tokens

            # Submit final batch if not empty
            if current_batch:
                try:
                    batch_future = self.vector_manager.submit_batch_task(
                        current_batch, metadata
                    )
                    batch_futures.append(batch_future)
                    logger.debug(
                        f"Submitted final batch of {len(current_batch)} chunks ({current_tokens} tokens) for {file_path}"
                    )
                except RuntimeError as e:
                    if "Thread pool not started" in str(e):
                        logger.info(f"Vector manager shut down, cancelling {file_path}")
                        return FileProcessingResult(
                            success=False,
                            file_path=file_path,
                            chunks_processed=0,
                            processing_time=time.time() - start_time,
                            error="Cancelled",
                        )
                    raise

            if not batch_futures:
                logger.warning(f"No batches created for {file_path}")
                return FileProcessingResult(
                    success=False,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error="No batches created",
                )

            logger.debug(f"Submitted {len(batch_futures)} batches for {file_path}")

            slot_tracker.update_slot(slot_id, FileStatus.FINALIZING)

            # PROGRESS REPORTING ADJUSTMENT: Remove intermediate callback
            # Status updates tracked by CleanSlotTracker, progress callback only on completion

            # Phase 3: MULTI-BATCH RESULT PROCESSING - Process all batch embeddings with chunk mapping
            file_points = []
            all_embeddings: List[List[float]] = []

            try:
                # Collect embeddings from all batches in order
                for batch_future in batch_futures:
                    batch_result = batch_future.result(
                        timeout=VECTOR_PROCESSING_TIMEOUT
                    )

                    # CRITICAL: Validate each batch result
                    if (
                        batch_result
                        and not batch_result.error
                        and batch_result.embeddings
                    ):
                        all_embeddings.extend(
                            [list(emb) for emb in batch_result.embeddings]
                        )
                    else:
                        # ATOMIC FAILURE: Any batch fails, fail entire file
                        error_msg = (
                            batch_result.error if batch_result else "No batch result"
                        )
                        logger.error(
                            f"Batch vector processing failed for {file_path}: {error_msg}"
                        )
                        return FileProcessingResult(
                            success=False,
                            file_path=file_path,
                            chunks_processed=0,
                            processing_time=time.time() - start_time,
                            error=f"Batch processing failed: {error_msg}",
                        )

                # CRITICAL: Validate total embedding count matches chunks
                if len(all_embeddings) != len(chunks):
                    logger.error(
                        f"Total embedding count mismatch: {len(all_embeddings)} embeddings for {len(chunks)} chunks in {file_path}"
                    )
                    return FileProcessingResult(
                        success=False,
                        file_path=file_path,
                        chunks_processed=0,
                        processing_time=time.time() - start_time,
                        error="Total embedding count mismatch",
                    )

                # Create points with preserved order: chunks[i] → embeddings[i] → points[i]
                for i, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
                    if embedding:  # Validate individual embedding
                        file_points.append(
                            {
                                "text": chunk["text"],
                                "vector": embedding,  # Direct embedding from batch result
                                "metadata": {
                                    **metadata,
                                    "line_start": chunk["line_start"],
                                    "line_end": chunk["line_end"],
                                },
                            }
                        )
                    else:
                        logger.warning(
                            f"Skipping chunk {i} with invalid embedding in {file_path}"
                        )

            except Exception as e:
                logger.error(f"Batch vector processing failed for {file_path}: {e}")
                return FileProcessingResult(
                    success=False,
                    file_path=file_path,
                    chunks_processed=0,
                    processing_time=time.time() - start_time,
                    error=f"Batch processing failed: {e}",
                )

            # Phase 4: Atomic write to Qdrant if we have valid vectors
            if file_points:
                try:
                    points_data = []
                    for i, point in enumerate(file_points):
                        # Create proper Qdrant point using existing method
                        chunk_data = {
                            "text": point["text"],
                            "chunk_index": i,
                            "total_chunks": len(file_points),
                            "line_start": point["metadata"].get("line_start"),
                            "line_end": point["metadata"].get("line_end"),
                            "file_extension": file_path.suffix.lstrip(".") or "txt",
                        }

                        # Use the existing _create_qdrant_point method to ensure proper formatting
                        qdrant_point = self._create_qdrant_point(
                            chunk_data, point["vector"], point["metadata"], file_path
                        )
                        points_data.append(qdrant_point)

                    # Atomic write to Qdrant
                    success = self.qdrant_client.upsert_points(
                        points=points_data,
                        collection_name=metadata.get("collection_name"),
                    )
                    if not success:
                        raise RuntimeError(
                            f"Failed to write {len(points_data)} points to Qdrant"
                        )

                    logger.debug(
                        f"Successfully wrote {len(points_data)} points for {file_path}"
                    )

                except Exception as e:
                    logger.error(f"Qdrant write failed for {file_path}: {e}")
                    return FileProcessingResult(
                        success=False,
                        file_path=file_path,
                        chunks_processed=0,
                        processing_time=time.time() - start_time,
                        error=f"Qdrant write failed: {e}",
                    )

            processing_time = time.time() - start_time

            # Mark as complete
            slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)

            # PROGRESS REPORTING ADJUSTMENT: File completion callback
            # This is the ONLY progress callback - when file truly completes
            # HighThroughputProcessor will handle file count updates and metrics
            if progress_callback:
                concurrent_files = slot_tracker.get_concurrent_files_data()
                progress_callback(
                    None,  # current - HighThroughputProcessor manages file counts
                    None,  # total - HighThroughputProcessor manages file counts
                    file_path,
                    concurrent_files=concurrent_files,
                )

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

            # Mark file failed
            slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)

            # PROGRESS REPORTING ADJUSTMENT: Error file completion callback
            if progress_callback:
                concurrent_files = slot_tracker.get_concurrent_files_data()
                progress_callback(
                    None,  # current - HighThroughputProcessor manages file counts
                    None,  # total - HighThroughputProcessor manages file counts
                    file_path,
                    concurrent_files=concurrent_files,
                )

            return FileProcessingResult(
                success=False,
                file_path=file_path,
                chunks_processed=0,
                processing_time=processing_time,
                error=error_msg,
            )

        finally:
            # SINGLE release - guaranteed (CLAUDE.md Foundation #8 compliance)
            if slot_id is not None:
                slot_tracker.release_slot(slot_id)
