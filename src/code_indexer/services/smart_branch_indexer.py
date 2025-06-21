"""
Smart Branch Indexer for efficient incremental branch-aware indexing.

Handles branch-aware incremental indexing with topology understanding,
working directory support, and performance optimization.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from .git_topology_service import GitTopologyService
from .qdrant import QdrantClient
from .metadata_schema import GitAwareMetadataSchema
from ..indexing import TextChunker
from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class IndexingStats:
    """Statistics for indexing operations."""

    files_processed: int = 0
    chunks_created: int = 0
    metadata_updates: int = 0
    failed_files: int = 0
    duration: float = 0.0
    performance_stats: Optional[Dict[str, Any]] = None

    def merge(self, other: "IndexingStats") -> None:
        """Merge another IndexingStats into this one."""
        self.files_processed += other.files_processed
        self.chunks_created += other.chunks_created
        self.metadata_updates += other.metadata_updates
        self.failed_files += other.failed_files
        self.duration += other.duration

        if self.performance_stats is None:
            self.performance_stats = {}
        if other.performance_stats:
            self.performance_stats.update(other.performance_stats)


class SmartBranchIndexer:
    """Handles branch-aware incremental indexing with topology understanding."""

    def __init__(
        self,
        config: Config,
        embedding_provider,
        qdrant_client: QdrantClient,
        git_topology_service: GitTopologyService,
    ):
        """Initialize the smart branch indexer.

        Args:
            config: Application configuration
            embedding_provider: Embedding provider instance
            qdrant_client: Qdrant database client
            git_topology_service: Git topology analysis service
        """
        self.config = config
        self.embedding_provider = embedding_provider
        self.qdrant_client = qdrant_client
        self.git_topology_service = git_topology_service
        self.text_chunker = TextChunker(config.indexing)

    def handle_branch_change(
        self,
        old_branch: str,
        new_branch: str,
        progress_callback: Optional[Callable] = None,
        batch_size: int = 50,
    ) -> IndexingStats:
        """Execute smart incremental indexing based on branch change analysis."""
        start_time = time.time()
        stats = IndexingStats()

        logger.info(f"Handling branch change: {old_branch} -> {new_branch}")

        # Analyze branch change to determine what needs updating
        analysis = self.git_topology_service.analyze_branch_change(
            old_branch, new_branch
        )

        logger.info(
            f"Branch analysis: {len(analysis.files_to_reindex)} files to reindex, "
            f"{len(analysis.files_to_update_metadata)} metadata updates, "
            f"{len(analysis.staged_files)} staged, {len(analysis.unstaged_files)} unstaged"
        )

        try:
            # 1. Batch update metadata for unchanged files (fast operation)
            if analysis.files_to_update_metadata:
                if progress_callback:
                    progress_callback(
                        0,
                        len(analysis.files_to_update_metadata),
                        Path(""),
                        info="Updating branch metadata...",
                    )

                success = self.qdrant_client.batch_update_branch_metadata(
                    analysis.files_to_update_metadata, new_branch
                )

                if success:
                    stats.metadata_updates = len(analysis.files_to_update_metadata)
                    logger.info(f"Updated metadata for {stats.metadata_updates} files")
                else:
                    logger.warning("Batch metadata update partially failed")

            # 2. Reindex only changed files between branches
            if analysis.files_to_reindex:
                if progress_callback:
                    progress_callback(
                        0,
                        len(analysis.files_to_reindex),
                        Path(""),
                        info="Reindexing changed files...",
                    )

                changed_stats = self._reindex_files(
                    analysis.files_to_reindex, new_branch, progress_callback, batch_size
                )
                stats.merge(changed_stats)

            # 3. Index staged files (uncommitted changes)
            if analysis.staged_files:
                if progress_callback:
                    progress_callback(
                        0,
                        len(analysis.staged_files),
                        Path(""),
                        info="Indexing staged files...",
                    )

                staged_stats = self._index_working_directory_files(
                    analysis.staged_files,
                    new_branch,
                    "staged",
                    progress_callback,
                    batch_size,
                )
                stats.merge(staged_stats)

            # 4. Index unstaged files (working directory changes)
            if analysis.unstaged_files:
                if progress_callback:
                    progress_callback(
                        0,
                        len(analysis.unstaged_files),
                        Path(""),
                        info="Indexing unstaged files...",
                    )

                unstaged_stats = self._index_working_directory_files(
                    analysis.unstaged_files,
                    new_branch,
                    "unstaged",
                    progress_callback,
                    batch_size,
                )
                stats.merge(unstaged_stats)

        except Exception as e:
            logger.error(f"Branch change handling failed: {e}")
            raise

        stats.duration = time.time() - start_time
        stats.performance_stats = analysis.performance_stats

        logger.info(
            f"Branch change completed in {stats.duration:.2f}s: "
            f"{stats.files_processed} files, {stats.chunks_created} chunks, "
            f"{stats.metadata_updates} metadata updates"
        )

        return stats

    def _reindex_files(
        self,
        file_paths: List[str],
        branch_name: str,
        progress_callback: Optional[Callable] = None,
        batch_size: int = 50,
    ) -> IndexingStats:
        """Reindex specific files with full content processing."""
        stats = IndexingStats()
        batch_points = []

        for i, file_path in enumerate(file_paths):
            try:
                full_path = self.config.codebase_dir / file_path

                if progress_callback:
                    progress_callback(i + 1, len(file_paths), full_path)

                if not full_path.exists() or not full_path.is_file():
                    # File was deleted - remove from index for this branch
                    self._remove_file_from_index(file_path, branch_name)
                    continue

                # Delete existing points for this file in the current branch only
                self.qdrant_client.delete_by_filter(
                    {
                        "must": [
                            {"key": "path", "match": {"value": file_path}},
                            {"key": "git_branch", "match": {"value": branch_name}},
                        ]
                    }
                )

                # Process file chunks
                chunks = self.text_chunker.chunk_file(full_path)
                if not chunks:
                    continue

                # Create points for each chunk
                for chunk in chunks:
                    # Get embedding for the chunk
                    embedding = self.embedding_provider.get_embedding(chunk["text"])

                    # Create git-aware metadata
                    git_metadata = self._get_git_metadata_for_file(
                        file_path, branch_name
                    )

                    # Create metadata using branch topology schema
                    payload = GitAwareMetadataSchema.create_branch_topology_metadata(
                        path=file_path,
                        content=chunk["text"],
                        language=chunk["file_extension"],
                        file_size=full_path.stat().st_size,
                        chunk_index=chunk["chunk_index"],
                        total_chunks=chunk["total_chunks"],
                        project_id=self._get_project_id(),
                        file_hash=str(full_path.stat().st_mtime),  # Simple hash for now
                        git_metadata=git_metadata,
                    )

                    # Create point for Qdrant
                    point = self.qdrant_client.create_point(
                        vector=embedding, payload=payload
                    )

                    batch_points.append(point)
                    stats.chunks_created += 1

                    # Process batch when full
                    if len(batch_points) >= batch_size:
                        if self.qdrant_client.upsert_points(batch_points):
                            batch_points = []
                        else:
                            logger.error(f"Failed to upsert batch for {file_path}")
                            stats.failed_files += 1
                            break

                stats.files_processed += 1

            except Exception as e:
                logger.error(f"Failed to reindex {file_path}: {e}")
                stats.failed_files += 1

        # Process remaining points
        if batch_points:
            self.qdrant_client.upsert_points(batch_points)

        return stats

    def _index_working_directory_files(
        self,
        file_paths: List[str],
        branch_name: str,
        status: str,  # "staged" or "unstaged"
        progress_callback: Optional[Callable] = None,
        batch_size: int = 50,
    ) -> IndexingStats:
        """Index working directory files with special status metadata."""
        stats = IndexingStats()
        batch_points = []

        for i, file_path in enumerate(file_paths):
            try:
                full_path = self.config.codebase_dir / file_path

                if progress_callback:
                    progress_callback(i + 1, len(file_paths), full_path)

                if not full_path.exists() or not full_path.is_file():
                    continue

                # Remove existing working directory entries for this file
                self.qdrant_client.delete_by_filter(
                    {
                        "must": [
                            {"key": "path", "match": {"value": file_path}},
                            {
                                "key": "working_directory_status",
                                "match": {"any": ["staged", "unstaged"]},
                            },
                        ]
                    }
                )

                # Process file chunks
                chunks = self.text_chunker.chunk_file(full_path)
                if not chunks:
                    continue

                # Create points for each chunk with working directory metadata
                for chunk in chunks:
                    # Get embedding for the chunk
                    embedding = self.embedding_provider.get_embedding(chunk["text"])

                    # Get git metadata
                    git_metadata = self._get_git_metadata_for_file(
                        file_path, branch_name
                    )

                    # Create working directory metadata
                    working_dir_metadata = {
                        "status": status,
                        "change_type": "modified",  # Could be enhanced to detect actual change type
                        "staged_at": (
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            if status == "staged"
                            else None
                        ),
                    }

                    # Create metadata using branch topology schema
                    payload = GitAwareMetadataSchema.create_branch_topology_metadata(
                        path=file_path,
                        content=chunk["text"],
                        language=chunk["file_extension"],
                        file_size=full_path.stat().st_size,
                        chunk_index=chunk["chunk_index"],
                        total_chunks=chunk["total_chunks"],
                        project_id=self._get_project_id(),
                        file_hash=str(full_path.stat().st_mtime),
                        git_metadata=git_metadata,
                        working_dir_metadata=working_dir_metadata,
                    )

                    # Create point for Qdrant
                    point = self.qdrant_client.create_point(
                        vector=embedding, payload=payload
                    )

                    batch_points.append(point)
                    stats.chunks_created += 1

                    # Process batch when full
                    if len(batch_points) >= batch_size:
                        if self.qdrant_client.upsert_points(batch_points):
                            batch_points = []
                        else:
                            logger.error(f"Failed to upsert batch for {file_path}")
                            stats.failed_files += 1
                            break

                stats.files_processed += 1

            except Exception as e:
                logger.error(f"Failed to index working directory file {file_path}: {e}")
                stats.failed_files += 1

        # Process remaining points
        if batch_points:
            self.qdrant_client.upsert_points(batch_points)

        return stats

    def _remove_file_from_index(
        self, file_path: str, branch_name: Optional[str] = None
    ) -> bool:
        """Remove entries for a file from the index, optionally for a specific branch."""
        try:
            if branch_name:
                # Remove only for specific branch
                filter_conditions = {
                    "must": [
                        {"key": "path", "match": {"value": file_path}},
                        {"key": "git_branch", "match": {"value": branch_name}},
                    ]
                }
                logger.debug(f"Removed {file_path} from index for branch {branch_name}")
            else:
                # Remove all entries for the file (all branches)
                filter_conditions = {
                    "must": [{"key": "path", "match": {"value": file_path}}]
                }
                logger.debug(f"Removed {file_path} from index (all branches)")

            self.qdrant_client.delete_by_filter(filter_conditions)
            return True
        except Exception as e:
            logger.error(f"Failed to remove {file_path} from index: {e}")
            return False

    def _get_git_metadata_for_file(
        self, file_path: str, branch_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get git metadata for a specific file."""
        if not self.git_topology_service.is_git_available():
            return None

        try:
            # Get basic git info
            current_commit = self.git_topology_service.get_current_branch()
            if not current_commit:
                return None

            # Get branch ancestry for topology
            ancestry = self.git_topology_service._get_branch_ancestry(branch_name)

            return {
                "commit_hash": ancestry[0] if ancestry else "unknown",
                "branch": branch_name,
                "branch_ancestry": ancestry[:10],  # Limit ancestry for performance
                "git_hash": "unknown",  # Could be enhanced with actual git hash
            }

        except Exception as e:
            logger.warning(f"Failed to get git metadata for {file_path}: {e}")
            return None

    def _get_project_id(self) -> str:
        """Get project identifier."""
        # This could be enhanced to get actual project ID from git or config
        return self.config.codebase_dir.name

    def cleanup_branch_data(self, branch_name: str) -> bool:
        """Clean up all data associated with a specific branch."""
        try:
            return self.qdrant_client.delete_branch_data(branch_name)
        except Exception as e:
            logger.error(f"Failed to cleanup branch data for {branch_name}: {e}")
            return False

    def ensure_branch_topology_indexes(self) -> bool:
        """Ensure branch topology indexes are created for performance."""
        # With the new BranchAwareIndexer architecture, indexes are managed automatically
        return True
