"""Unit tests for Regex context truncation logic.

Story #684: S6 - Regex Search with Payload Control
AC2: Regex Context Truncation (context_before, context_after fields)

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import uuid
from unittest.mock import patch


class TestAC2ContextBeforeTruncation:
    """AC2: Regex context_before truncation tests."""

    @pytest.mark.asyncio
    async def test_large_context_before_is_truncated(self, cache):
        """Test that large context_before is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        # Create large context_before (many lines that exceed 2000 chars total)
        large_context = ["Line " + "X" * 100 for _ in range(30)]  # ~3000 chars
        results = [
            {
                "file_path": "/path/to/file.py",
                "line_number": 35,
                "column": 1,
                "line_content": "match line",
                "context_before": large_context,
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Should have context_before preview fields
        assert "context_before_preview" in result
        assert result["context_before_has_more"] is True
        assert "context_before_cache_handle" in result
        assert "context_before_total_size" in result

        # Original context_before should be removed
        assert "context_before" not in result

        # Verify handle is valid UUID
        uuid.UUID(result["context_before_cache_handle"], version=4)

    @pytest.mark.asyncio
    async def test_small_context_before_not_truncated(self, cache):
        """Test that small context_before is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        small_context = ["line 1", "line 2", "line 3"]
        results = [
            {
                "line_content": "match",
                "context_before": small_context,
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Should keep original context array
        assert result["context_before"] == small_context
        assert result["context_before_cache_handle"] is None
        assert result["context_before_has_more"] is False


class TestAC2ContextAfterTruncation:
    """AC2: Regex context_after truncation tests."""

    @pytest.mark.asyncio
    async def test_large_context_after_is_truncated(self, cache):
        """Test that large context_after is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        # Create large context_after (many lines that exceed 2000 chars total)
        large_context = ["Line " + "Y" * 100 for _ in range(30)]  # ~3000 chars
        results = [
            {
                "file_path": "/path/to/file.py",
                "line_number": 5,
                "column": 1,
                "line_content": "match line",
                "context_before": [],
                "context_after": large_context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Should have context_after preview fields
        assert "context_after_preview" in result
        assert result["context_after_has_more"] is True
        assert "context_after_cache_handle" in result
        assert "context_after_total_size" in result

        # Original context_after should be removed
        assert "context_after" not in result

    @pytest.mark.asyncio
    async def test_small_context_after_not_truncated(self, cache):
        """Test that small context_after is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        small_context = ["line 4", "line 5"]
        results = [
            {
                "line_content": "match",
                "context_before": [],
                "context_after": small_context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Should keep original context array
        assert result["context_after"] == small_context
        assert result["context_after_cache_handle"] is None
        assert result["context_after_has_more"] is False


class TestAC2EmptyContextArrays:
    """AC2: Empty context arrays tests."""

    @pytest.mark.asyncio
    async def test_empty_context_arrays(self, cache):
        """Test that empty context arrays are handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        results = [
            {
                "line_content": "match",
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Empty arrays should be preserved as-is
        assert result["context_before"] == []
        assert result["context_after"] == []
        assert result["context_before_cache_handle"] is None
        assert result["context_before_has_more"] is False
        assert result["context_after_cache_handle"] is None
        assert result["context_after_has_more"] is False

    @pytest.mark.asyncio
    async def test_both_contexts_small(self, cache):
        """Test that both small context arrays are preserved."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        small_before = ["before1", "before2"]
        small_after = ["after1", "after2"]
        results = [
            {
                "line_content": "match",
                "context_before": small_before,
                "context_after": small_after,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        assert result["context_before"] == small_before
        assert result["context_after"] == small_after
        assert result["context_before_cache_handle"] is None
        assert result["context_after_cache_handle"] is None
