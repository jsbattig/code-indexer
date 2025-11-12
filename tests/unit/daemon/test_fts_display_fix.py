"""Tests for FTS display bug fix in daemon mode.

This module tests that the daemon's _display_results() function correctly handles
both FTS and semantic result formats without KeyError crashes.

Bug Context:
- FTS queries in daemon mode crash with KeyError: 'payload'
- Root cause: _display_results() always calls _display_semantic_results()
- FTS results have different structure (match_text, snippet) vs semantic (payload)
- Fix: Detect result type and call appropriate display function
"""

from unittest.mock import Mock, patch
from io import StringIO

import pytest

from code_indexer.cli_daemon_fast import _display_results


class TestFTSDisplayFix:
    """Test suite for FTS display bug fix in daemon mode."""

    def test_fts_results_structure_detection(self):
        """Test that FTS result structure is correctly detected.

        FTS results have keys like: match_text, snippet, path, line, column
        Semantic results have keys like: score, payload
        """
        # FTS result structure
        fts_result = {
            "path": "src/auth.py",
            "line": 10,
            "column": 5,
            "match_text": "authenticate",
            "language": "python",
            "snippet": "def authenticate(user):",
            "snippet_start_line": 10,
        }

        # Semantic result structure
        semantic_result = {
            "score": 0.85,
            "payload": {
                "path": "src/config.py",
                "content": "config = load_config()",
                "line_start": 5,
                "line_end": 6,
            },
        }

        # FTS result should have match_text and no payload
        assert "match_text" in fts_result
        assert "payload" not in fts_result

        # Semantic result should have payload and no match_text
        assert "payload" in semantic_result
        assert "match_text" not in semantic_result

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_calls_fts_display_for_fts_results(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that _display_results() calls _display_fts_results() for FTS results.

        This is the critical fix: detect FTS format and route to correct display function.
        """
        # Arrange: FTS results
        fts_results = [
            {
                "path": "src/auth.py",
                "line": 10,
                "column": 5,
                "match_text": "authenticate",
                "language": "python",
                "snippet": "def authenticate(user):",
                "snippet_start_line": 10,
            },
            {
                "path": "src/login.py",
                "line": 5,
                "column": 1,
                "match_text": "login",
                "language": "python",
                "snippet": "def login(username, password):",
                "snippet_start_line": 5,
            },
        ]
        console = Mock()

        # Act: Display FTS results
        _display_results(fts_results, console, timing_info=None)

        # Assert: Should call FTS display, NOT semantic display
        mock_fts_display.assert_called_once()
        mock_semantic_display.assert_not_called()

        # Verify arguments passed to FTS display
        call_args = mock_fts_display.call_args
        assert call_args[1]["results"] == fts_results
        assert call_args[1]["console"] == console
        assert call_args[1]["quiet"] is False

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_calls_semantic_display_for_semantic_results(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that _display_results() calls _display_semantic_results() for semantic results.

        This ensures backward compatibility: semantic results continue to work as before.
        """
        # Arrange: Semantic results
        semantic_results = [
            {
                "score": 0.85,
                "payload": {
                    "path": "src/config.py",
                    "content": "config = load_config()",
                    "line_start": 5,
                    "line_end": 6,
                    "language": "python",
                },
            },
            {
                "score": 0.78,
                "payload": {
                    "path": "src/settings.py",
                    "content": "settings = Settings()",
                    "line_start": 10,
                    "line_end": 11,
                    "language": "python",
                },
            },
        ]
        console = Mock()
        timing_info = {"total": 0.5, "query": 0.1}

        # Act: Display semantic results
        _display_results(semantic_results, console, timing_info=timing_info)

        # Assert: Should call semantic display, NOT FTS display
        mock_semantic_display.assert_called_once()
        mock_fts_display.assert_not_called()

        # Verify arguments passed to semantic display
        call_args = mock_semantic_display.call_args
        assert call_args[1]["results"] == semantic_results
        assert call_args[1]["console"] == console
        assert call_args[1]["quiet"] is False
        assert call_args[1]["timing_info"] == timing_info

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_handles_empty_results(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that _display_results() handles empty result lists gracefully.

        Empty results should not crash and should call semantic display by default.
        """
        # Arrange: Empty results
        empty_results = []
        console = Mock()

        # Act: Display empty results
        _display_results(empty_results, console, timing_info=None)

        # Assert: Should call semantic display for empty results (default behavior)
        mock_semantic_display.assert_called_once()
        mock_fts_display.assert_not_called()

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_detects_fts_by_match_text_key(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that _display_results() detects FTS results by match_text key presence.

        FTS results always have match_text key, semantic results never do.
        """
        # Arrange: FTS result with match_text
        fts_results = [
            {
                "path": "test.py",
                "line": 1,
                "column": 1,
                "match_text": "test",  # Key indicator of FTS format
                "snippet": "test code",
            }
        ]
        console = Mock()

        # Act
        _display_results(fts_results, console, timing_info=None)

        # Assert: match_text presence should trigger FTS display
        mock_fts_display.assert_called_once()
        mock_semantic_display.assert_not_called()

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_detects_semantic_by_payload_key(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that _display_results() detects semantic results by payload key presence.

        Semantic results always have payload key, FTS results never do.
        """
        # Arrange: Semantic result with payload
        semantic_results = [
            {
                "score": 0.9,
                "payload": {  # Key indicator of semantic format
                    "path": "test.py",
                    "content": "test content",
                },
            }
        ]
        console = Mock()

        # Act
        _display_results(semantic_results, console, timing_info=None)

        # Assert: payload presence should trigger semantic display
        mock_semantic_display.assert_called_once()
        mock_fts_display.assert_not_called()

    @patch("code_indexer.cli._display_fts_results")
    def test_display_results_no_crash_on_fts_results(self, mock_fts_display):
        """Test that FTS results don't cause KeyError: 'payload' crash.

        This is the original bug: _display_results() tried to access result['payload']
        on FTS results which don't have payload key.
        """
        # Arrange: FTS results WITHOUT payload key
        fts_results = [
            {
                "path": "src/auth.py",
                "line": 10,
                "column": 5,
                "match_text": "authenticate",  # FTS-specific key
                "snippet": "def authenticate(user):",
                # NO payload key - this is what caused the crash
            }
        ]
        console = Mock()

        # Act & Assert: Should not raise KeyError
        try:
            _display_results(fts_results, console, timing_info=None)
        except KeyError as e:
            pytest.fail(f"_display_results() crashed with KeyError: {e}")

        # Verify correct display function was called
        mock_fts_display.assert_called_once()

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_display_results_timing_info_passed_to_semantic_only(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that timing_info is passed to semantic display but not FTS display.

        FTS display doesn't currently support timing info in its signature.
        """
        # Test semantic with timing
        semantic_results = [
            {"score": 0.85, "payload": {"path": "test.py", "content": "test"}}
        ]
        console = Mock()
        timing_info = {"total": 0.5, "query": 0.1}

        _display_results(semantic_results, console, timing_info=timing_info)

        # Assert: timing_info passed to semantic display
        call_args = mock_semantic_display.call_args
        assert call_args[1]["timing_info"] == timing_info

        # Reset mocks
        mock_semantic_display.reset_mock()
        mock_fts_display.reset_mock()

        # Test FTS without timing
        fts_results = [
            {"path": "test.py", "line": 1, "column": 1, "match_text": "test"}
        ]

        _display_results(fts_results, console, timing_info=timing_info)

        # Assert: FTS display doesn't receive timing_info (not in signature)
        call_args = mock_fts_display.call_args
        assert "timing_info" not in call_args[1]


class TestIntegrationWithRealDisplayFunctions:
    """Integration tests using real display functions (not mocked)."""

    def test_fts_display_with_real_function(self):
        """Test FTS results with real _display_fts_results() function.

        This ensures the actual display function works correctly with FTS data.
        """
        # Import real function
        from code_indexer.cli import _display_fts_results
        from rich.console import Console

        # Arrange: Real FTS results
        fts_results = [
            {
                "path": "src/auth.py",
                "line": 10,
                "column": 5,
                "match_text": "authenticate",
                "language": "python",
                "snippet": "def authenticate(user, password):\n    return check_credentials(user, password)",
                "snippet_start_line": 10,
            }
        ]

        # Act: Capture console output
        console = Console(file=StringIO(), force_terminal=True)
        _display_fts_results(fts_results, quiet=False, console=console)

        # Assert: No crash, output generated
        output = console.file.getvalue()
        assert "auth.py" in output
        assert "authenticate" in output
        # Check for line number (may have ANSI codes around it)
        assert "10" in output

    def test_semantic_display_with_real_function(self):
        """Test semantic results with real _display_semantic_results() function.

        This ensures the actual display function works correctly with semantic data.
        """
        # Import real function
        from code_indexer.cli import _display_semantic_results
        from rich.console import Console

        # Arrange: Real semantic results
        semantic_results = [
            {
                "score": 0.85,
                "payload": {
                    "path": "src/config.py",
                    "content": "config = load_config()",
                    "line_start": 5,
                    "line_end": 6,
                    "language": "python",
                },
            }
        ]

        # Act: Capture console output
        console = Console(file=StringIO(), force_terminal=True)
        _display_semantic_results(
            semantic_results, console, quiet=False, timing_info=None
        )

        # Assert: No crash, output generated
        output = console.file.getvalue()
        assert "config.py" in output
        assert "0.85" in output or "85" in output  # Score display


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("code_indexer.cli._display_fts_results")
    @patch("code_indexer.cli._display_semantic_results")
    def test_results_with_mixed_formats_defaults_to_first_result_type(
        self, mock_semantic_display, mock_fts_display
    ):
        """Test that mixed result formats use first result to determine type.

        This shouldn't happen in practice, but the code should handle it gracefully.
        """
        # Arrange: Mixed formats (shouldn't happen in practice)
        mixed_results = [
            {
                "match_text": "test",  # FTS format
                "path": "test1.py",
                "line": 1,
                "column": 1,
            },
            {"score": 0.8, "payload": {"path": "test2.py"}},  # Semantic format
        ]
        console = Mock()

        # Act: Should use first result to determine type (FTS in this case)
        _display_results(mixed_results, console, timing_info=None)

        # Assert: Should use FTS display based on first result
        mock_fts_display.assert_called_once()
        mock_semantic_display.assert_not_called()

    @patch("code_indexer.cli._display_fts_results")
    def test_fts_results_with_minimal_keys(self, mock_fts_display):
        """Test FTS results with minimal required keys still work.

        FTS results might not always have all optional fields.
        """
        # Arrange: Minimal FTS result
        minimal_fts = [
            {
                "path": "test.py",
                "line": 1,
                "column": 1,
                "match_text": "test",
                # No language, snippet, etc.
            }
        ]
        console = Mock()

        # Act
        _display_results(minimal_fts, console, timing_info=None)

        # Assert: Should still work
        mock_fts_display.assert_called_once()
