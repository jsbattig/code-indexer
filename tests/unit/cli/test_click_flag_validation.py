"""
Tests for Click flag validation in CLI commands.

This test suite validates that unknown flags are properly rejected,
preventing silent failures where typos or invalid flags are ignored.

BUG CONTEXT:
When running 'cidx query "test" --non-existent-flag' in daemon mode, the system
silently ignores the unknown flag instead of raising an error. This is dangerous
because users might make typos and not realize their flag is being ignored.

ROOT CAUSE:
The cli_daemon_fast.parse_query_args() function (line 85) silently skips unknown
flags with comment "# Skip other flags for now". This bypasses Click's argument
validation entirely when using the fast daemon delegation path.

EXPECTED BEHAVIOR:
Unknown flags should raise an error with clear message, regardless of whether
running in daemon mode or standalone mode.
"""

import pytest
from code_indexer.cli_daemon_fast import parse_query_args


class TestClickFlagValidation:
    """Test suite for flag validation in CLI commands."""

    def test_parse_query_args_rejects_unknown_flag(self):
        """
        Test that parse_query_args() rejects unknown flags.

        THIS TEST DEMONSTRATES THE BUG - parse_query_args() silently skips
        unknown flags instead of raising an error.

        EXPECTED: Should raise ValueError or similar for unknown flag
        ACTUAL: Silently ignores the flag
        """
        args = ["test", "--non-existent-flag"]

        # Should raise an error for unknown flag
        with pytest.raises(ValueError, match="Unknown flag|unknown option"):
            parse_query_args(args)

    def test_execute_via_daemon_handles_unknown_flag_gracefully(self, tmp_path):
        """
        Test that execute_via_daemon() provides user-friendly error for unknown flags.

        Validates that when parse_query_args() raises ValueError for unknown flags,
        the error is caught and presented to the user in a helpful way.

        EXPECTED: Exit code 2 with clear error message (no exception, no daemon connection)
        """
        from code_indexer.cli_daemon_fast import execute_via_daemon

        # Create config to enable daemon mode
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text('{"daemon": {"enabled": true}}')

        # Simulate CLI args with unknown flag
        argv = ["cidx", "query", "test", "--non-existent-flag"]

        # Should return exit code 2 without attempting daemon connection
        exit_code = execute_via_daemon(argv, config_file)

        # Should return usage error exit code (2, matching Click's behavior)
        assert exit_code == 2, f"Expected exit code 2 for usage error, got {exit_code}"
