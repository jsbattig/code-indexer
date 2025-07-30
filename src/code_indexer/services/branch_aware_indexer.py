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
import os
import datetime
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
    """Metadata for content points with branch visibility tracking.

    CRITICAL FIELD NAMING DOCUMENTATION:

    git_commit: str - The commit hash or working directory identifier for this content.
                     This field stores either:
                     1. Git commit hash (40 chars) for committed content
                     2. "working_dir_{mtime}_{size}" for working directory changes

                     When stored in Qdrant payload, this becomes "git_commit_hash"
                     (see line ~798 where payload["git_commit_hash"] = commit)

                     DO NOT confuse with:
                     - git_hash: Used elsewhere for git blob hash (content hash)
                     - git_commit_hash: The payload field name in Qdrant database
    """

    path: str
    chunk_index: int
    total_chunks: int
    git_commit: str  # See detailed documentation above ^^^
    content_hash: str
    file_size: int
    language: str
    created_at: float
    working_directory_status: str
    file_mtime: float  # File modification time for reconcile comparisons
    hidden_branches: List[
        str
    ]  # Array of branches where this content is hidden (deleted)
    line_start: int  # Starting line number of the chunk
    line_end: int  # Ending line number of the chunk


# VisibilityMetadata class removed - now using hidden_branches array in content points


@dataclass
class BranchIndexingResult:
    """Result of branch-aware indexing operation."""

    content_points_created: int
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
        # Debug logging
        import os
        import datetime

        debug_file = os.path.expanduser("~/.tmp/cidx_debug.log")
        with open(debug_file, "a") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] BranchAwareIndexer.index_branch_changes started with {len(changed_files)} changed files\n"
            )
            f.flush()

        start_time = time.time()
        result = BranchIndexingResult(
            content_points_created=0,
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
                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] Calling _index_changed_files\n"
                    )
                    f.flush()

                content_result = self._index_changed_files(
                    changed_files,
                    new_branch,
                    collection_name,
                    progress_callback,
                    vector_thread_count,
                )

                with open(debug_file, "a") as f:
                    f.write(
                        f"[{datetime.datetime.now().isoformat()}] _index_changed_files completed\n"
                    )
                    f.flush()
                result.content_points_created += content_result.content_points_created
                result.files_processed += len(changed_files)

            # 2. Update visibility for unchanged files - no longer needed with hidden_branches approach
            if unchanged_files:
                # With hidden_branches approach, unchanged files don't need visibility updates
                # They remain visible in the new branch by default (not in hidden_branches list)
                result.content_points_reused += len(unchanged_files)

            # 3. Ensure proper branch isolation by hiding files that shouldn't be visible
            # Get all files that should be visible in the new branch
            all_visible_files = changed_files + unchanged_files
            self.hide_files_not_in_branch(
                new_branch, all_visible_files, collection_name
            )

            result.processing_time = time.time() - start_time

            logger.info(
                f"Branch indexing completed: {result.content_points_created} content points created, "
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
        """Create content points for changed files."""
        # Debug logging
        debug_file = os.path.expanduser("~/.tmp/cidx_debug.log")
        with open(debug_file, "a") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] _index_changed_files started with {len(file_paths)} files\n"
            )
            f.flush()
        result = BranchIndexingResult(
            content_points_created=0,
            content_points_reused=0,
            processing_time=0,
            files_processed=0,
        )
        batch_points = []

        # Determine thread count for vector calculation
        if vector_thread_count is None:
            vector_thread_count = get_default_thread_count(self.embedding_provider)

        # Progress tracking
        total_files = len(file_paths)
        current_file_index = 0

        # Use VectorCalculationManager for parallel embedding processing
        with open(debug_file, "a") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] Creating VectorCalculationManager with {vector_thread_count} threads\n"
            )
            f.flush()

        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:
            with open(debug_file, "a") as f:
                f.write(
                    f"[{datetime.datetime.now().isoformat()}] VectorCalculationManager created, starting file loop\n"
                )
                f.flush()

            for file_path in file_paths:
                try:
                    # Debug log each file
                    with open(debug_file, "a") as f:
                        f.write(
                            f"[{datetime.datetime.now().isoformat()}] Processing file {current_file_index+1}/{total_files}: {file_path}\n"
                        )
                        f.flush()

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
                        # Content exists - ensure it's visible in this branch (remove from hidden_branches if present)
                        self._ensure_file_visible_in_branch(
                            file_path, branch, collection_name
                        )
                        result.content_points_reused += 1

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
                                    throttle_icon = getattr(
                                        stats, "throttling_status", None
                                    )
                                    throttle_str = (
                                        f" {throttle_icon.value}"
                                        if throttle_icon
                                        else ""
                                    )
                                    emb_speed = f"{stats.embeddings_per_second:.1f} emb/s{throttle_str}"

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
                    with open(debug_file, "a") as f:
                        f.write(
                            f"[{datetime.datetime.now().isoformat()}] Starting to chunk file: {file_path}\n"
                        )
                        f.flush()

                    chunks = self.text_chunker.chunk_file(full_path)

                    with open(debug_file, "a") as f:
                        f.write(
                            f"[{datetime.datetime.now().isoformat()}] Finished chunking: {len(chunks) if chunks else 0} chunks\n"
                        )
                        f.flush()
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
                        # Prepare metadata including semantic data
                        chunk_metadata = {
                            "file_path": file_path,
                            "chunk_index": chunk_idx,
                            "semantic_chunking": chunk.get("semantic_chunking", False),
                        }

                        # Add semantic metadata if available
                        if chunk.get("semantic_chunking", False):
                            chunk_metadata.update(
                                {
                                    "semantic_type": chunk.get("semantic_type"),
                                    "semantic_name": chunk.get("semantic_name"),
                                    "semantic_path": chunk.get("semantic_path"),
                                    "semantic_signature": chunk.get(
                                        "semantic_signature"
                                    ),
                                    "semantic_parent": chunk.get("semantic_parent"),
                                    "semantic_context": chunk.get(
                                        "semantic_context", {}
                                    ),
                                    "semantic_scope": chunk.get("semantic_scope"),
                                    "semantic_language_features": chunk.get(
                                        "semantic_language_features", []
                                    ),
                                }
                            )

                        # Submit chunk for parallel processing (don't wait for result yet)
                        future = vector_manager.submit_chunk(
                            chunk["text"],
                            chunk_metadata,
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
                                vector_result.metadata,
                            )
                            batch_points.append(content_point)
                            result.content_points_created += 1

                            # No need for separate visibility points - using hidden_branches field instead

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
                                throttle_icon = getattr(
                                    stats, "throttling_status", None
                                )
                                throttle_str = (
                                    f" {throttle_icon.value}" if throttle_icon else ""
                                )
                                emb_speed = f"{stats.embeddings_per_second:.1f} emb/s{throttle_str}"

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

                    # CRITICAL: Maintain point-in-time snapshot behavior by hiding outdated content
                    if current_commit.startswith("working_dir_"):
                        # This is working directory content - hide the old committed version
                        try:
                            # Find and hide all content points for this file that are NOT working directory versions
                            content_points, _ = self.qdrant_client.scroll_points(
                                filter_conditions={
                                    "must": [
                                        {"key": "type", "match": {"value": "content"}},
                                        {"key": "path", "match": {"value": file_path}},
                                    ]
                                },
                                limit=1000,  # Should be enough for any file's chunks
                                collection_name=collection_name,
                            )

                            # Filter out working directory versions manually (Qdrant doesn't support startswith)
                            committed_content_points = [
                                point
                                for point in content_points
                                if not point.get("payload", {})
                                .get("git_commit", "")
                                .startswith("working_dir_")
                            ]

                            # Hide old committed content points by adding current branch to hidden_branches
                            points_to_update = []
                            for point in committed_content_points:
                                point_id = point["id"]
                                payload = point.get("payload", {})
                                hidden_branches = payload.get("hidden_branches", [])

                                if branch not in hidden_branches:
                                    new_hidden = hidden_branches + [branch]
                                    points_to_update.append(
                                        {
                                            "id": point_id,
                                            "payload": {"hidden_branches": new_hidden},
                                        }
                                    )

                            # Batch update the points
                            if points_to_update:
                                success = self.qdrant_client._batch_update_points(
                                    points_to_update,
                                    collection_name,
                                    "WORKING_DIR_HIDE_COMMITTED",
                                )
                                if success:
                                    logger.debug(
                                        f"Successfully hid {len(points_to_update)} committed content points for working directory file {file_path}"
                                    )
                                else:
                                    logger.warning(
                                        f"Failed to hide {len(points_to_update)} committed content points for file {file_path}"
                                    )

                        except Exception as e:
                            logger.warning(
                                f"Failed to hide old committed content for working directory file {file_path}: {e}"
                            )

                    else:
                        # This is committed content - hide any working directory versions for this file
                        try:
                            # Find and hide all working directory content points for this file
                            all_file_points, _ = self.qdrant_client.scroll_points(
                                filter_conditions={
                                    "must": [
                                        {"key": "type", "match": {"value": "content"}},
                                        {"key": "path", "match": {"value": file_path}},
                                    ]
                                },
                                limit=1000,  # Should be enough for any file's chunks
                                collection_name=collection_name,
                            )

                            # Filter for working directory versions manually
                            working_dir_points = [
                                point
                                for point in all_file_points
                                if point.get("payload", {})
                                .get("git_commit", "")
                                .startswith("working_dir_")
                            ]

                            # Hide working directory content points by adding current branch to hidden_branches
                            points_to_update = []
                            for point in working_dir_points:
                                point_id = point["id"]
                                payload = point.get("payload", {})
                                hidden_branches = payload.get("hidden_branches", [])

                                if branch not in hidden_branches:
                                    new_hidden = hidden_branches + [branch]
                                    points_to_update.append(
                                        {
                                            "id": point_id,
                                            "payload": {"hidden_branches": new_hidden},
                                        }
                                    )

                            # Batch update the points
                            if points_to_update:
                                success = self.qdrant_client._batch_update_points(
                                    points_to_update,
                                    collection_name,
                                    "COMMITTED_HIDE_WORKING_DIR",
                                )
                                if success:
                                    logger.debug(
                                        f"Successfully hid {len(points_to_update)} working directory points for committed file {file_path}"
                                    )
                                else:
                                    logger.warning(
                                        f"Failed to hide {len(points_to_update)} working directory points for file {file_path}"
                                    )

                        except Exception as e:
                            logger.warning(
                                f"Failed to hide working directory content for committed file {file_path}: {e}"
                            )

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

    # Note: _update_visibility_for_unchanged_files method removed
    # With hidden_branches approach, unchanged files don't need visibility updates

    def _create_content_point(
        self,
        file_path: str,
        chunk: Dict[str, Any],
        commit: str,
        embedding: List[float],
        branch: str,
        vector_metadata: Optional[Dict[str, Any]] = None,
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

        # Create content metadata with initial visibility state
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
            hidden_branches=[],  # Initially visible in all branches (empty = not hidden anywhere)
            line_start=chunk.get("line_start", 1),  # Default to line 1 if not available
            line_end=chunk.get("line_end", 1),  # Default to line 1 if not available
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
            # CRITICAL: git_commit field from ContentMetadata becomes git_commit_hash in payload
            # This is the KEY field for commit identification in queries and hiding logic
            # Other services expect "git_commit_hash" in payload, NOT "git_commit"
            "git_commit_hash": commit,  # Alias for ContentMetadata.git_commit field
            "content": content_text,  # Required for search results
            "indexed_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),  # ISO format for consistency
            # Project info (but NOT branch - that's in visibility points)
            "project_id": project_id,  # Project identifier
        }

        # Add semantic metadata if available
        if vector_metadata and vector_metadata.get("semantic_chunking", False):
            payload.update(
                {
                    "semantic_chunking": vector_metadata["semantic_chunking"],
                    "semantic_type": vector_metadata.get("semantic_type"),
                    "semantic_name": vector_metadata.get("semantic_name"),
                    "semantic_path": vector_metadata.get("semantic_path"),
                    "semantic_signature": vector_metadata.get("semantic_signature"),
                    "semantic_parent": vector_metadata.get("semantic_parent"),
                    "semantic_context": vector_metadata.get("semantic_context", {}),
                    "semantic_scope": vector_metadata.get("semantic_scope"),
                    "semantic_language_features": vector_metadata.get(
                        "semantic_language_features", []
                    ),
                }
            )
        else:
            payload["semantic_chunking"] = False

        # Get embedding model name for metadata
        embedding_model = self.embedding_provider.get_current_model()

        result = self.qdrant_client.create_point(
            point_id=content_id,
            vector=embedding,
            payload=payload,
            embedding_model=embedding_model,
        )
        return result if result is not None else {}

    def _ensure_file_visible_in_branch(
        self, file_path: str, branch: str, collection_name: str
    ):
        """Ensure file is visible in branch by removing branch from hidden_branches array if present."""
        # Get all content points for this file
        content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"value": file_path}},
                ]
            },
            limit=1000,  # Should be enough for any file's chunks
            collection_name=collection_name,
        )

        # Update each content point to remove branch from hidden_branches if present
        points_to_update = []
        for point in content_points:
            current_hidden = point.get("payload", {}).get("hidden_branches", [])
            if branch in current_hidden:
                # Remove branch from hidden_branches array
                new_hidden = [b for b in current_hidden if b != branch]
                points_to_update.append(
                    {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                )

        # Batch update the points with new hidden_branches arrays
        if points_to_update:
            return self.qdrant_client._batch_update_points(
                points_to_update, collection_name
            )

        return True  # No updates needed

    def search_with_branch_context(
        self,
        query_vector: List[float],
        branch: str,
        limit: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search content with branch visibility filtering using hidden_branches field.

        Content is visible in a branch unless the branch is in the hidden_branches array.
        """
        # Search content points with branch visibility filter built-in
        # Content is visible if current branch is NOT in hidden_branches array
        filter_conditions = {
            "must": [
                {"key": "type", "match": {"value": "content"}},
            ],
            "must_not": [
                # Exclude content where current branch is in hidden_branches array
                {"key": "hidden_branches", "match": {"any": [branch]}},
            ],
        }

        results = self.qdrant_client.search(
            query_vector=query_vector,
            filter_conditions=filter_conditions,
            limit=limit,
            collection_name=collection_name,
        )

        return results if results is not None else []

    def cleanup_branch(self, branch: str, collection_name: str) -> Dict[str, int]:
        """
        Clean up branch data by adding branch to hidden_branches of all content points.

        This marks all content as hidden in the specified branch.
        Content points are preserved for other branches.
        """
        logger.info(f"Cleaning up branch: {branch}")

        # Get all content points
        content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=10000,
        )

        # Add branch to hidden_branches for all content points
        points_to_update = []
        for point in content_points:
            current_hidden = point.get("payload", {}).get("hidden_branches", [])
            if branch not in current_hidden:
                new_hidden = current_hidden + [branch]
                points_to_update.append(
                    {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                )

        updated_count = 0
        if points_to_update:
            result = self.qdrant_client._batch_update_points(
                points_to_update, collection_name
            )
            updated_count = len(points_to_update) if result else 0

        logger.info(f"Hidden {updated_count} content points for branch {branch}")

        return {
            "content_points_hidden": updated_count,
            "content_points_preserved": len(content_points) - updated_count,
        }

    def garbage_collect_content(self, collection_name: str) -> Dict[str, int]:
        """
        Remove content points that are hidden in ALL branches (completely orphaned).

        This is a maintenance operation that can be run periodically.
        With hidden_branches approach, we can only delete content that is hidden in all existing branches.
        """
        logger.info("Starting content garbage collection")

        # Get all unique branches that exist in the system
        all_content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=10000,
        )

        if not all_content_points:
            logger.info("No content points found")
            return {"content_points_deleted": 0, "content_points_preserved": 0}

        # Collect all branches mentioned in hidden_branches
        all_branches = set()
        for point in all_content_points:
            hidden_branches = point.get("payload", {}).get("hidden_branches", [])
            all_branches.update(hidden_branches)

        logger.info(
            f"Found {len(all_branches)} branches in system: {sorted(all_branches)}"
        )

        # Find content points hidden in ALL branches (completely orphaned)
        orphaned_content_ids = []
        for point in all_content_points:
            hidden_branches = point.get("payload", {}).get("hidden_branches", [])
            # If content is hidden in all known branches, it's orphaned
            if all_branches and set(hidden_branches) >= all_branches:
                orphaned_content_ids.append(point["id"])

        # Delete orphaned content points
        if orphaned_content_ids:
            deleted_count = self.qdrant_client.delete_points(
                point_ids=orphaned_content_ids, collection_name=collection_name
            )
            logger.info(
                f"Garbage collected {deleted_count} completely orphaned content points"
            )
        else:
            deleted_count = 0
            logger.info("No completely orphaned content points found")

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
        """Get current commit hash for file, or working directory indicator if modified."""
        try:
            # Check if this is a git repository
            is_git_repo = self._is_git_repository()

            if not is_git_repo:
                # For non-git projects, always use timestamp-based IDs for consistency
                try:
                    file_path_obj = self.codebase_dir / file_path
                    file_stat = file_path_obj.stat()
                    return f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                except Exception:
                    # Fallback if stat fails
                    import time

                    return f"working_dir_{time.time()}_error"

            # For git repositories, use the original git-aware logic
            # Check if file differs from committed version
            if self._file_differs_from_committed_version(file_path):
                # File has working directory changes - generate unique ID based on mtime/size
                try:
                    file_path_obj = self.codebase_dir / file_path
                    file_stat = file_path_obj.stat()
                    return f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                except Exception:
                    # Fallback if stat fails
                    import time

                    return f"working_dir_{time.time()}_error"

            # File matches committed version - use commit hash
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

    def _file_differs_from_committed_version(self, file_path: str) -> bool:
        """Check if working directory file differs from committed version."""
        try:
            # Use git diff to check if file differs from HEAD
            result = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", file_path],
                cwd=self.codebase_dir,
                capture_output=True,
                timeout=10,
            )
            # git diff --quiet returns 0 if no differences, 1 if differences exist
            differs = result.returncode != 0
            if differs:
                logger.debug(
                    f"RECONCILE: File {file_path} differs from committed version (git diff returncode={result.returncode})"
                )
            return differs
        except Exception as e:
            # If git command fails, assume no differences
            logger.debug(f"RECONCILE: Git diff failed for {file_path}: {e}")
            return False

    def _is_git_repository(self) -> bool:
        """Check if the current directory is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.codebase_dir,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_effective_content_id_for_reconcile(self, file_path: str) -> str:
        """Get content ID that represents current working directory state."""
        # Check if this is a git repository
        is_git_repo = self._is_git_repository()

        if not is_git_repo:
            # For non-git projects, always use timestamp-based content IDs for consistency
            # Use the same format as _get_file_commit to ensure consistency
            try:
                file_stat = (self.codebase_dir / file_path).stat()
                commit = f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                return f"{file_path}:{commit}"
            except Exception:
                # Fallback if stat fails
                return f"{file_path}:working_dir_error"

        # For git repositories, use the original git-aware logic
        if self._file_differs_from_committed_version(file_path):
            # File has working directory changes - use mtime/size based ID
            try:
                file_stat = (self.codebase_dir / file_path).stat()
                commit = f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
                return f"{file_path}:{commit}"
            except Exception:
                # Fallback if stat fails
                return f"{file_path}:working_dir_error"
        else:
            # File matches committed version - use commit-based ID
            commit = self._get_file_commit(file_path)
            return f"{file_path}:{commit}"

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
            ".kts": "kotlin",
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

    def _get_content_points_for_file(
        self, file_path: str, collection_name: str
    ) -> List[Dict[str, Any]]:
        """Get content points for file."""
        points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"value": file_path}},
                ]
            },
            collection_name=collection_name,
            limit=1000,
        )
        return list(points)

    def _get_visible_content_ids(self, branch: str, collection_name: str) -> Set[str]:
        """Get all content IDs visible from branch using hidden_branches filter."""
        points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}],
                "must_not": [
                    # Content is visible if current branch is NOT in hidden_branches
                    {"key": "hidden_branches", "match": {"any": [branch]}},
                ],
            },
            collection_name=collection_name,
            limit=10000,
        )

        return {point["id"] for point in points}

    def _hide_file_in_branch(self, file_path: str, branch: str, collection_name: str):
        """Mark file as hidden in branch by adding branch to hidden_branches array."""
        # Get all content points for this file
        content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"value": file_path}},
                ]
            },
            limit=1000,  # Should be enough for any file's chunks
            collection_name=collection_name,
        )

        # Update each content point to add branch to hidden_branches if not already present
        points_to_update = []
        for point in content_points:
            current_hidden = point.get("payload", {}).get("hidden_branches", [])
            if branch not in current_hidden:
                # Add branch to hidden_branches array
                new_hidden = current_hidden + [branch]
                points_to_update.append(
                    {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                )

        # Batch update the points with new hidden_branches arrays
        if points_to_update:
            return self.qdrant_client._batch_update_points(
                points_to_update, collection_name
            )

        return True  # No updates needed

        # Note: No fallback needed with hidden_branches approach
        # If no content points exist for the file, that's expected for deleted files

    def _unhide_file_in_branch(self, file_path: str, branch: str, collection_name: str):
        """Mark file as visible in branch by removing branch from hidden_branches array."""
        # Get all content points for this file
        content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"value": file_path}},
                ]
            },
            limit=1000,  # Should be enough for any file's chunks
            collection_name=collection_name,
        )

        # Update each content point to remove branch from hidden_branches if present
        points_to_update = []
        for point in content_points:
            current_hidden = point.get("payload", {}).get("hidden_branches", [])
            if branch in current_hidden:
                # Remove branch from hidden_branches array
                new_hidden = [b for b in current_hidden if b != branch]
                points_to_update.append(
                    {"id": point["id"], "payload": {"hidden_branches": new_hidden}}
                )

        # Batch update the points with new hidden_branches arrays
        if points_to_update:
            return self.qdrant_client._batch_update_points(
                points_to_update, collection_name
            )

        return True  # No updates needed

    def hide_files_not_in_branch(
        self,
        branch: str,
        current_files: List[str],
        collection_name: str,
        progress_callback: Optional[Callable] = None,
    ):
        """Hide all files that exist in the database but not in the current branch's file list.

        This is essential for proper branch isolation during full indexing.

        Args:
            branch: Current branch name
            current_files: List of files that exist in the current branch
            collection_name: Qdrant collection name
            progress_callback: Optional callback for progress reporting
        """
        # Phase 1: Scanning database
        if progress_callback:
            progress_callback(
                0, 0, Path(""), info="🔍 Scanning database for branch isolation..."
            )

        # Get all unique file paths from content points in the database
        all_content_points, _ = self.qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            limit=10000,  # Should be enough for most codebases
            collection_name=collection_name,
        )

        # Phase 2: Building file mappings
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"📊 Analyzing {len(all_content_points)} chunks across files...",
            )

        # Build comprehensive mapping of files to point IDs and their hidden_branches
        file_to_point_info: Dict[str, List[Dict[str, Any]]] = (
            {}
        )  # file_path -> list of {id, hidden_branches}

        for point in all_content_points:
            file_path = point.get("payload", {}).get("path")
            point_id = point.get("id")
            if file_path and point_id:  # Only process if we have both path and id
                if file_path not in file_to_point_info:
                    file_to_point_info[file_path] = []
                file_to_point_info[file_path].append(
                    {
                        "id": point_id,
                        "hidden_branches": point.get("payload", {}).get(
                            "hidden_branches", []
                        ),
                    }
                )

        # Phase 3: Calculate what needs updating
        current_files_set = set(current_files)
        db_files = set(file_to_point_info.keys())
        files_to_hide = db_files - current_files_set

        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🔧 Preparing branch isolation: {len(files_to_hide)} files to hide, checking {len(current_files_set)} for visibility...",
            )

        # Collect ALL updates in memory to batch them
        all_updates = []

        # Process files that need to be hidden
        for file_path in files_to_hide:
            for point_info in file_to_point_info.get(file_path, []):
                if branch not in point_info["hidden_branches"]:
                    # Add branch to hidden_branches array
                    new_hidden = point_info["hidden_branches"] + [branch]
                    all_updates.append(
                        {
                            "id": point_info["id"],
                            "payload": {"hidden_branches": new_hidden},
                        }
                    )

        # Process files that should be visible (only if they're currently hidden)
        # CRITICAL: Preserve point-in-time snapshot behavior - don't unhide committed content
        # when working directory content exists for the same file
        for file_path in current_files_set:
            if file_path in file_to_point_info:  # File exists in DB
                # Check if this file has working directory content
                has_working_dir_content = any(
                    point.get("payload", {})
                    .get("git_commit", "")
                    .startswith("working_dir_")
                    for point in all_content_points
                    if point.get("payload", {}).get("path") == file_path
                )

                for point_info in file_to_point_info[file_path]:
                    if branch in point_info["hidden_branches"]:
                        # Get the actual point to check if it's committed content
                        point_git_commit = None
                        for point in all_content_points:
                            if point.get("id") == point_info["id"]:
                                point_git_commit = point.get("payload", {}).get(
                                    "git_commit", ""
                                )
                                break

                        # POINT-IN-TIME SNAPSHOT LOGIC:
                        # If this is committed content and working directory content exists,
                        # don't unhide it (preserve the snapshot behavior)
                        is_committed_content = (
                            point_git_commit
                            and not point_git_commit.startswith("working_dir_")
                        )
                        if is_committed_content and has_working_dir_content:
                            # Skip unhiding - preserve point-in-time snapshot
                            continue

                        # Remove branch from hidden_branches array
                        new_hidden = [
                            b for b in point_info["hidden_branches"] if b != branch
                        ]
                        all_updates.append(
                            {
                                "id": point_info["id"],
                                "payload": {"hidden_branches": new_hidden},
                            }
                        )

        # Phase 4: Apply updates in batches
        if all_updates:
            logger.info(
                f"Branch isolation: applying {len(all_updates)} updates for branch {branch}"
            )

            total_updates = len(all_updates)
            chunk_size = 1000

            for i in range(0, total_updates, chunk_size):
                chunk = all_updates[i : i + chunk_size]
                self.qdrant_client._batch_update_points(chunk, collection_name)

                if progress_callback:
                    completed = min(i + chunk_size, total_updates)
                    progress_callback(
                        completed,
                        total_updates,
                        Path(""),
                        info=f"🔄 Applying branch isolation: {completed}/{total_updates} updates",
                    )
        else:
            logger.info(f"No branch isolation updates needed for branch {branch}")
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info="✅ Branch isolation complete - no updates needed",
                )

        return True

    def _hide_file_in_branch_with_verification(
        self, file_path: str, branch: str, collection_name: str
    ) -> bool:
        """Mark file as hidden in branch with persistence verification for watch mode reliability."""
        import time

        logger.info(
            f"🔧 WATCH MODE: Attempting to hide file {file_path} in branch {branch}"
        )

        # Perform the hiding operation
        self._hide_file_in_branch(file_path, branch, collection_name)

        # Verify the hiding was successful with retries for eventual consistency
        # DEADLOCK FIX: Reduced from 10 retries to prevent 5+ minute hangs
        max_retries = 3  # Reduced from 10 to 3 for faster deletion processing
        retry_delay = 0.2  # Reduced from 1.0s to 0.2s to prevent long delays

        for attempt in range(max_retries):
            # Small delay to allow for persistence
            if attempt > 0:
                time.sleep(retry_delay)

            # Check if the file is properly hidden
            if self._verify_file_hidden(file_path, branch, collection_name):
                logger.info(
                    f"Successfully hidden file {file_path} in branch {branch} (attempt {attempt + 1})"
                )
                return True

            logger.warning(
                f"File {file_path} still visible after hiding attempt {attempt + 1}"
            )

        # If we get here, hiding failed after all retries
        logger.error(
            f"Failed to hide file {file_path} in branch {branch} after {max_retries} attempts"
        )
        return False

    def _verify_file_hidden(
        self, file_path: str, branch: str, collection_name: str
    ) -> bool:
        """Verify that a file is properly hidden by checking hidden_branches field."""
        try:
            # Get all content points for this file
            content_points, _ = self.qdrant_client.scroll_points(
                filter_conditions={
                    "must": [
                        {"key": "type", "match": {"value": "content"}},
                        {"key": "path", "match": {"value": file_path}},
                    ]
                },
                limit=1000,
                collection_name=collection_name,
            )

            # Check if all content points have the branch in their hidden_branches array
            for content_point in content_points:
                hidden_branches = content_point.get("payload", {}).get(
                    "hidden_branches", []
                )
                if branch not in hidden_branches:
                    # File is still visible in this branch - hiding failed
                    return False

            # All content points are properly hidden in this branch
            return True

        except Exception as e:
            logger.error(f"Error verifying file visibility for {file_path}: {e}")
            return False

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
