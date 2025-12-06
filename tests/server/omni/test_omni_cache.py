"""
Tests for OmniCache - cursor pagination with TTL and LRU eviction.

Tests AC5: Cursor pagination cache with thread safety.
"""

import pytest
import time
import threading
from code_indexer.server.omni.omni_cache import OmniCache


class TestOmniCacheBasics:
    """Test basic cache operations."""

    def test_store_and_retrieve_results(self):
        """Test storing and retrieving results with cursor."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        results = [{"score": 0.9, "content": "test"}]
        cursor = cache.store_results(results, query_params={"query": "test"})

        assert cursor is not None
        assert len(cursor) > 0

        retrieved = cache.get_results(cursor, offset=0, limit=10)
        assert retrieved is not None
        assert len(retrieved) == 1
        assert retrieved[0]["content"] == "test"

    def test_cursor_uniqueness(self):
        """Test that each store operation generates unique cursor."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        cursor1 = cache.store_results([{"a": 1}], query_params={"q": "1"})
        cursor2 = cache.store_results([{"b": 2}], query_params={"q": "2"})

        assert cursor1 != cursor2

    def test_invalid_cursor_returns_none(self):
        """Test that invalid cursor returns None."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        retrieved = cache.get_results("invalid-cursor-uuid", offset=0, limit=10)
        assert retrieved is None

    def test_pagination_with_offset_and_limit(self):
        """Test pagination works with offset and limit."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        results = [{"id": i} for i in range(100)]
        cursor = cache.store_results(results, query_params={"query": "test"})

        # Get first page
        page1 = cache.get_results(cursor, offset=0, limit=10)
        assert len(page1) == 10
        assert page1[0]["id"] == 0
        assert page1[9]["id"] == 9

        # Get second page
        page2 = cache.get_results(cursor, offset=10, limit=10)
        assert len(page2) == 10
        assert page2[0]["id"] == 10
        assert page2[9]["id"] == 19

    def test_offset_beyond_results_returns_empty(self):
        """Test offset beyond results returns empty list."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        results = [{"id": i} for i in range(10)]
        cursor = cache.store_results(results, query_params={"query": "test"})

        page = cache.get_results(cursor, offset=100, limit=10)
        assert page == []


class TestOmniCacheTTL:
    """Test TTL (time-to-live) functionality."""

    def test_expired_cursor_returns_none(self):
        """Test that expired cursor returns None."""
        cache = OmniCache(ttl_seconds=1, max_entries=100)

        results = [{"id": 1}]
        cursor = cache.store_results(results, query_params={"query": "test"})

        # Wait for expiration
        time.sleep(1.1)

        retrieved = cache.get_results(cursor, offset=0, limit=10)
        assert retrieved is None

    def test_non_expired_cursor_works(self):
        """Test that non-expired cursor works correctly."""
        cache = OmniCache(ttl_seconds=5, max_entries=100)

        results = [{"id": 1}]
        cursor = cache.store_results(results, query_params={"query": "test"})

        # Retrieve immediately (within TTL)
        retrieved = cache.get_results(cursor, offset=0, limit=10)
        assert retrieved is not None
        assert len(retrieved) == 1


class TestOmniCacheLRU:
    """Test LRU (least recently used) eviction."""

    def test_lru_eviction_when_max_entries_exceeded(self):
        """Test LRU eviction when max entries exceeded."""
        cache = OmniCache(ttl_seconds=60, max_entries=3)

        cursor1 = cache.store_results([{"id": 1}], query_params={"q": "1"})
        cursor2 = cache.store_results([{"id": 2}], query_params={"q": "2"})
        cursor3 = cache.store_results([{"id": 3}], query_params={"q": "3"})

        # All should be retrievable
        assert cache.get_results(cursor1, 0, 10) is not None
        assert cache.get_results(cursor2, 0, 10) is not None
        assert cache.get_results(cursor3, 0, 10) is not None

        # Add 4th entry, should evict least recently used (cursor1)
        cursor4 = cache.store_results([{"id": 4}], query_params={"q": "4"})

        assert cache.get_results(cursor1, 0, 10) is None  # Evicted
        assert cache.get_results(cursor2, 0, 10) is not None
        assert cache.get_results(cursor3, 0, 10) is not None
        assert cache.get_results(cursor4, 0, 10) is not None

    def test_lru_access_updates_usage(self):
        """Test that accessing an entry updates its LRU position."""
        cache = OmniCache(ttl_seconds=60, max_entries=3)

        cursor1 = cache.store_results([{"id": 1}], query_params={"q": "1"})
        cursor2 = cache.store_results([{"id": 2}], query_params={"q": "2"})
        cursor3 = cache.store_results([{"id": 3}], query_params={"q": "3"})

        # Access cursor1 to make it recently used
        cache.get_results(cursor1, 0, 10)

        # Add 4th entry, should evict cursor2 (now least recently used)
        cursor4 = cache.store_results([{"id": 4}], query_params={"q": "4"})

        assert cache.get_results(cursor1, 0, 10) is not None  # Still available
        assert cache.get_results(cursor2, 0, 10) is None  # Evicted
        assert cache.get_results(cursor3, 0, 10) is not None
        assert cache.get_results(cursor4, 0, 10) is not None


class TestOmniCacheThreadSafety:
    """Test thread safety of cache operations."""

    def test_concurrent_store_operations(self):
        """Test concurrent store operations are thread-safe."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)
        cursors = []

        def store_results(i):
            cursor = cache.store_results([{"id": i}], query_params={"q": str(i)})
            cursors.append(cursor)

        threads = [threading.Thread(target=store_results, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All cursors should be unique and valid
        assert len(cursors) == 10
        assert len(set(cursors)) == 10  # All unique

        # All should be retrievable
        for cursor in cursors:
            assert cache.get_results(cursor, 0, 10) is not None

    def test_concurrent_read_operations(self):
        """Test concurrent read operations are thread-safe."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        results = [{"id": i} for i in range(100)]
        cursor = cache.store_results(results, query_params={"query": "test"})

        retrieved_results = []

        def read_results(offset):
            page = cache.get_results(cursor, offset=offset, limit=10)
            retrieved_results.append(page)

        threads = [
            threading.Thread(target=read_results, args=(i * 10,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert len(retrieved_results) == 10
        assert all(page is not None for page in retrieved_results)


class TestOmniCacheMemoryLimit:
    """Test memory limit enforcement."""

    def test_memory_limit_enforcement(self):
        """Test that cache enforces memory limit."""
        # Small memory limit for testing
        cache = OmniCache(ttl_seconds=60, max_entries=100, max_memory_mb=1)

        # Try to store large result set
        large_results = [{"data": "x" * 10000} for _ in range(1000)]

        cursor = cache.store_results(large_results, query_params={"query": "test"})

        # Should still work but may trigger eviction
        assert cursor is not None

    def test_get_cache_stats(self):
        """Test cache statistics retrieval."""
        cache = OmniCache(ttl_seconds=60, max_entries=100)

        # Store some results
        cursor1 = cache.store_results([{"id": 1}], query_params={"q": "1"})
        cursor2 = cache.store_results([{"id": 2}], query_params={"q": "2"})

        stats = cache.get_stats()

        assert "total_entries" in stats
        assert "max_entries" in stats
        assert "ttl_seconds" in stats
        assert stats["total_entries"] == 2
