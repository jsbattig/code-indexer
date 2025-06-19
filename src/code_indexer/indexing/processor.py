"""Document processing utilities for indexing."""

import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..services import OllamaClient, QdrantClient
from .file_finder import FileFinder
from .chunker import TextChunker


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
        self, config: Config, ollama_client: OllamaClient, qdrant_client: QdrantClient
    ):
        self.config = config
        self.ollama_client = ollama_client
        self.qdrant_client = qdrant_client
        self.file_finder = FileFinder(config)
        self.text_chunker = TextChunker(config.indexing)

    def process_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Process a single file and return Qdrant points."""
        try:
            # Chunk the file
            chunks = self.text_chunker.chunk_file(file_path)

            if not chunks:
                return []

            points = []
            for chunk in chunks:
                # Get embedding
                embedding = self.ollama_client.get_embedding(chunk["text"])

                # Create Qdrant point
                point = self.qdrant_client.create_point(
                    vector=embedding,
                    payload={
                        "path": str(file_path.relative_to(self.config.codebase_dir)),
                        "content": chunk["text"],
                        "language": chunk["file_extension"],
                        "file_size": file_path.stat().st_size,
                        "chunk_index": chunk["chunk_index"],
                        "total_chunks": chunk["total_chunks"],
                        "indexed_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                    },
                )
                points.append(point)

            return points

        except Exception as e:
            raise ValueError(f"Failed to process file {file_path}: {e}")

    def process_files(
        self,
        files: List[Path],
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Process multiple files with batching."""
        stats = ProcessingStats()
        stats.start_time = time.time()

        batch_points = []

        for i, file_path in enumerate(files):
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

                # Call progress callback
                if progress_callback:
                    progress_callback(i + 1, len(files), file_path)

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

    def index_codebase(
        self,
        clear_existing: bool = False,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Index the entire codebase."""
        # Clear existing index if requested
        if clear_existing:
            self.qdrant_client.clear_collection()

        # Ensure collection exists before indexing
        if not self.qdrant_client.collection_exists():
            self.qdrant_client.create_collection()

        # Find files to index
        files_to_index = list(self.file_finder.find_files())

        if not files_to_index:
            raise ValueError("No files found to index")

        # Process files
        return self.process_files(files_to_index, batch_size, progress_callback)

    def update_index(
        self,
        since_timestamp: float,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Update index with files modified since timestamp."""
        # Find modified files
        modified_files = list(self.file_finder.find_modified_files(since_timestamp))

        if not modified_files:
            return ProcessingStats()  # No files to update

        # Process modified files
        return self.process_files(modified_files, batch_size, progress_callback)

    def get_indexable_stats(self) -> Dict[str, Any]:
        """Get statistics about indexable files."""
        return self.file_finder.get_file_stats()
