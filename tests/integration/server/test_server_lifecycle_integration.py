"""
Integration tests for server lifecycle with GlobalReposLifecycleManager.

Tests that the server starts up correctly with all background services
and makes QueryTracker accessible via app.state.
"""

import logging
import os
import time
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.server.lifecycle.global_repos_lifecycle import (
    GlobalReposLifecycleManager,
)


logger = logging.getLogger(__name__)


@pytest.fixture
def test_server_data_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create temporary server data directory for testing."""
    server_data_dir = tmp_path / "cidx-server"
    server_data_dir.mkdir(parents=True, exist_ok=True)

    # Set environment variable for server
    old_env = os.environ.get("CIDX_SERVER_DATA_DIR")
    os.environ["CIDX_SERVER_DATA_DIR"] = str(server_data_dir)

    yield server_data_dir

    # Cleanup environment
    if old_env is not None:
        os.environ["CIDX_SERVER_DATA_DIR"] = old_env
    else:
        os.environ.pop("CIDX_SERVER_DATA_DIR", None)


@pytest.fixture
def test_client(test_server_data_dir: Path) -> Generator[TestClient, None, None]:
    """Create test client with server lifecycle."""
    app = create_app()

    with TestClient(app) as client:
        yield client


class TestServerLifecycleIntegration:
    """Test suite for server lifecycle integration."""

    def test_server_starts_with_lifecycle_manager(self, test_client: TestClient):
        """Test that server starts successfully with GlobalReposLifecycleManager."""
        # Access app through test client
        app = test_client.app

        # Verify lifecycle manager is in app state
        assert hasattr(app.state, "global_lifecycle_manager")
        assert app.state.global_lifecycle_manager is not None
        assert isinstance(
            app.state.global_lifecycle_manager, GlobalReposLifecycleManager
        )

    def test_query_tracker_accessible_via_app_state(self, test_client: TestClient):
        """Test that QueryTracker is accessible via app.state."""
        app = test_client.app

        # Verify query tracker is in app state
        assert hasattr(app.state, "query_tracker")
        assert app.state.query_tracker is not None
        assert isinstance(app.state.query_tracker, QueryTracker)

    def test_background_services_are_running(self, test_client: TestClient):
        """Test that background services are running after startup."""
        app = test_client.app
        lifecycle_manager = app.state.global_lifecycle_manager

        # Verify lifecycle manager is running
        assert lifecycle_manager.is_running()

        # Verify individual services are running
        assert lifecycle_manager.cleanup_manager.is_running()
        assert lifecycle_manager.refresh_scheduler.is_running()

    def test_query_tracker_works_from_app_state(self, test_client: TestClient):
        """Test that QueryTracker from app.state works correctly."""
        app = test_client.app
        tracker = app.state.query_tracker

        test_path = "/test/index/path"

        # Initially no references
        assert tracker.get_ref_count(test_path) == 0

        # Track a query
        with tracker.track_query(test_path):
            assert tracker.get_ref_count(test_path) == 1

        # Reference released
        assert tracker.get_ref_count(test_path) == 0

    def test_services_remain_active_after_app_creation(self, test_client: TestClient):
        """Test that background services remain active after app creation."""
        app = test_client.app
        lifecycle_manager = app.state.global_lifecycle_manager

        # Wait a moment to ensure services are stable
        time.sleep(0.1)

        # Verify services are still running
        assert lifecycle_manager.is_running()
        assert lifecycle_manager.cleanup_manager.is_running()
        assert lifecycle_manager.refresh_scheduler.is_running()

    def test_server_shutdown_stops_services(self, test_server_data_dir: Path):
        """Test that server shutdown stops all background services."""
        app = create_app()

        # Start server in context
        with TestClient(app):
            lifecycle_manager = app.state.global_lifecycle_manager

            # Verify services are running
            assert lifecycle_manager.is_running()
            assert lifecycle_manager.cleanup_manager.is_running()
            assert lifecycle_manager.refresh_scheduler.is_running()

        # After context exit, services should be stopped
        # Give a small grace period for shutdown
        time.sleep(0.2)

        assert not lifecycle_manager.is_running()
        assert not lifecycle_manager.cleanup_manager.is_running()
        assert not lifecycle_manager.refresh_scheduler.is_running()

    def test_multiple_requests_share_query_tracker(self, test_client: TestClient):
        """Test that multiple requests share the same QueryTracker instance."""
        app = test_client.app

        # Get tracker from app state
        tracker1 = app.state.query_tracker

        # Make a request (any request that accesses app)
        test_client.get("/health")

        # Get tracker again
        tracker2 = app.state.query_tracker

        # Should be the same instance
        assert tracker1 is tracker2

    def test_lifecycle_manager_persists_across_operations(
        self, test_client: TestClient
    ):
        """Test that lifecycle manager persists and remains stable."""
        app = test_client.app

        # Get lifecycle manager
        manager_before = app.state.global_lifecycle_manager

        # Simulate some operations with query tracker
        tracker = app.state.query_tracker
        for i in range(5):
            test_path = f"/test/path/{i}"
            with tracker.track_query(test_path):
                pass

        # Get lifecycle manager again
        manager_after = app.state.global_lifecycle_manager

        # Should be the same instance
        assert manager_before is manager_after

        # Should still be running
        assert manager_after.is_running()
