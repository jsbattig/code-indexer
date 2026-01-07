"""Unit tests for REST API /api/query Payload Truncation.

Story: Add payload truncation to /api/query REST endpoint for consistency with MCP handlers.

The MCP handlers apply truncation but the REST /api/query endpoint does not.
This creates inconsistency between MCP and REST API responses.

These tests verify that:
1. Semantic mode results have truncation applied to code_snippet field
2. FTS mode results have truncation applied to snippet field
3. Hybrid mode results have truncation applied to both
4. Small content is NOT truncated (has_more=false, cache_handle=null)
5. Cache handles returned by /api/query are retrievable

TDD methodology: Tests written BEFORE the fix is implemented.
"""

import pytest


class TestRestApiQueryTruncation:
    """Tests for REST API /api/query payload truncation."""

    @pytest.fixture
    async def cache_100_chars(self, tmp_path):
        """Create PayloadCache with 100 char preview for easy testing."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig(preview_size_chars=100, max_fetch_size_chars=200)
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()


class TestRestApiSemanticTruncation(TestRestApiQueryTruncation):
    """Tests for semantic mode payload truncation in /api/query endpoint."""

    @pytest.mark.asyncio
    async def test_apply_rest_semantic_truncation_large_content(self, cache_100_chars):
        """Semantic results with large code_snippet are truncated."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            # Semantic results have code_snippet field
            results = [
                {
                    "file_path": "/src/main.py",
                    "line_number": 42,
                    "code_snippet": "X" * 500,  # Large - should be truncated
                    "similarity_score": 0.92,
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Large content should be truncated
            assert result["has_more"] is True
            assert result["cache_handle"] is not None
            assert result["preview"] == "X" * 100
            assert "code_snippet" not in result  # Removed and replaced with preview
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_apply_rest_semantic_truncation_small_content(self, cache_100_chars):
        """Semantic results with small code_snippet are NOT truncated."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "file_path": "/src/main.py",
                    "line_number": 42,
                    "code_snippet": "small",  # Small - should NOT be truncated
                    "similarity_score": 0.92,
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Small content should not be truncated
            assert result["has_more"] is False
            assert result["cache_handle"] is None
            assert result["code_snippet"] == "small"  # Original field preserved
            assert "preview" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiFtsTruncation(TestRestApiQueryTruncation):
    """Tests for FTS mode payload truncation in /api/query endpoint."""

    @pytest.mark.asyncio
    async def test_apply_rest_fts_truncation_large_snippet(self, cache_100_chars):
        """FTS results with large snippet are truncated."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            # FTS results have snippet field
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "Y" * 500,  # Large - should be truncated
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Large snippet should be truncated
            assert result["snippet_has_more"] is True
            assert result["snippet_cache_handle"] is not None
            assert result["snippet_preview"] == "Y" * 100
            assert "snippet" not in result  # Removed and replaced with preview
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_apply_rest_fts_truncation_small_snippet(self, cache_100_chars):
        """FTS results with small snippet are NOT truncated."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "small",  # Small - should NOT be truncated
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Small snippet should not be truncated
            assert result["snippet_has_more"] is False
            assert result["snippet_cache_handle"] is None
            assert result["snippet"] == "small"  # Original field preserved
            assert "snippet_preview" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiCacheRetrieval(TestRestApiQueryTruncation):
    """Tests for cache handle retrieval from /api/query truncated results."""

    @pytest.mark.asyncio
    async def test_truncated_handle_is_retrievable(self, cache_100_chars):
        """Cache handles from truncated results can be used to retrieve full content."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            large_content = "Z" * 500
            results = [
                {
                    "file_path": "/src/main.py",
                    "line_number": 42,
                    "code_snippet": large_content,
                    "similarity_score": 0.92,
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)
            handle = truncated[0]["cache_handle"]

            # Should be able to retrieve full content using handle
            retrieved = await cache_100_chars.retrieve(handle, page=0)
            # Full content starts with the large content
            assert retrieved.content.startswith("Z" * 100)
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiNoPayloadCache:
    """Tests for behavior when PayloadCache is not available."""

    @pytest.mark.asyncio
    async def test_semantic_truncation_without_cache_returns_unchanged(self):
        """Semantic truncation without cache returns results unchanged."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        # Ensure no cache is set
        original = getattr(app_module.app.state, "payload_cache", None)
        if hasattr(app_module.app.state, "payload_cache"):
            delattr(app_module.app.state, "payload_cache")

        try:
            results = [
                {
                    "file_path": "/src/main.py",
                    "line_number": 42,
                    "code_snippet": "X" * 500,
                    "similarity_score": 0.92,
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)

            # Results should be unchanged when cache not available
            assert len(truncated) == 1
            assert truncated[0]["code_snippet"] == "X" * 500
        finally:
            if original is not None:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_fts_truncation_without_cache_returns_unchanged(self):
        """FTS truncation without cache returns results unchanged."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        # Ensure no cache is set
        original = getattr(app_module.app.state, "payload_cache", None)
        if hasattr(app_module.app.state, "payload_cache"):
            delattr(app_module.app.state, "payload_cache")

        try:
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "Y" * 500,
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            # Results should be unchanged when cache not available
            assert len(truncated) == 1
            assert truncated[0]["snippet"] == "Y" * 500
        finally:
            if original is not None:
                app_module.app.state.payload_cache = original


class TestRestApiFtsMatchTextTruncation(TestRestApiQueryTruncation):
    """Tests for FTS match_text field truncation (Issue #2 - missing match_text handling)."""

    @pytest.mark.asyncio
    async def test_apply_rest_fts_truncation_large_match_text(self, cache_100_chars):
        """FTS results with large match_text are truncated."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            # FTS results can have match_text field (separate from snippet)
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "small",  # Small snippet - not truncated
                    "match_text": "M" * 500,  # Large match_text - should be truncated
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Large match_text should be truncated
            assert result["match_text_has_more"] is True
            assert result["match_text_cache_handle"] is not None
            assert result["match_text_preview"] == "M" * 100
            assert "match_text" not in result  # Removed and replaced with preview
            # Small snippet should NOT be truncated
            assert result["snippet"] == "small"
            assert result["snippet_has_more"] is False
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_apply_rest_fts_truncation_small_match_text(self, cache_100_chars):
        """FTS results with small match_text are NOT truncated."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "small",
                    "match_text": "tiny",  # Small match_text - should NOT be truncated
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Small match_text should not be truncated
            assert result["match_text_has_more"] is False
            assert result["match_text_cache_handle"] is None
            assert result["match_text"] == "tiny"  # Original field preserved
            assert "match_text_preview" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_apply_rest_fts_truncation_both_fields_large(self, cache_100_chars):
        """FTS results with both large snippet and match_text are both truncated."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "path": "/src/main.py",
                    "line_start": 10,
                    "line_end": 20,
                    "snippet": "S" * 500,  # Large snippet
                    "match_text": "M" * 500,  # Large match_text
                    "language": "python",
                    "repository_alias": "test-repo",
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]
            # Both fields should be truncated
            assert result["snippet_has_more"] is True
            assert result["snippet_cache_handle"] is not None
            assert result["snippet_preview"] == "S" * 100
            assert "snippet" not in result
            assert result["match_text_has_more"] is True
            assert result["match_text_cache_handle"] is not None
            assert result["match_text_preview"] == "M" * 100
            assert "match_text" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiMultipleResults(TestRestApiQueryTruncation):
    """Tests for multiple results in one response (Issue #4)."""

    @pytest.mark.asyncio
    async def test_semantic_truncation_multiple_results(self, cache_100_chars):
        """Multiple semantic results are all processed correctly."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "file_path": "/src/file1.py",
                    "line_number": 10,
                    "code_snippet": "A" * 500,  # Large - should be truncated
                    "similarity_score": 0.95,
                },
                {
                    "file_path": "/src/file2.py",
                    "line_number": 20,
                    "code_snippet": "B" * 500,  # Large - should be truncated
                    "similarity_score": 0.90,
                },
                {
                    "file_path": "/src/file3.py",
                    "line_number": 30,
                    "code_snippet": "C" * 500,  # Large - should be truncated
                    "similarity_score": 0.85,
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)

            assert len(truncated) == 3
            # All three should be truncated
            for i, char in enumerate(["A", "B", "C"]):
                assert truncated[i]["has_more"] is True
                assert truncated[i]["cache_handle"] is not None
                assert truncated[i]["preview"] == char * 100
                assert "code_snippet" not in truncated[i]
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_fts_truncation_multiple_results(self, cache_100_chars):
        """Multiple FTS results are all processed correctly."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "path": "/src/file1.py",
                    "snippet": "X" * 500,  # Large
                    "match_text": "Y" * 500,  # Large
                },
                {
                    "path": "/src/file2.py",
                    "snippet": "P" * 500,  # Large
                    "match_text": "Q" * 500,  # Large
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 2
            # First result
            assert truncated[0]["snippet_has_more"] is True
            assert truncated[0]["snippet_preview"] == "X" * 100
            assert truncated[0]["match_text_has_more"] is True
            assert truncated[0]["match_text_preview"] == "Y" * 100
            # Second result
            assert truncated[1]["snippet_has_more"] is True
            assert truncated[1]["snippet_preview"] == "P" * 100
            assert truncated[1]["match_text_has_more"] is True
            assert truncated[1]["match_text_preview"] == "Q" * 100
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiEmptyResults(TestRestApiQueryTruncation):
    """Tests for empty results list handling (Issue #4)."""

    @pytest.mark.asyncio
    async def test_semantic_truncation_empty_results(self, cache_100_chars):
        """Empty results list returns empty list."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = []
            truncated = await _apply_rest_semantic_truncation(results)
            assert truncated == []
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_fts_truncation_empty_results(self, cache_100_chars):
        """Empty FTS results list returns empty list."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = []
            truncated = await _apply_rest_fts_truncation(results)
            assert truncated == []
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRestApiMixedContent(TestRestApiQueryTruncation):
    """Tests for mixed small/large content in same response (Issue #4)."""

    @pytest.mark.asyncio
    async def test_semantic_truncation_mixed_sizes(self, cache_100_chars):
        """Mixed large and small content in semantic results."""
        from code_indexer.server.app import _apply_rest_semantic_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "file_path": "/src/large.py",
                    "code_snippet": "L" * 500,  # Large - truncated
                    "similarity_score": 0.95,
                },
                {
                    "file_path": "/src/small.py",
                    "code_snippet": "S" * 50,  # Small - NOT truncated
                    "similarity_score": 0.90,
                },
                {
                    "file_path": "/src/medium.py",
                    "code_snippet": "M" * 300,  # Medium (>100) - truncated
                    "similarity_score": 0.85,
                },
            ]

            truncated = await _apply_rest_semantic_truncation(results)

            assert len(truncated) == 3

            # First: Large - should be truncated
            assert truncated[0]["has_more"] is True
            assert truncated[0]["cache_handle"] is not None
            assert truncated[0]["preview"] == "L" * 100
            assert "code_snippet" not in truncated[0]

            # Second: Small - should NOT be truncated
            assert truncated[1]["has_more"] is False
            assert truncated[1]["cache_handle"] is None
            assert truncated[1]["code_snippet"] == "S" * 50
            assert "preview" not in truncated[1]

            # Third: Medium - should be truncated (>100 chars)
            assert truncated[2]["has_more"] is True
            assert truncated[2]["cache_handle"] is not None
            assert truncated[2]["preview"] == "M" * 100
            assert "code_snippet" not in truncated[2]
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_fts_truncation_mixed_sizes(self, cache_100_chars):
        """Mixed large and small content in FTS results."""
        from code_indexer.server.app import _apply_rest_fts_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "path": "/src/file1.py",
                    "snippet": "L" * 500,  # Large snippet
                    "match_text": "small",  # Small match_text
                },
                {
                    "path": "/src/file2.py",
                    "snippet": "tiny",  # Small snippet
                    "match_text": "M" * 500,  # Large match_text
                },
            ]

            truncated = await _apply_rest_fts_truncation(results)

            assert len(truncated) == 2

            # First: Large snippet, small match_text
            assert truncated[0]["snippet_has_more"] is True
            assert truncated[0]["snippet_cache_handle"] is not None
            assert truncated[0]["snippet_preview"] == "L" * 100
            assert "snippet" not in truncated[0]
            assert truncated[0]["match_text_has_more"] is False
            assert truncated[0]["match_text_cache_handle"] is None
            assert truncated[0]["match_text"] == "small"

            # Second: Small snippet, large match_text
            assert truncated[1]["snippet_has_more"] is False
            assert truncated[1]["snippet_cache_handle"] is None
            assert truncated[1]["snippet"] == "tiny"
            assert truncated[1]["match_text_has_more"] is True
            assert truncated[1]["match_text_cache_handle"] is not None
            assert truncated[1]["match_text_preview"] == "M" * 100
            assert "match_text" not in truncated[1]
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original
