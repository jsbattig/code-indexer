"""
High-throughput processor that maximizes worker thread utilization.

Instead of processing files sequentially, this approach:
1. Pre-processes ALL files to create a chunk queue
2. Worker threads continuously pull from the queue
3. Results are collected asynchronously

This ensures workers are never idle waiting for the next file to be processed.

⚠️  CRITICAL PROGRESS REPORTING WARNING:
This module contains progress_callback calls that MUST follow the pattern:
- Use files_total > 0 for file progress (triggers CLI progress bar)
- Use info format: "files (%) | emb/s | threads | filename"
- See BranchAwareIndexer and CLI progress_callback for the exact pattern
"""

import logging
import time
from concurrent.futures import as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Set

from ..indexing.processor import ProcessingStats
from ..services.git_aware_processor import GitAwareDocumentProcessor
from .vector_calculation_manager import VectorCalculationManager
from .consolidated_file_tracker import ConsolidatedFileTracker, FileStatus

logger = logging.getLogger(__name__)


@dataclass
class BranchIndexingResult:
    """Results of branch indexing operation."""

    files_processed: int = 0
    content_points_created: int = 0
    content_points_reused: int = 0
    processing_time: float = 0.0
    cancelled: bool = False


@dataclass
class ChunkTask:
    """Task for processing a single chunk."""

    file_path: Path
    chunk_data: Dict[str, Any]
    file_metadata: Dict[str, Any]
    task_id: str


class HighThroughputProcessor(GitAwareDocumentProcessor):
    """Processor that maximizes throughput by pre-queuing all chunks."""

    def __init__(self, *args, progress_log=None, **kwargs):
        """Initialize the processor with cancellation support and structured logging."""
        super().__init__(*args, **kwargs)
        self.cancelled = False
        self.progress_log = progress_log

        # Initialize shared locks for thread safety
        import threading

        self._visibility_lock = threading.Lock()
        self._git_lock = threading.Lock()
        self._content_id_lock = threading.Lock()
        self._database_lock = threading.Lock()

        # File processing rate tracking for files/s metric
        self._file_rate_lock = threading.Lock()
        self._file_processing_start_time = None
        self._file_completion_history = (
            []
        )  # List of (timestamp, files_completed) tuples
        self._rolling_window_seconds = (
            5.0  # Rolling window for smoothed files/s calculation
        )
        self._min_time_diff = 0.1  # Minimum time difference to avoid inflated rates

        # Source bytes tracking for KB/s throughput reporting (Story 3)
        self._source_bytes_lock = threading.Lock()
        self._total_source_bytes_processed = (
            0  # Thread-safe counter for cumulative source bytes
        )
        self._source_bytes_history = (
            []
        )  # List of (timestamp, total_bytes) tuples for smoothed KB/s

        # NEW: Consolidated file tracking system - replaces three duplicate systems
        # Initialize lazily with actual thread count in process_files_high_throughput
        self.file_tracker = None
        self._thread_counter = 0  # For assigning stable thread IDs

        # Fix static file display: Map file paths to thread IDs for proper updates
        self._file_to_thread_map: Dict[Path, int] = {}
        self._file_to_thread_lock = threading.Lock()

    def request_cancellation(self):
        """Request cancellation of processing."""
        self.cancelled = True
        logger.info("High throughput processing cancellation requested")

    def _ensure_file_tracker_initialized(self, thread_count: int = 8):
        """Ensure file tracker is initialized with appropriate thread count.

        Args:
            thread_count: Number of threads to use for file tracking (defaults to 8 for backwards compatibility)
        """
        if self.file_tracker is None:
            self.file_tracker = ConsolidatedFileTracker(
                max_concurrent_files=thread_count
            )
            logger.info(
                f"Initialized ConsolidatedFileTracker with {thread_count} max concurrent files"
            )

    def _register_thread_file(
        self, file_path: Path, status: str = "starting..."
    ) -> int:
        """Register a file with a thread for concurrent tracking.

        Args:
            file_path: Path to the file being processed
            status: Current processing status

        Returns:
            Thread ID assigned to this file
        """
        # Assign a stable thread ID
        thread_id: int = self._thread_counter
        self._thread_counter += 1

        # Map file path to thread ID for efficient lookups during processing
        with self._file_to_thread_lock:
            self._file_to_thread_map[file_path] = thread_id

        # Ensure file tracker is initialized (fallback for backwards compatibility)
        self._ensure_file_tracker_initialized()

        # Use consolidated tracker - handles file I/O outside critical sections
        if status == "starting...":
            file_status = FileStatus.STARTING
        elif "processing" in status.lower():
            file_status = FileStatus.PROCESSING
        else:
            file_status = FileStatus.STARTING

        if self.file_tracker:
            self.file_tracker.start_file_processing(thread_id, file_path)
            self.file_tracker.update_file_status(thread_id, file_status)
        return thread_id

    def _update_thread_status(self, file_path: Path, status: str) -> None:
        """Update the status of a thread processing a file.

        Args:
            file_path: Path to the file being processed
            status: New processing status
        """
        # Use efficient file-to-thread mapping instead of linear search
        with self._file_to_thread_lock:
            thread_id = self._file_to_thread_map.get(file_path)

        if thread_id is None:
            # File not registered - this shouldn't happen but handle gracefully
            logger.warning(
                f"Attempted to update status for unregistered file: {file_path}"
            )
            return

        # Ensure file tracker is initialized (fallback for backwards compatibility)
        self._ensure_file_tracker_initialized()

        # Convert status string to FileStatus enum
        if "complete" in status.lower():
            file_status = FileStatus.COMPLETE
        elif "processing" in status.lower() or "vectorizing" in status.lower():
            file_status = FileStatus.PROCESSING
        elif "finalizing" in status.lower() or "queued" in status.lower():
            file_status = FileStatus.COMPLETING
        else:
            file_status = FileStatus.PROCESSING

        if self.file_tracker:
            self.file_tracker.update_file_status(thread_id, file_status)

    def _complete_thread_file(self, file_path: Path) -> None:
        """Mark a file as completed and free up the thread.

        Args:
            file_path: Path to the completed file
        """
        # Use efficient file-to-thread mapping instead of linear search
        with self._file_to_thread_lock:
            thread_id = self._file_to_thread_map.get(file_path)
            if thread_id is not None:
                # Clean up the mapping since file is complete
                del self._file_to_thread_map[file_path]

        if thread_id is None:
            # File not registered - this shouldn't happen but handle gracefully
            logger.warning(f"Attempted to complete unregistered file: {file_path}")
            return

        # Ensure file tracker is initialized (fallback for backwards compatibility)
        self._ensure_file_tracker_initialized()

        if self.file_tracker:
            self.file_tracker.complete_file_processing(thread_id)

    def _get_concurrent_threads_snapshot(
        self, max_threads: int = 8
    ) -> List[Dict[str, Any]]:
        """Get current snapshot of active threads for concurrent display.

        REPLACED: Now using consolidated file tracker instead of duplicate logic.

        Args:
            max_threads: Maximum number of threads to show

        Returns:
            List of thread info dictionaries for display
        """
        # Ensure file tracker is initialized (fallback for backwards compatibility)
        self._ensure_file_tracker_initialized()

        # Use consolidated tracker - eliminates race conditions and duplication
        if self.file_tracker:
            concurrent_data: List[Dict[str, Any]] = (
                self.file_tracker.get_concurrent_files_data()
            )
        else:
            concurrent_data = []
        return concurrent_data

    def _initialize_file_rate_tracking(self):
        """Initialize file processing rate tracking."""
        with self._file_rate_lock:
            self._file_processing_start_time = time.time()
            self._file_completion_history.clear()

        # Initialize source bytes tracking for KB/s calculation (Story 3)
        with self._source_bytes_lock:
            self._total_source_bytes_processed = 0
            self._source_bytes_history.clear()

    def _calculate_files_per_second(self, current_files_completed: int) -> float:
        """Calculate files per second using rolling window for smooth updates."""
        current_time = time.time()

        with self._file_rate_lock:
            if not self._file_processing_start_time:
                return 0.0

            # Record current state (inline to avoid recursive lock)
            self._file_completion_history.append(
                (current_time, current_files_completed)
            )

            # Remove entries older than rolling window
            cutoff_time = current_time - self._rolling_window_seconds
            self._file_completion_history = [
                (timestamp, count)
                for timestamp, count in self._file_completion_history
                if timestamp >= cutoff_time
            ]

            # Calculate smoothed files per second
            if len(self._file_completion_history) >= 2:
                # Get oldest and newest entries in window
                oldest_time, oldest_count = self._file_completion_history[0]
                newest_time, newest_count = self._file_completion_history[-1]

                time_diff = newest_time - oldest_time
                files_diff = newest_count - oldest_count

                # Only use rolling window if we have sufficient time difference
                if time_diff >= self._min_time_diff and files_diff > 0:
                    return float(files_diff / time_diff)
                else:
                    # Fall back to total average if window is too small
                    elapsed_total = current_time - self._file_processing_start_time
                    if elapsed_total >= self._min_time_diff:
                        return float(current_files_completed / elapsed_total)
                    else:
                        return 0.0
            else:
                # Fall back to total average if not enough data points
                elapsed_total = current_time - self._file_processing_start_time
                if elapsed_total >= self._min_time_diff:
                    return float(current_files_completed / elapsed_total)
                else:
                    return 0.0

    def _add_source_bytes_processed(self, bytes_count: int) -> None:
        """Thread-safe method to add processed source bytes for KB/s calculation."""
        with self._source_bytes_lock:
            self._total_source_bytes_processed += bytes_count
            current_time = time.time()
            self._source_bytes_history.append(
                (current_time, self._total_source_bytes_processed)
            )

            # Remove entries older than rolling window to prevent memory growth
            cutoff_time = current_time - self._rolling_window_seconds
            self._source_bytes_history = [
                (timestamp, total_bytes)
                for timestamp, total_bytes in self._source_bytes_history
                if timestamp >= cutoff_time
            ]

    def _calculate_kbs_throughput(self) -> float:
        """Calculate KB/s throughput using rolling window for smooth updates."""
        current_time = time.time()

        with self._source_bytes_lock:
            if (
                not self._file_processing_start_time
                or self._total_source_bytes_processed == 0
            ):
                return 0.0

            # Use rolling window for smoothed KB/s if we have sufficient data points
            if len(self._source_bytes_history) >= 2:
                # Get oldest and newest entries in window
                oldest_time, oldest_bytes = self._source_bytes_history[0]
                newest_time, newest_bytes = self._source_bytes_history[-1]

                time_diff = newest_time - oldest_time
                bytes_diff = newest_bytes - oldest_bytes

                # Only use rolling window if we have sufficient time difference
                if time_diff >= self._min_time_diff and bytes_diff > 0:
                    return float((bytes_diff / 1024) / time_diff)
                else:
                    # Fall back to total average if window is too small
                    elapsed_total = current_time - self._file_processing_start_time
                    if (
                        elapsed_total > 0
                    ):  # Allow any positive time for KB/s calculation
                        return float(
                            (self._total_source_bytes_processed / 1024) / elapsed_total
                        )
                    else:
                        return 0.0
            else:
                # Fall back to total average if not enough data points
                elapsed_total = current_time - self._file_processing_start_time
                if elapsed_total > 0:  # Allow any positive time for KB/s calculation
                    return float(
                        (self._total_source_bytes_processed / 1024) / elapsed_total
                    )
                else:
                    return 0.0

    def process_files_high_throughput(
        self,
        files: List[Path],
        vector_thread_count: int,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Process files with maximum throughput using pre-queued chunks."""

        # Initialize ConsolidatedFileTracker with actual thread count
        # This fixes the hardcoded 8-file limit bug - now supports any thread count
        self._ensure_file_tracker_initialized(vector_thread_count)

        stats = ProcessingStats()
        stats.start_time = time.time()

        # Initialize file processing rate tracking for files/s metric
        self._initialize_file_rate_tracking()

        # Phase 1: Pre-process all files to create chunk queue
        all_chunk_tasks = []
        task_counter = 0

        # Debug: Log processing start
        import os
        import datetime

        debug_file = os.path.expanduser("~/.tmp/cidx_debug.log")
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)

        logger.info("Phase 1: Creating chunk queue from all files...")
        for file_path in files:
            try:
                # Don't register files during chunking - they're not actually being processed yet
                # File registration will happen when actual processing begins

                # Debug: Log each file being processed
                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] Starting to chunk: {file_path}\n"
                    )
                    f.flush()

                # Skip status update during chunking - no display registration yet

                # Chunk the file
                chunks = self.fixed_size_chunker.chunk_file(file_path)

                # Debug: Log completion of chunking
                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] Completed chunking: {file_path} - {len(chunks) if chunks else 0} chunks\n"
                    )
                    f.flush()

                if not chunks:
                    # Skip - no file registered during chunking
                    continue

                # Files will be registered when actual processing starts in ThreadPoolExecutor

                # Get file metadata once per file
                file_metadata = self.file_identifier.get_file_metadata(file_path)

                # Create tasks for all chunks
                for chunk in chunks:
                    task_counter += 1
                    chunk_task = ChunkTask(
                        file_path=file_path,
                        chunk_data=chunk,
                        file_metadata=file_metadata,
                        task_id=f"task_{task_counter}",
                    )
                    all_chunk_tasks.append(chunk_task)

                # Don't count files as processed until actually completed
                # stats.files_processed will be updated during actual processing
                file_size = file_path.stat().st_size
                stats.total_size += file_size

            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {e}")
                stats.failed_files += 1
                # Skip cleanup - no file registered during chunking
                continue

        if not all_chunk_tasks:
            logger.warning("No chunks to process")
            return stats

        logger.info(
            f"Created {len(all_chunk_tasks)} chunk tasks from {len(files)} files"
        )

        # Phase 2: Process all chunks in parallel with maximum worker utilization
        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:
            # Submit ALL chunks to the vector calculation manager
            chunk_futures = []
            for chunk_task in all_chunk_tasks:
                future = vector_manager.submit_chunk(
                    chunk_task.chunk_data["text"],
                    {
                        "chunk_task": chunk_task,
                        "file_path": str(chunk_task.file_path),
                    },
                )
                chunk_futures.append(future)

            logger.info(
                f"Submitted {len(chunk_futures)} chunks to {vector_thread_count} worker threads"
            )

            # Phase 3: Collect results and batch to Qdrant with file-level atomicity
            batch_points = []
            completed_chunks = 0

            # Track file-level progress for smooth updates
            file_chunk_counts: Dict[Path, int] = {}  # file_path -> total_chunks
            file_completed_chunks: Dict[Path, int] = {}  # file_path -> completed_chunks
            completed_files: Set[Path] = set()
            last_progress_file: Optional[Path] = None

            # File-level transaction management for atomicity
            file_chunks: Dict[Path, List[Dict[str, Any]]] = (
                {}
            )  # file_path -> list of completed points
            file_completion_status: Dict[Path, bool] = (
                {}
            )  # file_path -> all_chunks_complete

            # Pre-calculate chunk counts per file for accurate progress
            for chunk_task in all_chunk_tasks:
                file_path = chunk_task.file_path
                file_chunk_counts[file_path] = file_chunk_counts.get(file_path, 0) + 1
                file_completed_chunks[file_path] = 0
                file_chunks[file_path] = []
                file_completion_status[file_path] = False

            for future in as_completed(chunk_futures):
                # Check for cancellation at the beginning of each iteration
                if self.cancelled:
                    logger.info(
                        "Processing cancelled - breaking out of as_completed loop"
                    )
                    # Also cancel the vector manager to stop new tasks
                    vector_manager.request_cancellation()

                    # Before breaking, commit any completed files to maintain atomicity
                    completed_file_chunks = []
                    for file_path, is_complete in file_completion_status.items():
                        if is_complete:
                            completed_file_chunks.extend(file_chunks[file_path])
                            logger.info(
                                f"Committing completed file on cancellation: {file_path}"
                            )

                    if completed_file_chunks:
                        logger.info(
                            f"Committing {len(completed_file_chunks)} chunks from {len(completed_files)} completed files due to cancellation"
                        )
                        try:
                            if not self.qdrant_client.upsert_points_atomic(
                                completed_file_chunks
                            ):
                                logger.error(
                                    "Failed to commit completed files during cancellation"
                                )
                        except Exception as e:
                            last_file = (
                                list(completed_files)[-1].name
                                if completed_files
                                else "unknown"
                            )
                            logger.error(
                                f"Failed to commit completed files during cancellation (last file: {last_file}): {e}"
                            )

                    break

                try:
                    vector_result = future.result(timeout=300)  # 5 minute timeout

                    if vector_result.error:
                        logger.error(
                            f"Vector calculation failed: {vector_result.error}"
                        )
                        continue

                    # Extract chunk task from metadata
                    chunk_task = vector_result.metadata["chunk_task"]
                    current_file = chunk_task.file_path

                    # Register file with display system when first chunk completes (dynamic registration)
                    chunks_completed = file_completed_chunks.get(current_file, 0) + 1
                    if chunks_completed == 1:
                        # First chunk of this file - register for display
                        self._register_thread_file(current_file, "processing (0%)")

                    # Update thread status for processing with real-time progress
                    total_chunks = file_chunk_counts[current_file]
                    progress_pct = int((chunks_completed / total_chunks) * 100)
                    self._update_thread_status(
                        current_file, f"processing ({progress_pct}%)"
                    )

                    # Create Qdrant point using existing logic
                    point = self._create_qdrant_point(
                        chunk_task, vector_result.embedding
                    )

                    # Store point for this file (don't add to batch yet)
                    file_chunks[current_file].append(point)
                    stats.chunks_created += 1
                    completed_chunks += 1

                    # Update file-level progress tracking
                    file_completed_chunks[current_file] += 1

                    # Check if this file is now completed
                    if (
                        file_completed_chunks[current_file]
                        == file_chunk_counts[current_file]
                    ):
                        # File is complete - add all its chunks to batch for indexing
                        completed_files.add(current_file)
                        file_completion_status[current_file] = True

                        # Show completion status briefly before cleanup
                        self._update_thread_status(current_file, "complete ✓")

                        # Complete the file processing - consolidated tracker handles display and cleanup
                        self._complete_thread_file(current_file)

                        # Track source bytes for KB/s calculation when file completes (Story 3)
                        try:
                            file_size = current_file.stat().st_size
                            self._add_source_bytes_processed(file_size)
                        except Exception as e:
                            logger.warning(
                                f"Failed to track source bytes for {current_file}: {e}"
                            )

                        # Add all chunks for this completed file to the batch
                        batch_points.extend(file_chunks[current_file])
                        logger.debug(
                            f"File {current_file} completed - added {len(file_chunks[current_file])} chunks to batch"
                        )

                    # Process batch if full with enhanced atomicity
                    if len(batch_points) >= batch_size:
                        try:
                            if not self.qdrant_client.upsert_points_atomic(
                                batch_points
                            ):
                                raise RuntimeError("Failed to upload batch to Qdrant")
                        except Exception as e:
                            raise RuntimeError(
                                f"Failed to upload batch to Qdrant (last processed file: {file_path.name}): {e}"
                            )
                        batch_points = []

                    # Smooth progress updates: call every few chunks or when file changes
                    should_update_progress = False
                    if progress_callback:
                        # Update every 3 chunks OR when we start/complete a file
                        if (
                            completed_chunks % 3 == 0
                            or current_file != last_progress_file
                            or current_file in completed_files
                        ):
                            should_update_progress = True
                            last_progress_file = current_file

                    if should_update_progress:
                        vector_stats = vector_manager.get_stats()

                        # Create file-based progress information
                        files_completed = len(completed_files)
                        files_total = len(files)
                        file_progress_pct = (
                            (files_completed / files_total * 100)
                            if files_total > 0
                            else 0
                        )

                        # Show current file being processed (or last completed)
                        display_file = current_file
                        file_status = ""
                        if current_file in completed_files:
                            file_status = " ✓"
                        else:
                            # Show progress within current file
                            file_pct = (
                                (
                                    file_completed_chunks[current_file]
                                    / file_chunk_counts[current_file]
                                    * 100
                                )
                                if file_chunk_counts[current_file] > 0
                                else 0
                            )
                            file_status = f" ({file_pct:.0f}%)"

                        # Calculate files per second for progress reporting
                        files_per_second = self._calculate_files_per_second(
                            files_completed
                        )

                        # Calculate KB/s throughput for source data ingestion rate (Story 3)
                        kbs_throughput = self._calculate_kbs_throughput()

                        # NEW: Use real-time thread tracking for concurrent display
                        concurrent_files = self._get_concurrent_threads_snapshot(
                            max_threads=vector_thread_count
                        )

                        # Create comprehensive info message including file status for progress bar display
                        # STORY 3: Added KB/s between files/s and threads to show source data throughput
                        info_msg = (
                            f"{files_completed}/{files_total} files ({file_progress_pct:.0f}%) | "
                            f"{files_per_second:.1f} files/s | "
                            f"{kbs_throughput:.1f} KB/s | "
                            f"{vector_stats.active_threads} threads | "
                            f"{display_file.name}{file_status}"
                        )

                        if progress_callback:
                            # ⚠️  CRITICAL: files_total > 0 triggers CLI progress bar
                            # Use empty path with info to ensure progress bar updates instead of individual messages
                            # Include concurrent files data for multi-threaded display integration
                            callback_result = progress_callback(
                                files_completed,
                                files_total,
                                Path(
                                    ""
                                ),  # Empty path with info = progress bar description update
                                info=info_msg,
                                concurrent_files=concurrent_files,  # NEW: Add concurrent file data
                            )
                            # Check for cancellation signal
                            if callback_result == "INTERRUPT":
                                logger.info("Processing interrupted by user")
                                # Set cancellation flag for immediate response
                                self.cancelled = True
                                # Also cancel the vector manager
                                vector_manager.request_cancellation()
                                # Update stats to reflect actual files processed before interruption
                                stats.files_processed = files_completed
                                stats.cancelled = True
                                return stats

                except Exception as e:
                    logger.error(f"Failed to process chunk result: {e}")
                    continue

            # Process remaining points with enhanced atomicity
            if batch_points:
                try:
                    if not self.qdrant_client.upsert_points_atomic(batch_points):
                        raise RuntimeError("Failed to upload final batch to Qdrant")
                except Exception as e:
                    last_file = files[-1].name if files else "unknown"
                    raise RuntimeError(
                        f"Failed to upload final batch to Qdrant (last processed file: {last_file}): {e}"
                    )

        stats.end_time = time.time()
        # Set final files_processed count to actual completed files
        stats.files_processed = len(completed_files)
        logger.info(
            f"High-throughput processing completed: "
            f"{stats.files_processed} files, {stats.chunks_created} chunks in {stats.end_time - stats.start_time:.2f}s"
        )

        # STORY 1: Send final progress callback to reach 100% completion
        # This ensures Rich Progress bar shows 100% instead of stopping at ~94%
        if progress_callback and len(files) > 0:
            # Calculate final KB/s throughput for completion message (Story 3)
            final_kbs_throughput = self._calculate_kbs_throughput()

            final_info_msg = (
                f"{len(files)}/{len(files)} files (100%) | "
                f"0.0 files/s | "
                f"{final_kbs_throughput:.1f} KB/s | "
                f"0 threads | "
                f"✅ Completed"
            )
            progress_callback(
                len(files),  # current = total for 100% completion
                len(files),  # total files
                Path(""),  # Empty path with info = progress bar description update
                info=final_info_msg,
            )

        return stats

    def _create_qdrant_point(
        self, chunk_task: ChunkTask, embedding: List[float]
    ) -> Dict[str, Any]:
        """Create Qdrant point from chunk task and embedding."""

        # Use existing metadata creation logic
        metadata_info = None
        if chunk_task.file_metadata["git_available"]:
            metadata_info = {
                "commit_hash": chunk_task.file_metadata.get("commit_hash"),
                "branch": chunk_task.file_metadata.get("branch"),
                "git_hash": chunk_task.file_metadata.get("git_hash"),
            }
        else:
            metadata_info = {
                "file_mtime": chunk_task.file_metadata.get("file_mtime"),
                "file_size": chunk_task.file_metadata.get("file_size"),
            }

        # Import here to avoid circular imports
        from .metadata_schema import GitAwareMetadataSchema

        # Create payload
        payload = GitAwareMetadataSchema.create_git_aware_metadata(
            path=str(chunk_task.file_path),
            content=chunk_task.chunk_data["text"],
            language=chunk_task.chunk_data["file_extension"],
            file_size=chunk_task.file_path.stat().st_size,
            chunk_index=chunk_task.chunk_data["chunk_index"],
            total_chunks=chunk_task.chunk_data["total_chunks"],
            project_id=chunk_task.file_metadata["project_id"],
            file_hash=chunk_task.file_metadata["file_hash"],
            git_metadata=(
                metadata_info if chunk_task.file_metadata["git_available"] else None
            ),
            line_start=chunk_task.chunk_data.get("line_start"),
            line_end=chunk_task.chunk_data.get("line_end"),
        )

        # Add filesystem metadata for non-git projects
        if not chunk_task.file_metadata["git_available"] and metadata_info:
            if "file_mtime" in metadata_info:
                payload["filesystem_mtime"] = metadata_info["file_mtime"]
            if "file_size" in metadata_info:
                payload["filesystem_size"] = metadata_info["file_size"]

        # Create point ID
        point_id = self._create_point_id(
            chunk_task.file_metadata, chunk_task.chunk_data["chunk_index"]
        )
        payload["point_id"] = point_id
        payload["unique_key"] = self._create_unique_key(
            chunk_task.file_metadata, chunk_task.chunk_data["chunk_index"]
        )

        # Create Qdrant point
        point = self.qdrant_client.create_point(
            point_id=point_id,
            vector=embedding,
            payload=payload,
            embedding_model=self.embedding_provider.get_current_model(),
        )
        # Ensure we return a Dict[str, Any] as expected
        return dict(point) if point else {}

    # =============================================================================
    # BRANCH-AWARE HIGH-THROUGHPUT PROCESSING
    # =============================================================================

    def process_branch_changes_high_throughput(
        self,
        old_branch: str,
        new_branch: str,
        changed_files: List[str],
        unchanged_files: List[str],
        collection_name: str,
        progress_callback: Optional[Callable] = None,
        vector_thread_count: Optional[int] = None,
    ):
        """
        Process branch changes using high-throughput parallel processing.

        This method combines the git-aware features of BranchAwareIndexer with the
        parallel processing capabilities of HighThroughputProcessor for maximum performance.

        Args:
            old_branch: Previous branch name (for branch change analysis)
            new_branch: Current branch name
            changed_files: List of relative file paths that changed
            unchanged_files: List of relative file paths that didn't change but need visibility updates
            collection_name: Qdrant collection name
            progress_callback: Optional callback for progress reporting
            vector_thread_count: Number of threads for parallel processing

        Returns:
            BranchIndexingResult with processing statistics
        """
        import time

        start_time = time.time()
        result = BranchIndexingResult()

        logger.info(
            f"Starting high-throughput branch processing: {old_branch} -> {new_branch}"
        )
        logger.info(
            f"Changed files: {len(changed_files)}, Unchanged files: {len(unchanged_files)}"
        )

        try:
            # Convert relative paths to absolute paths for processing
            absolute_changed_files = []
            for rel_path in changed_files:
                abs_path = self.config.codebase_dir / rel_path
                if abs_path.exists():
                    absolute_changed_files.append(abs_path)

            total_files = len(absolute_changed_files)

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"🚀 High-throughput branch processing: {total_files} files with {vector_thread_count or 8} threads",
                )

            # Process changed files using high-throughput parallel processing
            if absolute_changed_files:
                # Use the existing high-throughput infrastructure
                stats = self.process_files_high_throughput(
                    files=absolute_changed_files,
                    vector_thread_count=vector_thread_count or 8,
                    batch_size=50,
                    progress_callback=progress_callback,
                )

                result.files_processed = stats.files_processed
                result.content_points_created = stats.chunks_created
                result.cancelled = stats.cancelled

                if result.cancelled:
                    logger.info("High-throughput branch processing was cancelled")
                    result.processing_time = time.time() - start_time
                    return result

            # Handle visibility updates for unchanged files (fast, non-parallel operation)
            if unchanged_files:
                if progress_callback:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"👁️  Updating visibility for {len(unchanged_files)} unchanged files",
                    )

                for file_path in unchanged_files:
                    try:
                        self._ensure_file_visible_in_branch_thread_safe(
                            file_path, new_branch, collection_name
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to update visibility for {file_path}: {e}"
                        )
                        continue

            # Hide files that don't exist in the new branch (branch isolation)
            if progress_callback:
                progress_callback(0, 0, Path(""), info="Applying branch isolation")

            # Get all files that should be visible in the new branch
            all_branch_files = changed_files + unchanged_files
            self.hide_files_not_in_branch_thread_safe(
                new_branch, all_branch_files, collection_name, progress_callback
            )

            result.processing_time = time.time() - start_time

            logger.info(
                f"High-throughput branch processing completed: "
                f"{result.files_processed} files, {result.content_points_created} chunks, "
                f"{result.processing_time:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"High-throughput branch processing failed: {e}")
            result.processing_time = time.time() - start_time
            raise

    # =============================================================================
    # THREAD-SAFE GIT-AWARE METHODS
    # =============================================================================

    def _generate_content_id_thread_safe(
        self, file_path: str, commit: str, chunk_index: int = 0
    ) -> str:
        """Thread-safe version of content ID generation."""
        import uuid

        content_str = f"{file_path}:{commit}:{chunk_index}"
        # Use UUID5 for deterministic UUIDs that Qdrant accepts
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
        return str(uuid.uuid5(namespace, content_str))

    def _content_exists_thread_safe(
        self, content_id: str, collection_name: str
    ) -> bool:
        """Thread-safe check if content point already exists."""
        with self._content_id_lock:
            try:
                point = self.qdrant_client.get_point(content_id, collection_name)
                return point is not None
            except Exception as e:
                logger.warning(
                    f"Failed to check content existence for {content_id}: {e}"
                )
                return False

    def _get_file_commit_thread_safe(self, file_path: str) -> str:
        """Thread-safe version of getting file commit hash."""
        import subprocess
        import time

        try:
            # Check if this is a git repository
            is_git_repo = self._is_git_repository_thread_safe()

            if not is_git_repo:
                # For non-git projects, always use timestamp-based IDs for consistency
                try:
                    file_path_obj = self.config.codebase_dir / file_path
                    file_stat = file_path_obj.stat()
                    return f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                except Exception:
                    return f"working_dir_{time.time()}_error"

            # For git repositories, use git-aware logic
            if self._file_differs_from_committed_version_thread_safe(file_path):
                # File has working directory changes
                try:
                    file_path_obj = self.config.codebase_dir / file_path
                    file_stat = file_path_obj.stat()
                    return f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                except Exception:
                    return f"working_dir_{time.time()}_error"

            # File matches committed version - use commit hash
            with self._git_lock:
                try:
                    result = subprocess.run(
                        ["git", "log", "-1", "--format=%H", "--", file_path],
                        cwd=self.config.codebase_dir,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    commit = result.stdout.strip() if result.returncode == 0 else ""
                    return commit if commit else "unknown"
                except subprocess.TimeoutExpired:
                    logger.warning(f"Git log timeout for {file_path}")
                    return "unknown"
                except Exception as e:
                    logger.warning(f"Git log failed for {file_path}: {e}")
                    return "unknown"
        except Exception:
            return "unknown"

    def _file_differs_from_committed_version_thread_safe(self, file_path: str) -> bool:
        """Thread-safe check if working directory file differs from committed version."""
        import subprocess

        with self._git_lock:
            try:
                result = subprocess.run(
                    ["git", "diff", "--quiet", "HEAD", "--", file_path],
                    cwd=self.config.codebase_dir,
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode != 0
            except subprocess.TimeoutExpired:
                logger.warning(f"Git diff timeout for {file_path}")
                return False
            except Exception as e:
                logger.warning(f"Git diff failed for {file_path}: {e}")
                return False

    def _is_git_repository_thread_safe(self) -> bool:
        """Thread-safe check if current directory is a git repository."""
        import subprocess

        with self._git_lock:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    cwd=self.config.codebase_dir,
                    capture_output=True,
                    timeout=5,
                )
                return result.returncode == 0
            except subprocess.TimeoutExpired:
                logger.warning("Git rev-parse timeout")
                return False
            except Exception as e:
                logger.warning(f"Git rev-parse failed: {e}")
                return False

    def _hide_file_in_branch_thread_safe(
        self, file_path: str, branch: str, collection_name: str
    ):
        """Thread-safe version of hiding file in branch."""

        # Use shared lock to ensure thread safety for visibility updates
        with self._visibility_lock:
            # Get all content points for this file with error handling
            try:
                content_points, _ = self.qdrant_client.scroll_points(
                    filter_conditions={
                        "must": [
                            {"key": "type", "match": {"value": "content"}},
                            {"key": "path", "match": {"value": file_path}},
                        ]
                    },
                    limit=1000,
                    collection_name=collection_name,
                )
                if not isinstance(content_points, list):
                    logger.error(
                        f"Unexpected scroll_points return type: {type(content_points)}"
                    )
                    return False
            except Exception as e:
                logger.error(f"Failed to get content points for {file_path}: {e}")
                return False

            # Update each content point to add branch to hidden_branches if not already present
            points_to_update = []
            for point in content_points:
                current_hidden = point.get("payload", {}).get("hidden_branches", [])
                if branch not in current_hidden:
                    new_hidden = current_hidden + [branch]
                    points_to_update.append(
                        {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                    )

            # Batch update the points with new hidden_branches arrays
            if points_to_update:
                return self.qdrant_client._batch_update_points(
                    points_to_update, collection_name
                )

            return True

    def _ensure_file_visible_in_branch_thread_safe(
        self, file_path: str, branch: str, collection_name: str
    ):
        """Thread-safe version of ensuring file is visible in branch."""
        with self._visibility_lock:
            # Get all content points for this file with error handling
            try:
                content_points, _ = self.qdrant_client.scroll_points(
                    filter_conditions={
                        "must": [
                            {"key": "type", "match": {"value": "content"}},
                            {"key": "path", "match": {"value": file_path}},
                        ]
                    },
                    limit=1000,
                    collection_name=collection_name,
                )
                if not isinstance(content_points, list):
                    logger.error(
                        f"Unexpected scroll_points return type: {type(content_points)}"
                    )
                    return False
            except Exception as e:
                logger.error(f"Failed to get content points for {file_path}: {e}")
                return False

            # Update each content point to remove branch from hidden_branches if present
            points_to_update = []
            for point in content_points:
                current_hidden = point.get("payload", {}).get("hidden_branches", [])
                if branch in current_hidden:
                    new_hidden = [b for b in current_hidden if b != branch]
                    points_to_update.append(
                        {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                    )

            # Batch update the points with new hidden_branches arrays
            if points_to_update:
                return self.qdrant_client._batch_update_points(
                    points_to_update, collection_name
                )

            return True

    def _batch_hide_files_in_branch(
        self, file_paths: List[str], branch: str, collection_name: str
    ):
        """Batch process hiding files in branch to avoid sequential locking bottleneck."""
        if not file_paths:
            return

        with self._visibility_lock:
            all_points_to_update = []

            try:
                # Get all content points for all files in a single batch query
                # This is more efficient than individual queries per file
                for file_path in file_paths:
                    try:
                        content_points, _ = self.qdrant_client.scroll_points(
                            filter_conditions={
                                "must": [
                                    {"key": "type", "match": {"value": "content"}},
                                    {"key": "path", "match": {"value": file_path}},
                                ]
                            },
                            limit=1000,
                            collection_name=collection_name,
                        )

                        if not isinstance(content_points, list):
                            logger.warning(
                                f"Unexpected scroll_points return type: {type(content_points)} for {file_path}"
                            )
                            continue

                        # Collect points that need updating
                        for point in content_points:
                            current_hidden = point.get("payload", {}).get(
                                "hidden_branches", []
                            )
                            if branch not in current_hidden:
                                new_hidden = current_hidden + [branch]
                                all_points_to_update.append(
                                    {
                                        "id": point["id"],
                                        "payload": {"hidden_branches": new_hidden},
                                    }
                                )

                    except Exception as e:
                        logger.warning(
                            f"Failed to get content points for {file_path}: {e}"
                        )
                        continue

                # Batch update all points at once instead of individual updates
                if all_points_to_update:
                    self.qdrant_client._batch_update_points(
                        all_points_to_update, collection_name
                    )
                    logger.info(
                        f"Batch updated {len(all_points_to_update)} points for branch hiding"
                    )

            except Exception as e:
                logger.error(f"Batch hide operation failed: {e}")

    def hide_files_not_in_branch_thread_safe(
        self,
        branch: str,
        current_files: List[str],
        collection_name: str,
        progress_callback: Optional[Callable] = None,
    ):
        """Thread-safe version of hiding files that don't exist in branch."""

        if progress_callback:
            progress_callback(
                0, 0, Path(""), info="Scanning database for branch isolation..."
            )

        # Get all unique file paths from content points in the database
        with self._database_lock:
            try:
                all_content_points, _ = self.qdrant_client.scroll_points(
                    filter_conditions={
                        "must": [{"key": "type", "match": {"value": "content"}}]
                    },
                    limit=10000,
                    collection_name=collection_name,
                )
                if not isinstance(all_content_points, list):
                    logger.error(
                        f"Unexpected scroll_points return type: {type(all_content_points)}"
                    )
                    return False
            except Exception as e:
                logger.error(f"Failed to get all content points from database: {e}")
                return False

        # Extract unique file paths from database
        db_file_paths = set()
        for point in all_content_points:
            if "path" in point.get("payload", {}):
                db_file_paths.add(point["payload"]["path"])

        # Find files in DB that aren't in current branch
        current_files_set = set(current_files)
        files_to_hide = db_file_paths - current_files_set

        if files_to_hide:
            logger.info(
                f"Branch isolation: hiding {len(files_to_hide)} files not in branch '{branch}'"
            )

            # Batch process files to hide - avoid sequential locking bottleneck
            self._batch_hide_files_in_branch(
                list(files_to_hide), branch, collection_name
            )

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"Hidden {len(files_to_hide)} files not in branch '{branch}'",
                )
        else:
            logger.info(f"Branch isolation: no files to hide for branch '{branch}'")

        return True

    def _build_concurrent_files_data(
        self,
        file_completed_chunks: Dict[Path, int],
        file_chunk_counts: Dict[Path, int],
        completed_files: Set[Path],
    ) -> List[Dict[str, Any]]:
        """Build concurrent files data structure for multi-threaded display integration.

        NOW USING CONSOLIDATED FILE TRACKER - eliminates race conditions and lock contention.

        Args:
            file_completed_chunks: Map of file paths to completed chunk counts
            file_chunk_counts: Map of file paths to total chunk counts
            completed_files: Set of fully completed file paths

        Returns:
            List of concurrent file data dictionaries for display manager
        """
        # Use consolidated file tracker instead of duplicate tracking logic
        concurrent_files_data: List[Dict[str, Any]] = (
            self.file_tracker.get_concurrent_files_data()
        )
        return concurrent_files_data
