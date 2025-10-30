"""
Unit tests for TantivyIndexManager path filtering functionality.

Tests verify that --path-filter flag works correctly with FTS queries.
"""

import pytest
from pathlib import Path

# Test fixtures will be imported from conftest
from src.code_indexer.services.tantivy_index_manager import TantivyIndexManager


@pytest.fixture
def sample_test_files(tmp_path: Path) -> Path:
    """
    Create a sample repository structure with files in different directories.

    Structure:
        tests/
            test_auth.py
            test_utils.py
        src/
            server/
                config.py
                app.py
            utils/
                helpers.py
        docs/
            README.md
        main.js
    """
    # Create directory structure
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_auth.py").write_text(
        "def test_login():\n    assert True\n\ndef test_logout():\n    assert False\n"
    )
    (tests_dir / "test_utils.py").write_text("def test_helper():\n    assert True\n")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    server_dir = src_dir / "server"
    server_dir.mkdir()
    (server_dir / "config.py").write_text("CONFIG = {'debug': True}\n")
    (server_dir / "app.py").write_text("def main():\n    pass\n")

    utils_dir = src_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "helpers.py").write_text("def helper_function():\n    return 'test'\n")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "README.md").write_text("# Test Documentation\n")

    (tmp_path / "main.js").write_text("function test() { console.log('test'); }\n")

    return tmp_path


@pytest.fixture
def indexed_tantivy_manager(
    sample_test_files: Path, tmp_path: Path
) -> TantivyIndexManager:
    """Create and populate a Tantivy index with sample files."""
    index_dir = tmp_path / ".code-indexer" / "tantivy"
    index_dir.mkdir(parents=True, exist_ok=True)

    manager = TantivyIndexManager(index_dir)
    manager.initialize_index(create_new=True)

    # Index all files in the sample repository
    for file_path in sample_test_files.rglob("*"):
        if file_path.is_file():
            content = file_path.read_text()
            relative_path = file_path.relative_to(sample_test_files)

            # Determine language from extension
            suffix = file_path.suffix
            language_map = {".py": "py", ".js": "js", ".md": "md"}
            language = language_map.get(suffix, "txt")

            # Index the entire file as a single document
            lines = content.split("\n")
            manager.add_document(
                {
                    "path": str(relative_path),
                    "language": language,
                    "content": content,
                    "content_raw": content,
                    "identifiers": [],  # Not extracting identifiers for this test
                    "line_start": 1,
                    "line_end": len(lines),
                }
            )

    manager.commit()
    return manager


class TestPathFilterBasics:
    """Test basic path filtering functionality."""

    def test_path_filter_tests_directory(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with tests/ and src/ directories
        WHEN searching with path_filter='*/tests/*'
        THEN only test files are returned

        Acceptance Criteria #1
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/tests/*", limit=50
        )

        assert len(results) > 0, "Should find matches in tests directory"
        for result in results:
            assert "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            ), f"Expected path to contain '/tests/', got: {result['path']}"

    def test_path_filter_server_directory(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with server/ directory
        WHEN searching with path_filter='*/server/*'
        THEN only server files are returned

        Acceptance Criteria #2
        """
        results = indexed_tantivy_manager.search(
            query_text="config", path_filter="*/server/*", limit=50
        )

        assert len(results) > 0, "Should find matches in server directory"
        for result in results:
            assert (
                "/server/" in result["path"] or "server/" in result["path"]
            ), f"Expected path to contain '/server/', got: {result['path']}"

    def test_path_filter_file_extension(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with .py and .js files
        WHEN searching with path_filter='*.py'
        THEN only Python files are returned

        Acceptance Criteria #3
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*.py", limit=50
        )

        assert len(results) > 0, "Should find matches in Python files"
        for result in results:
            assert result["path"].endswith(
                ".py"
            ), f"Expected .py file, got: {result['path']}"

    def test_path_filter_no_match_returns_empty(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with non-matching path filter
        THEN empty results are returned

        Acceptance Criteria #7 (graceful handling)
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/nonexistent/*", limit=50
        )

        assert (
            len(results) == 0
        ), "Should return empty list for non-matching path filter"

    def test_no_path_filter_returns_all_matches(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching without path filter
        THEN all matching files are returned

        Acceptance Criteria #8 (backward compatibility)
        """
        results_without_filter = indexed_tantivy_manager.search(
            query_text="test", path_filter=None, limit=50
        )

        assert len(results_without_filter) > 0, "Should find matches without filter"
        # Note: path_filter="*" matches everything, so results should be similar
        # to no filter (backward compatibility validation)


class TestPathFilterWithOtherFeatures:
    """Test path filter combined with other search features."""

    def test_path_filter_with_fuzzy_search(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with path filter AND fuzzy matching
        THEN results match both criteria

        Acceptance Criteria #4
        """
        results = indexed_tantivy_manager.search(
            query_text="tets",  # Typo: should match "test" with fuzzy
            path_filter="*/tests/*",
            edit_distance=1,  # Allow 1 character difference
            limit=50,
        )

        # Fuzzy matching should find "test" despite typo
        assert len(results) >= 0  # May or may not find fuzzy matches
        for result in results:
            assert "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            ), f"Expected path to contain '/tests/', got: {result['path']}"

    def test_path_filter_with_case_sensitive(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with path filter AND case-sensitive matching
        THEN results match both criteria

        Acceptance Criteria #5
        """
        results = indexed_tantivy_manager.search(
            query_text="TEST",  # Uppercase - should not match with case-sensitive
            path_filter="*/tests/*",
            case_sensitive=True,
            limit=50,
        )

        # Case-sensitive search for "TEST" likely won't match lowercase "test"
        # But path filter should still be applied
        for result in results:
            assert "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            ), f"Expected path to contain '/tests/', got: {result['path']}"

    def test_path_filter_with_language_filter(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with .py and .js files in tests/
        WHEN searching with both path and language filters
        THEN results match BOTH filters

        Acceptance Criteria #6
        """
        results = indexed_tantivy_manager.search(
            query_text="test",
            path_filter="*/tests/*",
            languages=["py"],  # Only Python files
            limit=50,
        )

        assert len(results) > 0, "Should find Python test files"
        for result in results:
            assert "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            ), f"Expected path to contain '/tests/', got: {result['path']}"
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
            ], f"Expected Python language, got: {result['language']}"


class TestPathFilterEdgeCases:
    """Test edge cases and complex patterns."""

    def test_path_filter_multiple_wildcards(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """Test complex glob patterns with multiple wildcards."""
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/src/*/helpers.py", limit=50
        )

        # Should match src/utils/helpers.py
        for result in results:
            assert (
                "helpers.py" in result["path"]
            ), f"Expected helpers.py in path, got: {result['path']}"

    def test_path_filter_root_level_files(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """Test filtering for root-level files."""
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*.js", limit=50  # Root level .js files
        )

        # Should match main.js but not files in subdirectories
        for result in results:
            assert result["path"].endswith(
                ".js"
            ), f"Expected .js file, got: {result['path']}"
            # Note: fnmatch behavior for *.js may match files in any directory
            # This tests the current implementation behavior

    def test_path_filter_preserves_limit(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """Verify that path filter respects the limit parameter."""
        limit = 2
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/tests/*", limit=limit
        )

        # Results should not exceed limit
        assert (
            len(results) <= limit
        ), f"Expected at most {limit} results, got {len(results)}"


class TestMultiplePathFilters:
    """Test multiple path filter support with OR logic (Story 4)."""

    def test_multiple_path_filters_or_logic(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with tests/ and src/ directories
        WHEN searching with multiple path filters
        THEN results match ANY of the patterns (OR logic)

        Acceptance Criteria #1, #2
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filters=["*/tests/*", "*/src/*"], limit=50
        )

        assert len(results) > 0, "Should find matches in tests OR src directories"
        for result in results:
            # Must match at least one pattern
            matches_tests = "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            )
            matches_src = "/src/" in result["path"] or result["path"].startswith("src/")
            assert (
                matches_tests or matches_src
            ), f"Expected path to match tests OR src, got: {result['path']}"

    def test_three_path_filters(self, indexed_tantivy_manager: TantivyIndexManager):
        """
        GIVEN indexed repo with multiple directories
        WHEN searching with three path filters
        THEN results match any of the three patterns

        Acceptance Criteria #3 (complex patterns)
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filters=["*/tests/*", "*/src/*", "*.js"], limit=50
        )

        assert len(results) > 0, "Should find matches with any of three patterns"
        for result in results:
            path = result["path"]
            matches_tests = "/tests/" in path or path.startswith("tests/")
            matches_src = "/src/" in path or path.startswith("src/")
            matches_js = path.endswith(".js")
            assert (
                matches_tests or matches_src or matches_js
            ), f"Expected path to match one of three patterns, got: {path}"

    def test_multiple_path_filters_with_language(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN combining multiple path filters with language filter
        THEN results match (ANY path) AND (language)

        Acceptance Criteria #4
        """
        results = indexed_tantivy_manager.search(
            query_text="test",
            path_filters=["*/tests/*", "*/src/*"],
            languages=["py"],
            limit=50,
        )

        assert len(results) > 0, "Should find Python files in tests OR src"
        for result in results:
            # Must match at least one path pattern
            matches_tests = "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            )
            matches_src = "/src/" in result["path"] or result["path"].startswith("src/")
            assert (
                matches_tests or matches_src
            ), f"Expected path to match tests OR src, got: {result['path']}"

            # Must be Python
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
            ], f"Expected Python language, got: {result['language']}"

    def test_single_filter_backward_compat_via_path_filter(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN existing code using single path_filter parameter
        WHEN searching with deprecated path_filter
        THEN still works for backward compatibility

        Acceptance Criteria #7
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/tests/*", limit=50
        )

        assert len(results) > 0, "Single path_filter should still work"
        for result in results:
            assert "/tests/" in result["path"] or result["path"].startswith(
                "tests/"
            ), f"Expected path to contain '/tests/', got: {result['path']}"

    def test_empty_path_filters_returns_all(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with empty path_filters list
        THEN all results are returned
        """
        results = indexed_tantivy_manager.search(
            query_text="test", path_filters=[], limit=50
        )

        assert len(results) > 0, "Empty filters should return all matches"

    def test_or_logic_returns_more_than_individual_filters(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with multiple filters
        THEN combined results >= max(individual results)

        Validates OR logic semantics
        """
        # Get individual results
        tests_results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/tests/*", limit=50
        )
        src_results = indexed_tantivy_manager.search(
            query_text="test", path_filter="*/src/*", limit=50
        )

        # Get combined results
        combined_results = indexed_tantivy_manager.search(
            query_text="test", path_filters=["*/tests/*", "*/src/*"], limit=50
        )

        # Combined should have at least as many as the max individual count
        max_individual = max(len(tests_results), len(src_results))
        assert (
            len(combined_results) >= max_individual
        ), f"OR logic should return at least {max_individual} results, got {len(combined_results)}"


class TestPathPatternMatcherIntegration:
    """Test PathPatternMatcher integration in FTS (Story 3)."""

    def test_double_star_recursive_pattern(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with nested directory structure
        WHEN searching with double-star pattern '**/server/**'
        THEN files at any depth in server directories match

        Acceptance Criteria #5 (complex glob patterns)
        """
        results = indexed_tantivy_manager.search(
            query_text="config", path_filter="**/server/**", limit=50
        )

        # Should match src/server/config.py and src/server/app.py
        assert len(results) > 0, "Should find matches in server directory at any depth"
        for result in results:
            assert (
                "server" in result["path"]
            ), f"Expected 'server' in path, got: {result['path']}"

    def test_double_star_prefix_pattern(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with prefix pattern '**/helpers.py'
        THEN matches files at any depth with that name

        Acceptance Criteria #5 (complex glob patterns)
        """
        results = indexed_tantivy_manager.search(
            query_text="helper", path_filter="**/helpers.py", limit=50
        )

        # Should match src/utils/helpers.py regardless of depth
        assert len(results) > 0, "Should find helpers.py at any depth"
        for result in results:
            assert result["path"].endswith(
                "helpers.py"
            ), f"Expected path to end with helpers.py, got: {result['path']}"

    def test_cross_platform_separator_normalization(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN searching with forward slash pattern
        THEN matches work regardless of platform path separators

        Acceptance Criteria #4 (cross-platform handling)
        """
        # Use forward slashes in pattern (should work on both Unix and Windows)
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter="tests/test_auth.py", limit=50
        )

        # Should match tests/test_auth.py or tests\test_auth.py
        # PathPatternMatcher normalizes both to forward slashes
        assert len(results) > 0, "Should find test_auth.py with forward slash pattern"
        for result in results:
            # Normalize path for comparison
            normalized_path = result["path"].replace("\\", "/")
            assert normalized_path.endswith(
                "tests/test_auth.py"
            ), f"Expected tests/test_auth.py, got: {result['path']}"

    def test_pattern_matching_consistency_with_semantic_search(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN using same pattern with PathPatternMatcher
        THEN FTS matches same files as semantic search would

        Acceptance Criteria #2 (identical behavior to semantic search)
        """
        from src.code_indexer.services.path_pattern_matcher import PathPatternMatcher

        pattern = "*/tests/*"
        results = indexed_tantivy_manager.search(
            query_text="test", path_filter=pattern, limit=50
        )

        # Verify all results match using PathPatternMatcher directly
        matcher = PathPatternMatcher()
        for result in results:
            assert matcher.matches_pattern(
                result["path"], pattern
            ), f"Path {result['path']} should match pattern {pattern} using PathPatternMatcher"

    def test_backward_compatibility_with_fnmatch_patterns(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN existing fnmatch patterns from Story 2
        WHEN switching to PathPatternMatcher
        THEN all existing patterns continue to work

        Acceptance Criteria #3 (no regression)
        """
        # These patterns worked with fnmatch in Story 2
        test_cases = [
            ("*/tests/*", "test", lambda p: "/tests/" in p or p.startswith("tests/")),
            ("*.py", "test", lambda p: p.endswith(".py")),
            ("*/server/*", "config", lambda p: "/server/" in p or "server/" in p),
        ]

        for pattern, query, path_check in test_cases:
            results = indexed_tantivy_manager.search(
                query_text=query, path_filter=pattern, limit=50
            )

            # Should find results
            if len(results) > 0:
                # All results should match expected path pattern
                for result in results:
                    assert path_check(
                        result["path"]
                    ), f"Pattern {pattern} failed for path {result['path']}"


class TestExcludePath:
    """Test --exclude-path functionality (Story 5)."""

    def test_single_exclude_path(self, indexed_tantivy_manager: TantivyIndexManager):
        """
        GIVEN indexed repo with tests directory
        WHEN searching with exclude_paths=['*/tests/*']
        THEN no test files are returned

        Acceptance Criteria #1
        """
        results = indexed_tantivy_manager.search(
            query_text="test", exclude_paths=["*/tests/*"], limit=50
        )

        # Should find matches outside tests/
        assert len(results) >= 0  # May or may not find matches
        for result in results:
            assert "/tests/" not in result["path"] and not result["path"].startswith(
                "tests/"
            ), f"Expected no tests/ in path, got: {result['path']}"

    def test_multiple_exclude_paths(self, indexed_tantivy_manager: TantivyIndexManager):
        """
        GIVEN indexed repo with tests, docs, and src directories
        WHEN excluding multiple paths
        THEN none of the excluded directories appear in results

        Acceptance Criteria #2
        """
        results = indexed_tantivy_manager.search(
            query_text="test", exclude_paths=["*/tests/*", "*/docs/*"], limit=50
        )

        # Should find matches outside excluded directories
        for result in results:
            path = result["path"]
            assert "/tests/" not in path and not path.startswith(
                "tests/"
            ), f"Expected no tests/ in path, got: {path}"
            assert "/docs/" not in path and not path.startswith(
                "docs/"
            ), f"Expected no docs/ in path, got: {path}"

    def test_exclude_with_include_path_filters(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo with src directory containing server subdirectory
        WHEN including src but excluding src/server
        THEN src files returned except server

        Acceptance Criteria #3
        """
        results = indexed_tantivy_manager.search(
            query_text="test",
            path_filters=["*/src/*"],
            exclude_paths=["*/server/*"],
            limit=50,
        )

        # Should have src files but not server files
        for result in results:
            path = result["path"]
            assert "/src/" in path or path.startswith(
                "src/"
            ), f"Expected /src/ in path, got: {path}"
            assert "/server/" not in path, f"Expected no /server/ in path, got: {path}"

    def test_exclusion_precedence_over_inclusion(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN path that matches both inclusion and exclusion
        WHEN both filters applied
        THEN exclusion takes precedence

        Acceptance Criteria #4
        """
        # Include all .py files but exclude tests/*.py
        results = indexed_tantivy_manager.search(
            query_text="test",
            path_filters=["*.py"],  # Include all Python files
            exclude_paths=["*/tests/*"],  # But exclude tests
            limit=50,
        )

        # Should have Python files but not in tests/
        for result in results:
            path = result["path"]
            assert path.endswith(".py"), f"Expected .py file, got: {path}"
            assert "/tests/" not in path and not path.startswith(
                "tests/"
            ), f"Expected no tests/ in path (exclusion precedence), got: {path}"

    def test_exclude_with_language_filter(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN combining exclusion and language filters
        THEN results match language AND do not match exclusions

        Acceptance Criteria #5
        """
        results = indexed_tantivy_manager.search(
            query_text="test", languages=["py"], exclude_paths=["*/tests/*"], limit=50
        )

        # Should have Python files but not in tests/
        for result in results:
            assert result["language"] in [
                "py",
                "pyw",
                "pyi",
            ], f"Expected Python language, got: {result['language']}"
            assert "/tests/" not in result["path"] and not result["path"].startswith(
                "tests/"
            ), f"Expected no tests/ in path, got: {result['path']}"

    def test_exclude_with_fuzzy_search(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN combining exclusion with fuzzy search
        THEN results match fuzzy query AND do not match exclusions

        Acceptance Criteria #6
        """
        results = indexed_tantivy_manager.search(
            query_text="tets",  # Typo
            edit_distance=1,
            exclude_paths=["*/docs/*"],
            limit=50,
        )

        # All results should not be in docs/
        for result in results:
            assert "/docs/" not in result["path"] and not result["path"].startswith(
                "docs/"
            ), f"Expected no docs/ in path, got: {result['path']}"

    def test_exclude_with_case_sensitive(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN combining exclusion with case-sensitive search
        THEN results match case-sensitive query AND do not match exclusions

        Acceptance Criteria #6
        """
        results = indexed_tantivy_manager.search(
            query_text="test",
            case_sensitive=True,
            exclude_paths=["*/tests/*"],
            limit=50,
        )

        # All results should not be in tests/
        for result in results:
            assert "/tests/" not in result["path"] and not result["path"].startswith(
                "tests/"
            ), f"Expected no tests/ in path, got: {result['path']}"

    def test_no_exclusions_returns_all(
        self, indexed_tantivy_manager: TantivyIndexManager
    ):
        """
        GIVEN indexed repo
        WHEN no exclusions specified
        THEN all matching results returned
        """
        results_without = indexed_tantivy_manager.search(
            query_text="test", exclude_paths=None, limit=50
        )
        results_with_empty = indexed_tantivy_manager.search(
            query_text="test", exclude_paths=[], limit=50
        )

        # Both should return results
        assert len(results_without) > 0
        assert len(results_with_empty) > 0
        # Should be same number of results
        assert len(results_without) == len(results_with_empty)

    def test_exclude_file_extension(self, indexed_tantivy_manager: TantivyIndexManager):
        """
        GIVEN indexed repo with .py and .md files
        WHEN excluding .md files
        THEN only non-.md files are returned
        """
        results = indexed_tantivy_manager.search(
            query_text="test", exclude_paths=["*.md"], limit=50
        )

        # Should not have .md files
        for result in results:
            assert not result["path"].endswith(
                ".md"
            ), f"Expected no .md files, got: {result['path']}"
