"""Unit tests for Temporal truncation edge cases.

Story #681: S3 - Temporal Search with Payload Control

Edge cases:
- No temporal_context
- temporal_context without evolution
- Evolution entry without content
- Evolution entry without diff
- Unicode content handling
- Preserving other temporal_context fields
"""

import pytest
from unittest.mock import patch


# Use preview size from PayloadCacheConfig default
PREVIEW_SIZE = 2000


class TestTemporalTruncationEdgeCases:
    """Edge case tests for temporal payload truncation."""

    @pytest.mark.asyncio
    async def test_no_temporal_context(self, cache):
        """Test that results without temporal_context are handled."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "file_path": "/path/to/file.py",
                "content": "X" * (PREVIEW_SIZE + 1000),
                "similarity_score": 0.95,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Content should still be truncated
        assert result["content_preview"] == "X" * PREVIEW_SIZE
        assert result["content_has_more"] is True
        assert "content" not in result

    @pytest.mark.asyncio
    async def test_temporal_context_without_evolution(self, cache):
        """Test that temporal_context without evolution is handled."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "content": "main content",
                "temporal_context": {
                    "commit_hash": "abc123",
                    "commit_date": "2024-01-01",
                    # No evolution field
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        # Should work without error
        assert truncated[0]["temporal_context"]["commit_hash"] == "abc123"
        assert "evolution" not in truncated[0]["temporal_context"]

    @pytest.mark.asyncio
    async def test_evolution_entry_without_content(self, cache):
        """Test evolution entry with no content field (metadata only)."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "content": "main",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            # No content field
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

        # Should handle missing content gracefully
        assert "content" not in evo_entry
        assert "content_preview" not in evo_entry
        # When field is missing, no cache handle is set
        assert evo_entry.get("content_cache_handle") is None
        assert evo_entry.get("content_has_more") is None or not evo_entry.get(
            "content_has_more"
        )

    @pytest.mark.asyncio
    async def test_evolution_entry_without_diff(self, cache):
        """Test evolution entry with no diff field (new file)."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "content": "main",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": "some content",
                            # No diff field (new file)
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

        # Should handle missing diff gracefully
        assert "diff" not in evo_entry
        assert "diff_preview" not in evo_entry
        assert evo_entry.get("diff_cache_handle") is None
        assert evo_entry.get("diff_has_more") is None or not evo_entry.get(
            "diff_has_more"
        )

    @pytest.mark.asyncio
    async def test_unicode_content_truncated_correctly(self, cache):
        """Test that Unicode content is truncated at char boundary."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        # Unicode content - emojis are 1+ chars but multiple bytes
        unicode_content = "\U0001f600" * (PREVIEW_SIZE + 1000)

        results = [{"content": unicode_content, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Should truncate at char boundary, not byte boundary
        assert len(result["content_preview"]) == PREVIEW_SIZE
        assert result["content_preview"] == "\U0001f600" * PREVIEW_SIZE
        assert result["content_total_size"] == PREVIEW_SIZE + 1000

    @pytest.mark.asyncio
    async def test_preserves_other_temporal_context_fields(self, cache):
        """Test that non-evolution temporal_context fields are preserved."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "content": "main",
                "temporal_context": {
                    "first_seen": "2024-01-01T00:00:00Z",
                    "last_seen": "2024-06-01T00:00:00Z",
                    "commit_count": 5,
                    "commits": [{"hash": "abc"}, {"hash": "def"}],
                    "is_removed": False,
                    "evolution": [
                        {
                            "commit_hash": "abc123",
                            "content": "C" * (PREVIEW_SIZE + 1000),
                            "diff": "small diff",
                        }
                    ],
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        tc = truncated[0]["temporal_context"]

        # Non-evolution fields should be preserved
        assert tc["first_seen"] == "2024-01-01T00:00:00Z"
        assert tc["last_seen"] == "2024-06-01T00:00:00Z"
        assert tc["commit_count"] == 5
        assert tc["commits"] == [{"hash": "abc"}, {"hash": "def"}]
        assert tc["is_removed"] is False

        # Evolution should be truncated
        assert tc["evolution"][0]["content_has_more"] is True

    @pytest.mark.asyncio
    async def test_no_content_field_in_result(self, cache):
        """Test result without content field (edge case)."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        results = [
            {
                "file_path": "/path/to/file.py",
                # No content field
                "temporal_context": {
                    "commit_hash": "abc123",
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Should handle gracefully
        assert "content" not in result
        assert "content_preview" not in result
        assert result.get("content_cache_handle") is None
