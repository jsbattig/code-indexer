"""
Smart incremental indexer that combines index and update functionality.
"""

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


@dataclass
class ThroughputStats:
    """Statistics for tracking indexing throughput and throttling."""

    files_per_minute: float = 0.0
    chunks_per_minute: float = 0.0
    embedding_requests_per_minute: float = 0.0
    is_throttling: bool = False
    throttle_reason: str = ""
    average_processing_time_per_file: float = 0.0


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

    def smart_index(
        self,
        force_full: bool = False,
        reconcile_with_database: bool = False,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        safety_buffer_seconds: int = 60,
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

            # Check for reconcile operation first
            if reconcile_with_database:
                return self._do_reconcile_with_database(
                    batch_size,
                    progress_callback,
                    git_status,
                    provider_name,
                    model_name,
                )

            # Determine indexing strategy
            if force_full:
                return self._do_full_index(
                    batch_size, progress_callback, git_status, provider_name, model_name
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
                    batch_size, progress_callback, git_status, provider_name, model_name
                )

            # Try incremental indexing
            return self._do_incremental_index(
                batch_size,
                progress_callback,
                git_status,
                provider_name,
                model_name,
                safety_buffer_seconds,
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
    ) -> ProcessingStats:
        """Perform full indexing."""

        # Ensure provider-aware collection exists and clear it
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider
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

        # Process files with progressive metadata updates
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
                batch_size, progress_callback, git_status, provider_name, model_name
            )

        # Ensure provider-aware collection exists for incremental indexing
        self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider
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

        # Process modified files with progressive metadata updates
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
    ) -> ProcessingStats:
        """Reconcile disk files with database contents and index missing/modified files."""

        # Ensure provider-aware collection exists
        collection_name = self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider
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
                        # Path is already absolute in the database
                        file_path = Path(point["payload"]["path"])

                        # Get timestamp from database (try different fields based on git vs filesystem)
                        db_timestamp = None

                        # For filesystem-based projects, use filesystem_mtime
                        if "filesystem_mtime" in point["payload"]:
                            db_timestamp = point["payload"]["filesystem_mtime"]
                        # For git-based projects, we'll compare using git hash or use indexed_at as fallback
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

        # Show what we're reconciling
        if progress_callback:
            total_files = len(all_files_to_index)
            already_indexed = len(indexed_files_with_timestamps)
            to_index = len(files_to_index)

            status_parts = []
            if missing_files > 0:
                status_parts.append(f"{missing_files} missing")
            if modified_files > 0:
                status_parts.append(f"{modified_files} modified")

            status_str = " + ".join(status_parts) if status_parts else "files"
            progress_callback(
                0,
                0,
                Path(""),
                info=f"Reconcile: {already_indexed}/{total_files} files up-to-date, indexing {to_index} {status_str}",
            )

        # Start/update indexing metadata
        if self.progressive_metadata.metadata["status"] != "in_progress":
            self.progressive_metadata.start_indexing(
                provider_name, model_name, git_status
            )

        # Store file list for resumability
        self.progressive_metadata.set_files_to_index(files_to_index)

        # Process missing files with resumable tracking
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
    ) -> ProcessingStats:
        """Resume a previously interrupted indexing operation."""

        # Ensure provider-aware collection exists for resuming
        self.qdrant_client.ensure_provider_aware_collection(
            self.config, self.embedding_provider
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

        # Process remaining files with resumable tracking
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

        # Throughput tracking
        throughput_window_start = time.time()
        throughput_window_files = 0
        throughput_window_chunks = 0
        throughput_window_size = 60.0  # 1 minute window
        last_throttle_check = time.time()
        current_throughput_stats = ThroughputStats()  # Cache current stats

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

        def calculate_throughput() -> ThroughputStats:
            """Calculate current throughput and detect throttling."""
            current_time = time.time()
            elapsed = current_time - throughput_window_start

            if elapsed <= 0:
                return ThroughputStats()

            # Calculate rates per minute
            files_per_min = (throughput_window_files / elapsed) * 60
            chunks_per_min = (throughput_window_chunks / elapsed) * 60
            avg_time_per_file = elapsed / max(throughput_window_files, 1)

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
                avg_time_per_file > 5.0 and not is_throttling
            ):  # More than 5 seconds per file
                is_throttling = True
                throttle_reason = (
                    f"Slow processing detected ({avg_time_per_file:.1f}s/file)"
                )

            return ThroughputStats(
                files_per_minute=files_per_min,
                chunks_per_minute=chunks_per_min,
                embedding_requests_per_minute=chunks_per_min,  # Assuming 1 request per chunk
                is_throttling=is_throttling,
                throttle_reason=throttle_reason,
                average_processing_time_per_file=avg_time_per_file,
            )

        for i, file_path in enumerate(files):
            points = []

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

                # Process batch if full
                if len(batch_points) >= batch_size:
                    if not self.qdrant_client.upsert_points(batch_points):
                        raise RuntimeError("Failed to upload batch to Qdrant")
                    batch_points = []

                # Update metadata after successful processing
                update_metadata(file_path, chunks_count=len(points), failed=False)

                # Calculate throughput every 30 seconds or every 50 files
                current_time = time.time()
                if (current_time - last_throttle_check > 30) or (i % 50 == 0 and i > 0):
                    current_throughput_stats = calculate_throughput()
                    last_throttle_check = current_time

                    # Reset throughput window if it's been more than window size
                    if current_time - throughput_window_start > throughput_window_size:
                        throughput_window_start = current_time
                        throughput_window_files = 0
                        throughput_window_chunks = 0

                # Call progress callback with cached throughput info
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
