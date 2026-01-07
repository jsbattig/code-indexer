"""Integration tests for REST cache retrieval API.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC4: REST Cache Retrieval API

These tests use REAL PayloadCache with temporary SQLite database.
NO MOCKS - following MESSI Anti-Mock rule.
"""

import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)


class TestCacheRetrievalEndpoint:
    """Tests for GET /cache/{handle} endpoint (AC4).

    Uses real PayloadCache with temporary SQLite database.
    """

    @pytest.fixture
    async def real_cache(self, tmp_path):
        """Create a real PayloadCache with temporary database."""
        config = PayloadCacheConfig(
            preview_size_chars=2000,
            max_fetch_size_chars=5000,
            cache_ttl_seconds=900,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.fixture
    def app_with_cache(self, real_cache):
        """Get app with real cache attached."""
        from code_indexer.server.app import app

        original = getattr(app.state, "payload_cache", None)
        app.state.payload_cache = real_cache
        yield app
        if original is None:
            if hasattr(app.state, "payload_cache"):
                delattr(app.state, "payload_cache")
        else:
            app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_get_cache_page_0_returns_content(self, app_with_cache, real_cache):
        """Test GET /cache/{handle}?page=0 returns first page content."""
        # Store real content larger than max_fetch_size_chars (5000)
        content = "A" * 5000 + "B" * 5000
        handle = await real_cache.store(content)

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "A" * 5000
        assert data["page"] == 0
        assert data["total_pages"] == 2
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_cache_page_1_returns_second_page(self, app_with_cache, real_cache):
        """Test GET /cache/{handle}?page=1 returns second page content."""
        # Store real content with two pages
        content = "A" * 5000 + "B" * 5000
        handle = await real_cache.store(content)

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}?page=1")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "B" * 5000
        assert data["page"] == 1
        assert data["total_pages"] == 2
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_cache_invalid_handle_returns_404(self, app_with_cache):
        """Test GET /cache/{handle} with invalid handle returns 404."""
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/cache/invalid-handle-uuid?page=0")

        assert response.status_code == 404
        data = response.json()
        # FastAPI HTTPException wraps detail in "detail" key
        assert data["detail"]["error"] == "cache_expired"
        assert "invalid-handle-uuid" in data["detail"]["handle"]

    @pytest.mark.asyncio
    async def test_get_cache_default_page_is_zero(self, app_with_cache, real_cache):
        """Test GET /cache/{handle} without page param defaults to 0."""
        # Store content that fits on one page
        content = "Small test content"
        handle = await real_cache.store(content)

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 0
        assert data["content"] == content
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_cache_small_content_single_page(self, app_with_cache, real_cache):
        """Test GET /cache/{handle} with small content returns full content."""
        content = "This is a small piece of content"
        handle = await real_cache.store(content)

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == content
        assert data["page"] == 0
        assert data["total_pages"] == 1
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_cache_page_out_of_range_returns_404(self, app_with_cache, real_cache):
        """Test GET /cache/{handle}?page=999 returns 404 for out-of-range page."""
        content = "Small content"
        handle = await real_cache.store(content)

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{handle}?page=999")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "cache_expired"

    @pytest.mark.asyncio
    async def test_cache_unavailable_returns_503(self):
        """Test GET /cache/{handle} returns 503 when cache not initialized."""
        from code_indexer.server.app import app

        # Remove payload_cache from app.state
        original = getattr(app.state, "payload_cache", None)
        if hasattr(app.state, "payload_cache"):
            delattr(app.state, "payload_cache")

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/cache/any-handle?page=0")

            assert response.status_code == 503
            data = response.json()
            assert "not available" in data["detail"].lower()
        finally:
            if original is not None:
                app.state.payload_cache = original
