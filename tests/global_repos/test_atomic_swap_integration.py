"""
Integration tests for atomic alias swapping with zero-downtime guarantees.

Tests AC4 and AC6:
- AC4: Zero-Downtime Query Guarantee
- AC6: Failed Refresh Handling
"""

import time
import threading
from unittest.mock import patch, MagicMock

from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.global_repos.alias_manager import AliasManager
from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.config import ConfigManager


class TestZeroDowntimeQueryGuarantee:
    """
    Integration tests for AC4: Zero-Downtime Query Guarantee.

    Validates that queries succeed throughout refresh cycle with no errors.
    """

    def test_query_before_swap_uses_old_index(self, tmp_path):
        """
        Test that query submitted before swap uses old index.

        AC4: Queries submitted before swap use old index
        """
        # Setup
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")
        new_index = str(repo_dir / "v_new")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        alias_mgr.create_alias("test-repo-global", old_index)

        tracker = QueryTracker()

        # Simulate query starting before swap
        with tracker.track_query(old_index):
            # Query reads old index
            current_alias = alias_mgr.read_alias("test-repo-global")
            assert current_alias == old_index

            # Swap occurs during query
            alias_mgr.swap_alias("test-repo-global", new_index, old_index)

            # Query continues using old index (snapshot at query start)
            # In real implementation, query would hold reference to old_index
            # and continue using it regardless of swap

        # After query completes, ref count drops to zero
        assert tracker.get_ref_count(old_index) == 0

    def test_query_after_swap_uses_new_index(self, tmp_path):
        """
        Test that query submitted after swap uses new index.

        AC4: Queries submitted after swap use new index
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")
        new_index = str(repo_dir / "v_new")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        alias_mgr.create_alias("test-repo-global", old_index)

        # Swap alias
        alias_mgr.swap_alias("test-repo-global", new_index, old_index)

        # Query starts after swap
        tracker = QueryTracker()
        with tracker.track_query(new_index):
            # Query uses new index
            current_alias = alias_mgr.read_alias("test-repo-global")
            assert current_alias == new_index

    def test_concurrent_queries_during_swap(self, tmp_path):
        """
        Test that concurrent queries continue during swap without errors.

        AC4: No queries fail or timeout during the swap
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        repo_dir = golden_repos_dir / "test-repo"
        repo_dir.mkdir()
        old_index = str(repo_dir / "v_old")
        new_index = str(repo_dir / "v_new")

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))
        alias_mgr.create_alias("test-repo-global", old_index)

        tracker = QueryTracker()
        query_results = []
        errors = []

        def simulate_query(query_id):
            """Simulate a query that reads alias during swap."""
            try:
                # Query reads current alias
                alias_path = alias_mgr.read_alias("test-repo-global")

                # Track query
                tracker.increment_ref(alias_path)
                time.sleep(0.05)  # Simulate query processing
                tracker.decrement_ref(alias_path)

                query_results.append((query_id, alias_path))
            except Exception as e:
                errors.append((query_id, str(e)))

        # Start multiple queries
        query_threads = []
        for i in range(10):
            t = threading.Thread(target=simulate_query, args=(i,))
            query_threads.append(t)
            t.start()
            time.sleep(0.01)  # Stagger query starts

            # Swap alias partway through
            if i == 5:
                alias_mgr.swap_alias("test-repo-global", new_index, old_index)

        # Wait for all queries to complete
        for t in query_threads:
            t.join()

        # Verify no errors occurred
        assert len(errors) == 0, f"Queries failed during swap: {errors}"

        # Verify queries got valid results (either old or new index)
        assert len(query_results) == 10
        for query_id, alias_path in query_results:
            assert alias_path in [old_index, new_index]

    def test_swap_completes_within_100ms(self, tmp_path):
        """
        Test that alias swap completes within 100ms.

        AC4: No query latency impact from refresh operations
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        alias_mgr = AliasManager(str(golden_repos_dir / "aliases"))

        old_index = str(tmp_path / "v_old")
        new_index = str(tmp_path / "v_new")

        alias_mgr.create_alias("test-global", old_index)

        # Measure swap time
        start = time.time()
        alias_mgr.swap_alias("test-global", new_index, old_index)
        duration = time.time() - start

        # Verify swap was fast (<100ms)
        assert duration < 0.1, f"Swap took {duration * 1000:.1f}ms, expected <100ms"

    def test_cleanup_waits_for_active_queries(self, tmp_path):
        """
        Test that cleanup waits for active queries to complete.

        AC3 + AC4: Query-aware cleanup with zero-downtime guarantee
        """
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create index directory
        index_path = tmp_path / "v_old"
        index_path.mkdir()
        (index_path / "test.txt").write_text("test")

        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Start query (increment ref count)
        tracker.increment_ref(str(index_path))

        # Schedule cleanup
        cleanup_mgr.schedule_cleanup(str(index_path))
        cleanup_mgr.start()

        # Wait (cleanup should NOT happen yet)
        time.sleep(0.3)

        # Verify directory still exists (query active)
        assert index_path.exists()

        # Complete query (decrement ref count)
        tracker.decrement_ref(str(index_path))

        # Wait for cleanup
        time.sleep(0.3)

        cleanup_mgr.stop()

        # Verify directory was deleted
        assert not index_path.exists()


class TestFailedRefreshHandling:
    """
    Integration tests for AC6: Failed Refresh Handling.

    Validates graceful error handling when refresh operations fail.
    """

    def test_network_failure_leaves_current_index_active(self, tmp_path, caplog):
        """
        Test that network failure during git pull leaves current index active.

        AC6: Current alias remains unchanged, users continue querying existing index
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
            config_manager=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Simulate network failure during git pull
        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.side_effect = RuntimeError("Network unreachable")
            mock_updater_cls.return_value = mock_updater

            # Refresh should not raise exception
            scheduler.refresh_repo("test-repo-global")

        # Verify error was logged
        assert "Refresh failed" in caplog.text

        # Verify alias unchanged
        current_target = alias_mgr.read_alias("test-repo-global")
        assert current_target == old_index

    def test_index_creation_failure_leaves_current_index_active(self, tmp_path, caplog):
        """
        Test that index creation failure leaves current index active.

        AC6: Current index remains active when new index creation fails
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
            config_manager=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Simulate failure during index creation
        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.return_value = True
            mock_updater.update.return_value = None
            mock_updater.get_source_path.return_value = str(repo_dir)
            mock_updater_cls.return_value = mock_updater

            with patch.object(scheduler, "_create_new_index") as mock_create_index:
                mock_create_index.side_effect = RuntimeError("Disk full")

                # Refresh should not raise exception
                scheduler.refresh_repo("test-repo-global")

        # Verify error was logged
        assert "Refresh failed" in caplog.text

        # Verify alias unchanged
        current_target = alias_mgr.read_alias("test-repo-global")
        assert current_target == old_index

    def test_no_retry_storm_after_failure(self, tmp_path, caplog):
        """
        Test that failed refresh does not trigger immediate retry.

        AC6: No retry storm occurs - wait for next scheduled cycle
        """
        import logging

        caplog.set_level(logging.ERROR)

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
            config_manager=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        failure_count = [0]

        def failing_has_changes():
            failure_count[0] += 1
            raise RuntimeError("Simulated failure")

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.side_effect = failing_has_changes
            mock_updater_cls.return_value = mock_updater

            # Call refresh multiple times
            scheduler.refresh_repo("test-repo-global")
            scheduler.refresh_repo("test-repo-global")
            scheduler.refresh_repo("test-repo-global")

        # Verify each call tried once (no internal retry storm)
        assert failure_count[0] == 3

    def test_error_logged_with_full_context(self, tmp_path, caplog):
        """
        Test that refresh errors are logged with full context.

        AC6: Log error with full context (repo, error type, message)
        """
        import logging

        caplog.set_level(logging.ERROR)

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
            config_manager=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        with patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_cls:
            mock_updater = MagicMock()
            mock_updater.has_changes.side_effect = RuntimeError(
                "Specific error message"
            )
            mock_updater_cls.return_value = mock_updater

            scheduler.refresh_repo("test-repo-global")

        # Verify log contains repo name and error message
        assert "test-repo-global" in caplog.text
        assert "Specific error message" in caplog.text
        assert "Refresh failed" in caplog.text
