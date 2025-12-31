"""Unit tests for ChangeDetector - git change detection for auto-update."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import subprocess

from code_indexer.server.auto_update.change_detector import ChangeDetector


class TestChangeDetectorInitialization:
    """Test ChangeDetector initialization."""

    def test_initializes_with_repo_path(self):
        """ChangeDetector should initialize with repository path."""
        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        assert detector.repo_path == Path("/tmp/test-repo")

    def test_initializes_with_default_branch(self):
        """ChangeDetector should initialize with master as default branch."""
        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        assert detector.branch == "master"

    def test_initializes_with_custom_branch(self):
        """ChangeDetector should support custom branch name."""
        detector = ChangeDetector(
            repo_path=Path("/tmp/test-repo"),
            branch="main",
        )

        assert detector.branch == "main"


class TestChangeDetectorGitFetch:
    """Test ChangeDetector git fetch operation."""

    @patch("subprocess.run")
    def test_fetch_executes_git_fetch_command(self, mock_run):
        """fetch() should execute git fetch origin <branch>."""
        mock_run.return_value = Mock(returncode=0)

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        detector.fetch()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "fetch", "origin", "master", "--quiet"]

    @patch("subprocess.run")
    def test_fetch_uses_correct_working_directory(self, mock_run):
        """fetch() should run git command in repository directory."""
        mock_run.return_value = Mock(returncode=0)

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        detector.fetch()

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == Path("/tmp/test-repo")

    @patch("subprocess.run")
    def test_fetch_raises_on_git_failure(self, mock_run):
        """fetch() should raise exception when git fetch fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stderr="fatal: Could not read from remote repository",
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        with pytest.raises(subprocess.CalledProcessError):
            detector.fetch()


class TestChangeDetectorRefComparison:
    """Test ChangeDetector ref comparison logic."""

    @patch("subprocess.run")
    def test_get_local_ref_executes_git_rev_parse(self, mock_run):
        """get_local_ref() should execute git rev-parse HEAD."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="abc123def456\n",
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        ref = detector.get_local_ref()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "rev-parse", "HEAD"]
        assert ref == "abc123def456"

    @patch("subprocess.run")
    def test_get_remote_ref_executes_git_rev_parse(self, mock_run):
        """get_remote_ref() should execute git rev-parse origin/<branch>."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="def456abc789\n",
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        ref = detector.get_remote_ref()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "rev-parse", "origin/master"]
        assert ref == "def456abc789"

    @patch("subprocess.run")
    def test_get_local_ref_strips_whitespace(self, mock_run):
        """get_local_ref() should strip whitespace from output."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="  abc123def456  \n\n",
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        ref = detector.get_local_ref()

        assert ref == "abc123def456"

    @patch("subprocess.run")
    def test_get_local_ref_raises_on_git_failure(self, mock_run):
        """get_local_ref() should raise CalledProcessError when git rev-parse fails."""
        mock_run.return_value = Mock(
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
            args=["git", "rev-parse", "HEAD"],
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            detector.get_local_ref()

        assert exc_info.value.returncode == 128

    @patch("subprocess.run")
    def test_get_remote_ref_raises_on_git_failure(self, mock_run):
        """get_remote_ref() should raise CalledProcessError when git rev-parse fails."""
        mock_run.return_value = Mock(
            returncode=128,
            stdout="",
            stderr="fatal: ambiguous argument 'origin/master': unknown revision",
            args=["git", "rev-parse", "origin/master"],
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            detector.get_remote_ref()

        assert exc_info.value.returncode == 128


class TestChangeDetectorHasChanges:
    """Test ChangeDetector has_changes() method."""

    @patch("subprocess.run")
    def test_has_changes_returns_true_when_refs_differ(self, mock_run):
        """has_changes() should return True when local and remote refs differ."""
        # Mock git fetch (no-op)
        # Mock git rev-parse HEAD
        # Mock git rev-parse origin/master
        responses = [
            Mock(returncode=0),  # git fetch
            Mock(returncode=0, stdout="abc123\n"),  # git rev-parse HEAD
            Mock(returncode=0, stdout="def456\n"),  # git rev-parse origin/master
        ]
        mock_run.side_effect = responses

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        result = detector.has_changes()

        assert result is True

    @patch("subprocess.run")
    def test_has_changes_returns_false_when_refs_match(self, mock_run):
        """has_changes() should return False when local and remote refs match."""
        responses = [
            Mock(returncode=0),  # git fetch
            Mock(returncode=0, stdout="abc123\n"),  # git rev-parse HEAD
            Mock(returncode=0, stdout="abc123\n"),  # git rev-parse origin/master
        ]
        mock_run.side_effect = responses

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        result = detector.has_changes()

        assert result is False

    @patch("subprocess.run")
    def test_has_changes_fetches_before_comparing(self, mock_run):
        """has_changes() should fetch from remote before comparing refs."""
        responses = [
            Mock(returncode=0),  # git fetch
            Mock(returncode=0, stdout="abc123\n"),  # git rev-parse HEAD
            Mock(returncode=0, stdout="abc123\n"),  # git rev-parse origin/master
        ]
        mock_run.side_effect = responses

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))
        detector.has_changes()

        # First call should be git fetch
        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args[0] == "git"
        assert first_call_args[1] == "fetch"

    @patch("subprocess.run")
    def test_has_changes_raises_on_fetch_failure(self, mock_run):
        """has_changes() should raise exception when fetch fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stderr="fatal: unable to access repository",
        )

        detector = ChangeDetector(repo_path=Path("/tmp/test-repo"))

        with pytest.raises(subprocess.CalledProcessError):
            detector.has_changes()
