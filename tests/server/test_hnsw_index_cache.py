"""
Tests for HNSW Index Cache for Server-Side Performance.

Story #526: Server-Side HNSW Index Caching for 1800x Query Performance

Tests verify:
- AC1: Server-side index cache with memory caching
- AC2: TTL-based cache eviction
- AC3: Access-based TTL refresh
- AC4: Per-repository cache isolation
- AC5: Thread-safe cache operations
- AC6: Configuration externalization
- AC7: Cache statistics and monitoring
"""

import json
import os
import threading
import time
from unittest.mock import Mock

import pytest

from code_indexer.server.cache.hnsw_index_cache import (
    HNSWIndexCache,
    HNSWIndexCacheEntry,
    HNSWIndexCacheConfig,
)


class TestHNSWIndexCacheConfig:
    """Test configuration externalization (AC6)."""

    def test_default_config_values(self):
        """Test default configuration values."""
        config = HNSWIndexCacheConfig()

        assert config.ttl_minutes == 10
        assert config.cleanup_interval_seconds == 60
        assert config.max_cache_size_mb is None  # No limit by default

    def test_config_from_dict(self):
        """Test configuration creation from dictionary."""
        config_dict = {
            "ttl_minutes": 20,
            "cleanup_interval_seconds": 120,
            "max_cache_size_mb": 1024,
        }

        config = HNSWIndexCacheConfig.from_dict(config_dict)

        assert config.ttl_minutes == 20
        assert config.cleanup_interval_seconds == 120
        assert config.max_cache_size_mb == 1024

    def test_config_validation_negative_ttl(self):
        """Test configuration validation rejects negative TTL."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            HNSWIndexCacheConfig(ttl_minutes=-1)

    def test_config_validation_zero_ttl(self):
        """Test configuration validation rejects zero TTL."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            HNSWIndexCacheConfig(ttl_minutes=0)

    def test_config_from_env_variable(self):
        """Test configuration from environment variable."""
        os.environ["CIDX_INDEX_CACHE_TTL_MINUTES"] = "15"

        try:
            config = HNSWIndexCacheConfig.from_env()
            assert config.ttl_minutes == 15
        finally:
            del os.environ["CIDX_INDEX_CACHE_TTL_MINUTES"]

    def test_config_from_file(self, tmp_path):
        """Test configuration from config file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "index_cache_ttl_minutes": 25,
            "index_cache_cleanup_interval_seconds": 90,
        }
        config_file.write_text(json.dumps(config_data))

        config = HNSWIndexCacheConfig.from_file(str(config_file))

        assert config.ttl_minutes == 25
        assert config.cleanup_interval_seconds == 90


class TestHNSWIndexCacheEntry:
    """Test cache entry behavior (AC3: TTL refresh)."""

    def test_cache_entry_creation(self):
        """Test cache entry is created with initial values."""
        mock_index = Mock()
        mock_id_mapping = {"0": "vec_0"}

        entry = HNSWIndexCacheEntry(
            hnsw_index=mock_index,
            id_mapping=mock_id_mapping,
            repo_path="/path/to/repo",
            ttl_minutes=10,
        )

        assert entry.hnsw_index is mock_index
        assert entry.id_mapping == mock_id_mapping
        assert entry.repo_path == "/path/to/repo"
        assert entry.ttl_minutes == 10
        assert entry.access_count == 0
        assert entry.created_at is not None
        assert entry.last_accessed is not None

    def test_cache_entry_access_updates_timestamp(self):
        """Test accessing cache entry refreshes TTL (AC3)."""
        mock_index = Mock()
        entry = HNSWIndexCacheEntry(
            hnsw_index=mock_index,
            id_mapping={},
            repo_path="/path/to/repo",
            ttl_minutes=10,
        )

        original_access_time = entry.last_accessed
        time.sleep(0.01)  # Small delay to ensure timestamp changes

        entry.record_access()

        assert entry.last_accessed > original_access_time
        assert entry.access_count == 1

    def test_cache_entry_is_expired_false_when_fresh(self):
        """Test cache entry is not expired when within TTL."""
        mock_index = Mock()
        entry = HNSWIndexCacheEntry(
            hnsw_index=mock_index,
            id_mapping={},
            repo_path="/path/to/repo",
            ttl_minutes=10,
        )

        assert not entry.is_expired()

    def test_cache_entry_is_expired_true_when_stale(self):
        """Test cache entry expires after TTL (AC2)."""
        mock_index = Mock()
        entry = HNSWIndexCacheEntry(
            hnsw_index=mock_index,
            id_mapping={},
            repo_path="/path/to/repo",
            ttl_minutes=0.0001,  # Very short TTL for testing
        )

        time.sleep(0.01)  # Wait for expiration

        assert entry.is_expired()

    def test_cache_entry_access_extends_ttl(self):
        """Test accessing entry extends TTL from access time (AC3)."""
        mock_index = Mock()
        entry = HNSWIndexCacheEntry(
            hnsw_index=mock_index,
            id_mapping={},
            repo_path="/path/to/repo",
            ttl_minutes=0.001,  # 0.06 seconds
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


class TestHNSWIndexCache:
    """Test HNSW index cache implementation (AC1, AC2, AC4, AC5)."""

    def test_cache_initialization(self):
        """Test cache initializes with default config."""
        cache = HNSWIndexCache()

        assert cache.config.ttl_minutes == 10
        assert len(cache._cache) == 0

    def test_cache_get_or_load_new_index(self):
        """Test cache loads index on first access (AC1)."""
        cache = HNSWIndexCache()
        mock_index = Mock()
        mock_id_mapping = {"0": "vec_0"}

        # Mock the loader function
        def mock_loader():
            return mock_index, mock_id_mapping

        # First access should load
        index, id_mapping = cache.get_or_load("/path/to/repo", mock_loader)

        assert index is mock_index
        assert id_mapping == mock_id_mapping
        assert "/path/to/repo" in cache._cache

    def test_cache_get_or_load_cached_index(self):
        """Test cache returns cached index on subsequent access (AC1)."""
        cache = HNSWIndexCache()
        mock_index = Mock()
        mock_id_mapping = {"0": "vec_0"}

        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            return mock_index, mock_id_mapping

        # First access
        index1, id_mapping1 = cache.get_or_load("/path/to/repo", mock_loader)

        # Second access should use cache
        index2, id_mapping2 = cache.get_or_load("/path/to/repo", mock_loader)

        assert index1 is index2
        assert id_mapping1 == id_mapping2
        assert load_count == 1  # Loader called only once

    def test_cache_per_repository_isolation(self):
        """Test different repositories have isolated cache entries (AC4)."""
        cache = HNSWIndexCache()

        mock_index1 = Mock(name="index1")
        mock_index2 = Mock(name="index2")

        def loader1():
            return mock_index1, {"0": "vec1_0"}

        def loader2():
            return mock_index2, {"0": "vec2_0"}

        # Load different repositories
        index1, mapping1 = cache.get_or_load("/repo1", loader1)
        index2, mapping2 = cache.get_or_load("/repo2", loader2)

        assert index1 is mock_index1
        assert index2 is mock_index2
        assert index1 is not index2
        assert mapping1 != mapping2

    def test_cache_eviction_after_ttl(self):
        """Test cache evicts entries after TTL expires (AC2)."""
        config = HNSWIndexCacheConfig(ttl_minutes=0.001)  # Very short TTL
        cache = HNSWIndexCache(config=config)

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Load index
        cache.get_or_load("/repo", mock_loader)

        # Verify cached
        assert "/repo" in cache._cache

        # Wait for TTL expiration
        time.sleep(0.1)

        # Trigger cleanup
        cache._cleanup_expired_entries()

        # Should be evicted
        assert "/repo" not in cache._cache

    def test_cache_access_refreshes_ttl_prevents_eviction(self):
        """Test accessing cache entry prevents eviction (AC3)."""
        config = HNSWIndexCacheConfig(ttl_minutes=0.001)  # 0.06 seconds
        cache = HNSWIndexCache(config=config)

        mock_index = Mock()
        load_count = 0

        def mock_loader():
            nonlocal load_count
            load_count += 1
            return mock_index, {}

        # Initial load
        cache.get_or_load("/repo", mock_loader)

        # Access repeatedly before TTL expires
        for _ in range(5):
            time.sleep(0.03)  # Half the TTL
            cache.get_or_load("/repo", mock_loader)

        # Should still be cached (accessed within TTL each time)
        assert "/repo" in cache._cache
        assert load_count == 1  # Only loaded once, not reloaded

    def test_cache_thread_safety_concurrent_loads(self):
        """Test cache is thread-safe for concurrent loads (AC5)."""
        cache = HNSWIndexCache()

        mock_index = Mock()
        load_count = 0
        load_lock = threading.Lock()

        def mock_loader():
            nonlocal load_count
            with load_lock:
                load_count += 1
            time.sleep(0.01)  # Simulate loading time
            return mock_index, {}

        # Concurrent loads from multiple threads
        threads = []
        results = []

        def load_index():
            index, mapping = cache.get_or_load("/repo", mock_loader)
            results.append((index, mapping))

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
        cache = HNSWIndexCache()

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Pre-load index
        cache.get_or_load("/repo", mock_loader)

        # Concurrent access from multiple threads
        threads = []
        access_counts = []

        def access_index():
            for _ in range(100):
                index, mapping = cache.get_or_load("/repo", mock_loader)
                assert index is mock_index

            # Check access count
            entry = cache._cache["/repo"]
            access_counts.append(entry.access_count)

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
        entry = cache._cache["/repo"]
        assert entry.access_count == 501  # 1 initial load + (5 threads * 100 accesses)

    def test_cache_stats_empty_cache(self):
        """Test cache statistics for empty cache (AC7)."""
        cache = HNSWIndexCache()

        stats = cache.get_stats()

        assert stats.cached_repositories == 0
        assert stats.total_memory_mb == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.eviction_count == 0

    def test_cache_stats_with_entries(self):
        """Test cache statistics with cached entries (AC7)."""
        cache = HNSWIndexCache()

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Load multiple repositories
        cache.get_or_load("/repo1", mock_loader)
        cache.get_or_load("/repo2", mock_loader)
        cache.get_or_load("/repo1", mock_loader)  # Hit

        stats = cache.get_stats()

        assert stats.cached_repositories == 2
        assert stats.hit_count == 1
        assert stats.miss_count == 2

    def test_cache_stats_per_repository(self):
        """Test per-repository cache statistics (AC7)."""
        cache = HNSWIndexCache()

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Load and access
        cache.get_or_load("/repo1", mock_loader)
        cache.get_or_load("/repo1", mock_loader)
        cache.get_or_load("/repo1", mock_loader)

        stats = cache.get_stats()
        repo_stats = stats.per_repository_stats.get("/repo1")

        assert repo_stats is not None
        assert repo_stats["access_count"] == 3
        assert repo_stats["last_accessed"] is not None
        assert "ttl_remaining_seconds" in repo_stats

    def test_cache_background_cleanup_starts(self):
        """Test background cleanup thread starts automatically."""
        config = HNSWIndexCacheConfig(cleanup_interval_seconds=1)
        cache = HNSWIndexCache(config=config)

        cache.start_background_cleanup()

        assert cache._cleanup_thread is not None
        assert cache._cleanup_thread.is_alive()

        cache.stop_background_cleanup()

    def test_cache_background_cleanup_evicts_expired(self):
        """Test background cleanup evicts expired entries (AC2)."""
        config = HNSWIndexCacheConfig(
            ttl_minutes=0.001,  # 0.06 seconds
            cleanup_interval_seconds=0.1,
        )
        cache = HNSWIndexCache(config=config)

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Start background cleanup
        cache.start_background_cleanup()

        try:
            # Load index
            cache.get_or_load("/repo", mock_loader)
            assert "/repo" in cache._cache

            # Wait for TTL expiration + cleanup
            time.sleep(0.3)

            # Should be evicted by background cleanup
            assert "/repo" not in cache._cache
        finally:
            cache.stop_background_cleanup()

    def test_cache_clear_all_entries(self):
        """Test cache can clear all entries."""
        cache = HNSWIndexCache()

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Load multiple repos
        cache.get_or_load("/repo1", mock_loader)
        cache.get_or_load("/repo2", mock_loader)
        cache.get_or_load("/repo3", mock_loader)

        assert len(cache._cache) == 3

        cache.clear()

        assert len(cache._cache) == 0

    def test_cache_invalidate_specific_repository(self):
        """Test cache can invalidate specific repository."""
        cache = HNSWIndexCache()

        mock_index = Mock()

        def mock_loader():
            return mock_index, {}

        # Load multiple repos
        cache.get_or_load("/repo1", mock_loader)
        cache.get_or_load("/repo2", mock_loader)

        assert len(cache._cache) == 2

        cache.invalidate("/repo1")

        assert "/repo1" not in cache._cache
        assert "/repo2" in cache._cache
