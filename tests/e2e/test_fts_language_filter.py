"""
E2E tests for FTS multi-language filtering via CLI.

Tests the complete integration from CLI --language flags through to
LanguageMapper and TantivyIndexManager.
"""

import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path


@pytest.fixture(scope="function")
def test_repo():
    """
    Create a temporary test repository with multiple language files.
    """
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir) / "test_repo"
    repo_path.mkdir()

    # Create source files
    src_dir = repo_path / "src"
    src_dir.mkdir()

    # Python files
    (src_dir / "main.py").write_text("def test_function(): pass")
    (src_dir / "utils.py").write_text("class TestClass: pass")

    # JavaScript files
    (src_dir / "app.js").write_text("function test() { return 42; }")
    (src_dir / "helper.jsx").write_text("const TestComponent = () => <div>Test</div>;")

    # TypeScript files
    (src_dir / "component.ts").write_text("export function test(): void {}")
    (src_dir / "types.tsx").write_text("type TestType = { test: string };")

    # Java file
    (src_dir / "Main.java").write_text(
        "public class Main { public static void test() {} }"
    )

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        },
    )

    # Initialize cidx (no --fts flag on init)
    subprocess.run(["cidx", "init"], cwd=repo_path, check=True, capture_output=True)

    # Index with FTS enabled
    subprocess.run(
        ["cidx", "index", "--fts"], cwd=repo_path, check=True, capture_output=True
    )

    # Start services (no --fts flag on start)
    subprocess.run(["cidx", "start"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    # Cleanup
    try:
        subprocess.run(["cidx", "stop"], cwd=repo_path, capture_output=True)
    except Exception:
        pass
    shutil.rmtree(temp_dir)


class TestSingleLanguageFilterE2E:
    """E2E tests for single language filtering."""

    def test_filter_python_files(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language python --fts
        THEN only Python files (.py) are returned
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--language", "python", "--quiet"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Check output contains Python files
        assert (
            "main.py" in result.stdout or "utils.py" in result.stdout
        ), "Should find Python files"

        # Check output does NOT contain other language files
        assert "app.js" not in result.stdout, "Should not find JavaScript files"
        assert "Main.java" not in result.stdout, "Should not find Java files"

    def test_filter_javascript_files(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language javascript --fts
        THEN only JavaScript files (.js, .jsx) are returned
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--language", "javascript", "--quiet"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Check output contains JavaScript files
        assert (
            "app.js" in result.stdout or "helper.jsx" in result.stdout
        ), "Should find JavaScript files"

        # Check output does NOT contain other language files
        assert "main.py" not in result.stdout, "Should not find Python files"


class TestMultiLanguageFilterE2E:
    """E2E tests for multiple language filtering."""

    def test_filter_python_and_javascript(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language python --language javascript --fts
        THEN Python OR JavaScript files are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should find Python and/or JavaScript files
        has_python = "main.py" in result.stdout or "utils.py" in result.stdout
        has_javascript = "app.js" in result.stdout or "helper.jsx" in result.stdout

        assert has_python or has_javascript, "Should find Python or JavaScript files"

        # Should NOT find Java files
        assert "Main.java" not in result.stdout, "Should not find Java files"

    def test_filter_three_languages(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language python --language javascript --language java --fts
        THEN Python OR JavaScript OR Java files are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--language",
                "javascript",
                "--language",
                "java",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should find at least one of the target languages
        output = result.stdout
        found_target = any(
            [
                "main.py" in output,
                "utils.py" in output,
                "app.js" in output,
                "helper.jsx" in output,
                "Main.java" in output,
            ]
        )

        assert found_target, "Should find Python, JavaScript, or Java files"


class TestLanguageFilterWithFuzzyE2E:
    """E2E tests for language filtering with fuzzy search."""

    def test_fuzzy_search_with_language_filter(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running fuzzy FTS query with --language filter
        THEN only files of specified language matching fuzzily are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "tst",
                "--fts",
                "--fuzzy",
                "--language",
                "python",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # If results found, verify they are Python files
        if result.stdout.strip():
            assert (
                "main.py" in result.stdout or "utils.py" in result.stdout
            ), "Fuzzy results should be Python files"


class TestLanguageFilterWithCaseSensitiveE2E:
    """E2E tests for language filtering with case-sensitive search."""

    def test_case_sensitive_with_language_filter(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running case-sensitive FTS query with --language filter
        THEN only files of specified language with exact case matches are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "Test",
                "--fts",
                "--case-sensitive",
                "--language",
                "python",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # If results found, verify they are Python files
        if result.stdout.strip():
            output = result.stdout
            assert (
                "main.py" in output or "utils.py" in output
            ), "Case-sensitive results should be Python files"


class TestEdgeCasesE2E:
    """E2E tests for edge cases."""

    def test_unknown_language_returns_no_results(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running FTS query with --language unknown
        THEN no results are returned
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--language", "unknownlang", "--quiet"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        # Command should succeed but return no results
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        # Output should be empty or only contain headers
        assert "main.py" not in result.stdout, "Should not find any files"

    def test_no_language_filter_returns_all_languages(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running FTS query without --language flag
        THEN all matching files are returned (backward compatibility)
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--quiet"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should find files from multiple languages
        output = result.stdout
        has_multiple_languages = (
            sum(
                [
                    "main.py" in output or "utils.py" in output,
                    "app.js" in output or "helper.jsx" in output,
                    "Main.java" in output,
                ]
            )
            > 1
        )

        assert has_multiple_languages, "Should find files from multiple languages"


class TestPerformanceE2E:
    """E2E tests for performance requirements."""

    def test_language_filter_performance(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running FTS query with --language filter
        THEN query completes in <2 seconds (performance requirement includes CLI startup)

        NOTE: Original requirement was <1s for query execution, but CLI startup overhead
        adds ~300-500ms. Adjusted to <2s to account for subprocess and CLI initialization.
        """
        import time

        start_time = time.time()
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start_time

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert elapsed < 2.0, f"Query took {elapsed:.2f}s, should be <2s"


class TestExcludeLanguageE2E:
    """E2E tests for language exclusion."""

    def test_exclude_javascript(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --exclude-language javascript --fts
        THEN no JavaScript files are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have results (from other languages)
        assert result.stdout.strip(), "Should return non-JavaScript results"

        # Should NOT contain JavaScript files
        assert "app.js" not in result.stdout, "JavaScript files should be excluded"
        assert "helper.jsx" not in result.stdout, "JSX files should be excluded"

    def test_exclude_python(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --exclude-language python --fts
        THEN no Python files are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-language",
                "python",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have results (from other languages)
        assert result.stdout.strip(), "Should return non-Python results"

        # Should NOT contain Python files
        assert "main.py" not in result.stdout, "Python files should be excluded"
        assert "utils.py" not in result.stdout, "Python files should be excluded"

    def test_exclude_multiple_languages(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --exclude-language javascript --exclude-language typescript --fts
        THEN no JavaScript or TypeScript files are returned
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-language",
                "javascript",
                "--exclude-language",
                "typescript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have results (from other languages)
        assert result.stdout.strip(), "Should return non-JS/TS results"

        # Should NOT contain JavaScript or TypeScript files
        assert "app.js" not in result.stdout, "JavaScript should be excluded"
        assert "helper.jsx" not in result.stdout, "JSX should be excluded"
        assert "component.ts" not in result.stdout, "TypeScript should be excluded"
        assert "types.tsx" not in result.stdout, "TSX should be excluded"


class TestExclusionPrecedenceE2E:
    """E2E tests for exclusion precedence over inclusion."""

    def test_include_and_exclude_same_language(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language python --exclude-language python --fts
        THEN exclusion takes precedence (no results)
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--exclude-language",
                "python",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Exclusion wins - should return empty or only non-Python files
        # Since we only included Python but then excluded it, should be empty
        # (depending on implementation, might show "no results" message)
        assert "main.py" not in result.stdout, "Python should be excluded"
        assert "utils.py" not in result.stdout, "Python should be excluded"

    def test_include_multiple_exclude_one(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN running cidx query with --language python --language javascript --exclude-language javascript --fts
        THEN only Python files are returned (exclusion takes precedence)
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--language",
                "javascript",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have Python results
        assert (
            "main.py" in result.stdout or "utils.py" in result.stdout
        ), "Should return Python files"

        # Should NOT have JavaScript results
        assert "app.js" not in result.stdout, "JavaScript should be excluded"
        assert "helper.jsx" not in result.stdout, "JSX should be excluded"


class TestExcludeLanguageWithPathFiltersE2E:
    """E2E tests for language exclusion combined with path filters."""

    def test_exclude_language_with_path_filter(self, test_repo):
        """
        GIVEN a repository with files in multiple directories
        WHEN combining --exclude-language and --path-filter
        THEN results match path filter AND do not match excluded languages
        """
        # Create test-specific files
        tests_dir = test_repo / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_main.py").write_text("def test_function(): pass")
        (tests_dir / "test_app.js").write_text("function test() { return 42; }")

        # Re-index with new files
        subprocess.run(
            ["git", "add", "."], cwd=test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add test files"],
            cwd=test_repo,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )
        subprocess.run(
            ["cidx", "index", "--fts"], cwd=test_repo, check=True, capture_output=True
        )

        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have Python test files
        if result.stdout.strip():
            assert "test_main.py" in result.stdout, "Should find Python test files"
            # Should NOT have JavaScript test files
            assert "test_app.js" not in result.stdout, "JavaScript should be excluded"

    def test_exclude_language_with_exclude_path(self, test_repo):
        """
        GIVEN a repository with files in multiple directories
        WHEN combining --exclude-language and --exclude-path
        THEN both exclusions are applied
        """
        # Create vendor directory with files
        vendor_dir = test_repo / "vendor"
        vendor_dir.mkdir(exist_ok=True)
        (vendor_dir / "lib.js").write_text("function test() { return 1; }")

        # Re-index
        subprocess.run(
            ["git", "add", "."], cwd=test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add vendor"],
            cwd=test_repo,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )
        subprocess.run(
            ["cidx", "index", "--fts"], cwd=test_repo, check=True, capture_output=True
        )

        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-path",
                "*/vendor/*",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should NOT have vendor files
        assert "vendor/lib.js" not in result.stdout, "vendor should be excluded"
        # Should NOT have any JavaScript files
        assert "app.js" not in result.stdout, "JavaScript should be excluded"


class TestAllFiltersCombinedE2E:
    """E2E tests for all filter types working together."""

    def test_all_filters_combined(self, test_repo):
        """
        GIVEN a repository with files in multiple languages and paths
        WHEN using all filter types together
        THEN results match all filter criteria
        """
        # Create comprehensive test structure
        tests_dir = test_repo / "tests"
        tests_dir.mkdir(exist_ok=True)
        slow_dir = tests_dir / "slow"
        slow_dir.mkdir(exist_ok=True)
        unit_dir = tests_dir / "unit"
        unit_dir.mkdir(exist_ok=True)

        (slow_dir / "test_perf.py").write_text("def test_performance(): pass")
        (unit_dir / "test_utils.py").write_text("def test_utils(): pass")
        (tests_dir / "Main.java").write_text("public void test() {}")

        # Re-index
        subprocess.run(
            ["git", "add", "."], cwd=test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add test structure"],
            cwd=test_repo,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )
        subprocess.run(
            ["cidx", "index", "--fts"], cwd=test_repo, check=True, capture_output=True
        )

        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--language",
                "java",
                "--path-filter",
                "*/tests/*",
                "--exclude-path",
                "*/tests/slow/*",
                "--exclude-language",
                "java",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have Python unit test
        if result.stdout.strip():
            assert "test_utils.py" in result.stdout, "Should find Python unit tests"
            # Should NOT have slow tests
            assert "test_perf.py" not in result.stdout, "slow tests should be excluded"
            # Should NOT have Java (despite being in --language)
            assert "Main.java" not in result.stdout, "Java should be excluded"


class TestExcludeLanguageWithFuzzyE2E:
    """E2E tests for language exclusion with fuzzy and case-sensitive search."""

    def test_exclude_with_fuzzy_search(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN using --fuzzy with --exclude-language
        THEN fuzzy matching works and exclusions are applied
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "tst",
                "--fts",
                "--fuzzy",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # If results found, should NOT be JavaScript
        if result.stdout.strip():
            assert "app.js" not in result.stdout, "JavaScript should be excluded"
            assert "helper.jsx" not in result.stdout, "JSX should be excluded"

    def test_exclude_with_case_sensitive(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN using --case-sensitive with --exclude-language
        THEN case sensitivity is preserved and exclusions are applied
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "Test",
                "--fts",
                "--case-sensitive",
                "--exclude-language",
                "python",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # If results found, should NOT be Python
        if result.stdout.strip():
            assert "main.py" not in result.stdout, "Python should be excluded"
            assert "utils.py" not in result.stdout, "Python should be excluded"


class TestExcludeLanguagePerformanceE2E:
    """E2E tests for language exclusion performance."""

    def test_exclude_multiple_languages_performance(self, test_repo):
        """
        GIVEN a repository with multiple language files
        WHEN excluding multiple languages
        THEN query completes in <2 seconds
        """
        import time

        start_time = time.time()
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-language",
                "javascript",
                "--exclude-language",
                "typescript",
                "--exclude-language",
                "java",
                "--quiet",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start_time

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert (
            elapsed < 2.0
        ), f"Query with exclusions took {elapsed:.2f}s, should be <2s"
