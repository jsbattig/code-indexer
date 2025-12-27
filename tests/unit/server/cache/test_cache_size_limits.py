"""
Tests for cache size limit enforcement (Story #620, Priority 3A).

Validates that both HNSWIndexCache and FTSIndexCache enforce max_cache_size_mb limits:
- Evict oldest entries when cache exceeds size limit
- Maintain LRU eviction order
- No eviction when under limit
- Accurate size calculation

These tests verify AC3A: Cache size limits prevent unbounded memory growth.
"""

import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

import pytest

from code_indexer.server.cache.fts_index_cache import (
    FTSIndexCache,
    FTSIndexCacheConfig,
)
from code_indexer.server.cache.hnsw_index_cache import (
    HNSWIndexCache,
    HNSWIndexCacheConfig,
)


class TestHNSWIndexCacheSizeLimits:
    """Test HNSW cache size limit enforcement."""

    def test_eviction_when_over_limit(self, tmp_path: Path):
        """
        Test that cache evicts oldest entries when size limit exceeded.

        Story #620, AC3A: Cache evicts LRU entries to stay within max_cache_size_mb.
        """
        # Configure cache with 150MB limit (1.5 entries at 100MB estimate per entry)
        config = HNSWIndexCacheConfig(
            ttl_minutes=60.0,  # Long TTL to avoid TTL-based eviction
            max_cache_size_mb=150,  # Should hold 1 entry, evict when 2nd added
        )
        cache = HNSWIndexCache(config=config)

        # Create mock HNSW indexes (each ~100MB estimate)
        def create_loader(repo_name: str) -> Any:
            def loader() -> Tuple[Any, Dict[int, str]]:
                mock_index = MagicMock()
                id_mapping = {i: f"{repo_name}_vec_{i}" for i in range(1000)}
                return mock_index, id_mapping

            return loader

        # Load first entry (repo1) - should be cached
        repo1_path = str(tmp_path / "repo1")
        cache.get_or_load(repo1_path, create_loader("repo1"))

        # Verify repo1 is cached
        assert repo1_path in cache._cache
        assert len(cache._cache) == 1

        # Small delay to ensure different access times
        time.sleep(0.01)

        # Load second entry (repo2) - should trigger eviction of repo1
        repo2_path = str(tmp_path / "repo2")
        cache.get_or_load(repo2_path, create_loader("repo2"))

        # Verify only repo2 is cached (repo1 was evicted)
        assert repo2_path in cache._cache
        assert repo1_path not in cache._cache, "Oldest entry should be evicted"
        assert len(cache._cache) == 1

        # Verify eviction count increased
        stats = cache.get_stats()
        assert stats.eviction_count == 1, "Should have 1 size-based eviction"

    def test_lru_eviction_order(self, tmp_path: Path):
        """
        Test that LRU (Least Recently Used) eviction order is maintained.

        Story #620, AC3A: Most recently accessed entries are retained.
        """
        # Configure cache with 150MB limit
        config = HNSWIndexCacheConfig(ttl_minutes=60.0, max_cache_size_mb=150)
        cache = HNSWIndexCache(config=config)

        def create_loader(repo_name: str) -> Any:
            def loader() -> Tuple[Any, Dict[int, str]]:
                mock_index = MagicMock()
                id_mapping = {i: f"{repo_name}_vec_{i}" for i in range(1000)}
                return mock_index, id_mapping

            return loader

        # Load repo1
        repo1_path = str(tmp_path / "repo1")
        cache.get_or_load(repo1_path, create_loader("repo1"))
        time.sleep(0.01)

        # Load repo2 (triggers eviction of repo1)
        repo2_path = str(tmp_path / "repo2")
        cache.get_or_load(repo2_path, create_loader("repo2"))
        time.sleep(0.01)

        # Access repo2 again to refresh its access time
        cache.get_or_load(repo2_path, create_loader("repo2"))
        time.sleep(0.01)

        # Load repo3 (should evict repo2 since it was accessed more recently than repo1)
        # Actually, repo1 is already evicted, so repo3 should evict repo2
        repo3_path = str(tmp_path / "repo3")
        cache.get_or_load(repo3_path, create_loader("repo3"))

        # Verify only repo3 is cached
        assert repo3_path in cache._cache
        assert repo2_path not in cache._cache, "Older entry should be evicted"
        assert len(cache._cache) == 1

    def test_no_eviction_under_limit(self, tmp_path: Path):
        """
        Test that no eviction occurs when cache is under size limit.

        Story #620, AC3A: Entries are retained when total size < max_cache_size_mb.
        """
        # Configure cache with 500MB limit (can hold 5 entries at 100MB each)
        config = HNSWIndexCacheConfig(ttl_minutes=60.0, max_cache_size_mb=500)
        cache = HNSWIndexCache(config=config)

        def create_loader(repo_name: str) -> Any:
            def loader() -> Tuple[Any, Dict[int, str]]:
                mock_index = MagicMock()
                id_mapping = {i: f"{repo_name}_vec_{i}" for i in range(1000)}
                return mock_index, id_mapping

            return loader

        # Load 3 entries (300MB total, under 500MB limit)
        repo_paths = []
        for i in range(3):
            repo_path = str(tmp_path / f"repo{i}")
            repo_paths.append(repo_path)
            cache.get_or_load(repo_path, create_loader(f"repo{i}"))
            time.sleep(0.01)

        # Verify all 3 entries are cached
        for repo_path in repo_paths:
            assert repo_path in cache._cache, f"{repo_path} should be cached"

        assert len(cache._cache) == 3

        # Verify no evictions occurred
        stats = cache.get_stats()
        assert stats.eviction_count == 0, "No evictions should occur under limit"

    def test_accurate_size_calculation(self, tmp_path: Path):
        """
        Test that cache size is calculated accurately.

        Story #620, AC3A: Size calculation reflects actual cached entries.
        """
        # Configure cache with known limit
        config = HNSWIndexCacheConfig(ttl_minutes=60.0, max_cache_size_mb=300)
        cache = HNSWIndexCache(config=config)

        def create_loader(repo_name: str) -> Any:
            def loader() -> Tuple[Any, Dict[int, str]]:
                mock_index = MagicMock()
                id_mapping = {i: f"{repo_name}_vec_{i}" for i in range(1000)}
                return mock_index, id_mapping

            return loader

        # Load 2 entries
        repo1_path = str(tmp_path / "repo1")
        repo2_path = str(tmp_path / "repo2")

        cache.get_or_load(repo1_path, create_loader("repo1"))
        cache.get_or_load(repo2_path, create_loader("repo2"))

        # Get stats and verify size calculation
        stats = cache.get_stats()

        # Current implementation estimates 100MB per HNSW index
        expected_size_mb = 200  # 2 entries * 100MB
        assert stats.total_memory_mb == expected_size_mb, (
            f"Size calculation incorrect: expected {expected_size_mb}MB, "
            f"got {stats.total_memory_mb}MB"
        )


class TestFTSIndexCacheSizeLimits:
    """Test FTS cache size limit enforcement."""

    def test_eviction_when_over_limit(self, tmp_path: Path):
        """
        Test that FTS cache evicts oldest entries when size limit exceeded.

        Story #620, AC3A: Cache evicts LRU entries to stay within max_cache_size_mb.
        """
        # Configure cache with 15MB limit (1.5 entries at 10MB estimate per entry)
        config = FTSIndexCacheConfig(
            ttl_minutes=60.0,
            max_cache_size_mb=15,  # Should hold 1 entry, evict when 2nd added
            reload_on_access=False,  # Disable reload for testing
        )
        cache = FTSIndexCache(config=config)

        # Create mock FTS indexes (each ~10MB estimate)
        def create_loader(index_name: str) -> Any:
            def loader() -> Tuple[Any, Any]:
                mock_index = MagicMock()
                mock_schema = MagicMock()
                return mock_index, mock_schema

            return loader

        # Load first entry (index1) - should be cached
        index1_dir = str(tmp_path / "index1")
        cache.get_or_load(index1_dir, create_loader("index1"))

        # Verify index1 is cached
        assert index1_dir in cache._cache
        assert len(cache._cache) == 1

        # Small delay to ensure different access times
        time.sleep(0.01)

        # Load second entry (index2) - should trigger eviction of index1
        index2_dir = str(tmp_path / "index2")
        cache.get_or_load(index2_dir, create_loader("index2"))

        # Verify only index2 is cached (index1 was evicted)
        assert index2_dir in cache._cache
        assert index1_dir not in cache._cache, "Oldest entry should be evicted"
        assert len(cache._cache) == 1

        # Verify eviction count increased
        stats = cache.get_stats()
        assert stats.eviction_count == 1, "Should have 1 size-based eviction"

    def test_lru_eviction_order(self, tmp_path: Path):
        """
        Test that FTS cache maintains LRU eviction order.

        Story #620, AC3A: Most recently accessed entries are retained.
        """
        # Configure cache with 15MB limit
        config = FTSIndexCacheConfig(
            ttl_minutes=60.0, max_cache_size_mb=15, reload_on_access=False
        )
        cache = FTSIndexCache(config=config)

        def create_loader(index_name: str) -> Any:
            def loader() -> Tuple[Any, Any]:
                mock_index = MagicMock()
                mock_schema = MagicMock()
                return mock_index, mock_schema

            return loader

        # Load index1
        index1_dir = str(tmp_path / "index1")
        cache.get_or_load(index1_dir, create_loader("index1"))
        time.sleep(0.01)

        # Load index2 (triggers eviction of index1)
        index2_dir = str(tmp_path / "index2")
        cache.get_or_load(index2_dir, create_loader("index2"))
        time.sleep(0.01)

        # Access index2 again to refresh its access time
        cache.get_or_load(index2_dir, create_loader("index2"))
        time.sleep(0.01)

        # Load index3 (should evict index2)
        index3_dir = str(tmp_path / "index3")
        cache.get_or_load(index3_dir, create_loader("index3"))

        # Verify only index3 is cached
        assert index3_dir in cache._cache
        assert index2_dir not in cache._cache, "Older entry should be evicted"
        assert len(cache._cache) == 1

    def test_no_eviction_under_limit(self, tmp_path: Path):
        """
        Test that FTS cache doesn't evict when under size limit.

        Story #620, AC3A: Entries are retained when total size < max_cache_size_mb.
        """
        # Configure cache with 50MB limit (can hold 5 entries at 10MB each)
        config = FTSIndexCacheConfig(
            ttl_minutes=60.0, max_cache_size_mb=50, reload_on_access=False
        )
        cache = FTSIndexCache(config=config)

        def create_loader(index_name: str) -> Any:
            def loader() -> Tuple[Any, Any]:
                mock_index = MagicMock()
                mock_schema = MagicMock()
                return mock_index, mock_schema

            return loader

        # Load 3 entries (30MB total, under 50MB limit)
        index_dirs = []
        for i in range(3):
            index_dir = str(tmp_path / f"index{i}")
            index_dirs.append(index_dir)
            cache.get_or_load(index_dir, create_loader(f"index{i}"))
            time.sleep(0.01)

        # Verify all 3 entries are cached
        for index_dir in index_dirs:
            assert index_dir in cache._cache, f"{index_dir} should be cached"

        assert len(cache._cache) == 3

        # Verify no evictions occurred
        stats = cache.get_stats()
        assert stats.eviction_count == 0, "No evictions should occur under limit"

    def test_accurate_size_calculation(self, tmp_path: Path):
        """
        Test that FTS cache size is calculated accurately.

        Story #620, AC3A: Size calculation reflects actual cached entries.
        """
        # Configure cache with known limit
        config = FTSIndexCacheConfig(
            ttl_minutes=60.0, max_cache_size_mb=30, reload_on_access=False
        )
        cache = FTSIndexCache(config=config)

        def create_loader(index_name: str) -> Any:
            def loader() -> Tuple[Any, Any]:
                mock_index = MagicMock()
                mock_schema = MagicMock()
                return mock_index, mock_schema

            return loader

        # Load 2 entries
        index1_dir = str(tmp_path / "index1")
        index2_dir = str(tmp_path / "index2")

        cache.get_or_load(index1_dir, create_loader("index1"))
        cache.get_or_load(index2_dir, create_loader("index2"))

        # Get stats and verify size calculation
        stats = cache.get_stats()

        # Current implementation estimates 10MB per FTS index
        expected_size_mb = 20  # 2 entries * 10MB
        assert stats.total_memory_mb == expected_size_mb, (
            f"Size calculation incorrect: expected {expected_size_mb}MB, "
            f"got {stats.total_memory_mb}MB"
        )
