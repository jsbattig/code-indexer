"""
Unit tests for SCIP workspace cleanup admin endpoints (Story #647 - AC4, AC5).

Tests admin API endpoints for workspace cleanup:
- AC4: POST /api/admin/scip-cleanup-workspaces - Manual cleanup trigger
- AC5: GET /api/admin/scip-cleanup-status - Cleanup status visibility

TDD Approach: Tests written FIRST, endpoints implemented to pass tests.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.workspace_cleanup_service import CleanupResult


@pytest.mark.e2e
class TestSCIPCleanupWorkspacesEndpointAC4:
    """AC4: Manual Cleanup Trigger endpoint tests."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.workspace_cleanup_service")
    def test_cleanup_workspaces_success_returns_200(
        self, mock_cleanup_service, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given admin authentication
        When POST /api/admin/scip-cleanup-workspaces is called
        Then it should return 200 with cleanup summary
        """
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock cleanup result
        cleanup_result = CleanupResult(
            workspaces_scanned=5,
            workspaces_deleted=2,
            workspaces_preserved=3,
            space_reclaimed_bytes=1024 * 1024 * 100,  # 100 MB
            errors=[],
            skipped=[],
            duration_seconds=1.5,
        )
        mock_cleanup_service.cleanup_workspaces.return_value = cleanup_result

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post("/api/admin/scip-cleanup-workspaces", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        # Verify response structure
        assert "deleted_count" in response_data
        assert "preserved_count" in response_data
        assert "space_freed_mb" in response_data
        assert "errors" in response_data

        # Verify response values
        assert response_data["deleted_count"] == 2
        assert response_data["preserved_count"] == 3
        assert response_data["space_freed_mb"] == 100.0
        assert response_data["errors"] == []

        # Verify cleanup_workspaces was called
        mock_cleanup_service.cleanup_workspaces.assert_called_once()

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.workspace_cleanup_service")
    def test_cleanup_workspaces_with_errors_returns_200_with_error_details(
        self, mock_cleanup_service, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given cleanup encounters errors
        When POST /api/admin/scip-cleanup-workspaces is called
        Then it should return 200 with error details in response
        """
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock cleanup result with errors
        cleanup_result = CleanupResult(
            workspaces_scanned=5,
            workspaces_deleted=2,
            workspaces_preserved=2,
            space_reclaimed_bytes=1024 * 1024 * 50,
            errors=["Failed to delete workspace cidx-scip-job123"],
            skipped=[],
            duration_seconds=1.5,
        )
        mock_cleanup_service.cleanup_workspaces.return_value = cleanup_result

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post("/api/admin/scip-cleanup-workspaces", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["deleted_count"] == 2
        assert response_data["preserved_count"] == 2
        assert len(response_data["errors"]) == 1
        assert "cidx-scip-job123" in response_data["errors"][0]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_cleanup_workspaces_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given non-admin user authentication
        When POST /api/admin/scip-cleanup-workspaces is called
        Then it should return 403 Forbidden
        """
        # Setup authentication for power user
        mock_jwt_manager.validate_token.return_value = {
            "username": "poweruser",
            "role": "power_user",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = power_user

        headers = {"Authorization": "Bearer power.jwt.token"}
        response = client.post("/api/admin/scip-cleanup-workspaces", headers=headers)

        assert response.status_code == 403

    def test_cleanup_workspaces_no_auth_returns_401(self, client):
        """
        Given no authentication
        When POST /api/admin/scip-cleanup-workspaces is called
        Then it should return 401 Unauthorized
        """
        response = client.post("/api/admin/scip-cleanup-workspaces")

        assert response.status_code == 401
        assert "www-authenticate" in response.headers


@pytest.mark.e2e
class TestSCIPCleanupStatusEndpointAC5:
    """AC5: Cleanup Status Visibility endpoint tests."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.workspace_cleanup_service")
    def test_get_cleanup_status_success_returns_200(
        self, mock_cleanup_service, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given admin authentication
        When GET /api/admin/scip-cleanup-status is called
        Then it should return 200 with cleanup status
        """
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock status result
        status_result = {
            "last_cleanup_time": "2024-12-31T10:00:00+00:00",
            "workspace_count": 5,
            "oldest_workspace_age": 10.5,
            "total_size_mb": 150.25,
        }
        mock_cleanup_service.get_cleanup_status.return_value = status_result

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.get("/api/admin/scip-cleanup-status", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        # Verify response structure matches status result
        assert "last_cleanup_time" in response_data
        assert "workspace_count" in response_data
        assert "oldest_workspace_age" in response_data
        assert "total_size_mb" in response_data

        # Verify response values
        assert response_data["last_cleanup_time"] == "2024-12-31T10:00:00+00:00"
        assert response_data["workspace_count"] == 5
        assert response_data["oldest_workspace_age"] == 10.5
        assert response_data["total_size_mb"] == 150.25

        # Verify get_cleanup_status was called
        mock_cleanup_service.get_cleanup_status.assert_called_once()

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.workspace_cleanup_service")
    def test_get_cleanup_status_before_first_cleanup_returns_null_time(
        self, mock_cleanup_service, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given cleanup has never run
        When GET /api/admin/scip-cleanup-status is called
        Then last_cleanup_time should be null
        """
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock status result with null last_cleanup_time
        status_result = {
            "last_cleanup_time": None,
            "workspace_count": 3,
            "oldest_workspace_age": 5.0,
            "total_size_mb": 50.0,
        }
        mock_cleanup_service.get_cleanup_status.return_value = status_result

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.get("/api/admin/scip-cleanup-status", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["last_cleanup_time"] is None
        assert response_data["workspace_count"] == 3

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_get_cleanup_status_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """
        Given non-admin user authentication
        When GET /api/admin/scip-cleanup-status is called
        Then it should return 403 Forbidden
        """
        # Setup authentication for power user
        mock_jwt_manager.validate_token.return_value = {
            "username": "poweruser",
            "role": "power_user",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = power_user

        headers = {"Authorization": "Bearer power.jwt.token"}
        response = client.get("/api/admin/scip-cleanup-status", headers=headers)

        assert response.status_code == 403

    def test_get_cleanup_status_no_auth_returns_401(self, client):
        """
        Given no authentication
        When GET /api/admin/scip-cleanup-status is called
        Then it should return 401 Unauthorized
        """
        response = client.get("/api/admin/scip-cleanup-status")

        assert response.status_code == 401
        assert "www-authenticate" in response.headers
