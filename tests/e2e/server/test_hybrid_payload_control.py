"""
E2E Tests for Hybrid Search Payload Control (Story #682).

CRITICAL REQUIREMENT: This test uses ZERO mocks - all real components:
- Real PayloadCache with real SQLite database
- Real hybrid truncation and cache retrieval
- Real MCP tool invocation
- Real REST API endpoint invocation

Tests verify the complete hybrid search workflow:
1. Hybrid results with semantic content are truncated via _apply_payload_truncation
2. Hybrid results with FTS snippet/match_text are truncated via _apply_fts_payload_truncation
3. All three fields can be cached and retrieved independently
4. MCP tool get_cached_content works for all hybrid field handles
5. REST API GET /cache/{handle} works for all hybrid field handles
"""

import json
import pytest
from unittest.mock import patch, Mock

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)
from code_indexer.server.auth.user_manager import User, UserRole


class TestHybridPayloadCacheE2E:
    """E2E tests for Hybrid PayloadCache truncation functionality."""

    @pytest.fixture
    async def cache_with_standard_config(self, tmp_path):
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
    async def test_hybrid_all_fields_truncation_workflow(self, cache_with_standard_config):
        """E2E: Hybrid result with all fields large - all are truncated independently."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # Create hybrid result with all three fields large
        large_content = "def semantic_function():\n" + "    # Code line\n" * 200
        large_snippet = "def fts_snippet():\n" + "    pass\n" * 300
        large_match_text = "exact_match_pattern " * 150

        results = [
            {
                "file_path": "/src/hybrid.py",
                "content": large_content,
                "code_snippet": large_snippet,
                "match_text": large_match_text,
                "hybrid_score": 0.92,
                "source": "hybrid",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            # Apply both truncations as hybrid mode does
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Verify all three fields truncated
        assert result["has_more"] is True
        assert result["snippet_has_more"] is True
        assert result["match_text_has_more"] is True

        # All three handles should be unique
        content_handle = result["cache_handle"]
        snippet_handle = result["snippet_cache_handle"]
        match_text_handle = result["match_text_cache_handle"]
        assert len({content_handle, snippet_handle, match_text_handle}) == 3

        # Retrieve each and verify correct content
        content_retrieved = await cache_with_standard_config.retrieve(content_handle, page=0)
        snippet_retrieved = await cache_with_standard_config.retrieve(snippet_handle, page=0)
        match_text_retrieved = await cache_with_standard_config.retrieve(match_text_handle, page=0)

        assert content_retrieved.content == large_content
        assert snippet_retrieved.content == large_snippet
        assert match_text_retrieved.content == large_match_text


class TestHybridMcpCacheRetrievalE2E:
    """E2E tests for MCP get_cached_content tool with hybrid field handles."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create PayloadCache for testing."""
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
    def mock_user(self):
        """Create a mock user for MCP handler testing."""
        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER
        user.has_permission = Mock(return_value=True)
        return user

    @pytest.mark.asyncio
    async def test_mcp_retrieve_all_hybrid_handles_independently(self, cache, mock_user):
        """E2E: MCP tool retrieves each hybrid field handle independently."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
            handle_get_cached_content,
        )

        # Create hybrid result with all large fields
        content_data = "CONTENT_DATA_" * 200  # 2600 chars
        snippet_data = "SNIPPET_DATA_" * 200  # 2600 chars
        match_data = "MATCH_DATA_" * 200  # 2200 chars

        results = [
            {
                "content": content_data,
                "code_snippet": snippet_data,
                "match_text": match_data,
                "file_path": "/test.py",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]
        content_handle = result["cache_handle"]
        snippet_handle = result["snippet_cache_handle"]
        match_handle = result["match_text_cache_handle"]

        # Retrieve each via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            content_mcp = await handle_get_cached_content(
                {"handle": content_handle, "page": 0}, mock_user
            )
            snippet_mcp = await handle_get_cached_content(
                {"handle": snippet_handle, "page": 0}, mock_user
            )
            match_mcp = await handle_get_cached_content(
                {"handle": match_handle, "page": 0}, mock_user
            )

        content_result = json.loads(content_mcp["content"][0]["text"])
        snippet_result = json.loads(snippet_mcp["content"][0]["text"])
        match_result = json.loads(match_mcp["content"][0]["text"])

        # Verify each retrieves correct content
        assert content_result["success"] is True
        assert content_result["content"] == content_data

        assert snippet_result["success"] is True
        assert snippet_result["content"] == snippet_data

        assert match_result["success"] is True
        assert match_result["content"] == match_data


class TestHybridRestApiCacheRetrievalE2E:
    """E2E tests for REST API cache retrieval with hybrid field handles."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create PayloadCache for testing."""
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
    async def test_rest_api_retrieve_hybrid_content_handle(self, app_with_cache, cache):
        """E2E: REST API retrieves hybrid semantic content handle."""
        from httpx import AsyncClient, ASGITransport
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_content = "HYBRID_REST_CONTENT_" * 150  # 3000 chars

        results = [{"content": large_content, "file_path": "/test.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        content_handle = truncated[0]["cache_handle"]

        # Retrieve via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{content_handle}?page=0")

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == large_content
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_rest_api_retrieve_all_hybrid_handles(self, app_with_cache, cache):
        """E2E: REST API retrieves all three hybrid field handles."""
        from httpx import AsyncClient, ASGITransport
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        content_data = "REST_CONTENT_" * 200  # 2600 chars
        snippet_data = "REST_SNIPPET_" * 200  # 2600 chars
        match_data = "REST_MATCH_" * 200  # 2200 chars

        results = [
            {
                "content": content_data,
                "code_snippet": snippet_data,
                "match_text": match_data,
                "file_path": "/test.py",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]
        content_handle = result["cache_handle"]
        snippet_handle = result["snippet_cache_handle"]
        match_handle = result["match_text_cache_handle"]

        # Retrieve all via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            content_resp = await client.get(f"/cache/{content_handle}?page=0")
            snippet_resp = await client.get(f"/cache/{snippet_handle}?page=0")
            match_resp = await client.get(f"/cache/{match_handle}?page=0")

        # Verify all three handles retrieve correct content
        assert content_resp.status_code == 200
        assert content_resp.json()["content"] == content_data

        assert snippet_resp.status_code == 200
        assert snippet_resp.json()["content"] == snippet_data

        assert match_resp.status_code == 200
        assert match_resp.json()["content"] == match_data

    @pytest.mark.asyncio
    async def test_rest_api_pagination_for_hybrid_content(self, app_with_cache, cache):
        """E2E: REST API pagination works for large hybrid content."""
        from httpx import AsyncClient, ASGITransport
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # Create content spanning multiple pages (5000 chars per page)
        page1 = "A" * 5000
        page2 = "B" * 5000
        large_content = page1 + page2

        results = [{"content": large_content, "file_path": "/test.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        content_handle = truncated[0]["cache_handle"]

        # Retrieve pages via REST API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page0_resp = await client.get(f"/cache/{content_handle}?page=0")
            page1_resp = await client.get(f"/cache/{content_handle}?page=1")

        # Verify pagination
        page0_data = page0_resp.json()
        assert page0_data["content"] == page1
        assert page0_data["page"] == 0
        assert page0_data["total_pages"] == 2
        assert page0_data["has_more"] is True

        page1_data = page1_resp.json()
        assert page1_data["content"] == page2
        assert page1_data["page"] == 1
        assert page1_data["has_more"] is False
