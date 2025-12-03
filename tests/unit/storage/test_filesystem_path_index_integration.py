"""Integration tests for PathIndex with FilesystemVectorStore.

Tests the integration of PathIndex into FilesystemVectorStore for duplicate prevention.
Story #540: Fix duplicate chunks bug.
"""

import pytest
import tempfile
import numpy as np
from pathlib import Path
from src.code_indexer.storage.filesystem_vector_store import (
    FilesystemVectorStore,
    PathIndex,
)


class TestPathIndexLoadSave:
    """Test _load_path_index and _save_path_index helper methods."""

    def test_load_path_index_when_file_exists(self):
        """_load_path_index should load existing path_index.bin file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)
            collection_path = base_path / "test_collection"

            # Create and save a path index manually
            path_index = PathIndex()
            path_index.add_point("src/auth.py", "point_a1")
            path_index.add_point("src/auth.py", "point_a2")
            path_index.add_point("src/utils.py", "point_u1")

            path_index_file = collection_path / "path_index.bin"
            path_index.save(path_index_file)

            # Load it using the helper method
            loaded_index = store._load_path_index("test_collection")

            # Verify contents
            assert loaded_index.get_point_ids("src/auth.py") == {"point_a1", "point_a2"}
            assert loaded_index.get_point_ids("src/utils.py") == {"point_u1"}

    def test_load_path_index_when_file_missing_returns_empty(self):
        """_load_path_index should return empty PathIndex when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection but no path_index.bin
            store.create_collection("test_collection", vector_size=1024)

            # Load should return empty index
            loaded_index = store._load_path_index("test_collection")

            assert isinstance(loaded_index, PathIndex)
            assert loaded_index._path_index == {}

    def test_save_path_index_creates_file(self):
        """_save_path_index should save path index to collection directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)

            # Create a path index
            path_index = PathIndex()
            path_index.add_point("src/auth.py", "point_a1")
            path_index.add_point("src/utils.py", "point_u1")

            # Save using helper method
            store._save_path_index("test_collection", path_index)

            # Verify file exists and is loadable
            collection_path = base_path / "test_collection"
            path_index_file = collection_path / "path_index.bin"
            assert path_index_file.exists()

            # Verify contents by loading directly
            loaded = PathIndex.load(path_index_file)
            assert loaded.get_point_ids("src/auth.py") == {"point_a1"}
            assert loaded.get_point_ids("src/utils.py") == {"point_u1"}

    def test_path_index_loaded_in_begin_indexing(self):
        """begin_indexing should load PathIndex for the collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection and save a path index
            store.create_collection("test_collection", vector_size=1024)
            collection_path = base_path / "test_collection"

            path_index = PathIndex()
            path_index.add_point("src/auth.py", "point_a1")
            path_index.save(collection_path / "path_index.bin")

            # Call begin_indexing
            store.begin_indexing("test_collection")

            # Verify path index was loaded into memory
            assert "test_collection" in store._path_indexes
            loaded_index = store._path_indexes["test_collection"]
            assert loaded_index.get_point_ids("src/auth.py") == {"point_a1"}

    def test_path_index_saved_in_end_indexing(self):
        """end_indexing should save PathIndex to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)

            # Begin indexing (loads empty path index)
            store.begin_indexing("test_collection")

            # Modify the path index
            store._path_indexes["test_collection"].add_point("src/auth.py", "point_a1")

            # End indexing (should save)
            store.end_indexing("test_collection")

            # Verify file was saved
            collection_path = base_path / "test_collection"
            path_index_file = collection_path / "path_index.bin"
            assert path_index_file.exists()

            # Verify contents
            loaded = PathIndex.load(path_index_file)
            assert loaded.get_point_ids("src/auth.py") == {"point_a1"}


class TestPreUpsertCleanup:
    """Test pre-upsert cleanup logic that prevents duplicates."""

    def test_upsert_new_file_adds_to_path_index(self):
        """Upserting points for a new file should add to path index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)

            # Begin indexing
            store.begin_indexing("test_collection")

            # Upsert points for a new file
            points = [
                {
                    "id": "auth_chunk_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                },
                {
                    "id": "auth_chunk_1",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 1},
                },
            ]

            store.upsert_points("test_collection", points)

            # Verify path index was updated
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/auth.py")
            assert point_ids == {"auth_chunk_0", "auth_chunk_1"}

    def test_upsert_modified_file_removes_old_vectors(self):
        """Upserting points for a modified file should remove old vectors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # First upsert: original file with 3 chunks
            old_points = [
                {
                    "id": f"auth_old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": i},
                }
                for i in range(3)
            ]
            store.upsert_points("test_collection", old_points)

            # Verify old vectors exist
            collection_path = base_path / "test_collection"
            old_vector_files = list(collection_path.rglob("vector_auth_old_*.json"))
            assert len(old_vector_files) == 3

            # Second upsert: modified file with NEW point_ids (simulates content change)
            new_points = [
                {
                    "id": f"auth_new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": i},
                }
                for i in range(3)
            ]
            store.upsert_points("test_collection", new_points)

            # Verify old vector files were deleted
            old_vector_files_after = list(
                collection_path.rglob("vector_auth_old_*.json")
            )
            assert len(old_vector_files_after) == 0

            # Verify new vectors exist
            new_vector_files = list(collection_path.rglob("vector_auth_new_*.json"))
            assert len(new_vector_files) == 3

            # Verify path index only contains new point_ids
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/auth.py")
            assert point_ids == {"auth_new_0", "auth_new_1", "auth_new_2"}

    def test_upsert_file_shrinks_removes_extra_chunks(self):
        """Upserting fewer chunks should remove extra old chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # First upsert: 5 chunks
            old_points = [
                {
                    "id": f"utils_old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": i},
                }
                for i in range(5)
            ]
            store.upsert_points("test_collection", old_points)

            # Second upsert: only 2 chunks (file shrunk)
            new_points = [
                {
                    "id": f"utils_new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": i},
                }
                for i in range(2)
            ]
            store.upsert_points("test_collection", new_points)

            # Verify all 5 old vectors deleted
            collection_path = base_path / "test_collection"
            old_vector_files = list(collection_path.rglob("vector_utils_old_*.json"))
            assert len(old_vector_files) == 0

            # Verify only 2 new vectors exist
            new_vector_files = list(collection_path.rglob("vector_utils_new_*.json"))
            assert len(new_vector_files) == 2

            # Verify path index
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/utils.py")
            assert point_ids == {"utils_new_0", "utils_new_1"}

    def test_upsert_file_grows_adds_new_chunks(self):
        """Upserting more chunks should add new chunks and remove old ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # First upsert: 2 chunks
            old_points = [
                {
                    "id": f"config_old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/config.py", "chunk_index": i},
                }
                for i in range(2)
            ]
            store.upsert_points("test_collection", old_points)

            # Second upsert: 4 chunks (file grew)
            new_points = [
                {
                    "id": f"config_new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/config.py", "chunk_index": i},
                }
                for i in range(4)
            ]
            store.upsert_points("test_collection", new_points)

            # Verify all 2 old vectors deleted
            collection_path = base_path / "test_collection"
            old_vector_files = list(collection_path.rglob("vector_config_old_*.json"))
            assert len(old_vector_files) == 0

            # Verify 4 new vectors exist
            new_vector_files = list(collection_path.rglob("vector_config_new_*.json"))
            assert len(new_vector_files) == 4

            # Verify path index
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/config.py")
            assert point_ids == {
                "config_new_0",
                "config_new_1",
                "config_new_2",
                "config_new_3",
            }

    def test_cleanup_removes_from_id_index(self):
        """Cleanup should remove old point_ids from id_index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # First upsert
            old_points = [
                {
                    "id": "auth_old_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", old_points)

            # Verify old point in id_index
            assert "auth_old_0" in store._id_index["test_collection"]

            # Second upsert with new point_id
            new_points = [
                {
                    "id": "auth_new_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", new_points)

            # Verify old point removed from id_index
            assert "auth_old_0" not in store._id_index["test_collection"]
            assert "auth_new_0" in store._id_index["test_collection"]

    def test_cleanup_tracks_deletions_for_hnsw(self):
        """Cleanup should track deletions in _indexing_session_changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # First upsert
            old_points = [
                {
                    "id": "auth_old_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", old_points)

            # Clear change tracking to isolate second upsert
            store._indexing_session_changes["test_collection"]["deleted"].clear()

            # Second upsert (should trigger cleanup)
            new_points = [
                {
                    "id": "auth_new_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", new_points)

            # Verify deletion was tracked
            deleted = store._indexing_session_changes["test_collection"]["deleted"]
            assert "auth_old_0" in deleted


class TestDeletePointsPathIndexIntegration:
    """Test that delete_points maintains path index consistency."""

    def test_delete_points_removes_from_path_index(self):
        """delete_points should remove point_ids from path index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Upsert some points
            points = [
                {
                    "id": f"auth_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": i},
                }
                for i in range(3)
            ]
            store.upsert_points("test_collection", points)

            # Verify path index has all points
            path_index = store._path_indexes["test_collection"]
            assert path_index.get_point_ids("src/auth.py") == {
                "auth_0",
                "auth_1",
                "auth_2",
            }

            # Delete one point
            store.delete_points("test_collection", ["auth_1"])

            # Verify point removed from path index
            assert path_index.get_point_ids("src/auth.py") == {"auth_0", "auth_2"}

    def test_delete_all_points_for_file_removes_file_entry(self):
        """Deleting all points for a file should remove file from path index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Upsert points
            points = [
                {
                    "id": "auth_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", points)

            # Delete the only point
            store.delete_points("test_collection", ["auth_0"])

            # Verify file entry removed from path index
            path_index = store._path_indexes["test_collection"]
            assert "src/auth.py" not in path_index._path_index


class TestWatchModePathIndexIntegration:
    """Test PathIndex integration in watch mode (upsert without begin_indexing).

    CRITICAL BUG #1: In watch mode, upsert_points can be called WITHOUT begin_indexing,
    meaning path_index is never loaded from disk. This breaks duplicate cleanup.

    Story #540 Code Review Fix.
    """

    def test_watch_mode_upsert_loads_path_index_lazily(self):
        """Watch mode upsert should lazy-load path index if not already loaded.

        Simulates watch mode scenario:
        1. Index some files normally (with begin/end indexing)
        2. Call upsert_points WITHOUT begin_indexing (watch mode)
        3. Verify path index was loaded lazily from disk
        4. Verify duplicate cleanup works correctly
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            # Create collection
            store.create_collection("test_collection", vector_size=1024)

            # FIRST INDEXING SESSION: Normal indexing with begin/end
            store.begin_indexing("test_collection")

            # Index file with 3 chunks
            old_points = [
                {
                    "id": f"auth_old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": i},
                }
                for i in range(3)
            ]
            store.upsert_points("test_collection", old_points)

            # End indexing (saves path index to disk)
            store.end_indexing("test_collection")

            # CRITICAL: Clear in-memory path index (simulates daemon restart or watch mode)
            store._path_indexes.clear()

            # WATCH MODE: Upsert WITHOUT begin_indexing
            # This simulates file change detected by watch mode
            new_points = [
                {
                    "id": f"auth_new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": i},
                }
                for i in range(3)
            ]

            # This should:
            # 1. Lazy-load path index from disk
            # 2. Cleanup old vectors (auth_old_0, auth_old_1, auth_old_2)
            # 3. Insert new vectors (auth_new_0, auth_new_1, auth_new_2)
            store.upsert_points("test_collection", new_points, watch_mode=True)

            # VERIFICATION 1: Path index was loaded
            assert "test_collection" in store._path_indexes
            path_index = store._path_indexes["test_collection"]

            # VERIFICATION 2: Path index only contains NEW point_ids (old ones cleaned up)
            point_ids = path_index.get_point_ids("src/auth.py")
            assert point_ids == {"auth_new_0", "auth_new_1", "auth_new_2"}

            # VERIFICATION 3: Old vector files were deleted from disk
            collection_path = base_path / "test_collection"
            old_vector_files = list(collection_path.rglob("vector_auth_old_*.json"))
            assert len(old_vector_files) == 0, "Old vectors should be deleted"

            # VERIFICATION 4: New vector files exist
            new_vector_files = list(collection_path.rglob("vector_auth_new_*.json"))
            assert len(new_vector_files) == 3, "New vectors should exist"

    def test_watch_mode_upsert_file_shrinks_with_lazy_load(self):
        """Watch mode should handle file shrinking (fewer chunks) with lazy-loaded path index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)

            # Initial indexing: 5 chunks
            store.begin_indexing("test_collection")
            old_points = [
                {
                    "id": f"utils_old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": i},
                }
                for i in range(5)
            ]
            store.upsert_points("test_collection", old_points)
            store.end_indexing("test_collection")

            # Clear in-memory path index
            store._path_indexes.clear()

            # Watch mode: File shrunk to 2 chunks
            new_points = [
                {
                    "id": f"utils_new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": i},
                }
                for i in range(2)
            ]
            store.upsert_points("test_collection", new_points, watch_mode=True)

            # Verify all 5 old chunks deleted
            collection_path = base_path / "test_collection"
            old_vector_files = list(collection_path.rglob("vector_utils_old_*.json"))
            assert len(old_vector_files) == 0

            # Verify only 2 new chunks exist
            new_vector_files = list(collection_path.rglob("vector_utils_new_*.json"))
            assert len(new_vector_files) == 2

            # Verify path index
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/utils.py")
            assert point_ids == {"utils_new_0", "utils_new_1"}

    def test_watch_mode_multiple_files_with_lazy_load(self):
        """Watch mode should handle multiple file updates with lazy-loaded path index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)

            # Initial indexing: auth.py (2 chunks), utils.py (3 chunks)
            store.begin_indexing("test_collection")
            old_points = [
                {
                    "id": "auth_old_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                },
                {
                    "id": "auth_old_1",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 1},
                },
                {
                    "id": "utils_old_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": 0},
                },
                {
                    "id": "utils_old_1",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": 1},
                },
                {
                    "id": "utils_old_2",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": 2},
                },
            ]
            store.upsert_points("test_collection", old_points)
            store.end_indexing("test_collection")

            # Clear in-memory path index
            store._path_indexes.clear()

            # Watch mode: Update only auth.py
            new_auth_points = [
                {
                    "id": "auth_new_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                },
                {
                    "id": "auth_new_1",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 1},
                },
            ]
            store.upsert_points("test_collection", new_auth_points, watch_mode=True)

            # Verify auth.py old vectors deleted
            collection_path = base_path / "test_collection"
            old_auth_files = list(collection_path.rglob("vector_auth_old_*.json"))
            assert len(old_auth_files) == 0

            # Verify auth.py new vectors exist
            new_auth_files = list(collection_path.rglob("vector_auth_new_*.json"))
            assert len(new_auth_files) == 2

            # Verify utils.py old vectors STILL exist (not touched)
            old_utils_files = list(collection_path.rglob("vector_utils_old_*.json"))
            assert len(old_utils_files) == 3

            # Verify path index
            path_index = store._path_indexes["test_collection"]
            auth_ids = path_index.get_point_ids("src/auth.py")
            utils_ids = path_index.get_point_ids("src/utils.py")

            assert auth_ids == {"auth_new_0", "auth_new_1"}
            assert utils_ids == {"utils_old_0", "utils_old_1", "utils_old_2"}
