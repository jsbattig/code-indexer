"""Unit tests for MaintenanceState service - Core functionality.

Story #734: Job-Aware Auto-Update with Graceful Drain Mode
Tests AC1 (Server Maintenance Mode API) - Basic operations.
"""

import pytest
from unittest.mock import MagicMock


# Constants for thread safety tests
THREAD_COUNT = 5
ITERATIONS_PER_THREAD = 100


class TestMaintenanceStateBasics:
    """Test basic MaintenanceState functionality."""

    def test_singleton_pattern(self):
        """MaintenanceState should be a singleton."""
        from code_indexer.server.services.maintenance_service import (
            get_maintenance_state,
        )

        state1 = get_maintenance_state()
        state2 = get_maintenance_state()
        assert state1 is state2

    def test_initial_state_is_not_maintenance(self):
        """MaintenanceState should not be in maintenance mode initially."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()
        assert state.is_maintenance_mode() is False

    def test_enter_maintenance_mode(self):
        """Should be able to enter maintenance mode."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()

        result = state.enter_maintenance_mode()

        assert state.is_maintenance_mode() is True
        assert result["maintenance_mode"] is True
        assert "entered_at" in result

    def test_restart_clears_maintenance_mode(self):
        """AC5: Server restart (simulated via _reset) should clear maintenance mode."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        # Enter maintenance mode
        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()
        assert state.is_maintenance_mode() is True

        # Simulate server restart
        _reset_maintenance_state()

        # New state should NOT be in maintenance mode
        new_state = get_maintenance_state()
        assert new_state.is_maintenance_mode() is False
        assert new_state.get_status()["entered_at"] is None


class TestMaintenanceStateExitAndStatus:
    """Test exit and status operations."""

    def test_exit_maintenance_mode(self):
        """Should be able to exit maintenance mode."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        result = state.exit_maintenance_mode()

        assert state.is_maintenance_mode() is False
        assert result["maintenance_mode"] is False
        assert "message" in result

    def test_get_status_when_not_in_maintenance(self):
        """get_status should return correct info when not in maintenance."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()

        status = state.get_status()

        assert status["maintenance_mode"] is False
        assert status["entered_at"] is None
        assert "drained" in status

    def test_get_status_when_in_maintenance(self):
        """get_status should return correct info when in maintenance."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        status = state.get_status()

        assert status["maintenance_mode"] is True
        assert status["entered_at"] is not None
        assert "running_jobs" in status
        assert "queued_jobs" in status


class TestMaintenanceStateDrain:
    """Test drain status functionality (AC2)."""

    def test_is_drained_when_no_jobs(self):
        """System should be drained when no running or queued jobs."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        assert state.is_drained() is True

    def test_get_drain_status_response(self):
        """get_drain_status should return proper format."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()

        drain_status = state.get_drain_status()

        assert "drained" in drain_status
        assert "running_jobs" in drain_status
        assert "queued_jobs" in drain_status
        assert "estimated_drain_seconds" in drain_status

    def test_is_drained_with_running_jobs(self):
        """System should NOT be drained when running jobs exist."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )

        _reset_maintenance_state()
        state = get_maintenance_state()

        mock_tracker = MagicMock()
        mock_tracker.get_running_jobs_count.return_value = 1
        mock_tracker.get_queued_jobs_count.return_value = 0

        state.register_job_tracker(mock_tracker)
        state.enter_maintenance_mode()

        assert state.is_drained() is False


class TestSyncJobManagerMaintenanceIntegration:
    """Test SyncJobManager maintenance mode integration."""

    def test_sync_job_manager_rejects_during_maintenance(self):
        """SyncJobManager should raise error when in maintenance mode."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )
        from code_indexer.server.jobs.manager import SyncJobManager
        from code_indexer.server.jobs.models import JobType
        from code_indexer.server.jobs.exceptions import MaintenanceModeError

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        manager = SyncJobManager()

        with pytest.raises(MaintenanceModeError) as exc_info:
            manager.create_job(
                username="testuser",
                user_alias="Test User",
                job_type=JobType.REPOSITORY_SYNC,
            )

        assert "maintenance" in str(exc_info.value).lower()

    def test_background_job_manager_rejects_during_maintenance(self):
        """BackgroundJobManager should raise error when in maintenance mode."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )
        from code_indexer.server.jobs.exceptions import MaintenanceModeError

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        manager = BackgroundJobManager()

        def dummy_func():
            return {"status": "done"}

        with pytest.raises(MaintenanceModeError) as exc_info:
            manager.submit_job(
                operation_type="test_operation",
                func=dummy_func,
                submitter_username="testuser",
            )

        assert "maintenance" in str(exc_info.value).lower()

    def test_golden_repo_manager_add_rejects_during_maintenance(self):
        """GoldenRepoManager.add_golden_repo should raise error during maintenance."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )
        from code_indexer.server.jobs.exceptions import MaintenanceModeError
        import tempfile

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = GoldenRepoManager(data_dir=tmpdir)

            with pytest.raises(MaintenanceModeError) as exc_info:
                manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="test-repo",
                    submitter_username="testuser",
                )

            assert "maintenance" in str(exc_info.value).lower()

    def test_refresh_scheduler_job_submission_rejected_during_maintenance(self):
        """RefreshScheduler job submission via BackgroundJobManager is rejected during maintenance."""
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )
        from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )
        from code_indexer.server.jobs.exceptions import MaintenanceModeError
        from unittest.mock import MagicMock, patch
        import tempfile

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create real BackgroundJobManager (no mock)
            job_manager = BackgroundJobManager()

            # Create mock dependencies for RefreshScheduler
            mock_config = MagicMock()
            mock_query_tracker = MagicMock()
            mock_cleanup_manager = MagicMock()

            with patch(
                "code_indexer.server.utils.registry_factory.get_server_global_registry"
            ) as mock_get_registry:
                mock_registry = MagicMock()
                mock_get_registry.return_value = mock_registry

                scheduler = RefreshScheduler(
                    golden_repos_dir=tmpdir,
                    config_source=mock_config,
                    query_tracker=mock_query_tracker,
                    cleanup_manager=mock_cleanup_manager,
                    background_job_manager=job_manager,
                )

                # Verify that when scheduler tries to submit a job during maintenance,
                # BackgroundJobManager raises MaintenanceModeError
                with pytest.raises(MaintenanceModeError):
                    scheduler._submit_refresh_job("test-repo-global")


class TestHealthEndpointMaintenanceMode:
    """Test AC6: Health endpoint includes maintenance_mode field."""

    def test_health_endpoint_includes_maintenance_mode_false(self):
        """AC6: /health response should include maintenance_mode field (false when not in maintenance)."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
        )
        from code_indexer.server.auth.dependencies import get_current_user

        _reset_maintenance_state()
        app = create_app()

        # Create mock user for authentication bypass
        mock_user = MagicMock()
        mock_user.username = "test_admin"
        mock_user.role = "admin"

        # Override auth dependency
        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)

        # Check health endpoint
        health_response = client.get("/health")
        assert health_response.status_code == 200

        data = health_response.json()
        assert "maintenance_mode" in data
        assert data["maintenance_mode"] is False

        # Clean up
        app.dependency_overrides.clear()

    def test_health_endpoint_includes_maintenance_mode_true(self):
        """AC6: /health response should include maintenance_mode field (true when in maintenance)."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from code_indexer.server.services.maintenance_service import (
            _reset_maintenance_state,
            get_maintenance_state,
        )
        from code_indexer.server.auth.dependencies import get_current_user

        _reset_maintenance_state()
        state = get_maintenance_state()
        state.enter_maintenance_mode()

        app = create_app()

        # Create mock user for authentication bypass
        mock_user = MagicMock()
        mock_user.username = "test_admin"
        mock_user.role = "admin"

        # Override auth dependency
        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)

        # Check health endpoint
        health_response = client.get("/health")
        assert health_response.status_code == 200

        data = health_response.json()
        assert "maintenance_mode" in data
        assert data["maintenance_mode"] is True

        # Clean up
        app.dependency_overrides.clear()
