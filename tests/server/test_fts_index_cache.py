"""
Tests for FTS (Tantivy) Index Cache for Server-Side Performance.

Story #XXX: Server-Side FTS Index Caching for Query Performance

Tests verify:
- AC1: Server-side FTS index cache with memory caching
- AC2: TTL-based cache eviction
- AC3: Access-based TTL refresh
- AC4: Per-repository cache isolation
- AC5: Thread-safe cache operations
- AC6: Configuration externalization
- AC7: Cache statistics and monitoring
- AC8: reload_on_access behavior for fresh data
"""

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.server.cache.fts_index_cache import (
    FTSIndexCache,
    FTSIndexCacheEntry,
    FTSIndexCacheConfig,
    FTSIndexCacheStats,
)


class TestFTSIndexCacheConfig:
    """Test configuration externalization (AC6)."""

    def test_default_config_values(self):
        """Test default configuration values."""
        config = FTSIndexCacheConfig()

        assert config.ttl_minutes == 10.0
        assert config.cleanup_interval_seconds == 60
        assert config.max_cache_size_mb is None  # No limit by default
        assert config.reload_on_access is True  # Default: reload on cache hit

    def test_config_with_custom_values(self):
        """Test configuration creation with custom values."""
        config = FTSIndexCacheConfig(
            ttl_minutes=20.0,
            cleanup_interval_seconds=120,
            max_cache_size_mb=1024,
            reload_on_access=False,
        )

        assert config.ttl_minutes == 20.0
        assert config.cleanup_interval_seconds == 120
        assert config.max_cache_size_mb == 1024
        assert config.reload_on_access is False

    def test_config_validation_negative_ttl(self):
        """Test configuration validation rejects negative TTL."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            FTSIndexCacheConfig(ttl_minutes=-1)

    def test_config_validation_zero_ttl(self):
        """Test configuration validation rejects zero TTL."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            FTSIndexCacheConfig(ttl_minutes=0)

    def test_config_validation_negative_cleanup_interval(self):
        """Test configuration validation rejects negative cleanup interval."""
        with pytest.raises(ValueError, match="Cleanup interval must be positive"):
            FTSIndexCacheConfig(cleanup_interval_seconds=-1)

    def test_config_validation_zero_cleanup_interval(self):
        """Test configuration validation rejects zero cleanup interval."""
        with pytest.raises(ValueError, match="Cleanup interval must be positive"):
            FTSIndexCacheConfig(cleanup_interval_seconds=0)

    def test_config_from_env_variable(self):
        """Test configuration from environment variable."""
        os.environ["CIDX_FTS_CACHE_TTL_MINUTES"] = "15"
        os.environ["CIDX_FTS_CACHE_CLEANUP_INTERVAL"] = "90"
        os.environ["CIDX_FTS_CACHE_RELOAD_ON_ACCESS"] = "false"

        try:
            config = FTSIndexCacheConfig.from_env()
            assert config.ttl_minutes == 15.0
            assert config.cleanup_interval_seconds == 90
            assert config.reload_on_access is False
        finally:
            del os.environ["CIDX_FTS_CACHE_TTL_MINUTES"]
            del os.environ["CIDX_FTS_CACHE_CLEANUP_INTERVAL"]
            del os.environ["CIDX_FTS_CACHE_RELOAD_ON_ACCESS"]

    def test_config_from_env_variable_defaults(self):
        """Test configuration from environment uses defaults when not set."""
        # Ensure env vars are not set
        for key in [
            "CIDX_FTS_CACHE_TTL_MINUTES",
            "CIDX_FTS_CACHE_CLEANUP_INTERVAL",
            "CIDX_FTS_CACHE_RELOAD_ON_ACCESS",
        ]:
            if key in os.environ:
                del os.environ[key]

        config = FTSIndexCacheConfig.from_env()
        assert config.ttl_minutes == 10.0
        assert config.cleanup_interval_seconds == 60
        assert config.reload_on_access is True

    def test_config_from_file(self, tmp_path):
        """Test configuration from config file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "fts_cache_ttl_minutes": 25.0,
            "fts_cache_cleanup_interval_seconds": 90,
            "fts_cache_max_size_mb": 512,
            "fts_cache_reload_on_access": False,
        }
        config_file.write_text(json.dumps(config_data))

        config = FTSIndexCacheConfig.from_file(str(config_file))

        assert config.ttl_minutes == 25.0
        assert config.cleanup_interval_seconds == 90
        assert config.max_cache_size_mb == 512
        assert config.reload_on_access is False

    def test_config_from_file_not_found(self, tmp_path):
        """Test configuration from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            FTSIndexCacheConfig.from_file(str(tmp_path / "nonexistent.json"))


class TestFTSIndexCacheEntry:
    """Test cache entry behavior (AC3: TTL refresh)."""

    def test_cache_entry_creation(self):
        """Test cache entry is created with initial values."""
        mock_index = Mock()
        mock_schema = Mock()

        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=10.0,
        )

        assert entry.tantivy_index is mock_index
        assert entry.schema is mock_schema
        assert entry.index_dir == "/path/to/index"
        assert entry.ttl_minutes == 10.0
        assert entry.access_count == 0
        assert entry.created_at is not None
        assert entry.last_accessed is not None

    def test_cache_entry_access_updates_timestamp(self):
        """Test accessing cache entry refreshes TTL (AC3)."""
        mock_index = Mock()
        mock_schema = Mock()
        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=10.0,
        )

        original_access_time = entry.last_accessed
        time.sleep(0.01)  # Small delay to ensure timestamp changes

        entry.record_access()

        assert entry.last_accessed > original_access_time
        assert entry.access_count == 1

    def test_cache_entry_is_expired_false_when_fresh(self):
        """Test cache entry is not expired when within TTL."""
        mock_index = Mock()
        mock_schema = Mock()
        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=10.0,
        )

        assert not entry.is_expired()

    def test_cache_entry_is_expired_true_when_stale(self):
        """Test cache entry expires after TTL (AC2)."""
        mock_index = Mock()
        mock_schema = Mock()
        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=0.0001,  # Very short TTL for testing (~6ms)
        )

        time.sleep(0.01)  # Wait for expiration

        assert entry.is_expired()

    def test_cache_entry_access_extends_ttl(self):
        """Test accessing entry extends TTL from access time (AC3)."""
        mock_index = Mock()
        mock_schema = Mock()
        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=0.001,  # ~60ms TTL
        )

        # Wait half the TTL
        time.sleep(0.03)

        # Access should extend TTL
        entry.record_access()

        # Should not be expired immediately after access
        assert not entry.is_expired()

        # Wait another half TTL (original would have expired, but accessed)
        time.sleep(0.04)

        # Should still not be expired because TTL was refreshed
        assert not entry.is_expired()

    def test_cache_entry_ttl_remaining_seconds(self):
        """Test TTL remaining calculation."""
        mock_index = Mock()
        mock_schema = Mock()
        entry = FTSIndexCacheEntry(
            tantivy_index=mock_index,
            schema=mock_schema,
            index_dir="/path/to/index",
            ttl_minutes=1.0,  # 60 seconds
        )

        remaining = entry.ttl_remaining_seconds()

        # Should be close to 60 seconds (with small margin for execution time)
        assert 58 < remaining <= 60


class TestFTSIndexCacheStats:
    """Test cache statistics (AC7)."""

    def test_stats_creation(self):
        """Test cache statistics creation."""
        stats = FTSIndexCacheStats(
            cached_repositories=2,
            total_memory_mb=20.0,
            hit_count=10,
            miss_count=5,
            eviction_count=1,
            reload_count=8,
        )

        assert stats.cached_repositories == 2
        assert stats.total_memory_mb == 20.0
        assert stats.hit_count == 10
        assert stats.miss_count == 5
        assert stats.eviction_count == 1
        assert stats.reload_count == 8

    def test_stats_hit_ratio_calculation(self):
        """Test hit ratio calculation."""
        stats = FTSIndexCacheStats(
            cached_repositories=1,
            total_memory_mb=10.0,
            hit_count=80,
            miss_count=20,
            eviction_count=0,
            reload_count=0,
        )

        assert stats.hit_ratio == 0.8

    def test_stats_hit_ratio_zero_when_empty(self):
        """Test hit ratio is zero when no requests."""
        stats = FTSIndexCacheStats(
            cached_repositories=0,
            total_memory_mb=0.0,
            hit_count=0,
            miss_count=0,
            eviction_count=0,
            reload_count=0,
        )

        assert stats.hit_ratio == 0.0


class TestFTSIndexCache:
    """Test FTS index cache implementation (AC1, AC2, AC4, AC5)."""

    def test_cache_initialization(self):
        """Test cache initializes with default config."""
        cache = FTSIndexCache()

        assert cache.config.ttl_minutes == 10.0
        assert len(cache._cache) == 0

    def test_cache_initialization_with_custom_config(self):
        """Test cache initializes with custom config."""
        config = FTSIndexCacheConfig(ttl_minutes=20.0, reload_on_access=False)
        cache = FTSIndexCache(config=config)

        assert cache.config.ttl_minutes == 20.0
        assert cache.config.reload_on_access is False

    def test_cache_get_or_load_new_index(self):
        """Test cache loads index on first access (AC1)."""
        cache = FTSIndexCache()
        mock_index = Mock()
        mock_schema = Mock()

        # Mock the loader function
        def mock_loader():
            return mock_index, mock_schema

        # First access should load
        index, schema = cache.get_or_load("/path/to/index", mock_loader)

        assert index is mock_index
        assert schema is mock_schema
        # Path is normalized, so check if it's cached
        assert len(cache._cache) == 1

    def test_cache_get_or_load_cached_index(self):
        """Test cache returns cached index on subsequent access (AC1)."""
        # Disable reload_on_access for simpler test
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)
        mock_index = Mock()
        mock_schema = Mock()

        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            return mock_index, mock_schema

        # First access
        index1, schema1 = cache.get_or_load("/path/to/index", mock_loader)

        # Second access should use cache
        index2, schema2 = cache.get_or_load("/path/to/index", mock_loader)

        assert index1 is index2
        assert schema1 is schema2
        assert load_count == 1  # Loader called only once

    def test_cache_per_repository_isolation(self):
        """Test different repositories have isolated cache entries (AC4)."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index1 = Mock(name="index1")
        mock_index2 = Mock(name="index2")
        mock_schema1 = Mock(name="schema1")
        mock_schema2 = Mock(name="schema2")

        def loader1():
            return mock_index1, mock_schema1

        def loader2():
            return mock_index2, mock_schema2

        # Load different repositories
        index1, schema1 = cache.get_or_load("/repo1/tantivy_index", loader1)
        index2, schema2 = cache.get_or_load("/repo2/tantivy_index", loader2)

        assert index1 is mock_index1
        assert index2 is mock_index2
        assert index1 is not index2
        assert schema1 is not schema2

    def test_cache_eviction_after_ttl(self):
        """Test cache evicts entries after TTL expires (AC2)."""
        config = FTSIndexCacheConfig(ttl_minutes=0.001, reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load index
        cache.get_or_load("/repo/index", mock_loader)

        # Verify cached
        assert len(cache._cache) == 1

        # Wait for TTL expiration
        time.sleep(0.1)

        # Trigger cleanup
        cache._cleanup_expired_entries()

        # Should be evicted
        assert len(cache._cache) == 0

    def test_cache_access_refreshes_ttl_prevents_eviction(self):
        """Test accessing cache entry prevents eviction (AC3)."""
        config = FTSIndexCacheConfig(ttl_minutes=0.001, reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()
        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            return mock_index, mock_schema

        # Initial load
        cache.get_or_load("/repo/index", mock_loader)

        # Access repeatedly before TTL expires
        for _ in range(5):
            time.sleep(0.03)  # Half the TTL
            cache.get_or_load("/repo/index", mock_loader)

        # Should still be cached (accessed within TTL each time)
        assert len(cache._cache) == 1
        assert load_count == 1  # Only loaded once, not reloaded

    def test_cache_reload_on_access_behavior(self):
        """Test reload_on_access calls index.reload() on cache hit (AC8)."""
        config = FTSIndexCacheConfig(reload_on_access=True)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # First access (cache miss)
        cache.get_or_load("/repo/index", mock_loader)

        # Reset mock to verify reload is called
        mock_index.reset_mock()

        # Second access (cache hit) - should call reload()
        cache.get_or_load("/repo/index", mock_loader)

        # Verify reload was called
        mock_index.reload.assert_called_once()

    def test_cache_reload_on_access_disabled(self):
        """Test reload_on_access=False skips reload on cache hit."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # First access (cache miss)
        cache.get_or_load("/repo/index", mock_loader)

        # Reset mock
        mock_index.reset_mock()

        # Second access (cache hit) - should NOT call reload()
        cache.get_or_load("/repo/index", mock_loader)

        # Verify reload was NOT called
        mock_index.reload.assert_not_called()

    def test_cache_reload_failure_handled_gracefully(self):
        """Test reload failure is handled gracefully without crashing."""
        config = FTSIndexCacheConfig(reload_on_access=True)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_index.reload.side_effect = Exception("Reload failed")
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # First access
        cache.get_or_load("/repo/index", mock_loader)

        # Second access should not raise despite reload failure
        index, schema = cache.get_or_load("/repo/index", mock_loader)

        # Should still return cached index
        assert index is mock_index
        assert schema is mock_schema

    def test_cache_thread_safety_concurrent_loads(self):
        """Test cache is thread-safe for concurrent loads (AC5)."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()
        load_count = 0
        load_lock = threading.Lock()

        def mock_loader():
            nonlocal load_count
            with load_lock:
                load_count += 1
            time.sleep(0.01)  # Simulate loading time
            return mock_index, mock_schema

        # Concurrent loads from multiple threads
        threads = []
        results = []

        def load_index():
            index, schema = cache.get_or_load("/repo/index", mock_loader)
            results.append((index, schema))

        # Start 10 concurrent threads
        for _ in range(10):
            t = threading.Thread(target=load_index)
            t.start()
            threads.append(t)

        # Wait for all threads
        for t in threads:
            t.join()

        # All should get same index
        assert len(results) == 10
        assert all(index is mock_index for index, _ in results)

        # Loader should be called only once (deduplication)
        assert load_count == 1

    def test_cache_thread_safety_concurrent_access(self):
        """Test cache handles concurrent access safely (AC5)."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Pre-load index
        cache.get_or_load("/repo/index", mock_loader)

        # Get the normalized path for checking
        normalized_path = str(Path("/repo/index").resolve())

        # Concurrent access from multiple threads
        threads = []

        def access_index():
            for _ in range(100):
                index, schema = cache.get_or_load("/repo/index", mock_loader)
                assert index is mock_index

        # Start 5 concurrent threads
        for _ in range(5):
            t = threading.Thread(target=access_index)
            t.start()
            threads.append(t)

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify no data corruption
        # Expected: 1 initial load + (5 threads * 100 accesses) = 501
        entry = cache._cache[normalized_path]
        assert entry.access_count == 501

    def test_cache_stats_empty_cache(self):
        """Test cache statistics for empty cache (AC7)."""
        cache = FTSIndexCache()

        stats = cache.get_stats()

        assert stats.cached_repositories == 0
        assert stats.total_memory_mb == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.eviction_count == 0
        assert stats.reload_count == 0

    def test_cache_stats_with_entries(self):
        """Test cache statistics with cached entries (AC7)."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load multiple repositories
        cache.get_or_load("/repo1/index", mock_loader)
        cache.get_or_load("/repo2/index", mock_loader)
        cache.get_or_load("/repo1/index", mock_loader)  # Hit

        stats = cache.get_stats()

        assert stats.cached_repositories == 2
        assert stats.hit_count == 1
        assert stats.miss_count == 2

    def test_cache_stats_reload_count(self):
        """Test cache statistics tracks reload count (AC7)."""
        config = FTSIndexCacheConfig(reload_on_access=True)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load repository
        cache.get_or_load("/repo/index", mock_loader)

        # Access multiple times (each should trigger reload)
        for _ in range(5):
            cache.get_or_load("/repo/index", mock_loader)

        stats = cache.get_stats()

        assert stats.reload_count == 5  # 5 cache hits with reload

    def test_cache_stats_per_repository(self):
        """Test per-repository cache statistics (AC7)."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load and access
        cache.get_or_load("/repo1/index", mock_loader)
        cache.get_or_load("/repo1/index", mock_loader)
        cache.get_or_load("/repo1/index", mock_loader)

        stats = cache.get_stats()
        normalized_path = str(Path("/repo1/index").resolve())
        repo_stats = stats.per_repository_stats.get(normalized_path)

        assert repo_stats is not None
        assert repo_stats["access_count"] == 3
        assert repo_stats["last_accessed"] is not None
        assert "ttl_remaining_seconds" in repo_stats

    def test_cache_background_cleanup_starts(self):
        """Test background cleanup thread starts automatically."""
        config = FTSIndexCacheConfig(cleanup_interval_seconds=1)
        cache = FTSIndexCache(config=config)

        cache.start_background_cleanup()

        assert cache._cleanup_thread is not None
        assert cache._cleanup_thread.is_alive()

        cache.stop_background_cleanup()

    def test_cache_background_cleanup_evicts_expired(self):
        """Test background cleanup evicts expired entries (AC2)."""
        config = FTSIndexCacheConfig(
            ttl_minutes=0.001,  # ~60ms
            cleanup_interval_seconds=0.1,
            reload_on_access=False,
        )
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Start background cleanup
        cache.start_background_cleanup()

        try:
            # Load index
            cache.get_or_load("/repo/index", mock_loader)
            assert len(cache._cache) == 1

            # Wait for TTL expiration + cleanup
            time.sleep(0.3)

            # Should be evicted by background cleanup
            assert len(cache._cache) == 0
        finally:
            cache.stop_background_cleanup()

    def test_cache_clear_all_entries(self):
        """Test cache can clear all entries."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load multiple repos
        cache.get_or_load("/repo1/index", mock_loader)
        cache.get_or_load("/repo2/index", mock_loader)
        cache.get_or_load("/repo3/index", mock_loader)

        assert len(cache._cache) == 3

        cache.clear()

        assert len(cache._cache) == 0

    def test_cache_invalidate_specific_repository(self):
        """Test cache can invalidate specific repository."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()

        def mock_loader():
            return mock_index, mock_schema

        # Load multiple repos
        cache.get_or_load("/repo1/index", mock_loader)
        cache.get_or_load("/repo2/index", mock_loader)

        assert len(cache._cache) == 2

        cache.invalidate("/repo1/index")

        assert len(cache._cache) == 1
        # Verify correct one was removed
        normalized_path1 = str(Path("/repo1/index").resolve())
        normalized_path2 = str(Path("/repo2/index").resolve())
        assert normalized_path1 not in cache._cache
        assert normalized_path2 in cache._cache

    def test_cache_path_normalization(self):
        """Test cache normalizes paths for consistent caching."""
        config = FTSIndexCacheConfig(reload_on_access=False)
        cache = FTSIndexCache(config=config)

        mock_index = Mock()
        mock_schema = Mock()
        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            return mock_index, mock_schema

        # Load with one path format
        cache.get_or_load("/repo/index", mock_loader)

        # Access with slightly different path (same resolved path)
        cache.get_or_load("/repo/./index", mock_loader)

        # Should only load once due to path normalization
        assert load_count == 1
