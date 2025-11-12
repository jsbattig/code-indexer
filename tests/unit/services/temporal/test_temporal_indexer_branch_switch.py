"""Unit tests for TemporalWatchHandler branch switch catch-up functionality.

Story 3: Efficient Unindexed Commit Detection
Tests O(1) commit filtering, branch switch detection, and incremental catch-up indexing.
"""

from unittest.mock import Mock, patch
from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler


class TestBranchSwitchDetection:
    """Test suite for branch switch detection logic."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_branch_switch_same_branch_no_action(self, mock_run, tmp_path):
        """Test that same branch (detached HEAD -> branch) triggers no catch-up."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # Initial branch
            Mock(stdout="abc123\n", returncode=0),  # Initial commit hash
        ]

        handler = TemporalWatchHandler(project_root)

        # Mock dependencies
        handler._catch_up_temporal_index = Mock()

        # Reset mock_run for _get_current_branch call in _handle_branch_switch
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # Still main branch
        ]

        # Act
        handler._handle_branch_switch()

        # Assert - No catch-up should happen
        handler._catch_up_temporal_index.assert_not_called()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_branch_switch_different_branch_triggers_catchup(
        self, mock_run, tmp_path
    ):
        """Test that switching to different branch triggers catch-up indexing."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()
        (refs_heads / "feature").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # Initial branch
            Mock(stdout="abc123\n", returncode=0),  # Initial commit hash
        ]

        handler = TemporalWatchHandler(project_root)

        # Mock dependencies
        handler._catch_up_temporal_index = Mock()

        # Reset mock_run for branch switch detection
        mock_run.side_effect = [
            Mock(stdout="feature\n", returncode=0),  # New branch
        ]

        # Act
        handler._handle_branch_switch()

        # Assert
        assert handler.current_branch == "feature"
        assert handler.git_refs_file == refs_heads / "feature"
        handler._catch_up_temporal_index.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_handle_branch_switch_updates_git_refs_file(self, mock_run, tmp_path):
        """Test that branch switch updates git_refs_file path."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()
        (refs_heads / "develop").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),  # Initial branch
            Mock(stdout="abc123\n", returncode=0),  # Initial commit hash
        ]

        handler = TemporalWatchHandler(project_root)

        # Mock dependencies
        handler._catch_up_temporal_index = Mock()

        # Verify initial state
        assert handler.git_refs_file == refs_heads / "main"

        # Reset mock_run for branch switch
        mock_run.side_effect = [
            Mock(stdout="develop\n", returncode=0),  # New branch
        ]

        # Act
        handler._handle_branch_switch()

        # Assert
        assert handler.git_refs_file == refs_heads / "develop"
        assert handler.current_branch == "develop"


class TestCatchUpTemporalIndex:
    """Test suite for _catch_up_temporal_index() method."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_catch_up_with_unindexed_commits(self, mock_run, tmp_path):
        """Test catch-up indexes only unindexed commits."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "feature").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="feature\n", returncode=0),  # Branch
            Mock(stdout="abc123\n", returncode=0),  # Commit hash
        ]

        # Mock dependencies
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = {"commit1", "commit2"}

        mock_temporal_indexer = Mock()

        handler = TemporalWatchHandler(
            project_root,
            temporal_indexer=mock_temporal_indexer,
            progressive_metadata=mock_progressive_metadata,
        )
        handler.completed_commits_set = {"commit1", "commit2"}

        # Mock git rev-list to return all commits
        mock_run.side_effect = [
            Mock(stdout="commit3\ncommit2\ncommit1\n", returncode=0),  # git rev-list
        ]

        # Mock _index_commits_incremental
        handler._index_commits_incremental = Mock()

        # Act
        handler._catch_up_temporal_index()

        # Assert - Only commit3 should be indexed
        handler._index_commits_incremental.assert_called_once()
        indexed_commits = handler._index_commits_incremental.call_args[0][0]
        assert indexed_commits == ["commit3"]

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_catch_up_fully_indexed_branch_no_indexing(self, mock_run, tmp_path):
        """Test that fully indexed branch skips indexing."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock dependencies
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = {
            "commit1",
            "commit2",
            "commit3",
        }

        mock_temporal_indexer = Mock()

        handler = TemporalWatchHandler(
            project_root,
            temporal_indexer=mock_temporal_indexer,
            progressive_metadata=mock_progressive_metadata,
        )
        handler.completed_commits_set = {"commit1", "commit2", "commit3"}

        # Mock git rev-list - all commits already indexed
        mock_run.side_effect = [
            Mock(stdout="commit3\ncommit2\ncommit1\n", returncode=0),
        ]

        # Mock _index_commits_incremental
        handler._index_commits_incremental = Mock()

        # Act
        handler._catch_up_temporal_index()

        # Assert - No indexing should occur
        handler._index_commits_incremental.assert_not_called()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_catch_up_updates_metadata_and_invalidates_cache(self, mock_run, tmp_path):
        """Test catch-up updates metadata and invalidates daemon cache."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "feature").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="feature\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock dependencies
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = {"commit1"}
        mock_progressive_metadata.mark_completed = Mock()

        mock_temporal_indexer = Mock()

        handler = TemporalWatchHandler(
            project_root,
            temporal_indexer=mock_temporal_indexer,
            progressive_metadata=mock_progressive_metadata,
        )
        handler.completed_commits_set = {"commit1"}

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="commit3\ncommit2\ncommit1\n", returncode=0),
        ]

        # Mock methods
        handler._index_commits_incremental = Mock()
        handler._invalidate_daemon_cache = Mock()

        # Act
        handler._catch_up_temporal_index()

        # Assert
        handler._index_commits_incremental.assert_called_once()
        mock_progressive_metadata.mark_completed.assert_called_once()
        handler._invalidate_daemon_cache.assert_called_once()

        # Verify in-memory set updated
        assert handler.completed_commits_set == {"commit1", "commit2", "commit3"}


class TestInMemorySetPerformance:
    """Test suite for O(1) in-memory set commit filtering."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_in_memory_set_loaded_on_init(self, mock_run, tmp_path):
        """Test that completed_commits_set is loaded into memory on init."""
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
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock progressive_metadata.load_completed()
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = {
            "commit1",
            "commit2",
            "commit3",
        }

        # Act
        handler = TemporalWatchHandler(
            project_root, progressive_metadata=mock_progressive_metadata
        )

        # Assert
        assert hasattr(handler, "completed_commits_set")
        assert handler.completed_commits_set == {"commit1", "commit2", "commit3"}
        mock_progressive_metadata.load_completed.assert_called_once()

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_commit_filtering_uses_set_membership(self, mock_run, tmp_path):
        """Test that commit filtering uses O(1) set membership checks."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "main").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock progressive_metadata with 1000 commits
        completed_commits = {f"commit{i}" for i in range(1000)}
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = completed_commits

        handler = TemporalWatchHandler(
            project_root, progressive_metadata=mock_progressive_metadata
        )

        # Mock git rev-list with 1100 commits (1000 old + 100 new)
        # Range should be 1099 down to 0 (1100 commits total: commit0 to commit1099)
        all_commits = [f"commit{i}" for i in range(1099, -1, -1)]
        mock_run.side_effect = [
            Mock(stdout="\n".join(all_commits), returncode=0),
        ]

        # Mock _index_commits_incremental
        handler._index_commits_incremental = Mock()

        # Act
        import time

        start = time.time()
        handler._catch_up_temporal_index()
        elapsed = time.time() - start

        # Assert
        # Filtering 1100 commits against 1000 completed should be <100ms (O(1) per commit)
        assert elapsed < 0.1, f"Filtering took {elapsed}s, expected <0.1s"

        # Verify only new commits indexed
        handler._index_commits_incremental.assert_called_once()
        indexed_commits = handler._index_commits_incremental.call_args[0][0]
        assert len(indexed_commits) == 100  # Only commits 1000-1099

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_in_memory_set_updated_after_catch_up(self, mock_run, tmp_path):
        """Test that in-memory set is updated after catch-up indexing."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "feature").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="feature\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock progressive_metadata
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = {"commit1"}

        handler = TemporalWatchHandler(
            project_root, progressive_metadata=mock_progressive_metadata
        )

        # Verify initial state
        assert handler.completed_commits_set == {"commit1"}

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="commit3\ncommit2\ncommit1\n", returncode=0),
        ]

        # Mock methods
        handler._index_commits_incremental = Mock()
        handler._invalidate_daemon_cache = Mock()

        # Act
        handler._catch_up_temporal_index()

        # Assert - in-memory set updated
        assert "commit2" in handler.completed_commits_set
        assert "commit3" in handler.completed_commits_set
        assert len(handler.completed_commits_set) == 3


class TestProgressReporting:
    """Test suite for progress reporting during catch-up."""

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_catch_up_uses_progress_manager(self, mock_run, tmp_path):
        """Test that catch-up indexing uses RichLiveProgressManager."""
        # Arrange
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        git_dir = project_root / ".git"
        git_dir.mkdir()
        refs_heads = git_dir / "refs/heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "feature").touch()

        # Mock git commands for initialization
        mock_run.side_effect = [
            Mock(stdout="feature\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        # Mock dependencies
        mock_progressive_metadata = Mock()
        mock_progressive_metadata.load_completed.return_value = set()

        mock_temporal_indexer = Mock()

        handler = TemporalWatchHandler(
            project_root,
            temporal_indexer=mock_temporal_indexer,
            progressive_metadata=mock_progressive_metadata,
        )
        handler.completed_commits_set = set()

        # Mock git rev-list
        mock_run.side_effect = [
            Mock(stdout="commit1\ncommit2\n", returncode=0),
        ]

        # Mock _index_commits_incremental to verify it's called
        handler._index_commits_incremental = Mock()
        handler._invalidate_daemon_cache = Mock()

        # Act
        handler._catch_up_temporal_index()

        # Assert - _index_commits_incremental should be called with commits
        handler._index_commits_incremental.assert_called_once_with(
            ["commit1", "commit2"]
        )

    @patch("code_indexer.cli_temporal_watch_handler.subprocess.run")
    def test_index_commits_incremental_exists(self, mock_run, tmp_path):
        """Test that _index_commits_incremental method exists for Story 3."""
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
            Mock(stdout="main\n", returncode=0),
            Mock(stdout="abc123\n", returncode=0),
        ]

        handler = TemporalWatchHandler(project_root)

        # Assert - method should exist
        assert hasattr(handler, "_index_commits_incremental")
        assert callable(handler._index_commits_incremental)
