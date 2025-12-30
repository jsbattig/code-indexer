"""
Test suite for Rich markup injection vulnerability (P0 bug fix)

This test validates that file content containing Rich markup syntax
(e.g., [{status_style}], [bold], [red]) is displayed safely without
triggering MarkupError exceptions.

Root Cause: console.print() without markup=False allows Rich to parse
file content as markup, causing crashes when code contains markup syntax.

Bug Locations Fixed:
- cli.py content display lines (multiple locations)
- cli.py exception handler
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner


# Test constants
QUERY_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def temp_test_dir():
    """Create temporary directory with test files containing Rich markup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)

        # Create test file with Rich markup syntax that triggers the bug
        test_file = test_dir / "test_rich_markup.py"
        test_file.write_text("""
# Test file containing Rich markup syntax
def display_status():
    status_style = "bold green"
    console.print(f"[{status_style}]Status: OK[/{status_style}]")
    console.print("[red]Error message[/red]")
    console.print("[bold blue]Info: {info}[/bold blue]")
""")

        # Create test file with complex markup patterns
        complex_file = test_dir / "test_complex_markup.py"
        complex_file.write_text("""
# Complex Rich markup patterns
def render_ui():
    # These patterns caused MarkupError in manual testing
    markup = "[{status_style}]Text[/{status_style}]"
    nested = "[bold [red]Error[/red]][/bold]"
    unclosed = "[green]Missing close tag"
    special = "[link=https://example.com]Link[/link]"
""")

        yield test_dir


class TestRichMarkupInjectionBehavioral:
    """Behavioral tests for Rich markup injection vulnerability."""

    def test_query_result_with_rich_markup_syntax(self, temp_test_dir):
        """
        Core behavioral test: Query results containing Rich markup display safely.

        Bug: When file content contains Rich markup like [{status_style}],
        console.print() parses it as markup, causing MarkupError crash.

        Expected: File content displayed as plain text without MarkupError.
        """
        from code_indexer.cli import cli

        runner = CliRunner()

        # Initialize and index the test directory
        with runner.isolated_filesystem(temp_dir=str(temp_test_dir.parent)):
            import os
            os.chdir(temp_test_dir)

            # Initialize cidx
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0, f"Init failed: {result.output}"

            # Index the test files
            result = runner.invoke(cli, ["index"])
            assert result.exit_code == 0, f"Index failed: {result.output}"

            # Query for content that contains Rich markup syntax
            # This should NOT crash with MarkupError
            result = runner.invoke(cli, ["query", "status_style", "--quiet", "--limit", "5"])

            # CRITICAL: This must NOT crash with MarkupError
            assert result.exit_code == 0, (
                f"Query crashed with Rich markup injection vulnerability!\n"
                f"Output: {result.output}\n"
                f"Exception: {result.exception}"
            )

            # Verify the content is displayed (not just error-suppressed)
            assert "status_style" in result.output or "display_status" in result.output, (
                "Content should be displayed, not silently suppressed"
            )

    def test_exception_handler_has_markup_protection(self, temp_test_dir):
        """
        Exception handler test: Verify exception handler uses markup=False.

        The query exception handler must use markup=False to prevent Rich
        markup injection when exception messages contain markup syntax.
        """
        # Verify the fix is present in the code
        cli_file = Path(__file__).parent.parent / "src" / "code_indexer" / "cli.py"
        content = cli_file.read_text()

        # The exception handler should have markup=False
        assert 'console.print(f"❌ Search failed: {e}", style="red", markup=False)' in content, (
            "Query exception handler must use markup=False to prevent markup injection"
        )

    def test_nested_markup_patterns(self, temp_test_dir):
        """
        Complex markup test: Various nested and complex Rich markup patterns.

        Patterns tested:
        - Nested tags: [bold [red]Text[/red]][/bold]
        - Dynamic tags: [{variable}]Text[/{variable}]
        - Unclosed tags: [green]Text without close
        - Special syntax: [link=url]Text[/link]
        """
        from code_indexer.cli import cli

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(temp_test_dir.parent)):
            import os
            os.chdir(temp_test_dir)

            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["index"])

            # Query for complex markup file
            result = runner.invoke(cli, ["query", "nested", "--quiet", "--limit", "5"])

            # Must not crash
            assert result.exit_code == 0, (
                f"Complex markup patterns caused crash: {result.exception}"
            )

    def test_semantic_search_result_with_rich_markup(self, temp_test_dir):
        """
        Semantic search path test: Verify _display_hybrid_results() protects against markup injection.

        Bug: Lines 1370, 1372, 1383 in _display_hybrid_results() display content
        without markup=False, causing crashes when semantic search results contain
        Rich markup syntax.

        This test uses --hybrid mode to trigger semantic search display path.

        Expected: Semantic search results with Rich markup display safely without crash.
        """
        from code_indexer.cli import cli

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(temp_test_dir.parent)):
            import os
            os.chdir(temp_test_dir)

            # Initialize and index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0, f"Init failed: {result.output}"

            # Index semantic
            result = runner.invoke(cli, ["index"])
            assert result.exit_code == 0, f"Semantic index failed: {result.output}"

            # CRITICAL: Build FTS index to enable hybrid mode
            result = runner.invoke(cli, ["index", "--fts"])
            assert result.exit_code == 0, f"FTS index failed: {result.output}"

            # Query with --semantic --fts to trigger hybrid search path
            # This will hit _display_hybrid_results() which has the vulnerability
            result = runner.invoke(
                cli,
                ["query", "status_style", "--semantic", "--fts", "--quiet", "--limit", "5"]
            )

            # CRITICAL: This must NOT crash with MarkupError in semantic results display
            assert result.exit_code == 0, (
                f"Semantic search crashed with Rich markup injection vulnerability!\n"
                f"Output: {result.output}\n"
                f"Exception: {result.exception}"
            )

            # Verify content is displayed
            assert "status_style" in result.output or "display_status" in result.output, (
                "Semantic search content should be displayed"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
