"""
Tests for RefreshScheduler - timer-triggered refresh orchestration.

Tests AC1, AC2, AC3, AC6 Technical Requirements:
- Timer-triggered refresh at configured intervals
- Git pull and change detection
- New versioned index creation
- Atomic alias swap
- Query-aware cleanup scheduling
- Error handling and recovery
"""

from unittest.mock import patch, MagicMock
from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.global_repos.alias_manager import AliasManager
from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.config import ConfigManager


class TestRefreshScheduler:
    """Test suite for RefreshScheduler component."""

    def test_scheduler_starts_and_stops(self, tmp_path):
        """
        Test that scheduler can be started and stopped cleanly.

        Basic lifecycle management
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        scheduler.start()
        assert scheduler.is_running()

        scheduler.stop()
        assert not scheduler.is_running()

    def test_scheduler_uses_configured_interval(self, tmp_path):
        """
        Test that scheduler uses the configured refresh interval.

        AC5: All repos use same interval
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        config_mgr.set_global_refresh_interval(300)  # 5 minutes

        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Verify interval is read from config
        assert scheduler.get_refresh_interval() == 300

    def test_refresh_repo_executes_git_pull(self, tmp_path):
        """
        Test that refresh_repo() executes git pull via updater.

        AC1: Git pull operation on golden repo source
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create mock golden repo
        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()

        # Create alias and registry entry
        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", str(repo_dir))
        registry.register_global_repo(
            "test-repo",
            "test-repo-global",
            "https://github.com/test/repo",
            str(repo_dir),
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Mock updater
        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = False  # No changes
            mock_updater_cls.return_value = mock_updater

            scheduler.refresh_repo("test-repo-global")

            # Verify updater was called
            mock_updater.has_changes.assert_called_once()

    def test_refresh_skips_if_no_changes(self, tmp_path):
        """
        Test that refresh skips indexing if no git changes detected.

        AC1: Change detection before full reindex (skip if no changes)
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", str(repo_dir))
        registry.register_global_repo(
            "test-repo",
            "test-repo-global",
            "https://github.com/test/repo",
            str(repo_dir),
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = False  # No changes
            mock_updater_cls.return_value = mock_updater

            scheduler.refresh_repo("test-repo-global")

            # Verify update() was NOT called (skipped)
            mock_updater.update.assert_not_called()

    def test_refresh_executes_update_if_changes_detected(self, tmp_path):
        """
        Test that refresh executes git pull when changes detected.

        AC1: Git pull and indexing when changes exist
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", str(repo_dir))
        registry.register_global_repo(
            "test-repo",
            "test-repo-global",
            "https://github.com/test/repo",
            str(repo_dir),
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = True  # Changes detected
            mock_updater_cls.return_value = mock_updater

            with patch.object(scheduler, "_create_new_index") as mock_create_index:
                mock_create_index.return_value = str(tmp_path / "v_new")

                scheduler.refresh_repo("test-repo-global")

                # Verify update was called
                mock_updater.update.assert_called_once()

    def test_refresh_creates_versioned_index_directory(self, tmp_path):
        """
        Test that refresh creates new versioned index directory.

        AC1: New index directory with timestamp version
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", str(repo_dir))
        registry.register_global_repo(
            "test-repo",
            "test-repo-global",
            "https://github.com/test/repo",
            str(repo_dir),
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = True
            mock_updater.get_source_path.return_value = str(repo_dir)
            mock_updater_cls.return_value = mock_updater

            with patch.object(scheduler, "_create_new_index") as mock_create_index:
                new_index_path = str(tmp_path / "v_1234567890")
                mock_create_index.return_value = new_index_path

                scheduler.refresh_repo("test-repo-global")

                # Verify _create_new_index was called
                mock_create_index.assert_called_once()

    def test_refresh_swaps_alias_after_indexing(self, tmp_path):
        """
        Test that refresh swaps alias pointer after creating new index.

        AC2: Atomic alias swap after index creation
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", old_index)
        registry.register_global_repo(
            "test-repo", "test-repo-global", "https://github.com/test/repo", old_index
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = True
            mock_updater.get_source_path.return_value = str(repo_dir)
            mock_updater_cls.return_value = mock_updater

            new_index = str(tmp_path / "v_new")
            with patch.object(scheduler, "_create_new_index") as mock_create_index:
                mock_create_index.return_value = new_index

                scheduler.refresh_repo("test-repo-global")

                # Verify alias was swapped
                current_target = alias_mgr.read_alias("test-repo-global")
                assert current_target == new_index

    def test_refresh_schedules_cleanup_of_old_index(self, tmp_path):
        """
        Test that refresh schedules cleanup of old index after swap.

        AC3: Old index scheduled for cleanup
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", old_index)
        registry.register_global_repo(
            "test-repo", "test-repo-global", "https://github.com/test/repo", old_index
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = True
            mock_updater.get_source_path.return_value = str(repo_dir)
            mock_updater_cls.return_value = mock_updater

            new_index = str(tmp_path / "v_new")
            with patch.object(scheduler, "_create_new_index") as mock_create_index:
                mock_create_index.return_value = new_index

                scheduler.refresh_repo("test-repo-global")

                # Verify old index is in cleanup queue
                pending = cleanup_mgr.get_pending_cleanups()
                assert old_index in pending

    def test_refresh_handles_git_pull_failure(self, tmp_path, caplog):
        """
        Test that refresh handles git pull failure gracefully.

        AC6: Failed refresh handling - error logged, current index unchanged
        """
        import logging

        caplog.set_level(logging.ERROR)

        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", old_index)
        registry.register_global_repo(
            "test-repo", "test-repo-global", "https://github.com/test/repo", old_index
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.side_effect = RuntimeError("Network error")
            mock_updater_cls.return_value = mock_updater

            # Refresh should not raise exception
            scheduler.refresh_repo("test-repo-global")

            # Verify error was logged
            assert "Refresh failed" in caplog.text
            assert "test-repo-global" in caplog.text

            # Verify alias unchanged
            current_target = alias_mgr.read_alias("test-repo-global")
            assert current_target == old_index

    def test_scheduler_double_start_is_safe(self, tmp_path):
        """
        Test that calling start() twice is safe (idempotent).

        Error handling: Prevent duplicate threads
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        scheduler.start()
        scheduler.start()  # Should be no-op

        assert scheduler.is_running()

        scheduler.stop()

    def test_scheduler_double_stop_is_safe(self, tmp_path):
        """
        Test that calling stop() twice is safe (idempotent).
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        scheduler.start()
        scheduler.stop()
        scheduler.stop()  # Should be no-op

        assert not scheduler.is_running()

    def test_refresh_uses_meta_directory_updater_for_meta_repo(self, tmp_path):
        """
        Test that RefreshScheduler uses MetaDirectoryUpdater for meta-directory.

        CRITICAL: Meta-directory (repo_url=None) should use MetaDirectoryUpdater,
        not GitPullUpdater.

        This test will FAIL until RefreshScheduler is fixed to check repo_url.
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create meta-directory
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir()

        # Create alias and registry entry for meta-directory
        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("cidx-meta-global", str(meta_dir))
        registry.register_global_repo(
            "cidx-meta",
            "cidx-meta-global",
            None,  # Special marker for meta-directory
            str(meta_dir),
            allow_reserved=True,
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Mock MetaDirectoryUpdater
        with patch(
            "code_indexer.global_repos.refresh_scheduler.MetaDirectoryUpdater"
        ) as mock_meta_updater_cls:
            mock_meta_updater = MagicMock()
            mock_meta_updater.has_changes.return_value = False
            mock_meta_updater_cls.return_value = mock_meta_updater

            # Mock GitPullUpdater to ensure it's NOT called
            with patch(
                "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
            ) as mock_git_updater_cls:
                scheduler.refresh_repo("cidx-meta-global")

                # Verify MetaDirectoryUpdater was used
                # Check the call arguments (path and registry instance)
                assert mock_meta_updater_cls.call_count == 1
                call_args = mock_meta_updater_cls.call_args
                assert call_args[0][0] == str(meta_dir)  # First positional arg is path
                assert isinstance(call_args[0][1], GlobalRegistry)  # Second is registry
                mock_meta_updater.has_changes.assert_called_once()

                # Verify GitPullUpdater was NOT used
                mock_git_updater_cls.assert_not_called()

    def test_refresh_uses_git_pull_updater_for_normal_repos(self, tmp_path):
        """
        Test that RefreshScheduler uses GitPullUpdater for normal repos.

        Ensures that the meta-directory fix doesn't break normal repo refreshes.
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        registry = GlobalRegistry(str(golden_repos_dir))

        alias_mgr.create_alias("test-repo-global", str(repo_dir))
        registry.register_global_repo(
            "test-repo",
            "test-repo-global",
            "https://github.com/test/repo",  # Normal repo has URL
            str(repo_dir),
        )

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Mock GitPullUpdater
        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_git_updater_cls:
            mock_git_updater = MagicMock()
            mock_git_updater.has_changes.return_value = False
            mock_git_updater_cls.return_value = mock_git_updater

            # Mock MetaDirectoryUpdater to ensure it's NOT called
            with patch(
                "code_indexer.global_repos.refresh_scheduler.MetaDirectoryUpdater"
            ) as mock_meta_updater_cls:
                scheduler.refresh_repo("test-repo-global")

                # Verify GitPullUpdater was used
                mock_git_updater_cls.assert_called_once_with(str(repo_dir))
                mock_git_updater.has_changes.assert_called_once()

                # Verify MetaDirectoryUpdater was NOT used
                mock_meta_updater_cls.assert_not_called()
