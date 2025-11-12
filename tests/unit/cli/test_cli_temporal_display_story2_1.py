"""Unit tests for Story 2.1 CLI temporal display reimplementation."""

import unittest
from unittest.mock import Mock, patch

from src.code_indexer.cli import (
    _display_file_chunk_match,
    _display_commit_message_match,
    display_temporal_results,
)


class TestCLITemporalDisplayStory21(unittest.TestCase):
    """Test cases for Story 2.1 CLI temporal display changes."""

    def test_display_file_chunk_with_diff(self):
        """Test that file chunk matches display with diff and proper format."""
        # Create mock result
        result = Mock()
        result.metadata = {
            "type": "file_chunk",
            "file_path": "src/auth.py",
            "line_start": 45,
            "line_end": 67,
            "commit_hash": "def5678abc123",
            "blob_hash": "blob789",
        }
        result.score = 0.95
        result.content = """def validate_token(self, token):
    if not token:
        return False

    if token.expired():
        logger.warning("Token expired")
        raise TokenExpiredError()

    return True"""

        # Mock temporal service
        temporal_service = Mock()

        # Mock commit details
        temporal_service._fetch_commit_details.return_value = {
            "hash": "def5678abc123",
            "date": "2024-06-20 14:32:15",
            "author_name": "John Doe",
            "author_email": "john@example.com",
            "message": "Fix token expiry bug in JWT validation.\nNow properly logs warning and raises TokenExpiredError\ninstead of silently returning False. Updated tests\nto verify exception handling.",
        }

        # Mock diff generation
        diff_output = """[DIFF - Changes from parent abc1234 to def5678]

45   def validate_token(self, token):
46       if not token:
47           return False
48
49       if token.expired():
50  -        return False
50  +        logger.warning("Token expired")
51  +        raise TokenExpiredError()
52
53       return True"""
        temporal_service._generate_chunk_diff.return_value = diff_output

        # Capture output
        with patch("src.code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 1, temporal_service)

            # Verify display calls
            calls = mock_console.print.call_args_list

            # Check header format
            self.assertTrue(any("1. src/auth.py:45-67" in str(call) for call in calls))
            self.assertTrue(any("Score: 0.95" in str(call) for call in calls))
            self.assertTrue(any("Commit: def5678" in str(call) for call in calls))
            self.assertTrue(any("2024-06-20 14:32:15" in str(call) for call in calls))
            self.assertTrue(any("John Doe" in str(call) for call in calls))
            self.assertTrue(any("john@example.com" in str(call) for call in calls))

            # Check full commit message is displayed
            self.assertTrue(any("Fix token expiry bug" in str(call) for call in calls))
            self.assertTrue(
                any("verify exception handling" in str(call) for call in calls)
            )

            # Check diff is displayed
            self.assertTrue(any("[DIFF" in str(call) for call in calls))

    def test_display_commit_message_match(self):
        """Test that commit message matches display with proper format."""
        # Create mock result
        result = Mock()
        result.metadata = {
            "type": "commit_message",
            "commit_hash": "abc1234def567",
            "char_start": 0,
            "char_end": 150,
        }
        result.score = 0.89
        result.content = """Add JWT validation with support for RS256 algorithm.
Updated token parsing to handle new claims format.
Fixed issue with expired tokens not being rejected."""

        # Mock temporal service
        temporal_service = Mock()

        # Mock commit details
        temporal_service._fetch_commit_details.return_value = {
            "hash": "abc1234def567",
            "date": "2024-03-15 10:15:22",
            "author_name": "Jane Smith",
            "author_email": "jane@example.com",
            "message": result.content,  # Full message
        }

        # Mock file changes
        temporal_service._fetch_commit_file_changes.return_value = [
            {"file_path": "src/auth.py", "blob_hash": "blob1"},
            {"file_path": "src/tokens.py", "blob_hash": "blob2"},
            {"file_path": "tests/test_auth.py", "blob_hash": "blob3"},
        ]

        # Capture output
        with patch("src.code_indexer.cli.console") as mock_console:
            _display_commit_message_match(result, 2, temporal_service)

            # Verify display calls
            calls = mock_console.print.call_args_list

            # Check header format
            self.assertTrue(
                any("[COMMIT MESSAGE MATCH]" in str(call) for call in calls)
            )
            self.assertTrue(any("Score: 0.89" in str(call) for call in calls))
            self.assertTrue(any("Commit: abc1234" in str(call) for call in calls))
            self.assertTrue(any("2024-03-15 10:15:22" in str(call) for call in calls))
            self.assertTrue(any("Jane Smith" in str(call) for call in calls))

            # Check message content
            self.assertTrue(
                any("Message (matching section)" in str(call) for call in calls)
            )
            self.assertTrue(any("Add JWT validation" in str(call) for call in calls))

            # Check files modified
            self.assertTrue(any("Files Modified (3)" in str(call) for call in calls))
            self.assertTrue(any("src/auth.py" in str(call) for call in calls))
            self.assertTrue(any("src/tokens.py" in str(call) for call in calls))
            self.assertTrue(any("tests/test_auth.py" in str(call) for call in calls))

    def test_display_order_commit_messages_first(self):
        """Test that commit messages are displayed before file chunks."""
        # Create mixed results
        file_result1 = Mock()
        file_result1.metadata = {
            "type": "file_chunk",
            "file_path": "a.py",
            "line_start": 1,
            "line_end": 10,
            "commit_hash": "commit1",
            "blob_hash": "blob1",
        }
        file_result1.score = 0.99  # Higher score than commit message

        commit_result = Mock()
        commit_result.metadata = {"type": "commit_message", "commit_hash": "commit2"}
        commit_result.score = 0.85  # Lower score

        file_result2 = Mock()
        file_result2.metadata = {
            "type": "file_chunk",
            "file_path": "b.py",
            "line_start": 5,
            "line_end": 15,
            "commit_hash": "commit3",
            "blob_hash": "blob3",
        }
        file_result2.score = 0.90

        # Create results object
        results = Mock()
        results.results = [file_result1, commit_result, file_result2]  # Mixed order

        # Mock temporal service with minimal responses
        temporal_service = Mock()
        temporal_service._fetch_commit_details.return_value = {
            "hash": "test",
            "date": "2024-01-01",
            "author_name": "Test",
            "author_email": "test@example.com",
            "message": "Test",
        }
        temporal_service._fetch_commit_file_changes.return_value = []
        temporal_service._generate_chunk_diff.return_value = None

        # Mock the display functions to track call order
        with patch(
            "src.code_indexer.cli._display_commit_message_match"
        ) as mock_commit_display:
            with patch(
                "src.code_indexer.cli._display_file_chunk_match"
            ) as mock_file_display:
                display_temporal_results(results, temporal_service)

                # Verify commit message was displayed first (index 1)
                mock_commit_display.assert_called_once_with(
                    commit_result, 1, temporal_service
                )

                # Verify file chunks were displayed after (indices 2 and 3)
                calls = mock_file_display.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0][0], (file_result1, 2, temporal_service))
                self.assertEqual(calls[1][0], (file_result2, 3, temporal_service))

    def test_display_file_chunk_no_diff_shows_content(self):
        """Test that when no diff is available, chunk content is shown with line numbers."""
        result = Mock()
        result.metadata = {
            "type": "file_chunk",
            "file_path": "src/new_file.py",
            "line_start": 10,
            "line_end": 12,
            "commit_hash": "initial123",
            "blob_hash": "blob456",
        }
        result.score = 0.87
        result.content = """def new_function():
    # This is a new file
    return True"""

        temporal_service = Mock()
        temporal_service._fetch_commit_details.return_value = {
            "hash": "initial123",
            "date": "2024-01-01 09:00:00",
            "author_name": "Developer",
            "author_email": "dev@example.com",
            "message": "Add new file",
        }

        # No diff available (initial commit or new file)
        temporal_service._generate_chunk_diff.return_value = None

        with patch("src.code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 1, temporal_service)

            calls = mock_console.print.call_args_list

            # Should show content with line numbers when no diff
            self.assertTrue(
                any(
                    "10" in str(call) and "def new_function()" in str(call)
                    for call in calls
                )
                or any("def new_function()" in str(call) for call in calls)
            )

    def test_display_commit_message_many_files(self):
        """Test that commit message display handles many files gracefully."""
        result = Mock()
        result.metadata = {"type": "commit_message", "commit_hash": "bigcommit123"}
        result.score = 0.75
        result.content = "Massive refactoring"

        temporal_service = Mock()
        temporal_service._fetch_commit_details.return_value = {
            "hash": "bigcommit123",
            "date": "2024-02-01",
            "author_name": "Refactorer",
            "author_email": "refactor@example.com",
            "message": result.content,
        }

        # Create 15 file changes
        files = [
            {"file_path": f"src/file{i}.py", "blob_hash": f"blob{i}"} for i in range(15)
        ]
        temporal_service._fetch_commit_file_changes.return_value = files

        with patch("src.code_indexer.cli.console") as mock_console:
            _display_commit_message_match(result, 1, temporal_service)

            calls = mock_console.print.call_args_list

            # Should show Files Modified (15)
            self.assertTrue(any("Files Modified (15)" in str(call) for call in calls))

            # Should show first 10 files
            for i in range(10):
                self.assertTrue(any(f"src/file{i}.py" in str(call) for call in calls))

            # Should show "and 5 more"
            self.assertTrue(any("and 5 more" in str(call) for call in calls))


if __name__ == "__main__":
    unittest.main()
