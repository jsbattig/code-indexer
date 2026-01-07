"""
E2E Tests for Semantic Search Payload Control (Story #679).

CRITICAL REQUIREMENT: This test uses ZERO mocks - all real components:
- Real PayloadCache with real SQLite database
- Real content truncation and cache retrieval
- Real TTL expiration testing

Tests verify the complete user workflow:
1. Large content is truncated with cache handle for later retrieval
2. Small content is returned in full without caching
3. Large content can be retrieved in pages
4. TTL expiration removes expired content
"""

import asyncio
import pytest

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
    CacheNotFoundError,
)


class TestPayloadCacheE2E:
    """E2E tests for PayloadCache functionality."""

    @pytest.fixture
    async def cache_with_short_ttl(self, tmp_path):
        """Create PayloadCache with short TTL for expiration testing."""
        config = PayloadCacheConfig(
            preview_size_chars=100,
            max_fetch_size_chars=200,
            cache_ttl_seconds=2,
            cleanup_interval_seconds=1,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        cache.start_background_cleanup()
        yield cache
        await cache.close()

    @pytest.fixture
    async def standard_cache(self, tmp_path):
        """Create PayloadCache with standard settings."""
        config = PayloadCacheConfig(
            preview_size_chars=2000,
            max_fetch_size_chars=5000,
            cache_ttl_seconds=900,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_large_content_truncation_workflow(self, standard_cache):
        """E2E: Large content is truncated with cache handle for later retrieval."""
        large_content = "X" * 3000

        result = await standard_cache.truncate_result(large_content)

        assert result["has_more"] is True
        assert result["preview"] == "X" * 2000
        assert result["cache_handle"] is not None
        assert result["total_size"] == 3000

        retrieved = await standard_cache.retrieve(result["cache_handle"], page=0)
        assert retrieved.content == "X" * 3000
        assert retrieved.page == 0
        assert retrieved.has_more is False

    @pytest.mark.asyncio
    async def test_small_content_no_truncation(self, standard_cache):
        """E2E: Small content is returned in full without caching."""
        small_content = "Small content under 2000 chars"

        result = await standard_cache.truncate_result(small_content)

        assert result["has_more"] is False
        assert result["cache_handle"] is None
        assert result["content"] == small_content
        assert "preview" not in result

    @pytest.mark.asyncio
    async def test_pagination_workflow(self, standard_cache):
        """E2E: Large content can be retrieved in pages."""
        page1_content = "A" * 5000
        page2_content = "B" * 5000
        page3_content = "C" * 2500
        full_content = page1_content + page2_content + page3_content

        handle = await standard_cache.store(full_content)

        result0 = await standard_cache.retrieve(handle, page=0)
        assert result0.content == page1_content
        assert result0.page == 0
        assert result0.total_pages == 3
        assert result0.has_more is True

        result1 = await standard_cache.retrieve(handle, page=1)
        assert result1.content == page2_content
        assert result1.page == 1
        assert result1.has_more is True

        result2 = await standard_cache.retrieve(handle, page=2)
        assert result2.content == page3_content
        assert result2.page == 2
        assert result2.has_more is False

    @pytest.mark.asyncio
    async def test_ttl_expiration_workflow(self, cache_with_short_ttl):
        """E2E: Cache entries expire after TTL and cleanup removes them."""
        content = "Content that will expire"
        handle = await cache_with_short_ttl.store(content)

        result = await cache_with_short_ttl.retrieve(handle, page=0)
        assert result.content == content

        await asyncio.sleep(4)

        with pytest.raises(CacheNotFoundError):
            await cache_with_short_ttl.retrieve(handle, page=0)


class TestRestApiCacheRetrievalE2E:
    """E2E tests for REST API cache retrieval endpoint."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create PayloadCache for testing."""
        config = PayloadCacheConfig(
            preview_size_chars=100,
            max_fetch_size_chars=200,
            cache_ttl_seconds=900,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.fixture
    def app_with_cache(self, cache):
        """Get app with cache attached."""
        from code_indexer.server.app import app

        original = getattr(app.state, "payload_cache", None)
        app.state.payload_cache = cache
        yield app
        if original is None:
            if hasattr(app.state, "payload_cache"):
                delattr(app.state, "payload_cache")
        else:
            app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_complete_truncation_and_retrieval_workflow(self, app_with_cache, cache):
        """E2E: Complete workflow - truncate, then retrieve via REST API."""
        from httpx import AsyncClient, ASGITransport

        large_content = "Y" * 500
        truncated = await cache.truncate_result(large_content)

        assert truncated["has_more"] is True
        handle = truncated["cache_handle"]

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["content"]) == 200
        assert data["page"] == 0
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_expired_cache_returns_error(self, app_with_cache):
        """E2E: Expired or non-existent cache returns proper error."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/cache/non-existent-handle?page=0")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "cache_expired"
