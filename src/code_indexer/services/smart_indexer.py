"""
Smart incremental indexer that combines index and update functionality.
"""

import time
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
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        safety_buffer_seconds: int = 60,
    ) -> ProcessingStats:
        """
        Smart indexing that automatically chooses between full and incremental indexing.

        Args:
            force_full: Force full reindex (like --clear)
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

        # Process files with progressive metadata updates
        stats = self._process_files_with_metadata(
            files_to_index, batch_size, progress_callback
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

        # Process modified files with progressive metadata updates
        stats = self._process_files_with_metadata(
            files_to_index, batch_size, progress_callback
        )

        # Mark as completed
        self.progressive_metadata.complete_indexing()

        return stats

    def _process_files_with_metadata(
        self, files: List[Path], batch_size: int, progress_callback: Optional[Callable]
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

        def update_metadata(chunks_count=0, failed=False):
            """Update metadata after each file."""
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
                update_metadata(chunks_count=len(points), failed=False)

                # Calculate throughput every 30 seconds or every 50 files
                current_time = time.time()
                if (current_time - last_throttle_check > 30) or (i % 50 == 0 and i > 0):
                    throughput_stats = calculate_throughput()
                    last_throttle_check = current_time

                    # Reset throughput window if it's been more than window size
                    if current_time - throughput_window_start > throughput_window_size:
                        throughput_window_start = current_time
                        throughput_window_files = 0
                        throughput_window_chunks = 0

                # Call progress callback with throughput info
                if progress_callback:
                    throughput_stats = calculate_throughput()

                    # Create enhanced info string
                    info_parts = []
                    if throughput_stats.files_per_minute > 0:
                        info_parts.append(
                            f"{throughput_stats.files_per_minute:.1f} files/min"
                        )
                    if throughput_stats.chunks_per_minute > 0:
                        info_parts.append(
                            f"{throughput_stats.chunks_per_minute:.1f} chunks/min"
                        )
                    if throughput_stats.is_throttling:
                        info_parts.append(f"🐌 {throughput_stats.throttle_reason}")
                    elif throughput_stats.files_per_minute > 60:  # Fast processing
                        info_parts.append("🚀 Full speed")

                    info = " | ".join(info_parts) if info_parts else None
                    progress_callback(i + 1, len(files), file_path, info=info)

            except Exception as e:
                stats.failed_files += 1

                # Update metadata even for failed files
                update_metadata(chunks_count=0, failed=True)

                if progress_callback:
                    progress_callback(i + 1, len(files), file_path, error=str(e))

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
