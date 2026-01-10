"""
Unit tests for Immediate Effect of Changes.

Story #710: Admin User and Group Management Interface

This file covers:
- AC6: Immediate Effect of Changes - No cache invalidation required

TDD: These tests verify changes take effect immediately within same session.
"""

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


class TestAC6ImmediateEffectOfChanges:
    """
    AC6: Immediate Effect of Changes
    - Changes take effect immediately without restart
    - No cache invalidation required
    - Works within same session
    """

    def test_user_group_change_immediate_effect(self, test_client, group_manager):
        """Test that user group changes take effect immediately."""
        admins = group_manager.get_group_by_name("admins")
        users_group = group_manager.get_group_by_name("users")

        # Assign user to admins
        group_manager.assign_user_to_group("testuser", admins.id, "admin_user")

        # Verify in same session via API
        response1 = test_client.get("/api/v1/users")
        data1 = response1.json()
        user1 = next((u for u in data1["users"] if u["user_id"] == "testuser"), None)
        assert user1 is not None
        assert user1["group_name"] == "admins"

        # Move user via API
        test_client.put(
            "/api/v1/users/testuser/group", json={"group_id": users_group.id}
        )

        # Verify change is immediate (same session, no restart)
        response2 = test_client.get("/api/v1/users")
        data2 = response2.json()
        user2 = next((u for u in data2["users"] if u["user_id"] == "testuser"), None)
        assert user2 is not None
        assert user2["group_name"] == "users"

    def test_repo_access_change_immediate_effect(self, test_client, group_manager):
        """Test that repo access changes take effect immediately."""
        admins = group_manager.get_group_by_name("admins")

        # Add repos via API
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["new-repo"]}
        )

        # Verify change is immediate (same session)
        response = test_client.get(f"/api/v1/groups/{admins.id}")
        data = response.json()
        assert "new-repo" in data["accessible_repos"]

    def test_repo_removal_immediate_effect(self, test_client, group_manager):
        """Test that repo removal takes effect immediately."""
        admins = group_manager.get_group_by_name("admins")

        # Add a repo first
        group_manager.grant_repo_access("temp-repo", admins.id, "admin_user")

        # Verify it's there
        response1 = test_client.get(f"/api/v1/groups/{admins.id}")
        data1 = response1.json()
        assert "temp-repo" in data1["accessible_repos"]

        # Remove via API
        test_client.request(
            "DELETE", f"/api/v1/groups/{admins.id}/repos", json={"repos": ["temp-repo"]}
        )

        # Verify removal is immediate
        response2 = test_client.get(f"/api/v1/groups/{admins.id}")
        data2 = response2.json()
        assert "temp-repo" not in data2["accessible_repos"]

    def test_user_count_updates_immediately(self, test_client, group_manager):
        """Test that user_count in group details updates immediately."""
        powerusers = group_manager.get_group_by_name("powerusers")

        # Check initial count
        response1 = test_client.get(f"/api/v1/groups/{powerusers.id}")
        initial_count = response1.json()["user_count"]

        # Add a user
        group_manager.assign_user_to_group("newuser", powerusers.id, "admin_user")

        # Verify count updated immediately
        response2 = test_client.get(f"/api/v1/groups/{powerusers.id}")
        new_count = response2.json()["user_count"]
        assert new_count == initial_count + 1
