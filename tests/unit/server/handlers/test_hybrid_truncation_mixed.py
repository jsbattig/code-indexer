"""Unit tests for Hybrid Search truncation - mixed result handling.

Story #682: S4 - Hybrid Search with Payload Control
Tests: AC4 - Mixed Result Handling

These tests follow TDD methodology - written BEFORE verification.
"""

import pytest
from unittest.mock import patch


class TestAC4MixedResultHandling:
    """AC4: Mixed Result Handling - different result types with different fields."""

    @pytest.mark.asyncio
    async def test_semantic_only_result_in_hybrid_search(self, cache):
        """Test result with only semantic content (no FTS fields)."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_content = "C" * 3000
        results = [
            {
                "file_path": "/src/semantic.py",
                "content": large_content,
                "semantic_score": 0.90,
                "source": "semantic",
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
        assert result["preview"] == "C" * 2000
        assert result["has_more"] is True
        assert result["cache_handle"] is not None

        # FTS fields should not exist
        assert "code_snippet" not in result
        assert "snippet_preview" not in result
        assert "match_text" not in result
        assert "match_text_preview" not in result

    @pytest.mark.asyncio
    async def test_fts_only_result_in_hybrid_search(self, cache):
        """Test result with only FTS fields (no semantic content)."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_snippet = "S" * 3000
        large_match_text = "M" * 3000
        results = [
            {
                "file_path": "/src/fts.py",
                "code_snippet": large_snippet,
                "match_text": large_match_text,
                "fts_score": 0.95,
                "source": "fts",
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # FTS fields should be truncated
        assert "code_snippet" not in result
        assert result["snippet_preview"] == "S" * 2000
        assert result["snippet_has_more"] is True
        assert result["snippet_cache_handle"] is not None

        assert "match_text" not in result
        assert result["match_text_preview"] == "M" * 2000
        assert result["match_text_has_more"] is True
        assert result["match_text_cache_handle"] is not None

        # Semantic fields should not exist (no content field to truncate)
        assert "content" not in result
        assert "preview" not in result

    @pytest.mark.asyncio
    async def test_mixed_results_list(self, cache):
        """Test a list with semantic, FTS, and hybrid results."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        results = [
            # Semantic result
            {
                "file_path": "/src/semantic.py",
                "content": "A" * 3000,
                "semantic_score": 0.90,
                "source": "semantic",
            },
            # FTS result
            {
                "file_path": "/src/fts.py",
                "code_snippet": "B" * 3000,
                "fts_score": 0.95,
                "source": "fts",
            },
            # Hybrid result (all fields)
            {
                "file_path": "/src/hybrid.py",
                "content": "C" * 3000,
                "code_snippet": "D" * 3000,
                "match_text": "E" * 3000,
                "hybrid_score": 0.92,
                "source": "hybrid",
            },
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        # Verify semantic result
        semantic_result = truncated[0]
        assert "content" not in semantic_result
        assert semantic_result["preview"] == "A" * 2000
        assert semantic_result["has_more"] is True

        # Verify FTS result
        fts_result = truncated[1]
        assert "code_snippet" not in fts_result
        assert fts_result["snippet_preview"] == "B" * 2000
        assert fts_result["snippet_has_more"] is True

        # Verify hybrid result (all fields truncated)
        hybrid_result = truncated[2]
        assert "content" not in hybrid_result
        assert hybrid_result["preview"] == "C" * 2000
        assert hybrid_result["has_more"] is True

        assert "code_snippet" not in hybrid_result
        assert hybrid_result["snippet_preview"] == "D" * 2000
        assert hybrid_result["snippet_has_more"] is True

        assert "match_text" not in hybrid_result
        assert hybrid_result["match_text_preview"] == "E" * 2000
        assert hybrid_result["match_text_has_more"] is True

    @pytest.mark.asyncio
    async def test_score_fields_preserved(self, cache):
        """Test that all score fields are preserved without modification."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        results = [
            {
                "content": "X" * 3000,
                "code_snippet": "Y" * 3000,
                "match_text": "Z" * 3000,
                "semantic_score": 0.85,
                "fts_score": 0.90,
                "hybrid_score": 0.92,
                "similarity_score": 0.88,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # All score fields must be preserved
        assert result["semantic_score"] == 0.85
        assert result["fts_score"] == 0.90
        assert result["hybrid_score"] == 0.92
        assert result["similarity_score"] == 0.88
