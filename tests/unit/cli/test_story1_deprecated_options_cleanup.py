"""Test Story 1: Cleanup Existing API Attempts - Remove deprecated semantic CLI options.

Tests to verify that deprecated semantic query options from AST-based chunking are completely removed:
- --semantic-type, --type
- --semantic-scope, --scope
- --semantic-features, --features
- --semantic-parent, --parent
- --semantic-only

These options were part of the failed AST-based chunking approach and should no longer exist.
"""

from click.testing import CliRunner

from code_indexer.cli import query


class TestDeprecatedSemanticOptionsRemoval:
    """Test that deprecated semantic CLI options have been completely removed."""

    def test_deprecated_semantic_type_option_removed(self):
        """Verify --semantic-type option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--semantic-type", "function", "test query"])

        # Should fail with "No such option" error, not with internal TypeError
        assert result.exit_code != 0

        # Check if it's the right kind of failure - should be option error, not internal error
        if result.exception:
            # Should be a UsageError from Click for unknown option, not TypeError
            assert not isinstance(
                result.exception, TypeError
            ), "Should reject option, not fail with internal TypeError"

        # The output should indicate the option is not recognized
        output_text = result.output if result.output else str(result.exception)
        assert (
            "No such option" in output_text
            or "no such option" in output_text
            or "unknown option" in output_text.lower()
        ), f"Should show option error, got: {output_text}"

    def test_deprecated_type_shorthand_option_removed(self):
        """Verify --type shorthand option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--type", "function", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--type" in result.output

    def test_deprecated_semantic_scope_option_removed(self):
        """Verify --semantic-scope option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--semantic-scope", "global", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--semantic-scope" in result.output

    def test_deprecated_scope_shorthand_option_removed(self):
        """Verify --scope shorthand option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--scope", "global", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--scope" in result.output

    def test_deprecated_semantic_features_option_removed(self):
        """Verify --semantic-features option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(
            query, ["--semantic-features", "async,static", "test query"]
        )

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--semantic-features" in result.output

    def test_deprecated_features_shorthand_option_removed(self):
        """Verify --features shorthand option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--features", "async,static", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--features" in result.output

    def test_deprecated_semantic_parent_option_removed(self):
        """Verify --semantic-parent option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--semantic-parent", "ClassName", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--semantic-parent" in result.output

    def test_deprecated_parent_shorthand_option_removed(self):
        """Verify --parent shorthand option has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--parent", "ClassName", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--parent" in result.output

    def test_deprecated_semantic_only_flag_removed(self):
        """Verify --semantic-only flag has been removed from query command."""
        runner = CliRunner()
        result = runner.invoke(query, ["--semantic-only", "test query"])

        # Should fail with "No such option" error
        assert result.exit_code != 0
        assert "No such option" in result.output
        assert "--semantic-only" in result.output

    def test_query_help_text_no_semantic_options(self):
        """Verify query help text does not mention any deprecated semantic options."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # None of the deprecated options should appear in help text
        deprecated_options = [
            "--semantic-type",
            "--semantic-scope",
            "--semantic-features",
            "--semantic-parent",
            "--semantic-only",
        ]

        for option in deprecated_options:
            assert (
                option not in help_text
            ), f"Deprecated option {option} found in help text"

    def test_query_help_text_no_semantic_filtering_section(self):
        """Verify query help text does not have semantic filtering section."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # Should not have semantic filtering sections
        assert "result filtering (code structure)" not in help_text
        assert "structured only:" not in help_text
        assert "semantic filtering" not in help_text

    def test_query_help_text_no_semantic_examples(self):
        """Verify query help text does not contain semantic filtering examples."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # Should not contain examples using deprecated semantic options
        deprecated_example_patterns = [
            "--type function",
            "--type class",
            "--scope global",
            "--parent user",
            "--features async",
            "--semantic-only",
        ]

        for pattern in deprecated_example_patterns:
            assert (
                pattern not in help_text
            ), f"Deprecated example pattern '{pattern}' found in help text"


class TestDebugFilesRemoval:
    """Test that debug files from failed C# API implementation are removed."""

    def test_debug_async_api_implementation_file_removed(self):
        """Verify debug/test_async_api_implementation.py has been removed."""
        import os
        from pathlib import Path

        # Navigate to project root dynamically
        project_root = Path(__file__).parent.parent.parent.parent
        debug_file = project_root / "debug" / "test_async_api_implementation.py"

        assert not os.path.exists(
            debug_file
        ), f"Debug file {debug_file} should be removed"

    def test_debug_async_api_no_auth_file_removed(self):
        """Verify debug/test_async_api_no_auth.py has been removed."""
        import os
        from pathlib import Path

        # Navigate to project root dynamically
        project_root = Path(__file__).parent.parent.parent.parent
        debug_file = project_root / "debug" / "test_async_api_no_auth.py"

        assert not os.path.exists(
            debug_file
        ), f"Debug file {debug_file} should be removed"
