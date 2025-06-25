"""
Branch-Aware Content Indexer with Graph Topology Optimization.

This implementation separates content storage from branch visibility to achieve:
- O(δ) indexing time complexity (only changed files)
- O(1) branch visibility lookup time
- Precise cleanup without content loss
- Space efficiency through content deduplication

Architecture:
1. Content Points: Immutable, one per unique (file, commit) pair
2. Visibility Points: Mutable mapping from (branch, file) to content
3. Branch ancestry resolution for complex git topologies

✅ CLEAN PROGRESS REPORTING API ✅

This module uses clean, well-named methods for progress reporting:
- _update_file_progress(): Updates progress bar with file processing status
- _report_file_error(): Reports file processing errors with progress update

The old magic-parameter approach has been refactored into clear method names.
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable
import subprocess
from .vector_calculation_manager import (
    get_default_thread_count,
    VectorCalculationManager,
)

logger = logging.getLogger(__name__)


@dataclass
class ContentMetadata:
    """Metadata for immutable content points."""

    path: str
    chunk_index: int
    total_chunks: int
    git_commit: str
    content_hash: str
    file_size: int
    language: str
    created_at: float
    working_directory_status: str
    file_mtime: float  # File modification time for reconcile comparisons


@dataclass
class VisibilityMetadata:
    """Metadata for branch visibility mapping."""

    branch: str
    path: str
    chunk_index: int
    content_id: str
    status: str  # 'visible' or 'hidden'
    priority: int  # For conflict resolution when multiple versions exist
    created_at: float


@dataclass
class BranchIndexingResult:
    """Result of branch-aware indexing operation."""

    content_points_created: int
    visibility_points_created: int
    visibility_points_updated: int
    content_points_reused: int
    processing_time: float
    files_processed: int


class BranchAwareIndexer:
    """
    Branch-aware content indexer with graph topology optimization.

    This indexer maintains immutable content points and mutable visibility
    mappings to achieve efficient branch switching and accurate cleanup.
    """

    def __init__(self, qdrant_client, embedding_provider, text_chunker, config):
        self.qdrant_client = qdrant_client
        self.embedding_provider = embedding_provider
        self.text_chunker = text_chunker
        self.config = config
        self.codebase_dir = Path(config.codebase_dir)

        # Will be set by smart indexer to point to metadata file
        self.metadata_file = None

    def _update_file_progress(
        self, progress_callback, current: int, total: int, info_msg: str
    ):
        """Clean helper to update file progress using appropriate API."""
        if not progress_callback:
            return None

        # Use specialized method if available (CLI adds this dynamically)
        if hasattr(progress_callback, "update_file_progress"):
            return progress_callback.update_file_progress(current, total, info_msg)
        else:
            # Use standard function signature - "." indicates no specific file
            return progress_callback(current, total, ".", info=info_msg)

    def _report_file_error(
        self, progress_callback, current: int, total: int, info_msg: str, error_msg: str
    ):
        """Clean helper to report file processing errors."""
        if not progress_callback:
            return None

        # Use specialized method if available (CLI adds this dynamically)
        if hasattr(progress_callback, "show_error_message"):
            progress_callback.show_error_message(".", error_msg)
            return self._update_file_progress(
                progress_callback, current, total, info_msg
            )
        else:
            # Use standard function signature - "." indicates no specific file
            return progress_callback(
                current, total, ".", info=info_msg, error=error_msg
            )

    def get_current_branch_from_file(self) -> str:
        """Get current branch from metadata file with retry logic."""
        if not self.metadata_file:
            # Fallback to git subprocess if no metadata file configured
            return self._get_current_branch_from_git()

        # Import here to avoid circular imports
        from .progressive_metadata import ProgressiveMetadata

        try:
            metadata = ProgressiveMetadata(self.metadata_file)
            return metadata.get_current_branch_with_retry(fallback="unknown")
        except Exception:
            # Fallback to git subprocess on any error
            return self._get_current_branch_from_git()

    def _get_current_branch_from_git(self) -> str:
        """Fallback method to get current branch from git subprocess."""
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return "unknown"

    def index_branch_changes(
        self,
        old_branch: str,
        new_branch: str,
        changed_files: List[str],
        unchanged_files: List[str],
        collection_name: str,
        progress_callback: Optional[Callable] = None,
        vector_thread_count: Optional[int] = None,
    ) -> BranchIndexingResult:
        """
        Index changes when switching branches using graph-optimized approach.

        Progress reporting is handled by clean helper methods (_update_file_progress, _report_file_error).

        Args:
            old_branch: Previous branch name
            new_branch: Target branch name
            changed_files: Files that differ between branches
            unchanged_files: Files that are identical between branches
            collection_name: Qdrant collection name
            progress_callback: Optional callback for progress updates

        Returns:
            BranchIndexingResult with operation statistics
        """
        start_time = time.time()
        result = BranchIndexingResult(
            content_points_created=0,
            visibility_points_created=0,
            visibility_points_updated=0,
            content_points_reused=0,
            processing_time=0,
            files_processed=0,
        )

        logger.info(
            f"Branch indexing: {old_branch} -> {new_branch}, "
            f"{len(changed_files)} changed, {len(unchanged_files)} unchanged"
        )

        try:
            # 1. Process changed files - create new content points
            if changed_files:
                content_result = self._index_changed_files(
                    changed_files,
                    new_branch,
                    collection_name,
                    progress_callback,
                    vector_thread_count,
                )
                result.content_points_created += content_result.content_points_created
                result.visibility_points_created += (
                    content_result.visibility_points_created
                )
                result.files_processed += len(changed_files)

            # 2. Update visibility for unchanged files - no content creation
            if unchanged_files:
                visibility_result = self._update_visibility_for_unchanged_files(
                    unchanged_files, old_branch, new_branch, collection_name
                )
                result.visibility_points_created += (
                    visibility_result.visibility_points_created
                )
                result.content_points_reused += visibility_result.content_points_reused

            result.processing_time = time.time() - start_time

            logger.info(
                f"Branch indexing completed: {result.content_points_created} content points, "
                f"{result.visibility_points_created} visibility points created, "
                f"{result.content_points_reused} content points reused"
            )

        except Exception as e:
            logger.error(f"Branch indexing failed: {e}")
            raise

        return result if result is not None else {}

    def _index_changed_files(
        self,
        file_paths: List[str],
        branch: str,
        collection_name: str,
        progress_callback: Optional[Callable] = None,
        vector_thread_count: Optional[int] = None,
    ) -> BranchIndexingResult:
        """Create content and visibility points for changed files."""
        result = BranchIndexingResult(0, 0, 0, 0, 0, 0)
        batch_points = []

        # Determine thread count for vector calculation
        if vector_thread_count is None:
            vector_thread_count = get_default_thread_count(self.embedding_provider)

        # Progress tracking
        total_files = len(file_paths)
        current_file_index = 0

        # Use VectorCalculationManager for parallel embedding processing
        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:
            for file_path in file_paths:
                try:
                    full_path = self.codebase_dir / file_path
                    if not full_path.exists():
                        # File was deleted - update visibility to hidden
                        self._hide_file_in_branch(file_path, branch, collection_name)

                        # Report progress for deleted file
                        # Call progress callback for deleted file if provided
                        if progress_callback:
                            files_completed = current_file_index + 1
                            file_progress_pct = (
                                (files_completed / total_files) * 100
                                if total_files > 0
                                else 0
                            )
                            display_file = Path(file_path)

                            info_msg = (
                                f"{files_completed}/{total_files} files ({file_progress_pct:.0f}%) | "
                                f"-- emb/s | "
                                f"1 threads | "
                                f"{display_file.name} (deleted)"
                            )

                            # Use clean helper method
                            callback_result = self._update_file_progress(
                                progress_callback,
                                files_completed,
                                total_files,
                                info_msg,
                            )
                            if callback_result == "INTERRUPT":
                                break
                        current_file_index += 1
                        continue

                    # Get current commit for this file
                    current_commit = self._get_file_commit(file_path)

                    # Check if content already exists for this file+commit
                    content_id = self._generate_content_id(file_path, current_commit)
                    if self._content_exists(content_id, collection_name):
                        # Content exists - just create visibility point
                        visibility_point = self._create_visibility_point(
                            branch, file_path, 0, content_id
                        )
                        batch_points.append(visibility_point)
                        result.content_points_reused += 1
                        result.visibility_points_created += 1

                        # Call progress callback for content reuse with proper format
                        if progress_callback:
                            files_completed = current_file_index + 1
                            file_progress_pct = (
                                (files_completed / total_files) * 100
                                if total_files > 0
                                else 0
                            )
                            display_file = Path(file_path)

                            # Format progress message
                            # Create comprehensive info message for content reuse
                            emb_speed = "-- emb/s"  # Default for content reuse (no new embeddings)
                            if vector_manager and hasattr(vector_manager, "get_stats"):
                                stats = vector_manager.get_stats()
                                if hasattr(stats, "embeddings_per_second"):
                                    emb_speed = (
                                        f"{stats.embeddings_per_second:.1f} emb/s"
                                    )

                            info_msg = (
                                f"{files_completed}/{total_files} files ({file_progress_pct:.0f}%) | "
                                f"{emb_speed} | "
                                f"{vector_manager.thread_count if vector_manager else 1} threads | "
                                f"{display_file.name} ✓"
                            )

                            # ⚠️  CRITICAL: total_files > 0 triggers CLI progress bar
                            # Report error with progress update
                            callback_result = self._update_file_progress(
                                progress_callback,
                                files_completed,
                                total_files,
                                info_msg,
                            )
                            if callback_result == "INTERRUPT":
                                break
                        current_file_index += 1
                        continue

                    # Content doesn't exist - create content + visibility points
                    chunks = self.text_chunker.chunk_file(full_path)
                    if not chunks:
                        # Call progress callback for empty file if provided
                        if progress_callback:
                            files_completed = current_file_index + 1
                            file_progress_pct = (
                                (files_completed / total_files) * 100
                                if total_files > 0
                                else 0
                            )
                            display_file = Path(file_path)

                            info_msg = (
                                f"{files_completed}/{total_files} files ({file_progress_pct:.0f}%) | "
                                f"-- emb/s | "
                                f"1 threads | "
                                f"{display_file.name} (empty)"
                            )

                            # Report error with progress update
                            callback_result = self._update_file_progress(
                                progress_callback,
                                files_completed,
                                total_files,
                                info_msg,
                            )
                            if callback_result == "INTERRUPT":
                                break
                        current_file_index += 1
                        continue

                    # CRITICAL FIX: Submit ALL chunks for parallel processing, then collect results
                    chunk_futures = []
                    chunk_data = []

                    # Always use parallel processing - no fallbacks needed
                    for chunk_idx, chunk in enumerate(chunks):
                        # Submit chunk for parallel processing (don't wait for result yet)
                        future = vector_manager.submit_chunk(
                            chunk["text"],
                            {"file_path": file_path, "chunk_index": chunk_idx},
                        )
                        chunk_futures.append(future)
                        chunk_data.append((chunk, current_commit))

                    # Collect parallel results
                    for idx, future in enumerate(chunk_futures):
                        try:
                            vector_result = future.result()
                            if vector_result.error:
                                logger.error(
                                    f"Vector calculation failed: {vector_result.error}"
                                )
                                continue

                            chunk, commit = chunk_data[idx]

                            # Create content point with precomputed embedding
                            content_point = self._create_content_point(
                                file_path,
                                chunk,
                                commit,
                                vector_result.embedding,
                                branch,
                            )
                            batch_points.append(content_point)
                            result.content_points_created += 1

                            # Create visibility point linking branch to content
                            visibility_point = self._create_visibility_point(
                                branch,
                                file_path,
                                chunk["chunk_index"],
                                content_point["id"],
                            )
                            batch_points.append(visibility_point)
                            result.visibility_points_created += 1

                        except Exception as e:
                            logger.error(f"Failed to process chunk result: {e}")
                            continue

                    result.files_processed += 1

                    # Call main progress callback for file completion with proper format
                    if progress_callback:
                        files_completed = current_file_index + 1
                        file_progress_pct = (
                            (files_completed / total_files) * 100
                            if total_files > 0
                            else 0
                        )
                        display_file = Path(file_path)

                        # Create comprehensive progress message matching HighThroughputProcessor format
                        emb_speed = "-- emb/s"  # Default when no stats available
                        if vector_manager and hasattr(vector_manager, "get_stats"):
                            stats = vector_manager.get_stats()
                            if hasattr(stats, "embeddings_per_second"):
                                emb_speed = f"{stats.embeddings_per_second:.1f} emb/s"

                        info_msg = (
                            f"{files_completed}/{total_files} files ({file_progress_pct:.0f}%) | "
                            f"{emb_speed} | "
                            f"{vector_manager.thread_count if vector_manager else 1} threads | "
                            f"{display_file.name} ✓"
                        )

                        # Update file progress using clean helper method
                        callback_result = self._update_file_progress(
                            progress_callback,
                            files_completed,
                            total_files,
                            info_msg,
                        )
                        if callback_result == "INTERRUPT":
                            break

                    current_file_index += 1

                    # Process batch when full
                    if len(batch_points) >= 50:
                        self.qdrant_client.upsert_points(batch_points, collection_name)
                        batch_points = []

                except Exception as e:
                    logger.error(f"Failed to index changed file {file_path}: {e}")

                    # Call progress callback for failed file if provided
                    if progress_callback:
                        files_completed = current_file_index + 1
                        file_progress_pct = (
                            (files_completed / total_files) * 100
                            if total_files > 0
                            else 0
                        )
                        display_file = Path(file_path)

                        info_msg = (
                            f"{files_completed}/{total_files} files ({file_progress_pct:.0f}%) | "
                            f"-- emb/s | "
                            f"1 threads | "
                            f"{display_file.name} (error: {str(e)[:50]}...)"
                        )

                        # Report error with progress update
                        self._report_file_error(
                            progress_callback,
                            files_completed,
                            total_files,
                            info_msg,
                            str(e),
                        )
                    current_file_index += 1

        # Process remaining points
        if batch_points:
            self.qdrant_client.upsert_points(batch_points, collection_name)

        return result if result is not None else {}

    def _update_visibility_for_unchanged_files(
        self,
        file_paths: List[str],
        old_branch: str,
        new_branch: str,
        collection_name: str,
    ) -> BranchIndexingResult:
        """Update visibility points for unchanged files without touching content."""
        result = BranchIndexingResult(0, 0, 0, 0, 0, 0)
        batch_points = []

        # Find content points that are visible in old branch
        for file_path in file_paths:
            try:
                # Get visibility points for this file in old branch
                old_visibility_points = self._get_visibility_points(
                    old_branch, file_path, collection_name
                )

                for vis_point in old_visibility_points:
                    content_id = vis_point["payload"]["content_id"]
                    chunk_index = vis_point["payload"]["chunk_index"]

                    # Create new visibility point for new branch
                    new_visibility_point = self._create_visibility_point(
                        new_branch, file_path, chunk_index, content_id
                    )
                    batch_points.append(new_visibility_point)
                    result.visibility_points_created += 1
                    result.content_points_reused += 1

                # Process batch when full
                if len(batch_points) >= 100:
                    self.qdrant_client.upsert_points(batch_points, collection_name)
                    batch_points = []

            except Exception as e:
                logger.error(f"Failed to update visibility for {file_path}: {e}")

        # Process remaining points
        if batch_points:
            self.qdrant_client.upsert_points(batch_points, collection_name)

        return result if result is not None else {}

    def _create_content_point(
        self,
        file_path: str,
        chunk: Dict[str, Any],
        commit: str,
        embedding: List[float],
        branch: str,
    ) -> Dict[str, Any]:
        """Create immutable content point with precomputed embedding and branch context."""
        # Generate content hash
        content_text = chunk["text"]
        content_hash = hashlib.sha256(content_text.encode()).hexdigest()

        # Determine working directory status
        working_dir_status = self._determine_working_dir_status(file_path)

        # Get file modification time for reconcile comparisons
        try:
            absolute_file_path = self.codebase_dir / file_path
            file_mtime = absolute_file_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            # If file doesn't exist or can't be accessed, use current time
            file_mtime = time.time()

        # Create content metadata
        metadata = ContentMetadata(
            path=file_path,
            chunk_index=chunk["chunk_index"],
            total_chunks=chunk["total_chunks"],
            git_commit=commit,
            content_hash=content_hash,
            file_size=len(content_text),
            language=self._detect_language(file_path),
            created_at=time.time(),
            working_directory_status=working_dir_status,
            file_mtime=file_mtime,
        )

        # Generate deterministic content ID
        content_id = self._generate_content_id(file_path, commit, chunk["chunk_index"])

        # Get git context for compatibility fields
        # Always use provided branch - no fallbacks needed
        project_id = self.codebase_dir.name

        # Create payload with compatibility fields for GenericQueryService
        # NOTE: Content points are IMMUTABLE and should NOT contain branch info
        # Branch info belongs in visibility points only
        payload = {
            "type": "content",
            # Original fields from ContentMetadata
            **metadata.__dict__,
            # Compatibility fields for GenericQueryService (branch-agnostic)
            "git_available": True,
            "file_path": file_path,  # Alias for 'path'
            "git_commit_hash": commit,  # Alias for 'git_commit'
            "content": content_text,  # Required for search results
            "indexed_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),  # ISO format for consistency
            # Project info (but NOT branch - that's in visibility points)
            "project_id": project_id,  # Project identifier
        }

        # Get embedding model name for metadata
        embedding_model = self.embedding_provider.get_current_model()

        result = self.qdrant_client.create_point(
            point_id=content_id,
            vector=embedding,
            payload=payload,
            embedding_model=embedding_model,
        )
        return result if result is not None else {}

    def _create_visibility_point(
        self, branch: str, file_path: str, chunk_index: int, content_id: str
    ) -> Dict[str, Any]:
        """Create visibility point linking branch to content."""
        # Generate deterministic UUID for visibility point
        visibility_str = f"vis_{branch}_{file_path}_{chunk_index}"
        namespace = uuid.UUID(
            "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
        )  # Different namespace
        visibility_id = str(uuid.uuid5(namespace, visibility_str))

        metadata = VisibilityMetadata(
            branch=branch,
            path=file_path,
            chunk_index=chunk_index,
            content_id=content_id,
            status="visible",
            priority=1,
            created_at=time.time(),
        )

        # Zero vector - not used for similarity search
        zero_vector = [0.0] * self._get_embedding_dimensions()

        result = self.qdrant_client.create_point(
            point_id=visibility_id,
            vector=zero_vector,
            payload={"type": "visibility", **metadata.__dict__},
        )
        return result if result is not None else {}

    def search_with_branch_context(
        self,
        query_vector: List[float],
        branch: str,
        limit: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search content with branch visibility filtering.

        This performs a two-stage search:
        1. Vector similarity search on content points
        2. Filter results by branch visibility
        """
        # Over-fetch to account for branch filtering
        content_results = self.qdrant_client.search(
            query_vector=query_vector,
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            limit=limit * 3,
            collection_name=collection_name,
        )

        if not content_results:
            return []

        # Get visible content IDs for this branch
        visible_content_ids = self._get_visible_content_ids(
            branch, collection_name or ""
        )

        # Filter content results by visibility
        filtered_results = []
        for result in content_results:
            if result["id"] in visible_content_ids:
                filtered_results.append(result)
                if len(filtered_results) >= limit:
                    break

        return filtered_results

    def cleanup_branch(self, branch: str, collection_name: str) -> Dict[str, int]:
        """
        Clean up branch data by hiding visibility points.

        This marks all visibility points for the branch as hidden.
        Content points are preserved for garbage collection.
        """
        logger.info(f"Cleaning up branch: {branch}")

        # Hide all visibility points for this branch
        updated_count = self.qdrant_client.batch_update_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": branch}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            payload_updates={"status": "hidden"},
            collection_name=collection_name,
        )

        logger.info(f"Hidden {updated_count} visibility points for branch {branch}")

        return {
            "visibility_points_hidden": updated_count,
            "content_points_preserved": 0,  # Use 0 instead of string for type consistency
        }

    def garbage_collect_content(self, collection_name: str) -> Dict[str, int]:
        """
        Remove content points that are no longer visible from any branch.

        This is a maintenance operation that can be run periodically.
        """
        logger.info("Starting content garbage collection")

        # Find all visible content IDs across all branches
        all_visible_content_ids = set()

        # Get all visibility points that are still visible
        visible_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            collection_name=collection_name,
            limit=10000,  # Adjust based on expected volume
        )

        for point in visible_points:
            content_id = point["payload"]["content_id"]
            all_visible_content_ids.add(content_id)

        # Find orphaned content points
        all_content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=10000,
        )

        orphaned_content_ids = []
        for point in all_content_points:
            if point["id"] not in all_visible_content_ids:
                orphaned_content_ids.append(point["id"])

        # Delete orphaned content points
        if orphaned_content_ids:
            deleted_count = self.qdrant_client.delete_points(
                point_ids=orphaned_content_ids, collection_name=collection_name
            )
            logger.info(f"Garbage collected {deleted_count} orphaned content points")
        else:
            deleted_count = 0
            logger.info("No orphaned content points found")

        return {
            "content_points_deleted": deleted_count,
            "content_points_preserved": len(all_content_points) - deleted_count,
        }

    # Helper methods

    def _generate_content_id(
        self, file_path: str, commit: str, chunk_index: int = 0
    ) -> str:
        """Generate deterministic content ID."""
        content_str = f"{file_path}:{commit}:{chunk_index}"
        # Use UUID5 for deterministic UUIDs that Qdrant accepts
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
        return str(uuid.uuid5(namespace, content_str))

    def _content_exists(self, content_id: str, collection_name: str) -> bool:
        """Check if content point already exists."""
        try:
            point = self.qdrant_client.get_point(content_id, collection_name)
            return point is not None
        except Exception:
            return False

    def _get_file_commit(self, file_path: str) -> str:
        """Get current commit hash for file."""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", file_path],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            commit = result.stdout.strip() if result.returncode == 0 else ""
            # If no commit found, use "unknown"
            return commit if commit else "unknown"
        except Exception:
            return "unknown"

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        suffix = Path(file_path).suffix.lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".sh": "shell",
            ".bash": "shell",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".dart": "dart",
            ".vue": "vue",
            ".jsx": "javascript",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".txt": "text",
        }
        return language_map.get(suffix, "unknown")

    def _get_embedding_dimensions(self) -> int:
        """Get the embedding dimensions from the provider."""
        # For Ollama nomic-embed-text, it's typically 768
        # For other providers, we could query the model info
        model_info = self.embedding_provider.get_model_info()
        return int(model_info.get("dimensions", 768))

    def _get_visibility_points(
        self, branch: str, file_path: str, collection_name: str
    ) -> List[Dict[str, Any]]:
        """Get visibility points for file in branch."""
        points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": branch}},
                    {"key": "path", "match": {"value": file_path}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            collection_name=collection_name,
            limit=1000,
        )
        return list(points)

    def _get_visible_content_ids(self, branch: str, collection_name: str) -> Set[str]:
        """Get all content IDs visible from branch."""
        points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": branch}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            collection_name=collection_name,
            limit=10000,
        )

        return {point["payload"]["content_id"] for point in points}

    def _hide_file_in_branch(self, file_path: str, branch: str, collection_name: str):
        """Mark file as hidden in branch."""
        self.qdrant_client.batch_update_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": branch}},
                    {"key": "path", "match": {"value": file_path}},
                ]
            },
            payload_updates={"status": "hidden"},
            collection_name=collection_name,
        )

    def _determine_working_dir_status(self, file_path: str) -> str:
        """Determine working directory status for a file."""
        try:
            # Check if file is staged
            staged_result = subprocess.run(
                ["git", "diff", "--name-only", "--cached", "--", file_path],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if staged_result.returncode == 0 and staged_result.stdout.strip():
                return "staged"

            # Check if file has unstaged changes
            unstaged_result = subprocess.run(
                ["git", "diff", "--name-only", "--", file_path],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if unstaged_result.returncode == 0 and unstaged_result.stdout.strip():
                return "unstaged"

            # Check if file is untracked
            untracked_result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "--", file_path],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if untracked_result.returncode == 0 and untracked_result.stdout.strip():
                return "untracked"

            return "committed"

        except Exception:
            return "unknown"
