"""Unit tests for Temporal code_snippet truncation logic.

Story #681 Gap Fix: Temporal Search code_snippet Payload Control

PROBLEM: Temporal search results return full code_snippet (git diff content) without
truncation or caching, unlike semantic/FTS/regex search which properly truncate and
cache large content.

EVIDENCE from testing:
- Temporal returns: code_snippet (FULL content), NO cache_handle, NO has_more
- Semantic returns: preview (truncated), cache_handle, has_more=true, total_size

This test file validates that:
- code_snippet > preview_size gets truncated
- code_snippet_cache_handle is added to results
- code_snippet_has_more is set to true when truncated
- code_snippet_total_size contains original content length
- Small code_snippet is NOT truncated (kept as-is)

These tests follow TDD methodology - written BEFORE implementation fix.
"""

import pytest
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch


# Use preview size from PayloadCacheConfig default
PREVIEW_SIZE = 2000


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "payload_cache.db"


@pytest.fixture
async def cache(temp_db_path):
    """Create and initialize a PayloadCache instance for testing."""
    from code_indexer.server.cache.payload_cache import (
        PayloadCache,
        PayloadCacheConfig,
    )

    config = PayloadCacheConfig(preview_size_chars=PREVIEW_SIZE)
    cache = PayloadCache(db_path=temp_db_path, config=config)
    await cache.initialize()
    yield cache
    await cache.close()


class TestTemporalCodeSnippetTruncation:
    """Tests for code_snippet truncation in temporal search results."""

    @pytest.mark.asyncio
    async def test_large_code_snippet_is_truncated(self, cache):
        """Test that code_snippet > preview_size chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_snippet = "X" * (PREVIEW_SIZE + 1000)
        results = [
            {
                "file_path": "/path/to/file.py",
                "line_number": 1,
                "code_snippet": large_snippet,
                "similarity_score": 0.95,
                "repository_alias": "test-repo-global",
                "temporal_context": {
                    "first_seen": "2024-01-01T00:00:00Z",
                    "last_seen": "2024-06-01T00:00:00Z",
                    "commit_count": 3,
                },
                "metadata": {
                    "commit_hash": "abc123",
                    "commit_date": "2024-01-01",
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        assert len(truncated) == 1
        result = truncated[0]

        # Should have code_snippet preview fields (following FTS pattern)
        assert "code_snippet_preview" in result
        assert result["code_snippet_preview"] == "X" * PREVIEW_SIZE
        assert result["code_snippet_has_more"] is True
        assert result["code_snippet_total_size"] == PREVIEW_SIZE + 1000
        assert "code_snippet_cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["code_snippet_cache_handle"], version=4)

        # Original code_snippet should be removed
        assert "code_snippet" not in result

        # Other fields should be preserved
        assert result["file_path"] == "/path/to/file.py"
        assert result["line_number"] == 1
        assert result["similarity_score"] == 0.95
        assert result["repository_alias"] == "test-repo-global"
        assert result["temporal_context"]["commit_count"] == 3
        assert result["metadata"]["commit_hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_small_code_snippet_not_truncated(self, cache):
        """Test that code_snippet <= preview_size chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        small_snippet = "Small file content"
        results = [
            {
                "file_path": "/path/to/file.py",
                "code_snippet": small_snippet,
                "similarity_score": 0.95,
                "temporal_context": {"commit_count": 1},
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Should keep original code_snippet
        assert result["code_snippet"] == small_snippet
        assert result["code_snippet_cache_handle"] is None
        assert result["code_snippet_has_more"] is False

        # Should NOT have preview fields
        assert "code_snippet_preview" not in result
        assert "code_snippet_total_size" not in result

    @pytest.mark.asyncio
    async def test_code_snippet_at_exact_boundary_not_truncated(self, cache):
        """Test that code_snippet exactly at preview_size chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        exact_snippet = "Y" * PREVIEW_SIZE
        results = [{"code_snippet": exact_snippet, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Exactly at boundary should NOT be truncated
        assert result["code_snippet"] == exact_snippet
        assert result["code_snippet_cache_handle"] is None
        assert result["code_snippet_has_more"] is False

    @pytest.mark.asyncio
    async def test_code_snippet_empty_not_truncated(self, cache):
        """Test that empty code_snippet is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [{"code_snippet": "", "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        assert result["code_snippet"] == ""
        assert result["code_snippet_cache_handle"] is None
        assert result["code_snippet_has_more"] is False

    @pytest.mark.asyncio
    async def test_code_snippet_unicode_truncated_at_char_boundary(self, cache):
        """Test that Unicode code_snippet is truncated at char boundary, not byte."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        # Unicode content - emojis are 1+ chars but multiple bytes
        unicode_snippet = "\U0001F600" * (PREVIEW_SIZE + 1000)

        results = [{"code_snippet": unicode_snippet, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Should truncate at char boundary, not byte boundary
        assert len(result["code_snippet_preview"]) == PREVIEW_SIZE
        assert result["code_snippet_preview"] == "\U0001F600" * PREVIEW_SIZE
        assert result["code_snippet_total_size"] == PREVIEW_SIZE + 1000

    @pytest.mark.asyncio
    async def test_cache_not_available_returns_original(self, cache):
        """Test that results are unchanged when cache is not available."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_snippet = "X" * (PREVIEW_SIZE + 1000)
        results = [{"code_snippet": large_snippet, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = None  # No cache

            truncated = await _apply_temporal_payload_truncation(results)

        # Results should be unchanged
        assert truncated[0]["code_snippet"] == large_snippet
