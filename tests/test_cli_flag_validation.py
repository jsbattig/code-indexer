"""
Tests for CLI flag validation functionality.

Tests ensure proper flag combinations are allowed/disallowed
and that appropriate error messages are displayed to users.
"""

import subprocess
import sys
from pathlib import Path

import pytest


class TestCLIFlagValidation:
    """Test CLI flag combination validation."""

    def run_cli_command(self, args, expect_failure=False):
        """Run CLI command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if expect_failure:
            assert (
                result.returncode != 0
            ), f"Command should have failed: {' '.join(cmd)}"
        else:
            assert result.returncode == 0, f"Command failed: {result.stderr}"

        return result

    def test_detect_deletions_with_reconcile_error(self):
        """Test that --detect-deletions with --reconcile shows error and exits."""
        result = self.run_cli_command(
            ["index", "--detect-deletions", "--reconcile"], expect_failure=True
        )

        # Should show error message
        assert "❌ Cannot use --detect-deletions with --reconcile" in result.stdout
        assert (
            "💡 --reconcile mode includes deletion detection automatically"
            in result.stdout
        )

        # Should exit with non-zero code
        assert result.returncode == 1

    def test_detect_deletions_with_clear_warning(self, tmp_path):
        """Test that --detect-deletions with --clear shows warning but continues."""
        # Create a minimal test directory
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()
        test_file = test_dir / "test.py"
        test_file.write_text("print('hello')")

        # Change to test directory
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(test_dir)

            # This should show warning but then may fail due to missing services
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "code_indexer.cli",
                    "index",
                    "--detect-deletions",
                    "--clear",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should show warning message
            assert (
                "⚠️  Warning: --detect-deletions is redundant with --clear"
                in result.stdout
            )
            assert "💡 --clear empties the collection completely" in result.stdout

            # Command may fail due to missing services, but flag validation should pass
            if result.returncode != 0:
                # Acceptable failures are service-related, not flag validation
                acceptable_errors = [
                    "No configuration found",
                    "Services not running",
                    "Connection refused",
                    "Failed to connect",
                    "Qdrant",
                    "Ollama service not available",
                ]
                error_output = result.stderr + result.stdout
                assert any(
                    error in error_output for error in acceptable_errors
                ), f"Unexpected error (should be service-related): {error_output}"

        finally:
            os.chdir(original_cwd)

    def test_detect_deletions_alone_valid(self, tmp_path):
        """Test that --detect-deletions alone is valid."""
        # Create a minimal test directory
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()
        test_file = test_dir / "test.py"
        test_file.write_text("print('hello')")

        # Change to test directory
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(test_dir)

            # This should work (though may fail due to services not running)
            # We're only testing flag validation, not full functionality
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "code_indexer.cli",
                    "index",
                    "--detect-deletions",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should not show flag validation errors
            assert (
                "❌ Cannot use --detect-deletions with --reconcile" not in result.stdout
            )
            assert (
                "⚠️  Warning: --detect-deletions is redundant with --clear"
                not in result.stdout
            )

            # The command might fail due to missing services, but not due to flag validation
            if result.returncode != 0:
                # Acceptable failures are service-related, not flag validation
                acceptable_errors = [
                    "No configuration found",
                    "Services not running",
                    "Connection refused",
                    "Failed to connect",
                    "Qdrant",
                    "Ollama service not available",
                ]
                error_output = result.stderr + result.stdout
                assert any(
                    error in error_output for error in acceptable_errors
                ), f"Unexpected error (should be service-related): {error_output}"

        finally:
            os.chdir(original_cwd)

    def test_reconcile_alone_valid(self, tmp_path):
        """Test that --reconcile alone is valid (includes deletion detection)."""
        # Create a minimal test directory
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()
        test_file = test_dir / "test.py"
        test_file.write_text("print('hello')")

        # Change to test directory
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(test_dir)

            # This should work (though may fail due to services not running)
            result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "index", "--reconcile"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should not show flag validation errors
            assert (
                "❌ Cannot use --detect-deletions with --reconcile" not in result.stdout
            )

            # The command might fail due to missing services, but not due to flag validation
            if result.returncode != 0:
                # Acceptable failures are service-related, not flag validation
                acceptable_errors = [
                    "No configuration found",
                    "Services not running",
                    "Connection refused",
                    "Failed to connect",
                    "Qdrant",
                    "Ollama service not available",
                ]
                error_output = result.stderr + result.stdout
                assert any(
                    error in error_output for error in acceptable_errors
                ), f"Unexpected error (should be service-related): {error_output}"

        finally:
            os.chdir(original_cwd)

    def test_help_includes_deletion_detection_section(self):
        """Test that help text includes DELETION DETECTION section."""
        result = self.run_cli_command(["index", "--help"])

        # Should include deletion detection documentation
        help_text = result.stdout
        assert "DELETION DETECTION" in help_text
        assert "--detect-deletions" in help_text
        assert "Detect and handle files deleted from" in help_text

        # Should explain when to use it
        assert "NOT needed with --reconcile" in help_text
        assert "NOT useful with --clear" in help_text
        assert "soft delete" in help_text
        assert "hard delete" in help_text

    def test_multiple_invalid_combinations(self):
        """Test multiple invalid flag combinations at once."""
        # Test --detect-deletions --reconcile --clear (should fail on the first invalid combo)
        result = self.run_cli_command(
            ["index", "--detect-deletions", "--reconcile", "--clear"],
            expect_failure=True,
        )

        # Should fail with reconcile error (first validation check)
        assert "❌ Cannot use --detect-deletions with --reconcile" in result.stdout
        assert result.returncode == 1

    def test_flag_order_independence(self):
        """Test that flag validation works regardless of flag order."""
        # Test with flags in different order
        result = self.run_cli_command(
            ["index", "--reconcile", "--detect-deletions"], expect_failure=True
        )

        # Should still catch the invalid combination
        assert "❌ Cannot use --detect-deletions with --reconcile" in result.stdout
        assert result.returncode == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
