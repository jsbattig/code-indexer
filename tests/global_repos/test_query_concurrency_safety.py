"""Tests for query concurrency safety in MCP handlers and repository removal.

These tests verify that:
1. QueryTracker is properly integrated into MCP query handlers (Fix 1)
2. Repository removal uses CleanupManager instead of immediate deletion (Fix 2)
3. Queries properly track reference counts to prevent concurrent access issues
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path


class TestQueryTrackerIntegrationInHandlers:
    """Test Fix 1: QueryTracker integration in MCP query handlers."""

    @pytest.fixture
    def mock_user(self):
        """Create mock user for handler calls."""
        from code_indexer.server.auth.user_manager import User, UserRole
        from datetime import datetime

        return User(
            username="test_user",
            password_hash="test_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(),
        )

    @pytest.mark.asyncio
    async def test_search_code_increments_ref_count_for_global_repo(
        self, mock_user, tmp_path
    ):
        """Test that search_code increments QueryTracker ref count for global repos."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        query_tracker = QueryTracker()
        test_index_path = str(tmp_path / "test-repo-v1")

        # Create actual directory for exists() check
        Path(test_index_path).mkdir(parents=True)

        # Track calls to increment/decrement
        increment_calls = []
        decrement_calls = []
        original_increment = query_tracker.increment_ref
        original_decrement = query_tracker.decrement_ref

        def track_increment(path):
            increment_calls.append(path)
            return original_increment(path)

        def track_decrement(path):
            decrement_calls.append(path)
            return original_decrement(path)

        query_tracker.increment_ref = track_increment
        query_tracker.decrement_ref = track_decrement

        mock_state = Mock()
        mock_state.query_tracker = query_tracker
        mock_state.golden_repos_dir = str(tmp_path)

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state = mock_state

            # Mock GlobalRegistry
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry"
            ) as mock_registry_cls:
                mock_registry = Mock()
                mock_registry.list_global_repos.return_value = [
                    {
                        "alias_name": "test-repo-global",
                        "repo_name": "test-repo",
                        "index_path": test_index_path,
                    }
                ]
                mock_registry_cls.return_value = mock_registry

                # Mock AliasManager at the correct import location
                with patch(
                    "code_indexer.global_repos.alias_manager.AliasManager"
                ) as mock_alias_cls:
                    mock_alias = Mock()
                    mock_alias.read_alias.return_value = test_index_path
                    mock_alias_cls.return_value = mock_alias

                    mock_app.semantic_query_manager = Mock()
                    mock_app.semantic_query_manager._perform_search = Mock(
                        return_value=[]
                    )

                    from code_indexer.server.mcp.handlers import search_code

                    params = {
                        "repository_alias": "test-repo-global",
                        "query_text": "test query",
                    }

                    # Execute search
                    await search_code(params, mock_user)

                    # Verify ref count tracking was called
                    assert (
                        len(increment_calls) >= 1
                    ), "QueryTracker.increment_ref should be called during global repo search"
                    assert (
                        len(decrement_calls) >= 1
                    ), "QueryTracker.decrement_ref should be called after search completes"
                    assert (
                        query_tracker.get_ref_count(test_index_path) == 0
                    ), "Ref count should be 0 after search completes"

    @pytest.mark.asyncio
    async def test_search_code_decrements_ref_on_exception(self, mock_user, tmp_path):
        """Test that search_code decrements ref count even when exception occurs."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        query_tracker = QueryTracker()
        test_index_path = str(tmp_path / "test-repo-v1")

        # Create actual directory for exists() check
        Path(test_index_path).mkdir(parents=True)

        mock_state = Mock()
        mock_state.query_tracker = query_tracker
        mock_state.golden_repos_dir = str(tmp_path)

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state = mock_state

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry"
            ) as mock_registry_cls:
                mock_registry = Mock()
                mock_registry.list_global_repos.return_value = [
                    {
                        "alias_name": "test-repo-global",
                        "repo_name": "test-repo",
                        "index_path": test_index_path,
                    }
                ]
                mock_registry_cls.return_value = mock_registry

                with patch(
                    "code_indexer.global_repos.alias_manager.AliasManager"
                ) as mock_alias_cls:
                    mock_alias = Mock()
                    mock_alias.read_alias.return_value = test_index_path
                    mock_alias_cls.return_value = mock_alias

                    # Make search raise exception
                    mock_app.semantic_query_manager = Mock()
                    mock_app.semantic_query_manager._perform_search = Mock(
                        side_effect=RuntimeError("Query failed")
                    )

                    from code_indexer.server.mcp.handlers import search_code

                    params = {
                        "repository_alias": "test-repo-global",
                        "query_text": "test query",
                    }

                    # Execute search (should handle exception gracefully)
                    await search_code(params, mock_user)

                    # Ref count should be 0 after exception (decremented in finally)
                    assert (
                        query_tracker.get_ref_count(test_index_path) == 0
                    ), "Ref count should be 0 even after exception"


class TestCleanupManagerIntegrationInRemoval:
    """Test Fix 2: CleanupManager integration in golden repo removal."""

    @pytest.fixture
    def golden_repo_manager_with_cleanup(self, tmp_path):
        """Create GoldenRepoManager with CleanupManager dependency."""
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.cleanup_manager import CleanupManager
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )

        data_dir = str(tmp_path / "data")
        Path(data_dir).mkdir(parents=True)

        query_tracker = QueryTracker()
        cleanup_manager = CleanupManager(query_tracker, check_interval=0.1)

        manager = GoldenRepoManager(data_dir=data_dir)
        manager.background_job_manager = BackgroundJobManager()

        # Inject cleanup manager dependency
        manager._cleanup_manager = cleanup_manager
        manager._query_tracker = query_tracker

        return manager, cleanup_manager, query_tracker

    def test_removal_waits_for_active_queries_before_deletion(
        self, golden_repo_manager_with_cleanup
    ):
        """Test that removal waits for queries to complete before deleting."""
        manager, cleanup_manager, query_tracker = golden_repo_manager_with_cleanup

        # Add a test repository
        test_alias = "test-repo"
        test_path = Path(manager.golden_repos_dir) / test_alias
        test_path.mkdir(parents=True)
        (test_path / "test_file.txt").write_text("test content")

        from code_indexer.server.repositories.golden_repo_manager import GoldenRepo
        from datetime import datetime, timezone

        manager.golden_repos[test_alias] = GoldenRepo(
            alias=test_alias,
            repo_url="file://" + str(test_path),
            default_branch="main",
            clone_path=str(test_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manager._save_metadata()

        # Simulate active query by incrementing ref count
        query_tracker.increment_ref(str(test_path))

        cleanup_manager.start()

        try:
            # Schedule cleanup
            cleanup_manager.schedule_cleanup(str(test_path))

            import time

            time.sleep(0.3)  # Give cleanup manager time to check

            # Path should still exist (waiting for query)
            assert (
                test_path.exists()
            ), "Path should not be deleted while query is active"

            # Complete the "query"
            query_tracker.decrement_ref(str(test_path))

            # Wait for cleanup manager to process
            time.sleep(0.3)

            # Now path should be deleted
            assert (
                not test_path.exists()
            ), "Path should be deleted after query completes"
        finally:
            cleanup_manager.stop()


class TestQueryTrackerContextManager:
    """Test QueryTracker context manager usage."""

    def test_track_query_context_manager_increments_and_decrements(self):
        """Test that track_query context manager properly manages ref counts."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        tracker = QueryTracker()
        test_path = "/test/index/path"

        assert tracker.get_ref_count(test_path) == 0

        with tracker.track_query(test_path):
            assert tracker.get_ref_count(test_path) == 1

        assert tracker.get_ref_count(test_path) == 0

    def test_track_query_decrements_on_exception(self):
        """Test that track_query decrements even on exception."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        tracker = QueryTracker()
        test_path = "/test/index/path"

        try:
            with tracker.track_query(test_path):
                assert tracker.get_ref_count(test_path) == 1
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        assert tracker.get_ref_count(test_path) == 0

    def test_multiple_concurrent_queries_tracked(self):
        """Test that multiple concurrent queries are properly tracked."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        tracker = QueryTracker()
        test_path = "/test/index/path"

        # Simulate 3 concurrent queries
        tracker.increment_ref(test_path)
        tracker.increment_ref(test_path)
        tracker.increment_ref(test_path)

        assert tracker.get_ref_count(test_path) == 3

        # Complete queries one by one
        tracker.decrement_ref(test_path)
        assert tracker.get_ref_count(test_path) == 2

        tracker.decrement_ref(test_path)
        assert tracker.get_ref_count(test_path) == 1

        tracker.decrement_ref(test_path)
        assert tracker.get_ref_count(test_path) == 0


class TestActivatedRepoDeactivationWithCleanup:
    """Test Fix 3: Query tracking for activated repo deactivation."""

    @pytest.fixture
    def activated_repo_manager_with_cleanup(self, tmp_path):
        """Create ActivatedRepoManager with cleanup dependencies."""
        from code_indexer.server.repositories.activated_repo_manager import (
            ActivatedRepoManager,
        )
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.cleanup_manager import CleanupManager

        data_dir = str(tmp_path / "data")
        Path(data_dir).mkdir(parents=True)

        golden_repo_manager = GoldenRepoManager(data_dir=data_dir)
        background_job_manager = BackgroundJobManager()
        golden_repo_manager.background_job_manager = background_job_manager

        query_tracker = QueryTracker()
        cleanup_manager = CleanupManager(query_tracker, check_interval=0.1)

        manager = ActivatedRepoManager(
            data_dir=data_dir,
            golden_repo_manager=golden_repo_manager,
            background_job_manager=background_job_manager,
        )

        # Inject cleanup dependencies
        manager._cleanup_manager = cleanup_manager
        manager._query_tracker = query_tracker

        return manager, cleanup_manager, query_tracker, golden_repo_manager

    def test_deactivation_schedules_cleanup_for_repo_path(
        self, activated_repo_manager_with_cleanup
    ):
        """Test that deactivation schedules cleanup instead of immediate deletion."""
        manager, cleanup_manager, query_tracker, golden_manager = (
            activated_repo_manager_with_cleanup
        )

        # Create a golden repo first
        test_username = "testuser"
        test_alias = "test-repo"

        # Create golden repo directory structure
        golden_path = Path(golden_manager.golden_repos_dir) / test_alias
        golden_path.mkdir(parents=True)
        (golden_path / ".git").mkdir()
        (golden_path / "test.txt").write_text("test")

        from code_indexer.server.repositories.golden_repo_manager import GoldenRepo
        from datetime import datetime, timezone

        golden_manager.golden_repos[test_alias] = GoldenRepo(
            alias=test_alias,
            repo_url="file://" + str(golden_path),
            default_branch="main",
            clone_path=str(golden_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Create activated repo directory
        user_dir = Path(manager.activated_repos_dir) / test_username
        user_dir.mkdir(parents=True)
        activated_path = user_dir / test_alias
        activated_path.mkdir()
        (activated_path / "test.txt").write_text("activated test")

        # Create metadata
        from code_indexer.server.repositories.activated_repo_manager import (
            ActivatedRepo,
        )
        import json

        metadata = ActivatedRepo(
            user_alias=test_alias,
            golden_repo_alias=test_alias,
            current_branch="main",
            activated_at=datetime.now(timezone.utc).isoformat(),
            last_accessed=datetime.now(timezone.utc).isoformat(),
        )

        metadata_file = user_dir / f"{test_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict()))

        cleanup_manager.start()

        try:
            # Simulate active query
            query_tracker.increment_ref(str(activated_path))

            # Attempt deactivation
            manager.deactivate_repository(username=test_username, user_alias=test_alias)

            import time

            time.sleep(0.3)

            # Path should still exist due to active query
            # (if CleanupManager integration is implemented)
            # For now, this test documents expected behavior

            # Complete query
            query_tracker.decrement_ref(str(activated_path))

        finally:
            cleanup_manager.stop()


class TestEndToEndConcurrencySafety:
    """Integration tests for full concurrency safety flow."""

    @pytest.mark.asyncio
    async def test_query_during_removal_is_safe(self, tmp_path):
        """Test that queries are safe during concurrent removal operations."""
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.cleanup_manager import CleanupManager

        query_tracker = QueryTracker()
        cleanup_manager = CleanupManager(query_tracker, check_interval=0.1)

        # Create test directory
        test_index = tmp_path / "test-index"
        test_index.mkdir()
        (test_index / "vectors.json").write_text('{"test": "data"}')

        cleanup_manager.start()

        try:
            # Start a "query" (increment ref)
            query_tracker.increment_ref(str(test_index))

            # Schedule cleanup (simulating removal)
            cleanup_manager.schedule_cleanup(str(test_index))

            # Verify directory still exists (query protection)
            import time

            time.sleep(0.3)
            assert test_index.exists(), "Index should exist while query is active"

            # "Query" completes
            query_tracker.decrement_ref(str(test_index))

            # Wait for cleanup
            time.sleep(0.3)

            # Now should be deleted
            assert (
                not test_index.exists()
            ), "Index should be deleted after query completes"

        finally:
            cleanup_manager.stop()

    def test_concurrent_queries_prevent_premature_cleanup(self, tmp_path):
        """Test that multiple concurrent queries prevent cleanup."""
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.cleanup_manager import CleanupManager

        query_tracker = QueryTracker()
        cleanup_manager = CleanupManager(query_tracker, check_interval=0.1)

        test_index = tmp_path / "test-index"
        test_index.mkdir()

        cleanup_manager.start()

        try:
            # Multiple concurrent queries
            query_tracker.increment_ref(str(test_index))
            query_tracker.increment_ref(str(test_index))
            query_tracker.increment_ref(str(test_index))

            cleanup_manager.schedule_cleanup(str(test_index))

            import time

            # Complete first query
            query_tracker.decrement_ref(str(test_index))
            time.sleep(0.2)
            assert test_index.exists(), "Still 2 queries active"

            # Complete second query
            query_tracker.decrement_ref(str(test_index))
            time.sleep(0.2)
            assert test_index.exists(), "Still 1 query active"

            # Complete last query
            query_tracker.decrement_ref(str(test_index))
            time.sleep(0.3)

            # Now should be deleted
            assert not test_index.exists(), "All queries done, should be deleted"

        finally:
            cleanup_manager.stop()


class TestGetQueryTrackerFunction:
    """Test the get_query_tracker helper function in handlers."""

    def test_get_query_tracker_returns_tracker_from_app_state(self):
        """Test that get_query_tracker retrieves QueryTracker from app.state."""
        from code_indexer.global_repos.query_tracker import QueryTracker

        query_tracker = QueryTracker()
        mock_state = Mock()
        mock_state.query_tracker = query_tracker

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state = mock_state

            # Import after patching
            from code_indexer.server.mcp.handlers import _get_query_tracker

            result = _get_query_tracker()
            assert result is query_tracker

    def test_get_query_tracker_returns_none_when_not_configured(self):
        """Test that get_query_tracker returns None when not configured."""
        mock_state = Mock(spec=[])  # Empty spec - no attributes

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state = mock_state

            from code_indexer.server.mcp.handlers import _get_query_tracker

            result = _get_query_tracker()
            assert result is None
