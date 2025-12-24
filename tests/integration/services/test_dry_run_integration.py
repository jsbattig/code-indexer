"""
Integration tests for dry-run functionality using shared containers.

Converted to use shared_container_test_environment for better performance.
These tests validate that the --dry-run-show-claude-prompt flag works correctly.
"""

import subprocess
import os
import pytest
from unittest.mock import patch
from click.testing import CliRunner

from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider
from src.code_indexer.cli import cli

# Mark tests as integration to exclude from ci-github.sh when needed
pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for integration tests (set VOYAGE_API_KEY environment variable)",
)
def test_shared_container_dry_run_simple_integration():
    """Test dry-run flag with shared containers to verify it shows prompt without executing Claude."""
    with shared_container_test_environment(
        "test_shared_container_dry_run_simple", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create a simple Python file to make it look like a real codebase
        (project_path / "main.py").write_text("print('hello world')")

        # Initialize with voyage-ai (containers should already be running)
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Ensure services are running (should be fast since containers are shared)
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Services should start successfully or already be running
        if start_result.returncode != 0:
            # Check if services are already running
            status_result = subprocess.run(
                ["code-indexer", "status"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if "✅" not in status_result.stdout:
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

        # Dry-run should work since services are available
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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for integration tests (set VOYAGE_API_KEY environment variable)",
)
def test_shared_container_normal_execution_differs_from_dry_run():
    """Test that normal execution attempts to actually run Claude (vs dry-run which doesn't)."""
    with shared_container_test_environment(
        "test_shared_container_normal_execution", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create a simple Python file to make it look like a real codebase
        (project_path / "main.py").write_text("print('hello world')")

        # Initialize the project for testing with voyage-ai (containers should already be running)
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Ensure services are running (should be fast since containers are shared)
        subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        runner = CliRunner()

        # Mock just the Claude dependency check
        with patch(
            "src.code_indexer.cli.check_claude_sdk_availability", return_value=True
        ):
            # Run the command WITHOUT dry-run flag
            result = runner.invoke(cli, ["claude", "Test question"])

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
            "services not available",  # Expected failure case when services aren't running
        ]

        found_execution = any(
            indicator in output_lower for indicator in execution_indicators
        )
        assert (
            found_execution
        ), f"Expected execution-related messages in normal mode. Got: {result.output[:1000]}"


if __name__ == "__main__":
    # Allow running this test standalone for quick validation
    test_shared_container_dry_run_simple_integration()
    test_shared_container_normal_execution_differs_from_dry_run()
    print("✅ All shared container dry-run integration tests passed!")
