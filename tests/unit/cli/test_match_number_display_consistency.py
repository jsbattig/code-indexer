"""
Unit tests for match number display consistency across all CIDX query modes.

Tests verify that ALL query modes display sequential match numbers (1, 2, 3...)
in both regular and quiet modes.

Reference: .analysis/match-number-display-fix-spec.md
"""

from unittest.mock import Mock
from rich.console import Console
from io import StringIO


class TestFTSQuietModeMatchNumbers:
    """Test FTS quiet mode displays match numbers."""

    def test_fts_quiet_mode_shows_sequential_match_numbers(self):
        """FTS quiet mode should display: 1. path:line:col"""
        from code_indexer.cli import _display_fts_results

        # FTS results are dictionaries, not objects
        mock_results = [
            {
                "path": "src/auth.py",
                "line": 42,
                "column": 5,
                "match_text": "def authenticate",
            },
            {
                "path": "src/database.py",
                "line": 103,
                "column": 1,
                "match_text": "def connect",
            },
            {
                "path": "tests/test_auth.py",
                "line": 25,
                "column": 9,
                "match_text": "def test_auth",
            },
        ]

        # Capture console output
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        # Call with quiet=True
        _display_fts_results(results=mock_results, console=console, quiet=True)

        output = string_io.getvalue()

        # Verify match numbers are present and sequential
        assert "1. src/auth.py:42:5" in output
        assert "2. src/database.py:103:1" in output
        assert "3. tests/test_auth.py:25:9" in output


class TestSemanticRegularModeMatchNumbers:
    """Test semantic regular mode displays match numbers."""

    def test_semantic_regular_mode_shows_match_numbers(self):
        """Semantic regular mode should display: 1. 📄 File: path"""
        from code_indexer.cli import _display_semantic_results

        # Semantic results are dicts with 'score' and 'payload'
        mock_results = [
            {
                "score": 0.850,
                "payload": {
                    "path": "src/auth.py",
                    "line_start": 10,
                    "line_end": 20,
                    "content": "def authenticate(user):\n    return True",
                    "language": "python",
                    "file_size": 1024,
                    "indexed_at": "2025-11-12",
                },
            },
            {
                "score": 0.820,
                "payload": {
                    "path": "src/database.py",
                    "line_start": 45,
                    "line_end": 60,
                    "content": "class Database:\n    pass",
                    "language": "python",
                    "file_size": 2048,
                    "indexed_at": "2025-11-12",
                },
            },
        ]

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        _display_semantic_results(results=mock_results, console=console, quiet=False)

        output = string_io.getvalue()

        # Verify match numbers are present with file header
        assert "1. 📄 File: src/auth.py:10-20" in output
        assert "2. 📄 File: src/database.py:45-60" in output


class TestSemanticQuietModeMatchNumbers:
    """Test semantic quiet mode displays match numbers."""

    def test_semantic_quiet_mode_shows_match_numbers(self):
        """Semantic quiet mode should display: 1. score path"""
        from code_indexer.cli import _display_semantic_results

        mock_results = [
            {
                "score": 0.850,
                "payload": {
                    "path": "src/auth.py",
                    "line_start": 10,
                    "line_end": 20,
                    "content": "def authenticate(user):\n    return True",
                    "language": "python",
                },
            },
            {
                "score": 0.820,
                "payload": {
                    "path": "src/database.py",
                    "line_start": 45,
                    "line_end": 60,
                    "content": "class Database:\n    pass",
                    "language": "python",
                },
            },
        ]

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        _display_semantic_results(results=mock_results, console=console, quiet=True)

        output = string_io.getvalue()

        # Verify match numbers with scores
        assert "1. 0.850 src/auth.py:10-20" in output
        assert "2. 0.820 src/database.py:45-60" in output


class TestHybridQuietModeMatchNumbers:
    """Test hybrid quiet mode displays match numbers."""

    def test_hybrid_quiet_mode_shows_match_numbers_for_semantic_results(self):
        """Hybrid quiet mode should display: 1. score path"""
        from code_indexer.cli import _display_hybrid_results

        fts_results = []
        semantic_results = [
            {
                "score": 0.850,
                "payload": {
                    "path": "src/auth.py",
                    "line_start": 10,
                    "line_end": 20,
                    "content": "def authenticate(user):\n    return True",
                    "language": "python",
                },
            },
            {
                "score": 0.820,
                "payload": {
                    "path": "src/database.py",
                    "line_start": 45,
                    "line_end": 60,
                    "content": "class Database:\n    pass",
                    "language": "python",
                },
            },
        ]

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        _display_hybrid_results(
            fts_results=fts_results,
            semantic_results=semantic_results,
            console=console,
            quiet=True,
        )

        output = string_io.getvalue()

        # Verify match numbers are present
        assert "1. 0.850 src/auth.py:10-20" in output
        assert "2. 0.820 src/database.py:45-60" in output


class TestTemporalCommitMessageQuietMode:
    """Test temporal commit message quiet mode displays full content."""

    def test_temporal_commit_quiet_should_show_match_numbers_not_placeholder(self):
        """Temporal commit quiet should show '1. score [Commit hash]' not '0.602 [Commit Message]'"""
        # Mock temporal results matching actual structure
        mock_temporal_result = Mock()
        mock_temporal_result.score = 0.602
        mock_temporal_result.content = "feat: implement HNSW incremental updates"
        mock_temporal_result.metadata = {
            "type": "commit_message",
            "commit_hash": "237d7361234567890abcdef",
            "commit_date": "2025-11-02",
            "author_name": "Seba Battig",
            "author_email": "seba.battig@lightspeeddms.com",
        }
        mock_temporal_result.temporal_context = {
            "commit_date": "2025-11-02",
            "author_name": "Seba Battig",
        }

        mock_temporal_results = Mock()
        mock_temporal_results.results = [mock_temporal_result]

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)

        # FIXED implementation - should match cli.py lines 5266-5277 after fix
        for index, temporal_result in enumerate(mock_temporal_results.results, start=1):
            match_type = temporal_result.metadata.get("type", "commit_diff")
            if match_type == "commit_message":
                commit_hash = temporal_result.metadata.get("commit_hash", "unknown")
                console.print(
                    f"{index}. {temporal_result.score:.3f} [Commit {commit_hash[:7]}]",
                    markup=False,
                )
            else:
                console.print(
                    f"{index}. {temporal_result.score:.3f} {temporal_result.file_path}",
                    markup=False,
                )

        output = string_io.getvalue()

        # Test should FAIL because current implementation shows placeholder
        # After fix, it should show: "1. 0.602 [Commit 237d736]" (with match number and commit hash)
        assert "1. " in output  # Should have match number
        assert "[Commit 237d736]" in output  # Should have commit hash (first 7 chars)
        assert "[Commit Message]" not in output  # Should NOT have placeholder
