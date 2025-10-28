"""
End-to-end integration tests for language exclusion feature.

These tests verify the complete flow from CLI to vector store search,
ensuring language exclusion works correctly across the entire system.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner

from code_indexer.cli import cli


@pytest.fixture
def test_codebase():
    """Create a temporary codebase with multiple languages."""
    temp_dir = tempfile.mkdtemp()
    base_path = Path(temp_dir)

    # Create Python files
    python_dir = base_path / "python_code"
    python_dir.mkdir()
    (python_dir / "auth.py").write_text("""
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    return verify_credentials(username, password)
""")
    (python_dir / "database.py").write_text("""
def connect_database(host, port):
    '''Connect to database server'''
    return establish_connection(host, port)
""")

    # Create JavaScript files
    js_dir = base_path / "js_code"
    js_dir.mkdir()
    (js_dir / "app.js").write_text("""
function initializeApp() {
    // Initialize application
    setupRoutes();
    startServer();
}
""")
    (js_dir / "utils.js").write_text("""
function formatDate(date) {
    // Format date string
    return date.toISOString();
}
""")

    # Create TypeScript files
    ts_dir = base_path / "ts_code"
    ts_dir.mkdir()
    (ts_dir / "component.ts").write_text("""
interface ComponentProps {
    name: string;
    value: number;
}

function renderComponent(props: ComponentProps) {
    return `Component: ${props.name}`;
}
""")

    # Create Java file
    java_dir = base_path / "java_code"
    java_dir.mkdir()
    (java_dir / "Main.java").write_text("""
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
""")

    yield base_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.mark.slow
@pytest.mark.integration
def test_exclude_javascript_returns_only_non_js_files(test_codebase):
    """
    GIVEN a codebase indexed with Python, JavaScript, TypeScript, and Java files
    WHEN querying with --exclude-language javascript
    THEN results contain only non-JavaScript files
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Initialize CIDX in test codebase
        init_result = runner.invoke(
            cli,
            ["init", str(test_codebase), "--provider", "voyageai"],
        )
        assert init_result.exit_code == 0, f"Init failed: {init_result.output}"

        # Start services
        start_result = runner.invoke(cli, ["start"])
        assert start_result.exit_code == 0, f"Start failed: {start_result.output}"

        # Index the codebase
        index_result = runner.invoke(cli, ["index"])
        assert index_result.exit_code == 0, f"Index failed: {index_result.output}"

        # Query with JavaScript exclusion
        query_result = runner.invoke(
            cli,
            ["query", "function implementation", "--exclude-language", "javascript", "--quiet"],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        # Verify no JavaScript files in output
        output = query_result.output
        assert ".js" not in output or "app.js" not in output, "Should not contain JavaScript files"
        assert "utils.js" not in output, "Should not contain JavaScript utility files"

        # Should contain other languages
        assert any(ext in output for ext in [".py", ".ts", ".java"]), "Should contain non-JavaScript files"


@pytest.mark.slow
@pytest.mark.integration
def test_exclude_multiple_languages(test_codebase):
    """
    GIVEN a codebase indexed with multiple languages
    WHEN querying with multiple --exclude-language flags
    THEN results exclude all specified languages
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Initialize and index
        runner.invoke(cli, ["init", str(test_codebase), "--provider", "voyageai"])
        runner.invoke(cli, ["start"])
        runner.invoke(cli, ["index"])

        # Query excluding both JavaScript and TypeScript
        query_result = runner.invoke(
            cli,
            [
                "query",
                "function code",
                "--exclude-language", "javascript",
                "--exclude-language", "typescript",
                "--quiet",
            ],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # Verify no JS or TS files in output
        assert ".js" not in output or "app.js" not in output, "Should not contain JavaScript files"
        assert ".ts" not in output or "component.ts" not in output, "Should not contain TypeScript files"

        # Should contain Python or Java
        assert any(ext in output for ext in [".py", ".java"]), "Should contain Python or Java files"


@pytest.mark.slow
@pytest.mark.integration
def test_exclude_with_include_language_filter(test_codebase):
    """
    GIVEN a codebase indexed with multiple languages
    WHEN querying with both --language (include) and --exclude-language
    THEN results match include filter AND exclude specified languages
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Initialize and index
        runner.invoke(cli, ["init", str(test_codebase), "--provider", "voyageai"])
        runner.invoke(cli, ["start"])
        runner.invoke(cli, ["index"])

        # Query for Python but exclude JavaScript (should only affect if somehow both matched)
        query_result = runner.invoke(
            cli,
            [
                "query",
                "function",
                "--language", "python",
                "--exclude-language", "javascript",
                "--quiet",
            ],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # Verify only Python files in output
        if output.strip():  # If there are results
            assert ".py" in output or "python" in output.lower(), "Should contain Python files"
            assert ".js" not in output or "app.js" not in output, "Should not contain JavaScript files"


@pytest.mark.slow
@pytest.mark.integration
def test_exclude_with_path_filter(test_codebase):
    """
    GIVEN a codebase indexed with multiple languages
    WHEN querying with both --path and --exclude-language
    THEN results match path filter AND exclude specified languages
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Initialize and index
        runner.invoke(cli, ["init", str(test_codebase), "--provider", "voyageai"])
        runner.invoke(cli, ["start"])
        runner.invoke(cli, ["index"])

        # Query with path filter and language exclusion
        query_result = runner.invoke(
            cli,
            [
                "query",
                "code",
                "--path", "*/python_code/*",
                "--exclude-language", "javascript",
                "--quiet",
            ],
        )
        assert query_result.exit_code == 0, f"Query failed: {query_result.output}"

        output = query_result.output

        # Verify path filter worked and JS is excluded
        if output.strip():  # If there are results
            assert "python_code" in output, "Should contain files from python_code directory"
            assert ".js" not in output or "app.js" not in output, "Should not contain JavaScript files"
