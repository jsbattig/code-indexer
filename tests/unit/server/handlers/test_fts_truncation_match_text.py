"""Unit tests for FTS match_text truncation logic.

Story #680: S2 - FTS Search with Payload Control
AC2: FTS Match Text Truncation (match_text field)

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import uuid
from unittest.mock import patch


class TestAC2MatchTextTruncation:
    """AC2: FTS Match Text Truncation tests.

    When match_text > 2000 chars: return match_text_preview, match_text_cache_handle,
                                  match_text_has_more=true, match_text_total_size
    When match_text <= 2000 chars: return full match_text, match_text_cache_handle=null,
                                   match_text_has_more=false
    """

    @pytest.mark.asyncio
    async def test_large_match_text_is_truncated(self, cache):
        """Test that match_text > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_match_text = "M" * 3500
        results = [
            {
                "file_path": "/path/to/file.py",
                "match_text": large_match_text,
                "line_number": 10,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Should have preview fields
        assert "match_text_preview" in result
        assert result["match_text_preview"] == "M" * 2000
        assert result["match_text_has_more"] is True
        assert result["match_text_total_size"] == 3500
        assert "match_text_cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["match_text_cache_handle"], version=4)

        # Original match_text should be removed
        assert "match_text" not in result

    @pytest.mark.asyncio
    async def test_small_match_text_not_truncated(self, cache):
        """Test that match_text <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        small_match_text = "Small match text"
        results = [{"match_text": small_match_text}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Should keep original match_text
        assert result["match_text"] == small_match_text
        assert result["match_text_cache_handle"] is None
        assert result["match_text_has_more"] is False

        # Should NOT have preview fields
        assert "match_text_preview" not in result
        assert "match_text_total_size" not in result

    @pytest.mark.asyncio
    async def test_match_text_at_exact_boundary_not_truncated(self, cache):
        """Test that match_text exactly at 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        exact_match_text = "Z" * 2000
        results = [{"match_text": exact_match_text}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Exactly at boundary should NOT be truncated
        assert result["match_text"] == exact_match_text
        assert result["match_text_cache_handle"] is None
        assert result["match_text_has_more"] is False

    @pytest.mark.asyncio
    async def test_missing_match_text_handled_gracefully(self, cache):
        """Test that results without match_text field are handled gracefully."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        # Result with only code_snippet, no match_text
        results = [{"code_snippet": "Some code", "file_path": "/path.py"}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Should not fail, should not add match_text fields
        assert "match_text" not in result
        assert "match_text_preview" not in result
        assert "match_text_cache_handle" not in result
        assert "match_text_has_more" not in result
