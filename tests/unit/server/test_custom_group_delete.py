"""
Unit tests for Story #709: Custom Group Management - AC5, AC6, AC7.

TDD Tests covering:
- AC5: Cannot Delete Default Groups
- AC6: Cannot Delete Groups with Users
- AC7: Delete Empty Custom Group (cascade delete repo_group_access)

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
)
from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.routers.groups import set_group_manager


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
    """Create and initialize a GroupAccessManager for testing."""
    manager = GroupAccessManager(temp_db_path)
    set_group_manager(manager)
    yield manager
    set_group_manager(None)


@pytest.fixture
def client(group_manager):
    """Create FastAPI test client with initialized group manager."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_user_manager():
    """Create mock user manager for authentication."""
    with (
        patch("code_indexer.server.app.user_manager") as app_mock,
        patch("code_indexer.server.auth.dependencies.user_manager") as deps_mock,
    ):
        yield app_mock, deps_mock


@pytest.fixture
def admin_auth_token(client, mock_user_manager):
    """Get authentication token for admin user."""
    app_mock, deps_mock = mock_user_manager
    admin_user = User(
        username="admin",
        password_hash="$2b$12$hash",
        role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    )
    app_mock.authenticate_user.return_value = admin_user
    deps_mock.get_user.return_value = admin_user

    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    return response.json()["access_token"]


class TestAC5CannotDeleteDefaultGroups:
    """AC5: DELETE /api/v1/groups/{id} on default group returns 400."""

    def test_delete_admins_returns_400(self, client, admin_auth_token, group_manager):
        """Test DELETE on admins group returns 400."""
        admins = group_manager.get_group_by_name("admins")

        response = client.delete(
            f"/api/v1/groups/{admins.id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 400

    def test_delete_powerusers_returns_400(
        self, client, admin_auth_token, group_manager
    ):
        """Test DELETE on powerusers group returns 400."""
        powerusers = group_manager.get_group_by_name("powerusers")

        response = client.delete(
            f"/api/v1/groups/{powerusers.id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 400

    def test_delete_users_returns_400(self, client, admin_auth_token, group_manager):
        """Test DELETE on users group returns 400."""
        users_group = group_manager.get_group_by_name("users")

        response = client.delete(
            f"/api/v1/groups/{users_group.id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 400

    def test_delete_default_group_error_message(
        self, client, admin_auth_token, group_manager
    ):
        """Test DELETE error message indicates default groups cannot be deleted."""
        admins = group_manager.get_group_by_name("admins")

        response = client.delete(
            f"/api/v1/groups/{admins.id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        # AC5: Error message should indicate default groups cannot be deleted
        detail_lower = data["detail"].lower()
        assert (
            "default" in detail_lower
            and "cannot" in detail_lower
            and "delete" in detail_lower
        )

    def test_delete_default_group_remains_unchanged(
        self, client, admin_auth_token, group_manager
    ):
        """Test default group remains in database after delete attempt."""
        admins = group_manager.get_group_by_name("admins")
        original_id = admins.id

        # Attempt to delete
        client.delete(
            f"/api/v1/groups/{admins.id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Verify group still exists
        admins_after = group_manager.get_group_by_name("admins")
        assert admins_after is not None
        assert admins_after.id == original_id


class TestAC6CannotDeleteGroupsWithUsers:
    """AC6: DELETE on group with assigned users returns 400."""

    def test_delete_group_with_users_returns_400(
        self, client, admin_auth_token, group_manager
    ):
        """Test DELETE on group with users returns 400."""
        # Create group and assign user
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "group-with-user", "description": "Has a user"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]
        group_manager.assign_user_to_group("testuser", group_id, "admin")

        # Try to delete
        response = client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 400

    def test_delete_group_with_users_error_includes_count(
        self, client, admin_auth_token, group_manager
    ):
        """Test error message includes user count."""
        # Create group and assign multiple users
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "group-with-many-users", "description": "Has users"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]
        group_manager.assign_user_to_group("user1", group_id, "admin")
        group_manager.assign_user_to_group("user2", group_id, "admin")
        group_manager.assign_user_to_group("user3", group_id, "admin")

        # Try to delete
        response = client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        # Error should mention user count (3 users)
        assert "3" in data["detail"] or "user" in data["detail"].lower()

    def test_delete_group_with_users_group_unchanged(
        self, client, admin_auth_token, group_manager
    ):
        """Test group remains unchanged after failed delete."""
        # Create group and assign user
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "unchanged-group", "description": "Should remain"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]
        group_manager.assign_user_to_group("keeper", group_id, "admin")

        # Try to delete
        client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Verify group still exists
        group = group_manager.get_group(group_id)
        assert group is not None
        assert group.name == "unchanged-group"

    def test_delete_group_manager_raises_error_for_users(self, temp_db_path):
        """Test GroupAccessManager.delete_group() raises error when group has users."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("has-users", "Group with users")
        manager.assign_user_to_group("testuser", group.id, "admin")

        # Import the expected error class
        from code_indexer.server.services.group_access_manager import GroupHasUsersError

        with pytest.raises(GroupHasUsersError) as exc_info:
            manager.delete_group(group.id)

        assert "1" in str(exc_info.value) or "user" in str(exc_info.value).lower()


class TestAC7DeleteEmptyCustomGroup:
    """AC7: DELETE /api/v1/groups/{id} on empty custom group succeeds."""

    def test_delete_empty_custom_group_returns_204(
        self, client, admin_auth_token, group_manager
    ):
        """Test DELETE on empty custom group returns 204 No Content."""
        # Create group (no users)
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "empty-deletable", "description": "No users"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Delete
        response = client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 204

    def test_delete_empty_group_removes_from_database(
        self, client, admin_auth_token, group_manager
    ):
        """Test deleted group no longer exists in database."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "to-be-deleted", "description": "Will be deleted"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Delete
        client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Verify gone
        group = group_manager.get_group(group_id)
        assert group is None

    def test_delete_cascades_repo_group_access(
        self, client, admin_auth_token, group_manager, temp_db_path
    ):
        """Test all repo_group_access records for group are cascade deleted."""
        # Create group with repo access
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "cascade-test", "description": "Has repos"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Grant access to multiple repos
        group_manager.grant_repo_access("repo-1", group_id, "admin")
        group_manager.grant_repo_access("repo-2", group_id, "admin")
        group_manager.grant_repo_access("repo-3", group_id, "admin")

        # Verify records exist
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group_id,)
        )
        count_before = cursor.fetchone()[0]
        assert count_before == 3

        # Delete group
        client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Verify cascade delete
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group_id,)
        )
        count_after = cursor.fetchone()[0]
        conn.close()

        assert count_after == 0

    def test_delete_requires_admin(self, client, mock_user_manager, group_manager):
        """Test DELETE /api/v1/groups/{id} requires admin role."""
        app_mock, deps_mock = mock_user_manager

        # First login as admin to create group
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        app_mock.authenticate_user.return_value = admin_user
        deps_mock.get_user.return_value = admin_user

        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        admin_token = login_response.json()["access_token"]

        create_response = client.post(
            "/api/v1/groups",
            json={"name": "admin-only-delete", "description": "Test"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        group_id = create_response.json()["id"]

        # Now switch to normal user
        normal_user = User(
            username="normaluser",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        app_mock.authenticate_user.return_value = normal_user
        deps_mock.get_user.return_value = normal_user

        login_response = client.post(
            "/auth/login", json={"username": "normaluser", "password": "password"}
        )
        token = login_response.json()["access_token"]

        response = client.delete(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
