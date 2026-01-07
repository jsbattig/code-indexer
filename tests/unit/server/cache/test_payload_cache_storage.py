"""Unit tests for PayloadCache SQLite storage operations.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC2: Cache Storage with SQLite WAL

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import tempfile
import time
import uuid
from pathlib import Path


class TestPayloadCacheSQLiteWAL:
    """Tests for PayloadCache SQLite WAL mode (AC2)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.mark.asyncio
    async def test_database_created_with_wal_mode(self, temp_db_path):
        """Test that SQLite database is created with WAL mode enabled."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)

        # Initialize the database
        await cache.initialize()

        # Verify WAL mode by checking pragma
        import aiosqlite

        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute("PRAGMA journal_mode") as cursor:
                result = await cursor.fetchone()
                assert result[0].lower() == "wal"

        await cache.close()

    @pytest.mark.asyncio
    async def test_table_schema_created(self, temp_db_path):
        """Test that payload_cache table is created with correct schema."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        import aiosqlite

        async with aiosqlite.connect(str(temp_db_path)) as db:
            # Check table exists
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='payload_cache'"
            ) as cursor:
                result = await cursor.fetchone()
                assert result is not None

            # Check columns
            async with db.execute("PRAGMA table_info(payload_cache)") as cursor:
                columns = {row[1]: row[2] for row in await cursor.fetchall()}
                assert "handle" in columns
                assert "content" in columns
                assert "created_at" in columns
                assert "total_size" in columns

        await cache.close()

    @pytest.mark.asyncio
    async def test_index_created_on_created_at(self, temp_db_path):
        """Test that index is created on created_at column for TTL cleanup."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()

        import aiosqlite

        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='idx_payload_cache_created_at'"
            ) as cursor:
                result = await cursor.fetchone()
                assert result is not None

        await cache.close()


class TestPayloadCacheStoreRetrieve:
    """Tests for PayloadCache store and retrieve operations (AC2, AC4)."""

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
    async def test_store_returns_uuid4_handle(self, cache):
        """Test that store() returns a valid UUID4 handle."""
        content = "Test content for caching"
        handle = await cache.store(content)

        # Verify it's a valid UUID4
        parsed_uuid = uuid.UUID(handle, version=4)
        assert str(parsed_uuid) == handle

    @pytest.mark.asyncio
    async def test_store_saves_content_and_metadata(self, cache, temp_db_path):
        """Test that store() saves content with correct metadata."""
        content = "Test content for caching with metadata"
        before_store = time.time()
        handle = await cache.store(content)
        after_store = time.time()

        import aiosqlite

        async with aiosqlite.connect(str(temp_db_path)) as db:
            async with db.execute(
                "SELECT handle, content, created_at, total_size "
                "FROM payload_cache WHERE handle = ?",
                (handle,),
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == handle
                assert row[1] == content
                assert before_store <= row[2] <= after_store
                assert row[3] == len(content)

    @pytest.mark.asyncio
    async def test_retrieve_page_0_returns_first_chunk(self, cache):
        """Test retrieve() page 0 returns first max_fetch_size_chars."""
        # Create content larger than max_fetch_size_chars (5000)
        content = "A" * 10000
        handle = await cache.store(content)

        result = await cache.retrieve(handle, page=0)

        assert result.content == "A" * 5000
        assert result.page == 0
        assert result.total_pages == 2
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_retrieve_page_1_returns_second_chunk(self, cache):
        """Test retrieve() page 1 returns chars 5000-9999."""
        content = "A" * 5000 + "B" * 5000
        handle = await cache.store(content)

        result = await cache.retrieve(handle, page=1)

        assert result.content == "B" * 5000
        assert result.page == 1
        assert result.total_pages == 2
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_retrieve_small_content_single_page(self, cache):
        """Test retrieve() with content smaller than max_fetch_size_chars."""
        content = "Small content"
        handle = await cache.store(content)

        result = await cache.retrieve(handle, page=0)

        assert result.content == content
        assert result.page == 0
        assert result.total_pages == 1
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_retrieve_invalid_handle_raises_error(self, cache):
        """Test retrieve() with invalid handle raises CacheNotFoundError."""
        from code_indexer.server.cache.payload_cache import CacheNotFoundError

        with pytest.raises(CacheNotFoundError) as exc_info:
            await cache.retrieve("invalid-handle", page=0)

        assert "invalid-handle" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retrieve_page_out_of_range_raises_error(self, cache):
        """Test retrieve() with page number beyond total pages."""
        from code_indexer.server.cache.payload_cache import CacheNotFoundError

        content = "Small content"
        handle = await cache.store(content)

        with pytest.raises(CacheNotFoundError):
            await cache.retrieve(handle, page=10)
