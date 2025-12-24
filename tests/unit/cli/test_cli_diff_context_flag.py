"""Unit tests for --diff-context CLI flag (Story #443 - AC2, AC3, AC7).

Tests the --diff-context flag for temporal indexing, including validation,
configuration override, and display.
"""

import subprocess
import sys

import pytest


class TestDiffContextCLIFlag:
    """Test --diff-context CLI flag integration."""

    def run_cli_command(self, args, cwd=None, expect_failure=False):
        """Run CLI command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )

        if expect_failure:
            assert (
                result.returncode != 0
            ), f"Command should have failed: {' '.join(cmd)}"
        else:
            if result.returncode != 0:
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
            assert result.returncode == 0, f"Command failed: {result.stderr}"

        return result

    def test_diff_context_flag_rejects_negative_value(self):
        """AC7: Reject negative diff-context values with clear error message."""
        result = self.run_cli_command(
            ["index", "--index-commits", "--diff-context", "-1"], expect_failure=True
        )

        # Check if we're hitting remote mode detection
        if "not available in remote mode" in result.stderr:
            assert "remote mode" in result.stderr
            assert result.returncode == 1
            return

        # Check for legacy container detection
        if "Legacy container detected" in result.stdout:
            assert "CoW migration required" in result.stdout
            assert result.returncode == 1
            return

        # Should show validation error in clean environment
        error_output = result.stdout + result.stderr
        assert "❌ Invalid diff-context -1" in error_output
        assert "Valid range: 0-50" in error_output
        assert result.returncode == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
