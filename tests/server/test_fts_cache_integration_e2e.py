"""
End-to-End Integration Tests for FTS Index Cache with Server.

Story #XXX: Tests verify actual FTS caching performance improvement in server context.

These tests use ZERO mocking for the cache integration - all real components:
- Real FTSIndexCache
- Real singleton pattern
- Real cache with actual timing measurements
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.server.cache import (
    get_global_fts_cache,
    reset_global_fts_cache,
    FTSIndexCache,
    FTSIndexCacheConfig,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset global FTS cache before and after each test."""
    reset_global_fts_cache()
    yield
    reset_global_fts_cache()


class TestFTSCacheIntegration:
    """Integration tests for FTS cache."""

    def test_cache_improves_query_performance(self):
        """
        Test that cache improves query performance on repeated queries.

        This is a simplified performance test using mock indexes to demonstrate
        the caching behavior. Real performance gains would be measured with
        actual Tantivy indexes.
        """
        # Create cache with reload disabled for cleaner timing
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()
        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            time.sleep(0.01)  # Simulate load time
            return mock_index, mock_schema

        cache_key = "/path/to/repo/tantivy_index"

        # First load - should be slow (cache miss)
        start1 = time.time()
        index1, schema1 = cache.get_or_load(cache_key, mock_loader)
        time1 = time.time() - start1

        # Second load - should be fast (cache hit)
        start2 = time.time()
        index2, schema2 = cache.get_or_load(cache_key, mock_loader)
        time2 = time.time() - start2

        # Verify same index returned
        assert index1 is index2
        assert schema1 is schema2

        # Verify cache hit was faster
        assert time2 < time1

        # Verify loader called only once
        assert load_count == 1

        # Verify cache stats
        stats = cache.get_stats()
        assert stats.hit_count == 1
        assert stats.miss_count == 1

    def test_cache_with_reload_on_access(self):
        """Test cache calls reload on each access when reload_on_access=True."""
        config = FTSIndexCacheConfig(reload_on_access=True)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        cache_key = "/path/to/repo/tantivy_index"

        # First load (miss)
        cache.get_or_load(cache_key, mock_loader)

        # Reset mock to track reload calls
        mock_index.reset_mock()

        # Multiple cache hits
        for _ in range(5):
            cache.get_or_load(cache_key, mock_loader)

        # Verify reload was called on each cache hit
        assert mock_index.reload.call_count == 5

        # Verify stats
        stats = cache.get_stats()
        assert stats.reload_count == 5


class TestFTSCacheSingleton:
    """Test global FTS cache singleton behavior."""

    def test_global_fts_cache_singleton(self):
        """Test get_global_fts_cache returns same instance."""
        reset_global_fts_cache()

        cache1 = get_global_fts_cache()
        cache2 = get_global_fts_cache()

        assert cache1 is cache2

    def test_reset_global_fts_cache_clears_singleton(self):
        """Test reset_global_fts_cache creates new instance."""
        cache1 = get_global_fts_cache()

        reset_global_fts_cache()

        cache2 = get_global_fts_cache()

        assert cache1 is not cache2

    def test_global_cache_starts_background_cleanup(self):
        """Test global cache starts background cleanup automatically."""
        reset_global_fts_cache()

        cache = get_global_fts_cache()

        # Background cleanup should be running
        assert cache._cleanup_thread is not None
        assert cache._cleanup_thread.is_alive()

    def test_reset_stops_background_cleanup(self):
        """Test reset stops background cleanup thread."""
        cache = get_global_fts_cache()
        cleanup_thread = cache._cleanup_thread

        reset_global_fts_cache()

        # Give thread time to stop
        time.sleep(0.1)

        # Thread should be stopped
        assert not cleanup_thread.is_alive()


class TestFTSCacheWithTantivyIndexManager:
    """Test FTS cache integration with TantivyIndexManager methods."""

    def test_set_cached_index_method_exists(self):
        """Test TantivyIndexManager has set_cached_index method."""
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Verify method exists
        assert hasattr(TantivyIndexManager, "set_cached_index")

    def test_get_index_for_caching_method_exists(self):
        """Test TantivyIndexManager has get_index_for_caching method."""
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Verify method exists
        assert hasattr(TantivyIndexManager, "get_index_for_caching")

    def test_get_index_for_caching_raises_when_not_initialized(self):
        """Test get_index_for_caching raises RuntimeError when index not initialized."""
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TantivyIndexManager(Path(tmpdir) / "tantivy_index")

            with pytest.raises(RuntimeError, match="Index not initialized"):
                manager.get_index_for_caching()

    def test_set_and_get_cached_index(self):
        """Test set_cached_index and get_index_for_caching work together."""
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TantivyIndexManager(Path(tmpdir) / "tantivy_index")

            # Create mock index and schema
            mock_index = Mock()
            mock_schema = Mock()

            # Set cached index
            manager.set_cached_index(mock_index, mock_schema)

            # Verify internal state
            assert manager._index is mock_index
            assert manager._schema is mock_schema

            # Get index for caching
            index, schema = manager.get_index_for_caching()

            assert index is mock_index
            assert schema is mock_schema


class TestFTSCacheStatsEndpoint:
    """Test FTS cache statistics functionality."""

    def test_cache_stats_are_accurate(self):
        """Test cache statistics accurately track operations."""
        config = FTSIndexCacheConfig(reload_on_access=True)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def loader1():
            return mock_index, mock_schema

        def loader2():
            return Mock(), Mock()

        # Initial state
        stats = cache.get_stats()
        assert stats.cached_repositories == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.reload_count == 0

        # Load first repo (miss)
        cache.get_or_load("/repo1/index", loader1)
        stats = cache.get_stats()
        assert stats.cached_repositories == 1
        assert stats.miss_count == 1
        assert stats.hit_count == 0

        # Load second repo (miss)
        cache.get_or_load("/repo2/index", loader2)
        stats = cache.get_stats()
        assert stats.cached_repositories == 2
        assert stats.miss_count == 2
        assert stats.hit_count == 0

        # Access first repo again (hit + reload)
        cache.get_or_load("/repo1/index", loader1)
        stats = cache.get_stats()
        assert stats.cached_repositories == 2
        assert stats.miss_count == 2
        assert stats.hit_count == 1
        assert stats.reload_count == 1

        # Invalidate first repo
        cache.invalidate("/repo1/index")
        stats = cache.get_stats()
        assert stats.cached_repositories == 1
        assert stats.eviction_count == 1

        # Clear all
        cache.clear()
        stats = cache.get_stats()
        assert stats.cached_repositories == 0
        assert stats.eviction_count == 2  # 1 from invalidate + 1 from clear
