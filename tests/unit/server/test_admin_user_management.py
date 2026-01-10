"""
Unit tests for Admin User Management Interface.

Story #710: Admin User and Group Management Interface

This file covers:
- AC1: List Users with Group Information - GET /api/v1/users with pagination
- AC2: Move User Between Groups - PUT /api/v1/users/{user_id}/group

TDD: These tests are written FIRST, before implementation.
"""

import time
import pytest
import tempfile
from pathlib import Path
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

    set_group_manager(group_manager)

    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_group_manager] = lambda: group_manager

    yield TestClient(app)

    app.dependency_overrides.clear()


class TestAC1ListUsersWithGroupInformation:
    """
    AC1: List Users with Group Information
    - GET /api/v1/users returns users with group membership
    - Includes: user_id, group_id, group_name, assigned_at, assigned_by
    - Sorted alphabetically by user_id
    - Pagination via limit/offset
    """

    def test_get_users_returns_200(self, test_client, group_manager):
        """Test GET /api/v1/users returns 200 status."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("alice", admins.id, "admin_user")

        response = test_client.get("/api/v1/users")
        assert response.status_code == 200

    def test_get_users_returns_list(self, test_client, group_manager):
        """Test GET /api/v1/users returns an array of users."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("alice", admins.id, "admin_user")

        response = test_client.get("/api/v1/users")
        data = response.json()
        assert isinstance(data["users"], list)

    def test_get_users_includes_group_membership_fields(
        self, test_client, group_manager
    ):
        """Test response includes user_id, group_id, group_name, assigned_at, assigned_by."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("testuser", admins.id, "admin_user")

        response = test_client.get("/api/v1/users")
        data = response.json()

        assert len(data["users"]) > 0
        user = data["users"][0]

        assert "user_id" in user
        assert "group_id" in user
        assert "group_name" in user
        assert "assigned_at" in user
        assert "assigned_by" in user

    def test_get_users_sorted_alphabetically(self, test_client, group_manager):
        """Test GET /api/v1/users returns users sorted alphabetically by user_id."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.assign_user_to_group("zebra", admins.id, "admin_user")
        group_manager.assign_user_to_group("alice", admins.id, "admin_user")
        group_manager.assign_user_to_group("bob", admins.id, "admin_user")

        response = test_client.get("/api/v1/users")
        data = response.json()

        user_ids = [u["user_id"] for u in data["users"]]
        assert user_ids == sorted(user_ids)

    def test_get_users_pagination_limit(self, test_client, group_manager):
        """Test GET /api/v1/users supports limit parameter."""
        admins = group_manager.get_group_by_name("admins")

        for i in range(5):
            group_manager.assign_user_to_group(f"user{i:02d}", admins.id, "admin_user")

        response = test_client.get("/api/v1/users?limit=2")
        data = response.json()

        assert len(data["users"]) == 2

    def test_get_users_pagination_offset(self, test_client, group_manager):
        """Test GET /api/v1/users supports offset parameter."""
        admins = group_manager.get_group_by_name("admins")

        for i in range(5):
            group_manager.assign_user_to_group(f"user{i:02d}", admins.id, "admin_user")

        response1 = test_client.get("/api/v1/users?limit=2&offset=0")
        data1 = response1.json()

        response2 = test_client.get("/api/v1/users?limit=2&offset=2")
        data2 = response2.json()

        ids1 = {u["user_id"] for u in data1["users"]}
        ids2 = {u["user_id"] for u in data2["users"]}
        assert ids1.isdisjoint(ids2)

    def test_get_users_includes_total_count(self, test_client, group_manager):
        """Test GET /api/v1/users includes total count for pagination."""
        admins = group_manager.get_group_by_name("admins")

        for i in range(5):
            group_manager.assign_user_to_group(f"user{i:02d}", admins.id, "admin_user")

        response = test_client.get("/api/v1/users?limit=2")
        data = response.json()

        assert "total" in data
        assert data["total"] == 5


class TestAC2MoveUserBetweenGroups:
    """
    AC2: Move User Between Groups
    - PUT /api/v1/users/{user_id}/group with {"group_id": N}
    - Updates membership, replaces old record
    - assigned_at updated, assigned_by set to admin's user_id
    - Returns 200 OK
    """

    def test_move_user_returns_200(self, test_client, group_manager):
        """Test PUT /api/v1/users/{user_id}/group returns 200."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")

        response = test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )
        assert response.status_code == 200

    def test_move_user_updates_membership(self, test_client, group_manager):
        """Test PUT /api/v1/users/{user_id}/group updates the user's group."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")

        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )

        current_group = group_manager.get_user_group("testuser")
        assert current_group.name == "users"

    def test_move_user_replaces_old_membership(self, test_client, group_manager):
        """Test PUT /api/v1/users/{user_id}/group replaces old membership."""
        admins = group_manager.get_group_by_name("admins")
        powerusers = group_manager.get_group_by_name("powerusers")

        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")

        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": powerusers.id}
        )

        users_in_admins = group_manager.get_users_in_group(admins.id)
        assert "testuser" not in users_in_admins

        users_in_powerusers = group_manager.get_users_in_group(powerusers.id)
        assert "testuser" in users_in_powerusers

    def test_move_user_updates_assigned_at(self, test_client, group_manager):
        """Test PUT /api/v1/users/{user_id}/group updates assigned_at timestamp."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")
        original = group_manager.get_user_membership("testuser")

        time.sleep(0.01)

        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )

        new = group_manager.get_user_membership("testuser")
        assert new.assigned_at >= original.assigned_at

    def test_move_user_sets_assigned_by(
        self, test_client, group_manager, mock_admin_user
    ):
        """Test PUT /api/v1/users/{user_id}/group sets assigned_by to admin."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")

        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )

        membership = group_manager.get_user_membership("testuser")
        assert membership.assigned_by == mock_admin_user.username

    def test_move_nonexistent_user_returns_404(self, test_client, group_manager):
        """Test PUT /api/v1/users/{user_id}/group returns 404 for nonexistent user."""
        users_group = group_manager.get_group_by_name("users")

        response = test_client.put(
            "/api/v1/users/nonexistent/group", json={"group_id": users_group.id}
        )
        assert response.status_code == 404

    def test_move_to_nonexistent_group_returns_404(self, test_client, group_manager):
        """Test PUT returns 404 for nonexistent group."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("testuser", admins.id, "initial_admin")

        response = test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": 99999}
        )
        assert response.status_code == 404
