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

        # Create HNSW index
        index = hnswlib.Index(space=self.space, dim=self.vector_dim)
        index.init_index(max_elements=num_vectors, M=M, ef_construction=ef_construction)

        # Add vectors to index with labels (use indices as labels)
        # We'll store the ID mapping separately in metadata
        labels = np.arange(num_vectors)

        # Report progress before adding items
        if progress_callback:
            progress_callback(0, num_vectors, Path(""), info="Building HNSW index")

        index.add_items(vectors, labels)

        # Report progress after adding items
        if progress_callback:
            progress_callback(
                num_vectors, num_vectors, Path(""), info="HNSW index complete"
            )

        # Save index to disk
        index_file = collection_path / self.INDEX_FILENAME
        index.save_index(str(index_file))

        # Update metadata
        self._update_metadata(
            collection_path=collection_path,
            vector_count=num_vectors,
            M=M,
            ef_construction=ef_construction,
            ids=ids,
            index_file_size=index_file.stat().st_size,
        )

    def load_index(
        self, collection_path: Path, max_elements: int = 100000
    ) -> Optional[Any]:
        """Load HNSW index from disk.

        Args:
            collection_path: Path to collection directory
            max_elements: Maximum number of elements (for index initialization)

        Returns:
            hnswlib.Index instance or None if index doesn't exist
        """
        index_file = collection_path / self.INDEX_FILENAME

        if not index_file.exists():
            return None

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

        # Get actual number of elements in index
        num_elements = index.get_current_count()

        # Limit k to available vectors
        k_actual = min(k, num_elements)

        # Query index (returns labels and distances)
        labels, distances = index.knn_query(query_vector, k=k_actual)

        # Load ID mapping from metadata
        id_mapping = self._load_id_mapping(collection_path)

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

        Args:
            collection_path: Path to collection directory
            progress_callback: Optional callback(current, total, file_path, info) for progress tracking

        Returns:
            Number of vectors indexed

        Raises:
            FileNotFoundError: If collection metadata is missing
        """
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

        # Load all vectors and IDs
        vectors_list = []
        ids_list = []

        for idx, vector_file in enumerate(vector_files, 1):
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

                # Report progress periodically
                if progress_callback and idx % 100 == 0:
                    progress_callback(idx, total_files, Path(""), info="Rebuilding HNSW index")

            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip malformed files
                continue

        if not vectors_list:
            return 0

        # Convert to numpy array
        vectors = np.array(vectors_list, dtype=np.float32)

        # Build index
        self.build_index(
            collection_path=collection_path,
            vectors=vectors,
            ids=ids_list,
            progress_callback=progress_callback,
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
        M: int,
        ef_construction: int,
        ids: List[str],
        index_file_size: int,
    ) -> None:
        """Update collection metadata with HNSW index information.

        Args:
            collection_path: Path to collection directory
            vector_count: Number of vectors in index
            M: HNSW M parameter
            ef_construction: HNSW ef_construction parameter
            ids: List of vector IDs
            index_file_size: Size of index file in bytes
        """
        import fcntl

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

                # Update HNSW index metadata with staleness tracking
                metadata["hnsw_index"] = {
                    "version": 1,
                    "vector_count": vector_count,
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
