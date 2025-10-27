"""Filesystem-based vector storage with git-aware optimization.

Implements QdrantClient-compatible interface for storing vectors in filesystem
with path-as-vector quantization and git-aware chunk storage.
Following Story 2 requirements.
"""

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
import threading
import numpy as np
import logging

from .vector_quantizer import VectorQuantizer
from .projection_matrix_manager import ProjectionMatrixManager


class FilesystemVectorStore:
    """Filesystem-based vector storage with git-aware optimization.

    Features:
    - QdrantClient-compatible interface
    - Path-as-vector quantization for efficient storage
    - Git-aware chunk storage (blob hash for clean, text for dirty)
    - Thread-safe atomic writes
    - ID indexing for fast lookups
    """

    def __init__(self, base_path: Path, project_root: Optional[Path] = None):
        """Initialize filesystem vector store.

        Args:
            base_path: Base directory for all collections
            project_root: Root directory of the project being indexed (for git operations)
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
        """
        self.logger.info(
            f"Beginning indexing session for collection '{collection_name}'"
        )

        # Clear file path cache for this collection
        with self._id_index_lock:
            if collection_name in self._file_path_cache:
                del self._file_path_cache[collection_name]

    def end_indexing(
        self, collection_name: str, progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Finalize indexing by rebuilding HNSW and ID indexes.

        Called ONCE after all upsert_points() operations complete. This is where
        the O(n²) → O(n) optimization happens - we rebuild indexes only once instead
        of after every upsert.

        Args:
            collection_name: Name of the collection
            progress_callback: Optional callback for progress reporting

        Returns:
            Status dictionary with rebuild results

        Raises:
            ValueError: If collection doesn't exist

        Note:
            Before this optimization, upsert_points() rebuilt indexes after EVERY file,
            causing O(n²) complexity. Now we rebuild indexes ONCE at the end.
        """
        collection_path = self.base_path / collection_name

        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        self.logger.info(f"Finalizing indexes for collection '{collection_name}'...")

        # Get vector size from cache (avoids file I/O)
        vector_size = self._get_vector_size(collection_name)

        # Rebuild HNSW index from ALL vectors on disk (ONCE)
        from .hnsw_index_manager import HNSWIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")
        hnsw_manager.rebuild_from_vectors(
            collection_path=collection_path, progress_callback=progress_callback
        )

        # Save ID index to disk (ONCE)
        from .id_index_manager import IDIndexManager

        id_manager = IDIndexManager()
        with self._id_index_lock:
            if collection_name in self._id_index:
                id_manager.save_index(collection_path, self._id_index[collection_name])

        vector_count = len(self._id_index.get(collection_name, {}))

        self.logger.info(
            f"Indexing finalized for '{collection_name}': {vector_count} vectors indexed"
        )

        return {
            "status": "ok",
            "vectors_indexed": vector_count,
            "collection": collection_name,
        }

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
    ) -> Dict[str, Any]:
        """Store vectors in filesystem with git-aware optimization.

        Args:
            collection_name: Name of the collection (if None, auto-resolves to only collection)
            points: List of point dictionaries with id, vector, payload
            progress_callback: Optional callback(current, total, Path, info) for progress reporting

        Returns:
            Status dictionary with operation result

        Raises:
            ValueError: If collection_name is None and multiple collections exist
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

        if repo_root is not None and file_paths:
            blob_hashes = self._get_blob_hashes_batch(file_paths, repo_root)
            uncommitted_files = self._check_uncommitted_batch(file_paths, repo_root)

        # Ensure ID index exists for this collection (also loads file path cache)
        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)
            # Ensure file path cache exists (in case ID index was manually populated)
            if collection_name not in self._file_path_cache:
                self._file_path_cache[collection_name] = set()

        # Process all points
        total_points = len(points)
        for idx, point in enumerate(points, 1):
            try:
                point_id = point["id"]
                vector = np.array(point["vector"])
                payload = point.get("payload", {})
                file_path = payload.get("path", "")

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
                repo_root=repo_root,
                blob_hashes=blob_hashes,
                uncommitted_files=uncommitted_files,
            )

            # Atomic write to filesystem
            self._atomic_write_json(vector_file, vector_data)

            # Update ID index and file path cache
            with self._id_index_lock:
                self._id_index[collection_name][point_id] = vector_file
                # Update file path cache
                if file_path:
                    self._file_path_cache[collection_name].add(file_path)

        # Return success - index rebuilding now happens in end_indexing() (O(n) not O(n²))
        # This fixes the performance disaster where we rebuilt indexes after EVERY file.
        # Now indexes are rebuilt ONCE at the end of the indexing session.
        return {"status": "ok", "count": len(points)}

    def count_points(self, collection_name: str) -> int:
        """Count vectors in collection using ID index.

        Args:
            collection_name: Name of the collection

        Returns:
            Number of vectors in collection
        """
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
        """
        deleted = 0

        with self._id_index_lock:
            if collection_name not in self._id_index:
                self._id_index[collection_name] = self._load_id_index(collection_name)

            index = self._id_index[collection_name]

            for point_id in point_ids:
                if point_id in index:
                    vector_file = index[point_id]

                    # Delete file if it exists
                    if vector_file.exists():
                        vector_file.unlink()
                        deleted += 1

                    # Remove from index
                    del index[point_id]

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

    def _load_id_index(self, collection_name: str) -> Dict[str, Path]:
        """Load ID index from filenames only - no file I/O required.

        Point IDs are encoded in filenames as: vector_POINTID.json
        This allows instant index loading without parsing JSON files.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary mapping point IDs to file paths
        """
        collection_path = self.base_path / collection_name
        index = {}

        # Scan vector files by filename pattern only
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

                # Extract file path from payload
                file_path = data.get("payload", {}).get("path") or data.get(
                    "file_path", ""
                )
                if file_path:
                    file_paths.add(file_path)

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                # Skip corrupted or missing files
                continue

        return file_paths

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
        repo_root: Optional[Path],
        blob_hashes: Dict[str, str],
        uncommitted_files: set,
    ) -> Dict[str, Any]:
        """Prepare vector data using batch git operation results.

        Args:
            point_id: Unique point identifier
            vector: Vector data
            payload: Point payload
            repo_root: Git repository root (None if not a git repo)
            blob_hashes: Dict of file_path -> blob_hash from batch operation
            uncommitted_files: Set of files with uncommitted changes

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
            "payload": payload,  # Store full payload for search operations
        }

        file_path = payload.get("path", "")

        # Git-aware chunk storage logic using batch results
        if repo_root and file_path:
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
                data["chunk_text"] = payload.get("content", "")
                data["indexed_with_uncommitted_changes"] = True
                # Remove content from payload (stored in chunk_text instead)
                if "content" in data["payload"]:
                    del data["payload"]["content"]
        else:
            # Non-git repo: always store chunk_text
            data["chunk_text"] = payload.get("content", "")
            # Remove content from payload (stored in chunk_text instead)
            if "content" in data["payload"]:
                del data["payload"]["content"]

        return data

    def _get_blob_hashes_batch(
        self, file_paths: List[str], repo_root: Path
    ) -> Dict[str, str]:
        """Get git blob hashes for multiple files in single git call.

        Args:
            file_paths: List of file paths relative to repo root
            repo_root: Git repository root

        Returns:
            Dictionary mapping file_path to blob_hash
        """
        try:
            # Single git ls-tree call for all files
            result = subprocess.run(
                ["git", "ls-tree", "HEAD"] + file_paths,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

            blob_hashes = {}
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
        """Check which files have uncommitted changes in single git call.

        Args:
            file_paths: List of file paths to check
            repo_root: Git repository root

        Returns:
            Set of file paths with uncommitted changes
        """
        try:
            # Single git status call with file arguments
            result = subprocess.run(
                ["git", "status", "--porcelain"] + file_paths,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

            uncommitted = set()
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

                return {
                    "id": data["id"],
                    "vector": data["vector"],
                    "payload": data.get(
                        "payload",
                        {
                            "path": data.get("file_path", ""),
                            "start_line": data.get("start_line", 0),
                            "end_line": data.get("end_line", 0),
                            "language": data.get("metadata", {}).get("language", ""),
                            "type": data.get("metadata", {}).get("type", "content"),
                        },
                    ),
                }
            except (json.JSONDecodeError, KeyError):
                return None

    def _parse_qdrant_filter(self, filter_conditions: Optional[Dict[str, Any]]) -> Any:
        """Parse filter to callable that evaluates payload.

        Supports TWO filter formats for backward compatibility:

        1. Qdrant-style nested filters (CLI format):
           {"must": [{"key": "language", "match": {"value": "python"}}]}
           {"should": [{"key": "type", "match": {"value": "test"}}]}
           {"must_not": [{"key": "git_available", "match": {"value": False}}]}

        2. Flat dict filters (legacy format):
           {"language": "python", "type": "test"}

        Args:
            filter_conditions: Filter dictionary in either format

        Returns:
            Callable that takes payload dict and returns True if matches filter
        """
        if not filter_conditions:
            return lambda payload: True

        # Detect filter format: Qdrant-style has "must"/"should"/"must_not" keys
        is_qdrant_style = any(
            key in filter_conditions for key in ["must", "should", "must_not"]
        )

        if is_qdrant_style:
            # Qdrant-style nested filter
            def evaluate_condition(
                condition: Dict[str, Any], payload: Dict[str, Any]
            ) -> bool:
                """Evaluate a single Qdrant-style condition against payload.

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

                    match_spec = condition.get("match", {})

                    # Handle nested payload keys (e.g., "metadata.language")
                    current: Any = payload
                    for key_part in key.split("."):
                        if isinstance(current, dict):
                            current = current.get(key_part)
                        else:
                            return False

                    # Support both "value" (exact match) and "text" (pattern match)
                    if "value" in match_spec:
                        # Exact match
                        expected_value = match_spec["value"]
                        return bool(current == expected_value)
                    elif "text" in match_spec:
                        # Pattern match (glob-style wildcards)
                        import fnmatch

                        pattern = match_spec["text"]
                        if not isinstance(current, str):
                            return False
                        return bool(fnmatch.fnmatch(current, pattern))
                    else:
                        # No match specification found
                        return False

            def evaluate_filter(payload: Dict[str, Any]) -> bool:
                """Evaluate full Qdrant-style filter against payload."""
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
                    point["payload"] = data.get(
                        "payload",
                        {
                            "path": data.get("file_path", ""),
                            "start_line": data.get("start_line", 0),
                            "end_line": data.get("end_line", 0),
                            "language": data.get("metadata", {}).get("language", ""),
                            "type": data.get("metadata", {}).get("type", "content"),
                        },
                    )

                if with_vectors:
                    point["vector"] = data["vector"]

                # Apply filter conditions using Qdrant filter parser
                if filter_conditions:
                    payload = point.get("payload", {})
                    filter_func = self._parse_qdrant_filter(filter_conditions)
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

        # === PARALLEL EXECUTION (always) ===
        from .hnsw_index_manager import HNSWIndexManager

        vector_size = metadata.get("vector_size", 1536)
        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

        def load_index():
            """Load HNSW and ID indexes in parallel thread."""
            # Load HNSW index
            t_hnsw = time.time()
            hnsw_index = hnsw_manager.load_index(collection_path, max_elements=100000)
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

        # Query HNSW index
        t0 = time.time()
        candidate_ids, distances = hnsw_manager.query(
            index=hnsw_index,
            query_vector=query_vec,
            collection_path=collection_path,
            k=limit * 2,  # Get more candidates for filtering
            ef=50,  # HNSW query parameter
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
                    filter_func = self._parse_qdrant_filter(filter_conditions)
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

                results.append(
                    {
                        "id": data["id"],
                        "score": float(similarity),
                        "payload": data.get(
                            "payload",
                            {
                                "path": data.get("file_path", ""),
                                "start_line": data.get("start_line", 0),
                                "end_line": data.get("end_line", 0),
                                "language": data.get("metadata", {}).get(
                                    "language", ""
                                ),
                                "type": data.get("metadata", {}).get("type", "content"),
                            },
                        ),
                        "_vector_data": data,
                    }
                )

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

        # Git repos: 3-tier fallback with staleness detection (old format + new format)
        if "git_blob_hash" in vector_data:
            # Try old format first, fall back to payload format
            # Use payload format if vector_data has zero values (new format uses payload)
            file_path = vector_data.get("file_path") or payload.get("path", "")
            start_line = (
                payload.get("line_start", 0)
                if vector_data.get("start_line", 1) == 0
                else vector_data.get("start_line", 0)
            )
            end_line = (
                payload.get("line_end", 0)
                if vector_data.get("end_line", 1) == 0
                else vector_data.get("end_line", 0)
            )
            stored_hash = vector_data.get("git_blob_hash") or payload.get(
                "git_blob_hash", ""
            )

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

        For filesystem backend, use model name as collection name.
        Compatible with QdrantClient interface.
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
            filter_conditions: Filter conditions (Qdrant-style filters)

        Returns:
            True if deletion successful
        """
        try:
            # Scroll through vectors with filter applied (scroll_points now uses Qdrant filter parser)
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

                # Extract file path
                file_path = data.get("payload", {}).get("path") or data.get(
                    "file_path", ""
                )

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

                sampled_vectors.append(
                    {
                        "id": data["id"],
                        "vector": data["vector"],
                        "file_path": data.get("file_path", ""),
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
