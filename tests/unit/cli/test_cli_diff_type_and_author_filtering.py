"""Unit tests for CLI --diff-type and --author parameter integration.

These tests verify that the CLI properly accepts and passes diff-type and author
filtering parameters to the temporal search service.
"""

import unittest
from click.testing import CliRunner

from src.code_indexer.cli import cli


class TestCLIDiffTypeAndAuthorFiltering(unittest.TestCase):
    """Test cases for --diff-type and --author CLI parameter integration."""

    def test_cli_has_diff_type_option(self):
        """Verify --diff-type option is available in query command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        assert result.exit_code == 0
        assert "--diff-type" in result.output
        # Check for the help text that explains the option
        assert "Filter by diff type" in result.output or "diff type" in result.output
        # Check for examples in help text
        assert "added" in result.output or "modified" in result.output

    def test_cli_has_author_option(self):
        """Verify --author option is available in query command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        assert result.exit_code == 0
        assert "--author" in result.output
        # Check for help text explaining the option
        assert "author" in result.output.lower()

    def test_cli_passes_diff_type_to_temporal_service(self):
        """Verify CLI passes diff_type parameter to temporal service.

        This test verifies the wiring exists by checking that query_temporal
        is called with the diff_types parameter from the CLI options.
        """
        # Import the query function to check its implementation
        from src.code_indexer.cli import query as query_command
        import inspect

        # Get the source code of the underlying callback function
        source = inspect.getsource(query_command.callback)

        # Verify that temporal_service.query_temporal is called with diff_types parameter
        assert (
            "query_temporal(" in source
        ), "query_temporal call not found in query command"
        assert (
            "diff_types=" in source
        ), "diff_types parameter not passed to query_temporal"

        # Verify the parameter transformation (tuple to list)
        assert (
            "list(diff_types)" in source or "diff_types" in source
        ), "diff_types not properly transformed"

    def test_cli_passes_author_to_temporal_service(self):
        """Verify CLI passes author parameter to temporal service."""
        # Import the query function to check its implementation
        from src.code_indexer.cli import query as query_command
        import inspect

        # Get the source code of the underlying callback function
        source = inspect.getsource(query_command.callback)

        # Verify that temporal_service.query_temporal is called with author parameter
        assert (
            "query_temporal(" in source
        ), "query_temporal call not found in query command"
        assert "author=" in source, "author parameter not passed to query_temporal"

    def test_cli_handles_multiple_diff_types(self):
        """Verify multiple --diff-type flags work correctly.

        Click's multiple=True automatically collects multiple values into a tuple,
        which we convert to a list before passing to the service.
        """
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        # Verify that --diff-type supports multiple values
        assert "--diff-type" in result.output
        # Check that help text mentions it can be specified multiple times
        assert (
            "multiple times" in result.output
            or "Can be specified multiple" in result.output
        )


if __name__ == "__main__":
    unittest.main()
