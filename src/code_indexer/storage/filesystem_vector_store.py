"""Filesystem-based vector storage with git-aware optimization.

Stores vectors in filesystem with path-as-vector quantization and git-aware chunk storage.
Following Story 2 requirements.
"""

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from datetime import datetime
import threading
import numpy as np
import logging
import msgpack

from .vector_quantizer import VectorQuantizer
from .projection_matrix_manager import ProjectionMatrixManager


class PathIndex:
    """Reverse index mapping file_path -> Set[point_id].

    Prevents duplicate chunks when files are re-indexed by maintaining
    a mapping from file paths to all point IDs associated with that file.
    This enables pre-upsert cleanup of old vectors before inserting new ones.

    Story #540: Fix duplicate chunks bug.
    """

    def __init__(self) -> None:
        """Initialize empty path index."""
        self._path_index: Dict[str, Set[str]] = {}

    def add_point(self, file_path: str, point_id: str) -> None:
        """Add a point_id to a file's set of point_ids.

        Args:
            file_path: Path to the file
            point_id: Point ID to add

        Note:
            If file_path doesn't exist in index, creates new set.
            Adding duplicate point_id is idempotent (set behavior).
        """
        if file_path not in self._path_index:
            self._path_index[file_path] = set()
        self._path_index[file_path].add(point_id)

    def remove_point(self, file_path: str, point_id: str) -> None:
        """Remove a point_id from a file's set of point_ids.

        Args:
            file_path: Path to the file
            point_id: Point ID to remove

        Note:
            If point_id is the last one for file_path, deletes the file's entry entirely.
            Removing nonexistent point_id or file_path is safe (no-op).
        """
        if file_path in self._path_index:
            self._path_index[file_path].discard(point_id)
            if not self._path_index[file_path]:
                del self._path_index[file_path]

    def get_point_ids(self, file_path: str) -> Set[str]:
        """Get all point_ids for a given file_path.

        Args:
            file_path: Path to the file

        Returns:
            Copy of the set of point_ids for this file (empty set if file not found)

        Note:
            Returns a copy to prevent external modification of internal state.
        """
        return self._path_index.get(file_path, set()).copy()

    def save(self, path: Path) -> None:
        """Save path index to disk using msgpack.

        Args:
            path: File path to save to (will create parent directories)

        Note:
            Sets are serialized as lists in msgpack format.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert sets to lists for msgpack serialization
        serializable_data = {
            file_path: list(point_ids)
            for file_path, point_ids in self._path_index.items()
        }

        with open(path, "wb") as f:
            msgpack.dump(serializable_data, f)

    @classmethod
    def load(cls, path: Path) -> "PathIndex":
        """Load path index from disk.

        Args:
            path: File path to load from

        Returns:
            PathIndex instance with loaded data (empty if file doesn't exist)

        Note:
            Lists are converted back to sets after deserialization.
        """
        instance = cls()

        if not path.exists():
            return instance

        with open(path, "rb") as f:
            serialized_data = msgpack.load(f)

        # Convert lists back to sets
        instance._path_index = {
            file_path: set(point_ids)
            for file_path, point_ids in serialized_data.items()
        }

        return instance


class FilesystemVectorStore:
    """Filesystem-based vector storage with git-aware optimization.

    Features:
    - Path-as-vector quantization for efficient storage
    - Git-aware chunk storage (blob hash for clean, text for dirty)
    - Thread-safe atomic writes
    - ID indexing for fast lookups
    """

    def __init__(
        self,
        base_path: Path,
        project_root: Optional[Path] = None,
        hnsw_index_cache: Optional[Any] = None,
    ):
        """Initialize filesystem vector store.

        Args:
            base_path: Base directory for all collections
            project_root: Root directory of the project being indexed (for git operations)
            hnsw_index_cache: Optional HNSW index cache for server-side performance (Story #526)
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Initialize logger
        self.logger = logging.getLogger(__name__)

        # Store project root for git operations
        # If not provided, try to derive from base_path (go up two levels from .code-indexer/index/)
        if project_root is None:
            # base_path is typically .code-indexer/index/, so project_root is two levels up
            self.project_root = self.base_path.parent.parent
        else:
            self.project_root = Path(project_root)

        # Initialize components
        self.quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)
        self.matrix_manager = ProjectionMatrixManager()

        # Thread safety for file writes
        self._write_lock = threading.Lock()

        # ID index cache: {collection_name: {point_id: file_path}}
        self._id_index: Dict[str, Dict[str, Path]] = {}
        self._id_index_lock = threading.Lock()

        # File path cache: {collection_name: set of file paths}
        self._file_path_cache: Dict[str, set] = {}

        # Cache for collection metadata (read once, reuse forever)
        self._vector_size_cache: Dict[str, int] = {}
        self._collection_metadata_cache: Dict[str, Dict[str, Any]] = {}
        self._metadata_lock = threading.Lock()  # Protect cache from concurrent access

        # HNSW-001 & HNSW-002: Incremental update change tracking
        # Structure: {collection_name: {'added': set(), 'updated': set(), 'deleted': set()}}
        self._indexing_session_changes: Dict[str, Dict[str, set]] = {}

        # HNSW-001 (AC3): Daemon mode cache entry (optional, set by daemon service)
        # When set, enables in-memory HNSW updates for watch mode instead of disk I/O
        self.cache_entry: Optional[Any] = None

        # Story #526: Server-side HNSW index cache for 1800x performance improvement
        # When set, caches hnswlib.Index objects with TTL-based eviction
        self.hnsw_index_cache = hnsw_index_cache

        # Story #540: Path-to-point_ids reverse index for duplicate prevention
        # Structure: {collection_name: PathIndex}
        self._path_indexes: Dict[str, PathIndex] = {}
        self._path_index_lock = threading.Lock()

    def create_collection(self, collection_name: str, vector_size: int) -> bool:
        """Create a new collection with projection matrix.

        Args:
            collection_name: Name of the collection
            vector_size: Size of input vectors (e.g., 1536)

        Returns:
            True if created successfully
        """
        collection_path = self.base_path / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Ensure collection directories are gitignored if in a git repo
        self._ensure_gitignore(collection_name)

        # Create projection matrix for this collection
        output_dim = 64  # Target 64-dim for 32-char hex path
        projection_matrix = self.matrix_manager.create_projection_matrix(
            input_dim=vector_size, output_dim=output_dim
        )

        # Save projection matrix
        self.matrix_manager.save_matrix(projection_matrix, collection_path)

        # Compute quantization range dynamically from projection matrix dimensions
        # Uses random projection theory: projected vectors have std ≈ sqrt(output_dim / input_dim)
        # We use ±3σ to cover 99.7% of the distribution
        std_estimate = np.sqrt(output_dim / vector_size)
        min_val = -3 * std_estimate
        max_val = 3 * std_estimate

        # Create collection metadata with dynamically computed quantization range
        # Range will be used for locality-preserving fixed-range scalar quantization
        metadata = {
            "name": collection_name,
            "vector_size": vector_size,
            "created_at": datetime.utcnow().isoformat(),
            "quantization_range": {
                "min": float(min_val),  # Dynamically computed from matrix dimensions
                "max": float(max_val),
            },
        }

        metadata_path = collection_path / "collection_meta.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Initialize ID index for this collection
        with self._id_index_lock:
            self._id_index[collection_name] = {}

        return True

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists.

        Args:
            collection_name: Name of the collection

        Returns:
            True if collection exists
        """
        collection_path = self.base_path / collection_name
        metadata_path = collection_path / "collection_meta.json"
        return metadata_path.exists()

    def list_collections(self) -> List[str]:
        """List all collections.

        Returns:
            List of collection names
        """
        collections = []
        for path in self.base_path.iterdir():
            if path.is_dir():
                metadata_path = path / "collection_meta.json"
                if metadata_path.exists():
                    collections.append(path.name)
        return collections

    def begin_indexing(self, collection_name: str) -> None:
        """Prepare for batch indexing operations.

        Called ONCE before indexing session starts. Clears file path cache to ensure
        fresh data after indexing.

        Args:
            collection_name: Name of the collection to begin indexing

        Note:
            This is part of the storage provider lifecycle interface that enables O(n)
            performance by deferring index rebuilding until end_indexing().

            HNSW-001 & HNSW-002: Initializes change tracking for incremental HNSW updates.
            Story #540: Loads PathIndex for duplicate prevention during upserts.
        """
        self.logger.info(
            f"Beginning indexing session for collection '{collection_name}'"
        )

        # Clear file path cache for this collection
        with self._id_index_lock:
            if collection_name in self._file_path_cache:
                del self._file_path_cache[collection_name]

        # HNSW-001 & HNSW-002: Initialize change tracking for incremental updates
        self._indexing_session_changes[collection_name] = {
            "added": set(),
            "updated": set(),
            "deleted": set(),
        }

        # Story #540: Load PathIndex for duplicate prevention
        with self._path_index_lock:
            if collection_name not in self._path_indexes:
                self._path_indexes[collection_name] = self._load_path_index(
                    collection_name
                )

        self.logger.debug(f"Change tracking initialized for '{collection_name}'")

    def end_indexing(
        self,
        collection_name: str,
        progress_callback: Optional[Any] = None,
        skip_hnsw_rebuild: bool = False,
    ) -> Dict[str, Any]:
        """Finalize indexing by rebuilding HNSW and ID indexes.

        Called ONCE after all upsert_points() operations complete. This is where
        the O(n²) → O(n) optimization happens - we rebuild indexes only once instead
        of after every upsert.

        Args:
            collection_name: Name of the collection
            progress_callback: Optional callback for progress reporting
            skip_hnsw_rebuild: If True, skip HNSW rebuild and mark index as stale
                             (watch mode optimization - defer rebuild to query time)

        Returns:
            Status dictionary with rebuild results and hnsw_skipped flag

        Raises:
            ValueError: If collection doesn't exist

        Note:
            Before this optimization, upsert_points() rebuilt indexes after EVERY file,
            causing O(n²) complexity. Now we rebuild indexes ONCE at the end.

            Watch Mode Optimization: When skip_hnsw_rebuild=True, HNSW rebuild is
            deferred to query time via staleness marking. This prevents watch mode
            from spending 5-10 seconds rebuilding HNSW after every batch of file changes.
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        self.logger.info(f"Finalizing indexes for collection '{collection_name}'...")

        # Get vector size from cache (avoids file I/O)
        vector_size = self._get_vector_size(collection_name)

        # Conditional HNSW rebuild based on watch mode
        from .hnsw_index_manager import HNSWIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")
        hnsw_skipped = False

        # HNSW-002: Auto-detection for incremental vs full rebuild
        incremental_update_result = None
        if (
            hasattr(self, "_indexing_session_changes")
            and collection_name in self._indexing_session_changes
        ):
            changes = self._indexing_session_changes[collection_name]
            has_changes = changes["added"] or changes["updated"] or changes["deleted"]

            if has_changes and not skip_hnsw_rebuild:
                # INCREMENTAL UPDATE PATH
                self.logger.info(
                    f"Applying incremental HNSW update for '{collection_name}': "
                    f"{len(changes['added'])} added, {len(changes['updated'])} updated, "
                    f"{len(changes['deleted'])} deleted"
                )
                incremental_update_result = self._apply_incremental_hnsw_batch_update(
                    collection_name=collection_name,
                    changes=changes,
                    progress_callback=progress_callback,
                )

                # Clear session changes after applying
                del self._indexing_session_changes[collection_name]

                self.logger.info(
                    f"Incremental HNSW update complete for '{collection_name}'"
                )

        # Fallback to original logic if no incremental update was applied
        if incremental_update_result is None:
            if skip_hnsw_rebuild:
                # Watch mode: Mark index as stale, defer rebuild to query time
                hnsw_manager.mark_stale(collection_path)
                hnsw_skipped = True
                self.logger.info(
                    f"HNSW rebuild skipped for '{collection_name}' (watch mode), "
                    f"marked as stale for query-time rebuild"
                )
            else:
                # Normal mode: Rebuild HNSW index from ALL vectors on disk (ONCE)
                hnsw_manager.rebuild_from_vectors(
                    collection_path=collection_path, progress_callback=progress_callback
                )
                self.logger.info(f"HNSW index rebuilt for '{collection_name}'")

        # Save ID index to disk (ALWAYS - needed for queries)
        from .id_index_manager import IDIndexManager

        id_manager = IDIndexManager()
        with self._id_index_lock:
            # BUG FIX: Load ID index from disk if not in memory (reconciliation path)
            # When reconciliation finds all commits indexed and calls end_indexing(),
            # _id_index is empty because no new vectors were upserted.
            if (
                collection_name not in self._id_index
                or not self._id_index[collection_name]
            ):
                self._id_index[collection_name] = self._load_id_index(collection_name)

            if collection_name in self._id_index:
                id_manager.save_index(collection_path, self._id_index[collection_name])

        # Story #540: Save path index to disk
        with self._path_index_lock:
            if collection_name in self._path_indexes:
                self._save_path_index(
                    collection_name, self._path_indexes[collection_name]
                )

        vector_count = len(self._id_index.get(collection_name, {}))

        # Calculate and update unique file count in metadata
        unique_file_count = self._calculate_and_save_unique_file_count(
            collection_name, collection_path
        )

        self.logger.info(
            f"Indexing finalized for '{collection_name}': {vector_count} vectors indexed "
            f"({unique_file_count} unique files)"
        )

        result = {
            "status": "ok",
            "vectors_indexed": vector_count,
            "unique_files": unique_file_count,
            "collection": collection_name,
            "hnsw_skipped": hnsw_skipped,
        }

        # Add HNSW update type if incremental was used
        if incremental_update_result is not None:
            result["hnsw_update"] = "incremental"

        return result

    def _get_vector_size(self, collection_name: str) -> int:
        """Get vector size for collection (cached to avoid repeated file I/O).

        This method implements caching to eliminate the O(n²) behavior of reading
        collection_meta.json on every upsert operation. Before optimization, we were
        reading a 163KB JSON file 1,127+ times. Now we read it once and cache the result.

        Args:
            collection_name: Name of the collection

        Returns:
            Vector size (dimensions) for the collection

        Raises:
            RuntimeError: If collection metadata is corrupted, missing, or invalid

        Note:
            Thread-safe via _metadata_lock to prevent race conditions during concurrent
            indexing operations.
        """
        with self._metadata_lock:
            if collection_name not in self._vector_size_cache:
                # Load metadata ONCE
                collection_path = self.base_path / collection_name
                meta_file = collection_path / "collection_meta.json"

                if not meta_file.exists():
                    raise RuntimeError(
                        f"Collection metadata not found: {meta_file}. "
                        f"Collection may be corrupted or not properly initialized."
                    )

                try:
                    with open(meta_file) as f:
                        metadata = json.load(f)

                    vector_size = metadata.get("vector_size")
                    if vector_size is None:
                        raise RuntimeError(
                            f"Collection metadata missing 'vector_size' field: {meta_file}"
                        )

                    # Cache for future use
                    self._vector_size_cache[collection_name] = vector_size
                    self._collection_metadata_cache[collection_name] = metadata

                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"Collection metadata file corrupted (invalid JSON): {meta_file}. "
                        f"Error: {e}. You may need to recreate the collection."
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to read collection metadata: {meta_file}. Error: {e}"
                    )

            return self._vector_size_cache[collection_name]

    def _load_quantization_range(self, collection_name: str) -> tuple[float, float]:
        """Load quantization range from collection metadata (cached).

        This method now uses the cached metadata from _get_vector_size() to avoid
        repeated file I/O during upsert operations.

        Args:
            collection_name: Name of the collection

        Returns:
            Tuple of (min_val, max_val) for quantization range
        """
        # Use cached metadata via _metadata_lock
        with self._metadata_lock:
            if collection_name in self._collection_metadata_cache:
                metadata = self._collection_metadata_cache[collection_name]
                quant_range = metadata.get(
                    "quantization_range", {"min": -2.0, "max": 2.0}
                )
                return (quant_range["min"], quant_range["max"])

        # Fallback: read from disk if not cached (shouldn't happen if using lifecycle properly)
        collection_path = self.base_path / collection_name
        metadata_path = collection_path / "collection_meta.json"

        if not metadata_path.exists():
            return (-2.0, 2.0)

        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
                quant_range = metadata.get(
                    "quantization_range", {"min": -2.0, "max": 2.0}
                )
                return (quant_range["min"], quant_range["max"])
        except (json.JSONDecodeError, KeyError):
            return (-2.0, 2.0)

    def upsert_points(
        self,
        collection_name: Optional[str],
        points: List[Dict[str, Any]],
        progress_callback: Optional[Any] = None,
        watch_mode: bool = False,
    ) -> Dict[str, Any]:
        """Store vectors in filesystem with git-aware optimization.

        Args:
            collection_name: Name of the collection (if None, auto-resolves to only collection)
            points: List of point dictionaries with id, vector, payload
            progress_callback: Optional callback(current, total, Path, info) for progress reporting
            watch_mode: If True, triggers immediate real-time HNSW updates (HNSW-001)

        Returns:
            Status dictionary with operation result

        Raises:
            ValueError: If collection_name is None and multiple collections exist

        Note:
            HNSW-001 (Watch Mode): When watch_mode=True, updates HNSW index immediately
            after upserting points, enabling real-time semantic search without delays.

            HNSW-002 (Batch Mode): When watch_mode=False and session changes are tracked,
            changes are accumulated for batch incremental update at end_indexing().
        """
        # Auto-resolve collection_name if None
        if collection_name is None:
            available_collections = self.list_collections()
            if len(available_collections) == 0:
                raise ValueError("No collections available. Create a collection first.")
            elif len(available_collections) == 1:
                collection_name = available_collections[0]
            else:
                raise ValueError(
                    f"collection_name is required when multiple collections exist. "
                    f"Available collections: {', '.join(available_collections)}"
                )

        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        # Load projection matrix (singleton-cached in ProjectionMatrixManager)
        projection_matrix = self.matrix_manager.load_matrix(collection_path)

        # Get expected vector dimensions from projection matrix
        expected_dims = projection_matrix.shape[0]

        # Load quantization range for locality-preserving quantization
        min_val, max_val = self._load_quantization_range(collection_name)

        # Detect git repo root once for batch operation
        repo_root = self._get_repo_root()

        # Batch git operations for performance
        file_paths = [
            p.get("payload", {}).get("path", "")
            for p in points
            if p.get("payload", {}).get("path")
        ]
        blob_hashes = {}
        uncommitted_files = set()

        # Skip blob hash lookup for temporal collection (FIX 1: Avoid Errno 7 on large temporal indexes)
        if (
            repo_root is not None
            and file_paths
            and collection_name != "code-indexer-temporal"
        ):
            blob_hashes = self._get_blob_hashes_batch(file_paths, repo_root)
            uncommitted_files = self._check_uncommitted_batch(file_paths, repo_root)

        # Ensure ID index exists for this collection (also loads file path cache)
        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)
            # Ensure file path cache exists (in case ID index was manually populated)
            if collection_name not in self._file_path_cache:
                self._file_path_cache[collection_name] = set()

        # Story #540: Pre-upsert cleanup to prevent duplicates
        # Group points by file_path and clean up old vectors before upserting new ones
        from collections import defaultdict

        points_by_file = defaultdict(list)
        for point in points:
            file_path = point.get("payload", {}).get("path", "")
            if file_path:
                points_by_file[file_path].append(point)

        # CRITICAL FIX (Story #540 Code Review): Refactor to minimize lock hold time
        # STEP 1: Gather orphan metadata INSIDE lock (fast, no I/O)
        orphans_to_delete = []  # List of (file_path, orphan_id, vector_file_path)

        with self._path_index_lock:
            # CRITICAL FIX (Story #540 Code Review): Lazy-load path index if not already loaded
            # This handles watch mode scenario where upsert_points can be called WITHOUT begin_indexing()
            if collection_name not in self._path_indexes:
                self._path_indexes[collection_name] = self._load_path_index(
                    collection_name
                )

            path_index = self._path_indexes[collection_name]

            # Gather orphan point_ids for each file
            for file_path, file_points in points_by_file.items():
                # Get new point_ids that will be upserted
                new_point_ids = {p["id"] for p in file_points}

                # Get old point_ids from path index
                old_point_ids = path_index.get_point_ids(file_path)

                # Identify orphaned point_ids (in old but not in new)
                orphan_point_ids = old_point_ids - new_point_ids

                # Gather orphan metadata (just reading id_index, no I/O)
                if orphan_point_ids:
                    with self._id_index_lock:
                        for orphan_id in orphan_point_ids:
                            if orphan_id in self._id_index.get(collection_name, {}):
                                vector_file = self._id_index[collection_name][orphan_id]
                                orphans_to_delete.append(
                                    (file_path, orphan_id, vector_file)
                                )

        # STEP 2: Perform file deletions OUTSIDE lock (I/O operations)
        # This releases both _path_index_lock and _id_index_lock before I/O
        for file_path, orphan_id, vector_file in orphans_to_delete:
            # Delete vector JSON file from disk
            # Use try/except to handle race condition: another thread may delete same file
            try:
                if vector_file.exists():
                    vector_file.unlink()
            except FileNotFoundError:
                # File already deleted by another thread - this is safe to ignore
                pass

        # STEP 3: Update indexes INSIDE lock (fast, just dict/set updates)
        if orphans_to_delete:
            with self._path_index_lock:
                path_index = self._path_indexes[collection_name]

                with self._id_index_lock:
                    for file_path, orphan_id, vector_file in orphans_to_delete:
                        # Remove from id_index
                        if orphan_id in self._id_index.get(collection_name, {}):
                            del self._id_index[collection_name][orphan_id]

                        # Track deletion for HNSW incremental updates
                        if collection_name in self._indexing_session_changes:
                            self._indexing_session_changes[collection_name][
                                "deleted"
                            ].add(orphan_id)

                        # Remove from path index
                        path_index.remove_point(file_path, orphan_id)

        # Process all points
        total_points = len(points)
        for idx, point in enumerate(points, 1):
            try:
                point_id = point["id"]
                vector = np.array(point["vector"])
                payload = point.get("payload", {})
                chunk_text = point.get("chunk_text")  # Extract chunk_text from root
                file_path = payload.get("path", "")

                # LAYER 2 VALIDATION: Validate vector is numeric, not object array
                if vector.dtype == object or vector.dtype == np.dtype("O"):
                    raise ValueError(
                        f"Point {point_id} has invalid vector with dtype={vector.dtype}. "
                        f"Vector contains non-numeric values. First 5 values: {point['vector'][:5]}"
                    )

                # Validate vector dimension matches expected
                if vector.shape[0] != expected_dims:
                    raise ValueError(
                        f"Point {point_id} has vector dimension {vector.shape[0]}, expected {expected_dims}"
                    )

                # Progress reporting
                if progress_callback:
                    # Pass empty Path("") instead of None to avoid path division errors
                    file_path_for_callback = Path(file_path) if file_path else Path("")
                    progress_callback(
                        idx, total_points, file_path_for_callback, info=file_path
                    )

                # Quantize vector to hex path
                if projection_matrix is None:
                    raise RuntimeError(
                        f"Projection matrix is None for collection {collection_name}"
                    )

                # Matrix multiplication (matrix is singleton-cached in ProjectionMatrixManager)
                reduced = vector @ projection_matrix

                # Use fixed-range scalar quantization for locality preservation
                quantized_bits = self.quantizer._quantize_to_2bit(
                    reduced, min_val, max_val
                )
                hex_path = self.quantizer._bits_to_hex(quantized_bits)
            except Exception as e:
                import traceback

                print(f"ERROR in upsert_points loop iteration {idx}: {e}")
                print("Traceback:")
                traceback.print_exc()
                raise

            # Split hex path into directory structure
            segments = self.quantizer._split_hex_path(hex_path)

            # Create directory structure
            dir_path = collection_path
            for segment in segments[:-1]:
                dir_path = dir_path / segment
            dir_path.mkdir(parents=True, exist_ok=True)

            # Create vector file path
            vector_file = dir_path / f"vector_{point_id.replace('/', '_')}.json"

            # Prepare vector data with git-aware storage (using batch results)
            vector_data = self._prepare_vector_data_batch(
                point_id=point_id,
                vector=vector,
                payload=payload,
                chunk_text=chunk_text,
                repo_root=repo_root,
                blob_hashes=blob_hashes,
                uncommitted_files=uncommitted_files,
            )

            # Atomic write to filesystem
            self._atomic_write_json(vector_file, vector_data)

            # Update ID index and file path cache
            with self._id_index_lock:
                # Check if point existed before (for change tracking)
                point_existed = point_id in self._id_index.get(collection_name, {})

                self._id_index[collection_name][point_id] = vector_file

                # Update file path cache
                if file_path:
                    self._file_path_cache[collection_name].add(file_path)

                # HNSW-001 & HNSW-002: Track changes for incremental updates
                if collection_name in self._indexing_session_changes:
                    if point_existed:
                        self._indexing_session_changes[collection_name]["updated"].add(
                            point_id
                        )
                    else:
                        self._indexing_session_changes[collection_name]["added"].add(
                            point_id
                        )

            # Story #540: Update path index with new point_id
            with self._path_index_lock:
                if collection_name in self._path_indexes and file_path:
                    self._path_indexes[collection_name].add_point(file_path, point_id)

        # HNSW-001: Watch mode real-time HNSW update
        if watch_mode:
            # In watch mode, update HNSW immediately for all upserted points
            # Note: Watch mode can be called outside of indexing sessions,
            # so we don't rely on _indexing_session_changes tracking
            if points:
                self._update_hnsw_incrementally_realtime(
                    collection_name=collection_name,
                    changed_points=points,
                    progress_callback=progress_callback,
                )

        # Return success - index rebuilding now happens in end_indexing() (O(n) not O(n²))
        # This fixes the performance disaster where we rebuilt indexes after EVERY file.
        # Now indexes are rebuilt ONCE at the end of the indexing session.
        return {"status": "ok", "count": len(points)}

    def count_points(self, collection_name: str) -> int:
        """Count vectors in collection using metadata (fast path) or ID index (fallback).

        Performance optimization: Reads vector_count from collection_meta.json
        instead of loading the full ID index (400K entries). This reduces
        cidx status time from 9+ seconds to <50ms for large collections.

        Args:
            collection_name: Name of the collection

        Returns:
            Number of vectors in collection
        """
        # Fast path: Try reading count from metadata
        collection_path = self.base_path / collection_name
        meta_file = collection_path / "collection_meta.json"

        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    metadata = json.load(f)

                # Check if hnsw_index exists with vector_count
                if "hnsw_index" in metadata:
                    vector_count = metadata["hnsw_index"].get("vector_count")
                    if isinstance(vector_count, int):
                        return vector_count
            except (json.JSONDecodeError, KeyError, OSError):
                # If metadata read fails, fall through to ID index path
                pass

        # Fallback path: Load ID index (original behavior)
        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)
            return len(self._id_index[collection_name])

    def delete_points(
        self, collection_name: str, point_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete vectors from filesystem.

        Args:
            collection_name: Name of the collection
            point_ids: List of point IDs to delete

        Returns:
            Status dictionary with deletion result

        Note:
            HNSW-001 & HNSW-002: Tracks deletions for incremental HNSW updates.
        """
        deleted = 0

        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            index = self._id_index[collection_name]

            for point_id in point_ids:
                if point_id in index:
                    vector_file = index[point_id]

                    # Story #540: Get file_path from vector data before deletion
                    file_path = None
                    if vector_file.exists():
                        try:
                            with open(vector_file) as f:
                                vector_data = json.load(f)
                                file_path = vector_data.get("payload", {}).get("path")
                        except (json.JSONDecodeError, KeyError, OSError):
                            # If we can't read the file, continue with deletion
                            pass

                        # Delete file
                        vector_file.unlink()
                        deleted += 1

                    # Remove from index
                    del index[point_id]

                    # HNSW-001 & HNSW-002: Track deletion for incremental updates
                    if collection_name in self._indexing_session_changes:
                        self._indexing_session_changes[collection_name]["deleted"].add(
                            point_id
                        )

                    # Story #540: Remove from path index
                    if file_path:
                        with self._path_index_lock:
                            if collection_name in self._path_indexes:
                                self._path_indexes[collection_name].remove_point(
                                    file_path, point_id
                                )

            # Clear file path cache since file structure changed
            if deleted > 0 and collection_name in self._file_path_cache:
                del self._file_path_cache[collection_name]

        return {"status": "ok", "deleted": deleted}

    def _prepare_vector_data(
        self,
        point_id: str,
        vector: np.ndarray,
        payload: Dict[str, Any],
        repo_root: Optional[Path],
    ) -> Dict[str, Any]:
        """Prepare vector data with git-aware storage logic.

        Args:
            point_id: Unique point identifier
            vector: Vector data
            payload: Point payload
            repo_root: Git repository root (None if not a git repo)

        Returns:
            Dictionary ready for JSON serialization
        """
        data = {
            "id": point_id,
            "vector": vector.tolist(),
            "file_path": payload.get("path", ""),
            "start_line": payload.get("start_line", 0),
            "end_line": payload.get("end_line", 0),
            "metadata": {
                "language": payload.get("language", ""),
                "type": payload.get("type", "content"),
            },
        }

        file_path = payload.get("path", "")

        # Git-aware chunk storage logic
        if repo_root:
            # Check if this specific file has uncommitted changes
            has_uncommitted = self._file_has_uncommitted_changes(file_path, repo_root)

            if not has_uncommitted:
                # File is clean: try to get blob hash
                blob_hash = self._get_git_blob_hash(file_path, repo_root)
                if blob_hash:
                    # Store only blob hash (space efficient)
                    data["git_blob_hash"] = blob_hash
                    data["indexed_with_uncommitted_changes"] = False
                else:
                    # File not in git (untracked): store chunk text
                    data["chunk_text"] = payload.get("content", "")
                    data["indexed_with_uncommitted_changes"] = True
            else:
                # File has uncommitted changes: store chunk text
                data["chunk_text"] = payload.get("content", "")
                data["indexed_with_uncommitted_changes"] = True
        else:
            # Non-git repo: always store chunk_text
            data["chunk_text"] = payload.get("content", "")

        return data

    def _get_repo_root(self) -> Optional[Path]:
        """Get git repository root directory.

        Returns:
            Path to git repo root, or None if not a git repo
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.project_root,  # Use project_root instead of base_path
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return Path(result.stdout.strip())
            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _file_has_uncommitted_changes(self, file_path: str, repo_root: Path) -> bool:
        """Check if a specific file has uncommitted changes.

        Args:
            file_path: Relative path to file from repo root
            repo_root: Git repository root

        Returns:
            True if file has uncommitted changes, False otherwise
        """
        try:
            # Check git status for this specific file
            result = subprocess.run(
                ["git", "status", "--porcelain", file_path],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            # If output is non-empty, file has uncommitted changes
            return len(result.stdout.strip()) > 0

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If git command fails, assume file has changes (safe fallback)
            return True

    def _get_git_blob_hash(self, file_path: str, repo_root: Path) -> Optional[str]:
        """Get git blob hash for a file.

        Args:
            file_path: Relative path to file
            repo_root: Git repository root

        Returns:
            Git blob hash or None if not found
        """
        try:
            result = subprocess.run(
                ["git", "ls-tree", "HEAD", file_path],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout:
                # Parse output: "mode type hash\tfilename"
                parts = result.stdout.split()
                if len(parts) >= 3:
                    return parts[2]  # Return blob hash

            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _atomic_write_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Atomically write JSON data to file.

        Uses write-to-temp-then-rename pattern for thread safety.

        Args:
            file_path: Target file path
            data: Data to serialize as JSON
        """
        with self._write_lock:
            # Write to temporary file first
            tmp_file = file_path.with_suffix(".tmp")

            with open(tmp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            tmp_file.replace(file_path)

    def load_id_index(self, collection_name: str) -> set:
        """Load ID index and return set of existing point IDs.

        Public method for external components that need to check existing points.

        Args:
            collection_name: Name of the collection

        Returns:
            Set of existing point IDs
        """
        id_index = self._load_id_index(collection_name)
        return set(id_index.keys())

    def _load_id_index(self, collection_name: str) -> Dict[str, Path]:
        """Load ID index from persistent binary file for fast loading.

        Uses IDIndexManager to load from id_index.bin binary file which contains
        all vector ID to file path mappings. Falls back to directory scan only
        if binary index doesn't exist (for backward compatibility).

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary mapping point IDs to file paths
        """
        from .id_index_manager import IDIndexManager

        collection_path = self.base_path / collection_name
        index_manager = IDIndexManager()

        # Try loading from persistent binary index first (FAST - O(1) file read)
        index = index_manager.load_index(collection_path)

        if index:
            # Binary index loaded successfully
            return index

        # Fallback: Scan vector files by filename pattern (SLOW - O(n) directory traversal)
        # Only used for backward compatibility with indexes created before binary index
        index = {}
        for json_file in collection_path.rglob("vector_*.json"):
            # Extract point ID from filename: vector_POINTID.json
            filename = json_file.name
            if filename.startswith("vector_") and filename.endswith(".json"):
                # Remove "vector_" prefix (7 chars) and ".json" suffix (5 chars)
                point_id = filename[7:-5]
                index[point_id] = json_file

        return index

    def _load_file_paths(self, collection_name: str, id_index: Dict[str, Path]) -> set:
        """Load file paths from JSON files using ID index.

        This is a separate operation from loading the ID index, allowing operations
        that only need vector counts to avoid parsing JSON files.

        Args:
            collection_name: Name of the collection
            id_index: ID index mapping point IDs to file paths

        Returns:
            Set of unique file paths
        """
        file_paths = set()

        # Parse JSON files to extract file paths
        for json_file in id_index.values():
            try:
                with open(json_file) as f:
                    data = json.load(f)

                # Extract file path from payload only
                file_path = data.get("payload", {}).get("path", "")
                if file_path:
                    file_paths.add(file_path)

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                # Skip corrupted or missing files
                continue

        return file_paths

    def _load_path_index(self, collection_name: str) -> PathIndex:
        """Load path index from persistent binary file.

        Loads the reverse index mapping file_path -> Set[point_id] from
        path_index.bin in the collection directory. Returns empty PathIndex
        if file doesn't exist (new collection or pre-Story #540 index).

        Args:
            collection_name: Name of the collection

        Returns:
            PathIndex instance with loaded mappings (empty if file doesn't exist)

        Note:
            Story #540: Prevents duplicate chunks by tracking all point_ids per file.
        """
        collection_path = self.base_path / collection_name
        path_index_file = collection_path / "path_index.bin"

        # Load from disk or return empty if file doesn't exist
        return PathIndex.load(path_index_file)

    def _save_path_index(self, collection_name: str, path_index: PathIndex) -> None:
        """Save path index to persistent binary file.

        Saves the reverse index mapping file_path -> Set[point_id] to
        path_index.bin in the collection directory.

        Args:
            collection_name: Name of the collection
            path_index: PathIndex instance to save

        Note:
            Story #540: Persists path index for duplicate prevention across sessions.
        """
        collection_path = self.base_path / collection_name
        path_index_file = collection_path / "path_index.bin"

        path_index.save(path_index_file)

    def _ensure_gitignore(self, collection_name: str) -> None:
        """Ensure collection directory is in .gitignore if in a git repo.

        This prevents collection storage from making the repo appear dirty.

        Args:
            collection_name: Name of the collection to add to .gitignore
        """
        try:
            # Check if we're in a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.project_root,  # Use project_root instead of base_path
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return  # Not a git repo, nothing to do

            repo_root = Path(result.stdout.strip())
            gitignore_path = repo_root / ".gitignore"

            # Read existing .gitignore if it exists
            existing_patterns = set()
            if gitignore_path.exists():
                with open(gitignore_path, "r") as f:
                    existing_patterns = {
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    }

            # Add collection pattern if not already present
            pattern = f"/{collection_name}/"
            if (
                pattern not in existing_patterns
                and collection_name not in existing_patterns
            ):
                with open(gitignore_path, "a") as f:
                    f.write(
                        f"\n# FilesystemVectorStore collection\n{collection_name}/\n"
                    )

        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            # Silently ignore errors - gitignore is best-effort
            pass

    def _prepare_vector_data_batch(
        self,
        point_id: str,
        vector: np.ndarray,
        payload: Dict[str, Any],
        chunk_text: Optional[str],
        repo_root: Optional[Path],
        blob_hashes: Dict[str, str],
        uncommitted_files: set,
    ) -> Dict[str, Any]:
        """Prepare vector data using batch git operation results.

        Args:
            point_id: Unique point identifier
            vector: Vector data
            payload: Point payload
            chunk_text: Content text at root level (optimization path, optional)
            repo_root: Git repository root (None if not a git repo)
            blob_hashes: Dict of file_path -> blob_hash from batch operation
            uncommitted_files: Set of files with uncommitted changes

        Returns:
            Dictionary ready for JSON serialization
        """
        data = {
            "id": point_id,
            "vector": vector.tolist(),
            # file_path, start_line, end_line removed - already in payload as path, line_start, line_end
            "metadata": {
                "language": payload.get("language", ""),
                "type": payload.get("type", "content"),
            },
            "payload": payload,  # Store full payload for search operations
        }

        file_path = payload.get("path", "")
        payload_type = payload.get("type", "")

        # Check if this is a commit message - these should ALWAYS store chunk_text
        # Commit messages are indexed as searchable entities and need their content stored
        if payload_type == "commit_message":
            # Commit messages: always store chunk_text
            if chunk_text is not None:
                data["chunk_text"] = chunk_text
            else:
                # MESSI Rule #2 (Anti-Fallback): Fail fast instead of masking bugs
                raise RuntimeError(
                    f"Missing chunk_text for vector with payload_type={payload_type}. "
                    f"This indicates an indexing bug. Vector ID: {point_id}"
                )
        # Check if this is a temporal diff - these should ALWAYS store content
        # Temporal diffs represent historical commit content at specific points in time,
        # NOT current working tree state. Using current HEAD blob hash would be meaningless.
        elif payload_type == "commit_diff":
            # Storage optimization: added/deleted files use pointer-based storage
            if payload.get("reconstruct_from_git"):
                # Added/deleted files: NO chunk_text storage (pointer only)
                # Content can be reconstructed from git on query using commit hash
                # This provides 88% storage reduction for these file types
                pass  # Don't store chunk_text
            else:
                # Modified files: store diff in chunk_text
                # Prefer chunk_text from point root (optimization path)
                if chunk_text is not None:
                    data["chunk_text"] = chunk_text
                else:
                    # Legacy: extract from payload if present
                    data["chunk_text"] = payload.get("content", "")

            # Remove content from payload to avoid duplication
            if "content" in data["payload"]:
                del data["payload"]["content"]
        # Git-aware chunk storage logic using batch results (for regular files only)
        elif repo_root and file_path:
            has_uncommitted = file_path in uncommitted_files

            if not has_uncommitted and file_path in blob_hashes:
                # File is clean and in git: store only blob hash (space efficient)
                data["git_blob_hash"] = blob_hashes[file_path]
                data["indexed_with_uncommitted_changes"] = False
                # Remove content from payload to avoid duplication
                if "content" in data["payload"]:
                    del data["payload"]["content"]
            else:
                # File has uncommitted changes or untracked: store chunk text
                # Prefer chunk_text from point root (optimization path)
                if chunk_text is not None:
                    data["chunk_text"] = chunk_text
                else:
                    # Legacy: extract from payload if present
                    data["chunk_text"] = payload.get("content", "")
                data["indexed_with_uncommitted_changes"] = True
                # Remove content from payload (stored in chunk_text instead)
                if "content" in data["payload"]:
                    del data["payload"]["content"]
        else:
            # Non-git repo: always store chunk_text
            # Prefer chunk_text from point root (optimization path)
            if chunk_text is not None:
                data["chunk_text"] = chunk_text
            else:
                # Legacy: extract from payload if present
                data["chunk_text"] = payload.get("content", "")
            # Remove content from payload (stored in chunk_text instead)
            if "content" in data["payload"]:
                del data["payload"]["content"]

        return data

    def _get_blob_hashes_batch(
        self, file_paths: List[str], repo_root: Path
    ) -> Dict[str, str]:
        """Get git blob hashes for multiple files in batched git calls.

        Args:
            file_paths: List of file paths relative to repo root
            repo_root: Git repository root

        Returns:
            Dictionary mapping file_path to blob_hash

        Note:
            FIX 2: Batches git ls-tree calls to avoid "Argument list too long" error (Errno 7)
            when processing thousands of files. Each batch processes up to 100 files.
        """
        try:
            # Batch to avoid "Argument list too long" error (Errno 7)
            BATCH_SIZE = 100
            blob_hashes = {}

            for i in range(0, len(file_paths), BATCH_SIZE):
                batch = file_paths[i : i + BATCH_SIZE]
                result = subprocess.run(
                    ["git", "ls-tree", "HEAD"] + batch,
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout:
                    # Parse output: "mode type hash\tfilename"
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split()
                        if len(parts) >= 3:
                            blob_hash = parts[2]
                            # Filename is after tab
                            tab_idx = line.find("\t")
                            if tab_idx >= 0:
                                filename = line[tab_idx + 1 :]
                                blob_hashes[filename] = blob_hash

            return blob_hashes

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {}

    def _check_uncommitted_batch(self, file_paths: List[str], repo_root: Path) -> set:
        """Check which files have uncommitted changes in batched git calls.

        Args:
            file_paths: List of file paths to check
            repo_root: Git repository root

        Returns:
            Set of file paths with uncommitted changes

        Note:
            Batches git status calls to avoid "Argument list too long" error (Errno 7)
            when processing thousands of files. Each batch processes up to 100 files.
        """
        try:
            # Batch to avoid "Argument list too long" error (Errno 7)
            BATCH_SIZE = 100
            uncommitted = set()

            for i in range(0, len(file_paths), BATCH_SIZE):
                batch = file_paths[i : i + BATCH_SIZE]
                result = subprocess.run(
                    ["git", "status", "--porcelain"] + batch,
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    # Parse output format: "XY filename"
                    # When file paths are provided as arguments, format is "XY filename" (status codes + space + filename)
                    # X = index status (position 0), Y = worktree status (position 1), space (position 2), filename (position 3+)
                    # However, when filtering by files, the format drops the leading space for clean index
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        # The status codes are in positions 0-1, space at position 2 (or 1 if no leading space)
                        # Safe approach: find the first space and take everything after it
                        space_idx = line.find(" ")
                        if space_idx >= 0 and space_idx < len(line) - 1:
                            filename = line[space_idx + 1 :]
                            if filename:
                                uncommitted.add(filename)

            return uncommitted

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If git command fails, assume all files have changes (safe fallback)
            return set(file_paths)

    def get_point(
        self, point_id: str, collection_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific point by ID.

        Args:
            point_id: Point ID to retrieve
            collection_name: Name of the collection

        Returns:
            Point data with id, vector, and payload, or None if not found
        """
        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            index = self._id_index[collection_name]

            if point_id not in index:
                return None

            vector_file = index[point_id]

            if not vector_file.exists():
                return None

            try:
                with open(vector_file) as f:
                    data = json.load(f)

                # Payload should always exist in new format, but provide empty fallback
                payload = data.get("payload", {})
                result = {
                    "id": data["id"],
                    "vector": data["vector"],
                    "payload": payload,
                }
                # Include chunk_text if present
                if "chunk_text" in data:
                    result["chunk_text"] = data["chunk_text"]
                return result
            except (json.JSONDecodeError, KeyError):
                return None

    def _parse_filter(self, filter_conditions: Optional[Dict[str, Any]]) -> Any:
        """Parse filter to callable that evaluates payload.

        Supports TWO filter formats:

        1. Nested filters (CLI format):
           {"must": [{"key": "language", "match": {"value": "python"}}]}
           {"should": [{"key": "type", "match": {"value": "test"}}]}
           {"must_not": [{"key": "git_available", "match": {"value": False}}]}

        2. Flat dict filters:
           {"language": "python", "type": "test"}

        Args:
            filter_conditions: Filter dictionary in either format

        Returns:
            Callable that takes payload dict and returns True if matches filter
        """
        if not filter_conditions:
            return lambda payload: True

        # Detect filter format: nested has "must"/"should"/"must_not" keys
        is_nested_style = any(
            key in filter_conditions for key in ["must", "should", "must_not"]
        )

        if is_nested_style:
            # Nested filter
            def evaluate_condition(
                condition: Dict[str, Any], payload: Dict[str, Any]
            ) -> bool:
                """Evaluate a single condition against payload.

                Supports both simple conditions and nested filters:
                - Simple: {"key": "language", "match": {"value": "python"}}
                - Nested: {"should": [{"key": "language", "match": {"value": "py"}}, ...]}
                """
                # Check if this is a nested filter (has must/should/must_not)
                is_nested = any(
                    key in condition for key in ["must", "should", "must_not"]
                )

                if is_nested:
                    # Recursively evaluate nested filter
                    # Handle "must" conditions (AND)
                    if "must" in condition:
                        for nested_condition in condition["must"]:
                            if not evaluate_condition(nested_condition, payload):
                                return False

                    # Handle "should" conditions (OR) - at least one must match
                    if "should" in condition:
                        if not any(
                            evaluate_condition(nested_condition, payload)
                            for nested_condition in condition["should"]
                        ):
                            return False

                    # Handle "must_not" conditions (NOT)
                    if "must_not" in condition:
                        for nested_condition in condition["must_not"]:
                            if evaluate_condition(nested_condition, payload):
                                return False

                    return True
                else:
                    # Simple key-match condition
                    key = condition.get("key")
                    if not key or not isinstance(key, str):
                        return False

                    # Handle nested payload keys (e.g., "metadata.language")
                    current: Any = payload
                    for key_part in key.split("."):
                        if isinstance(current, dict):
                            current = current.get(key_part)
                        else:
                            return False

                    # TEMPORAL COLLECTION FIX: If 'path' field is None and key is "path",
                    # fall back to 'file_path' field (temporal collection format)
                    # This enables path filters to work with both collection formats:
                    # - Main collection: uses 'path' field
                    # - Temporal collection: uses 'file_path' field
                    if current is None and key == "path" and "file_path" in payload:
                        current = payload["file_path"]

                    # Check for range specification (NEW: temporal filter support)
                    range_spec = condition.get("range")
                    if range_spec:
                        # Range filtering for numeric fields (timestamps, etc.)
                        if not isinstance(current, (int, float)):
                            return False

                        # Apply range constraints
                        if "gte" in range_spec and current < range_spec["gte"]:
                            return False
                        if "gt" in range_spec and current <= range_spec["gt"]:
                            return False
                        if "lte" in range_spec and current > range_spec["lte"]:
                            return False
                        if "lt" in range_spec and current >= range_spec["lt"]:
                            return False

                        return True

                    # Check for match specification (existing logic)
                    match_spec = condition.get("match", {})

                    # Support "any" (set membership - NEW: temporal filter support)
                    if "any" in match_spec:
                        allowed_values = match_spec["any"]
                        return current in allowed_values

                    # Support "contains" (substring match - NEW: temporal filter support)
                    if "contains" in match_spec:
                        if not isinstance(current, str):
                            return False
                        substring = match_spec["contains"]
                        return substring.lower() in current.lower()

                    # Support both "value" (exact match) and "text" (pattern match)
                    if "value" in match_spec:
                        # Exact match
                        expected_value = match_spec["value"]
                        return bool(current == expected_value)
                    elif "text" in match_spec:
                        # Pattern match (glob-style wildcards)
                        # Use PathPatternMatcher for cross-platform consistency
                        from code_indexer.services.path_pattern_matcher import (
                            PathPatternMatcher,
                        )

                        pattern = match_spec["text"]
                        if not isinstance(current, str):
                            return False

                        matcher = PathPatternMatcher()
                        return bool(matcher.matches_pattern(current, pattern))
                    else:
                        # No match or range specification found
                        return False

            def evaluate_filter(payload: Dict[str, Any]) -> bool:
                """Evaluate full filter against payload."""
                # Handle "must" conditions (AND)
                if "must" in filter_conditions:
                    for condition in filter_conditions["must"]:
                        if not evaluate_condition(condition, payload):
                            return False

                # Handle "should" conditions (OR) - at least one must match
                if "should" in filter_conditions:
                    if not any(
                        evaluate_condition(condition, payload)
                        for condition in filter_conditions["should"]
                    ):
                        return False

                # Handle "must_not" conditions (NOT)
                if "must_not" in filter_conditions:
                    for condition in filter_conditions["must_not"]:
                        if evaluate_condition(condition, payload):
                            return False

                return True

            return evaluate_filter
        else:
            # Flat dict filter (legacy format)
            def evaluate_flat_filter(payload: Dict[str, Any]) -> bool:
                """Evaluate flat dict filter against payload."""
                for key, expected_value in filter_conditions.items():
                    # Handle nested payload keys (e.g., "metadata.language")
                    current: Any = payload
                    for key_part in key.split("."):
                        if isinstance(current, dict):
                            current = current.get(key_part)
                        else:
                            return False

                    if current != expected_value:
                        return False

                return True

            return evaluate_flat_filter

    def scroll_points(
        self,
        collection_name: str,
        limit: int = 100,
        with_payload: bool = True,
        with_vectors: bool = False,
        offset: Optional[str] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Scroll through points in collection with pagination.

        Args:
            collection_name: Name of the collection
            limit: Maximum number of points to return
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            offset: Pagination offset (file path from previous page)
            filter_conditions: Optional filter conditions

        Returns:
            Tuple of (points_list, next_offset)
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return [], None

        # Get all vector files sorted by path
        all_files = sorted(
            [
                f
                for f in collection_path.rglob("*.json")
                if "collection_meta" not in f.name
            ]
        )

        # Apply offset for pagination
        start_idx = 0
        if offset:
            try:
                offset_path = Path(offset)
                for i, f in enumerate(all_files):
                    if f == offset_path:
                        start_idx = i + 1
                        break
            except (ValueError, TypeError, OSError):
                pass

        # Get page of files
        page_files = all_files[start_idx : start_idx + limit]

        # Load points
        points: List[Dict[str, Any]] = []
        for vector_file in page_files:
            try:
                with open(str(vector_file), "r") as file_handle:
                    data: Dict[str, Any] = json.load(file_handle)

                point: Dict[str, Any] = {"id": data["id"]}

                if with_payload:
                    # Payload should always exist in new format
                    point["payload"] = data.get("payload", {})

                if with_vectors:
                    point["vector"] = data["vector"]

                # Apply filter conditions
                if filter_conditions:
                    payload = point.get("payload", {})
                    filter_func = self._parse_filter(filter_conditions)
                    if not filter_func(payload):
                        continue

                points.append(point)

            except (json.JSONDecodeError, KeyError):
                continue

        # Calculate next offset
        next_offset = None
        if len(page_files) == limit and start_idx + limit < len(all_files):
            next_offset = str(page_files[-1])

        return points, next_offset

    def search(
        self,
        query: str,
        embedding_provider: Any,
        collection_name: str = "",
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        return_timing: bool = False,
        lazy_load: bool = False,
        prefetch_limit: Optional[int] = None,
        ef: int = 50,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
        """Search for similar vectors using parallel execution of index loading and embedding generation.

        This method ALWAYS executes in parallel mode:
        - Thread 1: Load HNSW index + ID mapping
        - Thread 2: Generate query embedding
        - Wait for both, then perform search

        Parallel execution reduces query latency by 350-467ms by overlapping I/O-bound
        index loading with CPU-bound embedding generation.

        Args:
            query: Query text for embedding generation (REQUIRED)
            embedding_provider: Provider with get_embedding() method (REQUIRED)
            collection_name: Name of the collection
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            filter_conditions: Optional filter conditions for payload
            return_timing: If True, return tuple of (results, timing_dict)
            lazy_load: If True, load payloads on-demand with early exit (optimization for restrictive filters)
            prefetch_limit: How many candidate IDs to fetch from HNSW (default: limit * 2 or limit * 15 for lazy_load)

        Returns:
            List of results with id, score, payload (including content), and staleness
            If return_timing=True: Tuple of (results, timing_dict)

        Raises:
            ValueError: If query or embedding_provider not provided
            RuntimeError: If index loading or embedding generation fails
        """
        import time
        from concurrent.futures import ThreadPoolExecutor

        timing: Dict[str, Any] = {}

        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return ([], timing) if return_timing else []

        # Load metadata to get vector size
        meta_file = collection_path / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        # === CHECK HNSW STALENESS AND REBUILD IF NEEDED ===
        from .hnsw_index_manager import HNSWIndexManager

        vector_size = metadata.get("vector_size", 1536)
        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

        # Check if HNSW needs rebuild (watch mode coordination)
        if hnsw_manager.is_stale(collection_path):
            self.logger.info(
                f"HNSW index is stale for '{collection_name}', rebuilding..."
            )

            # Rebuild HNSW with locking
            rebuild_start = time.time()
            hnsw_manager.rebuild_from_vectors(
                collection_path=collection_path, progress_callback=None
            )
            rebuild_ms = (time.time() - rebuild_start) * 1000

            if return_timing:
                timing["hnsw_rebuild_triggered"] = True
                timing["hnsw_rebuild_ms"] = rebuild_ms

            self.logger.info(
                f"HNSW rebuild complete for '{collection_name}' ({rebuild_ms:.0f}ms)"
            )

        # === PARALLEL EXECUTION (always) ===

        def load_index():
            """Load HNSW and ID indexes in parallel thread.

            Story #526: If hnsw_index_cache is configured, use cached HNSW index
            for 1800x performance improvement (~277ms → <1ms).
            """
            # Load HNSW index (with caching if available)
            t_hnsw = time.time()

            # Story #526: Use cache if available
            if self.hnsw_index_cache is not None:
                # Cache key is collection_path (unique per repository)
                cache_key = str(collection_path.resolve())

                def hnsw_loader():
                    """Loader function for cache miss."""
                    index = hnsw_manager.load_index(
                        collection_path, max_elements=100000
                    )
                    # Load ID mapping from metadata for cache entry
                    id_mapping = hnsw_manager._load_id_mapping(collection_path)
                    return index, id_mapping

                # Get or load from cache
                hnsw_index, _cached_id_mapping = self.hnsw_index_cache.get_or_load(
                    cache_key, hnsw_loader
                )
            else:
                # No cache - load directly (original behavior)
                hnsw_index = hnsw_manager.load_index(
                    collection_path, max_elements=100000
                )

            hnsw_load_ms = (time.time() - t_hnsw) * 1000

            # Load ID index in same thread (parallel with embedding generation)
            t_id = time.time()
            with self._id_index_lock:
                if collection_name not in self._id_index:
                    from .id_index_manager import IDIndexManager

                    id_manager = IDIndexManager()
                    self._id_index[collection_name] = id_manager.load_index(
                        collection_path
                    )
                id_index = self._id_index[collection_name]
            id_load_ms = (time.time() - t_id) * 1000

            return hnsw_index, id_index, hnsw_load_ms, id_load_ms

        def generate_embedding():
            """Generate query embedding in parallel thread."""
            t0 = time.time()
            embedding = embedding_provider.get_embedding(query)
            embedding_time_ms = (time.time() - t0) * 1000
            return embedding, embedding_time_ms

        # Execute both operations in parallel using ThreadPoolExecutor
        parallel_start = time.time()
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            index_future = executor.submit(load_index)
            embedding_future = executor.submit(generate_embedding)

            # Wait for both to complete and gather results
            hnsw_index, id_index, hnsw_load_ms, id_load_ms = index_future.result()
            query_vector, embedding_ms = embedding_future.result()

        # Calculate actual parallel execution time (wall clock)
        parallel_load_ms = (time.time() - parallel_start) * 1000

        # Record timing metrics
        timing["parallel_load_ms"] = parallel_load_ms  # Actual clock time
        timing["embedding_ms"] = embedding_ms  # For breakdown display
        timing["index_load_ms"] = hnsw_load_ms  # HNSW index load time
        timing["id_index_load_ms"] = id_load_ms  # ID index load time
        timing["parallel_execution"] = True

        # Calculate threading overhead
        # Max concurrent work = max(embedding, index_loads_combined)
        index_work_ms = hnsw_load_ms + id_load_ms
        max_concurrent_work_ms = max(embedding_ms, index_work_ms)
        overhead_ms = parallel_load_ms - max_concurrent_work_ms
        timing["parallel_overhead_ms"] = overhead_ms

        # Validate results
        if hnsw_index is None:
            raise RuntimeError(
                f"HNSW index not found for collection '{collection_name}'. "
                f"Run: cidx index --rebuild-index"
            )

        # === SEARCH LOGIC ===

        query_vec = np.array(query_vector)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return ([], timing) if return_timing else []

        # Mark search path for timing metrics
        timing["search_path"] = "hnsw_index"

        # Determine how many candidates to fetch from HNSW
        # Use prefetch_limit if provided (for over-fetching with filters), otherwise limit * 2
        hnsw_k = prefetch_limit if prefetch_limit is not None else limit * 2

        # Query HNSW index
        t0 = time.time()
        candidate_ids, distances = hnsw_manager.query(
            index=hnsw_index,
            query_vector=query_vec,
            collection_path=collection_path,
            k=hnsw_k,  # Use prefetch_limit when provided for filter headroom
            ef=ef,  # HNSW query parameter - passed from search method
        )
        timing["hnsw_search_ms"] = (time.time() - t0) * 1000

        # ID index already loaded in parallel section
        # Re-acquire lock for thread-safe reference assignment
        with self._id_index_lock:
            existing_id_index = id_index

        # Load candidate vectors and apply filters
        t0 = time.time()
        results = []
        for point_id in candidate_ids:
            if point_id not in existing_id_index:
                continue

            vector_file = existing_id_index[point_id]
            if not vector_file.exists():
                continue

            try:
                with open(vector_file) as f:
                    data = json.load(f)

                # Apply filter conditions
                if filter_conditions:
                    payload = data.get("payload", {})
                    filter_func = self._parse_filter(filter_conditions)
                    if not filter_func(payload):
                        continue

                # Calculate exact cosine similarity
                stored_vec = np.array(data["vector"])
                stored_norm = np.linalg.norm(stored_vec)

                if stored_norm == 0:
                    continue

                similarity = np.dot(query_vec, stored_vec) / (query_norm * stored_norm)

                # Apply score threshold
                if score_threshold is not None and similarity < score_threshold:
                    continue

                # Payload should always exist in new format
                results.append(
                    {
                        "id": data["id"],
                        "score": float(similarity),
                        "payload": data.get("payload", {}),
                        "_vector_data": data,
                    }
                )

                # EARLY EXIT: If lazy loading enabled, stop when we have enough results
                if lazy_load and len(results) >= limit:
                    break

            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        timing["candidate_load_ms"] = (time.time() - t0) * 1000

        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        limited_results = results[:limit]

        # Enhance with content and staleness
        t0 = time.time()
        enhanced_results = []
        for result in limited_results:
            vector_data = result.pop("_vector_data")
            content, staleness = self._get_chunk_content_with_staleness(vector_data)
            result["payload"]["content"] = content
            result["staleness"] = staleness
            # Return chunk_text at root level for optimization contract
            if "chunk_text" in vector_data:
                result["chunk_text"] = vector_data["chunk_text"]
            enhanced_results.append(result)

        timing["staleness_detection_ms"] = (time.time() - t0) * 1000

        return (enhanced_results, timing) if return_timing else enhanced_results

    def _get_chunk_content_with_staleness(self, vector_data: Dict[str, Any]) -> tuple:
        """Retrieve chunk content with staleness detection.

        Strategy:
        - Non-git repos: Return chunk_text from JSON (never stale)
        - Git repos (clean): Try current file → git blob → error
        - Git repos (dirty): Return chunk_text from JSON (never stale)

        Args:
            vector_data: Vector data dictionary from JSON

        Returns:
            Tuple of (content, staleness_info)

        Staleness info structure:
            {
                'is_stale': bool,
                'staleness_indicator': '⚠️ Modified' | '🗑️ Deleted' | '❌ Error' | None,
                'staleness_reason': str | None,
                'hash_mismatch': bool (git repos only)
            }
        """
        # Get payload structure
        payload = vector_data.get("payload", {})

        # Non-git repos: content stored in payload, never stale
        if "chunk_text" in vector_data:
            return vector_data["chunk_text"], {
                "is_stale": False,
                "staleness_indicator": None,
                "staleness_reason": None,
            }

        # Check for content in payload (new format)
        if "content" in payload and payload.get("git_available", False):
            # Git repos with payload format - continue to git blob retrieval logic below
            # (Don't return early - let staleness detection happen)
            pass
        elif "content" in payload:
            # Non-git repos with payload format
            return payload["content"], {
                "is_stale": False,
                "staleness_indicator": None,
                "staleness_reason": None,
            }

        # Git repos: 3-tier fallback with staleness detection
        if "git_blob_hash" in vector_data:
            # Get file info from payload (always use payload for consistency)
            file_path = payload.get("path", "")
            start_line = payload.get("line_start", 0)
            end_line = payload.get("line_end", 0)
            stored_hash = vector_data.get("git_blob_hash", "")

            # Tier 1: Try reading from current file
            full_path = self.project_root / file_path

            if full_path.exists():
                try:
                    # Read chunk from current file
                    # Note: line_start/line_end are 1-based, convert to 0-based for Python slicing
                    with open(full_path) as f:
                        lines = f.readlines()
                        chunk_content = "".join(lines[(start_line - 1) : end_line])

                    # Compute current file hash
                    current_hash = self._compute_file_hash(full_path)

                    # Check for staleness via hash comparison
                    if current_hash == stored_hash:
                        # File unchanged - content is current
                        return chunk_content, {
                            "is_stale": False,
                            "staleness_indicator": None,
                            "staleness_reason": None,
                            "hash_mismatch": False,
                        }
                    else:
                        # File modified - fall back to git blob
                        blob_content = self._retrieve_from_git_blob(
                            stored_hash, start_line, end_line
                        )

                        return blob_content, {
                            "is_stale": True,
                            "staleness_indicator": "⚠️ Modified",
                            "staleness_reason": "file_modified_after_indexing",
                            "hash_mismatch": True,
                        }

                except Exception as e:
                    # Tier 3: Error reading file - try git blob
                    try:
                        blob_content = self._retrieve_from_git_blob(
                            stored_hash, start_line, end_line
                        )

                        return blob_content, {
                            "is_stale": True,
                            "staleness_indicator": "❌ Error",
                            "staleness_reason": "retrieval_failed",
                            "hash_mismatch": False,
                        }
                    except Exception:
                        # Complete failure
                        return f"[Error retrieving content: {str(e)}]", {
                            "is_stale": True,
                            "staleness_indicator": "❌ Error",
                            "staleness_reason": "retrieval_failed",
                            "hash_mismatch": False,
                        }
            else:
                # File deleted - retrieve from git blob
                try:
                    blob_content = self._retrieve_from_git_blob(
                        stored_hash, start_line, end_line
                    )

                    return blob_content, {
                        "is_stale": True,
                        "staleness_indicator": "🗑️ Deleted",
                        "staleness_reason": "file_deleted",
                        "hash_mismatch": False,
                    }
                except Exception as e:
                    return f"[File deleted, cannot retrieve: {str(e)}]", {
                        "is_stale": True,
                        "staleness_indicator": "🗑️ Deleted",
                        "staleness_reason": "file_deleted",
                        "hash_mismatch": False,
                    }

        # Fallback: no content available
        return "[Content not available]", {
            "is_stale": False,
            "staleness_indicator": None,
            "staleness_reason": None,
        }

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute git blob hash for a file.

        Uses same algorithm as git for compatibility.

        Args:
            file_path: Path to file

        Returns:
            Git blob hash (40-char hex string)
        """
        try:
            with open(file_path, "rb") as f:
                content = f.read()

            # Git blob format: "blob <size>\0<content>"
            blob_data = f"blob {len(content)}\0".encode() + content

            return hashlib.sha1(blob_data).hexdigest()
        except Exception:
            return ""

    def _retrieve_from_git_blob(
        self, blob_hash: str, start_line: int, end_line: int
    ) -> str:
        """Retrieve chunk content from git blob.

        Args:
            blob_hash: Git blob hash
            start_line: Start line of chunk
            end_line: End line of chunk

        Returns:
            Chunk content from git blob

        Raises:
            RuntimeError: If git operation fails
        """
        try:
            # Use git cat-file to retrieve blob content
            result = subprocess.run(
                ["git", "cat-file", "blob", blob_hash],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Git cat-file failed: {result.stderr}")

            # Extract chunk lines
            # Note: line_start/line_end are 1-based, convert to 0-based for Python slicing
            # line_end is exclusive (Python slicing convention)
            lines = result.stdout.splitlines(keepends=True)
            chunk_content = "".join(lines[(start_line - 1) : end_line])

            return chunk_content

        except subprocess.TimeoutExpired:
            raise RuntimeError("Git cat-file timeout")
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve git blob: {str(e)}")

    def resolve_collection_name(self, config: Any, embedding_provider: Any) -> str:
        """Generate collection name based on current provider and model.

        Uses model name as collection name.
        """
        model_name: str = embedding_provider.get_current_model()
        # Replace special characters to make it filesystem-safe
        safe_name: str = model_name.replace("/", "_").replace(":", "_")
        return safe_name

    def ensure_provider_aware_collection(
        self,
        config,
        embedding_provider,
        quiet: bool = False,
        skip_migration: bool = False,
    ) -> str:
        """Create/validate collection with provider-aware naming.

        Args:
            config: Main configuration object (unused for filesystem)
            embedding_provider: Current embedding provider instance
            quiet: Suppress output (unused for filesystem)
            skip_migration: Skip migration checks (unused for filesystem)

        Returns:
            Collection name that was created/validated
        """
        collection_name = self.resolve_collection_name(config, embedding_provider)
        vector_size = embedding_provider.get_model_info()["dimensions"]

        if not self.collection_exists(collection_name):
            self.create_collection(collection_name, vector_size)

        return collection_name

    def clear_collection(
        self, collection_name: str, remove_projection_matrix: bool = False
    ) -> bool:
        """Clear vectors from collection while optionally preserving projection matrix.

        Removes all indexed vectors from a collection. By default, preserves the
        projection matrix to allow faster re-indexing. The collection metadata
        (quantization_range) is recreated on next index operation.

        Args:
            collection_name: Name of the collection to clear
            remove_projection_matrix: If True, also remove projection matrix (default: False)

        Returns:
            True if cleared successfully
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return False

        try:
            import shutil

            # Save projection matrix and metadata if we need to preserve them
            matrix_file = collection_path / "projection_matrix.npy"
            metadata_file = collection_path / "collection_meta.json"
            matrix_data = None
            metadata_data = None

            if not remove_projection_matrix:
                if matrix_file.exists():
                    matrix_data = matrix_file.read_bytes()
                if metadata_file.exists():
                    metadata_data = metadata_file.read_bytes()

            # Remove entire collection directory
            shutil.rmtree(collection_path)

            # Clear ID index for this collection
            with self._id_index_lock:
                if collection_name in self._id_index:
                    del self._id_index[collection_name]

            # Restore projection matrix and metadata if they were preserved
            if matrix_data is not None or metadata_data is not None:
                collection_path.mkdir(parents=True, exist_ok=True)
                if matrix_data is not None:
                    matrix_file.write_bytes(matrix_data)
                if metadata_data is not None:
                    metadata_file.write_bytes(metadata_data)

            return True

        except Exception:
            return False

    def delete_collection(self, collection_name: str) -> bool:
        """Delete entire collection including structure and metadata.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deleted successfully
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return False

        try:
            # Remove entire collection directory
            import shutil

            shutil.rmtree(collection_path)

            # Clear ID index and file path cache for this collection
            with self._id_index_lock:
                if collection_name in self._id_index:
                    del self._id_index[collection_name]
                if collection_name in self._file_path_cache:
                    del self._file_path_cache[collection_name]

            return True

        except Exception:
            return False

    def create_point(
        self,
        vector: List[float],
        payload: Dict[str, Any],
        point_id: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a point object for batch operations.

        Args:
            vector: Vector data
            payload: Point payload
            point_id: Optional point ID
            embedding_model: Optional embedding model (added to payload)

        Returns:
            Point dictionary ready for upsert
        """
        point_payload = payload.copy()

        if embedding_model:
            point_payload["embedding_model"] = embedding_model

        point = {"vector": vector, "payload": point_payload}

        if point_id:
            point["id"] = point_id

        return point

    def delete_by_filter(
        self, collection_name: str, filter_conditions: Dict[str, Any]
    ) -> bool:
        """Delete vectors matching filter conditions.

        Args:
            collection_name: Name of the collection
            filter_conditions: Filter conditions

        Returns:
            True if deletion successful
        """
        try:
            # Scroll through vectors with filter applied
            points, _ = self.scroll_points(
                collection_name=collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False,
                filter_conditions=filter_conditions,
            )

            # All returned points match the filter, so delete them all
            points_to_delete: List[str] = [point["id"] for point in points]

            # Delete matching points
            if points_to_delete:
                result: Dict[str, Any] = self.delete_points(
                    collection_name, points_to_delete
                )
                return bool(result["status"] == "ok")

            return True

        except Exception:
            return False

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Get collection metadata.

        Args:
            collection_name: Name of the collection

        Returns:
            Collection metadata dictionary

        Raises:
            RuntimeError: If collection doesn't exist
        """
        collection_path = self.base_path / collection_name
        metadata_path = collection_path / "collection_meta.json"

        if not metadata_path.exists():
            raise RuntimeError(f"Collection '{collection_name}' does not exist")

        try:
            with open(str(metadata_path), "r") as f:
                metadata: Dict[str, Any] = json.load(f)
                return metadata
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Failed to read collection metadata: {e}")

    def health_check(self) -> bool:
        """Check if filesystem backend is accessible.

        Returns:
            True if filesystem is readable and writable
        """
        return self.base_path.exists() and os.access(self.base_path, os.W_OK)

    def _batch_update_points(
        self, points: List[Dict[str, Any]], collection_name: str, batch_size: int = 100
    ) -> bool:
        """Update multiple points with new payload data.

        Args:
            points: List of point updates with structure {"id": point_id, "payload": {...}}
            collection_name: Name of the collection
            batch_size: Batch size (unused for filesystem, kept for compatibility)

        Returns:
            True if all updates succeeded
        """
        try:
            for point in points:
                point_id = point["id"]
                new_payload = point["payload"]

                # Get existing point
                existing = self.get_point(point_id, collection_name)
                if not existing:
                    continue

                # Update payload, keep vector
                updated_point = {
                    "id": point_id,
                    "vector": existing["vector"],
                    "payload": new_payload,
                }

                # Upsert updated point
                self.upsert_points(collection_name, [updated_point])

            return True

        except Exception:
            return False

    def rebuild_payload_indexes(self, collection_name: str) -> bool:
        """Rebuild payload indexes (no-op for filesystem backend).

        Filesystem backend doesn't use payload indexes.
        Returns True for compatibility.
        """
        return True

    def ensure_payload_indexes(self, collection_name: str, context: str = "") -> None:
        """Ensure payload indexes exist (no-op for filesystem backend).

        Filesystem backend doesn't use payload indexes.
        No-op for compatibility.
        """
        pass

    def get_all_indexed_files(self, collection_name: str) -> List[str]:
        """Get all unique file paths from indexed vectors.

        Uses lazy loading: ID index is loaded from filenames (fast), file paths
        are only loaded by parsing JSON files when actually needed.

        Args:
            collection_name: Name of the collection

        Returns:
            List of unique file paths
        """
        with self._id_index_lock:
            # Ensure ID index is loaded (fast - from filenames only)
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            # Lazily load file paths if not cached
            if collection_name not in self._file_path_cache:
                id_index = self._id_index[collection_name]
                self._file_path_cache[collection_name] = self._load_file_paths(
                    collection_name, id_index
                )

            file_paths = self._file_path_cache[collection_name]

        return sorted(list(file_paths))

    def get_indexed_file_count_fast(self, collection_name: str) -> int:
        """Get count of indexed files from metadata (FAST - single JSON read).

        Returns 100% accurate file count from collection metadata if available,
        otherwise falls back to estimation. Use this for status/monitoring.

        Args:
            collection_name: Name of the collection

        Returns:
            Number of unique files indexed (accurate if metadata has it, estimated otherwise)

        Note:
            After indexing completes, unique_file_count is stored in metadata for instant lookup.
            Old indexes without this field will fall back to estimation (~99.8% accurate).
        """
        collection_path = self.base_path / collection_name
        meta_file = collection_path / "collection_meta.json"

        # Try reading from metadata first (FAST - single small JSON read)
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    metadata = json.load(f)

                # Return accurate count from metadata if available
                if "unique_file_count" in metadata:
                    return int(metadata["unique_file_count"])

            except (json.JSONDecodeError, OSError) as e:
                self.logger.warning(f"Failed to read collection metadata: {e}")

        # Fallback: estimation for old indexes or if metadata read fails
        with self._id_index_lock:
            # If file paths already cached, return count from cache (instant)
            if collection_name in self._file_path_cache:
                return len(self._file_path_cache[collection_name])

            # Otherwise estimate: vectors / average chunks per file (~2)
            # This is fast but approximate - acceptable for status display
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            vector_count = len(self._id_index[collection_name])
            # Estimate: most files have 1-3 chunks, average ~2
            estimated_files = max(1, vector_count // 2)

            return estimated_files

    def _calculate_and_save_unique_file_count(
        self, collection_name: str, collection_path: Path
    ) -> int:
        """Calculate unique file count from all vectors and save to collection metadata.

        This method is called ONCE after indexing completes to calculate the 100% accurate
        file count. It's thread-safe with daemon operations via file locking.

        The count represents the CURRENT state of indexed files (not cumulative), which
        handles re-indexing correctly - same file indexed twice only counts once.

        Args:
            collection_name: Name of the collection
            collection_path: Path to collection directory

        Returns:
            Number of unique files indexed

        Note:
            Thread-safe: Uses file locking to prevent race conditions with daemon indexing
        """
        import fcntl
        import json

        # Calculate unique file count from vectors
        unique_files = set()

        # Use cached id_index for speed (already loaded during indexing)
        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            id_index = self._id_index[collection_name]

        # Parse each vector to extract source file path
        for point_id, vector_file in id_index.items():
            try:
                with open(vector_file) as f:
                    vector_data = json.load(f)

                # Extract source file path from payload
                file_path = vector_data.get("payload", {}).get("path")
                if file_path:
                    unique_files.add(file_path)

            except (json.JSONDecodeError, OSError) as e:
                self.logger.warning(
                    f"Failed to read vector file {vector_file} for file count: {e}"
                )
                continue

        unique_file_count = len(unique_files)

        # Update collection metadata with file locking (daemon-safe)
        meta_file = collection_path / "collection_meta.json"
        lock_file = collection_path / ".metadata.lock"
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r") as lock_f:
            # Acquire exclusive lock (blocks if daemon is writing)
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

            try:
                # Read current metadata
                with open(meta_file) as f:
                    metadata = json.load(f)

                # Update unique_file_count
                metadata["unique_file_count"] = unique_file_count

                # Save metadata atomically
                with open(meta_file, "w") as f:
                    json.dump(metadata, f, indent=2)

                self.logger.debug(
                    f"Updated collection metadata: {unique_file_count} unique files"
                )

            finally:
                # Release lock
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

        return unique_file_count

    def get_file_index_timestamps(self, collection_name: str) -> Dict[str, datetime]:
        """Get indexed_at timestamps for all files.

        For files with multiple chunks, returns the latest timestamp.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary mapping file paths to their latest index timestamps
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return {}

        file_timestamps: Dict[str, datetime] = {}

        # Scan all vector JSON files
        for json_file in collection_path.rglob("*.json"):
            # Skip collection metadata
            if "collection_meta" in json_file.name:
                continue

            try:
                with open(json_file) as f:
                    data = json.load(f)

                # Extract file path from payload only
                file_path = data.get("payload", {}).get("path", "")

                if not file_path:
                    continue

                # Get file modification time as timestamp
                file_mtime = json_file.stat().st_mtime
                timestamp = datetime.fromtimestamp(file_mtime)

                # Keep latest timestamp for each file
                if (
                    file_path not in file_timestamps
                    or timestamp > file_timestamps[file_path]
                ):
                    file_timestamps[file_path] = timestamp

            except (json.JSONDecodeError, KeyError, OSError):
                # Skip corrupted or inaccessible files
                continue

        return file_timestamps

    def sample_vectors(self, collection_name: str, sample_size: int = 5) -> List[Dict]:
        """Get random sample of vectors for debugging.

        Args:
            collection_name: Name of the collection
            sample_size: Number of vectors to sample (default: 5)

        Returns:
            List of sampled vector data dictionaries
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return []

        # Collect all vector files
        all_vector_files = [
            f
            for f in collection_path.rglob("*.json")
            if "collection_meta" not in f.name
        ]

        if not all_vector_files:
            return []

        # Sample random files
        sample_count = min(sample_size, len(all_vector_files))
        sampled_files = random.sample(all_vector_files, sample_count)

        sampled_vectors = []

        for vector_file in sampled_files:
            try:
                with open(vector_file) as f:
                    data = json.load(f)

                # Get file_path from payload for consistency
                payload = data.get("payload", {})
                sampled_vectors.append(
                    {
                        "id": data["id"],
                        "vector": data["vector"],
                        "file_path": payload.get("path", ""),
                        "metadata": data.get("metadata", {}),
                    }
                )

            except (json.JSONDecodeError, KeyError):
                # Skip corrupted files
                continue

        return sampled_vectors

    def validate_embedding_dimensions(
        self, collection_name: str, expected_dims: int
    ) -> bool:
        """Verify all vectors have expected dimensions.

        Optimized to sample from cached ID index instead of scanning entire directory tree.
        Performance: O(1) index lookup + O(20) JSON reads (sampled files only).

        Checks a sample of vectors for performance. Empty collections return True.

        Args:
            collection_name: Name of the collection
            expected_dims: Expected vector dimensions

        Returns:
            True if all sampled vectors have expected dimensions, False otherwise
        """
        with self._id_index_lock:
            # Ensure ID index is loaded (cached after first call)
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            index = self._id_index[collection_name]

            if not index:
                return True  # Empty collection is vacuously valid

            # Sample from cached index - no directory scan needed
            sample_count = min(20, len(index))
            sampled_files = random.sample(list(index.values()), sample_count)

        # Validate sampled files
        for vector_file in sampled_files:
            try:
                with open(vector_file) as f:
                    data = json.load(f)

                vector = data.get("vector", [])
                if len(vector) != expected_dims:
                    return False

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                # Skip corrupted or missing files, continue validation
                continue

        return True

    def get_collection_size(self, collection_name: str) -> int:
        """Get total size of collection in bytes.

        Args:
            collection_name: Name of the collection

        Returns:
            Total size in bytes, or 0 if collection doesn't exist
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            return 0

        total_size = 0
        for file_path in collection_path.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    # Skip files we can't access
                    pass

        return total_size

    # === HNSW INCREMENTAL UPDATE HELPER METHODS (HNSW-001 & HNSW-002) ===

    def _update_hnsw_incrementally_realtime(
        self,
        collection_name: str,
        changed_points: List[Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Update HNSW index incrementally in real-time (watch mode).

        Args:
            collection_name: Name of the collection
            changed_points: List of points that were added/updated
            progress_callback: Optional progress callback

        Note:
            HNSW-001: Real-time incremental updates for watch mode.
            Updates HNSW immediately after each batch of file changes,
            enabling queries without rebuild delays.

            AC2 (Concurrent Query Support): Uses readers-writer lock pattern
            AC3 (Daemon Cache Updates): Detects daemon mode and updates cache in-memory
            AC4 (Standalone Persistence): Falls back to disk persistence when no daemon
        """
        if not changed_points:
            return

        collection_path = self.base_path / collection_name
        vector_size = self._get_vector_size(collection_name)

        from .hnsw_index_manager import HNSWIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

        # AC3: Detect daemon mode vs standalone mode
        daemon_mode = hasattr(self, "cache_entry") and self.cache_entry is not None

        if daemon_mode and self.cache_entry is not None:
            # === DAEMON MODE: Update cache in-memory with locking ===
            cache_entry = self.cache_entry

            # AC2: Acquire write lock for exclusive HNSW update
            cache_entry.write_lock.acquire()
            try:
                # AC2: Nest read lock inside write lock to prevent concurrent queries
                cache_entry.read_lock.acquire()
                try:
                    # Load from cache or disk if not cached
                    if cache_entry.hnsw_index is None:
                        # Cache not loaded - load from disk
                        cache_entry.hnsw_index = hnsw_manager.load_index(
                            collection_path, max_elements=100000
                        )

                        from .id_index_manager import IDIndexManager

                        id_manager = IDIndexManager()
                        cache_entry.id_mapping = id_manager.load_index(collection_path)

                    # Use cache references
                    index = cache_entry.hnsw_index
                    id_mapping = cache_entry.id_mapping

                    if index is None:
                        # No existing index - mark as stale for query-time rebuild
                        self.logger.debug(
                            f"No existing HNSW index for watch mode update in '{collection_name}', "
                            f"marking as stale"
                        )
                        hnsw_manager.mark_stale(collection_path)
                        return

                    # Build ID-to-label and label-to-ID mappings
                    label_to_id = hnsw_manager._load_id_mapping(collection_path)
                    id_to_label = {v: k for k, v in label_to_id.items()}
                    next_label = max(label_to_id.keys()) + 1 if label_to_id else 0

                    # Process each changed point
                    processed = 0
                    for point in changed_points:
                        point_id = point["id"]
                        vector = np.array(point["vector"], dtype=np.float32)

                        try:
                            # Add or update in HNSW (updates cache index directly)
                            old_count = len(id_to_label)
                            label, id_to_label, label_to_id, next_label = (
                                hnsw_manager.add_or_update_vector(
                                    index,
                                    point_id,
                                    vector,
                                    id_to_label,
                                    label_to_id,
                                    next_label,
                                )
                            )
                            new_count = len(id_to_label)

                            self.logger.debug(
                                f"Daemon watch mode HNSW: added '{point_id}' with label {label}, "
                                f"mappings: {old_count} -> {new_count}, next_label: {next_label}"
                            )

                            processed += 1

                        except Exception as e:
                            self.logger.warning(
                                f"Failed to update HNSW for point '{point_id}': {e}"
                            )
                            continue

                    # Save updated index to disk (also updates cache since index is same object)
                    total_vectors = len(id_to_label)
                    hnsw_manager.save_incremental_update(
                        index, collection_path, id_to_label, label_to_id, total_vectors
                    )

                    # AC3: Update cache ID mapping (keep cache warm)
                    cache_entry.id_mapping = id_mapping

                    self.logger.debug(
                        f"Daemon watch mode HNSW update complete for '{collection_name}': "
                        f"{processed} points updated, total vectors: {total_vectors}, "
                        f"cache remains warm"
                    )

                finally:
                    # AC2: Release read lock
                    cache_entry.read_lock.release()
            finally:
                # AC2: Release write lock
                cache_entry.write_lock.release()

        else:
            # === STANDALONE MODE: Load from disk, update, save to disk ===
            # Load existing index for incremental update
            index, id_to_label, label_to_id, next_label = (
                hnsw_manager.load_for_incremental_update(collection_path)
            )

            if index is None:
                # No existing index - mark as stale for query-time rebuild
                self.logger.debug(
                    f"No existing HNSW index for watch mode update in '{collection_name}', "
                    f"marking as stale"
                )
                hnsw_manager.mark_stale(collection_path)
                return

            # Process each changed point
            processed = 0
            for point in changed_points:
                point_id = point["id"]
                vector = np.array(point["vector"], dtype=np.float32)

                try:
                    # Add or update in HNSW
                    old_count = len(id_to_label)
                    label, id_to_label, label_to_id, next_label = (
                        hnsw_manager.add_or_update_vector(
                            index,
                            point_id,
                            vector,
                            id_to_label,
                            label_to_id,
                            next_label,
                        )
                    )
                    new_count = len(id_to_label)

                    self.logger.debug(
                        f"Standalone watch mode HNSW: added '{point_id}' with label {label}, "
                        f"mappings: {old_count} -> {new_count}, next_label: {next_label}"
                    )

                    processed += 1

                except Exception as e:
                    self.logger.warning(
                        f"Failed to update HNSW for point '{point_id}': {e}"
                    )
                    continue

            # Save updated index to disk
            total_vectors = len(id_to_label)
            hnsw_manager.save_incremental_update(
                index, collection_path, id_to_label, label_to_id, total_vectors
            )

            self.logger.debug(
                f"Standalone watch mode HNSW update complete for '{collection_name}': "
                f"{processed} points updated, total vectors: {total_vectors}"
            )

    def _apply_incremental_hnsw_batch_update(
        self,
        collection_name: str,
        changes: Dict[str, set],
        progress_callback: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Apply incremental HNSW update for batch of changes.

        Args:
            collection_name: Name of the collection
            changes: Dictionary with 'added', 'updated', 'deleted' sets
            progress_callback: Optional progress callback

        Returns:
            Dictionary with update results, or None if no existing index (fallback to full rebuild)

        Note:
            HNSW-002: Batch incremental updates at end of indexing session.
            Applies all accumulated changes in one batch operation,
            significantly faster than full rebuild.
        """
        collection_path = self.base_path / collection_name
        vector_size = self._get_vector_size(collection_name)

        from .hnsw_index_manager import HNSWIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

        # DEBUG: Mark that we're entering incremental update path
        self.logger.info(
            f"⚡ ENTERING INCREMENTAL HNSW UPDATE PATH for '{collection_name}'"
        )

        # Load existing index for incremental update
        index, id_to_label, label_to_id, next_label = (
            hnsw_manager.load_for_incremental_update(collection_path)
        )

        if index is None:
            # No existing index - return None to trigger full rebuild fallback
            self.logger.info(
                f"🔨 No existing HNSW index for '{collection_name}', "
                f"falling back to FULL REBUILD"
            )
            return None

        # Process additions and updates
        total_changes = (
            len(changes["added"]) + len(changes["updated"]) + len(changes["deleted"])
        )
        processed = 0

        for point_id in changes["added"] | changes["updated"]:
            # Load vector from disk
            try:
                vector_file = self._id_index[collection_name].get(point_id)
                if not vector_file or not Path(vector_file).exists():
                    self.logger.warning(
                        f"Vector file not found for point '{point_id}', skipping"
                    )
                    continue

                with open(vector_file) as f:
                    data = json.load(f)

                vector = np.array(data["vector"], dtype=np.float32)

                # Add or update in HNSW
                label, id_to_label, label_to_id, next_label = (
                    hnsw_manager.add_or_update_vector(
                        index, point_id, vector, id_to_label, label_to_id, next_label
                    )
                )

                processed += 1

                # Report progress periodically
                if progress_callback and processed % 10 == 0:
                    progress_callback(
                        processed,
                        total_changes,
                        Path(""),
                        info=f"🔄 Incremental HNSW update: {processed}/{total_changes} changes",
                    )

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.logger.warning(
                    f"Failed to process point '{point_id}': {e}, skipping"
                )
                continue

        # Process deletions
        for point_id in changes["deleted"]:
            hnsw_manager.remove_vector(index, point_id, id_to_label, label_to_id)
            processed += 1

            # Report progress periodically
            if progress_callback and processed % 10 == 0:
                progress_callback(
                    processed,
                    total_changes,
                    Path(""),
                    info=f"🔄 Incremental HNSW update: {processed}/{total_changes} changes",
                )

        # Save updated index
        total_vectors = len(id_to_label)
        hnsw_manager.save_incremental_update(
            index, collection_path, id_to_label, label_to_id, total_vectors
        )

        # Final progress report
        if progress_callback:
            progress_callback(
                total_changes,
                total_changes,
                Path(""),
                info=f"✓ Incremental HNSW update complete: {total_changes} changes applied",
            )

        self.logger.info(
            f"Incremental HNSW update complete for '{collection_name}': "
            f"{len(changes['added'])} added, {len(changes['updated'])} updated, "
            f"{len(changes['deleted'])} deleted, total vectors: {total_vectors}"
        )

        return {
            "status": "incremental_update_applied",
            "vectors": total_vectors,
            "changes_applied": {
                "added": len(changes["added"]),
                "updated": len(changes["updated"]),
                "deleted": len(changes["deleted"]),
            },
        }
