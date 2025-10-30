"""
Unit tests for Tantivy language filtering functionality.

Tests multi-language filtering for FTS queries with --language flag.
"""

import pytest
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


@pytest.fixture
def temp_index_dir(tmp_path):
    """Create a temporary directory for the Tantivy index."""
    index_dir = tmp_path / "fts_test_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir


@pytest.fixture
def tantivy_manager(temp_index_dir):
    """Create and initialize a TantivyIndexManager instance."""
    manager = TantivyIndexManager(temp_index_dir)
    manager.initialize_index(create_new=True)
    return manager


@pytest.fixture
def indexed_files(tantivy_manager):
    """Add sample files to the index for testing."""
    # Python file
    tantivy_manager.add_document(
        {
            "path": "src/main.py",
            "content": "def test_function(): pass",
            "content_raw": "def test_function(): pass",
            "identifiers": ["test_function"],
            "line_start": 1,
            "line_end": 1,
            "language": "py",
        }
    )

    # Another Python file
    tantivy_manager.add_document(
        {
            "path": "src/utils.py",
            "content": "class TestClass: pass",
            "content_raw": "class TestClass: pass",
            "identifiers": ["TestClass"],
            "line_start": 1,
            "line_end": 1,
            "language": "py",
        }
    )

    # JavaScript file
    tantivy_manager.add_document(
        {
            "path": "src/app.js",
            "content": "function test() { return 42; }",
            "content_raw": "function test() { return 42; }",
            "identifiers": ["test"],
            "line_start": 1,
            "line_end": 1,
            "language": "js",
        }
    )

    # TypeScript file
    tantivy_manager.add_document(
        {
            "path": "src/component.tsx",
            "content": "const TestComponent = () => <div>Test</div>;",
            "content_raw": "const TestComponent = () => <div>Test</div>;",
            "identifiers": ["TestComponent"],
            "line_start": 1,
            "line_end": 1,
            "language": "tsx",
        }
    )

    # Java file
    tantivy_manager.add_document(
        {
            "path": "src/Main.java",
            "content": "public class Main { public static void test() {} }",
            "content_raw": "public class Main { public static void test() {} }",
            "identifiers": ["Main", "test"],
            "line_start": 1,
            "line_end": 1,
            "language": "java",
        }
    )

    tantivy_manager.commit()
    return tantivy_manager


class TestSingleLanguageFilter:
    """Test single language filtering."""

    def test_filter_by_python(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=["py"]
        THEN only Python files are returned
        """
        results = indexed_files.search(query_text="test", languages=["py"], limit=10)

        assert len(results) > 0, "Should return some results"
        for result in results:
            assert (
                result["language"] == "py"
            ), f"Expected Python file, got {result['language']}"

    def test_filter_by_javascript(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=["js"]
        THEN only JavaScript files are returned
        """
        results = indexed_files.search(query_text="test", languages=["js"], limit=10)

        assert len(results) > 0, "Should return some results"
        for result in results:
            assert (
                result["language"] == "js"
            ), f"Expected JavaScript file, got {result['language']}"


class TestMultiLanguageFilter:
    """Test multiple language filtering with OR semantics."""

    def test_filter_by_python_or_javascript(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=["py", "js"]
        THEN Python OR JavaScript files are returned
        """
        results = indexed_files.search(
            query_text="test", languages=["py", "js"], limit=10
        )

        assert len(results) > 0, "Should return some results"

        # Collect languages from results
        languages_found = {r["language"] for r in results}

        # Should contain Python or JavaScript files
        assert languages_found.issubset(
            {"py", "js"}
        ), f"Expected only Python/JavaScript, got {languages_found}"

        # Should actually contain both (based on our test data)
        assert "py" in languages_found, "Should contain Python results"
        assert "js" in languages_found, "Should contain JavaScript results"

    def test_filter_by_three_languages(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=["py", "js", "java"]
        THEN Python OR JavaScript OR Java files are returned
        """
        results = indexed_files.search(
            query_text="test", languages=["py", "js", "java"], limit=10
        )

        assert len(results) > 0, "Should return some results"

        languages_found = {r["language"] for r in results}
        assert languages_found.issubset(
            {"py", "js", "java"}
        ), f"Expected only py/js/java, got {languages_found}"


class TestLanguageFilterWithFuzzy:
    """Test language filtering combined with fuzzy search."""

    def test_fuzzy_search_with_python_filter(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with fuzzy matching and languages=["py"]
        THEN only Python files matching fuzzily are returned
        """
        results = indexed_files.search(
            query_text="tst",  # Fuzzy match for "test"
            edit_distance=1,
            languages=["py"],
            limit=10,
        )

        # May or may not find results depending on fuzzy matching
        for result in results:
            assert (
                result["language"] == "py"
            ), f"Expected Python file, got {result['language']}"


class TestLanguageFilterWithCaseSensitive:
    """Test language filtering combined with case-sensitive search."""

    def test_case_sensitive_with_language_filter(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching case-sensitively with languages=["tsx"]
        THEN only TypeScript files with exact case matches are returned
        """
        results = indexed_files.search(
            query_text="Test",  # Case-sensitive search
            case_sensitive=True,
            languages=["tsx"],
            limit=10,
        )

        # Should find the TypeScript file with "Test" in it
        for result in results:
            assert (
                result["language"] == "tsx"
            ), f"Expected TypeScript file, got {result['language']}"
            assert "Test" in result["match_text"] or "Test" in result["snippet"]


class TestEmptyAndEdgeCases:
    """Test edge cases and empty results."""

    def test_unknown_language_returns_empty(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=["unknown"]
        THEN no results are returned (no files match)
        """
        results = indexed_files.search(
            query_text="test", languages=["unknown"], limit=10
        )

        assert len(results) == 0, "Should return no results for unknown language"

    def test_no_language_filter_returns_all(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=None (backward compatibility)
        THEN all matching files are returned regardless of language
        """
        results = indexed_files.search(query_text="test", languages=None, limit=10)

        assert len(results) > 0, "Should return some results"

        # Should contain multiple languages
        languages_found = {r["language"] for r in results}
        assert (
            len(languages_found) > 1
        ), "Should contain multiple languages when no filter applied"

    def test_empty_language_list_returns_all(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with languages=[]
        THEN all matching files are returned (backward compatibility)
        """
        results = indexed_files.search(query_text="test", languages=[], limit=10)

        assert len(results) > 0, "Should return some results"


class TestBackwardCompatibility:
    """Test backward compatibility with old language_filter parameter."""

    def test_language_filter_parameter_still_works(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with old language_filter="py" parameter
        THEN only Python files are returned (backward compatibility)
        """
        results = indexed_files.search(
            query_text="test", language_filter="py", limit=10
        )

        assert len(results) > 0, "Should return some results"
        for result in results:
            assert (
                result["language"] == "py"
            ), f"Expected Python file, got {result['language']}"

    def test_languages_parameter_overrides_language_filter(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN both languages and language_filter are provided
        THEN languages parameter takes precedence
        """
        results = indexed_files.search(
            query_text="test",
            languages=["js"],
            language_filter="py",  # Should be ignored
            limit=10,
        )

        assert len(results) > 0, "Should return some results"
        for result in results:
            assert (
                result["language"] == "js"
            ), "languages parameter should override language_filter"


class TestPerformance:
    """Test that language filtering maintains performance requirements."""

    def test_language_filter_performance(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with language filter
        THEN query completes in <1s (performance requirement)
        """
        import time

        start_time = time.time()
        results = indexed_files.search(
            query_text="test", languages=["py", "js"], limit=10
        )
        elapsed = time.time() - start_time

        assert elapsed < 1.0, f"Search took {elapsed:.2f}s, should be <1s"
        assert len(results) > 0, "Should return results"


class TestExcludeLanguageSingle:
    """Test single language exclusion."""

    def test_exclude_javascript(self, indexed_files):
        """
        GIVEN an index with Python, JavaScript, TypeScript, and Java files
        WHEN searching with exclude_languages=["javascript"]
        THEN no JavaScript files are returned
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=["javascript"], limit=10
        )

        assert len(results) > 0, "Should return non-JavaScript results"
        for result in results:
            assert result["language"] not in [
                "js",
                "jsx",
            ], f"JavaScript should be excluded, got {result['language']}"

    def test_exclude_python(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN searching with exclude_languages=["python"]
        THEN no Python files are returned
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=["python"], limit=10
        )

        assert len(results) > 0, "Should return non-Python results"
        for result in results:
            assert result["language"] not in [
                "py",
                "pyw",
                "pyi",
            ], f"Python should be excluded, got {result['language']}"


class TestExcludeLanguageMultiple:
    """Test multiple language exclusions with OR logic."""

    def test_exclude_javascript_and_typescript(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN excluding multiple languages
        THEN none of the excluded languages appear
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=["javascript", "typescript"], limit=10
        )

        assert len(results) > 0, "Should return results after exclusions"
        for result in results:
            assert result["language"] not in [
                "js",
                "jsx",
                "ts",
                "tsx",
            ], f"JavaScript and TypeScript should be excluded, got {result['language']}"

    def test_exclude_three_languages(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN excluding three languages
        THEN only non-excluded languages are returned
        """
        results = indexed_files.search(
            query_text="test",
            exclude_languages=["python", "javascript", "typescript"],
            limit=10,
        )

        # Should only have Java results
        for result in results:
            assert result["language"] not in [
                "py",
                "pyw",
                "pyi",
                "js",
                "jsx",
                "ts",
                "tsx",
            ], f"Excluded languages should not appear, got {result['language']}"


class TestExclusionPrecedenceOverInclusion:
    """Test that language exclusions take precedence over inclusions."""

    def test_include_and_exclude_same_language(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN including Python and excluding Python
        THEN exclusion takes precedence (returns empty)
        """
        results = indexed_files.search(
            query_text="test",
            languages=["python"],
            exclude_languages=["python"],
            limit=10,
        )

        # Exclusion wins - should return empty
        assert (
            len(results) == 0
        ), "Exclusion should take precedence over inclusion (empty results expected)"

    def test_include_multiple_exclude_one(self, indexed_files):
        """
        GIVEN an index with Python, JavaScript, TypeScript
        WHEN including Python and JavaScript but excluding JavaScript
        THEN only Python files returned (exclusion takes precedence)
        """
        results = indexed_files.search(
            query_text="test",
            languages=["python", "javascript"],
            exclude_languages=["javascript"],
            limit=10,
        )

        assert len(results) > 0, "Should have Python results"
        for result in results:
            # Should only have Python
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
            ], f"Expected Python only, got {result['language']}"
            # Should NOT have JavaScript
            assert result["language"] not in [
                "js",
                "jsx",
            ], f"JavaScript should be excluded, got {result['language']}"

    def test_include_multiple_exclude_multiple_with_overlap(self, indexed_files):
        """
        GIVEN an index with multiple languages
        WHEN including [python, javascript, java] and excluding [javascript, typescript]
        THEN only Python and Java are returned (exclusions win on overlap)
        """
        results = indexed_files.search(
            query_text="test",
            languages=["python", "javascript", "java"],
            exclude_languages=["javascript", "typescript"],
            limit=10,
        )

        assert len(results) > 0, "Should have Python/Java results"
        for result in results:
            # Should have Python or Java
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
                "java",
            ], f"Expected Python or Java, got {result['language']}"
            # Should NOT have JavaScript or TypeScript
            assert result["language"] not in [
                "js",
                "jsx",
                "ts",
                "tsx",
            ], f"Excluded languages should not appear, got {result['language']}"


class TestExcludeLanguageWithPathFilters:
    """Test language exclusions combined with path filters."""

    def test_exclude_language_with_path_filter(self, indexed_files):
        """
        GIVEN an index with files in multiple directories
        WHEN combining language exclusion and path filters
        THEN results match path filters AND do not match excluded languages
        """
        # Add files in different paths
        indexed_files.add_document(
            {
                "path": "tests/test_main.py",
                "content": "def test_function(): pass",
                "content_raw": "def test_function(): pass",
                "identifiers": ["test_function"],
                "line_start": 1,
                "line_end": 1,
                "language": "py",
            }
        )
        indexed_files.add_document(
            {
                "path": "tests/test_app.js",
                "content": "function test() { return 42; }",
                "content_raw": "function test() { return 42; }",
                "identifiers": ["test"],
                "line_start": 1,
                "line_end": 1,
                "language": "js",
            }
        )
        indexed_files.commit()

        results = indexed_files.search(
            query_text="test",
            path_filters=["*/tests/*"],
            exclude_languages=["javascript"],
            limit=10,
        )

        assert len(results) > 0, "Should have results in tests directory"
        for result in results:
            assert (
                "tests/" in result["path"]
            ), f"Expected tests directory, got {result['path']}"
            assert result["language"] not in [
                "js",
                "jsx",
            ], f"JavaScript should be excluded, got {result['language']}"

    def test_exclude_language_with_exclude_path(self, indexed_files):
        """
        GIVEN an index with files in multiple directories
        WHEN combining language exclusion and path exclusion
        THEN both exclusions are applied (AND logic)
        """
        # Add more files
        indexed_files.add_document(
            {
                "path": "vendor/lib.js",
                "content": "function test() { return 1; }",
                "content_raw": "function test() { return 1; }",
                "identifiers": ["test"],
                "line_start": 1,
                "line_end": 1,
                "language": "js",
            }
        )
        indexed_files.commit()

        results = indexed_files.search(
            query_text="test",
            exclude_paths=["*/vendor/*"],
            exclude_languages=["javascript"],
            limit=10,
        )

        for result in results:
            # Should not be in vendor
            assert (
                "vendor/" not in result["path"]
            ), f"vendor directory should be excluded, got {result['path']}"
            # Should not be JavaScript
            assert result["language"] not in [
                "js",
                "jsx",
            ], f"JavaScript should be excluded, got {result['language']}"


class TestAllFiltersCombined:
    """Test all filter types working together."""

    def test_all_filters_combined(self, indexed_files):
        """
        GIVEN an index with files in multiple languages and paths
        WHEN using all filter types together
        THEN results match all filter criteria
        """
        # Add comprehensive test data
        indexed_files.add_document(
            {
                "path": "tests/slow/test_perf.py",
                "content": "def test_performance(): pass",
                "content_raw": "def test_performance(): pass",
                "identifiers": ["test_performance"],
                "line_start": 1,
                "line_end": 1,
                "language": "py",
            }
        )
        indexed_files.add_document(
            {
                "path": "tests/unit/test_utils.py",
                "content": "def test_utils(): pass",
                "content_raw": "def test_utils(): pass",
                "identifiers": ["test_utils"],
                "line_start": 1,
                "line_end": 1,
                "language": "py",
            }
        )
        indexed_files.add_document(
            {
                "path": "tests/Main.java",
                "content": "public void test() {}",
                "content_raw": "public void test() {}",
                "identifiers": ["test"],
                "line_start": 1,
                "line_end": 1,
                "language": "java",
            }
        )
        indexed_files.commit()

        results = indexed_files.search(
            query_text="test",
            languages=["python", "java"],  # Include Python and Java
            path_filters=["*/tests/*"],  # Include tests directory
            exclude_paths=["*/tests/slow/*"],  # Exclude slow tests
            exclude_languages=["java"],  # But exclude Java (so only Python)
            limit=10,
        )

        assert len(results) > 0, "Should have matching results"
        for result in results:
            # Must be Python (Java excluded despite being in languages)
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
            ], f"Expected Python only (Java excluded), got {result['language']}"
            # Must be in tests
            assert (
                "tests/" in result["path"]
            ), f"Expected tests directory, got {result['path']}"
            # Must NOT be in slow tests
            assert (
                "slow/" not in result["path"]
            ), f"slow tests should be excluded, got {result['path']}"


class TestExcludeLanguageWithFuzzyAndCaseSensitive:
    """Test language exclusions with fuzzy and case-sensitive search."""

    def test_exclude_with_fuzzy_search(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN using fuzzy search with language exclusion
        THEN fuzzy matching works and exclusions are applied
        """
        results = indexed_files.search(
            query_text="tst",  # Fuzzy match for "test"
            edit_distance=1,
            exclude_languages=["javascript"],
            limit=10,
        )

        # All results should not be JavaScript
        for result in results:
            assert result["language"] not in [
                "js",
                "jsx",
            ], f"JavaScript should be excluded, got {result['language']}"

    def test_exclude_with_case_sensitive(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN using case-sensitive search with language exclusion
        THEN case sensitivity is preserved and exclusions are applied
        """
        results = indexed_files.search(
            query_text="Test",
            case_sensitive=True,
            exclude_languages=["python"],
            limit=10,
        )

        # All results should not be Python
        for result in results:
            assert result["language"] not in [
                "py",
                "pyw",
                "pyi",
            ], f"Python should be excluded, got {result['language']}"


class TestExcludeLanguagePerformance:
    """Test that language exclusions maintain performance requirements."""

    def test_exclude_multiple_languages_performance(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN excluding multiple languages
        THEN query completes in <1s (performance requirement)
        """
        import time

        start_time = time.time()
        results = indexed_files.search(
            query_text="test",
            exclude_languages=["javascript", "typescript", "java"],
            limit=10,
        )
        elapsed = time.time() - start_time

        assert (
            elapsed < 1.0
        ), f"Search with exclusions took {elapsed:.2f}s, should be <1s"
        assert len(results) >= 0, "Should complete successfully"


class TestExcludeLanguageEdgeCases:
    """Test edge cases for language exclusions."""

    def test_exclude_all_languages(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN excluding all languages present
        THEN no results are returned
        """
        results = indexed_files.search(
            query_text="test",
            exclude_languages=["python", "javascript", "typescript", "java"],
            limit=10,
        )

        assert len(results) == 0, "All languages excluded, should return empty"

    def test_exclude_unknown_language(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN excluding a language not in the index
        THEN all results are returned (exclusion has no effect)
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=["rust"], limit=10
        )

        assert len(results) > 0, "Excluding unknown language should not affect results"

    def test_exclude_empty_list(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN exclude_languages=[]
        THEN all matching files are returned
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=[], limit=10
        )

        assert len(results) > 0, "Empty exclusion list should return results"

    def test_exclude_none(self, indexed_files):
        """
        GIVEN an index with multiple language files
        WHEN exclude_languages=None
        THEN all matching files are returned
        """
        results = indexed_files.search(
            query_text="test", exclude_languages=None, limit=10
        )

        assert len(results) > 0, "None exclusion should return results"
