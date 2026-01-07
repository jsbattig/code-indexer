"""Unit tests for Regex line_content truncation logic.

Story #684: S6 - Regex Search with Payload Control
AC1: Regex Line Content Truncation (line_content field)

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
import uuid
from unittest.mock import patch


class TestRegexTruncationFunctionExists:
    """Test that _apply_regex_payload_truncation function exists."""

    def test_function_exists_in_handlers_module(self):
        """Test that _apply_regex_payload_truncation is defined in handlers.py."""
        from code_indexer.server.mcp import handlers

        assert hasattr(handlers, "_apply_regex_payload_truncation")
        assert callable(handlers._apply_regex_payload_truncation)


class TestAC1LineContentTruncation:
    """AC1: Regex Line Content Truncation tests.

    When line_content > 2000 chars: return line_content_preview,
        line_content_cache_handle, line_content_has_more=true, line_content_total_size
    When line_content <= 2000 chars: return full line_content,
        line_content_cache_handle=null, line_content_has_more=false
    """

    @pytest.mark.asyncio
    async def test_large_line_content_is_truncated(self, cache):
        """Test that line_content > 2000 chars is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "X" * 3000
        results = [
            {
                "file_path": "/path/to/file.py",
                "line_number": 10,
                "column": 5,
                "line_content": large_line,
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        assert len(truncated) == 1
        result = truncated[0]

        # Should have preview fields
        assert "line_content_preview" in result
        assert result["line_content_preview"] == "X" * 2000
        assert result["line_content_has_more"] is True
        assert result["line_content_total_size"] == 3000
        assert "line_content_cache_handle" in result
        # Verify handle is a valid UUID
        uuid.UUID(result["line_content_cache_handle"], version=4)

        # Original line_content should be removed
        assert "line_content" not in result

        # Other fields preserved
        assert result["file_path"] == "/path/to/file.py"
        assert result["line_number"] == 10
        assert result["column"] == 5

    @pytest.mark.asyncio
    async def test_small_line_content_not_truncated(self, cache):
        """Test that line_content <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        small_line = "Small line content"
        results = [
            {
                "file_path": "/path/to/file.py",
                "line_number": 10,
                "column": 5,
                "line_content": small_line,
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Should keep original line_content
        assert result["line_content"] == small_line
        assert result["line_content_cache_handle"] is None
        assert result["line_content_has_more"] is False

        # Should NOT have preview fields
        assert "line_content_preview" not in result
        assert "line_content_total_size" not in result

    @pytest.mark.asyncio
    async def test_line_content_at_exact_boundary_not_truncated(self, cache):
        """Test that line_content exactly at 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        exact_line = "Y" * 2000
        results = [
            {
                "line_content": exact_line,
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Exactly at boundary should NOT be truncated
        assert result["line_content"] == exact_line
        assert result["line_content_cache_handle"] is None
        assert result["line_content_has_more"] is False

    @pytest.mark.asyncio
    async def test_empty_line_content_not_truncated(self, cache):
        """Test that empty line_content is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        results = [
            {
                "line_content": "",
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]
        assert result["line_content"] == ""
        assert result["line_content_cache_handle"] is None
        assert result["line_content_has_more"] is False

    @pytest.mark.asyncio
    async def test_returns_unmodified_when_no_cache(self):
        """Test that results are returned unmodified when cache unavailable."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "X" * 3000
        results = [
            {
                "file_path": "/test.py",
                "line_number": 1,
                "column": 1,
                "line_content": large_line,
                "context_before": [],
                "context_after": [],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = None

            truncated = await _apply_regex_payload_truncation(results)

        # Results should be unchanged
        assert truncated == results
        assert truncated[0]["line_content"] == large_line
