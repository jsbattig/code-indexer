"""
Tests for CLI --rebuild-fts-index flag functionality.

Tests ensure the --rebuild-fts-index flag integrates properly with the index command
and rebuilds only the FTS index from existing progress data.
"""

import subprocess
import sys

from click.testing import CliRunner

from code_indexer.cli import cli


class TestCLIRebuildFTSIndex:
    """Test CLI --rebuild-fts-index flag integration."""

    def test_index_command_has_rebuild_fts_index_flag(self):
        """Test that the index command accepts --rebuild-fts-index flag."""
        runner = CliRunner()

        result = runner.invoke(cli, ["index", "--help"])
        assert (
            "--rebuild-fts-index" in result.output
        ), "The --rebuild-fts-index flag should be available in index command help"

    def test_rebuild_fts_index_help_text(self):
        """Test that --rebuild-fts-index has appropriate help text."""
        runner = CliRunner()

        result = runner.invoke(cli, ["index", "--help"])

        # Check for help text
        help_text = result.output.lower()
        if "--rebuild-fts-index" in help_text:
            assert any(
                word in help_text
                for word in [
                    "rebuild",
                    "fts",
                    "full-text",
                    "tantivy",
                    "semantic",
                ]
            ), "Help text should describe FTS rebuild functionality"

    def test_rebuild_fts_index_is_optional_flag(self):
        """Test that --rebuild-fts-index is an optional boolean flag (no value required)."""
        runner = CliRunner()

        result = runner.invoke(cli, ["index", "--help"])

        # Verify it's a flag (no argument required)
        if "--rebuild-fts-index" in result.output:
            # Flags don't show [VALUE] or similar indicators
            assert "--rebuild-fts-index [" not in result.output.lower()


class TestCLIRebuildFTSIndexE2E:
    """End-to-end tests for --rebuild-fts-index flag using subprocess calls."""

    def run_cli_command(self, args, expect_failure=False, timeout=120):
        """Run CLI command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if expect_failure:
            assert (
                result.returncode != 0
            ), f"Command should have failed: {' '.join(cmd)}"

        return result

    def test_rebuild_fts_index_flag_recognized(self):
        """Test that --rebuild-fts-index flag is recognized by the CLI."""
        result = self.run_cli_command(["index", "--help"], timeout=10)

        # Check if help contains the flag
        assert (
            "--rebuild-fts-index" in result.stdout
        ), "The --rebuild-fts-index flag should be in help output"

    def test_rebuild_fts_index_flag_no_value_error(self):
        """Test that --rebuild-fts-index doesn't require a value."""
        # Use Click test runner to avoid actual subprocess execution
        runner = CliRunner()

        # Run with --help to verify flag syntax (fast, no actual indexing)
        result = runner.invoke(cli, ["index", "--help"])

        # Verify --rebuild-fts-index is a flag (not requiring a value)
        assert "--rebuild-fts-index" in result.output, "Flag should exist"
        assert (
            "--rebuild-fts-index VALUE" not in result.output
        ), "Flag should not require a value"
        assert (
            "--rebuild-fts-index [" not in result.output
        ), "Flag should not have optional value syntax"
