"""
Unit tests for Story #709: Custom Group Management - Delete Operations.

This file covers AC5-AC7:
- AC5: Cannot Delete Default Groups (DELETE returns 400)
- AC6: Cannot Delete Groups with Users (DELETE returns 400 with user count)
- AC7: Delete Empty Custom Group (204, cascade deletes repo_group_access)

TDD: These tests are written FIRST, before implementation validation.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    DefaultGroupCannotBeDeletedError,
    GroupHasUsersError,
)
from code_indexer.server.routers.groups import (
    router,
    set_group_manager,
    get_group_manager,
)
from code_indexer.server.auth.dependencies import (
    get_current_admin_user,
    get_current_user,
)


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
    app = FastAPI()
    app.include_router(router)
    set_group_manager(group_manager)
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_group_manager] = lambda: group_manager
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestAC5CannotDeleteDefaultGroups:
    """AC5: Cannot Delete Default Groups - DELETE returns 400."""

    def test_delete_admins_group_returns_400(self, test_client, group_manager):
        """Test that DELETE for admins group returns 400."""
        admins = group_manager.get_group_by_name("admins")
        response = test_client.delete(f"/api/v1/groups/{admins.id}")
        assert response.status_code == 400

    def test_delete_powerusers_group_returns_400(self, test_client, group_manager):
        """Test that DELETE for powerusers group returns 400."""
        powerusers = group_manager.get_group_by_name("powerusers")
        response = test_client.delete(f"/api/v1/groups/{powerusers.id}")
        assert response.status_code == 400

    def test_delete_users_group_returns_400(self, test_client, group_manager):
        """Test that DELETE for users group returns 400."""
        users = group_manager.get_group_by_name("users")
        response = test_client.delete(f"/api/v1/groups/{users.id}")
        assert response.status_code == 400

    def test_delete_default_group_error_message(self, test_client, group_manager):
        """Test that DELETE error message mentions 'default' and 'cannot delete'."""
        admins = group_manager.get_group_by_name("admins")
        response = test_client.delete(f"/api/v1/groups/{admins.id}")
        data = response.json()
        error_msg = data.get("detail", "").lower()
        assert (
            "cannot" in error_msg and "delete" in error_msg and "default" in error_msg
        )

    def test_delete_default_group_service_layer(self, group_manager):
        """Test that delete_group raises DefaultGroupCannotBeDeletedError."""
        admins = group_manager.get_group_by_name("admins")
        with pytest.raises(DefaultGroupCannotBeDeletedError):
            group_manager.delete_group(admins.id)


class TestAC6CannotDeleteGroupsWithUsers:
    """AC6: Cannot Delete Groups with Users - DELETE returns 400 with user count."""

    def test_delete_group_with_users_returns_400(self, test_client, group_manager):
        """Test that DELETE for group with users returns 400."""
        custom = group_manager.create_group("has-users", "Group with users")
        group_manager.assign_user_to_group("user1", custom.id, "admin")
        response = test_client.delete(f"/api/v1/groups/{custom.id}")
        assert response.status_code == 400

    def test_delete_group_with_users_error_contains_count(
        self, test_client, group_manager
    ):
        """Test that error message contains user count."""
        custom = group_manager.create_group("counted-users", "Group with counted")
        group_manager.assign_user_to_group("user1", custom.id, "admin")
        group_manager.assign_user_to_group("user2", custom.id, "admin")
        group_manager.assign_user_to_group("user3", custom.id, "admin")
        response = test_client.delete(f"/api/v1/groups/{custom.id}")
        data = response.json()
        error_msg = data.get("detail", "")
        assert "3" in error_msg

    def test_delete_group_with_single_user_returns_400(
        self, test_client, group_manager
    ):
        """Test that DELETE fails even with just one user."""
        custom = group_manager.create_group("single-user", "One user")
        group_manager.assign_user_to_group("only-user", custom.id, "admin")
        response = test_client.delete(f"/api/v1/groups/{custom.id}")
        assert response.status_code == 400

    def test_delete_group_with_users_service_layer(self, group_manager):
        """Test that delete_group raises GroupHasUsersError."""
        custom = group_manager.create_group("svc-users", "Service test")
        group_manager.assign_user_to_group("user1", custom.id, "admin")
        with pytest.raises(GroupHasUsersError) as exc_info:
            group_manager.delete_group(custom.id)
        assert "1" in str(exc_info.value)


class TestAC7DeleteEmptyCustomGroup:
    """AC7: Delete Empty Custom Group - 204, cascade deletes repo_group_access."""

    def test_delete_empty_custom_group_returns_204(self, test_client, group_manager):
        """Test that DELETE for empty custom group returns 204."""
        custom = group_manager.create_group("deletable", "To be deleted")
        response = test_client.delete(f"/api/v1/groups/{custom.id}")
        assert response.status_code == 204

    def test_delete_empty_custom_group_removes_from_database(
        self, test_client, group_manager
    ):
        """Test that deleted group is removed from database."""
        custom = group_manager.create_group("to-remove", "Will be removed")
        group_id = custom.id
        test_client.delete(f"/api/v1/groups/{group_id}")
        assert group_manager.get_group(group_id) is None

    def test_delete_custom_group_cascades_repo_access(
        self, test_client, group_manager, temp_db_path
    ):
        """Test that deleting group cascades to delete repo_group_access."""
        custom = group_manager.create_group("cascade-test", "Cascade test")
        group_manager.grant_repo_access("test-repo-1", custom.id, "admin")
        group_manager.grant_repo_access("test-repo-2", custom.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?",
            (custom.id,),
        )
        before_count = cursor.fetchone()[0]
        assert before_count == 2

        test_client.delete(f"/api/v1/groups/{custom.id}")

        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?",
            (custom.id,),
        )
        after_count = cursor.fetchone()[0]
        conn.close()
        assert after_count == 0

    def test_delete_nonexistent_group_returns_404(self, test_client):
        """Test that DELETE for nonexistent group returns 404."""
        response = test_client.delete("/api/v1/groups/99999")
        assert response.status_code == 404

    def test_delete_service_layer_returns_true(self, group_manager):
        """Test that delete_group returns True on success."""
        custom = group_manager.create_group("svc-delete", "Service delete")
        result = group_manager.delete_group(custom.id)
        assert result is True

    def test_delete_service_layer_nonexistent_returns_false(self, group_manager):
        """Test that delete_group returns False for nonexistent group."""
        result = group_manager.delete_group(99999)
        assert result is False
