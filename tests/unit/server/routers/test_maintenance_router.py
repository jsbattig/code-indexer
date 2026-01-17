"""Unit tests for maintenance router API endpoints.

Story #734: Job-Aware Auto-Update with Graceful Drain Mode

Tests AC1 enter/exit endpoints with admin authentication requirement.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with clean maintenance state."""
    from code_indexer.server.services.maintenance_service import (
        _reset_maintenance_state,
    )

    _reset_maintenance_state()

    from code_indexer.server.app import app

    return TestClient(app)


@pytest.fixture
def authenticated_client():
    """Create test client with mocked admin authentication."""
    from datetime import datetime, timezone
    from code_indexer.server.services.maintenance_service import (
        _reset_maintenance_state,
    )
    from code_indexer.server.auth.user_manager import User, UserRole
    from code_indexer.server.auth.dependencies import get_current_admin_user
    from code_indexer.server.app import app

    _reset_maintenance_state()

    admin_user = User(
        username="admin",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    app.dependency_overrides[get_current_admin_user] = lambda: admin_user

    yield TestClient(app)

    app.dependency_overrides.clear()


class TestMaintenanceEndpointsRequireAuth:
    """Test that all maintenance endpoints require admin authentication."""

    def test_enter_maintenance_requires_auth(self, client):
        """POST /api/admin/maintenance/enter should return 401 without auth."""
        response = client.post("/api/admin/maintenance/enter")
        assert response.status_code == 401

    def test_exit_maintenance_requires_auth(self, client):
        """POST /api/admin/maintenance/exit should return 401 without auth."""
        response = client.post("/api/admin/maintenance/exit")
        assert response.status_code == 401

    def test_status_requires_auth(self, client):
        """GET /api/admin/maintenance/status should return 401 without auth."""
        response = client.get("/api/admin/maintenance/status")
        assert response.status_code == 401

    def test_drain_status_requires_auth(self, client):
        """GET /api/admin/maintenance/drain-status should return 401 without auth."""
        response = client.get("/api/admin/maintenance/drain-status")
        assert response.status_code == 401


class TestMaintenanceEnterEndpoint:
    """Test POST /api/admin/maintenance/enter endpoint."""

    def test_enter_maintenance_returns_200(self, authenticated_client):
        """POST /api/admin/maintenance/enter should return 200 with auth."""
        response = authenticated_client.post("/api/admin/maintenance/enter")
        assert response.status_code == 200

    def test_enter_maintenance_response_format(self, authenticated_client):
        """Response should include maintenance_mode and job counts."""
        response = authenticated_client.post("/api/admin/maintenance/enter")
        data = response.json()

        assert data["maintenance_mode"] is True
        assert "running_jobs" in data
        assert "queued_jobs" in data
        assert "message" in data


class TestMaintenanceExitEndpoint:
    """Test POST /api/admin/maintenance/exit endpoint."""

    def test_exit_maintenance_returns_200(self, authenticated_client):
        """POST /api/admin/maintenance/exit should return 200 with auth."""
        authenticated_client.post("/api/admin/maintenance/enter")
        response = authenticated_client.post("/api/admin/maintenance/exit")
        assert response.status_code == 200

    def test_exit_maintenance_response_format(self, authenticated_client):
        """Response should include maintenance_mode false."""
        authenticated_client.post("/api/admin/maintenance/enter")
        response = authenticated_client.post("/api/admin/maintenance/exit")
        data = response.json()

        assert data["maintenance_mode"] is False
        assert "message" in data


class TestMaintenanceStatusEndpoint:
    """Test GET /api/admin/maintenance/status endpoint."""

    def test_status_returns_200(self, authenticated_client):
        """GET /api/admin/maintenance/status should return 200 with auth."""
        response = authenticated_client.get("/api/admin/maintenance/status")
        assert response.status_code == 200

    def test_status_response_format(self, authenticated_client):
        """Response should include maintenance_mode and drained."""
        authenticated_client.post("/api/admin/maintenance/enter")
        response = authenticated_client.get("/api/admin/maintenance/status")
        data = response.json()

        assert "maintenance_mode" in data
        assert "drained" in data
        assert "running_jobs" in data
        assert "queued_jobs" in data


class TestDrainStatusEndpoint:
    """Test GET /api/admin/maintenance/drain-status endpoint (AC2)."""

    def test_drain_status_returns_200(self, authenticated_client):
        """GET /api/admin/maintenance/drain-status should return 200 with auth."""
        response = authenticated_client.get("/api/admin/maintenance/drain-status")
        assert response.status_code == 200

    def test_drain_status_response_format(self, authenticated_client):
        """Response should include drained, running_jobs, queued_jobs, estimated_drain_seconds."""
        response = authenticated_client.get("/api/admin/maintenance/drain-status")
        data = response.json()

        assert "drained" in data
        assert "running_jobs" in data
        assert "queued_jobs" in data
        assert "estimated_drain_seconds" in data


class TestMaintenanceIdempotentBehavior:
    """Test idempotent behavior for enter/exit maintenance mode."""

    def test_enter_maintenance_is_idempotent(self, authenticated_client):
        """Calling enter twice should return 200 both times (idempotent)."""
        response1 = authenticated_client.post("/api/admin/maintenance/enter")
        assert response1.status_code == 200
        assert response1.json()["maintenance_mode"] is True

        response2 = authenticated_client.post("/api/admin/maintenance/enter")
        assert response2.status_code == 200
        assert response2.json()["maintenance_mode"] is True

    def test_exit_maintenance_is_idempotent(self, authenticated_client):
        """Calling exit twice should return 200 both times (idempotent)."""
        authenticated_client.post("/api/admin/maintenance/enter")

        response1 = authenticated_client.post("/api/admin/maintenance/exit")
        assert response1.status_code == 200
        assert response1.json()["maintenance_mode"] is False

        response2 = authenticated_client.post("/api/admin/maintenance/exit")
        assert response2.status_code == 200
        assert response2.json()["maintenance_mode"] is False

    def test_exit_without_enter_is_idempotent(self, authenticated_client):
        """Calling exit when not in maintenance mode should return 200 (idempotent)."""
        response = authenticated_client.post("/api/admin/maintenance/exit")
        assert response.status_code == 200
        assert response.json()["maintenance_mode"] is False
