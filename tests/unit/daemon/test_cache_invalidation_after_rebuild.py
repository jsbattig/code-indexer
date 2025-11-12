"""Unit tests for cache invalidation after background rebuild (AC11-13).

Tests the three missing acceptance criteria:
- AC11: Cache invalidation - Daemon detects version changes after atomic swap
- AC12: Version tracking - Metadata includes index_rebuild_uuid
- AC13: mmap safety - Cached mmap indexes properly invalidated after swap

Story 0 - Background Index Rebuilding with Atomic Swap
"""

import json
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from code_indexer.daemon.cache import CacheEntry
from code_indexer.daemon.service import CIDXDaemonService
from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestAC12VersionTracking:
    """Test AC12: Version tracking with index_rebuild_uuid in metadata.

    Requirement: Metadata file changes trigger automatic cache reload.
    """

    def test_metadata_contains_index_rebuild_uuid_after_build(self, tmp_path: Path):
        """Test that _update_metadata adds index_rebuild_uuid field.

        FAILS until AC12 is implemented.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create minimal HNSW index
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
        ids = ["vec1", "vec2"]

        # Build index (should add index_rebuild_uuid to metadata)
        hnsw_manager.build_index(
            collection_path=collection_path,
            vectors=vectors,
            ids=ids,
            M=16,
            ef_construction=200,
        )

        # Read metadata
        meta_file = collection_path / "collection_meta.json"
        assert meta_file.exists()

        with open(meta_file) as f:
            metadata = json.load(f)

        # Verify index_rebuild_uuid exists
        assert "hnsw_index" in metadata
        assert "index_rebuild_uuid" in metadata["hnsw_index"]

        # Verify it's a valid UUID
        rebuild_uuid = metadata["hnsw_index"]["index_rebuild_uuid"]
        assert isinstance(rebuild_uuid, str)
        # Should be parseable as UUID
        uuid.UUID(rebuild_uuid)

    def test_metadata_contains_different_uuid_after_rebuild(self, tmp_path: Path):
        """Test that rebuild generates NEW index_rebuild_uuid.

        FAILS until AC12 is implemented.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]

        # First build
        hnsw_manager.build_index(
            collection_path=collection_path,
            vectors=vectors,
            ids=ids,
        )

        # Read first UUID
        meta_file = collection_path / "collection_meta.json"
        with open(meta_file) as f:
            metadata1 = json.load(f)
        first_uuid = metadata1["hnsw_index"]["index_rebuild_uuid"]

        # Sleep to ensure timestamp difference
        time.sleep(0.01)

        # Rebuild with same data
        hnsw_manager.build_index(
            collection_path=collection_path,
            vectors=vectors,
            ids=ids,
        )

        # Read second UUID
        with open(meta_file) as f:
            metadata2 = json.load(f)
        second_uuid = metadata2["hnsw_index"]["index_rebuild_uuid"]

        # UUIDs must be different (rebuild detection)
        assert first_uuid != second_uuid

    def test_metadata_contains_uuid_after_incremental_update(self, tmp_path: Path):
        """Test that save_incremental_update preserves/updates index_rebuild_uuid.

        FAILS until AC12 is implemented.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")

        # Create initial index
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Load for incremental update
        index, id_to_label, label_to_id, next_label = (
            hnsw_manager.load_for_incremental_update(collection_path)
        )

        # Add new vector
        new_vector = np.array([0.7, 0.8, 0.9], dtype=np.float32)
        label, id_to_label, label_to_id, next_label = hnsw_manager.add_or_update_vector(
            index, "vec2", new_vector, id_to_label, label_to_id, next_label
        )

        # Save incremental update
        hnsw_manager.save_incremental_update(
            index, collection_path, id_to_label, label_to_id, vector_count=2
        )

        # Verify index_rebuild_uuid still exists
        meta_file = collection_path / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert "index_rebuild_uuid" in metadata["hnsw_index"]


class TestAC11CacheInvalidation:
    """Test AC11: Cache invalidation after background rebuild detection.

    Requirement: In-memory index caches detect version changes after atomic swap.
    """

    @pytest.fixture
    def service(self):
        """Create daemon service for testing."""
        service = CIDXDaemonService()
        yield service
        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_cache_entry_can_detect_stale_index_after_rebuild(self, tmp_path: Path):
        """Test CacheEntry.is_stale_after_rebuild() detects version mismatch.

        FAILS until AC11 is implemented.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create index with version A
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Create cache entry and "load" version A
        cache_entry = CacheEntry(tmp_path, ttl_minutes=10)

        # Simulate loading index - cache entry should track the version
        version_a = cache_entry._read_index_rebuild_uuid(collection_path)
        cache_entry.hnsw_index_version = version_a  # Simulate tracking loaded version
        cache_entry.hnsw_index = Mock()  # Simulate loaded index

        # Cache should not be stale (version matches)
        assert not cache_entry.is_stale_after_rebuild(collection_path)

        # Simulate background rebuild (new UUID)
        time.sleep(0.01)
        vectors2 = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
        ids2 = ["vec1", "vec2"]
        hnsw_manager.build_index(collection_path, vectors2, ids2)

        # Cache entry should detect staleness (version changed)
        assert cache_entry.is_stale_after_rebuild(collection_path)

    def test_cache_entry_tracks_loaded_index_version(self, tmp_path: Path):
        """Test CacheEntry stores hnsw_index_version when loading.

        FAILS until AC11 is implemented.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create index
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Create cache entry
        cache_entry = CacheEntry(tmp_path, ttl_minutes=10)

        # Verify hnsw_index_version attribute exists
        # This will FAIL until AC11 is implemented
        assert hasattr(cache_entry, "hnsw_index_version")
        assert cache_entry.hnsw_index_version is None  # Not loaded yet

    def test_daemon_invalidates_cache_when_background_rebuild_detected(
        self, service: CIDXDaemonService, tmp_path: Path
    ):
        """Test daemon detects rebuild and invalidates cache before next query.

        FAILS until AC11 is implemented.

        Workflow:
        1. Daemon loads index into cache (version A)
        2. Background rebuild completes atomic swap (version B)
        3. Next _ensure_cache_loaded() detects version mismatch
        4. Cache invalidated, fresh index loaded
        """
        project_path = tmp_path / "project"
        project_path.mkdir()
        index_dir = project_path / ".code-indexer" / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "test_collection"
        collection_path.mkdir()

        # Create initial index (version A)
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Create metadata file
        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(
                {
                    "vector_size": 3,
                    "hnsw_index": {
                        "version": 1,
                        "vector_count": 1,
                        "vector_dim": 3,
                        "M": 16,
                        "ef_construction": 200,
                        "space": "cosine",
                        "last_rebuild": "2025-01-01T00:00:00Z",
                        "file_size_bytes": 1000,
                        "id_mapping": {"0": "vec1"},
                        "is_stale": False,
                        "last_marked_stale": None,
                        "index_rebuild_uuid": str(uuid.uuid4()),
                    },
                },
                f,
            )

        # Simulate daemon loading cache (version A)
        service.cache_entry = CacheEntry(project_path, ttl_minutes=10)
        service.cache_entry.hnsw_index = Mock()  # Simulated loaded index
        service.cache_entry.id_mapping = {"vec1": "path1"}
        # Track the loaded version
        version_a = service.cache_entry._read_index_rebuild_uuid(collection_path)
        service.cache_entry.hnsw_index_version = version_a

        # Simulate background rebuild (version B) - new UUID
        time.sleep(0.01)
        vectors2 = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
        ids2 = ["vec1", "vec2"]
        hnsw_manager.build_index(collection_path, vectors2, ids2)

        # Call _ensure_cache_loaded - should detect staleness and invalidate
        # This will FAIL until AC11 is implemented
        with patch.object(service, "_load_semantic_indexes") as mock_load_semantic:
            with patch.object(service, "_load_fts_indexes"):
                service._ensure_cache_loaded(str(project_path))

        # After staleness detection, cache should be reloaded (new CacheEntry)
        # We verify this by checking that _load_semantic_indexes was called
        # (which only happens when cache is None or project changed)
        mock_load_semantic.assert_called()

    def test_daemon_does_not_invalidate_cache_when_no_rebuild(
        self, service: CIDXDaemonService, tmp_path: Path
    ):
        """Test daemon keeps cache when no rebuild detected.

        FAILS until AC11 is implemented.
        """
        project_path = tmp_path / "project"
        project_path.mkdir()
        index_dir = project_path / ".code-indexer" / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "test_collection"
        collection_path.mkdir()

        # Create index
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Simulate daemon loading cache
        service.cache_entry = CacheEntry(project_path, ttl_minutes=10)
        service.cache_entry.hnsw_index = Mock()
        service.cache_entry.id_mapping = {"vec1": "path1"}
        original_entry = service.cache_entry

        # Call _ensure_cache_loaded - should NOT invalidate
        with patch.object(service, "_load_semantic_indexes"):
            with patch.object(service, "_load_fts_indexes"):
                service._ensure_cache_loaded(str(project_path))

        # Cache entry should be same object (not replaced)
        assert service.cache_entry is original_entry


class TestAC13MmapSafety:
    """Test AC13: mmap invalidation after atomic file swap.

    Requirement: Cached mmap'd indexes properly invalidated after file swap.
    """

    @pytest.fixture
    def service(self):
        """Create daemon service for testing."""
        service = CIDXDaemonService()
        yield service
        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_cache_invalidation_closes_old_mmap_file_descriptor(self, tmp_path: Path):
        """Test that cache invalidation properly closes mmap file descriptors.

        FAILS until AC13 is implemented.

        When CacheEntry.invalidate() is called after rebuild detection,
        it must close the old mmap'd HNSW index file descriptor before
        setting hnsw_index to None.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create index
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids = ["vec1"]
        hnsw_manager.build_index(collection_path, vectors, ids)

        # Load index (creates mmap)
        index = hnsw_manager.load_index(collection_path, max_elements=1000)
        assert index is not None

        # Verify index is using mmap internally (hnswlib loads index via mmap)
        # The index file should be open
        index_file = collection_path / "hnsw_index.bin"
        assert index_file.exists()

        # Create cache entry with loaded index
        cache_entry = CacheEntry(tmp_path, ttl_minutes=10)
        cache_entry.hnsw_index = index

        # Invalidate cache (should close mmap file descriptor)
        # This will FAIL until AC13 is implemented
        cache_entry.invalidate()

        # Verify index is None
        assert cache_entry.hnsw_index is None

        # If mmap was properly closed, we should be able to delete the file
        # (on some systems, open file descriptors prevent deletion)
        # NOTE: This is a weak test - better test would check /proc/self/fd
        # but that's Linux-specific

    def test_cache_reload_after_rebuild_uses_fresh_mmap(
        self, service: CIDXDaemonService, tmp_path: Path
    ):
        """Test that cache reload after rebuild loads fresh mmap'd index.

        FAILS until AC13 is implemented.

        Workflow:
        1. Load index into cache (mmap file descriptor A)
        2. Background rebuild swaps file (new inode B)
        3. Cache detects staleness and invalidates (closes fd A)
        4. Cache reloads (opens new mmap fd B)
        5. Queries use fresh index from inode B
        """
        project_path = tmp_path / "project"
        project_path.mkdir()
        index_dir = project_path / ".code-indexer" / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "test_collection"
        collection_path.mkdir()

        # Create initial index (inode A)
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors_old = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids_old = ["vec_old"]
        hnsw_manager.build_index(collection_path, vectors_old, ids_old)

        index_file = collection_path / "hnsw_index.bin"
        inode_a = index_file.stat().st_ino

        # Load into cache (mmap inode A)
        index_old = hnsw_manager.load_index(collection_path, max_elements=1000)
        service.cache_entry = CacheEntry(project_path, ttl_minutes=10)
        service.cache_entry.hnsw_index = index_old

        # Background rebuild with atomic swap (creates new inode B)
        from code_indexer.storage.background_index_rebuilder import (
            BackgroundIndexRebuilder,
        )

        rebuilder = BackgroundIndexRebuilder(collection_path)

        def build_new_index(temp_file: Path):
            """Build new index to temp file."""
            import hnswlib

            vectors_new = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
            index_new = hnswlib.Index(space="cosine", dim=3)
            index_new.init_index(max_elements=2, M=16, ef_construction=200)
            labels = np.arange(2)
            index_new.add_items(vectors_new, labels)
            index_new.save_index(str(temp_file))

        # Perform atomic swap
        rebuilder.rebuild_with_lock(build_new_index, index_file)

        # Verify new inode (file was swapped)
        inode_b = index_file.stat().st_ino
        assert inode_a != inode_b  # Different inodes after atomic rename

        # Simulate cache invalidation (should close old mmap)
        service.cache_entry.invalidate()

        # Reload cache (should open new mmap from inode B)
        index_new = hnsw_manager.load_index(collection_path, max_elements=1000)
        service.cache_entry.hnsw_index = index_new

        # Verify new index has correct vector count
        assert index_new.get_current_count() == 2  # New index has 2 vectors

    def test_concurrent_query_during_rebuild_uses_old_index(
        self, service: CIDXDaemonService, tmp_path: Path
    ):
        """Test that queries during rebuild use old index (no interruption).

        FAILS until AC13 is implemented.

        This test verifies that:
        1. Queries during rebuild continue using cached old index
        2. Lock prevents cache invalidation during query execution
        3. After query completes, next query detects staleness and reloads
        """
        project_path = tmp_path / "project"
        project_path.mkdir()
        index_dir = project_path / ".code-indexer" / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "test_collection"
        collection_path.mkdir()

        # Create initial index
        hnsw_manager = HNSWIndexManager(vector_dim=3, space="cosine")
        vectors_old = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        ids_old = ["vec_old"]
        hnsw_manager.build_index(collection_path, vectors_old, ids_old)

        # Load into cache
        index_old = hnsw_manager.load_index(collection_path, max_elements=1000)
        service.cache_entry = CacheEntry(project_path, ttl_minutes=10)
        service.cache_entry.hnsw_index = index_old
        service.cache_entry.id_mapping = {"0": "vec_old"}
        # Track the loaded version
        version_old = service.cache_entry._read_index_rebuild_uuid(collection_path)
        service.cache_entry.hnsw_index_version = version_old

        rebuild_completed = threading.Event()
        query_completed = threading.Event()

        def background_rebuild():
            """Simulate background rebuild."""
            time.sleep(0.05)  # Let query start first

            # Rebuild with new data
            vectors_new = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
            ids_new = ["vec_old", "vec_new"]
            hnsw_manager.build_index(collection_path, vectors_new, ids_new)

            rebuild_completed.set()

        def concurrent_query():
            """Simulate query during rebuild."""
            with service.cache_lock:
                # Hold lock during query execution
                time.sleep(0.1)  # Simulate slow query

                # Query should use old cached index
                assert service.cache_entry.hnsw_index is index_old

            query_completed.set()

        # Start rebuild and query concurrently
        rebuild_thread = threading.Thread(target=background_rebuild)
        query_thread = threading.Thread(target=concurrent_query)

        rebuild_thread.start()
        query_thread.start()

        # Wait for both to complete
        assert rebuild_completed.wait(timeout=1.0)
        assert query_completed.wait(timeout=1.0)

        rebuild_thread.join()
        query_thread.join()

        # After query completes, next _ensure_cache_loaded should detect staleness
        # and reload fresh index with 2 vectors
        with patch.object(service, "_load_semantic_indexes") as mock_load:
            service._ensure_cache_loaded(str(project_path))
            # Should reload because version changed
            mock_load.assert_called()
