"""E2E tests for unsupported commands in proxy mode (Story 2.4).

Tests that unsupported commands (init, index, reconcile, etc.) properly error
with clear messages and exit code 3 when attempted in proxy mode.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestUnsupportedCommandsE2E:
    """E2E tests for unsupported command handling in proxy mode."""

    @pytest.fixture
    def proxy_setup(self):
        """Create a proxy mode directory structure for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create proxy root config
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_data = {
                "codebase_dir": str(root),
                "proxy_mode": True,
                "discovered_repos": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            yield root

    def test_init_command_unsupported_in_proxy_mode(self, proxy_setup):
        """Test that 'init' command fails with proper error in proxy mode."""
        result = subprocess.run(
            ["cidx", "init"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should exit with code 3 (invalid command)
        assert result.returncode == 3

        # Error message should mention command not supported
        assert "init" in result.stderr.lower()
        assert (
            "not supported" in result.stderr.lower() or "error" in result.stderr.lower()
        )
        assert "proxy mode" in result.stderr.lower()

    def test_index_command_unsupported_in_proxy_mode(self, proxy_setup):
        """Test that 'index' command fails with proper error in proxy mode."""
        result = subprocess.run(
            ["cidx", "index"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should exit with code 3 (invalid command)
        assert result.returncode == 3

        # Error message should mention command not supported
        assert "index" in result.stderr.lower()
        assert (
            "not supported" in result.stderr.lower() or "error" in result.stderr.lower()
        )
        assert "proxy mode" in result.stderr.lower()

    def test_error_message_includes_supported_commands(self, proxy_setup):
        """Test that error message lists supported commands."""
        result = subprocess.run(
            ["cidx", "init"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should mention some supported commands
        error_output = result.stderr.lower()
        # At least some of the supported commands should be mentioned
        supported_mentions = sum(
            [
                "query" in error_output,
                "status" in error_output,
                "start" in error_output,
                "stop" in error_output,
                "uninstall" in error_output,
            ]
        )
        assert supported_mentions >= 3, "Error should list supported commands"

    def test_error_message_suggests_navigation(self, proxy_setup):
        """Test that error message suggests navigating to specific repository."""
        result = subprocess.run(
            ["cidx", "init"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should suggest using cd or navigating to repository
        assert "cd" in result.stderr or "navigate" in result.stderr.lower()

    def test_error_message_shows_how_to_run_command(self, proxy_setup):
        """Test that error message shows how to run the unsupported command."""
        result = subprocess.run(
            ["cidx", "init"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should show how to run 'cidx init' in specific repository
        assert "cidx init" in result.stderr

    def test_no_subprocess_execution_for_unsupported_commands(self, proxy_setup):
        """Test that unsupported commands don't attempt subprocess execution."""
        # This is tested indirectly - if validation happens early,
        # the command should fail quickly without trying to execute
        # across repositories

        result = subprocess.run(
            ["cidx", "init"],
            cwd=str(proxy_setup),
            capture_output=True,
            text=True,
            timeout=2,  # Should fail very quickly
        )

        # Should fail with exit code 3
        assert result.returncode == 3

        # Should not have any output about repository processing
        combined_output = result.stdout + result.stderr
        assert "[1/" not in combined_output  # No progress indicators
        assert "Processing" not in combined_output

    def test_multiple_unsupported_commands(self, proxy_setup):
        """Test various unsupported commands all fail appropriately."""
        unsupported = ["init", "index", "reconcile"]

        for command in unsupported:
            result = subprocess.run(
                ["cidx", command], cwd=str(proxy_setup), capture_output=True, text=True
            )

            # All should exit with code 3
            assert (
                result.returncode == 3
            ), f"Command '{command}' should exit with code 3"

            # All should mention the command and error
            assert command in result.stderr.lower()
            assert (
                "not supported" in result.stderr.lower()
                or "error" in result.stderr.lower()
            )

    def test_supported_commands_dont_trigger_error(self, proxy_setup):
        """Test that supported commands don't trigger unsupported command error."""
        # Note: These commands might fail for other reasons (no repos, etc.)
        # but should NOT fail with unsupported command error (exit code 3)

        # query is supported but will fail due to no repositories
        result = subprocess.run(
            ["cidx", "query", "test"],
            cwd=str(proxy_setup),
            capture_output=True,
            text=True,
        )

        # Should NOT be exit code 3 (unsupported command)
        # Will be 1 (failure) due to no repositories
        assert result.returncode != 3, "Supported command should not exit with code 3"

    def test_case_sensitive_command_validation(self, proxy_setup):
        """Test that command validation is case-sensitive."""
        # 'INIT' (uppercase) should be treated as unknown command
        # This may fail with different error than lowercase 'init'
        result = subprocess.run(
            ["cidx", "INIT"], cwd=str(proxy_setup), capture_output=True, text=True
        )

        # Should fail (either as unknown command or unsupported)
        assert result.returncode != 0
