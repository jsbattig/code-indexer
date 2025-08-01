"""
Smart incremental indexer that combines index and update functionality.

⚠️  CRITICAL PROGRESS REPORTING WARNING:
This module calls progress_callback with setup messages using total=0.
These MUST use total=0 to show as ℹ️ messages in CLI, not progress bar.
See BranchAwareIndexer for file progress patterns (total>0).
"""

import logging
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..services import QdrantClient
from ..services.embedding_provider import EmbeddingProvider
from ..indexing.processor import ProcessingStats
from .progressive_metadata import ProgressiveMetadata
from .git_topology_service import GitTopologyService

# Removed: SmartBranchIndexer (abandoned code)
from .branch_aware_indexer import BranchAwareIndexer
from .indexing_lock import IndexingLockError, create_indexing_lock
from .high_throughput_processor import HighThroughputProcessor
from .vector_calculation_manager import get_default_thread_count
from .git_hook_manager import GitHookManager

logger = logging.getLogger(__name__)


@dataclass
class ThroughputStats:
    """Statistics for tracking indexing throughput and throttling."""

    files_per_minute: float = 0.0
    chunks_per_minute: float = 0.0
    embedding_requests_per_minute: float = 0.0
    is_throttling: bool = False
    throttle_reason: str = ""
    average_processing_time_per_file: float = 0.0
    estimated_time_remaining_seconds: float = 0.0


@dataclass
class RollingAverage:
    """Maintains a rolling average for more stable time estimates."""

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.values: List[float] = []
        self.sum = 0.0

    def add(self, value: float):
        """Add a new value to the rolling average."""
        self.values.append(value)
        self.sum += value

        # Remove oldest value if window is full
        if len(self.values) > self.window_size:
            self.sum -= self.values.pop(0)

    def get_average(self) -> float:
        """Get the current rolling average."""
        if not self.values:
            return 0.0
        return self.sum / len(self.values)

    def get_count(self) -> int:
        """Get the number of values in the window."""
        return len(self.values)


class SmartIndexer(HighThroughputProcessor):
    """Smart indexer with progressive metadata and resumability using high-throughput queue-based processing."""

    def __init__(
        self,
        config: Config,
        embedding_provider: EmbeddingProvider,
        qdrant_client: QdrantClient,
        metadata_path: Path,
    ):
        super().__init__(config, embedding_provider, qdrant_client)
        self.progressive_metadata = ProgressiveMetadata(metadata_path)

        # Initialize branch topology services
        self.git_topology_service = GitTopologyService(config.codebase_dir)
        # Removed: SmartBranchIndexer initialization (abandoned code)

        # Initialize new branch-aware indexer with graph optimization
        self.branch_aware_indexer = BranchAwareIndexer(
            qdrant_client, embedding_provider, self.text_chunker, config
        )

        # Configure branch tracking
        self.branch_aware_indexer.metadata_file = metadata_path

        # Initialize git hook manager for branch change detection
        self.git_hook_manager = GitHookManager(config.codebase_dir, metadata_path)

    def smart_index(
        self,
        force_full: bool = False,
        reconcile_with_database: bool = False,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        safety_buffer_seconds: int = 60,
        files_count_to_process: Optional[int] = None,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
        detect_deletions: bool = False,
    ) -> ProcessingStats:
        """
        Smart indexing that automatically chooses between full and incremental indexing.

        Args:
            force_full: Force full reindex (like --clear)
            reconcile_with_database: Reconcile disk files with database contents
            batch_size: Batch size for processing
            progress_callback: Optional progress callback
            safety_buffer_seconds: Safety buffer for incremental indexing
            files_count_to_process: Limit number of files to process (for testing)
            quiet: Suppress progress output
            vector_thread_count: Number of threads for vector calculation
            detect_deletions: Detect and handle files deleted from filesystem but still in database

        Returns:
            ProcessingStats with operation results
        """
        # Create indexing lock to prevent concurrent operations
        metadata_dir = self.progressive_metadata.metadata_path.parent
        indexing_lock = create_indexing_lock(metadata_dir)

        try:
            # Acquire lock before starting indexing
            indexing_lock.acquire(str(self.config.codebase_dir))
        except IndexingLockError as e:
            raise RuntimeError(str(e))

        try:
            # Get current git status
            git_status = self.get_git_status()
            provider_name = self.embedding_provider.get_provider_name()
            model_name = self.embedding_provider.get_current_model()

            # Ensure git hook is installed for branch change detection
            try:
                self.git_hook_manager.ensure_hook_installed()
            except Exception as e:
                logger.warning(f"Failed to install git hook for branch tracking: {e}")
                # Continue without hook - branch tracking will fall back to git subprocess

            # Check for branch topology optimization (only if not forcing full and collection exists)
            if not force_full:
                # Invalidate cache to get fresh branch info
                self.git_topology_service.invalidate_cache()
                current_branch = self.git_topology_service.get_current_branch()
                collection_name = self.qdrant_client.resolve_collection_name(
                    self.config, self.embedding_provider
                )

                # Check for branch change by comparing stored branch with current branch
                stored_branch = self.progressive_metadata.metadata.get("current_branch")
                logger.info(
                    f"Branch change detection: stored_branch={stored_branch}, current_branch={current_branch}"
                )

                if (
                    current_branch
                    and stored_branch
                    and stored_branch != current_branch
                    and self.qdrant_client.collection_exists(collection_name)
                ):
                    # Branch change detected - use graph-optimized branch indexing
                    old_branch = stored_branch
                    if progress_callback:
                        progress_callback(
                            0,
                            0,
                            Path(""),
                            info=f"Branch change detected: {old_branch} -> {current_branch}, using graph-optimized indexing",
                        )

                    try:
                        # Analyze branch change to determine what needs indexing
                        analysis = self.git_topology_service.analyze_branch_change(
                            old_branch, current_branch
                        )

                        # Use the new branch-aware indexer
                        branch_result = self.branch_aware_indexer.index_branch_changes(
                            old_branch=old_branch,
                            new_branch=current_branch,
                            changed_files=analysis.files_to_reindex,
                            unchanged_files=analysis.files_to_update_metadata,
                            collection_name=collection_name,
                            progress_callback=progress_callback,
                            vector_thread_count=vector_thread_count,
                        )

                        # Convert to ProcessingStats format
                        stats = ProcessingStats()
                        stats.files_processed = branch_result.files_processed
                        stats.chunks_created = branch_result.content_points_created
                        stats.failed_files = 0  # BranchAwareIndexer doesn't track failures in the same way
                        stats.start_time = time.time() - branch_result.processing_time
                        stats.end_time = time.time()

                        # Update progressive metadata with new git status
                        updated_git_status = git_status.copy()
                        updated_git_status["branch"] = current_branch
                        self.progressive_metadata.start_indexing(
                            provider_name, model_name, updated_git_status
                        )
                        self.progressive_metadata.complete_indexing()

                        logger.info(
                            f"Graph-optimized branch indexing completed: "
                            f"{branch_result.content_points_created} content points created, "
                            f"{branch_result.content_points_reused} content points reused"
                        )

                        return stats

                    except Exception as e:
                        logger.error(
                            f"Graph-optimized branch indexing failed in git project: {e}"
                        )
                        # NO FALLBACK - fail fast in git projects
                        raise RuntimeError(
                            f"Git-aware graph-optimized indexing failed and fallbacks are disabled. "
                            f"Original error: {e}"
                        ) from e

            # Check for interrupted operations first - highest priority (unless forcing full)
            if (
                not force_full
                and self.progressive_metadata.can_resume_interrupted_operation()
            ):
                if progress_callback:
                    # Get preview stats for initial feedback
                    metadata_stats = self.progressive_metadata.get_stats()
                    completed = metadata_stats.get("files_processed", 0)
                    total = metadata_stats.get("total_files_to_index", 0)
                    remaining = metadata_stats.get("remaining_files", 0)
                    chunks_so_far = metadata_stats.get("chunks_indexed", 0)

                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"🔄 Resuming interrupted operation: {completed}/{total} files completed ({chunks_so_far} chunks), {remaining} files remaining",
                    )
                return self._do_resume_interrupted(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    quiet,
                    vector_thread_count,
                )

            # Check for reconcile operation
            if reconcile_with_database:
                return self._do_reconcile_with_database(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    files_count_to_process,
                    quiet,
                    vector_thread_count,
                )

            # Handle deletion detection for standard indexing (when not doing reconcile)
            if detect_deletions and not reconcile_with_database:
                self._detect_and_handle_deletions(progress_callback)

            # Determine indexing strategy
            if force_full:
                return self._do_full_index(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    quiet,
                    vector_thread_count,
                )

            # Check if we need to force full index due to configuration changes
            if self.progressive_metadata.should_force_full_index(
                provider_name, model_name, git_status
            ):
                if progress_callback:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info="Configuration changed, performing full index",
                    )
                return self._do_full_index(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    quiet,
                    vector_thread_count,
                )

            # Try incremental indexing
            return self._do_incremental_index(
                batch_size,
                progress_callback,
                git_status,
                provider_name,
                model_name,
                safety_buffer_seconds,
                quiet,
                vector_thread_count,
            )

        except KeyboardInterrupt:
            # User cancellation should NOT mark as failed - leave in resumable state
            logger.info("Indexing operation was cancelled by user - can be resumed")
            raise
        except Exception as e:
            self.progressive_metadata.fail_indexing(str(e))
            raise
        finally:
            # Always release the lock, even on exception
            indexing_lock.release()

    def _do_full_index(
        self,
        batch_size: int,
        progress_callback: Optional[Callable],
        git_status: Dict[str, Any],
        provider_name: str,
        model_name: str,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Perform full indexing."""
        # Debug: Log start of full index
        import os
        import datetime

        debug_file = os.path.expanduser("~/.tmp/cidx_debug.log")
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)
        with open(debug_file, "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] _do_full_index started\n")
            f.flush()

        # Ensure provider-aware collection exists and get info before clearing
        # Skip migration for full index (clear) since we'll clear all data anyway
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet, skip_migration=True
        )

        # Get collection info before clearing for meaningful feedback
        try:
            collection_info = self.qdrant_client.get_collection_info(collection_name)
            points_before_clear = collection_info.get("points_count", 0)
        except Exception:
            points_before_clear = 0

        # Clear collection and provide meaningful feedback
        self.qdrant_client.clear_collection(collection_name)
        if progress_callback and points_before_clear > 0:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🗑️  Cleared collection '{collection_name}' ({points_before_clear} documents removed)",
            )
        elif progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🗑️  Cleared collection '{collection_name}' (collection was empty)",
            )

        self.progressive_metadata.clear()

        # Start indexing
        self.progressive_metadata.start_indexing(provider_name, model_name, git_status)

        # Find all files
        with open(debug_file, "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] Finding files...\n")
            f.flush()
        files_to_index = list(self.file_finder.find_files())
        with open(debug_file, "a") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] Found {len(files_to_index)} files\n"
            )
            f.flush()

        if not files_to_index:
            self.progressive_metadata.complete_indexing()
            raise ValueError("No files found to index")

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Get current branch for indexing
        current_branch = self.git_topology_service.get_current_branch() or "master"

        # Use BranchAwareIndexer for git-aware processing with parallel embeddings
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for file_path in files_to_index:
                try:
                    # If path is absolute and within codebase_dir, make it relative
                    if file_path.is_absolute():
                        relative_files.append(
                            str(file_path.relative_to(self.config.codebase_dir))
                        )
                    else:
                        # Already relative, use as-is
                        relative_files.append(str(file_path))
                except ValueError:
                    # Path is not within codebase_dir, use as-is (shouldn't happen in normal usage)
                    relative_files.append(str(file_path))

            with open(debug_file, "a") as f:
                f.write(
                    f"[{datetime.datetime.now().isoformat()}] Calling branch_aware_indexer.index_branch_changes with {len(relative_files)} files\n"
                )
                f.flush()

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for full index
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
                vector_thread_count=vector_thread_count,
            )

            with open(debug_file, "a") as f:
                f.write(
                    f"[{datetime.datetime.now().isoformat()}] branch_aware_indexer.index_branch_changes completed\n"
                )
                f.flush()

            # For full indexing, hide all files that don't exist in current branch
            # This ensures proper branch isolation
            # IMPORTANT: Use ALL files in current branch, not just the ones being processed
            all_files_in_branch = list(self.file_finder.find_files())
            all_relative_files = []
            for file_path in all_files_in_branch:
                try:
                    if file_path.is_absolute():
                        all_relative_files.append(
                            str(file_path.relative_to(self.config.codebase_dir))
                        )
                    else:
                        all_relative_files.append(str(file_path))
                except ValueError:
                    all_relative_files.append(str(file_path))

            self.branch_aware_indexer.hide_files_not_in_branch(
                current_branch, all_relative_files, collection_name, progress_callback
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.error(
                f"BranchAwareIndexer failed during full index in git project: {e}"
            )
            # NO FALLBACK - fail fast in git projects
            raise RuntimeError(
                f"Git-aware indexing failed and fallbacks are disabled. "
                f"Original error: {e}"
            ) from e

        # Update metadata with actual processing results
        self.progressive_metadata.update_progress(
            files_processed=stats.files_processed,
            chunks_added=stats.chunks_created,
            failed_files=stats.failed_files,
        )

        # Mark as completed
        self.progressive_metadata.complete_indexing()

        return stats

    def _do_incremental_index(
        self,
        batch_size: int,
        progress_callback: Optional[Callable],
        git_status: Dict[str, Any],
        provider_name: str,
        model_name: str,
        safety_buffer_seconds: int,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Perform incremental indexing."""

        # Get resume timestamp with safety buffer
        resume_timestamp = self.progressive_metadata.get_resume_timestamp(
            safety_buffer_seconds
        )

        if resume_timestamp == 0.0:
            # No previous index found, do full index
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info="No previous index found, performing full index",
                )
            return self._do_full_index(
                batch_size,
                progress_callback,
                git_status,
                provider_name,
                model_name,
                quiet,
            )

        # Ensure provider-aware collection exists for incremental indexing
        self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet
        )

        # Start/resume indexing
        if self.progressive_metadata.metadata["status"] != "in_progress":
            self.progressive_metadata.start_indexing(
                provider_name, model_name, git_status
            )

        # Find files modified since resume timestamp
        files_to_index = list(self.file_finder.find_modified_files(resume_timestamp))

        if not files_to_index:
            # No files to update
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info="No files modified since last index - nothing to do",
                )
            self.progressive_metadata.complete_indexing()
            return ProcessingStats()

        # ⚠️  CRITICAL: Setup message MUST use total=0 to show as ℹ️ message, not progress bar
        # Show what we're doing
        if progress_callback:
            safety_time = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(resume_timestamp)
            )
            # ⚠️  CRITICAL: total=0 makes this show as ℹ️ message in CLI
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Incremental update: {len(files_to_index)} files modified since {safety_time}",
            )

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Use BranchAwareIndexer for git-aware processing with parallel embeddings (SINGLE PROCESSING PATH)
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for file_path in files_to_index:
                try:
                    # If path is absolute and within codebase_dir, make it relative
                    if file_path.is_absolute():
                        relative_files.append(
                            str(file_path.relative_to(self.config.codebase_dir))
                        )
                    else:
                        # Already relative, use as-is
                        relative_files.append(str(file_path))
                except ValueError:
                    # Path is not within codebase_dir, use as-is (shouldn't happen in normal usage)
                    relative_files.append(str(file_path))

            # Get current branch for indexing
            current_branch = self.git_topology_service.get_current_branch() or "master"

            # Ensure collection exists
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for incremental
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
                vector_thread_count=vector_thread_count,
            )

            # For incremental indexing, also hide files that don't exist in current branch
            # This ensures proper branch isolation even during incremental updates
            # IMPORTANT: Use ALL files in current branch, not just the ones being processed
            all_files_in_branch = list(self.file_finder.find_files())
            all_relative_files = []
            for file_path in all_files_in_branch:
                try:
                    if file_path.is_absolute():
                        all_relative_files.append(
                            str(file_path.relative_to(self.config.codebase_dir))
                        )
                    else:
                        all_relative_files.append(str(file_path))
                except ValueError:
                    all_relative_files.append(str(file_path))

            self.branch_aware_indexer.hide_files_not_in_branch(
                current_branch, all_relative_files, collection_name, progress_callback
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.error(
                f"BranchAwareIndexer failed during incremental indexing in git project: {e}"
            )
            # NO FALLBACK - fail fast in git projects
            raise RuntimeError(
                f"Git-aware incremental indexing failed and fallbacks are disabled. "
                f"Original error: {e}"
            ) from e

        # Update metadata with actual processing results
        self.progressive_metadata.update_progress(
            files_processed=stats.files_processed,
            chunks_added=stats.chunks_created,
            failed_files=stats.failed_files,
        )

        # Mark as completed
        self.progressive_metadata.complete_indexing()

        return stats

    def _do_reconcile_with_database(
        self,
        batch_size: int,
        progress_callback: Optional[Callable],
        git_status: Dict[str, Any],
        provider_name: str,
        model_name: str,
        files_count_to_process: Optional[int] = None,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Reconcile disk files with database contents and index missing/modified files."""

        # Ensure provider-aware collection exists
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet
        )

        # Get current branch early for working directory aware reconcile
        current_branch = "master"  # Default branch name
        if self.git_topology_service.is_git_available():
            current_branch = self.git_topology_service.get_current_branch() or "master"

        # Get all files that should be indexed (from disk)
        all_files_to_index = list(self.file_finder.find_files())

        if not all_files_to_index:
            if progress_callback:
                # ⚠️  CRITICAL: total=0 makes this show as ℹ️ message in CLI
                progress_callback(0, 0, Path(""), info="No files found to index")
            return ProcessingStats()

        # Query database to see what files are already indexed with timestamps
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Checking database collection '{collection_name}' for indexed files...",
            )

        # Get indexed files using efficient snapshot approach (no infinite loops, minimal memory)
        indexed_files_with_timestamps = self._get_indexed_files_snapshot(
            collection_name, progress_callback
        )

        # Show what was found in database with meaningful reconcile feedback
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"📊 Found {len(indexed_files_with_timestamps)} files in database collection '{collection_name}', {len(all_files_to_index)} files on disk",
            )

        # Find files that need to be indexed using working directory aware comparison
        files_to_index = []
        modified_files = 0
        missing_files = 0

        for file_path in all_files_to_index:
            try:
                # Get relative path for content ID generation
                relative_path = str(file_path.relative_to(self.config.codebase_dir))

                # Get what the current effective content ID should be
                current_effective_id = (
                    self.branch_aware_indexer._get_effective_content_id_for_reconcile(
                        relative_path
                    )
                )

                # Check what's currently visible for this file in current branch
                currently_visible_id = self._get_currently_visible_content_id(
                    relative_path, current_branch, collection_name
                )

                if currently_visible_id is None:
                    # File exists on disk but no visible content in current branch
                    files_to_index.append(file_path)
                    missing_files += 1
                elif current_effective_id != currently_visible_id:
                    # File exists but current state differs from what's visible
                    files_to_index.append(file_path)
                    modified_files += 1
                    # Log the difference for debugging with more details
                    logger.info(
                        f"RECONCILE: Content ID mismatch for {relative_path}: current='{current_effective_id}' vs visible='{currently_visible_id}' - will re-index"
                    )

            except Exception as e:
                # File might have issues, log and skip
                logger.warning(f"Failed to analyze file {file_path} for reconcile: {e}")
                continue

        # NEW: For git projects, unhide files that should be visible in current branch
        files_unhidden = 0  # Initialize for all code paths

        if self.git_topology_service.is_git_available():

            # CRITICAL FIX: Check ALL files in database for unhiding, not just files_to_index
            # This fixes the bug where files hidden in other branches don't get unhidden
            # when switching back to the branch where they should be visible
            disk_files_set = {
                str(f.relative_to(self.config.codebase_dir)) for f in all_files_to_index
            }
            for indexed_file_path in indexed_files_with_timestamps:
                # Convert indexed file path to relative string for comparison
                try:
                    if hasattr(indexed_file_path, "relative_to"):
                        relative_file_path = str(
                            indexed_file_path.relative_to(self.config.codebase_dir)
                        )
                    else:
                        relative_file_path = str(indexed_file_path)
                except ValueError:
                    continue

                # Check if this file exists on disk in current branch (should be visible)
                if relative_file_path in disk_files_set:
                    # File exists on disk, check if it's hidden for current branch
                    content_points, _ = self.qdrant_client.scroll_points(
                        filter_conditions={
                            "must": [
                                {"key": "type", "match": {"value": "content"}},
                                {"key": "path", "match": {"value": relative_file_path}},
                            ]
                        },
                        limit=1,  # Just need to check one point
                        collection_name=collection_name,
                    )

                    if content_points:
                        hidden_branches = (
                            content_points[0]
                            .get("payload", {})
                            .get("hidden_branches", [])
                        )
                        if current_branch in hidden_branches:
                            # File exists on disk but is hidden for current branch - unhide it
                            self.branch_aware_indexer._unhide_file_in_branch(
                                relative_file_path, current_branch, collection_name
                            )
                            files_unhidden += 1

            if files_unhidden > 0 and progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"👁️  Made {files_unhidden} files visible in current branch '{current_branch}'",
                )

        # DIAGNOSTIC: Log reconcile progress after visibility update
        logger.info(
            f"Reconcile visibility update completed - made {files_unhidden} files visible in branch '{current_branch}', proceeding to deletion detection"
        )

        # NEW: Detect files that exist in database but were deleted from filesystem
        deleted_files = []
        disk_files_set = {
            str(f.relative_to(self.config.codebase_dir)) for f in all_files_to_index
        }

        for indexed_file_path in indexed_files_with_timestamps:
            # Convert to string for comparison
            indexed_file_str = (
                str(indexed_file_path.relative_to(self.config.codebase_dir))
                if hasattr(indexed_file_path, "relative_to")
                else str(indexed_file_path)
            )

            if indexed_file_str not in disk_files_set:
                # CRITICAL: Check if file genuinely deleted from filesystem vs just branch switch
                if self.is_git_aware():
                    # For git projects, check if file exists in current working directory
                    # If it doesn't exist on disk at all, it was genuinely deleted
                    file_path = self.config.codebase_dir / indexed_file_str
                    if not file_path.exists():
                        # File was genuinely deleted from filesystem - safe to remove from database
                        deleted_files.append(indexed_file_str)
                    # If file exists on disk but not in our scan, it might be excluded by filters
                    # In that case, branch isolation will handle visibility
                else:
                    # File exists in database but not on disk - was deleted (non-git projects)
                    deleted_files.append(indexed_file_str)

        # Handle deleted files using branch-aware strategy
        if deleted_files:
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            for deleted_file in deleted_files:
                self.delete_file_branch_aware(
                    deleted_file, collection_name, watch_mode=False
                )

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"🗑️  Cleaned up {len(deleted_files)} deleted files from database",
                )

        if not files_to_index:
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"✅ All {len(all_files_to_index)} files up-to-date - no reconciliation needed",
                )
            return ProcessingStats()

        # Apply files count limit if specified (for testing)
        if files_count_to_process is not None and files_to_index:
            original_count = len(files_to_index)
            files_to_index = files_to_index[:files_count_to_process]
            if progress_callback and len(files_to_index) < original_count:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"TESTING: Limited processing to {len(files_to_index)} files (of {original_count} total)",
                )

        # Show what we're reconciling
        if progress_callback:
            total_files = len(all_files_to_index)
            to_index = len(files_to_index)
            already_indexed = total_files - to_index  # Files that are truly up-to-date

            status_parts = []
            if missing_files > 0:
                status_parts.append(f"{missing_files} missing")
            if modified_files > 0:
                status_parts.append(f"{modified_files} modified")

            if status_parts:
                status_str = " + ".join(status_parts)
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"🔍 Reconcile: {already_indexed}/{total_files} files up-to-date, indexing {to_index} files ({status_str})",
                )
            else:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"🔍 Reconcile: {already_indexed}/{total_files} files up-to-date, indexing {to_index} files",
                )

        # Start/update indexing metadata
        if self.progressive_metadata.metadata["status"] != "in_progress":
            self.progressive_metadata.start_indexing(
                provider_name, model_name, git_status
            )

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # CRITICAL FIX: In non-git mode, delete old chunks for modified files before re-indexing
        # This ensures old content doesn't persist alongside new content
        if not self.is_git_aware() and files_to_index:
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            # Get relative paths that are being modified (not newly added)
            modified_relative_files = []
            for file_path in files_to_index:
                try:
                    # Check if this file was previously indexed (exists in database)
                    # indexed_files_with_timestamps has Path objects as keys
                    if file_path in indexed_files_with_timestamps:
                        if file_path.is_absolute():
                            relative_path = str(
                                file_path.relative_to(self.config.codebase_dir)
                            )
                        else:
                            relative_path = str(file_path)
                        modified_relative_files.append(relative_path)
                except ValueError:
                    continue

            # Delete old chunks for modified files
            if modified_relative_files:
                deleted_count = 0
                for relative_file_path in modified_relative_files:
                    success = self.qdrant_client.delete_by_filter(
                        {
                            "must": [
                                {"key": "path", "match": {"value": relative_file_path}}
                            ]
                        },
                        collection_name,
                    )
                    if success:
                        deleted_count += 1

                if progress_callback and deleted_count > 0:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"🗑️  Cleaned up old content for {deleted_count} modified files",
                    )

        # Use BranchAwareIndexer for git-aware processing with parallel embeddings (SINGLE PROCESSING PATH)
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for file_path in files_to_index:
                try:
                    # If path is absolute and within codebase_dir, make it relative
                    if file_path.is_absolute():
                        relative_files.append(
                            str(file_path.relative_to(self.config.codebase_dir))
                        )
                    else:
                        # Already relative, use as-is
                        relative_files.append(str(file_path))
                except ValueError:
                    # Path is not within codebase_dir, use as-is (shouldn't happen in normal usage)
                    relative_files.append(str(file_path))

            # Get current branch for indexing
            current_branch = self.git_topology_service.get_current_branch() or "master"

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for reconcile
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
                vector_thread_count=vector_thread_count,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.error(
                f"BranchAwareIndexer failed during reconcile in git project: {e}"
            )
            # NO FALLBACK - fail fast in git projects
            raise RuntimeError(
                f"Git-aware reconcile failed and fallbacks are disabled. "
                f"Original error: {e}"
            ) from e

        # Update metadata with actual processing results
        self.progressive_metadata.update_progress(
            files_processed=stats.files_processed,
            chunks_added=stats.chunks_created,
            failed_files=stats.failed_files,
        )

        # CRITICAL FIX: After reconcile indexing is complete, clean up multiple visible content points
        # This fixes the git restore scenario where both working_dir and committed content are visible
        if self.is_git_aware():
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )
            self._cleanup_multiple_visible_content_points(
                collection_name, current_branch, progress_callback
            )

        # Mark as completed
        self.progressive_metadata.complete_indexing()

        return stats

    def _do_resume_interrupted(
        self,
        batch_size: int,
        progress_callback: Optional[Callable],
        git_status: Dict[str, Any],
        provider_name: str,
        model_name: str,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Resume a previously interrupted indexing operation."""

        # Ensure provider-aware collection exists for resuming
        self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet
        )

        # Get remaining files from metadata
        remaining_file_strings = self.progressive_metadata.get_remaining_files()
        if not remaining_file_strings:
            # No files left to process
            self.progressive_metadata.complete_indexing()
            return ProcessingStats()

        # Convert strings back to Path objects
        remaining_files = [Path(f) for f in remaining_file_strings]

        # Filter out files that no longer exist
        existing_files = [f for f in remaining_files if f.exists()]

        if not existing_files:
            # All remaining files have been deleted
            self.progressive_metadata.complete_indexing()
            return ProcessingStats()

        # Show what we're resuming with detailed feedback
        if progress_callback:
            metadata_stats = self.progressive_metadata.get_stats()
            completed = metadata_stats.get("files_processed", 0)
            total = metadata_stats.get("total_files_to_index", 0)
            chunks_so_far = metadata_stats.get("chunks_indexed", 0)

            progress_callback(
                0,
                0,
                Path(""),
                info=f"🔄 Resuming interrupted operation: {completed}/{total} files completed ({chunks_so_far} chunks), {len(existing_files)} files remaining",
            )

        # Use BranchAwareIndexer for git-aware processing with parallel embeddings (SINGLE PROCESSING PATH)
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for f in existing_files:
                try:
                    # If path is absolute and within codebase_dir, make it relative
                    if f.is_absolute():
                        relative_files.append(
                            str(f.relative_to(self.config.codebase_dir))
                        )
                    else:
                        # Already relative, use as-is
                        relative_files.append(str(f))
                except ValueError:
                    # Path is not within codebase_dir, use as-is (shouldn't happen in normal usage)
                    relative_files.append(str(f))

            # Get current branch for indexing
            current_branch = self.git_topology_service.get_current_branch() or "master"

            # Ensure collection exists
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for resume
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
                vector_thread_count=vector_thread_count,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.error(f"BranchAwareIndexer failed during resume in git project: {e}")
            # NO FALLBACK - fail fast in git projects
            raise RuntimeError(
                f"Git-aware resume failed and fallbacks are disabled. "
                f"Original error: {e}"
            ) from e

        # Update metadata with actual processing results
        self.progressive_metadata.update_progress(
            files_processed=stats.files_processed,
            chunks_added=stats.chunks_created,
            failed_files=stats.failed_files,
        )

        # Mark as completed
        self.progressive_metadata.complete_indexing()

        return stats

    def _process_files_with_metadata(
        self,
        files: List[Path],
        batch_size: int,
        progress_callback: Optional[Callable],
        resumable: bool = False,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Process files with progressive metadata updates and throughput monitoring."""

        stats = ProcessingStats()
        stats.start_time = time.time()

        def update_metadata(file_path: Path, chunks_count=0, failed=False):
            """Update metadata after each file."""
            if resumable:
                # Use resumable tracking
                if failed:
                    self.progressive_metadata.mark_file_failed(str(file_path))
                else:
                    self.progressive_metadata.mark_file_completed(
                        str(file_path), chunks_count
                    )
            else:
                # Use legacy tracking
                self.progressive_metadata.update_progress(
                    files_processed=1,
                    chunks_added=chunks_count,
                    failed_files=1 if failed else 0,
                )

        # CRITICAL: Delete old chunks for files being re-indexed during reconcile
        # This prevents old content from remaining in the database when files are modified
        collection_name = self.qdrant_client.resolve_collection_name(
            self.config, self.embedding_provider
        )

        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🧹 Cleaning old chunks for {len(files)} files before re-indexing...",
            )

        files_cleaned = 0
        for file_path in files:
            # Convert to relative path for database lookup
            try:
                if file_path.is_absolute():
                    relative_path = str(file_path.relative_to(self.config.codebase_dir))
                else:
                    relative_path = str(file_path)
            except ValueError:
                # File outside codebase_dir, use as-is
                relative_path = str(file_path)

            # Delete all existing chunks for this file
            success = self.qdrant_client.delete_by_filter(
                {"must": [{"key": "path", "match": {"value": relative_path}}]},
                collection_name,
            )
            if success:
                files_cleaned += 1
                logger.debug(f"Deleted old chunks for file: {relative_path}")

        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"✅ Cleaned old chunks for {files_cleaned}/{len(files)} files",
            )

        # Use queue-based high-throughput processing for all code paths
        if vector_thread_count is None:
            vector_thread_count = get_default_thread_count(self.embedding_provider)

        # Process all files using queue-based high-throughput approach
        high_throughput_stats = self.process_files_high_throughput(
            files,
            vector_thread_count=vector_thread_count,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )

        # Update metadata for all files based on success/failure
        successful_files = high_throughput_stats.files_processed

        # For successful files, estimate chunks per file
        chunks_per_file = (
            high_throughput_stats.chunks_created // successful_files
            if successful_files > 0
            else 0
        )

        for i, file_path in enumerate(files):
            if i < successful_files:
                # File was processed successfully
                update_metadata(file_path, chunks_count=chunks_per_file, failed=False)
                stats.total_size += file_path.stat().st_size
            else:
                # File was not processed successfully
                update_metadata(file_path, chunks_count=0, failed=True)

        # Convert high-throughput stats to processing stats format
        stats.files_processed = high_throughput_stats.files_processed
        stats.chunks_created = high_throughput_stats.chunks_created
        stats.failed_files = high_throughput_stats.failed_files

        stats.end_time = time.time()
        return stats

    def get_indexing_status(self) -> Dict[str, Any]:
        """Get current indexing status and statistics."""
        return self.progressive_metadata.get_stats()

    def can_resume(self) -> bool:
        """Check if indexing can be resumed."""
        # Check both interrupted operations and general incremental resume capability
        stats = self.progressive_metadata.get_stats()
        can_resume_incremental = stats.get("can_resume", False)
        can_resume_interrupted = (
            self.progressive_metadata.can_resume_interrupted_operation()
        )

        return can_resume_incremental or can_resume_interrupted

    def clear_progress(self):
        """Clear progress metadata (for fresh start)."""
        self.progressive_metadata.clear()

    def cleanup_branch_data(self, branch: str) -> bool:
        """
        Clean up branch data using the graph-optimized approach.

        This delegates to the new BranchAwareIndexer for proper cleanup.
        """
        try:
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            cleanup_result = self.branch_aware_indexer.cleanup_branch(
                branch, collection_name
            )

            logger.info(
                f"Branch cleanup completed for {branch}: "
                f"{cleanup_result['content_points_hidden']} content points hidden, "
                f"{cleanup_result['content_points_preserved']} preserved"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup branch {branch}: {e}")
            return False

    def process_files_incrementally(
        self,
        file_paths: List[str],
        force_reprocess: bool = False,
        quiet: bool = False,
        vector_thread_count: Optional[int] = None,
        watch_mode: bool = False,
    ) -> ProcessingStats:
        """Process specific files incrementally using git-aware indexing.

        Args:
            file_paths: List of relative file paths to process
            force_reprocess: Force reprocessing even if files seem up to date
            quiet: Suppress progress output
            vector_thread_count: Number of threads for vector calculation
            watch_mode: If True, use verified deletion for reliability

        Returns:
            ProcessingStats with processing results
        """
        stats = ProcessingStats()
        stats.start_time = time.time()

        try:
            # Convert relative paths to absolute paths
            absolute_paths = []
            for file_path in file_paths:
                abs_path = self.config.codebase_dir / file_path
                if abs_path.exists():
                    absolute_paths.append(abs_path)
                else:
                    # File was deleted - handle cleanup using branch-aware strategy
                    logger.info(
                        f"🗑️  WATCH MODE: Processing deletion of {file_path} (watch_mode={watch_mode})"
                    )
                    collection_name = self.qdrant_client.resolve_collection_name(
                        self.config, self.embedding_provider
                    )
                    success = self.delete_file_branch_aware(
                        file_path, collection_name, watch_mode
                    )
                    if not success and watch_mode:
                        logger.error(
                            f"Watch mode deletion verification failed for {file_path}"
                        )
                        # Continue processing other files even if one deletion fails

            if not absolute_paths:
                stats.end_time = time.time()
                return stats

            # Convert to relative paths for indexer
            relative_files = []
            for abs_path in absolute_paths:
                try:
                    relative_files.append(
                        str(abs_path.relative_to(self.config.codebase_dir))
                    )
                except ValueError:
                    continue

            if absolute_paths:
                # Use BranchAwareIndexer for git-aware processing with parallel embeddings (SINGLE PROCESSING PATH)
                try:
                    # Get current branch for indexing
                    current_branch = (
                        self.git_topology_service.get_current_branch() or "master"
                    )

                    # Ensure collection exists
                    collection_name = self.qdrant_client.resolve_collection_name(
                        self.config, self.embedding_provider
                    )

                    branch_result = self.branch_aware_indexer.index_branch_changes(
                        old_branch="",  # No old branch for process files incrementally
                        new_branch=current_branch,
                        changed_files=relative_files,
                        unchanged_files=[],
                        collection_name=collection_name,
                        progress_callback=None,  # No progress callback for incremental processing
                        vector_thread_count=vector_thread_count,
                    )

                    # For incremental file processing, also ensure branch isolation
                    # IMPORTANT: Use ALL files in current branch, not just the ones being processed
                    all_files_in_branch = list(self.file_finder.find_files())
                    all_relative_files = []
                    for f in all_files_in_branch:
                        try:
                            if f.is_absolute():
                                all_relative_files.append(
                                    str(f.relative_to(self.config.codebase_dir))
                                )
                            else:
                                all_relative_files.append(str(f))
                        except ValueError:
                            all_relative_files.append(str(f))

                    self.branch_aware_indexer.hide_files_not_in_branch(
                        current_branch, all_relative_files, collection_name
                    )

                    # Convert BranchIndexingResult to ProcessingStats
                    stats.files_processed = branch_result.files_processed
                    stats.chunks_created = branch_result.content_points_created
                    stats.failed_files = 0

                except Exception as e:
                    logger.error(
                        f"BranchAwareIndexer failed during process_files_incrementally in git project: {e}"
                    )
                    # NO FALLBACK - fail fast in git projects
                    raise RuntimeError(
                        f"Git-aware incremental processing failed and fallbacks are disabled. "
                        f"Original error: {e}"
                    ) from e

                if not quiet:
                    logger.info(
                        f"Processed {stats.files_processed} files incrementally"
                    )

        except Exception as e:
            logger.error(f"Incremental processing failed: {e}")
            stats.failed_files = len(file_paths)

        stats.end_time = time.time()
        return stats

    def is_git_aware(self) -> bool:
        """Determine if this is a git-aware project."""
        return (
            self.git_topology_service is not None
            and self.git_topology_service.get_current_branch() is not None
        )

    def _get_indexed_files_snapshot(
        self, collection_name: str, progress_callback: Optional[Callable] = None
    ) -> Dict[Path, float]:
        """Get all indexed files with timestamps using efficient snapshot approach.

        This method loads only the minimal required data (file paths + timestamps)
        without vectors or full content, preventing memory issues and infinite loops.

        Returns:
            Dict mapping file paths to their timestamps
        """
        indexed_files_with_timestamps: Dict[Path, float] = {}

        try:
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), info="📸 Taking snapshot of indexed files..."
                )

            # Get all content points in a single atomic operation
            all_points = self._scroll_all_content_points(collection_name)

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"📊 Processing {len(all_points)} points from database snapshot",
                )

            # Process all points in memory (no database access = no consistency issues)
            for point in all_points:
                payload = point.get("payload", {})

                if "path" not in payload:
                    continue

                # Extract file path
                path_from_db = payload["path"]
                if Path(path_from_db).is_absolute():
                    file_path = Path(path_from_db)
                else:
                    file_path = self.config.codebase_dir / path_from_db

                # Extract best available timestamp
                timestamp = self._extract_best_timestamp(payload)

                # Keep the most recent timestamp per file (multiple chunks per file)
                if (
                    file_path not in indexed_files_with_timestamps
                    or timestamp > indexed_files_with_timestamps[file_path]
                ):
                    indexed_files_with_timestamps[file_path] = timestamp

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"✅ Snapshot complete: {len(indexed_files_with_timestamps)} unique files found",
                )

        except Exception as e:
            logger.error(f"Failed to get indexed files snapshot: {e}")
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"⚠️ Database snapshot failed: {e}, proceeding with empty state",
                )
            # Return empty dict - reconcile will treat all files as new
            indexed_files_with_timestamps = {}

        return indexed_files_with_timestamps

    def _scroll_all_content_points(self, collection_name: str) -> List[Dict[str, Any]]:
        """Scroll through all content points and return them as a list.

        This method uses only content points (not metadata) and excludes vectors
        for maximum memory efficiency.
        """
        all_points = []
        offset = None

        while True:
            points, next_offset = self.qdrant_client.scroll_points(
                collection_name=collection_name,
                filter_conditions={
                    "must": [{"key": "type", "match": {"value": "content"}}]
                },
                limit=5000,  # Larger batches for efficiency
                offset=offset,
                with_payload=True,
                with_vectors=False,  # CRITICAL: No vectors = massive memory savings
            )

            if not points:
                break

            all_points.extend(points)

            # Safety check to prevent infinite loops
            if next_offset == offset:
                logger.error(f"Pagination stuck at offset {offset} - breaking")
                break

            offset = next_offset
            if offset is None:
                break

        return all_points

    def _extract_best_timestamp(self, payload: Dict[str, Any]) -> float:
        """Extract the best available timestamp from payload."""
        # Priority 1: file_mtime from new architecture (most accurate)
        if "file_mtime" in payload:
            return float(payload["file_mtime"])
        # Priority 2: filesystem_mtime from legacy architecture
        elif "filesystem_mtime" in payload:
            return float(payload["filesystem_mtime"])
        # Priority 3: created_at (indexing time, less accurate for file changes)
        elif "created_at" in payload:
            return float(payload["created_at"])
        # Priority 4: indexed_at as last resort
        elif "indexed_at" in payload:
            try:
                dt = datetime.datetime.strptime(
                    payload["indexed_at"], "%Y-%m-%dT%H:%M:%SZ"
                )
                return dt.timestamp()
            except (ValueError, TypeError):
                return 0.0
        return 0.0

    def _get_currently_visible_content_id(
        self, file_path: str, branch: str, collection_name: str
    ) -> Optional[str]:
        """Get the content ID currently visible for this file in this branch."""
        try:
            # Query for content points for this file that are NOT hidden in this branch
            points, _ = self.qdrant_client.scroll_points(
                filter_conditions={
                    "must": [
                        {"key": "type", "match": {"value": "content"}},
                        {"key": "path", "match": {"value": file_path}},
                    ],
                    "must_not": [
                        {"key": "hidden_branches", "match": {"any": [branch]}}
                    ],
                },
                limit=10,  # Should be enough to find visible content
                collection_name=collection_name,
            )

            if not points:
                return None

            # CRITICAL FIX: Check if there are multiple visible points for this file
            # This can happen after git restore when both working_dir and committed content are visible
            if len(points) > 1:
                # Multiple content points visible - this is a problem that needs reconcile
                logger.warning(
                    f"Found {len(points)} visible content points for {file_path} in branch {branch}"
                )

                # Look for working directory content that should be hidden
                working_dir_points = []
                committed_points = []

                for point in points:
                    payload = point.get("payload", {})
                    git_commit_hash = payload.get("git_commit_hash", "unknown")

                    if git_commit_hash.startswith("working_dir_"):
                        working_dir_points.append(point)
                    else:
                        committed_points.append(point)

                # If we have both working_dir and committed content, prioritize committed
                # and schedule hiding of working_dir content
                if working_dir_points and committed_points:
                    logger.info(
                        f"Found mixed content for {file_path}: {len(working_dir_points)} working_dir + {len(committed_points)} committed - needs cleanup"
                    )

                    # Return the first committed content point to trigger reconcile
                    # The reconcile will detect mismatch and re-index, which will hide working_dir content
                    first_committed = committed_points[0]
                    payload = first_committed.get("payload", {})
                    commit = payload.get("git_commit_hash", "unknown")
                    return f"{file_path}:{commit}"

            # Find the most relevant content point (latest or most appropriate)
            # For now, return the first visible content point's effective ID
            for point in points:
                payload = point.get("payload", {})

                # Reconstruct content ID from point data
                path = payload.get("path", "")
                if path != file_path:
                    continue

                # Check if this is working_dir content or committed content
                if "working_dir" in str(point.get("id", "")):
                    # This is working directory content
                    return f"{file_path}:working_dir:{payload.get('filesystem_mtime', 'unknown')}:{payload.get('file_size', 0)}"
                else:
                    # This is committed content
                    # CRITICAL: Use git_commit_hash because that's what BranchAwareIndexer stores in payload
                    # (see branch_aware_indexer.py line 798: "git_commit_hash": commit)
                    # The ContentMetadata.git_commit field gets stored as git_commit_hash in Qdrant
                    commit = payload.get(
                        "git_commit_hash", payload.get("commit_hash", "unknown")
                    )
                    return f"{file_path}:{commit}"

            return None

        except Exception as e:
            logger.warning(
                f"Failed to get visible content ID for {file_path} in branch {branch}: {e}"
            )
            return None

    def _cleanup_multiple_visible_content_points(
        self,
        collection_name: str,
        current_branch: str,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        """
        Clean up situations where multiple content points are visible for the same file.

        This handles the git restore scenario where both working_dir and committed content
        are visible in the current branch, which should not happen.
        """
        try:
            # Get all content points visible in current branch
            all_points, _ = self.qdrant_client.scroll_points(
                filter_conditions={
                    "must": [
                        {"key": "type", "match": {"value": "content"}},
                    ],
                    "must_not": [
                        {"key": "hidden_branches", "match": {"any": [current_branch]}}
                    ],
                },
                limit=10000,  # Get all visible content points
                collection_name=collection_name,
            )

            if not all_points:
                return

            # Group points by file path
            files_with_points: Dict[str, List[Dict[str, Any]]] = {}
            for point in all_points:
                payload = point.get("payload", {})
                file_path = payload.get("path", "")
                if file_path:
                    if file_path not in files_with_points:
                        files_with_points[file_path] = []
                    files_with_points[file_path].append(point)

            # Find files with multiple visible content points
            files_to_cleanup = []
            for file_path, points in files_with_points.items():
                if len(points) > 1:
                    files_to_cleanup.append((file_path, points))

            if not files_to_cleanup:
                logger.debug(
                    "No multiple visible content points found - cleanup not needed"
                )
                return

            logger.info(
                f"Found {len(files_to_cleanup)} files with multiple visible content points - cleaning up"
            )

            # Clean up each file with multiple content points
            hidden_count = 0
            for file_path, points in files_to_cleanup:
                # Separate working_dir and committed content
                working_dir_points = []
                committed_points = []

                for point in points:
                    payload = point.get("payload", {})
                    git_commit_hash = payload.get("git_commit_hash", "")

                    if git_commit_hash.startswith("working_dir_"):
                        working_dir_points.append(point)
                    else:
                        committed_points.append(point)

                # If we have both types, hide working_dir content and keep committed content
                if working_dir_points and committed_points:
                    logger.info(
                        f"Hiding {len(working_dir_points)} working_dir points for {file_path} (keeping {len(committed_points)} committed)"
                    )

                    # Hide working directory content points
                    points_to_update = []
                    for point in working_dir_points:
                        point_id = point["id"]
                        payload = point.get("payload", {})
                        hidden_branches = payload.get("hidden_branches", [])

                        if current_branch not in hidden_branches:
                            new_hidden = hidden_branches + [current_branch]
                            points_to_update.append(
                                {
                                    "id": point_id,
                                    "payload": {"hidden_branches": new_hidden},
                                }
                            )

                    # Apply the updates
                    if points_to_update:
                        success = self.qdrant_client._batch_update_points(
                            points_to_update,
                            collection_name,
                        )
                        if success:
                            hidden_count += len(points_to_update)
                            logger.debug(
                                f"Successfully hid {len(points_to_update)} working_dir points for {file_path}"
                            )
                        else:
                            logger.warning(
                                f"Failed to hide working_dir points for {file_path}"
                            )

            if progress_callback and hidden_count > 0:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"🧹 Hidden {hidden_count} obsolete working directory content points",
                )

        except Exception as e:
            logger.warning(f"Failed to cleanup multiple visible content points: {e}")

    def delete_file_branch_aware(
        self, file_path: str, collection_name: str, watch_mode: bool = False
    ) -> bool:
        """Delete file using appropriate strategy based on project type.

        Args:
            file_path: Relative path of file to delete
            collection_name: Qdrant collection name
            watch_mode: If True, use verification for reliable watch mode deletion

        Returns:
            True if deletion was successful, False otherwise
        """
        if self.is_git_aware():
            # Use branch-aware soft delete for git projects
            current_branch = self.git_topology_service.get_current_branch()
            if current_branch:
                # DEADLOCK FIX: Always use fast deletion without verification
                # Trust synchronous operations - verification was causing 5+ minute hangs
                self.branch_aware_indexer._hide_file_in_branch(
                    file_path, current_branch, collection_name
                )
                logger.info(f"Hidden file in branch '{current_branch}': {file_path}")
                return True
            else:
                logger.warning(
                    f"Could not determine current branch for file deletion: {file_path}"
                )
                return False
        else:
            # DEADLOCK FIX: Use hard delete without verification
            # Trust synchronous operations - verification was causing 5+ minute hangs
            success = bool(
                self.qdrant_client.delete_by_filter(
                    {"must": [{"key": "path", "match": {"value": file_path}}]},
                    collection_name,
                )
            )
            if success:
                logger.info(f"Deleted vectors for removed file: {file_path}")
            else:
                logger.error(f"Failed to delete vectors for removed file: {file_path}")
            return success

    # DEADLOCK FIX: Removed _delete_file_hard_delete_with_verification method
    # The verification was causing 5+ minute hangs. Trust synchronous operations instead.

    def _detect_and_handle_deletions(
        self, progress_callback: Optional[Callable] = None
    ) -> None:
        """Detect and handle files that exist in database but were deleted from filesystem."""
        try:
            # Get collection name
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            # Get all files that should be indexed (from disk)
            disk_files = list(self.file_finder.find_files())
            disk_files_set = {
                str(f.relative_to(self.config.codebase_dir)) for f in disk_files
            }

            # Get all files from database (simplified version of reconcile logic)
            indexed_files = set()
            offset = None

            # DEADLOCK FIX: Add pagination safety to prevent infinite loops
            max_iterations = 1000  # Safety limit: max 1M points (1000 * 1000 limit)
            iteration_count = 0

            while True:
                try:
                    points, next_offset = self.qdrant_client.scroll_points(
                        filter_conditions={
                            "should": [
                                {"key": "type", "match": {"value": "content"}},
                                {"key": "type", "match": {"value": "visibility"}},
                            ]
                        },
                        limit=1000,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                        collection_name=collection_name,
                    )

                    for point in points:
                        if "path" in point["payload"]:
                            path_from_db = point["payload"]["path"]
                            # Normalize path - handle both relative and absolute paths
                            if Path(path_from_db).is_absolute():
                                file_path = Path(path_from_db)
                            else:
                                file_path = self.config.codebase_dir / path_from_db

                            # Convert to relative path string
                            try:
                                relative_path = str(
                                    file_path.relative_to(self.config.codebase_dir)
                                )
                                indexed_files.add(relative_path)
                            except ValueError:
                                # Path is outside codebase directory, skip
                                pass

                    offset = next_offset
                    iteration_count += 1

                    # DEADLOCK FIX: Check for infinite pagination loops
                    if iteration_count >= max_iterations:
                        logger.warning(
                            f"Pagination safety limit reached ({max_iterations} iterations). "
                            f"Breaking out of deletion detection loop."
                        )
                        if progress_callback:
                            progress_callback(
                                0,
                                0,
                                Path(""),
                                info=f"⚠️ Pagination limit reached, continuing with {len(indexed_files)} files found",
                            )
                        break

                    if offset is None:
                        break

                except Exception as e:
                    if progress_callback:
                        progress_callback(
                            0,
                            0,
                            Path(""),
                            info=f"Database query failed during deletion detection: {e}",
                        )
                    return

            # Find deleted files
            deleted_files = []
            for indexed_file in indexed_files:
                if indexed_file not in disk_files_set:
                    deleted_files.append(indexed_file)

            # Handle deleted files
            if deleted_files:
                # DEADLOCK FIX: Add progress feedback during deletion processing
                for i, deleted_file in enumerate(deleted_files):
                    if progress_callback:
                        progress_callback(
                            i + 1,
                            len(deleted_files),
                            Path(deleted_file),
                            info=f"🗑️ Cleaning up deleted files ({i + 1}/{len(deleted_files)}): {deleted_file}",
                        )

                    self.delete_file_branch_aware(
                        deleted_file, collection_name, watch_mode=False
                    )

                if progress_callback:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"🗑️  Detected and cleaned up {len(deleted_files)} deleted files",
                    )
                logger.info(
                    f"Deletion detection: cleaned up {len(deleted_files)} deleted files"
                )
            else:
                if progress_callback:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info="🔍 Deletion detection: no deleted files found",
                    )
                logger.info("Deletion detection: no deleted files found")

        except Exception as e:
            logger.error(f"Deletion detection failed: {e}")
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), info=f"Deletion detection failed: {e}"
                )
