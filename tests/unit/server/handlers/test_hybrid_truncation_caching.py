"""Unit tests for Hybrid Search truncation - caching functionality.

Story #682: S4 - Hybrid Search with Payload Control
Tests: AC5 (Independent Field Caching), AC6 (Cache Retrieval)

These tests follow TDD methodology - written BEFORE verification.
"""

import pytest
import uuid
from unittest.mock import patch


class TestAC5IndependentFieldCaching:
    """AC5: Independent Field Caching - each field gets its OWN cache handle."""

    @pytest.mark.asyncio
    async def test_all_three_fields_get_independent_handles(self, cache):
        """Test that content, snippet, and match_text each get unique handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        large_content = "CONTENT" * 500  # 3500 chars
        large_snippet = "SNIPPET" * 500  # 3500 chars
        large_match_text = "MATCHTEXT" * 300  # 2700 chars

        results = [
            {
                "file_path": "/src/hybrid.py",
                "content": large_content,
                "code_snippet": large_snippet,
                "match_text": large_match_text,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # All three handles should exist and be unique
        content_handle = result["cache_handle"]
        snippet_handle = result["snippet_cache_handle"]
        match_text_handle = result["match_text_cache_handle"]

        assert content_handle is not None
        assert snippet_handle is not None
        assert match_text_handle is not None

        # All handles must be different
        handles = {content_handle, snippet_handle, match_text_handle}
        assert len(handles) == 3, "All handles must be unique"

        # All handles must be valid UUIDs
        uuid.UUID(content_handle, version=4)
        uuid.UUID(snippet_handle, version=4)
        uuid.UUID(match_text_handle, version=4)

    @pytest.mark.asyncio
    async def test_handles_retrieve_correct_content(self, cache):
        """Test that each handle retrieves its correct content."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        content_data = "SEMANTIC_CONTENT_" * 200  # 3200 chars
        snippet_data = "FTS_SNIPPET_DATA_" * 200  # 3400 chars
        match_text_data = "FTS_MATCH_TEXT_" * 200  # 3000 chars

        results = [
            {
                "file_path": "/src/hybrid.py",
                "content": content_data,
                "code_snippet": snippet_data,
                "match_text": match_text_data,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]

        # Retrieve each independently and verify correct content
        content_retrieved = await cache.retrieve(result["cache_handle"], page=0)
        snippet_retrieved = await cache.retrieve(result["snippet_cache_handle"], page=0)
        match_text_retrieved = await cache.retrieve(
            result["match_text_cache_handle"], page=0
        )

        assert content_retrieved.content == content_data
        assert snippet_retrieved.content == snippet_data
        assert match_text_retrieved.content == match_text_data


class TestAC6CacheRetrievalForHybridFields:
    """AC6: Cache Retrieval for Hybrid Fields - all handles work with cache API."""

    @pytest.mark.asyncio
    async def test_content_handle_pagination(self, cache):
        """Test that semantic content handle supports pagination."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        # Create content that spans multiple pages (page size = 5000)
        page1 = "A" * 5000
        page2 = "B" * 5000
        large_content = page1 + page2

        results = [{"content": large_content}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)
            truncated = await _apply_payload_truncation(truncated)

        result = truncated[0]
        content_handle = result["cache_handle"]

        # Retrieve page 0
        page0_result = await cache.retrieve(content_handle, page=0)
        assert page0_result.content == page1
        assert page0_result.page == 0
        assert page0_result.has_more is True
        assert page0_result.total_pages == 2

        # Retrieve page 1
        page1_result = await cache.retrieve(content_handle, page=1)
        assert page1_result.content == page2
        assert page1_result.page == 1
        assert page1_result.has_more is False

    @pytest.mark.asyncio
    async def test_snippet_handle_pagination(self, cache):
        """Test that FTS snippet handle supports pagination."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        page1 = "S" * 5000
        page2 = "T" * 5000
        large_snippet = page1 + page2

        results = [{"code_snippet": large_snippet}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        snippet_handle = result["snippet_cache_handle"]

        # Retrieve page 0
        page0_result = await cache.retrieve(snippet_handle, page=0)
        assert page0_result.content == page1
        assert page0_result.has_more is True

        # Retrieve page 1
        page1_result = await cache.retrieve(snippet_handle, page=1)
        assert page1_result.content == page2
        assert page1_result.has_more is False

    @pytest.mark.asyncio
    async def test_match_text_handle_pagination(self, cache):
        """Test that FTS match_text handle supports pagination."""
        from code_indexer.server.mcp.handlers import (
            _apply_payload_truncation,
            _apply_fts_payload_truncation,
        )

        page1 = "M" * 5000
        page2 = "N" * 5000
        large_match_text = page1 + page2

        results = [{"match_text": large_match_text}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_fts_payload_truncation(results)

        result = truncated[0]
        match_text_handle = result["match_text_cache_handle"]

        # Retrieve page 0
        page0_result = await cache.retrieve(match_text_handle, page=0)
        assert page0_result.content == page1
        assert page0_result.has_more is True

        # Retrieve page 1
        page1_result = await cache.retrieve(match_text_handle, page=1)
        assert page1_result.content == page2
        assert page1_result.has_more is False
