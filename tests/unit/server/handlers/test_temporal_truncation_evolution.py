"""Unit tests for Temporal evolution entry truncation logic (AC2, AC3, AC4).

Story #681: S3 - Temporal Search with Payload Control

AC2: Evolution Entry Content Truncation
AC3: Evolution Entry Diff Truncation
AC4: Multiple Evolution Entries (independent handles)
"""

import pytest
import uuid
from unittest.mock import patch


# Use preview size from PayloadCacheConfig default
PREVIEW_SIZE = 2000


class TestAC2EvolutionContentTruncation:
    """AC2: Evolution Entry Content Truncation tests."""

    @pytest.mark.asyncio
    async def test_large_evolution_content_is_truncated(self, cache):
        """Test that evolution entry content > 2000 chars is truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_evo_content = "E" * (PREVIEW_SIZE + 2000)
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": "small main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": large_evo_content,
                            "diff": "small diff",
                            "timestamp": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]
        evo_entry = result["temporal_context"]["evolution"][0]

        # Evolution content should be truncated
        assert "content_preview" in evo_entry
        assert evo_entry["content_preview"] == "E" * PREVIEW_SIZE
        assert evo_entry["content_has_more"] is True
        assert evo_entry["content_total_size"] == PREVIEW_SIZE + 2000
        assert "content_cache_handle" in evo_entry
        uuid.UUID(evo_entry["content_cache_handle"], version=4)

        # Original content should be removed
        assert "content" not in evo_entry

        # Other evolution fields preserved
        assert evo_entry["commit_hash"] == "abc123"
        assert evo_entry["timestamp"] == "2024-01-01T00:00:00Z"

        # Diff not truncated (it's small)
        assert evo_entry["diff"] == "small diff"
        assert evo_entry["diff_cache_handle"] is None
        assert evo_entry["diff_has_more"] is False

    @pytest.mark.asyncio
    async def test_small_evolution_content_not_truncated(self, cache):
        """Test that evolution entry content <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        small_evo_content = "Small evolution content"
        results = [
            {
                "content": "main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": small_evo_content,
                            "diff": "some diff",
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Content should NOT be truncated
        assert evo_entry["content"] == small_evo_content
        assert evo_entry["content_cache_handle"] is None
        assert evo_entry["content_has_more"] is False

        # Should NOT have preview fields
        assert "content_preview" not in evo_entry
        assert "content_total_size" not in evo_entry


class TestAC3EvolutionDiffTruncation:
    """AC3: Evolution Diff Truncation tests."""

    @pytest.mark.asyncio
    async def test_large_evolution_diff_is_truncated(self, cache):
        """Test that evolution entry diff > 2000 chars is truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_diff = "D" * (PREVIEW_SIZE + 3000)
        results = [
            {
                "file_path": "/path/to/file.py",
                "content": "main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": "small content",
                            "diff": large_diff,
                            "timestamp": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Diff should be truncated
        assert "diff_preview" in evo_entry
        assert evo_entry["diff_preview"] == "D" * PREVIEW_SIZE
        assert evo_entry["diff_has_more"] is True
        assert evo_entry["diff_total_size"] == PREVIEW_SIZE + 3000
        assert "diff_cache_handle" in evo_entry
        uuid.UUID(evo_entry["diff_cache_handle"], version=4)

        # Original diff should be removed
        assert "diff" not in evo_entry

        # Content not truncated (it's small)
        assert evo_entry["content"] == "small content"
        assert evo_entry["content_cache_handle"] is None
        assert evo_entry["content_has_more"] is False

    @pytest.mark.asyncio
    async def test_small_evolution_diff_not_truncated(self, cache):
        """Test that evolution entry diff <= 2000 chars is NOT truncated."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        small_diff = "Small diff"
        results = [
            {
                "content": "main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": "content",
                            "diff": small_diff,
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Diff should NOT be truncated
        assert evo_entry["diff"] == small_diff
        assert evo_entry["diff_cache_handle"] is None
        assert evo_entry["diff_has_more"] is False

        # Should NOT have preview fields
        assert "diff_preview" not in evo_entry
        assert "diff_total_size" not in evo_entry

    @pytest.mark.asyncio
    async def test_both_evolution_content_and_diff_truncated(self, cache):
        """Test that both content and diff are truncated when both large."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_content = "C" * (PREVIEW_SIZE + 1000)
        large_diff = "D" * (PREVIEW_SIZE + 2000)
        results = [
            {
                "content": "main",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": large_content,
                            "diff": large_diff,
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Both should be truncated with different handles
        assert evo_entry["content_preview"] == "C" * PREVIEW_SIZE
        assert evo_entry["content_has_more"] is True
        assert evo_entry["content_total_size"] == PREVIEW_SIZE + 1000
        assert evo_entry["content_cache_handle"] is not None

        assert evo_entry["diff_preview"] == "D" * PREVIEW_SIZE
        assert evo_entry["diff_has_more"] is True
        assert evo_entry["diff_total_size"] == PREVIEW_SIZE + 2000
        assert evo_entry["diff_cache_handle"] is not None

        # Handles should be different
        assert evo_entry["content_cache_handle"] != evo_entry["diff_cache_handle"]


class TestAC4MultipleEvolutionEntries:
    """AC4: Multiple Evolution Entries tests (independent handles)."""

    @pytest.mark.asyncio
    async def test_multiple_entries_get_independent_handles(self, cache):
        """Test that each evolution entry gets independent cache handles."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "content": "main",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "commit1",
                            "content": "A" * (PREVIEW_SIZE + 1000),
                            "diff": "a" * (PREVIEW_SIZE + 500),
                        },
                        {
                            "commit_hash": "commit2",
                            "content": "B" * (PREVIEW_SIZE + 2000),
                            "diff": "small diff",
                        },
                        {
                            "commit_hash": "commit3",
                            "content": "small content",
                            "diff": "C" * (PREVIEW_SIZE + 1500),
                        },
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        evolution = truncated[0]["temporal_context"]["evolution"]

        # Entry 1: both content and diff truncated
        assert evolution[0]["content_preview"] == "A" * PREVIEW_SIZE
        assert evolution[0]["content_has_more"] is True
        assert evolution[0]["diff_preview"] == "a" * PREVIEW_SIZE
        assert evolution[0]["diff_has_more"] is True

        # Entry 2: content truncated, diff not
        assert evolution[1]["content_preview"] == "B" * PREVIEW_SIZE
        assert evolution[1]["content_has_more"] is True
        assert evolution[1]["diff"] == "small diff"
        assert evolution[1]["diff_has_more"] is False

        # Entry 3: content not truncated, diff truncated
        assert evolution[2]["content"] == "small content"
        assert evolution[2]["content_has_more"] is False
        assert evolution[2]["diff_preview"] == "C" * PREVIEW_SIZE
        assert evolution[2]["diff_has_more"] is True

        # All handles should be unique
        handles = []
        for entry in evolution:
            if entry.get("content_cache_handle"):
                handles.append(entry["content_cache_handle"])
            if entry.get("diff_cache_handle"):
                handles.append(entry["diff_cache_handle"])

        # Should have 4 handles: entry1 content, entry1 diff, entry2 content, entry3 diff
        assert len(handles) == 4
        assert len(set(handles)) == 4  # All unique

    @pytest.mark.asyncio
    async def test_empty_evolution_array_handled(self, cache):
        """Test that empty evolution array is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {"content": "main content", "temporal_context": {"evolution": []}}
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        # Evolution should remain empty array
        assert truncated[0]["temporal_context"]["evolution"] == []
