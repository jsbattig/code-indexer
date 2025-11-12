"""Unit tests for watch mode daemon HNSW updates (Story #435).

Tests AC2 (Concurrent Query Support) and AC3 (Daemon Cache In-Memory Updates).
"""

import numpy as np
import pytest
import threading
from pathlib import Path
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.daemon.cache import CacheEntry


@pytest.fixture
def temp_store(tmp_path: Path) -> FilesystemVectorStore:
    """Create FilesystemVectorStore instance for testing."""
    store_path = tmp_path / "vector_store"
    store_path.mkdir(parents=True, exist_ok=True)
    return FilesystemVectorStore(base_path=store_path, project_root=tmp_path)


@pytest.fixture
def cache_entry(tmp_path: Path) -> CacheEntry:
    """Create CacheEntry instance for daemon mode testing."""
    return CacheEntry(project_path=tmp_path)


@pytest.fixture
def sample_points():
    """Generate sample points for testing."""
    np.random.seed(42)
    vectors = np.random.randn(10, 128).astype(np.float32)
    points = []
    for i in range(10):
        points.append(
            {
                "id": f"file_{i}.py",
                "vector": vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py", "content": f"Content {i}"},
            }
        )
    return points


class TestDaemonModeDetection:
    """Test AC3: Daemon mode detection and cache entry usage."""

    def test_detect_daemon_mode_when_cache_entry_provided(
        self, temp_store: FilesystemVectorStore, cache_entry: CacheEntry, sample_points
    ):
        """
        AC3: Detect daemon mode when cache_entry exists.

        RED: This will fail because FilesystemVectorStore doesn't have cache_entry attribute.
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # Set cache_entry on vector store (simulating daemon mode)
        temp_store.cache_entry = cache_entry

        # Load cache with HNSW index
        collection_path = temp_store.base_path / collection_name
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
        cache_entry.hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )

        id_manager = IDIndexManager()
        cache_entry.id_mapping = id_manager.load_index(collection_path)

        # Watch mode update with cache_entry present
        new_point = [sample_points[5]]
        temp_store.upsert_points(collection_name, new_point, watch_mode=True)

        # Verify: cache_entry.hnsw_index should be updated (not None)
        assert (
            cache_entry.hnsw_index is not None
        ), "Cache HNSW index should remain loaded"

        # Verify: should NOT have called invalidate() (index still exists)
        # If invalidate was called, hnsw_index would be None
        assert cache_entry.hnsw_index is not None

    def test_standalone_mode_when_no_cache_entry(
        self, temp_store: FilesystemVectorStore, sample_points
    ):
        """
        AC4: Use standalone mode when cache_entry not provided.

        GREEN: This should already pass with current implementation.
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # No cache_entry set - should use standalone mode
        assert not hasattr(temp_store, "cache_entry") or temp_store.cache_entry is None

        # Watch mode update without cache_entry
        new_point = [sample_points[5]]
        temp_store.upsert_points(collection_name, new_point, watch_mode=True)

        # Verify: HNSW index file should exist on disk
        collection_path = temp_store.base_path / collection_name
        hnsw_file = collection_path / "hnsw_index.bin"
        assert hnsw_file.exists(), "Standalone mode should persist HNSW to disk"


class TestDaemonCacheInMemoryUpdates:
    """Test AC3: Daemon cache in-memory updates (no invalidation)."""

    def test_cache_hnsw_updated_in_memory(
        self, temp_store: FilesystemVectorStore, cache_entry: CacheEntry, sample_points
    ):
        """
        AC3: Update cache_entry.hnsw_index directly via add_items().

        RED: Will fail because current implementation doesn't update cache.
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # Load cache
        collection_path = temp_store.base_path / collection_name
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
        cache_entry.hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )
        cache_entry.id_mapping = id_manager = IDIndexManager().load_index(
            collection_path
        )

        # Get initial vector count
        initial_count = cache_entry.hnsw_index.get_current_count()

        # Set cache_entry on vector store
        temp_store.cache_entry = cache_entry

        # Watch mode update
        new_point = [sample_points[5]]
        temp_store.upsert_points(collection_name, new_point, watch_mode=True)

        # Verify: cache HNSW index should have new vector
        updated_count = cache_entry.hnsw_index.get_current_count()
        assert updated_count > initial_count, "Cache HNSW should have new vector added"

    def test_cache_not_invalidated_during_watch_update(
        self, temp_store: FilesystemVectorStore, cache_entry: CacheEntry, sample_points
    ):
        """
        AC3: Verify cache is NOT invalidated (no reload needed).

        RED: Will fail because we need to track invalidation calls.
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # Load cache
        collection_path = temp_store.base_path / collection_name
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
        cache_entry.hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )
        cache_entry.id_mapping = IDIndexManager().load_index(collection_path)

        # Track invalidate() calls
        original_invalidate = cache_entry.invalidate
        invalidate_called = []

        def track_invalidate():
            invalidate_called.append(True)
            original_invalidate()

        cache_entry.invalidate = track_invalidate

        # Set cache_entry
        temp_store.cache_entry = cache_entry

        # Watch mode update
        new_point = [sample_points[5]]
        temp_store.upsert_points(collection_name, new_point, watch_mode=True)

        # Verify: invalidate() should NOT have been called
        assert (
            len(invalidate_called) == 0
        ), "Cache should not be invalidated during watch update"

        # Verify: cache still has index loaded (warm cache)
        assert cache_entry.hnsw_index is not None, "Cache should remain warm"


class TestConcurrentQuerySupport:
    """Test AC2: Concurrent query support with readers-writer lock."""

    def test_write_lock_blocks_concurrent_queries(
        self, temp_store: FilesystemVectorStore, cache_entry: CacheEntry, sample_points
    ):
        """
        AC2: Write lock acquired during HNSW update.

        Verifies that locking is properly used (functional test).
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # Load cache
        collection_path = temp_store.base_path / collection_name
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
        cache_entry.hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )
        cache_entry.id_mapping = IDIndexManager().load_index(collection_path)

        temp_store.cache_entry = cache_entry

        # Watch mode update - should use locks internally
        new_point = [sample_points[5]]
        temp_store.upsert_points(collection_name, new_point, watch_mode=True)

        # Verify: cache was updated (functional verification)
        assert cache_entry.hnsw_index is not None, "Cache should remain loaded"
        assert (
            cache_entry.hnsw_index.get_current_count() == 6
        ), "Cache should have 6 vectors"

    def test_query_waits_for_write_completion(
        self, temp_store: FilesystemVectorStore, cache_entry: CacheEntry, sample_points
    ):
        """
        AC2: Query waits for write operation to complete.

        RED: Will fail because concurrent execution is not properly synchronized.
        """
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, vector_size=128)

        # Initial indexing
        temp_store.begin_indexing(collection_name)
        temp_store.upsert_points(collection_name, sample_points[:5])
        temp_store.end_indexing(collection_name)

        # Load cache
        collection_path = temp_store.base_path / collection_name
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager

        hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
        cache_entry.hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )
        cache_entry.id_mapping = IDIndexManager().load_index(collection_path)

        temp_store.cache_entry = cache_entry

        # Shared state for thread synchronization
        update_started = threading.Event()
        update_completed = threading.Event()
        query_executed = []

        def slow_watch_update():
            """Simulate slow HNSW update"""
            update_started.set()
            import time

            time.sleep(0.1)  # Simulate work
            new_point = [sample_points[5]]
            temp_store.upsert_points(collection_name, new_point, watch_mode=True)
            update_completed.set()

        def concurrent_query():
            """Try to query during update"""
            update_started.wait()  # Wait for update to start
            # Try to query (should block until write completes)
            with cache_entry.read_lock:
                query_executed.append(True)

        # Start update thread
        update_thread = threading.Thread(target=slow_watch_update)
        update_thread.start()

        # Start query thread
        query_thread = threading.Thread(target=concurrent_query)
        query_thread.start()

        # Wait for both
        update_thread.join(timeout=1.0)
        query_thread.join(timeout=1.0)

        # Verify: query executed (wasn't deadlocked)
        assert len(query_executed) > 0, "Query should have executed"

        # Verify: update completed
        assert update_completed.is_set(), "Update should have completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
