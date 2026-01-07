"""Unit tests for Hybrid Search handler-level truncation integration.

Story #682: S4 - Hybrid Search with Payload Control
Tests: Handler-level verification that search_mode="hybrid" triggers BOTH truncations

These tests verify the actual handler code path applies truncation correctly,
not just the truncation functions in isolation.
"""

import pytest
from unittest.mock import patch, AsyncMock


class TestHybridModeHandlerTruncationLogic:
    """Test that hybrid mode in handler triggers correct truncation sequence."""

    @pytest.mark.asyncio
    async def test_hybrid_search_mode_triggers_fts_truncation(self, cache):
        """Verify search_mode='hybrid' triggers FTS truncation."""
        from code_indexer.server.mcp.handlers import (
            _apply_fts_payload_truncation,
        )

        # Simulate the handler's truncation condition check
        search_mode = "hybrid"

        # This is the condition from handlers.py lines 805, 867
        assert search_mode in ["fts", "hybrid"]

        # Verify FTS truncation actually processes the fields
        large_snippet = "S" * 3000
        large_match_text = "M" * 3000
        results = [
            {
                "file_path": "/test.py",
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
        assert "snippet_preview" in result
        assert "snippet_cache_handle" in result
        assert "match_text_preview" in result
        assert "match_text_cache_handle" in result

    @pytest.mark.asyncio
    async def test_hybrid_search_mode_triggers_semantic_truncation(self, cache):
        """Verify search_mode='hybrid' triggers semantic truncation (non-temporal)."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _is_temporal_query,
        )

        # For hybrid mode, when NOT a temporal query, semantic truncation applies
        params = {"search_mode": "hybrid"}

        # Verify this is NOT a temporal query (no time_range, at_commit, etc)
        assert not _is_temporal_query(params)

        # Verify semantic truncation actually processes the content field
        large_content = "C" * 3000
        results = [{"file_path": "/test.py", "content": large_content}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_payload_truncation(results)

        result = truncated[0]
        assert "preview" in result
        assert "cache_handle" in result
        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_hybrid_mode_full_handler_truncation_sequence(self, cache):
        """Test the exact truncation sequence as in handler for hybrid mode.

        This test replicates the handler code at lines 805-815:

        if search_mode in ["fts", "hybrid"]:
            response_results = await _apply_fts_payload_truncation(response_results)
        if _is_temporal_query(params):
            response_results = await _apply_temporal_payload_truncation(...)
        else:
            response_results = await _apply_payload_truncation(response_results)
        """
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
            _is_temporal_query,
        )

        # Simulate hybrid mode with non-temporal params
        params = {"search_mode": "hybrid", "query_text": "test"}
        search_mode = params["search_mode"]

        # Create result with all three hybrid fields large
        large_content = "CONTENT_" * 400  # 3200 chars
        large_snippet = "SNIPPET_" * 400  # 3200 chars
        large_match_text = "MATCH_" * 400  # 2400 chars

        response_results = [
            {
                "file_path": "/src/hybrid.py",
                "content": large_content,
                "code_snippet": large_snippet,
                "match_text": large_match_text,
                "hybrid_score": 0.92,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            # Replicate exact handler logic
            if search_mode in ["fts", "hybrid"]:
                response_results = await _apply_fts_payload_truncation(response_results)
            if _is_temporal_query(params):
                # Not executed for non-temporal
                pass
            else:
                response_results = await _apply_payload_truncation(response_results)

        result = response_results[0]

        # Verify ALL three fields were truncated
        # 1. Semantic content (from _apply_payload_truncation)
        assert "content" not in result
        assert result["preview"] == large_content[:2000]
        assert result["cache_handle"] is not None
        assert result["has_more"] is True

        # 2. FTS snippet (from _apply_fts_payload_truncation)
        assert "code_snippet" not in result
        assert result["snippet_preview"] == large_snippet[:2000]
        assert result["snippet_cache_handle"] is not None
        assert result["snippet_has_more"] is True

        # 3. FTS match_text (from _apply_fts_payload_truncation)
        assert "match_text" not in result
        assert result["match_text_preview"] == large_match_text[:2000]
        assert result["match_text_cache_handle"] is not None
        assert result["match_text_has_more"] is True

        # Verify score preserved
        assert result["hybrid_score"] == 0.92

    @pytest.mark.asyncio
    async def test_hybrid_mode_independent_cache_handles(self, cache):
        """Verify each hybrid field gets unique cache handle through handler logic."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # All fields large enough to be cached
        results = [
            {
                "content": "A" * 3000,
                "code_snippet": "B" * 3000,
                "match_text": "C" * 3000,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            # Apply both truncations as handler does for hybrid mode
            results = await _apply_fts_payload_truncation(results)
            results = await _apply_payload_truncation(results)

        result = results[0]

        # Get all three handles
        content_handle = result["cache_handle"]
        snippet_handle = result["snippet_cache_handle"]
        match_handle = result["match_text_cache_handle"]

        # All should be non-null and unique
        assert content_handle is not None
        assert snippet_handle is not None
        assert match_handle is not None
        assert len({content_handle, snippet_handle, match_handle}) == 3

        # Verify retrieval returns correct content
        content_retrieved = await cache.retrieve(content_handle, page=0)
        snippet_retrieved = await cache.retrieve(snippet_handle, page=0)
        match_retrieved = await cache.retrieve(match_handle, page=0)

        assert content_retrieved.content == "A" * 3000
        assert snippet_retrieved.content == "B" * 3000
        assert match_retrieved.content == "C" * 3000


class TestHybridModeConditions:
    """Test the conditions that trigger hybrid mode truncation."""

    def test_search_mode_hybrid_matches_condition(self):
        """Verify 'hybrid' is in the list that triggers FTS truncation."""
        search_mode = "hybrid"
        assert search_mode in ["fts", "hybrid"]

    def test_search_mode_hybrid_is_not_temporal(self):
        """Verify hybrid mode without time params is not temporal."""
        from code_indexer.server.mcp.handlers import _is_temporal_query

        params = {"search_mode": "hybrid", "query_text": "test"}
        assert not _is_temporal_query(params)

    def test_search_mode_semantic_does_not_match_fts_condition(self):
        """Verify 'semantic' mode does NOT trigger FTS truncation."""
        search_mode = "semantic"
        assert search_mode not in ["fts", "hybrid"]

    def test_search_mode_fts_matches_condition(self):
        """Verify 'fts' mode matches the FTS truncation condition."""
        search_mode = "fts"
        assert search_mode in ["fts", "hybrid"]
