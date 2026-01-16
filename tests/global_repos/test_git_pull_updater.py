"""
Tests for GitPullUpdater - git-based update strategy.

Tests AC1 Technical Requirements:
- Git pull operation on golden repo source
- Change detection before full reindex
"""

import pytest
from unittest.mock import patch, MagicMock
from code_indexer.global_repos.git_pull_updater import GitPullUpdater


class TestGitPullUpdater:
    """Test suite for GitPullUpdater component."""

    def test_has_changes_detects_changes_via_git(self, tmp_path):
        """
        Test that has_changes() returns True when git detects remote changes.

        AC1: Change detection before full reindex
        """
        # Create a mock git repo directory
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Mock subprocess to simulate git fetch + log detecting remote changes
        with patch("subprocess.run") as mock_run:
            # First call: git fetch succeeds
            # Second call: git log shows remote commits
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # fetch success
                MagicMock(
                    returncode=0,
                    stdout="abc123 Remote commit\ndef456 Another commit\n",
                    stderr="",
                ),  # log shows 2 commits
            ]

            has_changes = updater.has_changes()

            assert has_changes is True
            # Verify git fetch and git log were called
            assert mock_run.call_count == 2
            fetch_args = mock_run.call_args_list[0][0][0]
            assert "git" in fetch_args
            assert "fetch" in fetch_args
            log_args = mock_run.call_args_list[1][0][0]
            assert "git" in log_args
            assert "log" in log_args
            assert "HEAD..@{upstream}" in log_args

    def test_has_changes_returns_false_when_no_changes(self, tmp_path):
        """
        Test that has_changes() returns False when git detects no remote changes.

        AC1: Skip index if no changes
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Mock subprocess to simulate no remote changes
        with patch("subprocess.run") as mock_run:
            # First call: git fetch succeeds
            # Second call: git log shows no commits (empty output)
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # fetch success
                MagicMock(returncode=0, stdout="", stderr=""),  # no commits
            ]

            has_changes = updater.has_changes()

            assert has_changes is False

    def test_update_executes_git_pull(self, tmp_path):
        """
        Test that update() executes git pull successfully.

        AC1: Git pull operation on golden repo source
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Track calls to verify git pull is executed
        call_sequence = []

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            call_sequence.append(cmd)

            # git status --porcelain returns clean (no modifications)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout="", stderr="")

            # git pull succeeds
            if cmd == ["git", "pull"]:
                return MagicMock(
                    returncode=0, stdout="Already up to date.\n", stderr=""
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            updater.update()

        # Verify git pull was called
        assert ["git", "pull"] in call_sequence, "git pull should be called"

    def test_update_raises_on_git_pull_failure(self, tmp_path):
        """
        Test that update() raises exception when git pull fails.

        AC6: Failed refresh handling
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]

            # git status --porcelain returns clean (no modifications)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout="", stderr="")

            # git pull fails
            if cmd == ["git", "pull"]:
                return MagicMock(
                    returncode=1, stdout="", stderr="fatal: unable to access repository"
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            with pytest.raises(RuntimeError, match="Git pull failed"):
                updater.update()

    def test_get_source_path_returns_repo_path(self, tmp_path):
        """
        Test that get_source_path() returns the repository path.
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        source = updater.get_source_path()

        assert source == str(repo_path)


class TestGitPullUpdaterDefenseInDepth:
    """
    Story #726: Defense in depth tests for GitPullUpdater.

    These tests verify that update() handles local modifications gracefully
    by resetting them before pulling, preventing git pull failures.
    """

    def test_update_resets_local_modifications_before_pull(self, tmp_path):
        """
        GIVEN a repository with local modifications (dirty working tree)
        WHEN update() is called
        THEN it should first reset local modifications, then pull successfully

        AC: Golden repo refresh succeeds even if repo has modified files (defense in depth)
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Track all subprocess calls
        call_sequence = []

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            call_sequence.append(cmd)

            # git status --porcelain shows modifications
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout="M .gitignore\n", stderr="")

            # git reset --hard HEAD succeeds
            if cmd == ["git", "reset", "--hard", "HEAD"]:
                return MagicMock(returncode=0, stdout="", stderr="")

            # git pull succeeds
            if cmd == ["git", "pull"]:
                return MagicMock(
                    returncode=0, stdout="Already up to date.\n", stderr=""
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            updater.update()

        # Verify sequence: status check -> reset -> pull
        assert ["git", "status", "--porcelain"] in call_sequence, (
            "Should check for modifications first"
        )
        assert ["git", "reset", "--hard", "HEAD"] in call_sequence, (
            "Should reset modifications"
        )
        assert ["git", "pull"] in call_sequence, "Should execute git pull"

        # Verify order: reset comes before pull
        reset_idx = call_sequence.index(["git", "reset", "--hard", "HEAD"])
        pull_idx = call_sequence.index(["git", "pull"])
        assert reset_idx < pull_idx, "Reset should happen before pull"

    def test_update_logs_warning_when_modifications_detected(self, tmp_path):
        """
        GIVEN a repository with local modifications
        WHEN update() is called
        THEN it should log a warning about the modifications being reset

        AC: Log warning when modifications are detected
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]

            # git status --porcelain shows modifications
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(
                    returncode=0,
                    stdout="M .gitignore\nM README.md\n",
                    stderr="",
                )

            # git reset and pull succeed
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch(
                "code_indexer.global_repos.git_pull_updater.logger"
            ) as mock_logger:
                updater.update()

                # Verify warning was logged
                mock_logger.warning.assert_called()
                warning_calls = [
                    str(call) for call in mock_logger.warning.call_args_list
                ]
                assert any(
                    "modification" in call.lower() or "reset" in call.lower()
                    for call in warning_calls
                ), f"Should log warning about modifications, got: {warning_calls}"

    def test_update_skips_reset_when_no_modifications(self, tmp_path):
        """
        GIVEN a repository with clean working tree (no modifications)
        WHEN update() is called
        THEN it should NOT execute git reset

        AC: Don't reset if there are no modifications (efficiency)
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        call_sequence = []

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            call_sequence.append(cmd)

            # git status --porcelain shows clean working tree
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout="", stderr="")

            # git pull succeeds
            if cmd == ["git", "pull"]:
                return MagicMock(
                    returncode=0, stdout="Already up to date.\n", stderr=""
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            updater.update()

        # Verify reset was NOT called
        assert ["git", "reset", "--hard", "HEAD"] not in call_sequence, (
            "Should NOT reset when working tree is clean"
        )

        # Verify pull was still called
        assert ["git", "pull"] in call_sequence, "Should still execute git pull"

    def test_update_succeeds_after_resetting_gitignore_modification(self, tmp_path):
        """
        GIVEN a repository where .gitignore was modified (by old CIDX version)
        WHEN update() is called
        THEN it should successfully reset .gitignore and pull

        AC: Existing repos with modified .gitignore can still refresh after fix
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Simulate the exact scenario: .gitignore modified by CIDX
        modification_output = " M .gitignore\n"

        call_sequence = []

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            call_sequence.append(cmd)

            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(
                    returncode=0, stdout=modification_output, stderr=""
                )

            if cmd == ["git", "reset", "--hard", "HEAD"]:
                return MagicMock(
                    returncode=0,
                    stdout="HEAD is now at abc123 Previous commit\n",
                    stderr="",
                )

            if cmd == ["git", "pull"]:
                return MagicMock(
                    returncode=0,
                    stdout="Updating abc123..def456\nFast-forward\n",
                    stderr="",
                )

            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess):
            # This should NOT raise an exception
            updater.update()

        # Verify the full sequence executed successfully
        assert ["git", "status", "--porcelain"] in call_sequence
        assert ["git", "reset", "--hard", "HEAD"] in call_sequence
        assert ["git", "pull"] in call_sequence
