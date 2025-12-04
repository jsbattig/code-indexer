"""
Comprehensive tests for catch-up processing of fallback READMEs.

Tests cover:
- Scanning for fallback README files (*_README.md)
- Batch processing with Claude CLI generation
- Stopping on CLI failure mid-batch
- Single commit and re-index after all swaps
- Triggering catch-up on first successful CLI run
"""

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch


from code_indexer.server.services.claude_cli_manager import (
    ClaudeCliManager,
)


class TestScanForFallbacks:
    """Test scanning for fallback README files."""

    def test_scan_finds_all_fallback_files(self):
        """AC1: scan_for_fallbacks() finds all *_README.md files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)

            # Create fallback files
            (meta_dir / "repo1_README.md").write_text("Fallback 1")
            (meta_dir / "repo2_README.md").write_text("Fallback 2")
            (meta_dir / "code-indexer_README.md").write_text("Fallback 3")

            # Create non-fallback files (should be ignored)
            (meta_dir / "repo1.md").write_text("Regular file")
            (meta_dir / "README.md").write_text("README")

            manager = ClaudeCliManager(api_key="test-key", max_workers=1)
            manager.set_meta_dir(meta_dir)

            fallbacks = manager.scan_for_fallbacks()

            # Should find exactly 3 fallback files
            assert len(fallbacks) == 3

            # Extract aliases
            aliases = {alias for alias, _ in fallbacks}
            assert aliases == {"repo1", "repo2", "code-indexer"}

            manager.shutdown()

    def test_scan_extracts_alias_from_filename(self):
        """AC1: Extract repo alias from filename (<alias>_README.md -> alias)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)

            # Create fallback with hyphenated name
            fallback_path = meta_dir / "my-repo-name_README.md"
            fallback_path.write_text("Fallback")

            manager = ClaudeCliManager(api_key="test-key", max_workers=1)
            manager.set_meta_dir(meta_dir)

            fallbacks = manager.scan_for_fallbacks()

            assert len(fallbacks) == 1
            alias, path = fallbacks[0]
            assert alias == "my-repo-name"
            assert path == fallback_path

            manager.shutdown()

    def test_scan_returns_empty_when_no_fallbacks(self):
        """AC1: scan_for_fallbacks() returns empty list when no fallbacks exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)

            # Create only non-fallback files
            (meta_dir / "repo1.md").write_text("Regular file")
            (meta_dir / "repo2.md").write_text("Regular file")

            manager = ClaudeCliManager(api_key="test-key", max_workers=1)
            manager.set_meta_dir(meta_dir)

            fallbacks = manager.scan_for_fallbacks()

            assert fallbacks == []

            manager.shutdown()

    def test_scan_handles_nonexistent_meta_dir(self):
        """AC1: scan_for_fallbacks() handles nonexistent meta directory gracefully."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)
        manager.set_meta_dir(Path("/nonexistent/directory"))

        fallbacks = manager.scan_for_fallbacks()

        assert fallbacks == []

        manager.shutdown()

    def test_scan_handles_meta_dir_not_set(self):
        """AC1: scan_for_fallbacks() handles meta_dir not being set."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)
        # Don't call set_meta_dir()

        fallbacks = manager.scan_for_fallbacks()

        assert fallbacks == []

        manager.shutdown()


class TestProcessAllFallbacks:
    """Tests for AC2-AC4: Process fallbacks and commit."""

    @patch.object(ClaudeCliManager, "check_cli_available", return_value=False)
    def test_returns_partial_when_cli_unavailable(self, mock_cli):
        """AC2: process_all_fallbacks() returns partial result when CLI unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            (meta_dir / "repo1_README.md").write_text("content")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            result = manager.process_all_fallbacks()
            manager.shutdown()

            assert result.partial is True
            assert result.error == "CLI not available"
            assert "repo1" in result.remaining
            assert result.processed == []

    @patch.object(ClaudeCliManager, "check_cli_available", return_value=True)
    @patch.object(ClaudeCliManager, "sync_api_key")
    @patch.object(ClaudeCliManager, "_commit_and_reindex")
    def test_processes_all_fallbacks_successfully(
        self, mock_commit, mock_sync, mock_cli
    ):
        """AC3: process_all_fallbacks() processes all fallbacks and calls commit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            (meta_dir / "repo1_README.md").write_text("content1")
            (meta_dir / "repo2_README.md").write_text("content2")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            result = manager.process_all_fallbacks()
            manager.shutdown()

            assert result.partial is False
            assert len(result.processed) == 2
            assert result.remaining == []
            assert (meta_dir / "repo1.md").exists()
            assert (meta_dir / "repo2.md").exists()
            assert not (meta_dir / "repo1_README.md").exists()
            assert not (meta_dir / "repo2_README.md").exists()
            mock_commit.assert_called_once()

    @patch.object(ClaudeCliManager, "check_cli_available", return_value=True)
    def test_returns_empty_when_no_fallbacks(self, mock_cli):
        """AC2: process_all_fallbacks() returns empty result when no fallbacks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            result = manager.process_all_fallbacks()
            manager.shutdown()

            assert result.partial is False
            assert result.processed == []
            assert result.remaining == []

    @patch.object(ClaudeCliManager, "check_cli_available", return_value=True)
    @patch.object(ClaudeCliManager, "sync_api_key")
    @patch.object(ClaudeCliManager, "_process_single_fallback", return_value=False)
    def test_stops_on_cli_failure_mid_batch(self, mock_process, mock_sync, mock_cli):
        """AC4: process_all_fallbacks() stops on first CLI failure, returns partial."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            (meta_dir / "repo1_README.md").write_text("content1")
            (meta_dir / "repo2_README.md").write_text("content2")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            result = manager.process_all_fallbacks()
            manager.shutdown()

            assert result.partial is True
            assert result.error == "CLI failed for repo1"
            assert result.processed == []
            assert len(result.remaining) == 2


class TestProcessSingleFallback:
    """Tests for single fallback processing."""

    @patch.object(ClaudeCliManager, "sync_api_key")
    def test_renames_fallback_to_generated(self, mock_sync):
        """AC3: _process_single_fallback() renames fallback to generated filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            fallback = meta_dir / "test-repo_README.md"
            fallback.write_text("original content")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            result = manager._process_single_fallback("test-repo", fallback)
            manager.shutdown()

            assert result is True
            assert not fallback.exists()
            assert (meta_dir / "test-repo.md").exists()

    def test_returns_false_when_no_meta_dir(self):
        """AC3: _process_single_fallback() returns False when meta_dir not set."""
        manager = ClaudeCliManager(max_workers=1)
        # meta_dir not set

        result = manager._process_single_fallback("test", Path("/tmp/test"))
        manager.shutdown()

        assert result is False


class TestOnCliSuccess:
    """Tests for AC5: Automatic catch-up trigger."""

    @patch.object(ClaudeCliManager, "process_all_fallbacks")
    def test_triggers_catchup_when_was_unavailable(self, mock_process):
        """AC5: _on_cli_success() triggers catch-up when CLI was unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(Path(tmpdir))
            manager._cli_was_unavailable = True

            manager._on_cli_success()
            time.sleep(0.1)  # Allow thread to start
            manager.shutdown()

            assert manager._cli_was_unavailable is False
            mock_process.assert_called_once()

    @patch.object(ClaudeCliManager, "process_all_fallbacks")
    def test_no_trigger_when_already_available(self, mock_process):
        """AC5: _on_cli_success() does not trigger when CLI already available."""
        manager = ClaudeCliManager(max_workers=1)
        manager._cli_was_unavailable = False

        manager._on_cli_success()
        manager.shutdown()

        mock_process.assert_not_called()

    @patch.object(ClaudeCliManager, "process_all_fallbacks")
    def test_no_trigger_when_no_meta_dir(self, mock_process):
        """AC5: _on_cli_success() does not trigger when meta_dir not set."""
        manager = ClaudeCliManager(max_workers=1)
        manager._cli_was_unavailable = True
        # meta_dir not set

        manager._on_cli_success()
        manager.shutdown()

        mock_process.assert_not_called()


class TestCommitAndReindex:
    """Tests for AC4: Single commit and re-index after all swaps."""

    @patch("subprocess.run")
    def test_git_commit_with_proper_message(self, mock_run):
        """AC4: _commit_and_reindex() creates git commit with descriptive message."""
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            manager._commit_and_reindex(["repo1", "repo2"])
            manager.shutdown()

            # Verify git add was called
            git_add_call = mock_run.call_args_list[0]
            assert git_add_call[0][0] == ["git", "add", "."]

            # Verify git commit was called with message containing aliases
            git_commit_call = mock_run.call_args_list[1]
            assert "git" in git_commit_call[0][0]
            assert "commit" in git_commit_call[0][0]
            commit_msg = git_commit_call[0][0][git_commit_call[0][0].index("-m") + 1]
            assert "repo1" in commit_msg
            assert "repo2" in commit_msg

    @patch("subprocess.run")
    def test_git_failure_handled_gracefully(self, mock_run):
        """AC4: _commit_and_reindex() handles git failures gracefully."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            # Should not raise exception
            manager._commit_and_reindex(["repo1"])
            manager.shutdown()

    @patch("subprocess.run")
    def test_triggers_cidx_reindex(self, mock_run):
        """AC4: _commit_and_reindex() triggers cidx index after commit."""
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            manager._commit_and_reindex(["repo1"])
            manager.shutdown()

            # Verify cidx index was called (3rd call after git add, git commit)
            cidx_call = mock_run.call_args_list[2]
            assert cidx_call[0][0] == ["cidx", "index"]

    def test_no_action_when_no_meta_dir(self):
        """_commit_and_reindex() does nothing when meta_dir not set."""
        manager = ClaudeCliManager(max_workers=1)
        # meta_dir not set

        # Should not raise exception
        manager._commit_and_reindex(["repo1"])
        manager.shutdown()


class TestExceptionHandling:
    """Tests for exception handling paths."""

    @patch.object(ClaudeCliManager, "check_cli_available", return_value=True)
    @patch.object(ClaudeCliManager, "sync_api_key")
    def test_process_all_fallbacks_handles_rename_exception(self, mock_sync, mock_cli):
        """AC3: process_all_fallbacks() handles file operation exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            fallback = meta_dir / "test-repo_README.md"
            fallback.write_text("content")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            # Mock _process_single_fallback to raise exception
            with patch.object(
                manager,
                "_process_single_fallback",
                side_effect=Exception("Rename failed"),
            ):
                result = manager.process_all_fallbacks()

            manager.shutdown()

            assert result.partial is True
            assert "Rename failed" in result.error
            assert "test-repo" in result.remaining

    @patch.object(ClaudeCliManager, "sync_api_key")
    def test_process_single_fallback_handles_rename_exception(self, mock_sync):
        """AC3: _process_single_fallback() handles rename exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_dir = Path(tmpdir)
            fallback = meta_dir / "test-repo_README.md"
            fallback.write_text("content")

            manager = ClaudeCliManager(max_workers=1)
            manager.set_meta_dir(meta_dir)

            # Use a path that will cause rename to fail
            with patch.object(Path, "rename", side_effect=OSError("Permission denied")):
                result = manager._process_single_fallback("test-repo", fallback)

            manager.shutdown()

            assert result is False
