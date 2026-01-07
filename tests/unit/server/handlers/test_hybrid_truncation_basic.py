"""Unit tests for Hybrid Search truncation - basic functionality.

Story #682: S4 - Hybrid Search with Payload Control
Tests: Core integration, AC1, AC2, AC3

These tests follow TDD methodology - written BEFORE verification.
"""

import pytest
import uuid
from unittest.mock import patch


class TestHybridTruncationFunctionIntegration:
    """Test that hybrid mode applies both truncation functions."""

    @pytest.mark.asyncio
    async def test_hybrid_mode_applies_both_semantic_and_fts_truncation(self, cache):
        """Test that hybrid search results have ALL fields truncated.

        AC4: Mixed Result Handling - Results from hybrid have ALL fields truncated.

        A hybrid result can have:
        - content (semantic) -> truncated by _apply_payload_truncation
        - code_snippet (FTS) -> truncated by _apply_fts_payload_truncation
        - match_text (FTS) -> truncated by _apply_fts_payload_truncation
        """
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # Create a hybrid result with all three fields large
        large_content = "CONTENT" * 500  # 3500 chars
        large_snippet = "SNIPPET" * 500  # 3500 chars
        large_match_text = "MATCHTEXT" * 300  # 2700 chars

        results = [
            {
                "file_path": "/src/hybrid.py",
                "content": large_content,
                "code_snippet": large_snippet,
                "match_text": large_match_text,
                "hybrid_score": 0.92,
                "source": "hybrid",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            # Simulate hybrid mode processing order (FTS first, then semantic)
            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Verify semantic content truncation (AC1)
        assert "content" not in result
        assert "preview" in result
        assert result["preview"] == large_content[:2000]
        assert result["cache_handle"] is not None
        assert result["has_more"] is True
        assert result["total_size"] == len(large_content)

        # Verify FTS snippet truncation (AC2)
        assert "code_snippet" not in result
        assert "snippet_preview" in result
        assert result["snippet_preview"] == large_snippet[:2000]
        assert result["snippet_cache_handle"] is not None
        assert result["snippet_has_more"] is True
        assert result["snippet_total_size"] == len(large_snippet)

        # Verify FTS match_text truncation (AC3)
        assert "match_text" not in result
        assert "match_text_preview" in result
        assert result["match_text_preview"] == large_match_text[:2000]
        assert result["match_text_cache_handle"] is not None
        assert result["match_text_has_more"] is True
        assert result["match_text_total_size"] == len(large_match_text)

        # Verify non-truncated fields preserved
        assert result["file_path"] == "/src/hybrid.py"
        assert result["hybrid_score"] == 0.92
        assert result["source"] == "hybrid"


class TestAC1HybridContentTruncation:
    """AC1: Hybrid Content Truncation (Semantic Component)."""

    @pytest.mark.asyncio
    async def test_large_content_is_truncated_in_hybrid_result(self, cache):
        """Test that content > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_content = "X" * 3000
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": large_content,
                "code_snippet": "small snippet",
                "hybrid_score": 0.85,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Semantic content should be truncated
        assert "content" not in result
        assert result["preview"] == "X" * 2000
        assert result["has_more"] is True
        assert result["total_size"] == 3000
        assert result["cache_handle"] is not None
        uuid.UUID(result["cache_handle"], version=4)

        # FTS fields should remain (small, not truncated)
        assert result["code_snippet"] == "small snippet"
        assert result["snippet_has_more"] is False
        assert result["snippet_cache_handle"] is None

    @pytest.mark.asyncio
    async def test_small_content_not_truncated_in_hybrid_result(self, cache):
        """Test that content <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        small_content = "Small content"
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": small_content,
                "code_snippet": "small snippet",
                "hybrid_score": 0.85,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Semantic content should NOT be truncated
        assert result["content"] == small_content
        assert result["cache_handle"] is None
        assert result["has_more"] is False


class TestAC2HybridSnippetTruncation:
    """AC2: Hybrid Snippet Truncation (FTS Component)."""

    @pytest.mark.asyncio
    async def test_large_snippet_is_truncated_in_hybrid_result(self, cache):
        """Test that code_snippet > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_snippet = "S" * 3000
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": "small content",
                "code_snippet": large_snippet,
                "hybrid_score": 0.85,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # FTS snippet should be truncated
        assert "code_snippet" not in result
        assert result["snippet_preview"] == "S" * 2000
        assert result["snippet_has_more"] is True
        assert result["snippet_total_size"] == 3000
        assert result["snippet_cache_handle"] is not None
        uuid.UUID(result["snippet_cache_handle"], version=4)

        # Semantic field should remain (small, not truncated)
        assert result["content"] == "small content"
        assert result["has_more"] is False
        assert result["cache_handle"] is None


class TestAC3HybridMatchTextTruncation:
    """AC3: Hybrid Match Text Truncation (FTS Component)."""

    @pytest.mark.asyncio
    async def test_large_match_text_is_truncated_in_hybrid_result(self, cache):
        """Test that match_text > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_match_text = "M" * 3000
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": "small content",
                "match_text": large_match_text,
                "hybrid_score": 0.85,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # FTS match_text should be truncated
        assert "match_text" not in result
        assert result["match_text_preview"] == "M" * 2000
        assert result["match_text_has_more"] is True
        assert result["match_text_total_size"] == 3000
        assert result["match_text_cache_handle"] is not None
        uuid.UUID(result["match_text_cache_handle"], version=4)
