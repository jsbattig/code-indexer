"""
Unit tests for Admin Audit Logs.

Story #710: Admin User and Group Management Interface

This file covers:
- AC7: Audit Log for Administrative Actions - Create audit_logs table
- AC8: Get Audit Logs - GET /api/v1/audit-logs with filters

TDD: These tests are written FIRST, before implementation.
"""

import sqlite3
import time
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_indexer.server.services.group_access_manager import GroupAccessManager


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_manager(temp_db_path):
    """Create a GroupAccessManager instance."""
    return GroupAccessManager(temp_db_path)


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.username = "admin_user"
    user.role = "admin"
    return user


@pytest.fixture
def test_client(group_manager, mock_admin_user):
    """Create a test client with mocked dependencies."""
    from code_indexer.server.routers.groups import (
        router as groups_router,
        users_router,
        audit_router,
        set_group_manager,
        get_group_manager,
    )
    from code_indexer.server.auth.dependencies import (
        get_current_admin_user,
        get_current_user,
    )

    app = FastAPI()
    app.include_router(groups_router)
    app.include_router(users_router)
    app.include_router(audit_router)

    set_group_manager(group_manager)

    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_group_manager] = lambda: group_manager

    yield TestClient(app)

    app.dependency_overrides.clear()


class TestAC7AuditLogTable:
    """
    AC7: Audit Log for Administrative Actions
    - Create audit_logs table in groups.db
    - Log actions: user_group_change, repo_access_grant, repo_access_revoke,
                   group_create, group_delete
    - Fields: timestamp, admin_id, action_type, target_type, target_id, details
    """

    def test_audit_logs_table_exists(self, group_manager):
        """Test that audit_logs table is created in schema."""
        conn = sqlite3.connect(str(group_manager.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "audit_logs"

    def test_audit_logs_table_has_required_columns(self, group_manager):
        """Test that audit_logs table has all required columns."""
        conn = sqlite3.connect(str(group_manager.db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audit_logs)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        required = {
            "id",
            "timestamp",
            "admin_id",
            "action_type",
            "target_type",
            "target_id",
            "details",
        }
        assert required.issubset(columns)


class TestAC7AuditLogRecording:
    """Test that administrative actions are logged."""

    def test_log_user_group_change(self, test_client, group_manager):
        """Test that user group changes are logged."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        group_manager.assign_user_to_group("testuser", admins.id, "admin_user")

        # Move user via API
        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )

        # Check audit log
        logs, total = group_manager.get_audit_logs(action_type="user_group_change")
        assert len(logs) > 0
        log = logs[0]
        assert log["action_type"] == "user_group_change"
        assert log["admin_id"] == "admin_user"

    def test_log_repo_access_grant(self, test_client, group_manager):
        """Test that repo access grants are logged."""
        admins = group_manager.get_group_by_name("admins")

        # Add repo via API
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        # Check audit log
        logs, total = group_manager.get_audit_logs(action_type="repo_access_grant")
        assert len(logs) > 0

    def test_log_repo_access_revoke(self, test_client, group_manager):
        """Test that repo access revocations are logged."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("test-repo", admins.id, "admin_user")

        # Remove repo via API
        test_client.request(
            "DELETE", f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        # Check audit log
        logs, total = group_manager.get_audit_logs(action_type="repo_access_revoke")
        assert len(logs) > 0

    def test_log_group_create(self, test_client, group_manager):
        """Test that group creation is logged."""
        # Create group via API
        test_client.post(
            "/api/v1/groups", json={"name": "test-group", "description": "Test group"}
        )

        # Check audit log
        logs, total = group_manager.get_audit_logs(action_type="group_create")
        assert len(logs) > 0

    def test_log_group_delete(self, test_client, group_manager):
        """Test that group deletion is logged."""
        # Create and then delete a group
        custom_group = group_manager.create_group("deletable", "To be deleted")

        test_client.delete(f"/api/v1/groups/{custom_group.id}")

        # Check audit log
        logs, total = group_manager.get_audit_logs(action_type="group_delete")
        assert len(logs) > 0

    def test_audit_log_has_required_fields(self, test_client, group_manager):
        """Test that audit log entries have all required fields."""
        admins = group_manager.get_group_by_name("admins")

        # Perform an action
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        logs, total = group_manager.get_audit_logs()
        assert len(logs) > 0
        log = logs[0]

        # AC7 required fields
        assert "timestamp" in log
        assert "admin_id" in log
        assert "action_type" in log
        assert "target_type" in log
        assert "target_id" in log
        assert "details" in log


class TestAC8GetAuditLogsEndpoint:
    """
    AC8: Get Audit Logs
    - GET /api/v1/audit-logs with optional filters
    - Filters: action_type, target_type, admin_id, date_from, date_to
    - Pagination support
    - Sorted by timestamp descending
    """

    def test_get_audit_logs_returns_200(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs returns 200."""
        # Perform some action to generate logs
        admins = group_manager.get_group_by_name("admins")
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        response = test_client.get("/api/v1/audit-logs")

        assert response.status_code == 200

    def test_get_audit_logs_returns_list(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs returns list of logs."""
        admins = group_manager.get_group_by_name("admins")
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        response = test_client.get("/api/v1/audit-logs")
        data = response.json()

        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_get_audit_logs_filter_by_action_type(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs filters by action_type."""
        admins = group_manager.get_group_by_name("admins")

        # Create different types of actions
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )
        test_client.post(
            "/api/v1/groups",
            json={"name": "filter-test", "description": "For filtering"},
        )

        response = test_client.get("/api/v1/audit-logs?action_type=repo_access_grant")
        data = response.json()

        for log in data["logs"]:
            assert log["action_type"] == "repo_access_grant"

    def test_get_audit_logs_filter_by_admin_id(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs filters by admin_id."""
        admins = group_manager.get_group_by_name("admins")
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        response = test_client.get("/api/v1/audit-logs?admin_id=admin_user")
        data = response.json()

        for log in data["logs"]:
            assert log["admin_id"] == "admin_user"

    def test_get_audit_logs_pagination(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs supports pagination."""
        admins = group_manager.get_group_by_name("admins")

        # Create multiple log entries
        for i in range(5):
            test_client.post(
                f"/api/v1/groups/{admins.id}/repos", json={"repos": [f"repo{i}"]}
            )

        response = test_client.get("/api/v1/audit-logs?limit=2")
        data = response.json()

        assert len(data["logs"]) <= 2
        assert "total" in data

    def test_get_audit_logs_sorted_by_timestamp_descending(
        self, test_client, group_manager
    ):
        """Test GET /api/v1/audit-logs is sorted by timestamp descending."""
        admins = group_manager.get_group_by_name("admins")

        # Create multiple log entries with slight delay
        for i in range(3):
            test_client.post(
                f"/api/v1/groups/{admins.id}/repos", json={"repos": [f"repo{i}"]}
            )
            time.sleep(0.01)

        response = test_client.get("/api/v1/audit-logs")
        data = response.json()

        timestamps = [log["timestamp"] for log in data["logs"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_get_audit_logs_filter_by_date_range(self, test_client, group_manager):
        """Test GET /api/v1/audit-logs filters by date range."""
        admins = group_manager.get_group_by_name("admins")
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["test-repo"]}
        )

        # Use today's date range
        today = datetime.now(timezone.utc).date().isoformat()
        response = test_client.get(
            f"/api/v1/audit-logs?date_from={today}&date_to={today}"
        )
        data = response.json()

        # Should include logs from today
        assert len(data["logs"]) > 0
