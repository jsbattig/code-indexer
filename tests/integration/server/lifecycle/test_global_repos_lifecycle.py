"""
Integration tests for GlobalReposLifecycleManager.

Tests the complete lifecycle management for global repos background services:
- QueryTracker instantiation
- CleanupManager creation and lifecycle
- RefreshScheduler creation and lifecycle
- Graceful shutdown coordination
"""

import logging
import time
from pathlib import Path
from typing import Generator

import pytest

from code_indexer.server.lifecycle.global_repos_lifecycle import (
    GlobalReposLifecycleManager,
)
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.global_repos.refresh_scheduler import RefreshScheduler


logger = logging.getLogger(__name__)


@pytest.fixture
def golden_repos_dir(tmp_path: Path) -> Path:
    """Create temporary golden repos directory for testing."""
    repos_dir = tmp_path / "golden-repos"
    repos_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories needed by GlobalRepoOperations
    (repos_dir / "aliases").mkdir(exist_ok=True)
    (repos_dir / ".registry").mkdir(exist_ok=True)

    return repos_dir


@pytest.fixture
def lifecycle_manager(
    golden_repos_dir: Path,
) -> Generator[GlobalReposLifecycleManager, None, None]:
    """Create lifecycle manager for testing."""
    manager = GlobalReposLifecycleManager(str(golden_repos_dir))
    yield manager

    # Cleanup: Ensure manager is stopped
    if manager.is_running():
        manager.stop()


class TestGlobalReposLifecycleManager:
    """Test suite for GlobalReposLifecycleManager."""

    def test_initialization_creates_components(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that initialization creates all required components."""
        # QueryTracker should be created
        assert lifecycle_manager.query_tracker is not None
        assert isinstance(lifecycle_manager.query_tracker, QueryTracker)

        # CleanupManager should be created
        assert lifecycle_manager.cleanup_manager is not None
        assert isinstance(lifecycle_manager.cleanup_manager, CleanupManager)

        # RefreshScheduler should be created
        assert lifecycle_manager.refresh_scheduler is not None
        assert isinstance(lifecycle_manager.refresh_scheduler, RefreshScheduler)

    def test_start_starts_all_services(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that start() starts all background services."""
        # Verify not running initially
        assert not lifecycle_manager.is_running()
        assert not lifecycle_manager.cleanup_manager.is_running()
        assert not lifecycle_manager.refresh_scheduler.is_running()

        # Start services
        lifecycle_manager.start()

        # Verify all services are running
        assert lifecycle_manager.is_running()
        assert lifecycle_manager.cleanup_manager.is_running()
        assert lifecycle_manager.refresh_scheduler.is_running()

        # Cleanup
        lifecycle_manager.stop()

    def test_stop_stops_all_services(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that stop() stops all background services gracefully."""
        # Start services first
        lifecycle_manager.start()
        assert lifecycle_manager.is_running()

        # Stop services
        lifecycle_manager.stop()

        # Verify all services stopped
        assert not lifecycle_manager.is_running()
        assert not lifecycle_manager.cleanup_manager.is_running()
        assert not lifecycle_manager.refresh_scheduler.is_running()

    def test_start_is_idempotent(self, lifecycle_manager: GlobalReposLifecycleManager):
        """Test that calling start() multiple times is safe."""
        lifecycle_manager.start()
        first_running = lifecycle_manager.is_running()

        # Call start again
        lifecycle_manager.start()
        second_running = lifecycle_manager.is_running()

        # Should still be running, no errors
        assert first_running
        assert second_running

        # Cleanup
        lifecycle_manager.stop()

    def test_stop_is_idempotent(self, lifecycle_manager: GlobalReposLifecycleManager):
        """Test that calling stop() multiple times is safe."""
        lifecycle_manager.start()
        lifecycle_manager.stop()

        first_stopped = not lifecycle_manager.is_running()

        # Call stop again
        lifecycle_manager.stop()
        second_stopped = not lifecycle_manager.is_running()

        # Should still be stopped, no errors
        assert first_stopped
        assert second_stopped

    def test_query_tracker_tracks_queries(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that QueryTracker correctly tracks queries."""
        tracker = lifecycle_manager.query_tracker

        # Initially no references
        assert tracker.get_ref_count("/some/index/path") == 0

        # Track a query
        with tracker.track_query("/some/index/path"):
            # Should have reference while in context
            assert tracker.get_ref_count("/some/index/path") == 1

        # Reference should be released after context
        assert tracker.get_ref_count("/some/index/path") == 0

    def test_cleanup_manager_schedules_cleanup(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that CleanupManager schedules and processes cleanups."""
        lifecycle_manager.start()

        cleanup_mgr = lifecycle_manager.cleanup_manager
        test_path = "/fake/index/path"

        # Schedule cleanup
        cleanup_mgr.schedule_cleanup(test_path)

        # Verify path is in cleanup queue
        assert test_path in cleanup_mgr.get_pending_cleanups()

        # Cleanup
        lifecycle_manager.stop()

    def test_refresh_scheduler_respects_configuration(
        self, lifecycle_manager: GlobalReposLifecycleManager, golden_repos_dir: Path
    ):
        """Test that RefreshScheduler reads configuration correctly."""
        # Set custom refresh interval via GlobalRepoOperations
        from code_indexer.global_repos.shared_operations import GlobalRepoOperations

        ops = GlobalRepoOperations(str(golden_repos_dir))
        ops.set_config(refresh_interval=300)  # 5 minutes

        # Get interval from scheduler
        interval = lifecycle_manager.refresh_scheduler.get_refresh_interval()

        # Should match configured value
        assert interval == 300

    def test_graceful_shutdown_with_active_queries(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that shutdown waits for active queries to complete."""
        lifecycle_manager.start()

        tracker = lifecycle_manager.query_tracker
        test_path = "/test/index/path"

        # Simulate active query
        tracker.increment_ref(test_path)

        # Schedule cleanup while query is active
        lifecycle_manager.cleanup_manager.schedule_cleanup(test_path)

        # Stop should complete without errors
        lifecycle_manager.stop()

        # Verify services stopped cleanly
        assert not lifecycle_manager.is_running()
        assert not lifecycle_manager.cleanup_manager.is_running()
        assert not lifecycle_manager.refresh_scheduler.is_running()

    def test_components_share_query_tracker(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Test that CleanupManager uses the same QueryTracker instance."""
        # CleanupManager should use the shared QueryTracker
        assert (
            lifecycle_manager.cleanup_manager._query_tracker
            is lifecycle_manager.query_tracker
        )

    def test_startup_shutdown_integration(
        self, lifecycle_manager: GlobalReposLifecycleManager
    ):
        """Integration test of complete startup/shutdown cycle."""
        # Initial state: not running
        assert not lifecycle_manager.is_running()

        # Start: all services active
        lifecycle_manager.start()
        time.sleep(0.1)  # Allow threads to start

        assert lifecycle_manager.is_running()
        assert lifecycle_manager.cleanup_manager.is_running()
        assert lifecycle_manager.refresh_scheduler.is_running()

        # Stop: all services shut down gracefully
        lifecycle_manager.stop()
        time.sleep(0.1)  # Allow threads to stop

        assert not lifecycle_manager.is_running()
        assert not lifecycle_manager.cleanup_manager.is_running()
        assert not lifecycle_manager.refresh_scheduler.is_running()
