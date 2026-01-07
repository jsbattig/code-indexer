"""
E2E Tests for FTS Search Payload Control (Story #680).

CRITICAL REQUIREMENT: This test uses ZERO mocks - all real components:
- Real PayloadCache with real SQLite database
- Real FTS truncation and cache retrieval
- Real MCP tool invocation

Tests verify the complete FTS user workflow:
1. Large FTS content is truncated with cache handle for later retrieval
2. Both snippet and match_text fields can be cached independently
3. Cached FTS content can be retrieved via MCP get_cached_content tool
4. Pagination works for FTS cached content
"""

import pytest
from unittest.mock import patch, Mock

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)
from code_indexer.server.auth.user_manager import User, UserRole


class TestFtsPayloadCacheE2E:
    """E2E tests for FTS PayloadCache truncation functionality."""

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
    async def test_fts_large_snippet_truncation_workflow(self, cache_with_standard_config):
        """E2E: Large FTS snippet is truncated with cache handle for retrieval."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_snippet = "def example_function():\n" + "    # Code line\n" * 200
        results = [
            {
                "file_path": "/src/example.py",
                "code_snippet": large_snippet,
                "line_number": 1,
                "similarity_score": 0.95,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Verify truncation happened
        assert result["snippet_has_more"] is True
        assert len(result["snippet_preview"]) == 2000
        assert result["snippet_cache_handle"] is not None

        # Verify full content can be retrieved
        retrieved = await cache_with_standard_config.retrieve(
            result["snippet_cache_handle"], page=0
        )
        assert retrieved.content == large_snippet
        assert retrieved.page == 0
        assert retrieved.has_more is False

    @pytest.mark.asyncio
    async def test_fts_large_match_text_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large FTS match_text is truncated with cache handle for retrieval."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_match_text = "pattern_match" * 300  # 3900 chars
        results = [
            {
                "file_path": "/src/example.py",
                "match_text": large_match_text,
                "line_number": 10,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Verify truncation happened
        assert result["match_text_has_more"] is True
        assert len(result["match_text_preview"]) == 2000
        assert result["match_text_cache_handle"] is not None

        # Verify full content can be retrieved
        retrieved = await cache_with_standard_config.retrieve(
            result["match_text_cache_handle"], page=0
        )
        assert retrieved.content == large_match_text

    @pytest.mark.asyncio
    async def test_fts_both_fields_independent_caching(self, cache_with_standard_config):
        """E2E: Both snippet and match_text are cached independently."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        snippet_content = "SNIPPET_DATA_" * 200  # 2600 chars
        match_text_content = "MATCH_TEXT_DATA_" * 200  # 3200 chars
        results = [
            {
                "file_path": "/src/test.py",
                "code_snippet": snippet_content,
                "match_text": match_text_content,
                "line_number": 5,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Both should be truncated with independent handles
        assert result["snippet_has_more"] is True
        assert result["match_text_has_more"] is True
        assert result["snippet_cache_handle"] != result["match_text_cache_handle"]

        # Retrieve each independently and verify correct content
        snippet_retrieved = await cache_with_standard_config.retrieve(
            result["snippet_cache_handle"], page=0
        )
        match_text_retrieved = await cache_with_standard_config.retrieve(
            result["match_text_cache_handle"], page=0
        )

        assert snippet_retrieved.content == snippet_content
        assert match_text_retrieved.content == match_text_content

    @pytest.mark.asyncio
    async def test_fts_small_content_no_truncation(self, cache_with_standard_config):
        """E2E: Small FTS content is returned in full without caching."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        small_snippet = "def hello(): pass"
        small_match_text = "hello"
        results = [
            {
                "file_path": "/src/hello.py",
                "code_snippet": small_snippet,
                "match_text": small_match_text,
                "line_number": 1,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Neither should be truncated
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None
        assert result["code_snippet"] == small_snippet

        assert result["match_text_has_more"] is False
        assert result["match_text_cache_handle"] is None
        assert result["match_text"] == small_match_text


class TestFtsMcpCacheRetrievalE2E:
    """E2E tests for MCP get_cached_content tool with FTS handles (AC5)."""

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
    async def test_mcp_get_cached_content_for_fts_snippet(self, cache, mock_user):
        """E2E: MCP get_cached_content tool works with FTS snippet handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_fts_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create and truncate FTS result
        large_snippet = "FTS_SNIPPET_CONTENT_" * 150  # 3000 chars
        results = [{"code_snippet": large_snippet, "file_path": "/test.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)

        snippet_handle = truncated[0]["snippet_cache_handle"]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": snippet_handle, "page": 0}, mock_user
            )

        # Parse MCP response
        data = json.loads(mcp_result["content"][0]["text"])

        assert data["success"] is True
        assert data["content"] == large_snippet
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_mcp_get_cached_content_for_fts_match_text(self, cache, mock_user):
        """E2E: MCP get_cached_content tool works with FTS match_text handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_fts_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create and truncate FTS result
        large_match_text = "MATCH_TEXT_PATTERN_" * 150  # 2850 chars
        results = [{"match_text": large_match_text, "file_path": "/test.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)

        match_text_handle = truncated[0]["match_text_cache_handle"]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": match_text_handle, "page": 0}, mock_user
            )

        # Parse MCP response
        data = json.loads(mcp_result["content"][0]["text"])

        assert data["success"] is True
        assert data["content"] == large_match_text
        assert data["page"] == 0

    @pytest.mark.asyncio
    async def test_mcp_pagination_for_fts_content(self, cache, mock_user):
        """E2E: MCP pagination works for large FTS cached content."""
        from code_indexer.server.mcp.handlers import (
            _apply_fts_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create content that spans multiple pages
        page1_content = "A" * 5000
        page2_content = "B" * 5000
        large_snippet = page1_content + page2_content

        results = [{"code_snippet": large_snippet, "file_path": "/test.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_fts_payload_truncation(results)

        snippet_handle = truncated[0]["snippet_cache_handle"]

        # Retrieve page 0 via MCP
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            page0_result = await handle_get_cached_content(
                {"handle": snippet_handle, "page": 0}, mock_user
            )
            page1_result = await handle_get_cached_content(
                {"handle": snippet_handle, "page": 1}, mock_user
            )

        # Verify page 0
        page0_data = json.loads(page0_result["content"][0]["text"])
        assert page0_data["success"] is True
        assert page0_data["content"] == page1_content
        assert page0_data["page"] == 0
        assert page0_data["total_pages"] == 2
        assert page0_data["has_more"] is True

        # Verify page 1
        page1_data = json.loads(page1_result["content"][0]["text"])
        assert page1_data["success"] is True
        assert page1_data["content"] == page2_content
        assert page1_data["page"] == 1
        assert page1_data["has_more"] is False

    @pytest.mark.asyncio
    async def test_mcp_expired_fts_handle_returns_error(self, cache, mock_user):
        """E2E: MCP returns error for expired/invalid FTS cache handle."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content
        import json

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": "non-existent-fts-handle", "page": 0}, mock_user
            )

        data = json.loads(mcp_result["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data
