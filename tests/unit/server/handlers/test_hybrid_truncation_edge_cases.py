"""Unit tests for Hybrid Search truncation - edge cases.

Story #682: S4 - Hybrid Search with Payload Control
Tests: Edge cases for hybrid truncation

Note: The `cache` fixture is provided by conftest.py in this directory.

These tests follow TDD methodology - written BEFORE verification.
"""

import pytest
from unittest.mock import patch


class TestHybridEdgeCases:
    """Edge cases for hybrid truncation."""

    @pytest.mark.asyncio
    async def test_empty_fields_handled_correctly(self, cache):
        """Test that empty fields don't cause errors."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        results = [
            {
                "file_path": "/src/empty.py",
                "content": "",
                "code_snippet": "",
                "match_text": "",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # All empty fields should not be truncated
        assert result["content"] == ""
        assert result["has_more"] is False
        assert result["cache_handle"] is None

        assert result["code_snippet"] == ""
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None

        assert result["match_text"] == ""
        assert result["match_text_has_more"] is False
        assert result["match_text_cache_handle"] is None

    @pytest.mark.asyncio
    async def test_exact_boundary_fields(self, cache):
        """Test fields at exactly 2000 chars are NOT truncated."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        exact_content = "C" * 2000
        exact_snippet = "S" * 2000
        exact_match_text = "M" * 2000

        results = [
            {
                "content": exact_content,
                "code_snippet": exact_snippet,
                "match_text": exact_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # At boundary, should NOT be truncated
        assert result["content"] == exact_content
        assert result["has_more"] is False
        assert result["cache_handle"] is None

        assert result["code_snippet"] == exact_snippet
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None

        assert result["match_text"] == exact_match_text
        assert result["match_text_has_more"] is False
        assert result["match_text_cache_handle"] is None

    @pytest.mark.asyncio
    async def test_unicode_content_preserved(self, cache):
        """Test that unicode content is preserved correctly in all fields."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # Actual unicode content larger than 2000 chars
        # CJK: 5 chars per repeat x 500 = 2500 chars
        unicode_content = "Hello" * 500  # 2500 chars with CJK unicode
        # Accented: 11 chars per repeat x 250 = 2750 chars
        unicode_snippet = "cafe emoji " * 250  # 2750 chars
        # Greek: 11 chars per repeat x 250 = 2750 chars
        unicode_match = "alpha beta " * 250  # 2750 chars

        results = [
            {
                "content": unicode_content,
                "code_snippet": unicode_snippet,
                "match_text": unicode_match,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # All should be truncated (all > 2000 chars)
        assert result["has_more"] is True
        assert result["snippet_has_more"] is True
        assert result["match_text_has_more"] is True

        # Retrieve and verify unicode preserved
        content_retrieved = await cache.retrieve(result["cache_handle"], page=0)
        snippet_retrieved = await cache.retrieve(result["snippet_cache_handle"], page=0)
        match_text_retrieved = await cache.retrieve(
            result["match_text_cache_handle"], page=0
        )

        # Unicode content should be correctly preserved
        assert "Hello" in content_retrieved.content
        assert "cafe" in snippet_retrieved.content
        assert "alpha" in match_text_retrieved.content

    @pytest.mark.asyncio
    async def test_null_fields_skipped(self, cache):
        """Test that None/missing fields are handled gracefully."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        results = [
            {
                "file_path": "/src/partial.py",
                "content": "A" * 3000,  # Only content, no FTS fields
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Content should be truncated
        assert "content" not in result
        assert result["preview"] == "A" * 2000
        assert result["has_more"] is True

        # FTS fields should not exist at all
        assert "code_snippet" not in result
        assert "snippet_preview" not in result
        assert "snippet_has_more" not in result
        assert "snippet_cache_handle" not in result

    @pytest.mark.asyncio
    async def test_one_char_over_boundary(self, cache):
        """Test fields at 2001 chars are truncated."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        content_2001 = "X" * 2001

        results = [{"content": content_2001}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # One char over boundary should be truncated
        assert "content" not in result
        assert result["preview"] == "X" * 2000
        assert result["has_more"] is True
        assert result["total_size"] == 2001
        assert result["cache_handle"] is not None
