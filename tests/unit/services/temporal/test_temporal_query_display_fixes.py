"""Test fixes for temporal query display issues.

ISSUE 1: Results not sorted chronologically (reverse chronological order)
ISSUE 2: Suppress ":0-0" line numbers for temporal diffs
"""

from pathlib import Path
from unittest.mock import Mock

from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
    TemporalSearchResult,
)


class TestTemporalQuerySorting:
    """Test that temporal results are sorted reverse chronologically (newest first)."""

    def test_results_sorted_newest_first(self):
        """Temporal results should be sorted newest first (like git log)."""
        # Setup
        config_manager = Mock()
        project_root = Path("/tmp/test_repo")
        vector_store = Mock()
        embedding_provider = Mock()

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
            vector_store_client=vector_store,
            embedding_provider=embedding_provider,
            collection_name="test-collection",
        )

        # Create mock results with different timestamps
        # Simulate semantic search returning results in random order
        # Using timestamps that fall within the date range (adding hours to avoid edge cases)
        # 2023-01-01 12:00 = 1672574400, 2023-01-02 12:00 = 1672660800, 2023-01-03 12:00 = 1672747200
        # NEW FORMAT: chunk_text at root level
        result1 = {
            "chunk_text": "content1",  # NEW FORMAT
            "payload": {
                "path": "file1.py",
                "commit_hash": "abc123",
                "commit_timestamp": 1672574400,  # 2023-01-01 12:00 (Oldest)
                "commit_date": "2023-01-01",
                "author_name": "User",
                "diff_type": "modified",
            },
            "score": 0.9,
        }
        result2 = {
            "chunk_text": "content2",  # NEW FORMAT
            "payload": {
                "path": "file2.py",
                "commit_hash": "def456",
                "commit_timestamp": 1672747200,  # 2023-01-03 12:00 (Newest)
                "commit_date": "2023-01-03",
                "author_name": "User",
                "diff_type": "added",
            },
            "score": 0.95,
        }
        result3 = {
            "chunk_text": "content3",  # NEW FORMAT
            "payload": {
                "path": "file3.py",
                "commit_hash": "ghi789",
                "commit_timestamp": 1672660800,  # 2023-01-02 12:00 (Middle)
                "commit_date": "2023-01-02",
                "author_name": "User",
                "diff_type": "deleted",
            },
            "score": 0.85,
        }

        # Mock vector store to return results in random order
        # For non-FilesystemVectorStore path (QdrantClient behavior)
        vector_store.search.return_value = [
            result1,
            result2,
            result3,
        ]  # Just list, not tuple
        vector_store.collection_exists.return_value = True
        embedding_provider.get_embedding.return_value = [0.1] * 1536

        # Execute
        results = service.query_temporal(
            query="test",
            time_range=("2023-01-01", "2023-01-03"),
            limit=10,
        )

        # Verify: Results should be reverse chronological (newest first)
        assert len(results.results) == 3
        assert (
            results.results[0].temporal_context["commit_timestamp"] == 1672747200
        )  # Newest (2023-01-03 12:00)
        assert (
            results.results[1].temporal_context["commit_timestamp"] == 1672660800
        )  # Middle (2023-01-02 12:00)
        assert (
            results.results[2].temporal_context["commit_timestamp"] == 1672574400
        )  # Oldest (2023-01-01 12:00)

        # Verify they're NOT sorted by score
        assert results.results[0].score == 0.95  # Newest (not highest score)
        assert results.results[1].score == 0.85  # Middle (lowest score!)
        assert results.results[2].score == 0.9  # Oldest


class TestTemporalDisplayLineNumbers:
    """Test smart line number display logic (suppress :0-0 for temporal diffs)."""

    def test_cli_display_suppresses_zero_line_numbers(self):
        """CLI display should suppress :0-0 for temporal diffs with zero line numbers."""
        from io import StringIO
        from unittest.mock import patch
        from code_indexer.cli import _display_file_chunk_match
        from rich.console import Console

        # Create result with zero line numbers (typical for temporal diffs)
        result = TemporalSearchResult(
            file_path="src/file.py",
            chunk_index=0,
            content="def foo():\n    pass",
            score=0.9,
            metadata={
                "path": "src/file.py",
                "line_start": 0,
                "line_end": 0,
                "diff_type": "modified",
                "commit_hash": "abc123",
                "author_name": "User",
                "author_email": "user@example.com",
            },
            temporal_context={
                "commit_hash": "abc123",
                "commit_date": "2023-01-01",
                "commit_message": "Test commit",
                "author_name": "User",
                "commit_timestamp": 1000,
                "diff_type": "modified",
            },
        )

        # Capture console output
        output = StringIO()
        test_console = Console(file=output, force_terminal=True, width=120)

        # Mock the global console in cli module
        with patch("code_indexer.cli.console", test_console):
            _display_file_chunk_match(result, index=1, temporal_service=None)

        # Get output
        display_output = output.getvalue()

        # Strip ANSI escape codes for reliable testing
        import re

        ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
        clean_output = ansi_escape.sub("", display_output)

        # Verify: Should NOT contain :0-0 (the key requirement)
        assert (
            ":0-0" not in clean_output
        ), f"Output should not contain ':0-0', but got: {clean_output}"
        # Verify: Should contain the file path
        assert "src/file.py" in clean_output
        # Verify: Should contain MODIFIED marker
        assert "MODIFIED" in clean_output
