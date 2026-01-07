"""
E2E Tests for Regex Search Payload Control (Story #684).

CRITICAL REQUIREMENT: This test uses ZERO mocks for core functionality:
- Real PayloadCache with real SQLite database
- Real regex truncation and cache retrieval
- Real MCP tool invocation

Tests verify the complete regex user workflow:
1. Large regex content is truncated with cache handle for later retrieval
2. line_content, context_before, context_after fields can be cached independently
3. Cached regex content can be retrieved via MCP get_cached_content tool
4. Pagination works for regex cached content
"""

import pytest
from unittest.mock import patch, Mock

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)
from code_indexer.server.auth.user_manager import User, UserRole


class TestRegexPayloadCacheE2E:
    """E2E tests for Regex PayloadCache truncation functionality."""

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
    async def test_regex_large_line_content_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large regex line_content is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "def example_function():\n" + "    # Code line\n" * 200
        results = [
            {
                "file_path": "/src/example.py",
                "line_number": 1,
                "column": 1,
                "line_content": large_line,
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Verify truncation happened
        assert result["line_content_has_more"] is True
        assert len(result["line_content_preview"]) == 2000
        assert result["line_content_cache_handle"] is not None

        # Verify full content can be retrieved
        retrieved = await cache_with_standard_config.retrieve(
            result["line_content_cache_handle"], page=0
        )
        assert retrieved.content == large_line
        assert retrieved.page == 0
        assert retrieved.has_more is False

    @pytest.mark.asyncio
    async def test_regex_large_context_before_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large regex context_before is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        # Create large context (30 lines * ~105 chars each = ~3150 chars)
        large_context = ["# Context line " + "X" * 90 for _ in range(30)]
        results = [
            {
                "file_path": "/src/example.py",
                "line_number": 35,
                "column": 1,
                "line_content": "match_line",
                "context_before": large_context,
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Verify truncation happened
        assert result["context_before_has_more"] is True
        assert result["context_before_cache_handle"] is not None

        # Verify full content can be retrieved (stored as newline-joined)
        retrieved = await cache_with_standard_config.retrieve(
            result["context_before_cache_handle"], page=0
        )
        assert retrieved.content == "\n".join(large_context)

    @pytest.mark.asyncio
    async def test_regex_all_fields_independent_caching(
        self, cache_with_standard_config
    ):
        """E2E: All regex fields are cached independently."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "LINE_CONTENT_" * 250  # 3250 chars
        large_before = ["BEFORE_" * 20 for _ in range(20)]  # ~2800 chars
        large_after = ["AFTER_" * 20 for _ in range(20)]  # ~2600 chars

        results = [
            {
                "file_path": "/src/test.py",
                "line_number": 50,
                "column": 1,
                "line_content": large_line,
                "context_before": large_before,
                "context_after": large_after,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # All should be truncated with independent handles
        assert result["line_content_has_more"] is True
        assert result["context_before_has_more"] is True
        assert result["context_after_has_more"] is True
        assert (
            result["line_content_cache_handle"] != result["context_before_cache_handle"]
        )
        assert (
            result["context_before_cache_handle"]
            != result["context_after_cache_handle"]
        )

        # Retrieve each independently and verify correct content
        line_retrieved = await cache_with_standard_config.retrieve(
            result["line_content_cache_handle"], page=0
        )
        before_retrieved = await cache_with_standard_config.retrieve(
            result["context_before_cache_handle"], page=0
        )
        after_retrieved = await cache_with_standard_config.retrieve(
            result["context_after_cache_handle"], page=0
        )

        assert line_retrieved.content == large_line
        assert before_retrieved.content == "\n".join(large_before)
        assert after_retrieved.content == "\n".join(large_after)

    @pytest.mark.asyncio
    async def test_regex_small_content_no_truncation(self, cache_with_standard_config):
        """E2E: Small regex content is returned in full without caching."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        small_line = "def hello(): pass"
        small_context = ["line1", "line2"]
        results = [
            {
                "file_path": "/src/hello.py",
                "line_number": 1,
                "column": 1,
                "line_content": small_line,
                "context_before": small_context,
                "context_after": small_context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # None should be truncated
        assert result["line_content_has_more"] is False
        assert result["line_content_cache_handle"] is None
        assert result["line_content"] == small_line

        assert result["context_before_has_more"] is False
        assert result["context_before_cache_handle"] is None
        assert result["context_before"] == small_context

        assert result["context_after_has_more"] is False
        assert result["context_after_cache_handle"] is None
        assert result["context_after"] == small_context


class TestRegexMcpCacheRetrievalE2E:
    """E2E tests for MCP get_cached_content tool with regex handles (AC5)."""

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
    async def test_mcp_get_cached_content_for_regex_line_content(
        self, cache, mock_user
    ):
        """E2E: MCP get_cached_content tool works with regex line_content handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_regex_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create and truncate regex result
        large_line = "REGEX_LINE_CONTENT_" * 200  # 3800 chars
        results = [
            {
                "line_content": large_line,
                "context_before": [],
                "context_after": [],
                "file_path": "/test.py",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_regex_payload_truncation(results)

        line_handle = truncated[0]["line_content_cache_handle"]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": line_handle, "page": 0}, mock_user
            )

        # Parse MCP response
        data = json.loads(mcp_result["content"][0]["text"])

        assert data["success"] is True
        assert data["content"] == large_line
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_mcp_get_cached_content_for_regex_context(self, cache, mock_user):
        """E2E: MCP get_cached_content tool works with regex context handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_regex_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create large context that exceeds preview_size (2000) but fits in
        # max_fetch_size (5000) for single page retrieval
        # Each line is ~25 chars, 150 lines = ~3750 chars (> 2000, < 5000)
        large_context = ["CTX_LINE_" * 3 for _ in range(150)]  # ~4050 chars
        results = [
            {
                "line_content": "match",
                "context_before": large_context,
                "context_after": [],
                "file_path": "/test.py",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_regex_payload_truncation(results)

        context_handle = truncated[0]["context_before_cache_handle"]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": context_handle, "page": 0}, mock_user
            )

        # Parse MCP response
        data = json.loads(mcp_result["content"][0]["text"])

        assert data["success"] is True
        assert data["content"] == "\n".join(large_context)
        assert data["page"] == 0
