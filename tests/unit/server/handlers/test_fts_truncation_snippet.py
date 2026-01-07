"""Unit tests for FTS snippet truncation logic.

Story #680: S2 - FTS Search with Payload Control
AC1: FTS Snippet Truncation (code_snippet field)

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import uuid
from unittest.mock import patch


class TestFtsTruncationFunctionExists:
    """Test that _apply_fts_payload_truncation function exists."""

    def test_function_exists_in_handlers_module(self):
        """Test that _apply_fts_payload_truncation is defined in handlers.py."""
        from code_indexer.server.mcp import handlers

        assert hasattr(handlers, "_apply_fts_payload_truncation")
        assert callable(handlers._apply_fts_payload_truncation)


class TestAC1SnippetTruncation:
    """AC1: FTS Snippet Truncation tests.

    When code_snippet > 2000 chars: return snippet_preview, snippet_cache_handle,
                                    snippet_has_more=true, snippet_total_size
    When code_snippet <= 2000 chars: return full code_snippet, snippet_cache_handle=null,
                                     snippet_has_more=false
    """

    @pytest.mark.asyncio
    async def test_large_snippet_is_truncated(self, cache):
        """Test that code_snippet > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_snippet = "X" * 3000
        results = [
            {
                "file_path": "/path/to/file.py",
                "code_snippet": large_snippet,
                "line_number": 10,
                "similarity_score": 0.95,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        assert len(truncated) == 1
        result = truncated[0]

        # Should have preview fields
        assert "snippet_preview" in result
        assert result["snippet_preview"] == "X" * 2000
        assert result["snippet_has_more"] is True
        assert result["snippet_total_size"] == 3000
        assert "snippet_cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["snippet_cache_handle"], version=4)

        # Original code_snippet should be removed
        assert "code_snippet" not in result

        # Other fields preserved
        assert result["file_path"] == "/path/to/file.py"
        assert result["line_number"] == 10
        assert result["similarity_score"] == 0.95

    @pytest.mark.asyncio
    async def test_small_snippet_not_truncated(self, cache):
        """Test that code_snippet <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        small_snippet = "Small code snippet"
        results = [
            {
                "file_path": "/path/to/file.py",
                "code_snippet": small_snippet,
                "line_number": 10,
                "similarity_score": 0.95,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Should keep original code_snippet
        assert result["code_snippet"] == small_snippet
        assert result["snippet_cache_handle"] is None
        assert result["snippet_has_more"] is False

        # Should NOT have preview fields
        assert "snippet_preview" not in result
        assert "snippet_total_size" not in result

    @pytest.mark.asyncio
    async def test_snippet_at_exact_boundary_not_truncated(self, cache):
        """Test that code_snippet exactly at 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        exact_snippet = "Y" * 2000
        results = [{"code_snippet": exact_snippet}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Exactly at boundary should NOT be truncated
        assert result["code_snippet"] == exact_snippet
        assert result["snippet_cache_handle"] is None
        assert result["snippet_has_more"] is False

    @pytest.mark.asyncio
    async def test_empty_snippet_not_truncated(self, cache):
        """Test that empty code_snippet is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        results = [{"code_snippet": ""}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        assert result["code_snippet"] == ""
        assert result["snippet_cache_handle"] is None
        assert result["snippet_has_more"] is False
