"""
Smart incremental indexer that combines index and update functionality.
"""

import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from ..config import Config
from ..services import QdrantClient
from ..services.embedding_provider import EmbeddingProvider
from ..services.git_aware_processor import GitAwareDocumentProcessor
from ..indexing.processor import ProcessingStats
from .progressive_metadata import ProgressiveMetadata


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
        """Process files with progressive metadata updates."""

        stats = ProcessingStats()
        stats.start_time = time.time()

        batch_points = []

        def update_metadata(chunks_count=0, failed=False):
            """Update metadata after each file."""
            self.progressive_metadata.update_progress(
                files_processed=1,
                chunks_added=chunks_count,
                failed_files=1 if failed else 0,
            )

        for i, file_path in enumerate(files):
            points = []

            try:
                # Process file
                points = self.process_file(file_path)

                if points:
                    batch_points.extend(points)
                    stats.chunks_created += len(points)

                stats.files_processed += 1
                stats.total_size += file_path.stat().st_size

                # Process batch if full
                if len(batch_points) >= batch_size:
                    if not self.qdrant_client.upsert_points(batch_points):
                        raise RuntimeError("Failed to upload batch to Qdrant")
                    batch_points = []

                # Update metadata after successful processing
                update_metadata(chunks_count=len(points), failed=False)

                # Call progress callback
                if progress_callback:
                    progress_callback(i + 1, len(files), file_path)

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
