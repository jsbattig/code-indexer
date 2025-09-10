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
import concurrent.futures
from concurrent.futures import as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Set

from ..indexing.processor import ProcessingStats
from ..services.git_aware_processor import GitAwareDocumentProcessor
from .vector_calculation_manager import VectorCalculationManager
from .clean_slot_tracker import CleanSlotTracker, FileStatus
from .file_chunking_manager import FileChunkingManager, FileProcessingResult

# SURGICAL FIX: Remove RealTimeFeedbackManager import - causes individual callback spam

logger = logging.getLogger(__name__)

# Export imports for tests
__all__ = [
    "HighThroughputProcessor",
    "FileChunkingManager",
    "FileProcessingResult",
    "BranchIndexingResult",
    "FileStatus",  # Export unified FileStatus enum
]


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

        # CRITICAL FIX: Single cancellation event for unified cancellation
        self._cancellation_event = threading.Event()
        self._cancellation_lock = threading.Lock()

        # File processing rate tracking for files/s metric
        self._file_rate_lock = threading.Lock()
        self._file_processing_start_time = None
        self._file_completion_history = (
            []
        )  # List of (timestamp, files_completed) tuples
        self._rolling_window_seconds = (
            30.0  # Rolling window for smoothed files/s calculation
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

        # CleanSlotTracker system - single source of truth
        # Initialize lazily with actual thread count in process_files_high_throughput
        self.slot_tracker: CleanSlotTracker

    def request_cancellation(self) -> None:
        """Request cancellation of processing."""
        with self._cancellation_lock:
            self.cancelled = True
            self._cancellation_event.set()
        logger.info("High throughput processing cancellation requested")

    def _ensure_slot_tracker_initialized(self, thread_count: int = 8) -> None:
        """Ensure slot tracker is initialized with appropriate thread count.

        Args:
            thread_count: Number of threads to use for file tracking (defaults to 8 for backwards compatibility)
        """
        if not hasattr(self, "slot_tracker") or self.slot_tracker is None:
            self.slot_tracker = CleanSlotTracker(
                max_slots=thread_count + 2  # Match FileChunkingManager workers
            )
            logger.info(
                f"Initialized CleanSlotTracker with {thread_count + 2} max concurrent files"
            )

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
        # Ensure slot tracker is initialized for real-time file status tracking
        self._ensure_slot_tracker_initialized()

        # Use consolidated tracker - eliminates race conditions and duplication
        concurrent_data: List[Dict[str, Any]] = (
            self.slot_tracker.get_concurrent_files_data()
        )
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

        # Initialize CleanSlotTracker with proper thread count
        self._ensure_slot_tracker_initialized(vector_thread_count)

        stats = ProcessingStats()
        stats.start_time = time.time()

        # Initialize file processing rate tracking for files/s metric
        self._initialize_file_rate_tracking()

        # PARALLEL FILE PROCESSING: Replace sequential chunking with parallel submission
        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:
            with FileChunkingManager(
                vector_manager=vector_manager,
                chunker=self.fixed_size_chunker,
                qdrant_client=self.qdrant_client,
                thread_count=vector_thread_count,
                slot_tracker=self.slot_tracker,  # Clean tracker for real-time state
            ) as file_manager:

                # Submit all files for parallel processing
                file_futures = []
                for file_path in files:
                    try:
                        file_metadata = self.file_identifier.get_file_metadata(
                            file_path
                        )
                        file_future = file_manager.submit_file_for_processing(
                            file_path, file_metadata, progress_callback
                        )
                        file_futures.append(file_future)

                        # Update stats with file size for total tracking
                        file_size = file_path.stat().st_size
                        stats.total_size += file_size

                    except Exception as e:
                        logger.error(f"Failed to submit file {file_path}: {e}")
                        stats.failed_files += 1
                        continue

                if not file_futures:
                    logger.warning("No files to process")
                    return stats

                logger.info(
                    f"Submitted {len(file_futures)} files for parallel processing"
                )

                # CRITICAL FIX: Send initial progress callback to show display immediately
                # This ensures user sees the progress bar and slots right away
                if progress_callback and len(files) > 0:
                    initial_info = (
                        f"0/{len(files)} files (0%) | "
                        f"0.0 files/s | "
                        f"0.0 KB/s | "
                        f"{vector_thread_count} threads | "
                        f"Starting..."
                    )
                    callback_result = progress_callback(
                        0,  # current = 0 at start
                        len(files),  # total files
                        Path(""),  # Empty path
                        info=initial_info,
                    )

                    # Check for immediate cancellation
                    if callback_result == "INTERRUPT":
                        logger.info(
                            "Cancellation requested at start - stopping before processing"
                        )
                        self.cancelled = True
                        stats.cancelled = True
                        return stats

                # Collect file-level results
                completed_files = 0

                # SIMPLE FIX: Use reasonable timeout for all file results
                # No aggressive graduated timeouts that cause false failures
                file_result_timeout = (
                    600.0  # 10 minutes - reasonable for file completion
                )

                for file_future in as_completed(file_futures):
                    # SIMPLE BETWEEN-FILES-ONLY CANCELLATION:
                    # Check cancellation only between files, never during file processing
                    if self.cancelled:
                        logger.info(
                            "Cancellation requested - stopping after current file"
                        )
                        stats.cancelled = True
                        break

                    try:
                        # SIMPLE FIX: Use reasonable timeout for all file results
                        file_result = file_future.result(timeout=file_result_timeout)

                        if file_result.success:
                            stats.files_processed += 1
                            stats.chunks_created += file_result.chunks_processed
                            completed_files += 1

                            # Track source bytes for KB/s calculation when file completes
                            try:
                                file_size = file_result.file_path.stat().st_size
                                self._add_source_bytes_processed(file_size)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to track source bytes for {file_result.file_path}: {e}"
                                )

                            # CRITICAL FIX: Restore progress callback for file completion
                            # AsyncDisplayWorker was removed - we MUST call progress_callback
                            # to update the display with file progress
                            if progress_callback:
                                # Calculate current throughput metrics
                                files_per_second = self._calculate_files_per_second(
                                    completed_files
                                )
                                kb_per_second = self._calculate_kbs_throughput()
                                # Get active thread count from slot tracker
                                active_threads = 0
                                if self.slot_tracker:
                                    active_threads = self.slot_tracker.get_slot_count()

                                # Get concurrent files from slot tracker
                                concurrent_files = []
                                if self.slot_tracker:
                                    concurrent_files = (
                                        self.slot_tracker.get_concurrent_files_data()
                                    )

                                # Format progress info in expected format
                                progress_info = (
                                    f"{completed_files}/{len(files)} files ({100 * completed_files // len(files)}%) | "
                                    f"{files_per_second:.1f} files/s | "
                                    f"{kb_per_second:.1f} KB/s | "
                                    f"{active_threads} threads | "
                                    f"{file_result.file_path.name}"
                                )

                                # Call progress callback with proper parameters
                                callback_result = progress_callback(
                                    completed_files,  # current files completed
                                    len(files),  # total files to process
                                    file_result.file_path,
                                    info=progress_info,
                                    concurrent_files=concurrent_files,
                                )

                                # CRITICAL FIX: Check for user cancellation via progress callback
                                if callback_result == "INTERRUPT":
                                    logger.info(
                                        "Cancellation requested via progress callback - stopping processing"
                                    )
                                    self.cancelled = True
                                    stats.cancelled = True
                                    break
                        else:
                            stats.failed_files += 1
                            logger.error(f"File processing failed: {file_result.error}")

                    except concurrent.futures.TimeoutError:
                        # Check if cancelled during timeout
                        with self._cancellation_lock:
                            if self.cancelled:
                                logger.info(
                                    "File result timeout during cancellation - expected behavior"
                                )
                                # Cancel the future and continue to next
                                file_future.cancel()
                                continue

                        # Real timeout - legitimate slow processing with reasonable timeout
                        logger.warning(
                            f"File processing timeout after {file_result_timeout}s - very slow embedding provider or extremely large file"
                        )
                        stats.failed_files += 1
                        continue
                    except Exception as e:
                        logger.error(f"Failed to get file result: {e}")
                        stats.failed_files += 1
                        continue

        stats.end_time = time.time()
        # stats.files_processed already updated during processing
        logger.info(
            f"High-throughput processing completed: "
            f"{stats.files_processed} files, {stats.chunks_created} chunks in {stats.end_time - stats.start_time:.2f}s"
        )

        # STORY 1: Send final progress callback to reach 100% completion
        # This ensures Rich Progress bar shows 100% instead of stopping at ~94%
        if progress_callback and len(files) > 0:
            # Calculate final KB/s throughput for completion message
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

        # CleanSlotTracker doesn't require explicit cleanup thread management

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
            self.slot_tracker.get_concurrent_files_data()
        )
        return concurrent_files_data
