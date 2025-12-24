"""HNSW-based index manager for fast vector search in filesystem storage.

Provides alternative to binary index using Hierarchical Navigable Small World (HNSW)
algorithm for approximate nearest neighbor search with better query performance.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Try to import hnswlib, gracefully degrade if not available
try:
    import hnswlib

    HNSWLIB_AVAILABLE = True
except ImportError:
    HNSWLIB_AVAILABLE = False


class HNSWIndexManager:
    """Manages HNSW index for fast approximate nearest neighbor search.

    Provides:
    - Build HNSW index from vectors (full rebuild only)
    - Save/load index to/from single binary file
    - Fast k-NN queries with configurable accuracy
    - Metadata tracking in collection_meta.json
    """

    INDEX_FILENAME = "hnsw_index.bin"
    VALID_SPACES = {"cosine", "l2", "ip"}  # inner product

    # Dynamic sizing constants
    GROWTH_FACTOR = 1.5  # 50% growth headroom
    RESIZE_THRESHOLD = 0.8  # Trigger resize at 80% capacity
    MINIMUM_MAX_ELEMENTS = 100000  # Minimum capacity (100K vectors)

    def __init__(self, vector_dim: int = 1536, space: str = "cosine"):
        """Initialize HNSW index manager.

        Args:
            vector_dim: Dimension of vectors (default 1536 for voyage-code-3)
            space: Distance metric ('cosine', 'l2', or 'ip')

        Raises:
            ImportError: If hnswlib is not installed
            ValueError: If space metric is invalid
        """
        if not HNSWLIB_AVAILABLE:
            raise ImportError(
                "hnswlib is not installed. Install with: pip install hnswlib"
            )

        if space not in self.VALID_SPACES:
            raise ValueError(
                f"Invalid space metric: {space}. " f"Must be one of {self.VALID_SPACES}"
            )

        self.vector_dim = vector_dim
        self.space = space

    def calculate_dynamic_max_elements(self, current_count: int) -> int:
        """Calculate dynamic max_elements based on current vector count.

        Uses 1.5x growth factor with 100K minimum to prevent hardcoded limit crashes.

        Args:
            current_count: Current number of vectors in index

        Returns:
            Calculated max_elements value (minimum 100K)
        """
        # Apply growth factor
        calculated = int(current_count * self.GROWTH_FACTOR)

        # Respect minimum threshold
        return max(calculated, self.MINIMUM_MAX_ELEMENTS)

    def should_resize(self, current_count: int, max_elements: int) -> bool:
        """Check if index should be resized based on utilization threshold.

        Triggers resize at 80% capacity to prevent hitting hard limit.

        Args:
            current_count: Current number of vectors in index
            max_elements: Current max_elements capacity

        Returns:
            True if resize needed, False otherwise
        """
        if max_elements == 0:
            return False

        utilization = current_count / max_elements
        return utilization >= self.RESIZE_THRESHOLD

    def build_index(
        self,
        collection_path: Path,
        vectors: np.ndarray,
        ids: List[str],
        M: int = 16,
        ef_construction: int = 200,
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Build HNSW index from vectors and save to disk.

        Args:
            collection_path: Path to collection directory
            vectors: Numpy array of shape (N, vector_dim)
            ids: List of vector IDs (same length as vectors)
            M: HNSW parameter - number of connections per layer
               (higher = more accurate, larger index)
            ef_construction: HNSW parameter - size of dynamic candidate list
                           (higher = better quality, slower build)
            progress_callback: Optional callback(current, total, file_path, info) for progress tracking

        Raises:
            ValueError: If vector dimensions don't match or IDs length doesn't match
        """
        # Validate inputs
        if vectors.shape[1] != self.vector_dim:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.vector_dim}, "
                f"got {vectors.shape[1]}"
            )

        if len(ids) != len(vectors):
            raise ValueError(
                f"IDs length ({len(ids)}) doesn't match vectors length ({len(vectors)})"
            )

        num_vectors = len(vectors)

        # Calculate dynamic max_elements with growth headroom
        max_elements = self.calculate_dynamic_max_elements(num_vectors)

        # Create HNSW index
        index = hnswlib.Index(space=self.space, dim=self.vector_dim)
        index.init_index(max_elements=max_elements, M=M, ef_construction=ef_construction)

        # Add vectors to index with labels (use indices as labels)
        # We'll store the ID mapping separately in metadata
        labels = np.arange(num_vectors)

        # Report info message at start
        if progress_callback:
            progress_callback(0, 0, Path(""), info="🔧 Building HNSW index...")
            # DEBUG: Mark full build for manual testing
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🔨 FULL HNSW INDEX BUILD: Creating index from scratch with {num_vectors} vectors",
            )

        index.add_items(vectors, labels)

        # Report info message at completion
        if progress_callback:
            progress_callback(0, 0, Path(""), info="🔧 HNSW index built ✓")

        # Save index to disk
        index_file = collection_path / self.INDEX_FILENAME
        index.save_index(str(index_file))

        # Update metadata
        self._update_metadata(
            collection_path=collection_path,
            vector_count=num_vectors,
            max_elements=max_elements,
            M=M,
            ef_construction=ef_construction,
            ids=ids,
            index_file_size=index_file.stat().st_size,
        )

    def load_index(
        self, collection_path: Path, max_elements: Optional[int] = None
    ) -> Optional[Any]:
        """Load HNSW index from disk with dynamic sizing.

        Reads max_elements from metadata for crash recovery. Falls back to
        calculating dynamic max_elements if metadata missing.

        Args:
            collection_path: Path to collection directory
            max_elements: Optional override for maximum elements (for backward compatibility)

        Returns:
            hnswlib.Index instance or None if index doesn't exist
        """
        index_file = collection_path / self.INDEX_FILENAME

        if not index_file.exists():
            return None

        # Determine max_elements: override > metadata > calculated
        if max_elements is None:
            # Try to read from metadata
            meta_file = collection_path / "collection_meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        metadata = json.load(f)

                    stored_max = metadata.get("hnsw_index", {}).get("max_elements")
                    vector_count = metadata.get("hnsw_index", {}).get("vector_count", 0)

                    if stored_max is not None:
                        # Use stored max_elements from metadata
                        max_elements = stored_max
                    else:
                        # Fallback: calculate from vector_count for old metadata
                        max_elements = self.calculate_dynamic_max_elements(vector_count)

                except (json.JSONDecodeError, KeyError):
                    # Corrupted metadata - use safe default
                    max_elements = self.MINIMUM_MAX_ELEMENTS
            else:
                # No metadata - use safe default
                max_elements = self.MINIMUM_MAX_ELEMENTS

        # Create index instance
        index = hnswlib.Index(space=self.space, dim=self.vector_dim)

        # Load from disk
        index.load_index(str(index_file), max_elements=max_elements)

        return index

    def query(
        self,
        index: Any,
        query_vector: np.ndarray,
        collection_path: Path,
        k: int = 10,
        ef: int = 50,
    ) -> Tuple[List[str], List[float]]:
        """Query HNSW index for k nearest neighbors.

        Args:
            index: hnswlib.Index instance from load_index()
            query_vector: Query vector (1D array of shape (vector_dim,))
            collection_path: Path to collection directory (for loading ID mapping)
            k: Number of nearest neighbors to return
            ef: HNSW query parameter - size of dynamic candidate list
                (higher = more accurate, slower)

        Returns:
            Tuple of (ids, distances) where ids are vector IDs and
            distances are similarity scores

        Raises:
            ValueError: If query vector dimension doesn't match
        """
        # Validate query vector dimension
        if len(query_vector) != self.vector_dim:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.vector_dim}, "
                f"got {len(query_vector)}"
            )

        # Set ef parameter for query-time accuracy
        index.set_ef(ef)

        # Load ID mapping from metadata (reflects actual non-deleted vectors)
        id_mapping = self._load_id_mapping(collection_path)

        # Get actual queryable vector count (excludes soft-deleted)
        # Note: get_current_count() includes soft-deleted vectors, causing errors
        queryable_count = len(id_mapping) if id_mapping else index.get_current_count()

        # Limit k to available queryable vectors
        k_actual = min(k, queryable_count)

        # Ensure k_actual is at least 1 if there are any vectors
        if k_actual == 0 and queryable_count > 0:
            k_actual = 1

        # Query index (returns labels and distances)
        labels, distances = index.knn_query(query_vector, k=k_actual)

        # Convert labels to IDs
        result_ids = [id_mapping.get(int(label), f"vec_{label}") for label in labels[0]]
        result_distances = [float(d) for d in distances[0]]

        return result_ids, result_distances

    def index_exists(self, collection_path: Path) -> bool:
        """Check if HNSW index exists.

        Args:
            collection_path: Path to collection directory

        Returns:
            True if index file exists, False otherwise
        """
        index_file = collection_path / self.INDEX_FILENAME
        return index_file.exists()

    def get_index_stats(self, collection_path: Path) -> Optional[Dict[str, Any]]:
        """Get index statistics from metadata.

        Args:
            collection_path: Path to collection directory

        Returns:
            Dictionary with index statistics or None if index doesn't exist
        """
        meta_file = collection_path / "collection_meta.json"

        if not meta_file.exists():
            return None

        try:
            with open(meta_file) as f:
                metadata = json.load(f)

            if "hnsw_index" not in metadata:
                return None

            hnsw_meta: Dict[str, Any] = metadata["hnsw_index"]
            return hnsw_meta

        except (json.JSONDecodeError, KeyError):
            return None

    def rebuild_from_vectors(
        self, collection_path: Path, progress_callback: Optional[Any] = None
    ) -> int:
        """Rebuild HNSW index by scanning all vector JSON files.

        Uses BackgroundIndexRebuilder for atomic file swapping with exclusive
        locking. Queries can continue using old index during rebuild.

        Args:
            collection_path: Path to collection directory
            progress_callback: Optional callback(current, total, file_path, info) for progress tracking

        Returns:
            Number of vectors indexed

        Raises:
            FileNotFoundError: If collection metadata is missing
        """
        from .background_index_rebuilder import BackgroundIndexRebuilder

        # Load collection metadata to get vector dimension
        meta_file = collection_path / "collection_meta.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Collection metadata not found at {meta_file}")

        with open(meta_file) as f:
            metadata = json.load(f)
            expected_dim = metadata.get("vector_dim", self.vector_dim)

        # Scan all vector JSON files
        vector_files = list(collection_path.rglob("vector_*.json"))
        total_files = len(vector_files)

        if total_files == 0:
            return 0

        # Report info message at start
        if progress_callback:
            progress_callback(0, 0, Path(""), info="🔧 Rebuilding HNSW index...")

        # Load all vectors and IDs
        vectors_list = []
        ids_list = []

        for vector_file in vector_files:
            try:
                with open(vector_file) as f:
                    data = json.load(f)

                vector = np.array(data["vector"], dtype=np.float32)
                point_id = data["id"]

                # Validate dimension
                if len(vector) != expected_dim:
                    continue  # Skip mismatched dimensions

                vectors_list.append(vector)
                ids_list.append(point_id)

            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip malformed files
                continue

        if not vectors_list:
            return 0

        # Convert to numpy array
        vectors = np.array(vectors_list, dtype=np.float32)

        # Calculate dynamic max_elements
        max_elements = self.calculate_dynamic_max_elements(len(vectors))

        # Use BackgroundIndexRebuilder for atomic swap with locking
        rebuilder = BackgroundIndexRebuilder(collection_path)
        index_file = collection_path / self.INDEX_FILENAME

        def build_hnsw_index_to_temp(temp_file: Path) -> None:
            """Build HNSW index to temp file."""
            # Create HNSW index
            index = hnswlib.Index(space=self.space, dim=self.vector_dim)
            index.init_index(max_elements=max_elements, M=16, ef_construction=200)

            # Add vectors
            labels = np.arange(len(vectors))
            if progress_callback:
                progress_callback(0, 0, Path(""), info="🔧 Building HNSW index...")
            index.add_items(vectors, labels)

            # Save to temp file
            index.save_index(str(temp_file))

            if progress_callback:
                progress_callback(0, 0, Path(""), info="🔧 HNSW index built ✓")

        # Rebuild with lock (entire rebuild duration)
        rebuilder.rebuild_with_lock(build_hnsw_index_to_temp, index_file)

        # Update metadata AFTER atomic swap
        self._update_metadata(
            collection_path=collection_path,
            vector_count=len(vectors),
            max_elements=max_elements,
            M=16,
            ef_construction=200,
            ids=ids_list,
            index_file_size=index_file.stat().st_size,
        )

        return len(vectors)

    def mark_stale(self, collection_path: Path) -> None:
        """Mark HNSW index as stale (needs rebuilding).

        Uses file locking for cross-process coordination. Sets is_stale=true
        in collection metadata to indicate index needs rebuilding.

        Args:
            collection_path: Path to collection directory

        Note:
            This method is called by watch mode to defer HNSW rebuild until query time.
        """
        import fcntl

        meta_file = collection_path / "collection_meta.json"
        lock_file = collection_path / ".metadata.lock"
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r") as lock_f:
            # Acquire exclusive lock (blocks if query is rebuilding)
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            try:
                # Load existing metadata
                if not meta_file.exists():
                    return  # No metadata to mark stale

                with open(meta_file) as f:
                    metadata = json.load(f)

                if "hnsw_index" not in metadata:
                    return  # No HNSW index to mark stale

                # Mark as stale
                metadata["hnsw_index"]["is_stale"] = True
                metadata["hnsw_index"]["last_marked_stale"] = datetime.now(
                    timezone.utc
                ).isoformat()

                # Save metadata
                with open(meta_file, "w") as f:
                    json.dump(metadata, f, indent=2)
            finally:
                # Release lock
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

    def is_stale(self, collection_path: Path) -> bool:
        """Check if HNSW index needs rebuilding.

        Returns True if any of the following conditions are met:
        - is_stale flag is set to True in metadata
        - Vector count mismatch (fallback detection for incremental indexing)
        - No metadata exists (no index built yet)

        Args:
            collection_path: Path to collection directory

        Returns:
            True if HNSW index needs rebuilding, False if fresh

        Note:
            No locking needed - atomic boolean read. Defaults to True if
            is_stale flag missing (backward compatibility with old metadata).
        """
        meta_file = collection_path / "collection_meta.json"

        if not meta_file.exists():
            return True  # No metadata = needs build

        try:
            with open(meta_file) as f:
                metadata = json.load(f)

            if "hnsw_index" not in metadata:
                return True  # No HNSW index = needs build

            hnsw_info = metadata["hnsw_index"]

            # Check is_stale flag (default to True if missing for backward compatibility)
            is_stale_flag = hnsw_info.get("is_stale", True)
            if is_stale_flag:
                return True

            # Fallback detection: Check for vector count mismatch
            # This catches incremental indexing that bypassed mark_stale()
            # Only perform this check if there are actual vector files (not just HNSW index)
            stored_count = hnsw_info.get("vector_count", 0)
            vector_files = list(collection_path.rglob("vector_*.json"))
            actual_count = len(vector_files)

            # Only check count mismatch if vector files exist
            # (avoids false positives when only HNSW index exists)
            if actual_count > 0 and stored_count != actual_count:
                return True  # Count mismatch = needs rebuild

            return False  # Fresh index

        except (json.JSONDecodeError, KeyError):
            return True  # Corrupted metadata = needs rebuild

    def _update_metadata(
        self,
        collection_path: Path,
        vector_count: int,
        max_elements: int,
        M: int,
        ef_construction: int,
        ids: List[str],
        index_file_size: int,
    ) -> None:
        """Update collection metadata with HNSW index information.

        Args:
            collection_path: Path to collection directory
            vector_count: Number of vectors in index
            max_elements: Maximum elements capacity of index
            M: HNSW M parameter
            ef_construction: HNSW ef_construction parameter
            ids: List of vector IDs
            index_file_size: Size of index file in bytes
        """
        import fcntl
        import uuid

        meta_file = collection_path / "collection_meta.json"

        # Use file locking to prevent race conditions in concurrent writes
        lock_file = collection_path / ".metadata.lock"
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r") as lock_f:
            # Acquire exclusive lock
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            try:
                # Load existing metadata or create new
                if meta_file.exists():
                    with open(meta_file) as f:
                        metadata = json.load(f)
                else:
                    metadata = {}

                # Create ID mapping (label -> ID)
                id_mapping = {str(i): ids[i] for i in range(len(ids))}

                # Update HNSW index metadata with staleness tracking + rebuild version (AC12)
                metadata["hnsw_index"] = {
                    "version": 1,
                    "index_rebuild_uuid": str(
                        uuid.uuid4()
                    ),  # AC12: Track rebuild version
                    "vector_count": vector_count,
                    "max_elements": max_elements,  # Store for crash recovery
                    "vector_dim": self.vector_dim,
                    "M": M,
                    "ef_construction": ef_construction,
                    "space": self.space,
                    "last_rebuild": datetime.now(timezone.utc).isoformat(),
                    "file_size_bytes": index_file_size,
                    "id_mapping": id_mapping,
                    # Staleness tracking fields
                    "is_stale": False,  # Fresh after rebuild
                    "last_marked_stale": None,  # No staleness marking yet
                }

                # Save metadata
                with open(meta_file, "w") as f:
                    json.dump(metadata, f, indent=2)
            finally:
                # Release lock
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

    def _load_id_mapping(self, collection_path: Path) -> Dict[int, str]:
        """Load ID mapping from metadata.

        Args:
            collection_path: Path to collection directory

        Returns:
            Dictionary mapping label (int) to vector ID (str)
        """
        meta_file = collection_path / "collection_meta.json"

        if not meta_file.exists():
            return {}

        try:
            with open(meta_file) as f:
                metadata = json.load(f)

            if "hnsw_index" not in metadata:
                return {}

            id_mapping_str = metadata["hnsw_index"].get("id_mapping", {})

            # Convert string keys back to int
            return {int(k): v for k, v in id_mapping_str.items()}

        except (json.JSONDecodeError, KeyError, ValueError):
            return {}

    # === INCREMENTAL UPDATE METHODS (HNSW-001 & HNSW-002) ===

    def load_for_incremental_update(
        self, collection_path: Path
    ) -> Tuple[Optional[Any], Dict[str, int], Dict[int, str], int]:
        """Load HNSW index with metadata for incremental updates.

        Args:
            collection_path: Path to collection directory

        Returns:
            Tuple of (index, id_to_label, label_to_id, next_label)
            - index: hnswlib.Index instance or None if doesn't exist
            - id_to_label: Dict mapping point_id (str) to label (int)
            - label_to_id: Dict mapping label (int) to point_id (str)
            - next_label: Next available label for new vectors

        Note:
            For watch mode real-time updates and batch incremental updates.
        """
        index_file = collection_path / self.INDEX_FILENAME

        if not index_file.exists():
            # No existing index - return empty mappings
            return None, {}, {}, 0

        # Load HNSW index (using dynamic sizing from metadata)
        index = self.load_index(collection_path)

        # Load ID mappings from metadata
        label_to_id = self._load_id_mapping(collection_path)

        # Create reverse mapping
        id_to_label = {v: k for k, v in label_to_id.items()}

        # Calculate next label
        next_label = max(label_to_id.keys()) + 1 if label_to_id else 0

        return index, id_to_label, label_to_id, next_label

    def add_or_update_vector(
        self,
        index: Any,
        point_id: str,
        vector: np.ndarray,
        id_to_label: Dict[str, int],
        label_to_id: Dict[int, str],
        next_label: int,
    ) -> Tuple[int, Dict[str, int], Dict[int, str], int]:
        """Add new vector or update existing vector in HNSW index.

        Args:
            index: hnswlib.Index instance
            point_id: Point identifier
            vector: Vector to add/update
            id_to_label: Current id_to_label mapping
            label_to_id: Current label_to_id mapping
            next_label: Next available label

        Returns:
            Tuple of (label, updated_id_to_label, updated_label_to_id, updated_next_label)

        Note:
            - For new points: Assigns new label and adds to index
            - For existing points: Reuses label and marks old version as deleted,
              then adds updated version (soft delete + add pattern)
        """
        if point_id in id_to_label:
            # Existing point - reuse label
            label = id_to_label[point_id]

            # Mark old version as deleted (soft delete)
            index.mark_deleted(label)

            # Add updated version with same label
            # Note: HNSW doesn't support in-place update, so we delete + re-add
            index.add_items(vector.reshape(1, -1), np.array([label]))

            return label, id_to_label, label_to_id, next_label
        else:
            # New point - assign new label
            label = next_label

            # Add to index
            index.add_items(vector.reshape(1, -1), np.array([label]))

            # Update mappings
            id_to_label[point_id] = label
            label_to_id[label] = point_id

            return label, id_to_label, label_to_id, next_label + 1

    def remove_vector(
        self,
        index: Any,
        point_id: str,
        id_to_label: Dict[str, int],
        label_to_id: Optional[Dict[int, str]] = None,
    ) -> None:
        """Remove vector from HNSW index using soft delete and clean up mappings.

        Args:
            index: hnswlib.Index instance
            point_id: Point identifier to remove
            id_to_label: Current id_to_label mapping
            label_to_id: Current label_to_id mapping (optional for backward compatibility)

        Note:
            Uses HNSW soft delete (mark_deleted) which filters results during search.
            Physical removal is NOT performed - the vector remains in the index structure
            but won't appear in search results.

            CRITICAL: Also removes the point_id from id_to_label and label_to_id mappings
            to prevent stale metadata from causing duplicate results in queries (Story #540).
        """
        if point_id in id_to_label:
            label = id_to_label[point_id]
            index.mark_deleted(label)

            # Clean up mappings to prevent stale metadata (Story #540)
            del id_to_label[point_id]
            if label_to_id is not None and label in label_to_id:
                del label_to_id[label]

    def save_incremental_update(
        self,
        index: Any,
        collection_path: Path,
        id_to_label: Dict[str, int],
        label_to_id: Dict[int, str],
        vector_count: int,
    ) -> None:
        """Save HNSW index after incremental updates.

        Args:
            index: hnswlib.Index instance with updates
            collection_path: Path to collection directory
            id_to_label: Updated id_to_label mapping
            label_to_id: Updated label_to_id mapping
            vector_count: Total number of vectors (including deleted)

        Note:
            Updates both index file and metadata with new mappings.
            Preserves existing HNSW parameters (M, ef_construction).
        """
        import fcntl
        import logging

        logger = logging.getLogger(__name__)

        # DEBUG: Mark incremental update for manual testing
        current_index_size = index.get_current_count() if index else 0
        num_new_vectors = len(id_to_label)
        # Use INFO level so it's visible in logs
        logger.info(
            f"⚡ INCREMENTAL HNSW UPDATE: Adding/updating {num_new_vectors} vectors (total index size: {current_index_size})"
        )

        # Save index to disk
        index_file = collection_path / self.INDEX_FILENAME
        index.save_index(str(index_file))

        # Update metadata with new mappings
        meta_file = collection_path / "collection_meta.json"
        lock_file = collection_path / ".metadata.lock"
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r") as lock_f:
            # Acquire exclusive lock
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            try:
                # Load existing metadata
                if meta_file.exists():
                    with open(meta_file) as f:
                        metadata = json.load(f)
                else:
                    metadata = {}

                # Get existing HNSW config or use defaults
                existing_hnsw = metadata.get("hnsw_index", {})
                M = existing_hnsw.get("M", 16)
                ef_construction = existing_hnsw.get("ef_construction", 200)

                # Calculate dynamic max_elements based on current vector count
                max_elements = self.calculate_dynamic_max_elements(vector_count)

                # Create ID mapping (label -> ID) for metadata
                id_mapping = {
                    str(label): point_id for label, point_id in label_to_id.items()
                }

                # Update HNSW index metadata (AC12: preserve or generate new UUID)
                import uuid

                # Generate new UUID for incremental updates too (version tracking)
                metadata["hnsw_index"] = {
                    "version": 1,
                    "index_rebuild_uuid": str(
                        uuid.uuid4()
                    ),  # AC12: Track rebuild version
                    "vector_count": vector_count,
                    "max_elements": max_elements,  # Store for crash recovery
                    "vector_dim": self.vector_dim,
                    "M": M,
                    "ef_construction": ef_construction,
                    "space": self.space,
                    "last_rebuild": datetime.now(timezone.utc).isoformat(),
                    "file_size_bytes": index_file.stat().st_size,
                    "id_mapping": id_mapping,
                    # Mark as fresh after incremental update
                    "is_stale": False,
                    "last_marked_stale": None,
                }

                # Save metadata
                with open(meta_file, "w") as f:
                    json.dump(metadata, f, indent=2)
            finally:
                # Release lock
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
