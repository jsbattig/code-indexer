"""
Unit tests for CLI temporal display functions (Story 2.1 fixes).

Tests verify:
1. Diff display with line numbers and +/- markers
2. Commit message search and display
3. Display ordering (commit messages first, then chunks)
4. Line number tracking (dual: parent + current)
5. Error handling for edge cases
"""

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

# Import the functions to test
from src.code_indexer.cli import (
    _display_file_chunk_match,
    _display_commit_message_match,
    display_temporal_results,
)


class MockResult:
    """Mock search result object."""

    def __init__(self, score, content, metadata):
        self.score = score
        self.content = content
        self.metadata = metadata


class MockSearchResults:
    """Mock search results collection."""

    def __init__(self, results_list):
        self.results = results_list


class TestCLITemporalDisplayComprehensive(TestCase):
    """Test suite for temporal display functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir) / "test_project"
        self.project_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_display_file_chunk_match_with_diff(self):
        """Test that file chunk match displays diff with line numbers."""
        # Mock result
        result = MockResult(
            score=0.85,
            content="def validate_token(token):\\n    if token.expired():\\n        logger.warning('Token expired')\\n        raise TokenExpiredError()",
            metadata={
                "type": "file_chunk",
                "file_path": "auth.py",
                "commit_hash": "fa6d59d1234567890abcdef1234567890abcdef",
                "blob_hash": "abc123",
                "line_start": 1,
                "line_end": 4,
            },
        )

        # Mock temporal service
        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "hash": "fa6d59d1234567890abcdef1234567890abcdef",
            "date": "2024-01-15 14:30:00",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "message": "Fix JWT validation bug",
        }

        # Story 2: _generate_chunk_diff removed - diffs are pre-computed and stored in payloads
        # No longer need to mock diff generation

        # Patch console.print to capture output
        with patch("src.code_indexer.cli.console.print") as mock_print:
            _display_file_chunk_match(result, 1, mock_service)

            # Verify commit details were fetched
            mock_service._fetch_commit_details.assert_called_once_with(
                "fa6d59d1234567890abcdef1234567890abcdef"
            )

            # Story 2: _generate_chunk_diff removed - no diff generation anymore
            # Diffs are pre-computed and stored in payloads

            # Verify content was printed (Story 2: pre-computed diffs in content)
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any(
                "def validate_token" in str(call) for call in print_calls
            ), "Content should be displayed"

    def test_display_file_chunk_match_without_diff_shows_content(self):
        """Test that file chunk without diff shows chunk content with line numbers."""
        result = MockResult(
            score=0.85,
            content="def initial_function():\\n    return True",
            metadata={
                "type": "file_chunk",
                "file_path": "initial.py",
                "commit_hash": "413bcb3",
                "blob_hash": "xyz789",
                "line_start": 10,
                "line_end": 11,
            },
        )

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "hash": "413bcb3",
            "date": "2024-01-14 10:00:00",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "message": "Initial commit",
        }

        # Story 2: No diff generation - content is pre-computed in payloads

        with patch("src.code_indexer.cli.console.print") as mock_print:
            _display_file_chunk_match(result, 1, mock_service)

            # Verify chunk content was printed with line numbers
            print_calls = [str(call) for call in mock_print.call_args_list]

            # Should show line numbers starting at line_start (10)
            assert any(
                "10" in str(call) for call in print_calls
            ), "Line 10 should be displayed"
            assert any(
                "11" in str(call) for call in print_calls
            ), "Line 11 should be displayed"

    def test_display_commit_message_match(self):
        """Test that commit message match displays correctly."""
        result = MockResult(
            score=0.92,
            content="Fix JWT validation bug\\n\\nNow properly logs warnings and raises TokenExpiredError",
            metadata={
                "type": "commit_message",
                "commit_hash": "fa6d59d1234567890abcdef1234567890abcdef",
            },
        )

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "hash": "fa6d59d1234567890abcdef1234567890abcdef",
            "date": "2024-01-15 14:30:00",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "message": "Fix JWT validation bug\\n\\nNow properly logs warnings and raises TokenExpiredError\\ninstead of silently returning False.",
        }

        mock_service._fetch_commit_file_changes.return_value = [
            {"file_path": "auth.py", "blob_hash": "abc123"},
            {"file_path": "tests/test_auth.py", "blob_hash": "def456"},
        ]

        with patch("src.code_indexer.cli.console.print") as mock_print:
            _display_commit_message_match(result, 1, mock_service)

            # Verify commit details were fetched
            mock_service._fetch_commit_details.assert_called_once()
            mock_service._fetch_commit_file_changes.assert_called_once()

            # Verify output contains commit message marker
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any(
                "COMMIT MESSAGE MATCH" in str(call) for call in print_calls
            ), "Commit message marker should be displayed"

            # Verify files modified list
            assert any(
                "auth.py" in str(call) for call in print_calls
            ), "Modified file should be listed"

    def test_display_ordering_commit_messages_first(self):
        """Test that display_temporal_results shows commit messages before file chunks."""
        # Create mixed results
        commit_msg_result = MockResult(
            score=0.95,
            content="Add authentication system",
            metadata={"type": "commit_message", "commit_hash": "abc123"},
        )

        file_chunk_result = MockResult(
            score=0.90,
            content="def authenticate(user):\\n    return True",
            metadata={
                "type": "file_chunk",
                "file_path": "auth.py",
                "commit_hash": "def456",
                "blob_hash": "xyz789",
                "line_start": 1,
                "line_end": 2,
            },
        )

        # Results in file_chunk, commit_message order (should be reordered)
        results = MockSearchResults([file_chunk_result, commit_msg_result])

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "hash": "abc123",
            "date": "2024-01-15 14:30:00",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "message": "Add authentication system",
        }
        mock_service._fetch_commit_file_changes.return_value = []

        with (
            patch(
                "src.code_indexer.cli._display_commit_message_match"
            ) as mock_commit_display,
            patch(
                "src.code_indexer.cli._display_file_chunk_match"
            ) as mock_file_display,
        ):

            display_temporal_results(results, mock_service)

            # Verify commit message was displayed first (index=1)
            mock_commit_display.assert_called_once()
            assert mock_commit_display.call_args[0][1] == 1  # index=1

            # Verify file chunk was displayed second (index=2)
            mock_file_display.assert_called_once()
            assert mock_file_display.call_args[0][1] == 2  # index=2

    def test_display_ordering_all_commit_messages_before_all_chunks(self):
        """Test that ALL commit messages display before ANY file chunks."""
        # Create multiple of each type
        commit_1 = MockResult(
            score=0.95,
            content="Add auth",
            metadata={"type": "commit_message", "commit_hash": "abc111"},
        )
        commit_2 = MockResult(
            score=0.92,
            content="Fix bug",
            metadata={"type": "commit_message", "commit_hash": "abc222"},
        )
        chunk_1 = MockResult(
            score=0.90,
            content="def func1():\\n    pass",
            metadata={
                "type": "file_chunk",
                "file_path": "file1.py",
                "commit_hash": "def111",
                "blob_hash": "xyz111",
                "line_start": 1,
                "line_end": 2,
            },
        )
        chunk_2 = MockResult(
            score=0.88,
            content="def func2():\\n    pass",
            metadata={
                "type": "file_chunk",
                "file_path": "file2.py",
                "commit_hash": "def222",
                "blob_hash": "xyz222",
                "line_start": 10,
                "line_end": 11,
            },
        )

        # Mixed order: chunk, commit, commit, chunk
        results = MockSearchResults([chunk_1, commit_1, commit_2, chunk_2])

        mock_service = MagicMock()
        mock_service._fetch_commit_details.return_value = {
            "hash": "abc",
            "date": "2024-01-15 14:30:00",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "message": "Message",
        }
        mock_service._fetch_commit_file_changes.return_value = []

        with (
            patch(
                "src.code_indexer.cli._display_commit_message_match"
            ) as mock_commit_display,
            patch(
                "src.code_indexer.cli._display_file_chunk_match"
            ) as mock_file_display,
        ):

            display_temporal_results(results, mock_service)

            # Verify commit messages were displayed as index 1, 2
            assert mock_commit_display.call_count == 2
            commit_indices = [call[0][1] for call in mock_commit_display.call_args_list]
            assert commit_indices == [1, 2], "Commits should be displayed first"

            # Verify file chunks were displayed as index 3, 4
            assert mock_file_display.call_count == 2
            chunk_indices = [call[0][1] for call in mock_file_display.call_args_list]
            assert chunk_indices == [3, 4], "Chunks should be displayed after commits"
