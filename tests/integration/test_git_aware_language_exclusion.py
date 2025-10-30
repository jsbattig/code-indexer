"""
Integration tests for language exclusion in git-aware repositories.

This test suite specifically validates that --exclude-language works correctly
in git-aware repositories (the most common use case), where the query path
rebuilds filter conditions from scratch.

BUG: Lines 3407-3409 in cli.py discard must_not conditions for git-aware queries,
causing --exclude-language to be ignored.
"""

import pytest
import tempfile
import shutil
import subprocess
from pathlib import Path
from click.testing import CliRunner

from code_indexer.cli import cli


@pytest.fixture
def git_aware_test_codebase():
    """Create a git repository with multiple languages for testing git-aware queries."""
    temp_dir = tempfile.mkdtemp()
    base_path = Path(temp_dir)

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=base_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=base_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=base_path,
        check=True,
        capture_output=True,
    )

    # Create Python file
    (base_path / "test.py").write_text(
        """
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    return verify_credentials(username, password)
"""
    )

    # Create JavaScript file
    (base_path / "test.js").write_text(
        """
function authenticateUser(username, password) {
    // Authenticate user with credentials
    return verifyCredentials(username, password);
}
"""
    )

    # Create TypeScript file
    (base_path / "test.ts").write_text(
        """
function authenticateUser(username: string, password: string): boolean {
    // Authenticate user with credentials
    return verifyCredentials(username, password);
}
"""
    )

    # Commit files to git
    subprocess.run(["git", "add", "."], cwd=base_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=base_path,
        check=True,
        capture_output=True,
    )

    yield base_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.mark.integration
def test_exclude_javascript_in_git_aware_repository(git_aware_test_codebase):
    """
    GIVEN a git-aware repository with Python and JavaScript files
    WHEN querying with --exclude-language javascript
    THEN results contain only Python files, NOT JavaScript files

    This test reproduces the critical bug where must_not conditions are discarded
    in the git-aware query path (lines 3407-3409 in cli.py).
    """
    runner = CliRunner()

    # Run all commands in the git repository directory (no isolated filesystem)
    import os

    original_dir = os.getcwd()

    try:
        os.chdir(git_aware_test_codebase)

        # Initialize CIDX in current directory (the git-aware test codebase)
        init_result = runner.invoke(
            cli,
            ["init", "--embedding-provider", "voyage-ai"],
        )
        assert init_result.exit_code == 0, f"Init failed: {init_result.output}"

        # Start services
        start_result = runner.invoke(cli, ["start"])
        assert start_result.exit_code == 0, f"Start failed: {start_result.output}"

        # Index the codebase (will detect git and use git-aware indexing)
        index_result = runner.invoke(cli, ["index"])
        assert index_result.exit_code == 0, f"Index failed: {index_result.output}"

        # Query with JavaScript exclusion - THIS SHOULD EXCLUDE .js FILES
        query_result = runner.invoke(
            cli,
            ["query", "authenticate", "--exclude-language", "javascript", "--quiet"],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # CRITICAL ASSERTION: JavaScript files MUST NOT appear in results
        # BUG: Currently test.js DOES appear because must_not conditions are discarded
        assert "test.js" not in output, (
            f"BUG: JavaScript file should be excluded but appears in results. "
            f"The git-aware query path (lines 3407-3409) discards must_not conditions. "
            f"Output:\n{output}"
        )

        # Python files SHOULD appear
        assert (
            "test.py" in output
        ), f"Python file should appear in results but doesn't. Output:\n{output}"

        # Cleanup - stop services
        runner.invoke(cli, ["stop"])

    finally:
        os.chdir(original_dir)


@pytest.mark.integration
def test_exclude_multiple_languages_in_git_aware_repository(git_aware_test_codebase):
    """
    GIVEN a git-aware repository with Python, JavaScript, and TypeScript files
    WHEN querying with multiple --exclude-language flags
    THEN results exclude ALL specified languages
    """
    runner = CliRunner()
    import os

    original_dir = os.getcwd()

    try:
        os.chdir(git_aware_test_codebase)

        # Initialize and index
        runner.invoke(cli, ["init", "--embedding-provider", "voyage-ai"])
        runner.invoke(cli, ["start"])
        runner.invoke(cli, ["index"])

        # Query excluding both JavaScript and TypeScript
        query_result = runner.invoke(
            cli,
            [
                "query",
                "authenticate",
                "--exclude-language",
                "javascript",
                "--exclude-language",
                "typescript",
                "--quiet",
            ],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # Verify no JS or TS files in output
        assert (
            "test.js" not in output
        ), f"JavaScript file should be excluded. Output:\n{output}"
        assert (
            "test.ts" not in output
        ), f"TypeScript file should be excluded. Output:\n{output}"

        # Python file should appear
        assert (
            "test.py" in output
        ), f"Python file should appear in results. Output:\n{output}"

        # Cleanup
        runner.invoke(cli, ["stop"])

    finally:
        os.chdir(original_dir)


@pytest.mark.integration
def test_exclude_with_language_filter_in_git_aware_repository(git_aware_test_codebase):
    """
    GIVEN a git-aware repository with multiple languages
    WHEN querying with both --language python and --exclude-language javascript
    THEN results contain only Python files
    """
    runner = CliRunner()
    import os

    original_dir = os.getcwd()

    try:
        os.chdir(git_aware_test_codebase)

        # Initialize and index
        runner.invoke(cli, ["init", "--embedding-provider", "voyage-ai"])
        runner.invoke(cli, ["start"])
        runner.invoke(cli, ["index"])

        # Query for Python with JavaScript exclusion
        query_result = runner.invoke(
            cli,
            [
                "query",
                "authenticate",
                "--language",
                "python",
                "--exclude-language",
                "javascript",
                "--quiet",
            ],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # Verify only Python files in output
        if output.strip():  # If there are results
            assert "test.py" in output, "Should contain Python files"
            assert "test.js" not in output, "Should not contain JavaScript files"

        # Cleanup
        runner.invoke(cli, ["stop"])

    finally:
        os.chdir(original_dir)
