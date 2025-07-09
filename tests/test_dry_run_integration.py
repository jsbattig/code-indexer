"""
Simple integration test for dry-run functionality.

This test validates that the --dry-run-show-claude-prompt flag works correctly.
"""

from .conftest import local_temporary_directory

from click.testing import CliRunner
import subprocess
import os
from pathlib import Path
from unittest.mock import patch

from src.code_indexer.cli import cli


def test_dry_run_simple_integration():
    """Test dry-run flag with services setup to verify it shows prompt without executing Claude."""

    # Create a temporary directory structure that would be a valid codebase
    with local_temporary_directory() as temp_dir:
        temp_path = Path(temp_dir)
        # Safely get current working directory
        try:
            original_cwd = os.getcwd()
        except FileNotFoundError:
            # If current directory was deleted, use a safe fallback
            original_cwd = str(Path.home())

        try:
            # Create a simple Python file to make it look like a real codebase
            (temp_path / "main.py").write_text("print('hello world')")

            # Change to the test directory
            os.chdir(temp_path)

            # Initialize with voyage-ai to avoid service dependencies
            init_result = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=temp_path,
            )

            # If init fails, that's a setup issue
            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

            # Ensure services are running (VoyageAI + Qdrant)
            start_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "start", "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,  # Give more time for service startup
                cwd=temp_path,
            )

            # Services should start successfully or we need to handle it
            if start_result.returncode != 0:
                # Check if services are already running
                status_result = subprocess.run(
                    ["python", "-m", "code_indexer.cli", "status"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_path,
                )
                if "✅" not in status_result.stdout:
                    # If services can't start and aren't running, we need to handle this
                    # For integration tests in full-automation.sh, services should be manageable
                    assert (
                        False
                    ), f"Cannot start services for integration test: {start_result.stderr}"

            runner = CliRunner()

            # Mock just the Claude dependency check since dry-run shouldn't need Claude installed
            with patch(
                "src.code_indexer.cli.check_claude_sdk_availability", return_value=True
            ):
                result = runner.invoke(
                    cli,
                    ["claude", "Test question", "--dry-run-show-claude-prompt"],
                    catch_exceptions=False,
                )

        finally:
            # Always restore original directory
            os.chdir(original_cwd)

        # Now dry-run should work since services are available
        assert (
            result.exit_code == 0
        ), f"Dry-run should succeed with services available. Output: {result.output}"

        output_lower = result.output.lower()

        # Verify it shows dry-run behavior (prompt but no actual execution)
        good_indicators = [
            "generating claude prompt",
            "generated claude prompt",
            "this is the prompt that would be sent",
        ]

        found_good = any(indicator in output_lower for indicator in good_indicators)
        assert (
            found_good
        ), f"Expected to find prompt-related messages in output. Got: {result.output}"

        # Should NOT show execution results (since it's dry-run)
        bad_indicators = [
            "claude analysis results",
            "analysis summary",
            "tool_usage_summary",
        ]

        for bad_indicator in bad_indicators:
            assert (
                bad_indicator not in output_lower
            ), f"Found '{bad_indicator}' suggesting actual execution happened"

        # Should show the actual prompt content
        assert "test question" in output_lower, "Should show our specific test question"


def test_normal_execution_differs_from_dry_run():
    """Test that normal execution attempts to actually run Claude (vs dry-run which doesn't)."""

    # Create a temporary directory structure that would be a valid codebase
    with local_temporary_directory() as temp_dir:
        temp_path = Path(temp_dir)
        # Safely get current working directory
        try:
            original_cwd = os.getcwd()
        except FileNotFoundError:
            # If current directory was deleted, use a safe fallback
            original_cwd = str(Path.home())

        try:
            # Create a simple Python file to make it look like a real codebase
            (temp_path / "main.py").write_text("print('hello world')")

            # Change to the test directory
            os.chdir(temp_path)

            # Initialize the project for testing with voyage-ai
            init_result = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=temp_path,
            )

            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

            # Ensure services are running
            subprocess.run(
                ["python", "-m", "code_indexer.cli", "start", "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=temp_path,
            )

            runner = CliRunner()

            # Mock just the Claude dependency check
            with patch(
                "src.code_indexer.cli.check_claude_sdk_availability", return_value=True
            ):
                # Run the command WITHOUT dry-run flag
                result = runner.invoke(cli, ["claude", "Test question"])

        finally:
            # Always restore original directory
            os.chdir(original_cwd)

        # Normal execution will either:
        # 1. Try to execute Claude (and may fail due to no Claude installed, but that's expected)
        # 2. Succeed if Claude is available
        # Either way, it should NOT show dry-run messages

        output_lower = result.output.lower()

        # Should NOT see dry-run specific messages
        dry_run_indicators = [
            "generating claude prompt",
            "this is the prompt that would be sent",
            "use without --dry-run-show-claude-prompt",
        ]

        for dry_run_indicator in dry_run_indicators:
            assert (
                dry_run_indicator not in output_lower
            ), f"Found dry-run message '{dry_run_indicator}' in normal execution"

        # Should see either Claude results or service errors or Claude CLI errors (all indicate actual execution was attempted)
        execution_indicators = [
            "claude analysis results",  # Success case
            "analysis summary",  # Success case
            "claude cli not available",  # Expected failure case
            "claude analysis failed",  # Expected failure case
        ]

        found_execution = any(
            indicator in output_lower for indicator in execution_indicators
        )
        assert (
            found_execution
        ), f"Expected execution-related messages in normal mode. Got: {result.output[:1000]}"


if __name__ == "__main__":
    # Allow running this test standalone for quick validation
    test_dry_run_simple_integration()
    test_normal_execution_differs_from_dry_run()
    print("✅ All dry-run integration tests passed!")
