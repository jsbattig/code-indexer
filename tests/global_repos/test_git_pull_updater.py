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

        # Mock subprocess to simulate successful git pull
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Already up to date.\n", stderr=""
            )

            updater.update()

            # Verify git pull was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "git" in args
            assert "pull" in args

    def test_update_raises_on_git_pull_failure(self, tmp_path):
        """
        Test that update() raises exception when git pull fails.

        AC6: Failed refresh handling
        """
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        updater = GitPullUpdater(str(repo_path))

        # Mock subprocess to simulate git pull failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="fatal: unable to access repository"
            )

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
