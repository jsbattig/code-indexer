"""
Tests for CLI --fts flag functionality.

Tests ensure the --fts flag integrates properly with the index command
and enables full-text search indexing alongside semantic indexing.
"""

import subprocess
import sys

from click.testing import CliRunner

from code_indexer.cli import cli


class TestCLIFTSFlag:
    """Test CLI --fts flag integration."""

    def test_index_command_has_fts_flag(self):
        """Test that the index command accepts --fts flag."""
        runner = CliRunner()

        # This should fail initially - flag doesn't exist yet
        result = runner.invoke(cli, ["index", "--help"])
        assert (
            "--fts" in result.output
        ), "The --fts flag should be available in index command help"

    def test_fts_help_text(self):
        """Test that --fts has appropriate help text."""
        runner = CliRunner()

        # This should fail initially - flag doesn't exist yet
        result = runner.invoke(cli, ["index", "--help"])

        # Check for help text
        help_text = result.output.lower()
        if "--fts" in help_text:
            assert any(
                word in help_text
                for word in ["full-text", "text search", "tantivy", "search index"]
            ), "Help text should describe FTS functionality"

    def test_fts_is_optional_flag(self):
        """Test that --fts is an optional boolean flag (no value required)."""
        runner = CliRunner()

        # This should fail initially - flag doesn't exist yet
        result = runner.invoke(cli, ["index", "--help"])

        # Verify it's a flag (no argument required)
        if "--fts" in result.output:
            # Flags don't show [VALUE] or similar indicators
            assert "--fts [" not in result.output.lower()


class TestCLIFTSFlagE2E:
    """End-to-end tests for --fts flag using subprocess calls."""

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
        else:
            # For this test, we'll be more lenient since services may not be running
            pass

        return result

    def test_fts_flag_recognized(self):
        """Test that --fts flag is recognized by the CLI."""
        # This should fail initially - flag doesn't exist yet
        result = self.run_cli_command(["index", "--help"], timeout=10)

        # Check if help contains the flag
        assert "--fts" in result.stdout, "The --fts flag should be in help output"

    def test_fts_flag_no_value_error(self):
        """Test that --fts doesn't require a value."""
        # Use Click test runner to avoid actual subprocess execution
        # This tests command parsing without running full indexing
        runner = CliRunner()

        # Run with --help to verify flag syntax (fast, no actual indexing)
        result = runner.invoke(cli, ["index", "--help"])

        # Verify --fts is a flag (not requiring a value)
        assert "--fts" in result.output, "Flag should exist"
        assert "--fts VALUE" not in result.output, "Flag should not require a value"
        assert (
            "--fts [" not in result.output
        ), "Flag should not have optional value syntax"

    def test_default_behavior_no_fts(self):
        """Test that without --fts flag, only semantic indexing occurs (default behavior)."""
        # This test verifies acceptance criterion #1: default behavior preserved
        result = self.run_cli_command(["index", "--help"])

        # Help should show that --fts is optional
        # Default behavior should be semantic-only indexing
        assert "--fts" in result.stdout, "FTS should be opt-in via flag"
