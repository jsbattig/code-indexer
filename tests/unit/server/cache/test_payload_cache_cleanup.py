"""Unit tests for PayloadCache cleanup operations.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC6: Background Cleanup Thread

These tests follow TDD methodology - written BEFORE implementation.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path


class TestPayloadCacheCleanup:
    """Tests for PayloadCache cleanup operations (AC6)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_entries(self, temp_db_path):
        """Test that cleanup_expired() removes entries older than TTL."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
            CacheNotFoundError,
        )

        # Use very short TTL for testing
        config = PayloadCacheConfig(cache_ttl_seconds=1)
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        # Store content
        handle = await cache.store("Test content")

        # Verify content exists
        result = await cache.retrieve(handle, page=0)
        assert result.content == "Test content"

        # Wait for TTL to expire
        await asyncio.sleep(1.5)

        # Run cleanup
        deleted_count = await cache.cleanup_expired()
        assert deleted_count == 1

        # Verify content is gone
        with pytest.raises(CacheNotFoundError):
            await cache.retrieve(handle, page=0)

        await cache.close()

    @pytest.mark.asyncio
    async def test_cleanup_expired_keeps_fresh_entries(self, temp_db_path):
        """Test that cleanup_expired() keeps entries within TTL."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig(cache_ttl_seconds=300)  # 5 minutes
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        handle = await cache.store("Fresh content")

        # Run cleanup immediately (entry is fresh)
        deleted_count = await cache.cleanup_expired()
        assert deleted_count == 0

        # Verify content still exists
        result = await cache.retrieve(handle, page=0)
        assert result.content == "Fresh content"

        await cache.close()


class TestPayloadCacheBackgroundCleanup:
    """Tests for background cleanup thread (AC6)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.mark.asyncio
    async def test_background_cleanup_thread_starts_as_daemon(self, temp_db_path):
        """Test that background cleanup thread is started as daemon."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig(cleanup_interval_seconds=1)
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        # Start background cleanup
        cache.start_background_cleanup()

        assert cache._cleanup_thread is not None
        assert cache._cleanup_thread.daemon is True
        assert cache._cleanup_thread.is_alive()

        # Stop cleanup
        cache.stop_background_cleanup()
        await cache.close()

    @pytest.mark.asyncio
    async def test_stop_background_cleanup_stops_thread(self, temp_db_path):
        """Test that stop_background_cleanup() stops the thread."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig(cleanup_interval_seconds=10)
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        cache.start_background_cleanup()
        assert cache._cleanup_thread.is_alive()

        cache.stop_background_cleanup()
        # Give thread time to stop
        await asyncio.sleep(0.5)

        # Thread should no longer be alive
        assert not cache._cleanup_thread.is_alive()

        await cache.close()
