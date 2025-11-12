"""
Test for CLI temporal display file path bug.

CRITICAL BUG: CLI display layer only checks 'file_path' metadata field,
but temporal search service uses 'path' field. This causes "unknown" paths
in temporal query output.
"""

from unittest.mock import MagicMock, Mock
from io import StringIO
import sys

from code_indexer.cli import _display_file_chunk_match


def test_display_file_chunk_match_uses_path_field():
    """Test that _display_file_chunk_match reads 'path' metadata field."""
    # ARRANGE: Create a result with 'path' metadata (not 'file_path')
    result = Mock()
    result.metadata = {
        "path": "src/auth.py",
        "line_start": 10,
        "line_end": 20,
        "commit_hash": "abc123",
        "diff_type": "changed",
        "commit_message": "Test commit message",
        "commit_date": "2025-11-01",
        "author_name": "Test Author",
        "author_email": "test@example.com",
    }
    result.score = 0.95
    result.temporal_context = {}
    result.content = "def authenticate():\n    pass"

    temporal_service = MagicMock()
    temporal_service.get_file_diff.return_value = "mock diff content"

    # Capture console output
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        # ACT: Display the match
        _display_file_chunk_match(result, index=1, temporal_service=temporal_service)

        # ASSERT: Output should contain the correct file path, not "unknown"
        output = captured_output.getvalue()
        assert (
            "src/auth.py" in output
        ), f"Expected 'src/auth.py' in output, got: {output}"
        assert (
            "unknown" not in output
        ), f"Should not show 'unknown' when 'path' is present: {output}"
    finally:
        sys.stdout = sys.__stdout__
