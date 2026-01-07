"""Unit tests for Regex metadata and caching logic.

Story #684: S6 - Regex Search with Payload Control
AC3: Regex-Specific Context Preservation
AC4: Independent Field Caching

These tests follow TDD methodology - written BEFORE implementation.

Note: Uses `cache` fixture from conftest.py in this directory.
"""

import pytest
import uuid
from unittest.mock import patch


class TestAC3MetadataPreservation:
    """AC3: Regex-Specific Context Preservation tests."""

    @pytest.mark.asyncio
    async def test_all_metadata_preserved_after_truncation(self, cache):
        """Test that all regex metadata is preserved after truncation."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "X" * 3000
        results = [
            {
                "file_path": "/src/module/test.py",
                "line_number": 42,
                "column": 15,
                "line_content": large_line,
                "context_before": ["prev1", "prev2"],
                "context_after": ["next1", "next2"],
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # All metadata should be preserved
        assert result["file_path"] == "/src/module/test.py"
        assert result["line_number"] == 42
        assert result["column"] == 15

        # Small context should be preserved as-is
        assert result["context_before"] == ["prev1", "prev2"]
        assert result["context_after"] == ["next1", "next2"]

    @pytest.mark.asyncio
    async def test_extra_fields_preserved(self, cache):
        """Test that any extra/unknown fields are preserved."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        results = [
            {
                "file_path": "/test.py",
                "line_number": 1,
                "column": 1,
                "line_content": "small",
                "context_before": [],
                "context_after": [],
                "custom_field": "custom_value",
                "score": 0.95,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Extra fields should be preserved
        assert result["custom_field"] == "custom_value"
        assert result["score"] == 0.95


class TestAC4IndependentFieldCaching:
    """AC4: Independent Field Caching tests."""

    @pytest.mark.asyncio
    async def test_all_large_fields_get_independent_handles(self, cache):
        """Test that each large field gets its own independent cache handle."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "L" * 3000
        large_before = ["B" * 100 for _ in range(30)]  # ~3000 chars
        large_after = ["A" * 100 for _ in range(30)]  # ~3000 chars

        results = [
            {
                "file_path": "/test.py",
                "line_number": 50,
                "column": 1,
                "line_content": large_line,
                "context_before": large_before,
                "context_after": large_after,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # All three fields should have cache handles
        assert result["line_content_cache_handle"] is not None
        assert result["context_before_cache_handle"] is not None
        assert result["context_after_cache_handle"] is not None

        # All handles should be different
        handles = [
            result["line_content_cache_handle"],
            result["context_before_cache_handle"],
            result["context_after_cache_handle"],
        ]
        assert len(set(handles)) == 3, "All handles should be unique"

        # Each should be valid UUID
        for handle in handles:
            uuid.UUID(handle, version=4)

    @pytest.mark.asyncio
    async def test_handles_are_retrievable_independently(self, cache):
        """Test that each cache handle can be retrieved independently."""
        from code_indexer.server.mcp.handlers import _apply_regex_payload_truncation

        large_line = "LINE_" * 600  # 3000 chars
        large_before = ["BEFORE_" * 20 for _ in range(20)]  # ~2800 chars
        large_after = ["AFTER_" * 20 for _ in range(20)]  # ~2600 chars

        results = [
            {
                "line_content": large_line,
                "context_before": large_before,
                "context_after": large_after,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_regex_payload_truncation(results)

        result = truncated[0]

        # Retrieve each cached content independently
        line_retrieved = await cache.retrieve(
            result["line_content_cache_handle"], page=0
        )
        before_retrieved = await cache.retrieve(
            result["context_before_cache_handle"], page=0
        )
        after_retrieved = await cache.retrieve(
            result["context_after_cache_handle"], page=0
        )

        # Verify content is correct for each
        assert line_retrieved.content == large_line
        # Context is stored as newline-joined string
        assert before_retrieved.content == "\n".join(large_before)
        assert after_retrieved.content == "\n".join(large_after)
