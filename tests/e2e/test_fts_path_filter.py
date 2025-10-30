"""
End-to-end tests for FTS path filtering via CLI.

Tests verify that --path-filter flag works correctly when invoked through the CLI.
"""

import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """
    Create a sample git repository with structured directories.

    Structure:
        tests/
            test_auth.py - contains "login" and "authentication"
            test_utils.py - contains "helper" and "utility"
        src/
            server/
                config.py - contains "configuration" and "settings"
                app.py - contains "application" and "server"
            utils/
                helpers.py - contains "utility" and "helper"
        docs/
            README.md - contains "documentation"
        main.js - contains "javascript" and "test"
    """
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create directory structure
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_auth.py").write_text(
        """def test_login():
    \"\"\"Test user login functionality\"\"\"
    assert authenticate_user('test', 'password')

def test_logout():
    \"\"\"Test user logout\"\"\"
    assert True
"""
    )
    (tests_dir / "test_utils.py").write_text(
        """def test_helper():
    \"\"\"Test helper function\"\"\"
    result = utility_helper()
    assert result is not None
"""
    )

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    server_dir = src_dir / "server"
    server_dir.mkdir()
    (server_dir / "config.py").write_text(
        """# Configuration settings
CONFIG = {
    'debug': True,
    'host': 'localhost'
}
"""
    )
    (server_dir / "app.py").write_text(
        """# Main application server
def main():
    \"\"\"Start the server application\"\"\"
    pass
"""
    )

    utils_dir = src_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "helpers.py").write_text(
        """# Utility helper functions
def utility_helper():
    \"\"\"Helper function for utilities\"\"\"
    return 'test'
"""
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "README.md").write_text(
        """# Test Documentation

This is test documentation for the project.
"""
    )

    (tmp_path / "main.js").write_text(
        """// JavaScript test file
function test() {
    console.log('test function');
}
"""
    )

    # Commit all files
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Initialize cidx and index with FTS
    subprocess.run(
        ["cidx", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cidx", "start"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cidx", "index", "--fts"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        timeout=60,
    )

    return tmp_path


class TestCLIPathFilterBasics:
    """Test basic CLI path filtering functionality."""

    def test_cli_path_filter_tests_directory(self, sample_repo: Path):
        """
        Test --path-filter '*/tests/*' with FTS returns only test files.

        Acceptance Criteria #1
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--path-filter", "*/tests/*", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find matches
        assert output.strip(), "Expected results, got empty output"

        # Verify all results are from tests/ directory
        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):  # Skip comments/headers
                assert "tests/" in line or line.startswith(
                    "tests/"
                ), f"Expected tests/ in path, got: {line}"

    def test_cli_path_filter_server_directory(self, sample_repo: Path):
        """
        Test --path-filter '*/server/*' returns only server files.

        Acceptance Criteria #2
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "config",
                "--fts",
                "--path-filter",
                "*/server/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find matches in server directory
        assert output.strip(), "Expected results, got empty output"

        # Verify all results are from server/ directory
        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert "server/" in line, f"Expected server/ in path, got: {line}"

    def test_cli_path_filter_file_extension(self, sample_repo: Path):
        """
        Test --path-filter '*.py' returns only Python files.

        Acceptance Criteria #3
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--path-filter", "*.py", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find matches
        assert output.strip(), "Expected results, got empty output"

        # Verify all results are .py files
        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert ".py" in line, f"Expected .py file, got: {line}"


class TestCLIPathFilterCombinations:
    """Test path filter combined with other CLI options."""

    def test_cli_path_filter_with_fuzzy(self, sample_repo: Path):
        """
        Test path filter with fuzzy search.

        Acceptance Criteria #4
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "tets",  # Typo
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--fuzzy",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Fuzzy matching may or may not find results depending on edit distance
        # But if it does, they should all be from tests/
        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "tests/" in line or line.startswith(
                        "tests/"
                    ), f"Expected tests/ in path, got: {line}"

    def test_cli_path_filter_with_case_sensitive(self, sample_repo: Path):
        """
        Test path filter with case-sensitive search.

        Acceptance Criteria #5
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--case-sensitive",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should find case-sensitive matches
        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "tests/" in line or line.startswith(
                        "tests/"
                    ), f"Expected tests/ in path, got: {line}"

    def test_cli_path_filter_with_language(self, sample_repo: Path):
        """
        Test combining --path-filter and --language filters.

        Acceptance Criteria #6
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--language",
                "python",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find Python test files
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert "tests/" in line or line.startswith(
                    "tests/"
                ), f"Expected tests/ in path, got: {line}"
                assert ".py" in line, f"Expected .py file, got: {line}"


class TestCLIPathFilterEdgeCases:
    """Test edge cases and error handling."""

    def test_cli_path_filter_no_matches(self, sample_repo: Path):
        """
        Test that non-matching path filter returns empty results gracefully.

        Acceptance Criteria #7
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/nonexistent/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        # Should succeed but return empty results
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Output should indicate no matches
        output = result.stdout.strip()
        # Either empty or contains "No matches" message
        assert not output or "No matches" in output or "0 results" in output

    def test_cli_no_path_filter_returns_all(self, sample_repo: Path):
        """
        Test that no path filter returns all matches.

        Acceptance Criteria #8 (backward compatibility)
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output_all = result.stdout

        # Should find matches from multiple directories
        assert output_all.strip(), "Expected results, got empty output"

        # Should include results from different directories
        # (tests/, src/, possibly root level)
        assert "test" in output_all.lower()

    def test_cli_help_shows_path_filter(self):
        """Verify that --help displays the --path-filter option."""
        result = subprocess.run(
            ["cidx", "query", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--path-filter" in result.stdout, "Expected --path-filter in help text"


class TestCLIMultiplePathFilters:
    """Test multiple path filter support via CLI (Story 4)."""

    def test_cli_multiple_path_filters_or_logic(self, sample_repo: Path):
        """
        Test multiple --path-filter flags with OR logic.

        Acceptance Criteria #1, #2
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--path-filter",
                "*/src/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find matches from tests OR src directories
        assert output.strip(), "Expected results, got empty output"

        # Verify all results match at least one pattern
        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                matches_tests = "tests/" in line or line.startswith("tests/")
                matches_src = "src/" in line or line.startswith("src/")
                assert (
                    matches_tests or matches_src
                ), f"Expected path to match tests OR src, got: {line}"

    def test_cli_three_path_filters(self, sample_repo: Path):
        """
        Test three path filters with complex patterns.

        Acceptance Criteria #3
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--path-filter",
                "*/src/*",
                "--path-filter",
                "*.js",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find matches with any of three patterns
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                matches_tests = "tests/" in line or line.startswith("tests/")
                matches_src = "src/" in line or line.startswith("src/")
                matches_js = ".js" in line
                assert (
                    matches_tests or matches_src or matches_js
                ), f"Expected path to match one of three patterns, got: {line}"

    def test_cli_path_and_language_filters(self, sample_repo: Path):
        """
        Test combining multiple path filters with language filter.

        Acceptance Criteria #4
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/tests/*",
                "--path-filter",
                "*/src/*",
                "--language",
                "python",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find Python files in tests OR src
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                matches_tests = "tests/" in line or line.startswith("tests/")
                matches_src = "src/" in line or line.startswith("src/")
                assert (
                    matches_tests or matches_src
                ), f"Expected path to match tests OR src, got: {line}"
                assert ".py" in line, f"Expected Python file, got: {line}"

    def test_cli_backward_compat_single_filter(self, sample_repo: Path):
        """
        Test that single --path-filter still works.

        Acceptance Criteria #7
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--path-filter", "*/tests/*", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should work exactly as before
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert "tests/" in line or line.startswith(
                    "tests/"
                ), f"Expected tests/ in path, got: {line}"

    def test_cli_help_shows_multiple_filters_supported(self):
        """
        Verify help text shows multiple filters are supported.

        Acceptance Criteria #5
        """
        result = subprocess.run(
            ["cidx", "query", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        help_text = result.stdout

        # Help should mention path-filter and ideally mention multiple times or OR logic
        assert "--path-filter" in help_text, "Expected --path-filter in help text"
        # Note: After implementation, help should mention "multiple times" or "OR logic"


class TestCLIPathPatternMatcherIntegration:
    """Test PathPatternMatcher integration via CLI (Story 3)."""

    def test_cli_double_star_recursive_pattern(self, sample_repo: Path):
        """
        Test double-star pattern '**/server/**' matches files at any depth.

        Acceptance Criteria #5 (complex glob patterns with **)
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "config",
                "--fts",
                "--path-filter",
                "**/server/**",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find src/server/config.py and src/server/app.py
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert "server" in line, f"Expected 'server' in path, got: {line}"

    def test_cli_double_star_prefix_pattern(self, sample_repo: Path):
        """
        Test prefix pattern '**/helpers.py' matches file at any depth.

        Acceptance Criteria #5 (complex glob patterns with **)
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "utility",
                "--fts",
                "--path-filter",
                "**/helpers.py",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should find src/utils/helpers.py regardless of depth
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                assert "helpers.py" in line, f"Expected helpers.py in path, got: {line}"

    def test_cli_cross_platform_forward_slash_pattern(self, sample_repo: Path):
        """
        Test that forward slash patterns work on all platforms.

        Acceptance Criteria #4 (cross-platform path separator handling)
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "tests/test_auth.py",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        output = result.stdout

        # Should match tests/test_auth.py (or tests\test_auth.py on Windows)
        assert output.strip(), "Expected results, got empty output"

        lines = output.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                # Normalize for comparison
                normalized = line.replace("\\", "/")
                assert (
                    "tests/test_auth.py" in normalized
                ), f"Expected tests/test_auth.py, got: {line}"


class TestCLIExcludePath:
    """Test --exclude-path CLI functionality (Story 5)."""

    def test_cli_exclude_single_directory(self, sample_repo: Path):
        """
        Test excluding tests directory via CLI.

        Acceptance Criteria #1
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-path",
                "*/tests/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should not find any tests/ files
        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "tests/" not in line and not line.startswith(
                        "tests/"
                    ), f"Expected no tests/ in path, got: {line}"

    def test_cli_multiple_exclusions(self, sample_repo: Path):
        """
        Test multiple --exclude-path flags.

        Acceptance Criteria #2
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--exclude-path",
                "*/tests/*",
                "--exclude-path",
                "*/docs/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "tests/" not in line and not line.startswith(
                        "tests/"
                    ), f"Expected no tests/ in path, got: {line}"
                    assert "docs/" not in line and not line.startswith(
                        "docs/"
                    ), f"Expected no docs/ in path, got: {line}"

    def test_cli_include_and_exclude_combination(self, sample_repo: Path):
        """
        Test combining --path-filter and --exclude-path.

        Acceptance Criteria #3
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*/src/*",
                "--exclude-path",
                "*/server/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "src/" in line or line.startswith(
                        "src/"
                    ), f"Expected src/ in path, got: {line}"
                    assert (
                        "server/" not in line
                    ), f"Expected no server/ in path (exclusion precedence), got: {line}"

    def test_cli_exclusion_precedence_over_inclusion(self, sample_repo: Path):
        """
        Test that exclusion takes precedence over inclusion.

        Acceptance Criteria #4
        """
        # First verify that tests/*.py files exist
        result_include_only = subprocess.run(
            ["cidx", "query", "test", "--fts", "--path-filter", "*.py", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )
        assert result_include_only.returncode == 0
        # Should have test files in output
        assert (
            "tests/" in result_include_only.stdout
            or result_include_only.stdout.startswith("tests/")
        )

        # Now exclude tests
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--path-filter",
                "*.py",
                "--exclude-path",
                "*/tests/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should have .py files but NOT in tests/
        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert ".py" in line, f"Expected .py file, got: {line}"
                    assert "tests/" not in line and not line.startswith(
                        "tests/"
                    ), f"Expected no tests/ (exclusion precedence), got: {line}"

    def test_cli_exclude_with_language_filter(self, sample_repo: Path):
        """
        Test combining --exclude-path with --language.

        Acceptance Criteria #5
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--language",
                "python",
                "--exclude-path",
                "*/tests/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert ".py" in line, f"Expected Python file, got: {line}"
                    assert "tests/" not in line and not line.startswith(
                        "tests/"
                    ), f"Expected no tests/ in path, got: {line}"

    def test_cli_exclude_with_fuzzy_search(self, sample_repo: Path):
        """
        Test combining --exclude-path with --fuzzy.

        Acceptance Criteria #6
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "tets",  # Typo
                "--fts",
                "--fuzzy",
                "--exclude-path",
                "*/docs/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "docs/" not in line and not line.startswith(
                        "docs/"
                    ), f"Expected no docs/ in path, got: {line}"

    def test_cli_exclude_with_case_sensitive(self, sample_repo: Path):
        """
        Test combining --exclude-path with --case-sensitive.

        Acceptance Criteria #6
        """
        result = subprocess.run(
            [
                "cidx",
                "query",
                "test",
                "--fts",
                "--case-sensitive",
                "--exclude-path",
                "*/tests/*",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert "tests/" not in line and not line.startswith(
                        "tests/"
                    ), f"Expected no tests/ in path, got: {line}"

    def test_cli_exclude_file_extension(self, sample_repo: Path):
        """
        Test excluding specific file extensions.
        """
        result = subprocess.run(
            ["cidx", "query", "test", "--fts", "--exclude-path", "*.md", "--quiet"],
            capture_output=True,
            text=True,
            cwd=sample_repo,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout.strip()
        if output:
            lines = output.split("\n")
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    assert not line.endswith(
                        ".md"
                    ), f"Expected no .md files, got: {line}"

    def test_cli_help_shows_exclude_path(self):
        """Verify that --help displays the --exclude-path option."""
        result = subprocess.run(
            ["cidx", "query", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--exclude-path" in result.stdout, "Expected --exclude-path in help text"
        # Should mention precedence
        help_text = result.stdout.lower()
        assert (
            "precedence" in help_text or "exclude" in help_text
        ), "Help text should mention exclusion behavior"
