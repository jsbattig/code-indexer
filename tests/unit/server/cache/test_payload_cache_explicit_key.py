"""Unit tests for PayloadCache explicit key operations.

Story #720: Delegation Result Caching and Timeout Parameterization
Part 1: Add store_with_key() and has_key() to PayloadCache

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import tempfile
import time
from pathlib import Path


class TestPayloadCacheStoreWithKey:
    """Tests for PayloadCache.store_with_key() method."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.fixture
    async def cache(self, temp_db_path):
        """Create and initialize a PayloadCache instance for testing."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_store_with_key_stores_content_with_explicit_key(self, cache):
        """
        store_with_key() stores content with the provided key instead of UUID4.

        Given an explicit key and content
        When store_with_key() is called
        Then the content should be retrievable using that exact key
        """
        explicit_key = "delegation:job-12345"
        content = "The authentication module uses JWT tokens."

        await cache.store_with_key(explicit_key, content)

        # Retrieve using the explicit key
        result = await cache.retrieve(explicit_key, page=0)
        assert result.content == content

    @pytest.mark.asyncio
    async def test_store_with_key_updates_existing_key(self, cache):
        """
        store_with_key() updates content if key already exists.

        Given a key that already has stored content
        When store_with_key() is called with new content
        Then the content should be updated to the new value
        """
        explicit_key = "delegation:job-99999"
        original_content = "Original content"
        updated_content = "Updated content with more details"

        # Store original content
        await cache.store_with_key(explicit_key, original_content)

        # Update with new content
        await cache.store_with_key(explicit_key, updated_content)

        # Retrieve should return updated content
        result = await cache.retrieve(explicit_key, page=0)
        assert result.content == updated_content

    @pytest.mark.asyncio
    async def test_store_with_key_preserves_total_size(self, cache, temp_db_path):
        """
        store_with_key() stores correct total_size metadata.

        Given content of known length
        When store_with_key() is called
        Then total_size should equal the content length
        """
        explicit_key = "delegation:size-test"
        content = "A" * 12345

        await cache.store_with_key(explicit_key, content)

        # Verify directly in database
        import aiosqlite

        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute(
                "SELECT total_size FROM payload_cache WHERE handle = ?",
                (explicit_key,),
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 12345

    @pytest.mark.asyncio
    async def test_store_with_key_updates_timestamp_on_replace(self, cache, temp_db_path):
        """
        store_with_key() updates created_at timestamp when updating existing key.

        Given a key with existing content
        When store_with_key() is called again with new content
        Then the timestamp should be updated (for TTL purposes)
        """
        import aiosqlite

        explicit_key = "delegation:timestamp-test"

        # Store initial content
        await cache.store_with_key(explicit_key, "Initial content")

        # Get initial timestamp
        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute(
                "SELECT created_at FROM payload_cache WHERE handle = ?",
                (explicit_key,),
            ) as cursor:
                row = await cursor.fetchone()
                initial_timestamp = row[0]

        # Wait a tiny bit to ensure timestamp difference
        time.sleep(0.01)

        # Update content
        await cache.store_with_key(explicit_key, "Updated content")

        # Get updated timestamp
        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute(
                "SELECT created_at FROM payload_cache WHERE handle = ?",
                (explicit_key,),
            ) as cursor:
                row = await cursor.fetchone()
                updated_timestamp = row[0]

        assert updated_timestamp > initial_timestamp

    @pytest.mark.asyncio
    async def test_store_with_key_pagination_works(self, cache):
        """
        store_with_key() content can be retrieved with pagination.

        Given large content stored with explicit key
        When retrieve() is called with different page numbers
        Then pagination should work correctly
        """
        explicit_key = "delegation:large-content"
        # Content larger than max_fetch_size_chars (5000)
        content = "A" * 5000 + "B" * 5000

        await cache.store_with_key(explicit_key, content)

        # Retrieve page 0
        result0 = await cache.retrieve(explicit_key, page=0)
        assert result0.content == "A" * 5000
        assert result0.total_pages == 2
        assert result0.has_more is True

        # Retrieve page 1
        result1 = await cache.retrieve(explicit_key, page=1)
        assert result1.content == "B" * 5000
        assert result1.has_more is False


class TestPayloadCacheHasKey:
    """Tests for PayloadCache.has_key() method."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.fixture
    async def cache(self, temp_db_path):
        """Create and initialize a PayloadCache instance for testing."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_has_key_returns_true_for_existing_key(self, cache):
        """
        has_key() returns True when key exists in cache.

        Given a key has been stored
        When has_key() is called
        Then it should return True
        """
        explicit_key = "delegation:exists-test"
        await cache.store_with_key(explicit_key, "Some content")

        result = await cache.has_key(explicit_key)

        assert result is True

    @pytest.mark.asyncio
    async def test_has_key_returns_false_for_nonexistent_key(self, cache):
        """
        has_key() returns False when key does not exist.

        Given a key that was never stored
        When has_key() is called
        Then it should return False
        """
        result = await cache.has_key("delegation:nonexistent-key")

        assert result is False

    @pytest.mark.asyncio
    async def test_has_key_works_with_uuid4_stored_content(self, cache):
        """
        has_key() works with handles from store() (UUID4).

        Given content was stored with store() returning UUID4
        When has_key() is called with that UUID
        Then it should return True
        """
        handle = await cache.store("Content stored with UUID4")

        result = await cache.has_key(handle)

        assert result is True

    @pytest.mark.asyncio
    async def test_has_key_does_not_retrieve_content(self, cache, temp_db_path):
        """
        has_key() is efficient - only checks existence without retrieving content.

        Given a key with large content
        When has_key() is called
        Then it should only check existence (not load content)

        Note: This is a behavioral test - implementation should use SELECT EXISTS
        or COUNT(*) rather than SELECT content.
        """
        explicit_key = "delegation:large-check"
        large_content = "X" * 100000  # 100KB of content

        await cache.store_with_key(explicit_key, large_content)

        # This should be fast because it doesn't load content
        result = await cache.has_key(explicit_key)

        assert result is True

    @pytest.mark.asyncio
    async def test_has_key_returns_false_after_cleanup(self, cache):
        """
        has_key() returns False for expired keys after cleanup.

        Given a key that has been stored and then expired
        When cleanup_expired() is run and has_key() is called
        Then it should return False
        """
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        # Create cache with very short TTL
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "short_ttl_cache.db"
            short_ttl_config = PayloadCacheConfig(cache_ttl_seconds=0)  # Immediate expiry
            short_ttl_cache = PayloadCache(db_path=temp_path, config=short_ttl_config)
            await short_ttl_cache.initialize()

            try:
                explicit_key = "delegation:expiring-key"
                await short_ttl_cache.store_with_key(explicit_key, "Will expire")

                # Key exists before cleanup
                assert await short_ttl_cache.has_key(explicit_key) is True

                # Wait a tiny bit and run cleanup
                time.sleep(0.01)
                await short_ttl_cache.cleanup_expired()

                # Key should be gone after cleanup
                assert await short_ttl_cache.has_key(explicit_key) is False
            finally:
                await short_ttl_cache.close()
