"""Integration tests for FTS cache retrieval API.

Story #680: S2 - FTS Search with Payload Control
AC4: Cache Retrieval for FTS Fields

These tests use REAL PayloadCache with temporary SQLite database.
NO MOCKS - following MESSI Anti-Mock rule.

Tests verify:
- GET /cache/{snippet_cache_handle}?page=0 returns snippet content page
- GET /cache/{match_text_cache_handle}?page=0 returns match_text content page
- Pagination works as defined in S1
"""

import pytest
from httpx import AsyncClient, ASGITransport

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)


class TestFtsCacheRetrievalEndpoint:
    """Tests for FTS cache retrieval via GET /cache/{handle} endpoint (AC4).

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
    async def test_fts_snippet_cache_retrieval(self, app_with_cache, real_cache):
        """Test that snippet_cache_handle can be retrieved via REST API."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation
        from unittest.mock import patch

        # Create a large FTS result
        large_snippet = "SNIPPET_CONTENT" * 200  # 3000 chars
        results = [{"code_snippet": large_snippet, "file_path": "/test.py"}]

        # Apply truncation to get cache handle
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = real_cache
            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        assert result["snippet_has_more"] is True
        snippet_handle = result["snippet_cache_handle"]

        # Retrieve via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{snippet_handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        # Content should be the full snippet (fits in one page of 5000 chars)
        assert data["content"] == large_snippet
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_fts_match_text_cache_retrieval(self, app_with_cache, real_cache):
        """Test that match_text_cache_handle can be retrieved via REST API."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation
        from unittest.mock import patch

        # Create a large match_text result
        large_match_text = "MATCH_TEXT_DATA" * 250  # 3750 chars
        results = [{"match_text": large_match_text, "file_path": "/test.py"}]

        # Apply truncation to get cache handle
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = real_cache
            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        assert result["match_text_has_more"] is True
        match_text_handle = result["match_text_cache_handle"]

        # Retrieve via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{match_text_handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == large_match_text
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_fts_independent_handles_retrieval(self, app_with_cache, real_cache):
        """Test that both snippet and match_text handles retrieve correct content."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation
        from unittest.mock import patch

        # Create result with both large fields
        snippet_content = "SNIPPET" * 500  # 3500 chars
        match_text_content = "MATCHTEXT" * 400  # 3600 chars
        results = [
            {
                "code_snippet": snippet_content,
                "match_text": match_text_content,
                "file_path": "/test.py",
            }
        ]

        # Apply truncation
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = real_cache
            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        snippet_handle = result["snippet_cache_handle"]
        match_text_handle = result["match_text_cache_handle"]

        # Verify handles are different
        assert snippet_handle != match_text_handle

        # Retrieve both via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            snippet_response = await client.get(f"/cache/{snippet_handle}?page=0")
            match_text_response = await client.get(f"/cache/{match_text_handle}?page=0")

        # Verify snippet content
        assert snippet_response.status_code == 200
        snippet_data = snippet_response.json()
        assert snippet_data["content"] == snippet_content

        # Verify match_text content
        assert match_text_response.status_code == 200
        match_text_data = match_text_response.json()
        assert match_text_data["content"] == match_text_content

    @pytest.mark.asyncio
    async def test_fts_pagination_for_very_large_content(self, app_with_cache, real_cache):
        """Test pagination works for FTS content larger than max_fetch_size."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation
        from unittest.mock import patch

        # Create content that spans multiple pages (>5000 chars per page)
        page1_content = "A" * 5000
        page2_content = "B" * 5000
        large_snippet = page1_content + page2_content  # 10000 chars total

        results = [{"code_snippet": large_snippet, "file_path": "/test.py"}]

        # Apply truncation
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = real_cache
            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        snippet_handle = result["snippet_cache_handle"]

        # Retrieve page 0
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page0_response = await client.get(f"/cache/{snippet_handle}?page=0")
            page1_response = await client.get(f"/cache/{snippet_handle}?page=1")

        # Verify page 0
        assert page0_response.status_code == 200
        page0_data = page0_response.json()
        assert page0_data["content"] == page1_content
        assert page0_data["page"] == 0
        assert page0_data["total_pages"] == 2
        assert page0_data["has_more"] is True

        # Verify page 1
        assert page1_response.status_code == 200
        page1_data = page1_response.json()
        assert page1_data["content"] == page2_content
        assert page1_data["page"] == 1
        assert page1_data["total_pages"] == 2
        assert page1_data["has_more"] is False

    @pytest.mark.asyncio
    async def test_fts_cache_expired_handle_returns_404(self, app_with_cache):
        """Test that expired/invalid FTS cache handle returns 404."""
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/cache/non-existent-fts-handle?page=0")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "cache_expired"
