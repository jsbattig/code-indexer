"""Unit tests for temporal git history indexing bug fixes.

Bug 1: Confirmation prompt blocks batch usage
Bug 2: UTF-8 decode error on binary/non-UTF-8 files

Following strict TDD methodology - red-green-refactor.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from src.code_indexer.cli import cli
from src.code_indexer.services.temporal.temporal_diff_scanner import (
    TemporalDiffScanner,
)


class TestTemporalConfirmationPromptBug:
    """Test suite for Bug 1: Confirmation prompt blocks batch usage."""

    @patch("click.confirm")
    @patch("src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer")
    @patch("subprocess.run")
    def test_all_branches_flag_does_not_prompt_for_confirmation(
        self,
        mock_subprocess_run,
        mock_temporal_indexer,
        mock_confirm,
    ):
        """Test that --all-branches flag proceeds without confirmation prompt.

        REQUIREMENT: Remove confirmation prompt entirely - just proceed with indexing.
        This test verifies that click.confirm is NEVER called when --index-commits
        is used with --all-branches flag.
        """
        runner = CliRunner()

        # Mock indexer instance
        mock_indexer_instance = MagicMock()
        mock_indexer_instance.index_temporal_history.return_value = None
        mock_temporal_indexer.return_value = mock_indexer_instance

        with runner.isolated_filesystem():
            # Create test repo structure
            test_repo = Path.cwd()
            (test_repo / ".code-indexer").mkdir(exist_ok=True)
            (test_repo / ".code-indexer" / "config.json").write_text(
                '{"codebase_dir": "' + str(test_repo) + '"}'
            )
            (test_repo / ".git").mkdir(exist_ok=True)

            # Mock git branch to return many branches (>50) to trigger warning path
            mock_subprocess_run.return_value = MagicMock(
                stdout="\n".join([f"  branch-{i}" for i in range(60)]),
                returncode=0,
            )

            # Run command with --index-commits and --all-branches
            result = runner.invoke(
                cli,
                ["index", "--index-commits", "--all-branches"],
                catch_exceptions=False,
            )

            # CRITICAL ASSERTION: click.confirm should NEVER be called
            # even when branch count > 50
            mock_confirm.assert_not_called()

            # Command should succeed (or at least not exit due to confirmation)
            # May fail for other reasons but NOT due to user cancellation
            assert "Cancelled" not in result.output

    @patch("click.confirm")
    @patch("src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer")
    @patch("subprocess.run")
    def test_all_branches_without_flag_also_does_not_prompt(
        self,
        mock_subprocess_run,
        mock_temporal_indexer,
        mock_confirm,
    ):
        """Test that even without --all-branches, no confirmation is needed.

        REQUIREMENT: Remove confirmation entirely - applies to all temporal indexing.
        """
        runner = CliRunner()

        # Mock indexer instance
        mock_indexer_instance = MagicMock()
        mock_indexer_instance.index_temporal_history.return_value = None
        mock_temporal_indexer.return_value = mock_indexer_instance

        with runner.isolated_filesystem():
            # Create test repo structure
            test_repo = Path.cwd()
            (test_repo / ".code-indexer").mkdir(exist_ok=True)
            (test_repo / ".code-indexer" / "config.json").write_text(
                '{"codebase_dir": "' + str(test_repo) + '"}'
            )
            (test_repo / ".git").mkdir(exist_ok=True)

            # Mock git commands (single branch, won't trigger warning)
            mock_subprocess_run.return_value = MagicMock(
                stdout="master\n",
                returncode=0,
            )

            # Run command with --index-commits (no --all-branches)
            result = runner.invoke(
                cli,
                ["index", "--index-commits"],
                catch_exceptions=False,
            )

            # CRITICAL ASSERTION: click.confirm should NEVER be called
            mock_confirm.assert_not_called()

            # Command should succeed
            assert "Cancelled" not in result.output


class TestTemporalUTF8DecodeBug:
    """Test suite for Bug 2: UTF-8 decode error on binary/non-UTF-8 files."""

    def test_subprocess_run_with_errors_parameter(self):
        """Test that subprocess.run is called with errors parameter for UTF-8 handling.

        REQUIREMENT: Use errors='replace' or 'ignore' in subprocess.run calls
        to prevent UnicodeDecodeError on binary/non-UTF-8 content.

        This is a WHITE BOX test that verifies the implementation uses the correct
        subprocess.run parameters in ALL temporal service files.
        """
        import re

        # All temporal service files that use subprocess.run with text=True
        temporal_files = [
            "temporal_diff_scanner.py",
            "temporal_indexer.py",
            "temporal_search_service.py",
        ]

        for filename in temporal_files:
            # Read the source file
            file_path = (
                Path(__file__).parent.parent.parent.parent
                / "src"
                / "code_indexer"
                / "services"
                / "temporal"
                / filename
            )
            source_code = file_path.read_text()

            # Find all subprocess.run calls with text=True
            text_true_calls = re.findall(
                r"subprocess\.run\([^)]*text=True[^)]*\)", source_code, re.DOTALL
            )

            # Every subprocess.run with text=True MUST have errors='replace' or errors='ignore'
            for subprocess_call in text_true_calls:
                assert (
                    "errors=" in subprocess_call
                ), f"{filename}: subprocess.run with text=True must include errors parameter:\n{subprocess_call}"

    @patch("subprocess.run")
    def test_deleted_file_with_non_utf8_content(self, mock_run):
        """Test deleted files with non-UTF-8 content are handled gracefully.

        Bug reproduction: git show parent:file on a file with byte 0xae causes
        UnicodeDecodeError when text=True without errors parameter.
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Simulate the actual error scenario from the bug report
        # When text=True without errors, subprocess would raise:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xae in position 96
        # But with errors='replace', it should work

        # First call: get changed files
        # Second call: git show parent:file - returns content with bad bytes
        # With errors='replace', bad bytes become \ufffd
        mock_run.side_effect = [
            MagicMock(stdout="D\tsome_file.txt\n", stderr="", returncode=0),
            MagicMock(
                stdout="text before bad byte: \ufffd text after",
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="abcd1234", stderr="", returncode=0),  # blob hash
            MagicMock(stdout="parent123", stderr="", returncode=0),  # parent commit
        ]

        # Should not raise UnicodeDecodeError
        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 1
        assert diffs[0].file_path == "some_file.txt"

    @patch("subprocess.run")
    def test_modified_file_with_non_utf8_content(self, mock_run):
        """Test modified files with non-UTF-8 content are handled gracefully.

        Lines 139-142: git show commit -- file_path can fail on non-UTF-8 files.
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        mock_run.side_effect = [
            MagicMock(stdout="M\tsome_file.txt\n", stderr="", returncode=0),
            MagicMock(
                stdout="@@ -1,2 +1,2 @@\n-old\n+new with bad byte: \ufffd",
                stderr="",
                returncode=0,
            ),
            MagicMock(stdout="efgh5678", stderr="", returncode=0),  # blob hash
        ]

        # Should not raise UnicodeDecodeError
        diffs = scanner.get_diffs_for_commit("def456")

        assert len(diffs) == 1
        assert diffs[0].file_path == "some_file.txt"
        assert diffs[0].diff_type == "modified"
