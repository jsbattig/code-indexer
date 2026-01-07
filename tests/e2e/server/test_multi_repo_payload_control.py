"""
E2E Tests for Multi-repo Search Payload Control (Story #683).

CRITICAL REQUIREMENT: This test uses ZERO mocks - all real components:
- Real PayloadCache with real SQLite database
- Real content truncation and cache retrieval
- Real multi-repo result processing

Tests verify the complete user workflow:
1. Multi-repo results with large content get truncated with cache handles
2. Repository attribution is preserved in truncated results
3. Cache handles can be retrieved via REST API without repo context
"""

import pytest


class TestMultiRepoPayloadCacheE2E:
    """E2E tests for multi-repo payload cache functionality."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create PayloadCache for testing."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

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
    async def test_multi_repo_large_content_truncation_and_retrieval(
        self, app_with_cache, cache
    ):
        """E2E: Multi-repo large content is truncated and retrievable via cache."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation

        # Simulate multi-repo results with large content
        multi_repo_results = [
            {
                "source_repo": "repo-alpha",
                "file_path": "/src/main.py",
                "content": "ALPHA_FULL_CONTENT_" + "A" * 500,
                "score": 0.92,
                "language": "python",
            },
            {
                "source_repo": "repo-beta",
                "file_path": "/lib/utils.py",
                "content": "BETA_FULL_CONTENT_" + "B" * 500,
                "score": 0.88,
                "language": "python",
            },
        ]

        # Apply truncation (simulates what _omni_search_code does internally)
        truncated = await _apply_payload_truncation(multi_repo_results)

        # Verify truncation applied
        assert len(truncated) == 2

        # Both should be truncated
        assert truncated[0]["has_more"] is True
        assert truncated[0]["cache_handle"] is not None
        assert "preview" in truncated[0]
        assert "content" not in truncated[0]

        assert truncated[1]["has_more"] is True
        assert truncated[1]["cache_handle"] is not None
        assert "preview" in truncated[1]
        assert "content" not in truncated[1]

        # Repository attribution preserved
        assert truncated[0]["source_repo"] == "repo-alpha"
        assert truncated[1]["source_repo"] == "repo-beta"

        # Retrieve via cache API (no repo context needed)
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Retrieve first result's content
            response_alpha = await client.get(
                f"/cache/{truncated[0]['cache_handle']}?page=0"
            )
            assert response_alpha.status_code == 200
            data_alpha = response_alpha.json()
            assert "ALPHA_FULL_CONTENT_" in data_alpha["content"]

            # Retrieve second result's content
            response_beta = await client.get(
                f"/cache/{truncated[1]['cache_handle']}?page=0"
            )
            assert response_beta.status_code == 200
            data_beta = response_beta.json()
            assert "BETA_FULL_CONTENT_" in data_beta["content"]

    @pytest.mark.asyncio
    async def test_mixed_content_multi_repo(self, app_with_cache, cache):
        """E2E: Mixed large/small content from multiple repos handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation

        # Simulate multi-repo results with mixed content sizes
        multi_repo_results = [
            {
                "source_repo": "repo-alpha",
                "file_path": "/src/main.py",
                "content": "LARGE_" + "X" * 500,  # Large - truncated
                "score": 0.92,
            },
            {
                "source_repo": "repo-beta",
                "file_path": "/lib/small.py",
                "content": "small content",  # Small - not truncated
                "score": 0.85,
            },
            {
                "source_repo": "repo-gamma",
                "file_path": "/pkg/core.py",
                "content": "GAMMA_LARGE_" + "Y" * 400,  # Large - truncated
                "score": 0.80,
            },
        ]

        truncated = await _apply_payload_truncation(multi_repo_results)

        # Verify mixed handling
        assert len(truncated) == 3

        # Result 0: Large content truncated
        assert truncated[0]["has_more"] is True
        assert truncated[0]["cache_handle"] is not None
        assert truncated[0]["source_repo"] == "repo-alpha"
        assert "LARGE_" in truncated[0]["preview"]

        # Result 1: Small content not truncated
        assert truncated[1]["has_more"] is False
        assert truncated[1]["cache_handle"] is None
        assert truncated[1]["content"] == "small content"
        assert truncated[1]["source_repo"] == "repo-beta"

        # Result 2: Large content truncated
        assert truncated[2]["has_more"] is True
        assert truncated[2]["cache_handle"] is not None
        assert truncated[2]["source_repo"] == "repo-gamma"
        assert "GAMMA_LARGE_" in truncated[2]["preview"]

    @pytest.mark.asyncio
    async def test_pagination_retrieval_for_multi_repo_handles(
        self, app_with_cache, cache
    ):
        """E2E: Paginated retrieval works for multi-repo cache handles."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from httpx import AsyncClient, ASGITransport

        # Create large content that spans multiple pages
        # With max_fetch_size_chars=200, 500 chars = 3 pages
        page1 = "PAGE1_" + "A" * 194
        page2 = "PAGE2_" + "B" * 194
        page3 = "PAGE3_" + "C" * 100
        large_content = page1 + page2 + page3

        multi_repo_results = [
            {
                "source_repo": "repo-alpha",
                "file_path": "/src/main.py",
                "content": large_content,
                "score": 0.92,
            },
        ]

        truncated = await _apply_payload_truncation(multi_repo_results)
        handle = truncated[0]["cache_handle"]

        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Get page 0
            resp0 = await client.get(f"/cache/{handle}?page=0")
            assert resp0.status_code == 200
            data0 = resp0.json()
            assert "PAGE1_" in data0["content"]
            assert data0["page"] == 0
            assert data0["has_more"] is True

            # Get page 1
            resp1 = await client.get(f"/cache/{handle}?page=1")
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert "PAGE2_" in data1["content"]
            assert data1["page"] == 1
            assert data1["has_more"] is True

            # Get page 2 (last page)
            resp2 = await client.get(f"/cache/{handle}?page=2")
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert "PAGE3_" in data2["content"]
            assert data2["page"] == 2
            assert data2["has_more"] is False

    @pytest.mark.asyncio
    async def test_semantic_code_snippet_truncation(self, app_with_cache, cache):
        """E2E: Real semantic search format with code_snippet field is truncated."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from httpx import AsyncClient, ASGITransport

        # Real semantic search result format from QueryResult.to_dict()
        # Uses code_snippet field, NOT content field
        semantic_results = [
            {
                "file_path": "/src/auth.py",
                "line_number": 42,
                "code_snippet": "SEMANTIC_CODE_" + "X" * 500,  # Real format
                "similarity_score": 0.95,
                "repository_alias": "my-repo",
                "source_repo": "repo-alpha",
            },
        ]

        truncated = await _apply_payload_truncation(semantic_results)

        # Verify code_snippet is truncated (not content)
        assert len(truncated) == 1
        result = truncated[0]
        assert result["has_more"] is True
        assert result["cache_handle"] is not None
        assert "SEMANTIC_CODE_" in result["preview"]
        assert "code_snippet" not in result  # code_snippet removed

        # Retrieve via cache API
        transport = ASGITransport(app=app_with_cache)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/cache/{result['cache_handle']}?page=0")
            assert response.status_code == 200
            data = response.json()
            assert "SEMANTIC_CODE_" in data["content"]
