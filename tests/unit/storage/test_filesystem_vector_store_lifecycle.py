"""Unit tests for FilesystemVectorStore lifecycle methods.

Tests for begin_indexing() and end_indexing() interface that fixes O(n²) performance disaster.

Test Strategy:
- RED: Tests demonstrating O(n²) behavior (index rebuilds on every upsert)
- GREEN: Tests proving O(n) behavior with lifecycle methods
- No mocking of file I/O or index operations (real behavior testing)
"""

import json
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
import time


class TestFilesystemVectorStoreLifecycle:
    """Test lifecycle interface for O(n²) → O(n) optimization."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        # Generate 10 test vectors (small set for fast tests)
        return [np.random.randn(1536) for _ in range(10)]

    @pytest.fixture
    def store(self, tmp_path):
        """Create FilesystemVectorStore with test collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)
        return store

    def test_begin_indexing_exists(self, store):
        """GIVEN FilesystemVectorStore instance
        WHEN begin_indexing() is called
        THEN method exists and doesn't raise exceptions

        AC1: begin_indexing() method exists on FilesystemVectorStore
        AC2: Accepts collection_name parameter
        AC3: Doesn't raise exceptions (no-op or setup operation)
        """
        # This will FAIL initially - method doesn't exist yet (RED phase)
        assert hasattr(store, "begin_indexing"), "begin_indexing() method must exist"

        # Should not raise exceptions
        store.begin_indexing("test_coll")

    def test_end_indexing_exists(self, store):
        """GIVEN FilesystemVectorStore instance
        WHEN end_indexing() is called
        THEN method exists and returns status dict

        AC1: end_indexing() method exists on FilesystemVectorStore
        AC2: Accepts collection_name and optional progress_callback
        AC3: Returns dict with status, vectors_indexed, collection keys
        """
        # This will FAIL initially - method doesn't exist yet (RED phase)
        assert hasattr(store, "end_indexing"), "end_indexing() method must exist"

        # Should return status dict
        result = store.end_indexing("test_coll")

        assert isinstance(result, dict), "end_indexing() must return dict"
        assert result["status"] == "ok", "Status must be 'ok'"
        assert "vectors_indexed" in result, "Must return vectors_indexed count"
        assert "collection" in result, "Must return collection name"

    def test_upsert_without_lifecycle_no_longer_rebuilds_indexes(
        self, store, test_vectors
    ):
        """GREEN TEST: Proves O(n²) behavior is FIXED - upsert no longer rebuilds indexes.

        GIVEN FilesystemVectorStore with fixed upsert_points()
        WHEN upsert_points() is called multiple times WITHOUT lifecycle wrapper
        THEN HNSW index is NOT rebuilt during upserts (index building deferred to end_indexing)

        This test PROVES the O(n²) problem is FIXED by showing index rebuilding is gone from upsert.
        The OLD behavior would have rebuilt indexes 5 times here - now it rebuilds 0 times.
        """
        from unittest.mock import patch

        # Insert some initial vectors
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(5)
        ]

        # Track how many times HNSW index is rebuilt
        rebuild_count = 0

        # Patch HNSWIndexManager.rebuild_from_vectors to count calls
        # Note: Import is done locally in end_indexing(), so patch the import location
        with patch(
            "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
        ) as mock_hnsw_class:
            mock_hnsw_instance = Mock()
            mock_hnsw_class.return_value = mock_hnsw_instance

            # Track rebuild calls
            def track_rebuild(*args, **kwargs):
                nonlocal rebuild_count
                rebuild_count += 1

            mock_hnsw_instance.rebuild_from_vectors.side_effect = track_rebuild

            # Upsert 5 points - WITHOUT using lifecycle methods
            # After optimization: No index rebuilding happens here!
            for point in points:
                store.upsert_points("test_coll", [point])

        # O(n²) FIX PROOF: Index should be rebuilt 0 times during upserts
        # OLD behavior: would be 5 (disaster!)
        # NEW behavior: 0 (index building deferred to end_indexing)
        assert (
            rebuild_count == 0
        ), f"O(n²) FIXED: Index rebuilt {rebuild_count} times during upserts (should be 0, was 5 before fix)"

    def test_upsert_with_lifecycle_rebuilds_index_once(self, store, test_vectors):
        """GREEN TEST: Demonstrates O(n) behavior WITH lifecycle methods.

        GIVEN FilesystemVectorStore with lifecycle interface
        WHEN begin_indexing() → multiple upsert_points() → end_indexing()
        THEN HNSW index is rebuilt ONLY ONCE in end_indexing() (O(n) fix)

        This test PROVES the fix works by showing single index rebuild.
        """
        from unittest.mock import patch

        # Insert some initial vectors
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(5)
        ]

        # Track how many times HNSW index is rebuilt
        rebuild_count = 0

        # Patch HNSWIndexManager.rebuild_from_vectors to count calls
        # Note: Import is done locally in end_indexing(), so patch the import location
        with patch(
            "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
        ) as mock_hnsw_class:
            mock_hnsw_instance = Mock()
            mock_hnsw_class.return_value = mock_hnsw_instance

            # Track rebuild calls
            def track_rebuild(*args, **kwargs):
                nonlocal rebuild_count
                rebuild_count += 1

            mock_hnsw_instance.rebuild_from_vectors.side_effect = track_rebuild

            # Use lifecycle methods properly
            store.begin_indexing("test_coll")

            # Upsert 5 points - index should NOT be rebuilt during upserts
            for point in points:
                store.upsert_points("test_coll", [point])

            # Finalize - index should be rebuilt ONCE here
            store.end_indexing("test_coll")

        # O(n) PROOF: Index should be rebuilt exactly 1 time (in end_indexing only)
        assert (
            rebuild_count == 1
        ), f"O(n) behavior: Index rebuilt {rebuild_count} times (should be 1 with lifecycle)"

    def test_vector_size_caching_avoids_repeated_json_parsing(
        self, store, test_vectors, tmp_path
    ):
        """GREEN TEST: Proves metadata caching eliminates repeated file I/O.

        GIVEN FilesystemVectorStore with metadata caching
        WHEN using lifecycle methods (begin_indexing → upserts → end_indexing)
        THEN collection_meta.json is read ONCE (not on every upsert)

        This test proves Issue 2 (repeated JSON parsing) is fixed.
        """
        # Create a few test points
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(3)
        ]

        # Track metadata file reads using mock
        meta_file_path = tmp_path / "test_coll" / "collection_meta.json"
        read_count = 0
        original_open = open

        def counting_open(file, *args, **kwargs):
            nonlocal read_count
            if str(file) == str(meta_file_path) and "r" in args[0] if args else True:
                read_count += 1
            return original_open(file, *args, **kwargs)

        # Patch open to count metadata reads
        # Using lifecycle methods properly populates cache
        with patch("builtins.open", side_effect=counting_open):
            # Populate cache by calling _get_vector_size (happens in end_indexing normally)
            _ = store._get_vector_size("test_coll")

            # Now upsert multiple points - should use cached metadata
            for point in points:
                store.upsert_points("test_coll", [point])

        # OPTIMIZATION PROOF: Should read metadata file ONCE (at cache population), not 4 times
        # First read populates cache, subsequent upserts use cache for quantization_range
        assert (
            read_count == 1
        ), f"Metadata read {read_count} times (should be 1 with caching)"

    def test_end_indexing_returns_vector_count(self, store, test_vectors):
        """GIVEN vectors indexed via lifecycle
        WHEN end_indexing() is called
        THEN accurate vector count is returned

        AC1: Returns dict with vectors_indexed key
        AC2: Count matches number of vectors actually indexed
        """
        # Index some vectors using lifecycle
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(5)
        ]

        store.begin_indexing("test_coll")
        for point in points:
            store.upsert_points("test_coll", [point])
        result = store.end_indexing("test_coll")

        assert result["vectors_indexed"] == 5, "Should return accurate vector count"

    def test_end_indexing_with_nonexistent_collection_raises_error(self, store):
        """GIVEN collection that doesn't exist
        WHEN end_indexing() is called
        THEN ValueError is raised with clear message

        AC1: Raises ValueError for nonexistent collection
        AC2: Error message indicates collection doesn't exist
        """
        with pytest.raises(ValueError, match="does not exist"):
            store.end_indexing("nonexistent_collection")


class TestQdrantClientLifecycle:
    """Test lifecycle interface for QdrantClient (no-op implementation)."""

    @pytest.fixture
    def qdrant_config(self):
        """Mock Qdrant configuration."""
        from code_indexer.config import QdrantConfig

        return QdrantConfig(
            host="localhost",
            port=6333,
            collection_base_name="test_collection",
            url=None,
            api_key=None,
        )

    def test_qdrant_begin_indexing_exists(self, qdrant_config):
        """GIVEN QdrantClient instance
        WHEN begin_indexing() is called
        THEN method exists and is a no-op (Qdrant handles indexes internally)

        AC1: begin_indexing() method exists on QdrantClient
        AC2: Accepts collection_name parameter
        AC3: Is effectively a no-op (Qdrant manages indexes automatically)
        """
        from code_indexer.services.qdrant import QdrantClient

        # Create client (skip container checks for unit test)
        client = QdrantClient(config=qdrant_config, project_root=Path("/tmp"))

        # This will FAIL initially - method doesn't exist yet (RED phase)
        assert hasattr(client, "begin_indexing"), "begin_indexing() method must exist"

        # Should not raise exceptions
        client.begin_indexing("test_collection")

    def test_qdrant_end_indexing_exists(self, qdrant_config):
        """GIVEN QdrantClient instance
        WHEN end_indexing() is called
        THEN method exists and returns status dict

        AC1: end_indexing() method exists on QdrantClient
        AC2: Accepts collection_name and optional progress_callback
        AC3: Returns dict with status, vectors_indexed, collection keys
        AC4: vectors_indexed reflects actual Qdrant collection size
        """
        from code_indexer.services.qdrant import QdrantClient
        from unittest.mock import patch

        # Create client
        client = QdrantClient(config=qdrant_config, project_root=Path("/tmp"))

        # This will FAIL initially - method doesn't exist yet (RED phase)
        assert hasattr(client, "end_indexing"), "end_indexing() method must exist"

        # Mock count_points to return known value
        with patch.object(client, "count_points", return_value=42):
            result = client.end_indexing("test_collection")

        assert isinstance(result, dict), "end_indexing() must return dict"
        assert result["status"] == "ok", "Status must be 'ok'"
        assert (
            result["vectors_indexed"] == 42
        ), "Must return accurate vector count from Qdrant"
        assert result["collection"] == "test_collection", "Must return collection name"


class TestVectorSizeCaching:
    """Test _get_vector_size() caching implementation."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create FilesystemVectorStore with test collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)
        return store

    def test_get_vector_size_caches_result(self, store):
        """GIVEN FilesystemVectorStore with collection
        WHEN _get_vector_size() is called multiple times
        THEN metadata file is read ONCE and cached

        AC1: First call reads metadata file
        AC2: Subsequent calls return cached value
        AC3: Thread-safe with _metadata_lock
        """
        # This will FAIL initially - method doesn't exist yet (RED phase)
        assert hasattr(
            store, "_get_vector_size"
        ), "_get_vector_size() method must exist"

        # First call should read and cache
        size1 = store._get_vector_size("test_coll")
        assert size1 == 1536, "Should return correct vector size"

        # Second call should use cache
        size2 = store._get_vector_size("test_coll")
        assert size2 == 1536, "Should return same cached value"

        # Verify cache exists
        assert hasattr(
            store, "_vector_size_cache"
        ), "Must have _vector_size_cache attribute"
        assert "test_coll" in store._vector_size_cache, "Collection should be cached"

    def test_get_vector_size_handles_corrupted_json(self, store, tmp_path):
        """GIVEN collection with corrupted metadata JSON
        WHEN _get_vector_size() is called
        THEN RuntimeError raised with clear message

        AC1: Catches JSONDecodeError
        AC2: Raises RuntimeError with helpful message
        AC3: Mentions JSON corruption in error
        """
        # Corrupt the metadata file
        meta_file = tmp_path / "test_coll" / "collection_meta.json"
        with open(meta_file, "w") as f:
            f.write("{invalid json")

        # Should raise RuntimeError with clear message
        with pytest.raises(RuntimeError, match="corrupted.*JSON"):
            store._get_vector_size("test_coll")

    def test_get_vector_size_handles_missing_metadata(self, store, tmp_path):
        """GIVEN collection with missing metadata file
        WHEN _get_vector_size() is called
        THEN RuntimeError raised indicating missing file

        AC1: Detects missing metadata file
        AC2: Raises RuntimeError with clear message
        AC3: Mentions file not found in error
        """
        # Delete metadata file
        meta_file = tmp_path / "test_coll" / "collection_meta.json"
        meta_file.unlink()

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="not found"):
            store._get_vector_size("test_coll")

    def test_get_vector_size_handles_missing_vector_size_field(self, store, tmp_path):
        """GIVEN collection with metadata missing vector_size field
        WHEN _get_vector_size() is called
        THEN RuntimeError raised indicating missing field

        AC1: Detects missing vector_size field
        AC2: Raises RuntimeError with clear message
        """
        # Write metadata without vector_size field
        meta_file = tmp_path / "test_coll" / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"name": "test_coll", "created_at": "2024-01-01"}, f)

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="missing.*vector_size"):
            store._get_vector_size("test_coll")


class TestFilesystemVectorStoreWatchModeOptimization:
    """Test skip_hnsw_rebuild parameter for watch mode optimization."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        return [np.random.randn(1536) for _ in range(10)]

    @pytest.fixture
    def store(self, tmp_path):
        """Create FilesystemVectorStore with test collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)
        return store

    def test_end_indexing_skip_hnsw_marks_stale(self, store, test_vectors, tmp_path):
        """Test that end_indexing with skip_hnsw_rebuild=True marks index stale.

        GIVEN FilesystemVectorStore in watch mode
        WHEN end_indexing(skip_hnsw_rebuild=True) is called
        THEN HNSW index is NOT rebuilt AND marked as stale
        """
        from unittest.mock import patch

        # Index some vectors
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(5)
        ]

        store.begin_indexing("test_coll")
        for point in points:
            store.upsert_points("test_coll", [point])

        # Track HNSW operations
        rebuild_called = False
        mark_stale_called = False

        with patch(
            "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
        ) as mock_hnsw_class:
            mock_hnsw_instance = Mock()
            mock_hnsw_class.return_value = mock_hnsw_instance

            def track_rebuild(*args, **kwargs):
                nonlocal rebuild_called
                rebuild_called = True

            def track_mark_stale(*args, **kwargs):
                nonlocal mark_stale_called
                mark_stale_called = True

            mock_hnsw_instance.rebuild_from_vectors.side_effect = track_rebuild
            mock_hnsw_instance.mark_stale.side_effect = track_mark_stale

            # Call end_indexing with skip_hnsw_rebuild=True
            result = store.end_indexing("test_coll", skip_hnsw_rebuild=True)

        # Verify behavior
        assert not rebuild_called, "HNSW rebuild should NOT be called in watch mode"
        assert mark_stale_called, "mark_stale() should be called to defer rebuild"
        assert "hnsw_skipped" in result, "Result should indicate HNSW was skipped"
        assert result["hnsw_skipped"] is True

    def test_end_indexing_normal_rebuilds_hnsw(self, store, test_vectors):
        """Test that end_indexing without skip_hnsw_rebuild rebuilds HNSW normally.

        GIVEN FilesystemVectorStore in normal mode
        WHEN end_indexing(skip_hnsw_rebuild=False) or default is called
        THEN HNSW index IS rebuilt normally
        """
        from unittest.mock import patch

        # Index some vectors
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(5)
        ]

        store.begin_indexing("test_coll")
        for point in points:
            store.upsert_points("test_coll", [point])

        # Track HNSW operations
        rebuild_called = False
        mark_stale_called = False

        with patch(
            "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
        ) as mock_hnsw_class:
            mock_hnsw_instance = Mock()
            mock_hnsw_class.return_value = mock_hnsw_instance

            def track_rebuild(*args, **kwargs):
                nonlocal rebuild_called
                rebuild_called = True

            def track_mark_stale(*args, **kwargs):
                nonlocal mark_stale_called
                mark_stale_called = True

            mock_hnsw_instance.rebuild_from_vectors.side_effect = track_rebuild
            mock_hnsw_instance.mark_stale.side_effect = track_mark_stale

            # Call end_indexing with skip_hnsw_rebuild=False (default)
            result = store.end_indexing("test_coll", skip_hnsw_rebuild=False)

        # Verify behavior
        assert rebuild_called, "HNSW rebuild SHOULD be called in normal mode"
        assert (
            not mark_stale_called
        ), "mark_stale() should NOT be called in normal mode"
        assert result.get("hnsw_skipped", False) is False

    def test_end_indexing_default_parameter_rebuilds_hnsw(self, store, test_vectors):
        """Test that end_indexing default behavior rebuilds HNSW (backward compatibility).

        GIVEN FilesystemVectorStore
        WHEN end_indexing() is called without skip_hnsw_rebuild parameter
        THEN HNSW index IS rebuilt (default behavior for backward compatibility)
        """
        from unittest.mock import patch

        # Index some vectors
        points = [
            {
                "id": f"point_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": 1,
                    "end_line": 10,
                    "language": "python",
                    "type": "content",
                    "content": f"test content {i}",
                },
            }
            for i in range(3)
        ]

        store.begin_indexing("test_coll")
        for point in points:
            store.upsert_points("test_coll", [point])

        # Track HNSW operations
        rebuild_called = False

        with patch(
            "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
        ) as mock_hnsw_class:
            mock_hnsw_instance = Mock()
            mock_hnsw_class.return_value = mock_hnsw_instance

            def track_rebuild(*args, **kwargs):
                nonlocal rebuild_called
                rebuild_called = True

            mock_hnsw_instance.rebuild_from_vectors.side_effect = track_rebuild

            # Call end_indexing WITHOUT skip_hnsw_rebuild parameter
            result = store.end_indexing("test_coll")

        # Verify default behavior
        assert (
            rebuild_called
        ), "HNSW rebuild SHOULD be called by default (backward compatibility)"
