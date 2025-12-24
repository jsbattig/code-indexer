"""Unit tests for --chunk-type CLI flag validation (Story #476 AC5).

Tests that --chunk-type requires --time-range or --time-range-all.
"""

from click.testing import CliRunner
from unittest.mock import patch
from pathlib import Path

from src.code_indexer.cli import cli


class TestChunkTypeValidation:
    """Test AC5: chunk-type filter requires temporal flags."""

    def test_chunk_type_without_temporal_flags_shows_error(self):
        """Test that --chunk-type without temporal flags displays error and exits."""
        runner = CliRunner()

        # Mock find_project_root to return a valid Path (not string)
        with patch("src.code_indexer.cli.find_project_root") as mock_find_root:
            mock_find_root.return_value = Path("/tmp/test-project")

            # Act: Run query with --chunk-type but no temporal flags
            result = runner.invoke(
                cli, ["query", "test query", "--chunk-type", "commit_message"]
            )

            # Assert: Should exit with error
            # Print full result for debugging
            if result.exception:
                import traceback

                print("\n=== Exception ===")
                print(
                    "".join(
                        traceback.format_exception(
                            type(result.exception),
                            result.exception,
                            result.exception.__traceback__,
                        )
                    )
                )
            print(f"\n=== Exit code: {result.exit_code} ===")
            print(f"\n=== Output: {result.output} ===")

            assert (
                result.exit_code != 0
            ), "Expected non-zero exit code for invalid flag combination"
            assert (
                "--chunk-type requires --time-range or --time-range-all"
                in result.output
            ), f"Expected error message about missing temporal flags. Got: {result.output}"
