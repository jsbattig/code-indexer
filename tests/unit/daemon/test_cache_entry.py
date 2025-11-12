"""Unit tests for CacheEntry class.

Tests cache entry initialization, TTL tracking, access counting, and concurrency primitives.
"""

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


class TestCacheEntryInitialization:
    """Test CacheEntry initialization and basic attributes."""

    def test_cache_entry_initializes_with_project_path(self):
        """Test CacheEntry initializes with project path."""
        from code_indexer.daemon.cache import CacheEntry

        project_path = Path("/tmp/test-project")
        entry = CacheEntry(project_path)

        assert entry.project_path == project_path

    def test_cache_entry_initializes_semantic_indexes_as_none(self):
        """Test CacheEntry initializes HNSW and ID mapping as None."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert entry.hnsw_index is None
        assert entry.id_mapping is None

    def test_cache_entry_initializes_fts_indexes_as_none(self):
        """Test CacheEntry initializes Tantivy indexes as None."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert entry.tantivy_index is None
        assert entry.tantivy_searcher is None
        assert entry.fts_available is False

    def test_cache_entry_initializes_last_accessed_to_now(self):
        """Test CacheEntry initializes last_accessed to current time."""
        from code_indexer.daemon.cache import CacheEntry

        before = datetime.now()
        entry = CacheEntry(Path("/tmp/test"))
        after = datetime.now()

        assert before <= entry.last_accessed <= after

    def test_cache_entry_initializes_with_default_ttl(self):
        """Test CacheEntry initializes with default 10-minute TTL."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert entry.ttl_minutes == 10

    def test_cache_entry_initializes_with_custom_ttl(self):
        """Test CacheEntry can initialize with custom TTL."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"), ttl_minutes=30)

        assert entry.ttl_minutes == 30

    def test_cache_entry_initializes_access_count_to_zero(self):
        """Test CacheEntry initializes access_count to 0."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert entry.access_count == 0


class TestCacheEntryConcurrencyPrimitives:
    """Test CacheEntry concurrency control primitives."""

    def test_cache_entry_has_read_lock(self):
        """Test CacheEntry has RLock for concurrent reads."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert hasattr(entry, "read_lock")
        assert isinstance(entry.read_lock, type(threading.RLock()))

    def test_cache_entry_has_write_lock(self):
        """Test CacheEntry has Lock for serialized writes."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        assert hasattr(entry, "write_lock")
        assert isinstance(entry.write_lock, type(threading.Lock()))

    def test_read_lock_allows_concurrent_acquisition(self):
        """Test RLock allows same thread to acquire multiple times."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        # RLock can be acquired multiple times by same thread
        assert entry.read_lock.acquire(blocking=False)
        assert entry.read_lock.acquire(blocking=False)

        entry.read_lock.release()
        entry.read_lock.release()

    def test_write_lock_serializes_access(self):
        """Test Lock ensures serialized write access."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        # First acquisition succeeds
        assert entry.write_lock.acquire(blocking=False)

        # Second acquisition fails (Lock is not reentrant)
        assert not entry.write_lock.acquire(blocking=False)

        entry.write_lock.release()


class TestCacheEntryAccessTracking:
    """Test CacheEntry access tracking and TTL updates."""

    def test_update_access_increments_count(self):
        """Test update_access increments access_count."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))
        assert entry.access_count == 0

        entry.update_access()
        assert entry.access_count == 1

        entry.update_access()
        assert entry.access_count == 2

    def test_update_access_updates_last_accessed_timestamp(self):
        """Test update_access updates last_accessed to current time."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))
        original_time = entry.last_accessed

        # Wait a tiny bit to ensure timestamp changes
        time.sleep(0.01)

        entry.update_access()

        assert entry.last_accessed > original_time

    def test_is_expired_returns_false_for_fresh_entry(self):
        """Test is_expired returns False for recently accessed entry."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"), ttl_minutes=10)

        assert not entry.is_expired()

    def test_is_expired_returns_true_for_expired_entry(self):
        """Test is_expired returns True when TTL exceeded."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)

        # Simulate expiration by backdating last_accessed
        entry.last_accessed = datetime.now() - timedelta(minutes=2)

        assert entry.is_expired()

    def test_is_expired_boundary_condition(self):
        """Test is_expired at exact TTL boundary."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)

        # Exactly at TTL boundary (should not be expired yet)
        entry.last_accessed = datetime.now() - timedelta(minutes=1)

        # Should be expired (boundary is inclusive)
        assert entry.is_expired()


class TestCacheEntryIndexManagement:
    """Test CacheEntry index loading and invalidation."""

    def test_set_semantic_indexes(self):
        """Test setting HNSW index and ID mapping."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        mock_hnsw = object()  # Mock HNSW index
        mock_mapping = {"id1": "path1"}

        entry.set_semantic_indexes(mock_hnsw, mock_mapping)

        assert entry.hnsw_index is mock_hnsw
        assert entry.id_mapping == mock_mapping

    def test_set_fts_indexes(self):
        """Test setting Tantivy indexes."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        mock_index = object()
        mock_searcher = object()

        entry.set_fts_indexes(mock_index, mock_searcher)

        assert entry.tantivy_index is mock_index
        assert entry.tantivy_searcher is mock_searcher
        assert entry.fts_available is True

    def test_invalidate_clears_all_indexes(self):
        """Test invalidate clears both semantic and FTS indexes."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        # Set up indexes
        entry.set_semantic_indexes(object(), {"test": "data"})
        entry.set_fts_indexes(object(), object())

        # Invalidate
        entry.invalidate()

        # All indexes should be cleared
        assert entry.hnsw_index is None
        assert entry.id_mapping is None
        assert entry.tantivy_index is None
        assert entry.tantivy_searcher is None
        assert entry.fts_available is False

    def test_invalidate_preserves_access_tracking(self):
        """Test invalidate preserves access count and timestamp."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))
        entry.update_access()
        entry.update_access()

        original_count = entry.access_count
        original_time = entry.last_accessed

        entry.invalidate()

        # Access tracking should be preserved
        assert entry.access_count == original_count
        assert entry.last_accessed == original_time


class TestCacheEntryStatistics:
    """Test CacheEntry statistics generation."""

    def test_get_stats_returns_basic_info(self):
        """Test get_stats returns cache entry statistics."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test-project"), ttl_minutes=15)
        entry.update_access()
        entry.update_access()

        stats = entry.get_stats()

        assert stats["project_path"] == str(Path("/tmp/test-project"))
        assert stats["access_count"] == 2
        assert stats["ttl_minutes"] == 15
        assert "last_accessed" in stats

    def test_get_stats_reports_semantic_loaded_status(self):
        """Test get_stats reports whether semantic indexes are loaded."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        # Initially not loaded
        stats = entry.get_stats()
        assert stats["semantic_loaded"] is False

        # After loading
        entry.set_semantic_indexes(object(), {})
        stats = entry.get_stats()
        assert stats["semantic_loaded"] is True

    def test_get_stats_reports_fts_loaded_status(self):
        """Test get_stats reports whether FTS indexes are loaded."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"))

        # Initially not loaded
        stats = entry.get_stats()
        assert stats["fts_loaded"] is False

        # After loading
        entry.set_fts_indexes(object(), object())
        stats = entry.get_stats()
        assert stats["fts_loaded"] is True

    def test_get_stats_reports_expiration_status(self):
        """Test get_stats reports whether entry is expired."""
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)

        # Fresh entry
        stats = entry.get_stats()
        assert stats["expired"] is False

        # Expired entry
        entry.last_accessed = datetime.now() - timedelta(minutes=2)
        stats = entry.get_stats()
        assert stats["expired"] is True
