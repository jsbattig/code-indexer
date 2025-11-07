"""Unit tests for incremental temporal indexing in TemporalWatchHandler.

Tests _handle_commit_detected() with:
1. Loading completed commits from temporal_progress.json
2. Filtering new commits
3. Calling TemporalIndexer
4. Updating metadata
5. Invalidating daemon cache

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
"""

from unittest.mock import Mock, patch
from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler


class TestIncrementalTemporalIndexing:
    """Test suite for _handle_commit_detected() incremental indexing."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_commit_detected_with_new_commits(self, mock_run, tmp_path):
        """Test that new commits are detected and indexed."""
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
            Mock(stdout="abc123\n", returncode=0),  # git rev-parse HEAD
        ]

        handler = TemporalWatchHandler(project_root)

        # Mock progressive_metadata
        handler.progressive_metadata = Mock()
        handler.progressive_metadata.load_completed.return_value = {
            "old_commit_1",
            "old_commit_2",
        }

        # Mock git rev-list output
        mock_run.side_effect = [
            Mock(
                stdout="new_commit_3\nnew_commit_2\nold_commit_1\nold_commit_2\n",
                returncode=0,
            ),
        ]

        # Mock temporal_indexer
        handler.temporal_indexer = Mock()
        mock_result = Mock()
        mock_result.new_blobs_indexed = 5
        mock_result.deduplication_ratio = 0.75
        handler.temporal_indexer.index_commits_list = Mock(return_value=mock_result)

        # Mock RichLiveProgressManager
        with patch(
            "code_indexer.progress.progress_display.RichLiveProgressManager"
        ) as mock_progress:
            mock_progress_manager = Mock()
            mock_progress.return_value = mock_progress_manager
            mock_progress_manager.start_bottom_display = Mock()
            mock_progress_manager.stop_display = Mock()
            mock_progress_manager.update_display = Mock()

            # Act
            handler._handle_commit_detected()

        # Assert
        handler.progressive_metadata.load_completed.assert_called_once()
        handler.temporal_indexer.index_commits_list.assert_called_once()

        # Verify only new commits were passed
        call_args = handler.temporal_indexer.index_commits_list.call_args
        commit_hashes = call_args.kwargs.get("commit_hashes") or call_args[0][0]
        assert len(commit_hashes) == 2
        assert "new_commit_3" in commit_hashes
        assert "new_commit_2" in commit_hashes
        assert "old_commit_1" not in commit_hashes
        assert "old_commit_2" not in commit_hashes

        # Verify metadata was updated
        handler.progressive_metadata.mark_completed.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_commit_detected_no_new_commits(self, mock_run, tmp_path):
        """Test that no indexing occurs when all commits are already indexed."""
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

        # Mock progressive_metadata - all commits already indexed
        handler.progressive_metadata = Mock()
        handler.progressive_metadata.load_completed.return_value = {
            "commit_1",
            "commit_2",
            "commit_3",
        }

        # Mock git rev-list - returns already indexed commits
        mock_run.side_effect = [
            Mock(stdout="commit_1\ncommit_2\ncommit_3\n", returncode=0),
        ]

        # Mock temporal_indexer
        handler.temporal_indexer = Mock()

        # Act
        handler._handle_commit_detected()

        # Assert
        handler.progressive_metadata.load_completed.assert_called_once()
        handler.temporal_indexer.index_commits_list.assert_not_called()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_commit_detected_updates_metadata(self, mock_run, tmp_path):
        """Test that temporal_progress.json is updated with new commits."""
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

        # Mock progressive_metadata
        handler.progressive_metadata = Mock()
        handler.progressive_metadata.load_completed.return_value = set()

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="new_commit_1\n", returncode=0),
        ]

        # Mock temporal_indexer
        handler.temporal_indexer = Mock()
        mock_result = Mock()
        mock_result.new_blobs_indexed = 3
        mock_result.deduplication_ratio = 0.5
        handler.temporal_indexer.index_commits_list = Mock(return_value=mock_result)

        # Mock RichLiveProgressManager
        with patch("code_indexer.progress.progress_display.RichLiveProgressManager"):
            # Act
            handler._handle_commit_detected()

        # Assert
        handler.progressive_metadata.mark_completed.assert_called_once_with(
            ["new_commit_1"]
        )

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_handle_commit_detected_invalidates_daemon_cache(
        self, mock_connect, mock_run, tmp_path
    ):
        """Test that daemon cache is invalidated after indexing."""
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

        # Mock progressive_metadata
        handler.progressive_metadata = Mock()
        handler.progressive_metadata.load_completed.return_value = set()

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="new_commit_1\n", returncode=0),
        ]

        # Mock temporal_indexer
        handler.temporal_indexer = Mock()
        mock_result = Mock()
        mock_result.new_blobs_indexed = 3
        mock_result.deduplication_ratio = 0.5
        handler.temporal_indexer.index_commits_list = Mock(return_value=mock_result)

        # Mock daemon connection
        mock_daemon_client = Mock()
        mock_connect.return_value = mock_daemon_client

        # Mock ConfigManager
        with patch("code_indexer.config.ConfigManager") as mock_config_manager:
            mock_config_manager.return_value.get_daemon_config.return_value = {
                "enabled": True
            }

            # Mock RichLiveProgressManager
            with patch(
                "code_indexer.progress.progress_display.RichLiveProgressManager"
            ):
                # Act
                handler._handle_commit_detected()

        # Assert
        mock_daemon_client.root.exposed_clear_cache.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_commit_detected_uses_rich_progress_manager(
        self, mock_run, tmp_path
    ):
        """Test that RichLiveProgressManager is used for progress reporting."""
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

        # Mock progressive_metadata
        handler.progressive_metadata = Mock()
        handler.progressive_metadata.load_completed.return_value = set()

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="new_commit_1\n", returncode=0),
        ]

        # Mock temporal_indexer
        handler.temporal_indexer = Mock()
        mock_result = Mock()
        mock_result.new_blobs_indexed = 3
        mock_result.deduplication_ratio = 0.5
        handler.temporal_indexer.index_commits_list = Mock(return_value=mock_result)

        # Mock RichLiveProgressManager
        with patch(
            "code_indexer.progress.progress_display.RichLiveProgressManager"
        ) as mock_progress_class:
            mock_progress_manager = Mock()
            mock_progress_class.return_value = mock_progress_manager
            mock_progress_manager.start_bottom_display = Mock()
            mock_progress_manager.stop_display = Mock()
            mock_progress_manager.update_display = Mock()

            # Act
            handler._handle_commit_detected()

            # Assert
            mock_progress_class.assert_called_once()
            # Verify progress callback was passed to index_commits_list
            call_kwargs = handler.temporal_indexer.index_commits_list.call_args.kwargs
            assert "progress_callback" in call_kwargs
            assert callable(call_kwargs["progress_callback"])
