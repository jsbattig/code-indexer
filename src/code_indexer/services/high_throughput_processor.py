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

logger = logging.getLogger(__name__)


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

    def request_cancellation(self):
        """Request cancellation of processing."""
        self.cancelled = True
        logger.info("High throughput processing cancellation requested")

    def process_files_high_throughput(
        self,
        files: List[Path],
        vector_thread_count: int,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Process files with maximum throughput using pre-queued chunks."""

        stats = ProcessingStats()
        stats.start_time = time.time()

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
                # Debug: Log each file being processed
                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] Starting to chunk: {file_path}\n"
                    )
                    f.flush()
                # Chunk the file
                chunks = self.fixed_size_chunker.chunk_file(file_path)

                # Debug: Log completion of chunking
                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] Completed chunking: {file_path} - {len(chunks) if chunks else 0} chunks\n"
                    )
                    f.flush()

                if not chunks:
                    continue

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
                stats.total_size += file_path.stat().st_size

            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {e}")
                stats.failed_files += 1
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

                        # Create comprehensive info message including file status for progress bar display
                        info_msg = (
                            f"{files_completed}/{files_total} files ({file_progress_pct:.0f}%) | "
                            f"{vector_stats.embeddings_per_second:.1f} emb/s | "
                            f"{vector_thread_count} threads | "
                            f"{display_file.name}{file_status}"
                        )

                        if progress_callback:
                            # ⚠️  CRITICAL: files_total > 0 triggers CLI progress bar
                            # Use empty path with info to ensure progress bar updates instead of individual messages
                            callback_result = progress_callback(
                                files_completed,
                                files_total,
                                Path(
                                    ""
                                ),  # Empty path with info = progress bar description update
                                info=info_msg,
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
