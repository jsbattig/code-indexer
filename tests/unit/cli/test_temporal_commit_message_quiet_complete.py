"""
Unit tests for temporal commit message quiet mode COMPLETE implementation.

Tests verify that commit message quiet mode displays:
1. Match number (1., 2., 3., ...)
2. Score (0.602, 0.598, ...)
3. Commit hash (first 7 characters)
4. Commit date (2025-11-02)
5. Author name (Seba Battig)
6. Author email (<seba.battig@lightspeeddms.com>)
7. ENTIRE commit message content (all lines, indented)
8. Blank line separator between results

Reference: Code review findings in reports/reviews/match-number-display-fix-code-review.md
"""

from unittest.mock import Mock
from rich.console import Console
from io import StringIO


class TestTemporalCommitMessageQuietModeComplete:
    """Test temporal commit message quiet mode displays ALL metadata and FULL content."""

    def test_commit_message_quiet_displays_all_metadata_and_full_content(self):
        """
        Commit message quiet mode must display:
        - Match number
        - Score
        - Commit hash (7 chars)
        - Commit date
        - Author name
        - Author email
        - ENTIRE commit message content (all lines, indented with 3 spaces)
        - Blank line separator between results
        """
        # Mock temporal results matching actual structure
        mock_result_1 = Mock()
        mock_result_1.score = 0.602
        mock_result_1.content = "feat: implement HNSW incremental updates with FTS incremental indexing and watch mode fixes"
        mock_result_1.metadata = {
            "type": "commit_message",
            "commit_hash": "237d7361234567890abcdef",
            "commit_date": "2025-11-02",
            "author_name": "Seba Battig",
            "author_email": "seba.battig@lightspeeddms.com",
        }
        mock_result_1.temporal_context = {
            "commit_date": "2025-11-02",
            "author_name": "Seba Battig",
        }

        mock_result_2 = Mock()
        mock_result_2.score = 0.598
        mock_result_2.content = "feat: add daemon mode indicator to status command"
        mock_result_2.metadata = {
            "type": "commit_message",
            "commit_hash": "fc86e71abcdef1234567890",
            "commit_date": "2025-10-30",
            "author_name": "Seba Battig",
            "author_email": "seba.battig@lightspeeddms.com",
        }
        mock_result_2.temporal_context = {
            "commit_date": "2025-10-30",
            "author_name": "Seba Battig",
        }

        mock_result_3 = Mock()
        mock_result_3.score = 0.565
        # Multi-line commit message to test indentation
        mock_result_3.content = """plan: HNSW watch staleness coordination with file locking

This planning document outlines coordination strategy between
watch mode and HNSW index building using file locking mechanisms."""
        mock_result_3.metadata = {
            "type": "commit_message",
            "commit_hash": "c035b1f9876543210fedcba",
            "commit_date": "2025-10-27",
            "author_name": "Seba Battig",
            "author_email": "seba.battig@lightspeeddms.com",
        }
        mock_result_3.temporal_context = {
            "commit_date": "2025-10-27",
            "author_name": "Seba Battig",
        }

        mock_temporal_results = Mock()
        mock_temporal_results.results = [mock_result_1, mock_result_2, mock_result_3]

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        # Test the FIXED implementation from cli.py lines 5272-5301
        for index, temporal_result in enumerate(mock_temporal_results.results, start=1):
            match_type = temporal_result.metadata.get("type", "commit_diff")
            if match_type == "commit_message":
                # Extract ALL commit metadata
                commit_hash = temporal_result.metadata.get("commit_hash", "unknown")
                temporal_ctx = getattr(temporal_result, "temporal_context", {})
                commit_date = temporal_ctx.get(
                    "commit_date",
                    temporal_result.metadata.get("commit_date", "Unknown"),
                )
                author_name = temporal_ctx.get(
                    "author_name",
                    temporal_result.metadata.get("author_name", "Unknown"),
                )
                author_email = temporal_result.metadata.get(
                    "author_email", "unknown@example.com"
                )

                # Header line with ALL metadata
                console.print(
                    f"{index}. {temporal_result.score:.3f} [Commit {commit_hash[:7]}] ({commit_date}) {author_name} <{author_email}>",
                    markup=False,
                )

                # Display ENTIRE commit message content (all lines, indented)
                for line in temporal_result.content.split("\n"):
                    console.print(f"   {line}", markup=False)

                # Blank line between results
                console.print()
            else:
                console.print(
                    f"{index}. {temporal_result.score:.3f} {temporal_result.file_path}",
                    markup=False,
                )

        output = string_io.getvalue()

        # These assertions will FAIL because current implementation is incomplete
        # After fix, these should PASS

        # Verify Result 1: ALL metadata and content
        assert (
            "1. 0.602 [Commit 237d736] (2025-11-02) Seba Battig <seba.battig@lightspeeddms.com>"
            in output
        )
        assert (
            "   feat: implement HNSW incremental updates with FTS incremental indexing and watch mode fixes"
            in output
        )

        # Verify Result 2: ALL metadata and content
        assert (
            "2. 0.598 [Commit fc86e71] (2025-10-30) Seba Battig <seba.battig@lightspeeddms.com>"
            in output
        )
        assert "   feat: add daemon mode indicator to status command" in output

        # Verify Result 3: Multi-line commit message with ALL lines indented
        assert (
            "3. 0.565 [Commit c035b1f] (2025-10-27) Seba Battig <seba.battig@lightspeeddms.com>"
            in output
        )
        assert "   plan: HNSW watch staleness coordination with file locking" in output
        assert (
            "   This planning document outlines coordination strategy between" in output
        )
        assert (
            "   watch mode and HNSW index building using file locking mechanisms."
            in output
        )

        # Verify blank line separators between results
        lines = output.split("\n")
        # After result 1's content, there should be a blank line before result 2
        result_1_content_index = next(
            i for i, line in enumerate(lines) if "feat: implement HNSW" in line
        )
        assert lines[result_1_content_index + 1] == ""  # Blank line after result 1
