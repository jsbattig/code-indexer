"""
Smart incremental indexer that combines index and update functionality.
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
from ..services.git_aware_processor import GitAwareDocumentProcessor
from ..indexing.processor import ProcessingStats
from .progressive_metadata import ProgressiveMetadata
from .git_topology_service import GitTopologyService
from .smart_branch_indexer import SmartBranchIndexer
from .branch_aware_indexer import BranchAwareIndexer

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


class SmartIndexer(GitAwareDocumentProcessor):
    """Smart indexer with progressive metadata and resumability."""

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
        self.smart_branch_indexer = SmartBranchIndexer(
            config, embedding_provider, qdrant_client, self.git_topology_service
        )

        # Initialize new branch-aware indexer with graph optimization
        self.branch_aware_indexer = BranchAwareIndexer(
            qdrant_client, embedding_provider, self.text_chunker, config
        )

    def smart_index(
        self,
        force_full: bool = False,
        reconcile_with_database: bool = False,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        safety_buffer_seconds: int = 60,
        files_count_to_process: Optional[int] = None,
        quiet: bool = False,
    ) -> ProcessingStats:
        """
        Smart indexing that automatically chooses between full and incremental indexing.

        Args:
            force_full: Force full reindex (like --clear)
            reconcile_with_database: Reconcile disk files with database contents
            batch_size: Batch size for processing
            progress_callback: Optional progress callback
            safety_buffer_seconds: Safety buffer for incremental indexing

        Returns:
            ProcessingStats with operation results
        """
        try:
            # Get current git status
            git_status = self.get_git_status()
            provider_name = self.embedding_provider.get_provider_name()
            model_name = self.embedding_provider.get_current_model()

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
                            f"{branch_result.content_points_created} content points, "
                            f"{branch_result.visibility_points_created} visibility points, "
                            f"{branch_result.content_points_reused} content points reused"
                        )

                        return stats

                    except Exception as e:
                        if progress_callback:
                            progress_callback(
                                0,
                                0,
                                Path(""),
                                info=f"Graph-optimized branch indexing failed: {e}, falling back to standard indexing",
                            )
                        # Fall through to standard indexing on error

            # Check for reconcile operation first
            if reconcile_with_database:
                return self._do_reconcile_with_database(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    files_count_to_process,
                    quiet,
                )

            # Determine indexing strategy
            if force_full:
                return self._do_full_index(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                    quiet,
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
            )

        except Exception as e:
            self.progressive_metadata.fail_indexing(str(e))
            raise

    def _do_full_index(
        self,
        batch_size: int,
        progress_callback: Optional[Callable],
        git_status: Dict[str, Any],
        provider_name: str,
        model_name: str,
        quiet: bool = False,
    ) -> ProcessingStats:
        """Perform full indexing."""

        # Ensure provider-aware collection exists and clear it
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet
        )
        self.qdrant_client.clear_collection(collection_name)
        self.progressive_metadata.clear()

        # Start indexing
        self.progressive_metadata.start_indexing(provider_name, model_name, git_status)

        # Find all files
        files_to_index = list(self.file_finder.find_files())

        if not files_to_index:
            self.progressive_metadata.complete_indexing()
            raise ValueError("No files found to index")

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Get current branch for indexing
        current_branch = self.git_topology_service.get_current_branch() or "master"

        # Use BranchAwareIndexer for consistent architecture
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for f in files_to_index:
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

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for full index
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.warning(
                f"BranchAwareIndexer failed during full index, falling back to standard indexing: {e}"
            )
            # Fallback to standard processing
            stats = self._process_files_with_metadata(
                files_to_index, batch_size, progress_callback, resumable=True
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
            self.progressive_metadata.complete_indexing()
            return ProcessingStats()

        # Show what we're doing
        if progress_callback:
            safety_time = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(resume_timestamp)
            )
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Incremental update: {len(files_to_index)} files modified since {safety_time}",
            )

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Get current branch for indexing
        current_branch = self.git_topology_service.get_current_branch() or "master"

        # Get collection name (already ensured above)
        collection_name = self.qdrant_client.resolve_collection_name(
            self.config, self.embedding_provider
        )

        # Use BranchAwareIndexer for consistent architecture
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for f in files_to_index:
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

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for incremental
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.warning(
                f"BranchAwareIndexer failed during incremental index, falling back to standard indexing: {e}"
            )
            # Fallback to standard processing
            stats = self._process_files_with_metadata(
                files_to_index, batch_size, progress_callback, resumable=True
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
    ) -> ProcessingStats:
        """Reconcile disk files with database contents and index missing/modified files."""

        # Ensure provider-aware collection exists
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider, quiet
        )

        # Get all files that should be indexed (from disk)
        all_files_to_index = list(self.file_finder.find_files())

        if not all_files_to_index:
            if progress_callback:
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

        # Get all points from the database for this collection with file timestamps
        indexed_files_with_timestamps: Dict[Path, float] = {}  # file_path -> timestamp
        try:
            # Use scroll to get all points in batches
            offset = None
            while True:
                points, next_offset = self.qdrant_client.scroll_points(
                    collection_name=collection_name,
                    limit=1000,  # Process in batches of 1000
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,  # We don't need vectors, just metadata
                )

                if not points:  # No more points
                    break

                # Extract file paths and timestamps from points
                for point in points:
                    if point.get("payload") and "path" in point["payload"]:
                        # Path in database might be relative, need to normalize for comparison
                        path_from_db = point["payload"]["path"]

                        # Convert to absolute path for consistent comparison
                        if Path(path_from_db).is_absolute():
                            file_path = Path(path_from_db)
                        else:
                            # Relative path from database, make it absolute
                            file_path = self.config.codebase_dir / path_from_db

                        # Get timestamp from database (priority order for accuracy)
                        db_timestamp = None

                        # Priority 1: file_mtime from new architecture (most accurate)
                        if "file_mtime" in point["payload"]:
                            db_timestamp = point["payload"]["file_mtime"]
                        # Priority 2: filesystem_mtime from legacy architecture
                        elif "filesystem_mtime" in point["payload"]:
                            db_timestamp = point["payload"]["filesystem_mtime"]
                        # Priority 3: created_at (indexing time, less accurate for file changes)
                        elif "created_at" in point["payload"]:
                            db_timestamp = point["payload"]["created_at"]
                        # Priority 4: indexed_at as last resort
                        elif "indexed_at" in point["payload"]:
                            # Convert indexed_at string back to timestamp for comparison
                            try:
                                dt = datetime.datetime.strptime(
                                    point["payload"]["indexed_at"], "%Y-%m-%dT%H:%M:%SZ"
                                )
                                db_timestamp = dt.timestamp()
                            except (ValueError, TypeError):
                                db_timestamp = 0

                        if db_timestamp is not None:
                            # Keep the most recent timestamp if multiple chunks exist for same file
                            if (
                                file_path not in indexed_files_with_timestamps
                                or db_timestamp
                                > indexed_files_with_timestamps[file_path]
                            ):
                                indexed_files_with_timestamps[file_path] = db_timestamp

                # Update offset for next batch
                offset = next_offset
                if offset is None:
                    break

        except Exception as e:
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), info=f"Database query failed: {e}, doing full index"
                )
            # If database query fails, do full index
            indexed_files_with_timestamps = {}

        # Debug: Show what was found in database
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Found {len(indexed_files_with_timestamps)} files in database collection '{collection_name}'",
            )

            # Debug: Show sample database timestamp format
            if indexed_files_with_timestamps:
                sample_file, sample_timestamp = next(
                    iter(indexed_files_with_timestamps.items())
                )
                try:
                    timestamp_str = datetime.datetime.fromtimestamp(
                        sample_timestamp
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"DEBUG: Sample DB timestamp for {sample_file.name}: {sample_timestamp} ({timestamp_str})",
                    )
                except (ValueError, OSError) as e:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        info=f"DEBUG: Invalid DB timestamp for {sample_file.name}: {sample_timestamp} - {e}",
                    )

        # Find files that need to be indexed (missing from DB or have newer timestamps)
        files_to_index = []
        modified_files = 0
        missing_files = 0

        for file_path in all_files_to_index:
            try:
                # Get current file modification time
                disk_mtime = file_path.stat().st_mtime

                if file_path not in indexed_files_with_timestamps:
                    # File exists on disk but not in database
                    files_to_index.append(file_path)
                    missing_files += 1
                else:
                    # File exists in both disk and database, compare timestamps
                    db_timestamp = indexed_files_with_timestamps[file_path]

                    # Add some tolerance (1 second) to account for filesystem precision differences
                    if disk_mtime > db_timestamp + 1.0:
                        # File on disk is newer than in database
                        files_to_index.append(file_path)
                        modified_files += 1

                        # Debug: Log first few modified file timestamp comparisons
                        if modified_files <= 3 and progress_callback:
                            disk_time_str = datetime.datetime.fromtimestamp(
                                disk_mtime
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            db_time_str = datetime.datetime.fromtimestamp(
                                db_timestamp
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            diff = disk_mtime - db_timestamp
                            progress_callback(
                                0,
                                0,
                                Path(""),
                                info=f"DEBUG: {file_path.name} - disk: {disk_time_str}, db: {db_time_str}, diff: {diff:.1f}s",
                            )

            except OSError:
                # File might have been deleted or is not accessible, skip it
                continue

        if not files_to_index:
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info="All files up-to-date - no reconciliation needed",
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
                    info=f"Reconcile: {already_indexed}/{total_files} files up-to-date, indexing {status_str}",
                )
            else:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"Reconcile: {already_indexed}/{total_files} files up-to-date, indexing {to_index} files",
                )

        # Start/update indexing metadata
        if self.progressive_metadata.metadata["status"] != "in_progress":
            self.progressive_metadata.start_indexing(
                provider_name, model_name, git_status
            )

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Get current branch for indexing
        current_branch = self.git_topology_service.get_current_branch() or "master"

        # Get collection name (already ensured above)
        collection_name = self.qdrant_client.resolve_collection_name(
            self.config, self.embedding_provider
        )

        # Use BranchAwareIndexer for consistent architecture
        try:
            # Convert absolute paths to relative paths for BranchAwareIndexer
            relative_files = []
            for f in files_to_index:
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

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for reconcile
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.warning(
                f"BranchAwareIndexer failed during reconcile, falling back to standard indexing: {e}"
            )
            # Fallback to standard processing
            stats = self._process_files_with_metadata(
                files_to_index, batch_size, progress_callback, resumable=True
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

        # Show what we're resuming
        if progress_callback:
            metadata_stats = self.progressive_metadata.get_stats()
            completed = metadata_stats.get("files_processed", 0)
            total = metadata_stats.get("total_files_to_index", 0)
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Resuming interrupted operation: {completed}/{total} files completed, {len(existing_files)} remaining",
            )

        # Get current branch for indexing
        current_branch = self.git_topology_service.get_current_branch() or "master"

        # Get collection name (already ensured above)
        collection_name = self.qdrant_client.resolve_collection_name(
            self.config, self.embedding_provider
        )

        # Use BranchAwareIndexer for consistent architecture
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

            branch_result = self.branch_aware_indexer.index_branch_changes(
                old_branch="",  # No old branch for resume
                new_branch=current_branch,
                changed_files=relative_files,
                unchanged_files=[],
                collection_name=collection_name,
                progress_callback=progress_callback,
            )

            # Convert BranchIndexingResult to ProcessingStats
            stats = ProcessingStats()
            stats.files_processed = branch_result.files_processed
            stats.chunks_created = branch_result.content_points_created
            stats.failed_files = 0
            stats.start_time = time.time() - branch_result.processing_time
            stats.end_time = time.time()

        except Exception as e:
            logger.warning(
                f"BranchAwareIndexer failed during resume, falling back to standard indexing: {e}"
            )
            # Fallback to standard processing
            stats = self._process_files_with_metadata(
                existing_files, batch_size, progress_callback, resumable=True
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
    ) -> ProcessingStats:
        """Process files with progressive metadata updates and throughput monitoring."""

        stats = ProcessingStats()
        stats.start_time = time.time()

        batch_points = []

        # Throughput tracking with rolling averages
        throughput_window_start = time.time()
        throughput_window_files = 0
        throughput_window_chunks = 0
        throughput_window_size = 60.0  # 1 minute window
        last_throttle_check = time.time()
        current_throughput_stats = ThroughputStats()  # Cache current stats

        # Rolling averages for stable time estimation
        files_per_min_rolling = RollingAverage(window_size=10)
        chunks_per_min_rolling = RollingAverage(window_size=10)
        processing_time_rolling = RollingAverage(window_size=15)

        # Track processing time per file
        individual_file_times = []

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

        def calculate_throughput(files_remaining: int = 0) -> ThroughputStats:
            """Calculate current throughput and detect throttling with rolling averages."""
            current_time = time.time()
            elapsed = current_time - throughput_window_start

            if elapsed <= 0:
                return ThroughputStats()

            # Calculate current window rates
            current_files_per_min = (throughput_window_files / elapsed) * 60
            current_chunks_per_min = (throughput_window_chunks / elapsed) * 60
            current_avg_time_per_file = elapsed / max(throughput_window_files, 1)

            # Add to rolling averages
            if throughput_window_files > 0:
                files_per_min_rolling.add(current_files_per_min)
                chunks_per_min_rolling.add(current_chunks_per_min)
                processing_time_rolling.add(current_avg_time_per_file)

            # Use rolling averages for stability
            stable_files_per_min = files_per_min_rolling.get_average()
            stable_chunks_per_min = chunks_per_min_rolling.get_average()
            stable_avg_time_per_file = processing_time_rolling.get_average()

            # Calculate estimated time remaining using rolling average
            estimated_time_remaining = 0.0
            if stable_files_per_min > 0 and files_remaining > 0:
                estimated_time_remaining = (files_remaining / stable_files_per_min) * 60

            # Detect throttling by checking embedding provider
            is_throttling = False
            throttle_reason = ""

            # Check if we're using VoyageAI and detect rate limiting
            provider_name = self.embedding_provider.get_provider_name()
            if provider_name == "voyage-ai":
                # Check if rate limiter indicates throttling
                if hasattr(self.embedding_provider, "rate_limiter"):
                    rate_limiter = self.embedding_provider.rate_limiter
                    wait_time = rate_limiter.wait_time(100)  # Estimate for 100 tokens
                    if wait_time > 0.5:  # If we need to wait more than 0.5 seconds
                        is_throttling = True
                        throttle_reason = f"API rate limiting (wait: {wait_time:.1f}s)"
                    elif rate_limiter.request_tokens < 10:  # Low on request tokens
                        is_throttling = True
                        throttle_reason = "API request quota running low"

            # Detect slow processing (could indicate network issues or service slowdown)
            if (
                stable_avg_time_per_file > 5.0 and not is_throttling
            ):  # More than 5 seconds per file
                is_throttling = True
                throttle_reason = (
                    f"Slow processing detected ({stable_avg_time_per_file:.1f}s/file)"
                )

            return ThroughputStats(
                files_per_minute=stable_files_per_min,
                chunks_per_minute=stable_chunks_per_min,
                embedding_requests_per_minute=stable_chunks_per_min,  # Assuming 1 request per chunk
                is_throttling=is_throttling,
                throttle_reason=throttle_reason,
                average_processing_time_per_file=stable_avg_time_per_file,
                estimated_time_remaining_seconds=estimated_time_remaining,
            )

        for i, file_path in enumerate(files):
            points = []
            file_start_time = time.time()

            try:
                # Process file
                points = self.process_file(file_path)

                if points:
                    batch_points.extend(points)
                    stats.chunks_created += len(points)
                    throughput_window_chunks += len(points)

                stats.files_processed += 1
                stats.total_size += file_path.stat().st_size
                throughput_window_files += 1

                # Track individual file processing time
                file_processing_time = time.time() - file_start_time
                individual_file_times.append(file_processing_time)

                # Process batch if full
                if len(batch_points) >= batch_size:
                    if not self.qdrant_client.upsert_points(batch_points):
                        raise RuntimeError("Failed to upload batch to Qdrant")
                    batch_points = []

                # Update metadata after successful processing
                update_metadata(file_path, chunks_count=len(points), failed=False)

                # Calculate throughput: initially after first 5 files, then every 30 seconds or every 50 files
                current_time = time.time()
                should_calculate = False

                if (
                    i < 5
                ):  # First 5 files - calculate more frequently for early estimates
                    should_calculate = (i > 0) and (i % 2 == 0)
                elif (current_time - last_throttle_check > 30) or (i % 50 == 0):
                    should_calculate = True

                if should_calculate:
                    files_remaining = len(files) - (i + 1)
                    current_throughput_stats = calculate_throughput(files_remaining)
                    last_throttle_check = current_time

                    # Reset throughput window if it's been more than window size
                    if current_time - throughput_window_start > throughput_window_size:
                        throughput_window_start = current_time
                        throughput_window_files = 0
                        throughput_window_chunks = 0

                # Call progress callback with enhanced info including time estimate
                if progress_callback:
                    # Create enhanced info string from cached stats
                    info_parts = []
                    if current_throughput_stats.files_per_minute > 0:
                        info_parts.append(
                            f"{current_throughput_stats.files_per_minute:.1f} files/min"
                        )
                    if current_throughput_stats.chunks_per_minute > 0:
                        info_parts.append(
                            f"{current_throughput_stats.chunks_per_minute:.1f} chunks/min"
                        )

                    # Add estimated time remaining
                    if current_throughput_stats.estimated_time_remaining_seconds > 0:
                        remaining_minutes = (
                            current_throughput_stats.estimated_time_remaining_seconds
                            / 60
                        )
                        if remaining_minutes >= 60:
                            hours = int(remaining_minutes // 60)
                            mins = int(remaining_minutes % 60)
                            info_parts.append(f"⏱️ {hours}h{mins}m left")
                        elif remaining_minutes >= 1:
                            info_parts.append(f"⏱️ {remaining_minutes:.0f}m left")
                        else:
                            info_parts.append(
                                f"⏱️ {current_throughput_stats.estimated_time_remaining_seconds:.0f}s left"
                            )

                    if current_throughput_stats.is_throttling:
                        info_parts.append(
                            f"🐌 {current_throughput_stats.throttle_reason}"
                        )
                    elif (
                        current_throughput_stats.files_per_minute > 60
                    ):  # Fast processing
                        info_parts.append("🚀 Full speed")

                    info = " | ".join(info_parts) if info_parts else None
                    result = progress_callback(i + 1, len(files), file_path, info=info)

                    # Check if we've been interrupted
                    if result == "INTERRUPT":
                        break

            except Exception as e:
                stats.failed_files += 1

                # Track failed file processing time too
                file_processing_time = time.time() - file_start_time
                individual_file_times.append(file_processing_time)

                # Update metadata even for failed files
                update_metadata(file_path, chunks_count=0, failed=True)

                if progress_callback:
                    result = progress_callback(
                        i + 1, len(files), file_path, error=str(e)
                    )
                    # Check if we've been interrupted even on error
                    if result == "INTERRUPT":
                        break

        # Process remaining points
        if batch_points:
            if not self.qdrant_client.upsert_points(batch_points):
                raise RuntimeError("Failed to upload final batch to Qdrant")

        stats.end_time = time.time()
        return stats

    def get_indexing_status(self) -> Dict[str, Any]:
        """Get current indexing status and statistics."""
        return self.progressive_metadata.get_stats()

    def can_resume(self) -> bool:
        """Check if indexing can be resumed."""
        stats = self.progressive_metadata.get_stats()
        can_resume = stats.get("can_resume", False)
        return bool(can_resume)

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
                f"{cleanup_result['visibility_points_hidden']} visibility points hidden"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup branch {branch}: {e}")
            return False

    def process_files_incrementally(
        self, file_paths: List[str], force_reprocess: bool = False, quiet: bool = False
    ) -> ProcessingStats:
        """Process specific files incrementally using git-aware indexing.

        Args:
            file_paths: List of relative file paths to process
            force_reprocess: Force reprocessing even if files seem up to date
            quiet: Suppress progress output

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
                    # File was deleted - handle it
                    collection_name = self.qdrant_client.resolve_collection_name(
                        self.config, self.embedding_provider
                    )
                    self.qdrant_client.delete_by_filter(
                        {"must": [{"key": "path", "match": {"value": file_path}}]}
                    )
                    if not quiet:
                        logger.info(f"Deleted vectors for removed file: {file_path}")

            if not absolute_paths:
                stats.end_time = time.time()
                return stats

            # Get current git state using git topology service
            git_state = self.git_topology_service.get_current_state()
            current_branch = git_state.get("current_branch", "unknown")

            # Use BranchAwareIndexer for git-aware processing
            collection_name = self.qdrant_client.resolve_collection_name(
                self.config, self.embedding_provider
            )

            # Convert to relative paths for indexer
            relative_files = []
            for abs_path in absolute_paths:
                try:
                    relative_files.append(
                        str(abs_path.relative_to(self.config.codebase_dir))
                    )
                except ValueError:
                    continue

            if relative_files:
                branch_result = self.branch_aware_indexer.index_branch_changes(
                    old_branch="",  # No old branch for incremental processing
                    new_branch=current_branch,
                    changed_files=relative_files,
                    unchanged_files=[],
                    collection_name=collection_name,
                    progress_callback=None,  # No progress callback for incremental processing
                )

                # Convert BranchIndexingResult to ProcessingStats
                stats.files_processed = branch_result.files_processed
                stats.chunks_created = branch_result.content_points_created
                stats.failed_files = 0

                if not quiet:
                    logger.info(
                        f"Processed {stats.files_processed} files incrementally"
                    )

        except Exception as e:
            logger.error(f"Incremental processing failed: {e}")
            stats.failed_files = len(file_paths)

        stats.end_time = time.time()
        return stats
