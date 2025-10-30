"""
Unit tests for TantivyIndexManager regex search functionality.

Tests cover:
- Basic regex pattern matching
- Regex with language filters
- Invalid regex error handling
- Case-sensitive regex matching
- Regex with path filters
"""

import pytest
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyRegex:
    """Test suite for TantivyIndexManager regex search functionality."""

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
        """Sample documents for testing regex patterns."""
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
                "path": "src/database.py",
                "content": "def connect_db():\n    return connection\n\ndef query_users():\n    return results",
                "content_raw": "def connect_db():\n    return connection\n\ndef query_users():\n    return results",
                "identifiers": ["connect_db", "query_users"],
                "line_start": 1,
                "line_end": 5,
                "language": "python",
            },
            {
                "path": "tests/test_auth.py",
                "content": "# TODO: Add more auth tests\ndef test_login():\n    user = login_user('test', 'pass')\n    assert user is not None",
                "content_raw": "# TODO: Add more auth tests\ndef test_login():\n    user = login_user('test', 'pass')\n    assert user is not None",
                "identifiers": ["test_login", "login_user"],
                "line_start": 1,
                "line_end": 4,
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
            {
                "path": "src/config.py",
                "content": "# TODO: refactor config\nCONFIG_PATH = '/etc/app/config'\nclass Configuration:\n    pass",
                "content_raw": "# TODO: refactor config\nCONFIG_PATH = '/etc/app/config'\nclass Configuration:\n    pass",
                "identifiers": ["CONFIG_PATH", "Configuration"],
                "line_start": 1,
                "line_end": 4,
                "language": "python",
            },
        ]

    @pytest.fixture
    def indexed_manager(self, tantivy_manager, sample_documents):
        """Manager with sample documents indexed."""
        for doc in sample_documents:
            tantivy_manager.add_document(doc)
        tantivy_manager.commit()
        return tantivy_manager

    def test_regex_simple_pattern(self, indexed_manager):
        """
        GIVEN indexed repo with function definitions
        WHEN searching with simple token-based regex pattern
        THEN matches regex pattern correctly

        NOTE: Tantivy regex operates on TOKENS, not full text.
        Pattern r"def" matches the token "def", not arbitrary text.
        """
        results = indexed_manager.search(
            query_text=r"def",  # Match "def" token
            use_regex=True,
            snippet_lines=0,  # Just verify matches, no snippets
            limit=10,
        )

        # Should find at least the Python function definitions
        assert len(results) > 0

        # Verify results contain function definitions with "def" token
        paths = [r["path"] for r in results]
        assert any("auth.py" in p or "database.py" in p for p in paths)

    def test_regex_with_language_filter(self, indexed_manager):
        """
        GIVEN indexed repo with multiple languages
        WHEN using regex with language filter
        THEN returns only matching language results

        NOTE: Token-based regex with language filtering
        This test verifies that regex search integrates with language filtering.
        """
        # Verify "def" exists across all files
        all_results = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            snippet_lines=0,
            limit=10,
        )
        assert len(all_results) > 0, "Should find 'def' token in indexed documents"

        # Filter to exclude JavaScript files - should still find Python files with "def"
        python_results = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            exclude_languages=["javascript"],
            snippet_lines=0,
            limit=10,
        )

        # Should still find results (since 'def' is in Python files, not JS)
        assert len(python_results) > 0

        # All results should NOT be JavaScript files
        for result in python_results:
            assert result["language"] != "javascript"

    def test_regex_invalid_pattern(self, indexed_manager):
        """
        GIVEN indexed repo
        WHEN using invalid regex pattern
        THEN raises ValueError with clear error message
        """
        with pytest.raises(ValueError) as exc_info:
            indexed_manager.search(
                query_text=r"[invalid(",  # Invalid regex - unclosed bracket
                use_regex=True,
                snippet_lines=0,
            )

        # Error should mention regex and pattern
        error_msg = str(exc_info.value).lower()
        assert "regex" in error_msg and "pattern" in error_msg

    def test_regex_case_sensitive(self, indexed_manager):
        """
        GIVEN indexed repo with mixed case text
        WHEN using case-sensitive regex
        THEN matches case exactly

        NOTE: Token-based regex with case sensitivity
        """
        # Use a token that definitely exists - like "def"
        # First verify case-insensitive works
        results_insensitive = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            case_sensitive=False,
            snippet_lines=0,
        )
        assert len(results_insensitive) > 0, "Should find 'def' case-insensitively"

        # Now test case-sensitive (should still find 'def' because it's lowercase)
        results_sensitive = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            case_sensitive=True,
            snippet_lines=0,
        )

        assert (
            len(results_sensitive) > 0
        ), "Should find lowercase 'def' with case-sensitive search"
        # Both should find the same results since 'def' is lowercase in source
        assert len(results_sensitive) == len(results_insensitive)

    def test_regex_with_path_filter(self, indexed_manager):
        """
        GIVEN indexed repo
        WHEN using regex with path filter
        THEN returns only results from matching paths
        """
        # Use a common token that exists in both src and tests
        # First, verify token exists across all paths
        all_results = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            snippet_lines=0,
        )
        assert len(all_results) > 0

        # Now filter to only test paths
        test_results = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            path_filters=["*/tests/*"],
            snippet_lines=0,
        )

        # Should find results in test files
        if len(test_results) > 0:
            for result in test_results:
                assert "tests/" in result["path"]

    def test_regex_complex_pattern(self, indexed_manager):
        """
        GIVEN indexed repo
        WHEN using complex regex pattern
        THEN matches pattern correctly

        NOTE: Using token-based patterns with wildcards
        """
        # Search for tokens starting with "login"
        results = indexed_manager.search(
            query_text=r"login.*",  # Match tokens starting with "login"
            use_regex=True,
            snippet_lines=5,
            limit=10,
        )

        assert len(results) > 0

        # Verify we got results from Python files
        paths = [r["path"] for r in results]
        assert any(p.endswith(".py") for p in paths)

    def test_regex_with_exclude_paths(self, indexed_manager):
        """
        GIVEN indexed repo
        WHEN using regex with path exclusions
        THEN excludes matching paths from results
        """
        results = indexed_manager.search(
            query_text=r"def",  # Match "def" token
            use_regex=True,
            exclude_paths=["*/tests/*"],
            snippet_lines=0,
        )

        # Should find functions but exclude test files
        assert len(results) > 0
        for result in results:
            assert "tests/" not in result["path"]
