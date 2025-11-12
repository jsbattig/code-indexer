"""Tests for quiet mode support in temporal_display.py.

Tests verify that quiet mode produces compact, single-line output
for both commit message matches and file chunk matches.
"""

from unittest.mock import patch

import pytest

from code_indexer.utils.temporal_display import _display_commit_message_match


class TestCommitMessageMatchQuietMode:
    """Test _display_commit_message_match with quiet mode."""

    def test_commit_message_match_quiet_mode_compact_format(self):
        """Test that quiet mode shows compact format for commit message."""
        result = {
            "metadata": {
                "type": "commit_message",
                "commit_hash": "c6ffd19abcd1234567890",
                "commit_date": "2025-07-14",
                "author_name": "Jose Sebastian Battig",
                "author_email": "jsbattig@gmail.com",
            },
            "temporal_context": {
                "commit_date": "2025-07-14",
                "author_name": "Jose Sebastian Battig",
            },
            "content": "Fix watch mode re-indexing already indexed files",
            "score": 0.700,
        }

        # Capture console output
        with patch("code_indexer.utils.temporal_display.console") as mock_console:
            _display_commit_message_match(result, 1, quiet=True)

            # Verify compact format: single line with number, score, commit metadata
            calls = mock_console.print.call_args_list
            assert len(calls) >= 2  # At least header + content line

            # First call should be compact header
            first_call_args = str(calls[0])
            assert "1." in first_call_args
            assert "0.700" in first_call_args
            assert "c6ffd19" in first_call_args
            assert "2025-07-14" in first_call_args
            assert "Jose Sebastian Battig" in first_call_args
            assert "jsbattig@gmail.com" in first_call_args

            # Second call should be indented content
            second_call_args = str(calls[1])
            assert "   Fix watch mode" in second_call_args

    def test_file_chunk_match_quiet_mode_compact_format(self):
        """Test that quiet mode shows compact format for file chunk."""
        result = {
            "metadata": {
                "type": "file_chunk",
                "path": "src/code_indexer/daemon/service.py",
                "file_path": "src/code_indexer/daemon/service.py",
                "line_start": 100,
                "line_end": 120,
                "commit_hash": "abc1234",
                "diff_type": "modified",
                "author_email": "test@example.com",
            },
            "temporal_context": {
                "commit_date": "2025-07-14",
                "author_name": "Test Author",
                "commit_message": "Update service",
            },
            "content": "def watch_mode():\n    pass",
            "score": 0.850,
        }

        with patch("code_indexer.utils.temporal_display.console") as mock_console:
            from code_indexer.utils.temporal_display import _display_file_chunk_match

            _display_file_chunk_match(result, 3, quiet=True)

            calls = mock_console.print.call_args_list
            # Quiet mode should be minimal - just index, score, file path
            assert len(calls) >= 1

            first_call_args = str(calls[0])
            assert "3." in first_call_args
            assert "0.850" in first_call_args
            assert "src/code_indexer/daemon/service.py" in first_call_args

    def test_quiet_mode_propagates_to_commit_message_display(self):
        """Test that quiet=True is passed to _display_commit_message_match."""
        from code_indexer.utils.temporal_display import display_temporal_results

        results = {
            "results": [
                {
                    "metadata": {
                        "type": "commit_message",
                        "commit_hash": "abc1234",
                        "commit_date": "2025-07-14",
                        "author_name": "Test",
                        "author_email": "test@example.com",
                    },
                    "temporal_context": {
                        "commit_date": "2025-07-14",
                        "author_name": "Test",
                    },
                    "content": "Test commit",
                    "score": 0.800,
                }
            ],
            "total_found": 1,
            "performance": {"total_time": 0.123},
        }

        with patch(
            "code_indexer.utils.temporal_display._display_commit_message_match"
        ) as mock_display:
            display_temporal_results(results, quiet=True)

            # Verify quiet=True was passed
            mock_display.assert_called_once()
            call_args = mock_display.call_args
            assert call_args[1]["quiet"] is True
