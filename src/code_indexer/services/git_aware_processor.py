"""
Git-aware document processor that extends the base DocumentProcessor.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from code_indexer.config import Config
from code_indexer.services import QdrantClient
from code_indexer.services.embedding_provider import EmbeddingProvider
from code_indexer.indexing.processor import DocumentProcessor, ProcessingStats
from code_indexer.services.file_identifier import FileIdentifier
from code_indexer.services.git_detection import GitDetectionService
from code_indexer.services.metadata_schema import (
    GitAwareMetadataSchema,
    MetadataValidator,
)


class GitAwareDocumentProcessor(DocumentProcessor):
    """Document processor with git-aware metadata enhancement."""

    def __init__(
        self,
        config: Config,
        embedding_provider: EmbeddingProvider,
        qdrant_client: QdrantClient,
    ):
        super().__init__(config, embedding_provider, qdrant_client)
        self.file_identifier = FileIdentifier(config.codebase_dir, config)
        self.git_detection = GitDetectionService(config.codebase_dir, config)

    def process_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Process a single file with git-aware metadata."""
        try:
            # Chunk the file using parent logic
            chunks = self.text_chunker.chunk_file(file_path)

            if not chunks:
                return []

            # Get git-aware metadata
            file_metadata = self.file_identifier.get_file_metadata(file_path)

            points = []
            for chunk in chunks:
                # Get embedding using the configured provider
                embedding = self.embedding_provider.get_embedding(chunk["text"])

                # Validate embedding dimensions
                if not self._validate_embedding(embedding):
                    raise ValueError(f"Invalid embedding dimensions for {file_path}")

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
                    path=str(file_path),
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
                point_id = self._create_point_id(file_metadata, chunk["chunk_index"])

                # Add the unique identifier to payload for tracking/deduplication
                payload["point_id"] = point_id
                payload["unique_key"] = self._create_unique_key(
                    file_metadata, chunk["chunk_index"]
                )

                # Create Qdrant point with embedding model metadata
                point = self.qdrant_client.create_point(
                    point_id=point_id,
                    vector=embedding,
                    payload=payload,
                    embedding_model=self.embedding_provider.get_current_model(),
                )
                points.append(point)

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

    def index_codebase(
        self,
        clear_existing: bool = False,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
        check_git_changes: bool = True,
    ) -> ProcessingStats:
        """Index the entire codebase with git-aware processing.

        Args:
            clear_existing: Whether to clear existing index
            batch_size: Batch size for processing
            progress_callback: Optional progress callback
            check_git_changes: Whether to check for git initialization
        """
        # Check for git initialization if requested
        if check_git_changes and self.git_detection.detect_git_initialization():
            # Git was newly initialized, force full re-index
            clear_existing = True

        # Use parent class indexing logic
        return super().index_codebase(clear_existing, batch_size, progress_callback)

    def update_index_smart(
        self,
        batch_size: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingStats:
        """Smart update that handles git-aware incremental updates.

        This method:
        1. Detects git changes (branch switches, commits)
        2. Finds files that need updating based on git metadata
        3. Removes outdated entries from the index
        4. Processes updated files
        """
        # Check for git state changes
        if self.git_detection.detect_git_initialization():
            # Git was newly initialized, full re-index
            return self.index_codebase(
                clear_existing=True,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )

        # Get current git state
        current_git_state = self.git_detection._get_current_git_state()
        previous_git_state = self.git_detection._load_previous_git_state()

        # Detect branch changes
        branch_changed = (
            current_git_state["git_available"]
            and previous_git_state.get("git_available")
            and current_git_state.get("branch") != previous_git_state.get("branch")
        )

        if branch_changed:
            # Branch changed, we need to update metadata for all files
            # But we don't need to clear the index since we're using git-aware point IDs
            files_to_update = list(self.file_finder.find_files())
        else:
            # Normal incremental update based on file modification times
            last_index_time = previous_git_state.get("last_index_time", 0)
            files_to_update = list(
                self.file_finder.find_modified_files(last_index_time)
            )

        if not files_to_update:
            return ProcessingStats()

        # Update git state
        self.git_detection._save_git_state(current_git_state)

        # Process updated files
        return self.process_files(files_to_update, batch_size, progress_callback)

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
