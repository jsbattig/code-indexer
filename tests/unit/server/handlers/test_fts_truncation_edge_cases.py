"""Unit tests for FTS truncation edge cases.

Story #680: S2 - FTS Search with Payload Control

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
from unittest.mock import patch


class TestFtsTruncationEdgeCases:
    """Edge case tests for FTS truncation."""

    @pytest.mark.asyncio
    async def test_empty_results_list(self, cache):
        """Test that empty results list is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation([])

        assert truncated == []

    @pytest.mark.asyncio
    async def test_multiple_results_truncated_independently(self, cache):
        """Test that multiple results in list are each truncated independently."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        results = [
            {"code_snippet": "A" * 3000, "match_text": "short"},  # snippet large
            {"code_snippet": "short", "match_text": "B" * 3000},  # match_text large
            {"code_snippet": "C" * 3000, "match_text": "D" * 3000},  # both large
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        assert len(truncated) == 3

        # First result: snippet large, match_text small
        assert truncated[0]["snippet_has_more"] is True
        assert truncated[0]["match_text_has_more"] is False

        # Second result: snippet small, match_text large
        assert truncated[1]["snippet_has_more"] is False
        assert truncated[1]["match_text_has_more"] is True

        # Third result: both large
        assert truncated[2]["snippet_has_more"] is True
        assert truncated[2]["match_text_has_more"] is True

        # All handles should be unique
        handles = [
            truncated[0].get("snippet_cache_handle"),
            truncated[1].get("match_text_cache_handle"),
            truncated[2].get("snippet_cache_handle"),
            truncated[2].get("match_text_cache_handle"),
        ]
        # Remove None values and check uniqueness
        valid_handles = [h for h in handles if h is not None]
        assert len(valid_handles) == len(set(valid_handles))

    @pytest.mark.asyncio
    async def test_unicode_content_handled_correctly(self, cache):
        """Test that unicode content is truncated correctly by character count."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        # Use unicode characters - each is 1 character but multiple bytes
        unicode_snippet = "\u4e2d\u6587" * 1500  # 3000 Chinese characters

        results = [{"code_snippet": unicode_snippet}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Should be truncated (3000 chars > 2000)
        assert result["snippet_has_more"] is True
        assert len(result["snippet_preview"]) == 2000
        assert result["snippet_total_size"] == 3000

    @pytest.mark.asyncio
    async def test_cache_unavailable_returns_results_unchanged(self):
        """Test that results are returned unchanged when cache is unavailable."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_snippet = "X" * 3000
        results = [{"code_snippet": large_snippet, "match_text": "test"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = None  # Cache unavailable

            truncated = await _apply_fts_payload_truncation(results)

        # Results should be unchanged when cache unavailable
        assert truncated[0]["code_snippet"] == large_snippet
        assert truncated[0]["match_text"] == "test"

    @pytest.mark.asyncio
    async def test_very_large_content_over_100kb(self, cache):
        """Test handling of very large content (>100KB)."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        # 150KB of content
        very_large_snippet = "X" * 150000

        results = [{"code_snippet": very_large_snippet}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        assert result["snippet_has_more"] is True
        assert len(result["snippet_preview"]) == 2000
        assert result["snippet_total_size"] == 150000
        assert result["snippet_cache_handle"] is not None

        # Verify we can retrieve the full content
        retrieved = await cache.retrieve(result["snippet_cache_handle"], page=0)
        assert retrieved.total_pages > 1  # Should span multiple pages

    @pytest.mark.asyncio
    async def test_result_with_no_truncatable_fields(self, cache):
        """Test result with no code_snippet or match_text fields."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        results = [{"file_path": "/path.py", "line_number": 10, "score": 0.9}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Original fields should be preserved
        assert result["file_path"] == "/path.py"
        assert result["line_number"] == 10
        assert result["score"] == 0.9

        # No truncation metadata added for missing fields
        assert "snippet_has_more" not in result
        assert "match_text_has_more" not in result
