"""Unit tests for TemporalWatchHandler class.

Tests git refs monitoring, polling fallback, and commit detection.
Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
"""

import pytest
import subprocess
from unittest.mock import Mock, patch
from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler


class TestTemporalWatchHandlerInit:
    """Test suite for TemporalWatchHandler initialization."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_init_with_valid_git_refs_file(self, mock_run, tmp_path):
        """Test initialization when git refs file exists."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        # Mock git commands
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # git rev-parse --abbrev-ref HEAD
            Mock(stdout="abc123def456\n", returncode=0),  # git rev-parse HEAD
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.project_root == project_root
        assert handler.current_branch == "main"
        assert handler.git_refs_file == refs_heads / "main"
        assert handler.git_refs_file.exists()
        assert handler.use_polling is False
        assert handler.last_commit_hash == "abc123def456"

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_init_without_git_refs_file_uses_polling(self, mock_run, tmp_path):
        """Test initialization falls back to polling when refs file doesn't exist."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Mock git commands
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # git rev-parse --abbrev-ref HEAD
            Mock(stdout="abc123def456\n", returncode=0),  # git rev-parse HEAD
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.use_polling is True

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_get_current_branch_success(self, mock_run, tmp_path):
        """Test _get_current_branch returns branch name."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        mock_run.side_effect = [
            Mock(
                stdout="feature/test-branch\n", returncode=0
            ),  # git rev-parse --abbrev-ref HEAD
            Mock(stdout="abc123def456\n", returncode=0),  # git rev-parse HEAD
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.current_branch == "feature/test-branch"

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_get_current_branch_detached_head(self, mock_run, tmp_path):
        """Test _get_current_branch handles detached HEAD state."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        mock_run.side_effect = [
            subprocess.CalledProcessError(
                1, "git"
            ),  # git rev-parse --abbrev-ref HEAD fails
            Mock(stdout="abc123def456\n", returncode=0),  # git rev-parse HEAD
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.current_branch == "HEAD"

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_get_last_commit_hash_success(self, mock_run, tmp_path):
        """Test _get_last_commit_hash returns commit hash."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # git rev-parse --abbrev-ref HEAD
            Mock(stdout="deadbeef12345678\n", returncode=0),  # git rev-parse HEAD
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.last_commit_hash == "deadbeef12345678"


class TestTemporalWatchHandlerGitRefsMonitoring:
    """Test suite for git refs inotify monitoring."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_on_modified_git_refs_file_triggers_commit_detection(
        self, mock_run, tmp_path
    ):
        """Test that modifying git refs directory triggers commit detection.

        Note: Git uses atomic rename (master.lock → master), which doesn't trigger
        MODIFY events on the target file. Instead, we detect MODIFY events on the
        refs/heads directory. This test verifies the directory-based detection.
        """
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        refs_file = refs_heads / "main"
        refs_file.touch()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # Initial branch
            Mock(stdout="abc123\n", returncode=0),  # Initial commit hash
            Mock(stdout="def456\n", returncode=0),  # New commit hash (changed)
        ]

        handler = TemporalWatchHandler(project_root)
        handler._handle_commit_detected = Mock()

        # Create event mock for refs/heads directory (not the file itself)
        event = Mock()
        event.src_path = str(refs_heads)  # Directory modification, not file

        # Act
        handler.on_modified(event)

        # Assert - should detect commit via hash change
        handler._handle_commit_detected.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_on_modified_git_head_triggers_branch_switch(self, mock_run, tmp_path):
        """Test that modifying .git/HEAD triggers branch switch detection."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()
        head_file = git_dir / "HEAD"
        head_file.touch()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        handler = TemporalWatchHandler(project_root)
        handler._handle_branch_switch = Mock()

        # Create event mock
        event = Mock()
        event.src_path = str(head_file)

        # Act
        handler.on_modified(event)

        # Assert
        handler._handle_branch_switch.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_on_modified_ignores_other_files(self, mock_run, tmp_path):
        """Test that modifying other files doesn't trigger handlers."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        handler = TemporalWatchHandler(project_root)
        handler._handle_commit_detected = Mock()
        handler._handle_branch_switch = Mock()

        # Create event mock for different file
        event = Mock()
        event.src_path = str(project_root / "some_other_file.txt")

        # Act
        handler.on_modified(event)

        # Assert
        handler._handle_commit_detected.assert_not_called()
        handler._handle_branch_switch.assert_not_called()


class TestTemporalWatchHandlerPollingFallback:
    """Test suite for polling fallback mechanism."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    @patch("code_indexer.cli_temporal_watch_handler.threading.Thread")
    def test_polling_thread_started_when_refs_file_missing(
        self, mock_thread, mock_run, tmp_path
    ):
        """Test that polling thread starts when refs file doesn't exist."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Act
        handler = TemporalWatchHandler(project_root)

        # Assert
        assert handler.use_polling is True
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    @patch("code_indexer.cli_temporal_watch_handler.time.sleep")
    def test_polling_detects_commit_hash_change(self, mock_sleep, mock_run, tmp_path):
        """Test that polling detects commit hash changes."""
        # This is a more complex integration test that we'll implement later
        pytest.skip("Requires more complex polling simulation")


class TestTemporalWatchHandlerBranchSwitch:
    """Test suite for branch switch detection (Story 3.1 placeholder)."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_branch_switch_is_placeholder(self, mock_run, tmp_path):
        """Test that _handle_branch_switch exists but is placeholder for Story 3.1."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        handler = TemporalWatchHandler(project_root)

        # Act & Assert - should not raise
        handler._handle_branch_switch()
