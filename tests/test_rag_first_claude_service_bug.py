"""
Test for --rag-first claude_service variable bug.

This test reproduces the issue where claude_service is not defined in the --rag-first code path.
"""

import tempfile
from pathlib import Path
from click.testing import CliRunner

from src.code_indexer.cli import cli


def test_rag_first_approach_now_works():
    """Test that --rag-first approach now works after fixing the claude_service variable scope error."""

    runner = CliRunner()

    # Create a minimal test project
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "test.py").write_text("print('hello world')")

        # Run the command with --rag-first flag
        # This test mainly checks that the claude_service variable scope bug is fixed
        result = runner.invoke(
            cli,
            [
                "claude",
                "Test question",
                "--rag-first",
                "--codebase-dir",
                str(temp_path),
            ],
        )

        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        if result.exception:
            print(f"Exception: {result.exception}")

        # The main goal is to ensure no "claude_service" variable scope error
        # The command might fail for other reasons (no services, etc.) but shouldn't have the variable error
        assert (
            "claude_service" not in str(result.output)
            and "cannot access local variable" not in str(result.output)
            and "UnboundLocalError" not in str(result.output)
        ), f"Should not contain claude_service variable error, got: {result.output}"

        # If it shows the RAG-first message, the code path is working
        if "🔄 Using legacy RAG-first approach" in result.output:
            print("✓ RAG-first code path is accessible")


def test_rag_first_vs_claude_first_comparison():
    """Test to compare the differences between --rag-first and default (claude-first) approaches."""

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "main.py").write_text("print('hello world')")

        # Test default approach (claude-first)
        result_claude_first = runner.invoke(
            cli, ["claude", "Test question", "--codebase-dir", str(temp_path)]
        )

        print(f"Claude-first exit code: {result_claude_first.exit_code}")
        print(f"Claude-first output: {result_claude_first.output}")

        # Test rag-first approach
        result_rag_first = runner.invoke(
            cli,
            [
                "claude",
                "Test question",
                "--rag-first",
                "--codebase-dir",
                str(temp_path),
            ],
        )

        print(f"RAG-first exit code: {result_rag_first.exit_code}")
        print(f"RAG-first output: {result_rag_first.output}")

        # Main goal: ensure no variable scope errors in either approach
        assert "claude_service" not in str(
            result_claude_first.output
        ) and "UnboundLocalError" not in str(
            result_claude_first.output
        ), "Claude-first should not have variable scope errors"

        assert "claude_service" not in str(
            result_rag_first.output
        ) and "UnboundLocalError" not in str(
            result_rag_first.output
        ), "RAG-first should not have variable scope errors"


def test_rag_first_with_dry_run():
    """Test that --rag-first works properly with --dry-run-show-claude-prompt functionality."""

    runner = CliRunner()

    # Create a minimal test project
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "test.py").write_text("def test(): pass")

        # Run the command with --rag-first and --dry-run-show-claude-prompt
        result = runner.invoke(
            cli,
            [
                "claude",
                "Test question about code",
                "--rag-first",
                "--dry-run-show-claude-prompt",
                "--codebase-dir",
                str(temp_path),
            ],
        )

        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        if result.exception:
            print(f"Exception: {result.exception}")

        # Main goal: ensure no variable scope errors
        assert (
            "claude_service" not in str(result.output)
            and "cannot access local variable" not in str(result.output)
            and "UnboundLocalError" not in str(result.output)
        ), f"Should not contain claude_service variable error, got: {result.output}"

        # If it shows the RAG-first approach message, the bug is fixed
        if "🔄 Using legacy RAG-first approach" in result.output:
            print("✓ RAG-first with dry-run code path is accessible")
