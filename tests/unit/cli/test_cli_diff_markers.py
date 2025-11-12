"""Test diff-type marker display in CLI for Story 2."""

import pytest
from unittest.mock import MagicMock, patch
from src.code_indexer.cli import _display_file_chunk_match
from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchResult,
)


class TestDiffTypeMarkers:
    """Test that diff-type markers are displayed correctly in temporal query results."""

    def test_display_added_file_marker(self):
        """Test that [ADDED] marker is displayed for added files."""
        # Arrange
        result = TemporalSearchResult(
            file_path="src/new_file.py",
            chunk_index=0,
            content="def hello():\n    return 'world'",
            score=0.95,
            metadata={
                "file_path": "src/new_file.py",
                "line_start": 1,
                "line_end": 2,
                "commit_hash": "abc123def456",
                "diff_type": "added",  # This is the key field from Story 1
            },
            temporal_context={},
        )

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "date": "2024-11-01",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "message": "Add new file",
        }

        # Act & Assert
        with patch("src.code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 1, mock_service)

            # Check that [ADDED] marker was printed
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any(
                "[ADDED]" in str(call) for call in calls
            ), f"Expected [ADDED] marker in output. Calls: {calls}"

    def test_display_modified_file_marker(self):
        """Test that [MODIFIED] marker is displayed for modified files."""
        # Arrange
        result = TemporalSearchResult(
            file_path="src/existing.py",
            chunk_index=0,
            content="def updated():\n    return 'modified'",
            score=0.90,
            metadata={
                "file_path": "src/existing.py",
                "line_start": 10,
                "line_end": 12,
                "commit_hash": "def789abc123",
                "diff_type": "modified",
            },
            temporal_context={},
        )

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "date": "2024-11-02",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "message": "Update existing file",
        }

        # Act & Assert
        with patch("src.code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 2, mock_service)

            # Check that [MODIFIED] marker was printed
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any(
                "[MODIFIED]" in str(call) for call in calls
            ), f"Expected [MODIFIED] marker in output. Calls: {calls}"

    def test_no_changes_in_chunk_not_displayed(self):
        """Test that [NO CHANGES IN CHUNK] is NOT displayed anymore."""
        # Arrange - even without diff_type, should not show NO CHANGES
        result = TemporalSearchResult(
            file_path="src/some_file.py",
            chunk_index=0,
            content="def code():\n    pass",
            score=0.80,
            metadata={
                "file_path": "src/some_file.py",
                "line_start": 5,
                "line_end": 6,
                "commit_hash": "aaa111bbb222",
                # No diff_type - simulating old payload
            },
            temporal_context={},
        )

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "date": "2024-11-04",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "message": "Some change",
        }
        # These methods should not be called anymore
        mock_service._generate_chunk_diff.return_value = None
        mock_service._is_new_file.return_value = False

        # Act & Assert
        with patch("src.code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 4, mock_service)

            # Check that [NO CHANGES IN CHUNK] was NOT printed
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert not any(
                "NO CHANGES IN CHUNK" in str(call) for call in calls
            ), f"Should not display [NO CHANGES IN CHUNK]. Calls: {calls}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
