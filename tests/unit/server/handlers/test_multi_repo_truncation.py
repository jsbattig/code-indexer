"""Unit tests for Multi-repo Search Payload Control (Story #683).

S5: Multi-repo Search with Payload Control
Depends on: S1 (semantic truncation) - already implemented

These tests verify that:
1. Multi-repo content is truncated correctly (AC1)
2. Repository attribution is preserved (AC6)
3. Each result gets independent cache handles (AC2)

TDD methodology: Tests written BEFORE any implementation changes.
"""

import pytest


class TestMultiRepoContentTruncation:
    """AC1: Multi-repo Content Truncation tests."""

    @pytest.mark.asyncio
    async def test_large_content_from_repo_alpha_truncated(self, cache_100_chars):
        """Large content from repo-alpha gets preview + cache_handle + repository preserved."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "X" * 500,
                    "score": 0.92,
                }
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]

            # AC1: Truncation applied
            assert result["has_more"] is True
            assert result["preview"] == "X" * 100
            assert result["cache_handle"] is not None
            assert result["total_size"] == 500

            # AC6: Repository attribution preserved
            assert result["source_repo"] == "repo-alpha"
            assert result["file_path"] == "/src/main.py"
            assert result["score"] == 0.92

            # Content field should be removed
            assert "content" not in result
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_small_content_returns_full_with_repository(self, cache_100_chars):
        """Small content returns full content with repository preserved."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-beta",
                    "file_path": "/lib/utils.py",
                    "content": "short content",
                    "score": 0.85,
                }
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 1
            result = truncated[0]

            # AC1: No truncation for small content
            assert result["has_more"] is False
            assert result["cache_handle"] is None
            assert result["content"] == "short content"
            assert "preview" not in result

            # AC6: Repository attribution preserved
            assert result["source_repo"] == "repo-beta"
            assert result["file_path"] == "/lib/utils.py"
            assert result["score"] == 0.85
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestPerResultCacheHandleIndependence:
    """AC2: Per-Repository Result Independence tests."""

    @pytest.mark.asyncio
    async def test_multiple_repos_get_independent_handles(self, cache_100_chars):
        """Results from different repos get independent cache handles."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "A" * 500,
                    "score": 0.92,
                },
                {
                    "source_repo": "repo-beta",
                    "file_path": "/lib/utils.py",
                    "content": "B" * 500,
                    "score": 0.88,
                },
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 2

            # Both should have cache handles
            assert truncated[0]["cache_handle"] is not None
            assert truncated[1]["cache_handle"] is not None

            # Handles must be DIFFERENT (independent)
            assert truncated[0]["cache_handle"] != truncated[1]["cache_handle"]

            # Repository attribution preserved for both
            assert truncated[0]["source_repo"] == "repo-alpha"
            assert truncated[1]["source_repo"] == "repo-beta"
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_same_repo_multiple_results_get_independent_handles(self, cache_100_chars):
        """Multiple results from SAME repo get independent cache handles."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "A" * 500,
                    "score": 0.92,
                },
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/helper.py",
                    "content": "B" * 500,
                    "score": 0.85,
                },
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 2

            # Both should have cache handles
            assert truncated[0]["cache_handle"] is not None
            assert truncated[1]["cache_handle"] is not None

            # Handles must be DIFFERENT (independent within same repo)
            assert truncated[0]["cache_handle"] != truncated[1]["cache_handle"]

            # Both have same source_repo
            assert truncated[0]["source_repo"] == "repo-alpha"
            assert truncated[1]["source_repo"] == "repo-alpha"

            # But different file_paths
            assert truncated[0]["file_path"] == "/src/main.py"
            assert truncated[1]["file_path"] == "/src/helper.py"
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestRepositoryAttributionPreservation:
    """AC6: Repository Attribution Preservation tests."""

    @pytest.mark.asyncio
    async def test_all_metadata_fields_preserved_after_truncation(self, cache_100_chars):
        """All metadata fields preserved after truncation (only content fields modified)."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/auth.py",
                    "content": "X" * 500,
                    "score": 0.95,
                    "language": "python",
                    "line_number": 42,
                    "similarity_score": 0.95,
                    "chunk_index": 3,
                }
            ]

            truncated = await _apply_payload_truncation(results)

            result = truncated[0]

            # All metadata preserved
            assert result["source_repo"] == "repo-alpha"
            assert result["file_path"] == "/src/auth.py"
            assert result["score"] == 0.95
            assert result["language"] == "python"
            assert result["line_number"] == 42
            assert result["similarity_score"] == 0.95
            assert result["chunk_index"] == 3

            # Content-related fields modified
            assert "content" not in result
            assert result["preview"] is not None
            assert result["cache_handle"] is not None
            assert result["has_more"] is True
            assert result["total_size"] == 500
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestCacheRetrievalWithoutRepoContext:
    """AC5: Cache Retrieval for Multi-repo Results tests."""

    @pytest.mark.asyncio
    async def test_handle_retrieval_without_repo_context(self, cache_100_chars):
        """Cache handle can be retrieved without any repository context."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "FULL_CONTENT_" + "X" * 500,
                    "score": 0.92,
                }
            ]

            truncated = await _apply_payload_truncation(results)
            handle = truncated[0]["cache_handle"]

            # Retrieve using ONLY the handle - no repo context needed
            retrieved = await cache_100_chars.retrieve(handle, page=0)

            # Should get the full content back
            assert "FULL_CONTENT_" in retrieved.content
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original

    @pytest.mark.asyncio
    async def test_handles_from_different_repos_all_retrievable(self, cache_100_chars):
        """Handles from different repos can all be retrieved using same API."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "ALPHA_" + "A" * 500,
                    "score": 0.92,
                },
                {
                    "source_repo": "repo-beta",
                    "file_path": "/lib/utils.py",
                    "content": "BETA_" + "B" * 500,
                    "score": 0.88,
                },
            ]

            truncated = await _apply_payload_truncation(results)

            # Retrieve both handles - no repo context needed
            retrieved_alpha = await cache_100_chars.retrieve(
                truncated[0]["cache_handle"], page=0
            )
            retrieved_beta = await cache_100_chars.retrieve(
                truncated[1]["cache_handle"], page=0
            )

            # Should get correct content for each
            assert "ALPHA_" in retrieved_alpha.content
            assert "BETA_" in retrieved_beta.content
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original


class TestMixedResultsTruncation:
    """Tests for mixed truncated and non-truncated results from multiple repos."""

    @pytest.mark.asyncio
    async def test_mixed_large_and_small_content_from_multiple_repos(self, cache_100_chars):
        """Mix of large and small content from multiple repos handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_payload_truncation
        from code_indexer.server import app as app_module

        original = getattr(app_module.app.state, "payload_cache", None)
        app_module.app.state.payload_cache = cache_100_chars

        try:
            results = [
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/main.py",
                    "content": "A" * 500,  # Large - truncated
                    "score": 0.92,
                },
                {
                    "source_repo": "repo-beta",
                    "file_path": "/lib/utils.py",
                    "content": "small",  # Small - not truncated
                    "score": 0.88,
                },
                {
                    "source_repo": "repo-alpha",
                    "file_path": "/src/helper.py",
                    "content": "short content",  # Small - not truncated
                    "score": 0.85,
                },
                {
                    "source_repo": "repo-gamma",
                    "file_path": "/pkg/core.py",
                    "content": "C" * 300,  # Large - truncated
                    "score": 0.80,
                },
            ]

            truncated = await _apply_payload_truncation(results)

            assert len(truncated) == 4

            # Result 0: Large from repo-alpha (truncated)
            assert truncated[0]["has_more"] is True
            assert truncated[0]["cache_handle"] is not None
            assert truncated[0]["preview"] == "A" * 100
            assert "content" not in truncated[0]
            assert truncated[0]["source_repo"] == "repo-alpha"

            # Result 1: Small from repo-beta (not truncated)
            assert truncated[1]["has_more"] is False
            assert truncated[1]["cache_handle"] is None
            assert truncated[1]["content"] == "small"
            assert "preview" not in truncated[1]
            assert truncated[1]["source_repo"] == "repo-beta"

            # Result 2: Small from repo-alpha (not truncated)
            assert truncated[2]["has_more"] is False
            assert truncated[2]["cache_handle"] is None
            assert truncated[2]["content"] == "short content"
            assert truncated[2]["source_repo"] == "repo-alpha"

            # Result 3: Large from repo-gamma (truncated)
            assert truncated[3]["has_more"] is True
            assert truncated[3]["cache_handle"] is not None
            assert truncated[3]["preview"] == "C" * 100
            assert truncated[3]["source_repo"] == "repo-gamma"

            # All handles are unique
            handles = [r["cache_handle"] for r in truncated if r["cache_handle"]]
            assert len(handles) == len(set(handles)), "Cache handles must be unique"
        finally:
            if original is None:
                if hasattr(app_module.app.state, "payload_cache"):
                    delattr(app_module.app.state, "payload_cache")
            else:
                app_module.app.state.payload_cache = original
