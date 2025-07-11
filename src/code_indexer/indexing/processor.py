"""Document processing utilities for indexing."""

import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..services import QdrantClient
from ..services.embedding_provider import EmbeddingProvider
from ..services.vector_calculation_manager import (
    VectorCalculationManager,
    get_default_thread_count,
)
from .file_finder import FileFinder
from .chunker import TextChunker
from .semantic_chunker import SemanticChunker
from typing import Union


@dataclass
class ProcessingStats:
    """Statistics from document processing."""

    files_processed: int = 0
    chunks_created: int = 0
    failed_files: int = 0
    total_size: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Processing duration in seconds."""
        return (
            self.end_time - self.start_time if self.end_time > self.start_time else 0.0
        )

    @property
    def files_per_second(self) -> float:
        """Files processed per second."""
        return self.files_processed / self.duration if self.duration > 0 else 0.0


class DocumentProcessor:
    """Processes documents for indexing."""

    def __init__(
        self,
        config: Config,
        embedding_provider: EmbeddingProvider,
        qdrant_client: QdrantClient,
    ):
        self.config = config
        self.embedding_provider = embedding_provider
        self.qdrant_client = qdrant_client
        self.file_finder = FileFinder(config)
        # Use semantic chunker if enabled, otherwise text chunker
        # Note: We assign to self.text_chunker for compatibility, but it may be a SemanticChunker
        self.text_chunker: Union[TextChunker, SemanticChunker]
        if config.indexing.use_semantic_chunking:
            self.text_chunker = SemanticChunker(config.indexing)
        else:
            self.text_chunker = TextChunker(config.indexing)

    def process_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """DEPRECATED: Use process_files_high_throughput instead."""
        raise NotImplementedError(
            "process_file is deprecated. Use process_files_high_throughput for all processing."
        )

    def process_file_parallel(
        self, file_path: Path, vector_manager: VectorCalculationManager
    ) -> List[Dict[str, Any]]:
        """Process a single file using parallel vector calculation."""
        try:
            # Step 1: File reading & chunking (main thread)
            chunks = self.text_chunker.chunk_file(file_path)

            if not chunks:
                return []

            # Step 2: Submit vector calculation tasks to worker threads
            chunk_futures = []
            for chunk in chunks:
                # Prepare metadata for the chunk
                chunk_metadata = {
                    "path": str(file_path.relative_to(self.config.codebase_dir)),
                    "language": chunk["file_extension"],
                    "file_size": file_path.stat().st_size,
                    "chunk_index": chunk["chunk_index"],
                    "total_chunks": chunk["total_chunks"],
                    "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "content": chunk[
                        "text"
                    ],  # Include content for Qdrant point creation
                    "line_start": chunk["line_start"],  # Line number metadata
                    "line_end": chunk["line_end"],  # Line number metadata
                }

                # Add semantic metadata if available
                if chunk.get("semantic_chunking", False):
                    chunk_metadata.update(
                        {
                            "semantic_chunking": chunk["semantic_chunking"],
                            "semantic_type": chunk.get("semantic_type"),
                            "semantic_name": chunk.get("semantic_name"),
                            "semantic_path": chunk.get("semantic_path"),
                            "semantic_signature": chunk.get("semantic_signature"),
                            "semantic_parent": chunk.get("semantic_parent"),
                            "semantic_context": chunk.get("semantic_context", {}),
                            "semantic_scope": chunk.get("semantic_scope"),
                            "semantic_language_features": chunk.get(
                                "semantic_language_features", []
                            ),
                        }
                    )
                else:
                    chunk_metadata["semantic_chunking"] = False

                # Submit to vector calculation manager
                future = vector_manager.submit_chunk(chunk["text"], chunk_metadata)
                chunk_futures.append(future)

            # Step 3: Collect results and create Qdrant points (main thread)
            points = []
            for future in chunk_futures:
                try:
                    vector_result = future.result(
                        timeout=300
                    )  # 5 minute timeout per chunk

                    if vector_result.error:
                        raise ValueError(
                            f"Vector calculation failed: {vector_result.error}"
                        )

                    # Create Qdrant point with the calculated embedding
                    payload = {
                        "path": vector_result.metadata["path"],
                        "content": vector_result.metadata["content"],
                        "language": vector_result.metadata["language"],
                        "file_size": vector_result.metadata["file_size"],
                        "chunk_index": vector_result.metadata["chunk_index"],
                        "total_chunks": vector_result.metadata["total_chunks"],
                        "indexed_at": vector_result.metadata["indexed_at"],
                        "line_start": vector_result.metadata["line_start"],
                        "line_end": vector_result.metadata["line_end"],
                        "semantic_chunking": vector_result.metadata.get(
                            "semantic_chunking", False
                        ),
                    }

                    # Add semantic metadata if available
                    if vector_result.metadata.get("semantic_chunking", False):
                        payload.update(
                            {
                                "semantic_type": vector_result.metadata.get(
                                    "semantic_type"
                                ),
                                "semantic_name": vector_result.metadata.get(
                                    "semantic_name"
                                ),
                                "semantic_path": vector_result.metadata.get(
                                    "semantic_path"
                                ),
                                "semantic_signature": vector_result.metadata.get(
                                    "semantic_signature"
                                ),
                                "semantic_parent": vector_result.metadata.get(
                                    "semantic_parent"
                                ),
                                "semantic_context": vector_result.metadata.get(
                                    "semantic_context", {}
                                ),
                                "semantic_scope": vector_result.metadata.get(
                                    "semantic_scope"
                                ),
                                "semantic_language_features": vector_result.metadata.get(
                                    "semantic_language_features", []
                                ),
                            }
                        )

                    point = self.qdrant_client.create_point(
                        vector=vector_result.embedding,
                        payload=payload,
                        embedding_model=self.embedding_provider.get_current_model(),
                    )
                    points.append(point)

                except Exception as e:
                    # Log the error but continue with other chunks
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to process chunk in {file_path}: {e}")
                    raise  # Re-raise to fail the entire file if any chunk fails

            return points

        except Exception as e:
            raise ValueError(f"Failed to process file {file_path}: {e}")

    def process_files(
        self,
        files: List[Path],
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """DEPRECATED: Use process_files_high_throughput instead."""
        raise NotImplementedError(
            "process_files is deprecated. Use process_files_high_throughput for all processing."
        )

    def process_files_parallel(
        self,
        files: List[Path],
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        vector_thread_count: Optional[int] = None,
    ) -> ProcessingStats:
        """Process multiple files with parallel vector calculation."""
        stats = ProcessingStats()
        stats.start_time = time.time()

        # Determine thread count
        if vector_thread_count is None:
            vector_thread_count = get_default_thread_count(self.embedding_provider)

        # Create vector calculation manager
        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:

            batch_points = []

            for i, file_path in enumerate(files):
                try:
                    # Process file with parallel vector calculation
                    points = self.process_file_parallel(file_path, vector_manager)

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

                    # Call progress callback with vector stats
                    if progress_callback:
                        vector_stats = vector_manager.get_stats()
                        # Include vector calculation throughput in info
                        info_msg = f"Vector threads: {vector_thread_count}, Queue: {vector_stats.queue_size}, {vector_stats.embeddings_per_second:.1f} emb/s | {file_path.name}"
                        # Use empty path with info to ensure progress bar updates instead of individual messages
                        progress_callback(i + 1, len(files), Path(""), info=info_msg)

                except Exception as e:
                    stats.failed_files += 1
                    if progress_callback:
                        progress_callback(i + 1, len(files), file_path, error=str(e))

            # Process remaining points
            if batch_points:
                if not self.qdrant_client.upsert_points(batch_points):
                    raise RuntimeError("Failed to upload final batch to Qdrant")

        stats.end_time = time.time()
        return stats

    def get_indexable_stats(self) -> Dict[str, Any]:
        """Get statistics about indexable files."""
        return self.file_finder.get_file_stats()
