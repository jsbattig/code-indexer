"""Unit tests for FTS independent caching per field.

Story #680: S2 - FTS Search with Payload Control
AC3: Independent Caching Per Field

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import uuid
from unittest.mock import patch


class TestAC3IndependentCachingPerField:
    """AC3: Independent Caching Per Field tests.

    When both snippet and match_text exceed 2000 chars, each gets its OWN cache handle.
    Handles can be retrieved independently via cache API.
    """

    @pytest.mark.asyncio
    async def test_both_fields_large_get_independent_handles(self, cache):
        """Test that large snippet and large match_text each get their own handle."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_snippet = "S" * 4000
        large_match_text = "T" * 5000
        results = [
            {
                "file_path": "/path/to/file.py",
                "code_snippet": large_snippet,
                "match_text": large_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Both should be truncated
        assert result["snippet_has_more"] is True
        assert result["match_text_has_more"] is True

        # Each should have its own handle
        snippet_handle = result["snippet_cache_handle"]
        match_text_handle = result["match_text_cache_handle"]

        assert snippet_handle is not None
        assert match_text_handle is not None
        # Handles must be different
        assert snippet_handle != match_text_handle

        # Verify handles are valid UUIDs
        uuid.UUID(snippet_handle, version=4)
        uuid.UUID(match_text_handle, version=4)

    @pytest.mark.asyncio
    async def test_independent_cache_retrieval(self, cache):
        """Test that each handle retrieves the correct content."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        snippet_content = "SNIPPET" * 500  # 3500 chars
        match_text_content = "MATCHTEXT" * 400  # 3600 chars

        results = [
            {
                "code_snippet": snippet_content,
                "match_text": match_text_content,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        snippet_handle = result["snippet_cache_handle"]
        match_text_handle = result["match_text_cache_handle"]

        # Retrieve each independently
        snippet_retrieved = await cache.retrieve(snippet_handle, page=0)
        match_text_retrieved = await cache.retrieve(match_text_handle, page=0)

        # Verify correct content was cached
        assert (
            snippet_content in snippet_retrieved.content
            or snippet_retrieved.content in snippet_content
        )
        assert (
            match_text_content in match_text_retrieved.content
            or match_text_retrieved.content in match_text_content
        )

    @pytest.mark.asyncio
    async def test_only_snippet_large(self, cache):
        """Test when only snippet is large, match_text is small."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        large_snippet = "S" * 3000
        small_match_text = "small match"
        results = [
            {
                "code_snippet": large_snippet,
                "match_text": small_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Snippet should be truncated
        assert result["snippet_has_more"] is True
        assert "snippet_cache_handle" in result
        assert result["snippet_cache_handle"] is not None
        assert "snippet_preview" in result

        # Match text should NOT be truncated
        assert result["match_text_has_more"] is False
        assert result["match_text_cache_handle"] is None
        assert result["match_text"] == small_match_text

    @pytest.mark.asyncio
    async def test_only_match_text_large(self, cache):
        """Test when only match_text is large, snippet is small."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        small_snippet = "small snippet"
        large_match_text = "M" * 3000
        results = [
            {
                "code_snippet": small_snippet,
                "match_text": large_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Snippet should NOT be truncated
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None
        assert result["code_snippet"] == small_snippet

        # Match text should be truncated
        assert result["match_text_has_more"] is True
        assert "match_text_cache_handle" in result
        assert result["match_text_cache_handle"] is not None
        assert "match_text_preview" in result

    @pytest.mark.asyncio
    async def test_neither_field_large(self, cache):
        """Test when neither field is large, both keep original content."""
        from code_indexer.server.mcp.handlers import _apply_fts_payload_truncation

        small_snippet = "small snippet"
        small_match_text = "small match"
        results = [
            {
                "code_snippet": small_snippet,
                "match_text": small_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]

        # Neither should be truncated
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None
        assert result["code_snippet"] == small_snippet

        assert result["match_text_has_more"] is False
        assert result["match_text_cache_handle"] is None
        assert result["match_text"] == small_match_text
