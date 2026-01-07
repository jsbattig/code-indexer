"""Unit tests for Temporal content truncation logic (AC1).

Story #681: S3 - Temporal Search with Payload Control

AC1: Temporal Content Truncation
- When content > 2000 chars: return content_preview, content_cache_handle,
                             content_has_more=true, content_total_size
- When content <= 2000 chars: return full content, content_cache_handle=null,
                              content_has_more=false
"""

import pytest
import uuid
from unittest.mock import patch


# Use preview size from PayloadCacheConfig default
PREVIEW_SIZE = 2000


class TestTemporalTruncationFunctionExists:
    """Test that _apply_temporal_payload_truncation function exists."""

    def test_function_exists_in_handlers_module(self):
        """Test that _apply_temporal_payload_truncation is defined in handlers.py."""
        from code_indexer.server.mcp import handlers

        assert hasattr(handlers, "_apply_temporal_payload_truncation")
        assert callable(handlers._apply_temporal_payload_truncation)


class TestAC1TemporalContentTruncation:
    """AC1: Temporal Content Truncation tests."""

    @pytest.mark.asyncio
    async def test_large_content_is_truncated(self, cache):
        """Test that content > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_content = "X" * (PREVIEW_SIZE + 1000)
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": large_content,
                "similarity_score": 0.95,
                "temporal_context": {
                    "commit_hash": "abc123",
                    "commit_date": "2024-01-01T00:00:00Z",
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

        # Should have content preview fields
        assert "content_preview" in result
        assert result["content_preview"] == "X" * PREVIEW_SIZE
        assert result["content_has_more"] is True
        assert result["content_total_size"] == PREVIEW_SIZE + 1000
        assert "content_cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["content_cache_handle"], version=4)

        # Original content should be removed
        assert "content" not in result

        # Other fields preserved
        assert result["file_path"] == "/path/to/file.py"
        assert result["similarity_score"] == 0.95
        assert result["temporal_context"]["commit_hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_small_content_not_truncated(self, cache):
        """Test that content <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        small_content = "Small file content"
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": small_content,
                "similarity_score": 0.95,
                "temporal_context": {"commit_hash": "abc123"},
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Should keep original content
        assert result["content"] == small_content
        assert result["content_cache_handle"] is None
        assert result["content_has_more"] is False

        # Should NOT have preview fields
        assert "content_preview" not in result
        assert "content_total_size" not in result

    @pytest.mark.asyncio
    async def test_content_at_exact_boundary_not_truncated(self, cache):
        """Test that content exactly at 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        exact_content = "Y" * PREVIEW_SIZE
        results = [{"content": exact_content, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Exactly at boundary should NOT be truncated
        assert result["content"] == exact_content
        assert result["content_cache_handle"] is None
        assert result["content_has_more"] is False

    @pytest.mark.asyncio
    async def test_cache_not_available_returns_original(self, cache):
        """Test that results are unchanged when cache is not available."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_content = "X" * (PREVIEW_SIZE + 1000)
        results = [{"content": large_content, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = None  # No cache

            truncated = await _apply_temporal_payload_truncation(results)

        # Results should be unchanged
        assert truncated[0]["content"] == large_content
