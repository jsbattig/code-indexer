"""
Git-aware document processor that extends the base DocumentProcessor.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import Config
from code_indexer.services.embedding_provider import EmbeddingProvider
from code_indexer.indexing.processor import DocumentProcessor
from code_indexer.services.file_identifier import FileIdentifier
from code_indexer.services.git_detection import GitDetectionService
from code_indexer.services.metadata_schema import (
    GitAwareMetadataSchema,
    MetadataValidator,
)
from code_indexer.services.vector_calculation_manager import VectorCalculationManager

logger = logging.getLogger(__name__)


class GitAwareDocumentProcessor(DocumentProcessor):
    """Document processor with git-aware metadata enhancement."""

    def __init__(
        self,
        config: Config,
        embedding_provider: EmbeddingProvider,
        vector_store_client: Any,  # QdrantClient or FilesystemVectorStore
    ):
        super().__init__(config, embedding_provider, vector_store_client)
        self.file_identifier = FileIdentifier(config.codebase_dir, config)
        self.git_detection = GitDetectionService(config.codebase_dir, config)

    def _normalize_path_for_storage(self, file_path: Path) -> str:
        """
        Normalize file path to relative for portable database storage.

        CRITICAL FOR COW CLONING: All paths stored in Qdrant must be relative
        to codebase_dir to ensure database portability across different filesystem
        locations (CoW clones, repository moves, etc.).

        Args:
            file_path: File path (absolute or relative)

        Returns:
            Relative path string for database storage

        Raises:
            ValueError: If file_path is not under codebase_dir
        """
        if file_path.is_absolute():
            try:
                return str(file_path.relative_to(self.config.codebase_dir))
            except ValueError as e:
                logger.error(
                    f"Cannot normalize path {file_path} - not under codebase_dir "
                    f"{self.config.codebase_dir}: {e}"
                )
                raise
        return str(file_path)

    def process_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Process a single file with git-aware metadata."""
        # Use VectorCalculationManager to process single file
        from .vector_calculation_manager import VectorCalculationManager

        thread_count = self.config.voyage_ai.parallel_requests
        with VectorCalculationManager(
            self.embedding_provider, thread_count
        ) as vector_manager:
            return self.process_file_parallel(file_path, vector_manager)

    def process_file_parallel(
        self, file_path: Path, vector_manager: VectorCalculationManager
    ) -> List[Dict[str, Any]]:
        """Process a single file with git-aware metadata using parallel vector calculation."""
        try:
            # Step 1: File reading & chunking (main thread)
            chunks = self.fixed_size_chunker.chunk_file(file_path)

            if not chunks:
                return []

            # Get git-aware metadata (main thread)
            file_metadata = self.file_identifier.get_file_metadata(file_path)

            # Step 2: Submit vector calculation tasks to worker threads
            chunk_futures = []
            for chunk in chunks:
                # Prepare comprehensive metadata for the chunk
                chunk_metadata = {
                    "chunk": chunk,
                    "file_metadata": file_metadata,
                    "file_path": str(file_path),
                }

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

                    # Note: vector_result.embedding now uses batch processing internally

                    # Reconstruct chunk and file metadata
                    chunk = vector_result.metadata["chunk"]
                    file_metadata = vector_result.metadata["file_metadata"]

                    # Validate embedding dimensions
                    if not self._validate_embedding(vector_result.embedding):
                        raise ValueError(
                            f"Invalid embedding dimensions for {file_path}"
                        )

                    # Create standardized git-aware metadata using schema
                    metadata_info = None
                    if file_metadata["git_available"]:
                        metadata_info = {
                            "commit_hash": file_metadata.get("commit_hash"),
                            "branch": file_metadata.get("branch"),
                            "git_hash": file_metadata.get("git_hash"),
                        }
                    else:
                        # For non-git projects, pass filesystem metadata as git_metadata (will be added as filesystem fields)
                        metadata_info = {
                            "file_mtime": file_metadata.get("file_mtime"),
                            "file_size": file_metadata.get("file_size"),
                        }

                    # Create payload using create_git_aware_metadata
                    payload = GitAwareMetadataSchema.create_git_aware_metadata(
                        path=self._normalize_path_for_storage(file_path),
                        content=chunk["text"],
                        language=chunk["file_extension"],
                        file_size=file_path.stat().st_size,
                        chunk_index=chunk["chunk_index"],
                        total_chunks=chunk["total_chunks"],
                        project_id=file_metadata["project_id"],
                        file_hash=file_metadata["file_hash"],
                        git_metadata=(
                            metadata_info if file_metadata["git_available"] else None
                        ),
                        line_start=chunk.get("line_start"),
                        line_end=chunk.get("line_end"),
                    )

                    # Manually add filesystem metadata for non-git projects
                    if not file_metadata["git_available"] and metadata_info:
                        if "file_mtime" in metadata_info:
                            payload["filesystem_mtime"] = metadata_info["file_mtime"]
                        if "file_size" in metadata_info:
                            payload["filesystem_size"] = metadata_info["file_size"]

                    # Validate metadata before creating point
                    if not MetadataValidator.validate_point_payload(payload):
                        # Log validation errors but continue processing
                        validation_result = GitAwareMetadataSchema.validate_metadata(
                            payload
                        )
                        print(
                            f"Warning: Metadata validation failed for {file_path}: {validation_result['errors']}"
                        )

                    # Create unique point ID using our git-aware scheme
                    point_id = self._create_point_id(
                        file_metadata, chunk["chunk_index"]
                    )

                    # Add the unique identifier to payload for tracking/deduplication
                    payload["point_id"] = point_id
                    payload["unique_key"] = self._create_unique_key(
                        file_metadata, chunk["chunk_index"]
                    )

                    # Create Qdrant point with the calculated embedding
                    point = self.qdrant_client.create_point(
                        point_id=point_id,
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

    def _create_point_id(self, file_metadata: Dict[str, Any], chunk_index: int) -> str:
        """Create deterministic UUID-based point ID.

        Uses a deterministic UUID based on the file signature and chunk index
        to ensure the same file+chunk always gets the same ID.
        """
        import uuid

        project_id = file_metadata["project_id"]

        # Use git blob hash if available, otherwise file hash
        if file_metadata["git_available"] and file_metadata.get("git_hash"):
            signature = file_metadata["git_hash"]
        else:
            signature = file_metadata["file_hash"]

        # Create deterministic seed for UUID
        seed_string = f"{project_id}:{signature}:{chunk_index}"

        # Generate deterministic UUID using namespace UUID and seed
        point_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, seed_string)

        return str(point_uuid)

    def _create_unique_key(
        self, file_metadata: Dict[str, Any], chunk_index: int
    ) -> str:
        """Create human-readable unique key for tracking purposes."""
        project_id = file_metadata["project_id"]

        # Use git blob hash if available, otherwise file hash
        if file_metadata["git_available"] and file_metadata.get("git_hash"):
            signature = file_metadata["git_hash"][:12]  # Short hash
        else:
            signature = file_metadata["file_hash"][:12]  # Short hash

        return f"{project_id}:{signature}:{chunk_index}"

    def _validate_embedding(self, embedding: List[float]) -> bool:
        """Validate embedding dimensions match collection configuration."""
        if not embedding:
            return False

        expected_size = self.config.qdrant.vector_size
        actual_size = len(embedding)

        if actual_size != expected_size:
            print(
                f"Warning: Embedding dimension mismatch. Expected: {expected_size}, Got: {actual_size}"
            )
            return False

        # Check for invalid values
        if not all(
            isinstance(x, (int, float)) and not (x != x) for x in embedding
        ):  # NaN check
            print("Warning: Embedding contains invalid values (NaN or non-numeric)")
            return False

        return True

    def get_git_status(self) -> Dict[str, Any]:
        """Get current git status and metadata."""
        git_state = self.git_detection._get_current_git_state()
        file_stats = self.get_indexable_stats()

        return {
            "git_available": git_state["git_available"],
            "current_branch": git_state.get("branch", "unknown"),
            "current_commit": git_state.get("commit_hash", "unknown"),
            "project_id": self.file_identifier._get_project_id(),
            "file_stats": file_stats,
            "last_index_time": git_state.get("last_index_time", 0),
        }
