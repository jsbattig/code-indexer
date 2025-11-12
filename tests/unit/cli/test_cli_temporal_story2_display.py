"""Test CLI display for Story 2 temporal query changes.

This test verifies that CLI uses temporal_context data from results,
not calling deleted SQLite methods.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.code_indexer.cli import (
    _display_file_chunk_match,
    _display_commit_message_match,
)


class TestTemporalDisplayStory2(unittest.TestCase):
    """Test temporal display functions use payload data, not deleted SQLite methods."""

    @patch("src.code_indexer.cli.console")
    def test_display_file_chunk_uses_temporal_context(self, console_mock):
        """Test that file chunk display uses temporal_context, not _fetch_commit_details."""
        # Arrange
        result = MagicMock()
        result.metadata = {
            "file_path": "auth.py",
            "line_start": 1,
            "line_end": 3,
            "commit_hash": "abc123def456",
            "diff_type": "added",
            "author_email": "test@example.com",
        }
        result.temporal_context = {
            "commit_date": "2025-11-01",
            "author_name": "Test Author",
            "commit_message": "Add authentication",
        }
        result.score = 0.95
        result.content = "def authenticate():\n    return True"

        temporal_service_mock = MagicMock()

        # Act
        _display_file_chunk_match(result, 1, temporal_service_mock)

        # Assert - should NOT call _fetch_commit_details
        temporal_service_mock._fetch_commit_details.assert_not_called()

        # Assert - should display data from temporal_context
        calls = console_mock.print.call_args_list
        output = " ".join(str(call) for call in calls)

        # Check that temporal_context data is used
        self.assertIn("Test Author", output)
        self.assertIn("2025-11-01", output)
        self.assertIn("Add authentication", output)
        self.assertIn("test@example.com", output)

    @patch("src.code_indexer.cli.console")
    def test_display_commit_message_no_fetch_methods(self, console_mock):
        """Test that commit message display doesn't call deleted SQLite methods."""
        # Arrange
        result = MagicMock()
        result.metadata = {
            "commit_hash": "abc123def456",
            "author_email": "test@example.com",
        }
        result.temporal_context = {
            "commit_date": "2025-11-01",
            "author_name": "Test Author",
        }
        result.score = 0.85
        result.content = "Fix critical bug in authentication"

        temporal_service_mock = MagicMock()

        # Act
        _display_commit_message_match(result, 1, temporal_service_mock)

        # Assert - should NOT call deleted methods
        temporal_service_mock._fetch_commit_details.assert_not_called()
        # _fetch_commit_file_changes was deleted, but check if called
        if hasattr(temporal_service_mock, "_fetch_commit_file_changes"):
            temporal_service_mock._fetch_commit_file_changes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
