"""Unit tests for count_points() performance optimization.

Tests the fast path that reads vector_count from collection_meta.json
instead of loading the full ID index.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.storage.id_index_manager import IDIndexManager


class TestCountPointsPerformance:
    """Test count_points() performance optimization."""

    @pytest.fixture
    def temp_index_dir(self, tmp_path: Path) -> Path:
        """Create temporary index directory."""
        index_dir = tmp_path / "test_index"
        index_dir.mkdir(parents=True, exist_ok=True)
        return index_dir

    @pytest.fixture
    def collection_with_metadata(self, temp_index_dir: Path) -> tuple[Path, int]:
        """Create collection directory with metadata file containing vector_count.

        Returns:
            Tuple of (collection_path, expected_count)
        """
        collection_path = temp_index_dir / "test_collection"
        collection_path.mkdir(parents=True, exist_ok=True)

        # Create metadata with vector_count
        expected_count = 399643
        metadata = {
            "vector_size": 1024,
            "vector_dim": 64,
            "quantization_range": [-1.0, 1.0],
            "hnsw_index": {
                "version": 1,
                "vector_count": expected_count,
                "vector_dim": 64,
                "M": 16,
                "ef_construction": 200,
                "space": "cosine",
                "last_rebuild": "2025-11-11T12:00:00",
            },
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f, indent=2)

        return collection_path, expected_count

    def test_count_points_uses_metadata_fast_path(
        self, temp_index_dir: Path, collection_with_metadata: tuple[Path, int]
    ):
        """Test that count_points() reads from metadata instead of loading ID index.

        This test verifies the FAST PATH:
        - Reads vector_count from collection_meta.json
        - Does NOT load the full ID index
        - Returns correct count
        """
        collection_path, expected_count = collection_with_metadata
        collection_name = collection_path.name

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Mock _load_id_index to ensure it's NOT called
        with patch.object(store, "_load_id_index") as mock_load_id_index:
            # Call count_points()
            actual_count = store.count_points(collection_name)

            # Verify count is correct
            assert (
                actual_count == expected_count
            ), f"Expected count {expected_count}, got {actual_count}"

            # Verify _load_id_index was NOT called (fast path used)
            mock_load_id_index.assert_not_called()

    def test_count_points_fallback_when_metadata_missing(self, temp_index_dir: Path):
        """Test that count_points() falls back to ID index when metadata missing.

        This test verifies the FALLBACK PATH:
        - collection_meta.json doesn't exist
        - Falls back to loading ID index
        - Returns correct count from ID index
        """
        collection_name = "test_collection"
        collection_path = temp_index_dir / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Create ID index file without metadata (using proper binary format)
        id_index = {
            "file1.py:0": Path("path/to/file1"),
            "file2.py:0": Path("path/to/file2"),
            "file3.py:0": Path("path/to/file3"),
        }

        id_index_manager = IDIndexManager()
        id_index_manager.save_index(collection_path, id_index)

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Call count_points() - should fall back to ID index
        actual_count = store.count_points(collection_name)

        # Verify count matches ID index length
        assert actual_count == len(
            id_index
        ), f"Expected count {len(id_index)}, got {actual_count}"

    def test_count_points_fallback_when_hnsw_index_missing(self, temp_index_dir: Path):
        """Test that count_points() falls back when hnsw_index field missing.

        This test verifies the FALLBACK PATH:
        - collection_meta.json exists but no hnsw_index field
        - Falls back to loading ID index
        - Returns correct count from ID index
        """
        collection_name = "test_collection"
        collection_path = temp_index_dir / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Create metadata WITHOUT hnsw_index field
        metadata = {
            "vector_size": 1024,
            "vector_dim": 64,
            "quantization_range": [-1.0, 1.0],
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        # Create ID index file (using proper binary format)
        id_index = {
            "file1.py:0": Path("path/to/file1"),
            "file2.py:0": Path("path/to/file2"),
        }

        id_index_manager = IDIndexManager()
        id_index_manager.save_index(collection_path, id_index)

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Call count_points() - should fall back to ID index
        actual_count = store.count_points(collection_name)

        # Verify count matches ID index length
        assert actual_count == len(
            id_index
        ), f"Expected count {len(id_index)}, got {actual_count}"

    def test_count_points_fallback_when_vector_count_missing(
        self, temp_index_dir: Path
    ):
        """Test that count_points() falls back when vector_count field missing.

        This test verifies the FALLBACK PATH:
        - collection_meta.json exists with hnsw_index but no vector_count
        - Falls back to loading ID index
        - Returns correct count from ID index
        """
        collection_name = "test_collection"
        collection_path = temp_index_dir / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Create metadata with hnsw_index but WITHOUT vector_count field
        metadata = {
            "vector_size": 1024,
            "vector_dim": 64,
            "quantization_range": [-1.0, 1.0],
            "hnsw_index": {
                "version": 1,
                "vector_dim": 64,
                "M": 16,
                "ef_construction": 200,
            },
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        # Create ID index file (using proper binary format)
        id_index = {
            "file1.py:0": Path("path/to/file1"),
            "file2.py:0": Path("path/to/file2"),
            "file3.py:0": Path("path/to/file3"),
        }

        id_index_manager = IDIndexManager()
        id_index_manager.save_index(collection_path, id_index)

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Call count_points() - should fall back to ID index
        actual_count = store.count_points(collection_name)

        # Verify count matches ID index length
        assert actual_count == len(
            id_index
        ), f"Expected count {len(id_index)}, got {actual_count}"

    def test_count_points_accuracy_matches_id_index(self, temp_index_dir: Path):
        """Test that fast path count exactly matches ID index count.

        This ensures the fast path is accurate and not just fast.
        """
        collection_name = "test_collection"
        collection_path = temp_index_dir / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Use a reasonable test count (not 399643 which is too slow for tests)
        test_count = 100

        # Create metadata with vector_count
        metadata = {
            "vector_size": 1024,
            "vector_dim": 64,
            "quantization_range": [-1.0, 1.0],
            "hnsw_index": {
                "version": 1,
                "vector_count": test_count,
                "vector_dim": 64,
                "M": 16,
                "ef_construction": 200,
            },
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        # Create ID index with SAME count as metadata (using proper binary format)
        id_index = {
            f"file{i}.py:0": Path(f"path/to/file{i}") for i in range(test_count)
        }

        id_index_manager = IDIndexManager()
        id_index_manager.save_index(collection_path, id_index)

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Get count from fast path (should use metadata)
        fast_count = store.count_points(collection_name)

        # Clear cache and force ID index load
        store._id_index.clear()
        store._id_index[collection_name] = store._load_id_index(collection_name)
        slow_count = len(store._id_index[collection_name])

        # Verify both methods return same count
        assert (
            fast_count == slow_count
        ), f"Fast path count {fast_count} != slow path count {slow_count}"
        assert fast_count == test_count, f"Count {fast_count} != expected {test_count}"

    def test_count_points_performance_improvement(
        self, temp_index_dir: Path, collection_with_metadata: tuple[Path, int]
    ):
        """Test that fast path is significantly faster than loading ID index.

        This is a smoke test - we verify the fast path is used, not actual timing.
        Actual performance testing should be done manually in real codebases.
        """
        collection_path, expected_count = collection_with_metadata
        collection_name = collection_path.name

        store = FilesystemVectorStore(base_path=temp_index_dir)

        # Mock _load_id_index to track calls
        original_load = store._load_id_index
        load_calls = []

        def tracked_load(name: str):
            load_calls.append(name)
            return original_load(name)

        with patch.object(store, "_load_id_index", side_effect=tracked_load):
            # First call - should use fast path
            count1 = store.count_points(collection_name)
            assert count1 == expected_count

            # Second call - should still use fast path (or cached)
            count2 = store.count_points(collection_name)
            assert count2 == expected_count

            # Verify _load_id_index was NOT called (fast path used)
            assert len(load_calls) == 0, (
                f"_load_id_index was called {len(load_calls)} times, "
                "expected 0 (fast path should be used)"
            )
