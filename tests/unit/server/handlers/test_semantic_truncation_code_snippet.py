"""Unit tests for Semantic Search Payload Control with code_snippet field (Story #683).

BUG FIX: Real semantic search results from QueryResult.to_dict() use 'code_snippet'
field, not 'content'. The _apply_payload_truncation function must handle both.

These tests verify that:
1. code_snippet field is truncated correctly for large content
2. code_snippet field is preserved for small content

TDD methodology: Tests written BEFORE the fix is implemented.
"""

import pytest


class TestCodeSnippetTruncation:
    """Tests for code_snippet field truncation in semantic search results."""

    @pytest.mark.asyncio
    async def test_code_snippet_large_content_truncated(self, cache_100_chars):
        """Large code_snippet gets preview + cache_handle (BUG FIX VALIDATION)."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            # Real semantic search result format from QueryResult.to_dict()
            results = [
                {
                    "file_path": "/src/auth.py",
                    "line_number": 42,
                    "code_snippet": "X" * 500,  # Real semantic uses code_snippet
                    "similarity_score": 0.95,
                    "repository_alias": "my-repo",
                    "source_repo": None,
                }
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]

            # code_snippet should be truncated
            assert result["has_more"] is True
            assert result["preview"] == "X" * 100
            assert result["cache_handle"] is not None
            assert result["total_size"] == 500

            # code_snippet field should be removed
            assert "code_snippet" not in result

            # Metadata preserved
            assert result["file_path"] == "/src/auth.py"
            assert result["line_number"] == 42
            assert result["similarity_score"] == 0.95
            assert result["repository_alias"] == "my-repo"
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_code_snippet_small_content_preserved(self, cache_100_chars):
        """Small code_snippet is preserved (not truncated)."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "file_path": "/src/small.py",
                    "line_number": 10,
                    "code_snippet": "small content",  # Under 100 chars
                    "similarity_score": 0.85,
                    "repository_alias": "my-repo",
                    "source_repo": None,
                }
            ]

            truncated = await _apply_payload_truncation(results)

            result = truncated[0]

            # Small content not truncated
            assert result["has_more"] is False
            assert result["cache_handle"] is None
            assert result["code_snippet"] == "small content"
            assert "preview" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original
