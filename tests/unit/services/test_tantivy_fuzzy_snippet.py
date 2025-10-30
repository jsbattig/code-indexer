"""
Unit tests for Tantivy fuzzy search snippet display.

Tests verify that fuzzy search (edit_distance > 0) correctly displays code snippets
and matches actual text in content, not the query text.
"""

import tempfile
from pathlib import Path

import pytest

from code_indexer.services.tantivy_index_manager import TantivyIndexManager


@pytest.fixture
def temp_index_dir():
    """Create a temporary directory for FTS index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def indexed_manager(temp_index_dir):
    """
    Create TantivyIndexManager with indexed test content.

    Content includes:
    - Python file with "glob pattern" text
    - Markdown file with "global pattern matching" text
    - JavaScript file with "glob patterns are useful" text
    """
    manager = TantivyIndexManager(temp_index_dir)

    # Initialize index
    manager.initialize_index()

    # Add test documents
    test_docs = [
        {
            "path": "tests/unit/services/test_patterns.py",
            "content_raw": '''"""Test glob pattern matching."""
import re

def test_glob_pattern():
    """Test glob pattern functionality."""
    pattern = "*.py"
    assert match_glob_pattern(pattern, "test.py")
    assert not match_glob_pattern(pattern, "test.js")
''',
            "content": '''"""test glob pattern matching."""
import re

def test_glob_pattern():
    """test glob pattern functionality."""
    pattern = "*.py"
    assert match_glob_pattern(pattern, "test.py")
    assert not match_glob_pattern(pattern, "test.js")
''',  # Lowercase version for case-insensitive search
            "language": "py",
            "line_start": 1,
            "line_end": 8,
            "identifiers": ["test_glob_pattern", "match_glob_pattern"],
        },
        {
            "path": "docs/patterns.md",
            "content_raw": """# Pattern Matching Guide

## Global Pattern Matching

When working with global pattern matching systems, you need to understand:

1. Glob patterns for file matching
2. Regex patterns for text matching
3. Wildcard patterns for searching
""",
            "content": """# pattern matching guide

## global pattern matching

when working with global pattern matching systems, you need to understand:

1. glob patterns for file matching
2. regex patterns for text matching
3. wildcard patterns for searching
""",
            "language": "md",
            "line_start": 1,
            "line_end": 9,
            "identifiers": [],
        },
        {
            "path": "src/utils/patterns.js",
            "content_raw": """/**
 * Pattern utilities
 */

// Glob patterns are useful for file matching
function matchGlobPattern(pattern, filename) {
    const regex = globToRegex(pattern);
    return regex.test(filename);
}
""",
            "content": """/**
 * pattern utilities
 */

// glob patterns are useful for file matching
function matchglobpattern(pattern, filename) {
    const regex = globtoregex(pattern);
    return regex.test(filename);
}
""",
            "language": "js",
            "line_start": 1,
            "line_end": 9,
            "identifiers": ["matchGlobPattern", "globToRegex"],
        },
    ]

    # Add all documents
    for doc in test_docs:
        manager.add_document(doc)

    # Commit changes
    manager.commit()

    return manager


class TestFuzzySearchSnippetDisplay:
    """Test fuzzy search snippet display functionality."""

    def test_exact_match_shows_snippet(self, indexed_manager):
        """
        Test that exact matches show snippets (baseline/regression test).

        This ensures our fix doesn't break existing exact match functionality.
        """
        results = indexed_manager.search(
            query_text="glob pattern",
            edit_distance=0,  # Exact match
            snippet_lines=3,
            limit=10,
        )

        # Should find match in Python file
        assert len(results) > 0

        # Find the Python file result
        py_result = next((r for r in results if r["path"].endswith(".py")), None)
        assert py_result is not None

        # Snippet should be present
        assert py_result["snippet"] != ""
        assert "glob pattern" in py_result["snippet"].lower()

        # Line and column should be valid
        assert py_result["line"] > 0
        assert py_result["column"] > 0

    def test_fuzzy_single_char_difference_shows_snippet(self, indexed_manager):
        """
        Test that fuzzy search with 1-char difference shows snippet.

        Search for "glub pattern" (typo: u instead of o) should find "glob pattern"
        and display the code snippet with context.
        """
        results = indexed_manager.search(
            query_text="glub pattern",  # Typo: u instead of o
            edit_distance=1,  # Allow 1-char difference
            snippet_lines=3,
            limit=10,
        )

        # Should find fuzzy match in Python file
        assert len(results) > 0

        # Find the Python file result
        py_result = next((r for r in results if r["path"].endswith(".py")), None)
        assert py_result is not None, "Should find fuzzy match in Python file"

        # BUG FIX: Snippet should be present (currently returns empty string)
        assert py_result["snippet"] != "", "Fuzzy match should show snippet"

        # Snippet should contain the ACTUAL matched text, not query text
        assert (
            "glob pattern" in py_result["snippet"].lower()
        ), "Snippet should contain actual matched text 'glob pattern'"
        assert (
            "glub pattern" not in py_result["snippet"].lower()
        ), "Snippet should NOT contain query text 'glub pattern'"

        # Line and column should be valid
        assert py_result["line"] > 0, "Line number should be valid"
        assert py_result["column"] > 0, "Column number should be valid"

    def test_fuzzy_multi_word_query_shows_snippet(self, indexed_manager):
        """
        Test that fuzzy search with multi-word query shows snippet.

        Search for "global patern" (typo: missing t in pattern) should find
        "global pattern matching" and display snippet.
        """
        results = indexed_manager.search(
            query_text="global patern",  # Typo: missing t
            edit_distance=1,
            snippet_lines=3,
            limit=10,
        )

        # Should find fuzzy match in Markdown file
        assert len(results) > 0

        # Find the Markdown file result
        md_result = next((r for r in results if r["path"].endswith(".md")), None)
        assert md_result is not None, "Should find fuzzy match in Markdown file"

        # BUG FIX: Snippet should be present
        assert md_result["snippet"] != "", "Fuzzy match should show snippet"

        # Snippet should contain actual matched text
        assert (
            "global pattern" in md_result["snippet"].lower()
        ), "Snippet should contain actual matched text 'global pattern'"

        # Line and column should be valid
        assert md_result["line"] > 0
        assert md_result["column"] > 0

    def test_fuzzy_match_shows_actual_text_not_query(self, indexed_manager):
        """
        Test that match_text shows ACTUAL matched text, not query text.

        When searching for "glub" (fuzzy), match_text should be "glob" (actual),
        not "glub" (query).
        """
        results = indexed_manager.search(
            query_text="glub",  # Typo
            edit_distance=1,
            snippet_lines=3,
            limit=10,
        )

        # Should find fuzzy matches
        assert len(results) > 0

        # Check that match_text contains actual matched text
        for result in results:
            # match_text should NOT be the query text "glub"
            assert (
                result["match_text"].lower() != "glub"
            ), f"match_text should be actual match, not query: {result['match_text']}"

            # match_text should be similar to actual content (e.g., "glob")
            # For fuzzy matches, we expect to see the actual word from content
            assert result["match_text"] != "", "match_text should not be empty"

    def test_fuzzy_line_column_accuracy(self, indexed_manager):
        """
        Test that line/column numbers are accurate for fuzzy matches.

        The line/column should point to the ACTUAL matched text location,
        not a fallback position.
        """
        results = indexed_manager.search(
            query_text="glub pattern",
            edit_distance=1,
            snippet_lines=3,
            limit=10,
        )

        # Find Python file result
        py_result = next((r for r in results if r["path"].endswith(".py")), None)
        assert py_result is not None

        # Line should be valid (>0, not the fallback line from document)
        # In our test content, "glob pattern" appears in line 1 and line 5
        # The fuzzy matcher finds the first occurrence (line 1)
        assert (
            py_result["line"] > 0
        ), f"Line number should be valid: {py_result['line']}"

        # Column should be > 1 (not the fallback value of 1)
        # The actual "glob pattern" text starts after some leading characters
        assert (
            py_result["column"] > 1
        ), f"Column should point to match location, not fallback: {py_result['column']}"

    def test_fuzzy_multiple_results_all_have_snippets(self, indexed_manager):
        """
        Test that ALL fuzzy search results show snippets, not just some.

        When searching with fuzzy matching, every result should have a snippet.
        """
        results = indexed_manager.search(
            query_text="glob patern",  # Matches multiple files with fuzzy
            edit_distance=1,
            snippet_lines=3,
            limit=10,
        )

        # Should find multiple matches
        assert len(results) >= 2, "Should find multiple fuzzy matches"

        # ALL results should have snippets
        for result in results:
            assert (
                result["snippet"] != ""
            ), f"All fuzzy results should have snippets: {result['path']}"
            assert (
                result["line"] > 0
            ), f"All fuzzy results should have valid line: {result['path']}"
            assert (
                result["column"] > 0
            ), f"All fuzzy results should have valid column: {result['path']}"

    def test_fuzzy_with_zero_snippet_lines(self, indexed_manager):
        """
        Test that fuzzy search with snippet_lines=0 works correctly.

        Even without snippets, line/column should be valid.
        """
        results = indexed_manager.search(
            query_text="glub pattern",
            edit_distance=1,
            snippet_lines=0,  # No snippet requested
            limit=10,
        )

        # Should find matches
        assert len(results) > 0

        # Find Python file result
        py_result = next((r for r in results if r["path"].endswith(".py")), None)
        assert py_result is not None

        # Snippet should be empty (as requested)
        assert py_result["snippet"] == ""

        # But line/column should still be valid
        assert py_result["line"] > 0
        assert py_result["column"] > 0

    def test_exact_match_no_regression(self, indexed_manager):
        """
        Test that exact matches still work perfectly after fuzzy fix.

        This is a comprehensive regression test to ensure our fuzzy matching
        fix doesn't break the existing exact match functionality.
        """
        # Test various exact match scenarios
        test_cases = [
            ("glob pattern", ".py"),
            ("global pattern", ".md"),
            ("glob patterns", ".js"),
        ]

        for query, file_ext in test_cases:
            results = indexed_manager.search(
                query_text=query,
                edit_distance=0,  # Exact match
                snippet_lines=3,
                limit=10,
            )

            # Should find at least one match
            assert len(results) > 0, f"Should find exact match for '{query}'"

            # Find result with expected file type
            file_result = next(
                (r for r in results if r["path"].endswith(file_ext)), None
            )
            assert (
                file_result is not None
            ), f"Should find exact match in {file_ext} file for '{query}'"

            # Snippet should be present
            assert (
                file_result["snippet"] != ""
            ), f"Exact match should have snippet for '{query}'"

            # Should contain query text
            assert (
                query.lower() in file_result["snippet"].lower()
            ), f"Snippet should contain exact query text '{query}'"

            # Line/column should be valid
            assert file_result["line"] > 0
            assert file_result["column"] > 0
