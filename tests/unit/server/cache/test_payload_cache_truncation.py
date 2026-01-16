"""Unit tests for PayloadCache truncation logic.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC3: Response Truncation for Semantic Search

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import tempfile
import uuid
from pathlib import Path


class TestPayloadCacheTruncation:
    """Tests for content truncation logic (AC3)."""

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

        config = PayloadCacheConfig(preview_size_chars=100)
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_truncate_result_large_content(self, cache):
        """Test truncate_result for content larger than preview_size_chars."""
        large_content = "X" * 500
        result = await cache.truncate_result(large_content)

        assert result["preview"] == "X" * 100
        assert result["has_more"] is True
        assert result["total_size"] == 500
        assert "cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["cache_handle"], version=4)

    @pytest.mark.asyncio
    async def test_truncate_result_small_content(self, cache):
        """Test truncate_result for content smaller than preview_size_chars."""
        small_content = "Small content"
        result = await cache.truncate_result(small_content)

        assert result["content"] == small_content
        assert result["has_more"] is False
        assert result["cache_handle"] is None

    @pytest.mark.asyncio
    async def test_truncate_result_exact_boundary(self, cache):
        """Test truncate_result for content exactly at preview_size_chars."""
        exact_content = "Y" * 100
        result = await cache.truncate_result(exact_content)

        # Content exactly at boundary should NOT be truncated
        assert result["content"] == exact_content
        assert result["has_more"] is False
        assert result["cache_handle"] is None

    @pytest.mark.asyncio
    async def test_truncate_result_empty_content(self, cache):
        """Test truncate_result for empty content."""
        result = await cache.truncate_result("")

        assert result["content"] == ""
        assert result["has_more"] is False
        assert result["cache_handle"] is None

    @pytest.mark.asyncio
    async def test_truncate_result_cached_handle_is_retrievable(self, cache):
        """Test that cache_handle from truncate_result can be retrieved."""
        large_content = "Z" * 500
        result = await cache.truncate_result(large_content)

        # Should be able to retrieve full content using handle
        handle = result["cache_handle"]
        retrieved = await cache.retrieve(handle, page=0)

        assert retrieved.content == large_content[: cache.config.max_fetch_size_chars]
