"""
Unit tests for Bug #4: Rich console crashes on temporal search with special characters.

BUG: Temporal search output crashes with markup parsing errors when diff content
contains regex or special characters like [/(lth|ct|rth)/...].

ROOT CAUSE: Rich console.print() interprets diff content as markup tags.

SOLUTION: Use markup=False when printing diff content, or use Text() with no_wrap=True.
"""

from unittest.mock import MagicMock, patch
import pytest
from rich.console import Console
from io import StringIO


def test_rich_markup_crash_with_regex_in_diff_content():
    """
    FAILING TEST: Demonstrates Rich markup crash when diff contains regex patterns.

    This test reproduces the exact error reported:
    "Unexpected error: closing tag '[/(lth|ct|rth)/...' doesn't match any open tag"

    The fix is to add markup=False to console.print() calls displaying diff content.
    """
    # Import the display functions
    from code_indexer.cli import _display_file_chunk_match

    # Create mock result with JavaScript regex in diff content
    # This is the exact pattern that causes Rich to crash
    diff_content = """@@ -1,5 +1,5 @@
 const patterns = {
-    old: [/(foo|bar)/g],
+    new: [/(lth|ct|rth)/g, /test/i],
 };
 export default patterns;"""

    mock_result = MagicMock()
    mock_result.metadata = {
        "path": "src/patterns.js",
        "line_start": 10,
        "line_end": 14,
        "commit_hash": "abc1234567890def",
        "diff_type": "modified",
        "author_name": "Test Author",
        "author_email": "test@example.com",
        "commit_date": "2024-01-15",
        "commit_message": "Update regex patterns",
        "type": "commit_diff",
    }
    mock_result.temporal_context = {
        "commit_date": "2024-01-15",
        "author_name": "Test Author",
        "commit_message": "Update regex patterns",
    }
    mock_result.content = diff_content
    mock_result.score = 0.95

    mock_temporal_service = MagicMock()

    # Capture console output to verify it doesn't crash
    console_output = StringIO()

    # Patch the global console object in cli module
    with patch("code_indexer.cli.console", Console(file=console_output, markup=True)):
        # This should NOT crash with Rich markup error
        # If it crashes, the test will fail with the exact error we're trying to fix
        try:
            _display_file_chunk_match(mock_result, 1, mock_temporal_service)
            output = console_output.getvalue()

            # Verify output contains expected content
            assert "src/patterns.js" in output
            assert "abc1234" in output  # Short commit hash
            assert "modified" in output or "MODIFIED" in output

            # Verify diff content is displayed (should contain the regex pattern)
            assert "[/(lth|ct|rth)/g" in output or "lth|ct|rth" in output

        except Exception as e:
            # If we get a Rich markup error, the test should fail with clear message
            error_msg = str(e)
            if (
                "doesn't match any open tag" in error_msg
                or "markup" in error_msg.lower()
            ):
                pytest.fail(
                    f"Rich markup parsing error (Bug #4): {error_msg}\n"
                    "Fix: Add markup=False to console.print() calls displaying diff content"
                )
            else:
                # Re-raise unexpected errors
                raise
