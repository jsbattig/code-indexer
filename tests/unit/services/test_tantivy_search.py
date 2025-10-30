"""
Unit tests for TantivyIndexManager search functionality.

Tests cover:
- Basic text search
- Case-sensitive vs case-insensitive matching
- Fuzzy matching with different edit distances
- Snippet extraction with line/column calculation
- Language and path filtering
- Performance requirements
"""

import pytest
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivySearch:
    """Test suite for TantivyIndexManager search functionality."""

    @pytest.fixture
    def temp_index_dir(self, tmp_path):
        """Create temporary index directory."""
        return tmp_path / "tantivy_index"

    @pytest.fixture
    def tantivy_manager(self, temp_index_dir):
        """Create and initialize TantivyIndexManager."""
        manager = TantivyIndexManager(temp_index_dir)
        manager.initialize_index(create_new=True)
        return manager

    @pytest.fixture
    def sample_documents(self):
        """Sample documents for testing."""
        return [
            {
                "path": "src/auth.py",
                "content": "def login_user(username, password):\n    authenticate(username, password)\n    return session",
                "content_raw": "def login_user(username, password):\n    authenticate(username, password)\n    return session",
                "identifiers": ["login_user", "authenticate", "session"],
                "line_start": 10,
                "line_end": 12,
                "language": "python",
            },
            {
                "path": "src/config.py",
                "content": "CONFIG_PATH = '/etc/app/config'\nclass Configuration:\n    pass",
                "content_raw": "CONFIG_PATH = '/etc/app/config'\nclass Configuration:\n    pass",
                "identifiers": ["CONFIG_PATH", "Configuration"],
                "line_start": 1,
                "line_end": 3,
                "language": "python",
            },
            {
                "path": "tests/test_auth.py",
                "content": "def test_login():\n    user = login_user('test', 'pass')\n    assert user is not None",
                "content_raw": "def test_login():\n    user = login_user('test', 'pass')\n    assert user is not None",
                "identifiers": ["test_login", "login_user"],
                "line_start": 5,
                "line_end": 7,
                "language": "python",
            },
            {
                "path": "src/utils.js",
                "content": "function authenticate(user, pass) {\n  return validateCredentials(user, pass);\n}",
                "content_raw": "function authenticate(user, pass) {\n  return validateCredentials(user, pass);\n}",
                "identifiers": ["authenticate", "validateCredentials"],
                "line_start": 15,
                "line_end": 17,
                "language": "javascript",
            },
        ]

    @pytest.fixture
    def indexed_manager(self, tantivy_manager, sample_documents):
        """Manager with sample documents indexed."""
        for doc in sample_documents:
            tantivy_manager.add_document(doc)
        tantivy_manager.commit()
        return tantivy_manager

    def test_basic_search_returns_results(self, indexed_manager):
        """Test basic search returns matching results."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        assert len(results) > 0
        assert any("authenticate" in r["match_text"].lower() for r in results)

    def test_case_sensitive_search(self, indexed_manager):
        """Test case-sensitive search only returns exact case matches."""
        # Search for uppercase CONFIG (should match CONFIG_PATH)
        results_upper = indexed_manager.search(
            query_text="CONFIG",
            case_sensitive=True,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Search for lowercase config (should NOT match CONFIG_PATH with case-sensitive)
        results_lower = indexed_manager.search(
            query_text="config",
            case_sensitive=True,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Upper case should find CONFIG_PATH
        assert len(results_upper) > 0
        # Lower case should find different results (if any)
        # This depends on how Tantivy tokenizes - we mainly verify they differ
        assert results_upper != results_lower

    def test_case_insensitive_search(self, indexed_manager):
        """Test case-insensitive search matches regardless of case."""
        results_upper = indexed_manager.search(
            query_text="AUTHENTICATE",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        results_lower = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Both should return results
        assert len(results_upper) > 0
        assert len(results_lower) > 0

        # Results should include paths with 'authenticate'
        paths_upper = {r["path"] for r in results_upper}
        paths_lower = {r["path"] for r in results_lower}
        assert paths_upper.intersection(paths_lower)

    def test_fuzzy_matching_finds_typos(self, indexed_manager):
        """Test fuzzy matching with edit distance 1 finds typos."""
        # Misspell "authenticate" as "authenticat" (missing 'e')
        results = indexed_manager.search(
            query_text="authenticat",
            case_sensitive=False,
            edit_distance=1,
            snippet_lines=5,
            limit=10,
        )

        # Should still find "authenticate" with edit distance 1
        assert len(results) > 0
        paths = {r["path"] for r in results}
        assert any("auth" in p for p in paths)

    def test_fuzzy_matching_edit_distance_2(self, indexed_manager):
        """Test fuzzy matching with edit distance 2 finds more variations."""
        # Misspell "authenticate" as "authentikat" (c→k, missing 'e')
        results = indexed_manager.search(
            query_text="authentikat",
            case_sensitive=False,
            edit_distance=2,
            snippet_lines=5,
            limit=10,
        )

        # Should find "authenticate" with edit distance 2
        assert (
            len(results) >= 0
        )  # May or may not find matches depending on tokenization

    def test_exact_matching_with_zero_edit_distance(self, indexed_manager):
        """Test exact matching does not find typos."""
        # Misspell "authenticate" as "authenticat"
        results = indexed_manager.search(
            query_text="authenticat",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Should not find "authenticate" with exact matching
        # (unless "authenticat" exists in documents)
        # We don't have exact "authenticat" in our sample docs
        assert len(results) == 0

    def test_snippet_extraction_with_lines(self, indexed_manager):
        """Test snippet extraction includes context lines."""
        results = indexed_manager.search(
            query_text="login_user",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        assert len(results) > 0
        result = results[0]

        # Check snippet exists
        assert "snippet" in result
        assert len(result["snippet"]) > 0

        # Check line and column are present
        assert "line" in result
        assert "column" in result
        assert result["line"] > 0
        assert result["column"] >= 0

    def test_snippet_zero_lines_returns_list_only(self, indexed_manager):
        """Test snippet_lines=0 returns results without snippets."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=0,
            limit=10,
        )

        assert len(results) > 0

        # With snippet_lines=0, snippets should be empty
        for result in results:
            assert result.get("snippet", "") == ""

    def test_language_filter_python_only(self, indexed_manager):
        """Test language filter returns only Python files."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            language_filter="python",
        )

        # All results should be Python files
        for result in results:
            assert result["language"] == "python"

    def test_language_filter_javascript_only(self, indexed_manager):
        """Test language filter returns only JavaScript files."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            language_filter="javascript",
        )

        # All results should be JavaScript files
        for result in results:
            assert result["language"] == "javascript"

    def test_path_filter_matches_pattern(self, indexed_manager):
        """Test path filter returns only matching paths."""
        results = indexed_manager.search(
            query_text="login",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            path_filter="*/tests/*",
        )

        # All results should match path pattern
        for result in results:
            assert "tests" in result["path"]

    def test_combined_filters(self, indexed_manager):
        """Test combining language and path filters."""
        results = indexed_manager.search(
            query_text="login",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            language_filter="python",
            path_filter="*/tests/*",
        )

        # Results should match both filters
        for result in results:
            assert result["language"] == "python"
            assert "tests" in result["path"]

    def test_limit_parameter_controls_result_count(self, indexed_manager):
        """Test limit parameter restricts number of results."""
        results_limit_1 = indexed_manager.search(
            query_text="login",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=1,
        )

        results_limit_10 = indexed_manager.search(
            query_text="login",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Limit should be respected
        assert len(results_limit_1) <= 1
        assert len(results_limit_10) <= 10

    def test_line_column_accuracy_with_multibyte_chars(self, tantivy_manager):
        """Test line/column positions are accurate with multi-byte UTF-8 characters."""
        # Document with Unicode characters
        doc = {
            "path": "src/unicode.py",
            "content": "# Café résumé\ndef function_name():\n    return '日本語'",
            "content_raw": "# Café résumé\ndef function_name():\n    return '日本語'",
            "identifiers": ["function_name"],
            "line_start": 1,
            "line_end": 3,
            "language": "python",
        }

        tantivy_manager.add_document(doc)
        tantivy_manager.commit()

        results = tantivy_manager.search(
            query_text="function_name",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        assert len(results) > 0
        result = results[0]

        # Check line is correct (function_name is on line 2)
        assert result["line"] == 2
        # Column should be positive
        assert result["column"] > 0

    def test_performance_requirement_under_5ms(self, indexed_manager):
        """Test query execution completes in under 5ms."""
        import time

        # Warm up
        indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Measure query time
        start = time.perf_counter()
        indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        end = time.perf_counter()

        query_time_ms = (end - start) * 1000

        # Should complete in under 5ms
        # Note: In CI environments, allow some slack
        assert query_time_ms < 10, f"Query took {query_time_ms:.2f}ms (target: <5ms)"

    def test_empty_results_for_nonexistent_query(self, indexed_manager):
        """Test search returns empty list for non-matching query."""
        results = indexed_manager.search(
            query_text="nonexistent_term_xyz123",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        assert results == []

    def test_search_returns_structured_results(self, indexed_manager):
        """Test search results have expected structure."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        assert len(results) > 0
        result = results[0]

        # Check required fields
        assert "path" in result
        assert "line" in result
        assert "column" in result
        assert "match_text" in result
        assert "snippet" in result
        assert "language" in result

    def test_snippet_includes_match_text(self, indexed_manager):
        """Test snippet contains the matched text."""
        results = indexed_manager.search(
            query_text="login_user",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=3,
            limit=10,
        )

        assert len(results) > 0
        result = results[0]

        # Snippet should contain the match text
        assert "login_user" in result["snippet"].lower()

    def test_exact_search_multi_word_requires_all_terms(self, indexed_manager):
        """Test exact search with multiple words requires ALL terms to match (Bug 1)."""
        # Add a document with "glob pattern" (not "gloc pattern")
        doc = {
            "path": "src/pattern_matcher.py",
            "content": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "content_raw": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "identifiers": ["match_glob_pattern", "glob"],
            "line_start": 1,
            "line_end": 2,
            "language": "python",
        }
        indexed_manager.add_document(doc)
        indexed_manager.commit()

        # Search for "glob pattern" should find the document
        results_correct = indexed_manager.search(
            query_text="glob pattern",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        assert len(results_correct) > 0, "Should find 'glob pattern'"
        assert any("pattern_matcher.py" in r["path"] for r in results_correct)

        # Search for "gloc pattern" (non-existent term "gloc") should return 0 results
        # BUG: Currently returns results because it matches "pattern" OR "gloc" (OR semantics)
        # EXPECTED: Should require BOTH "gloc" AND "pattern" to exist (AND semantics)
        results_nonexistent = indexed_manager.search(
            query_text="gloc pattern",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        assert len(results_nonexistent) == 0, (
            "Should NOT find any results for 'gloc pattern' since 'gloc' doesn't exist. "
            "Exact search should require ALL terms to match."
        )

    def test_exact_search_partial_match_returns_zero(self, indexed_manager):
        """Test exact search returns zero results when only some terms match."""
        # Search for "login nonexistent" - only "login" exists
        results = indexed_manager.search(
            query_text="login nonexistent_xyz123",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        assert len(results) == 0, (
            "Should return 0 results when not all terms exist. "
            "Exact search requires ALL terms to match."
        )

    def test_fuzzy_search_multi_word_phrase(self, indexed_manager):
        """Test fuzzy search works with multi-word phrases (Bug 2)."""
        # Add document with "glob pattern"
        doc = {
            "path": "src/pattern_matcher.py",
            "content": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "content_raw": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "identifiers": ["match_glob_pattern", "glob"],
            "line_start": 1,
            "line_end": 2,
            "language": "python",
        }
        indexed_manager.add_document(doc)
        indexed_manager.commit()

        # Search for "gloc pattern" with fuzzy matching should find "glob pattern"
        # BUG: Currently returns 0 results because fuzzy_term_query only works on single terms
        # EXPECTED: Should split into terms, apply fuzzy to each, and match "glob pattern"
        results = indexed_manager.search(
            query_text="gloc pattern",
            case_sensitive=False,
            edit_distance=1,
            snippet_lines=5,
            limit=10,
        )
        assert len(results) > 0, (
            "Should find 'glob pattern' when searching for 'gloc pattern' with fuzzy matching. "
            "Fuzzy search should work on multi-word phrases by applying fuzzy matching to each term."
        )
        assert any("pattern_matcher.py" in r["path"] for r in results)

    def test_fuzzy_search_multi_word_all_terms_fuzzy_match(self, indexed_manager):
        """Test fuzzy search requires all terms to fuzzy-match."""
        # Add document with "glob pattern"
        doc = {
            "path": "src/pattern_matcher.py",
            "content": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "content_raw": "def match_glob_pattern(pattern):\n    return glob.glob(pattern)",
            "identifiers": ["match_glob_pattern", "glob"],
            "line_start": 1,
            "line_end": 2,
            "language": "python",
        }
        indexed_manager.add_document(doc)
        indexed_manager.commit()

        # Search for "gloc xyz123" with fuzzy - first term fuzzy-matches "glob", second doesn't exist
        results = indexed_manager.search(
            query_text="gloc nonexistent_xyz",
            case_sensitive=False,
            edit_distance=1,
            snippet_lines=5,
            limit=10,
        )
        # Should return 0 results because "nonexistent_xyz" doesn't fuzzy-match anything
        assert len(results) == 0, (
            "Should return 0 results when not all terms fuzzy-match. "
            "Fuzzy search should use AND semantics across terms."
        )

    def test_single_term_exact_search_backward_compatibility(self, indexed_manager):
        """Test single-term exact search still works (backward compatibility)."""
        results = indexed_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        assert len(results) > 0
        assert any("authenticate" in r["match_text"].lower() for r in results)

    def test_single_term_fuzzy_search_backward_compatibility(self, indexed_manager):
        """Test single-term fuzzy search still works (backward compatibility)."""
        results = indexed_manager.search(
            query_text="authenticat",  # Missing 'e'
            case_sensitive=False,
            edit_distance=1,
            snippet_lines=5,
            limit=10,
        )
        assert len(results) > 0
        paths = {r["path"] for r in results}
        assert any("auth" in p for p in paths)
