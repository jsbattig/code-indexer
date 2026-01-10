"""
Unit tests for Admin Group Details Interface.

Story #710: Admin User and Group Management Interface

This file covers:
- AC3: View Group Details with Members - GET /api/v1/groups/{id} with user list

TDD: These tests are written FIRST, before implementation.
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


class TestAC3ViewGroupDetailsWithMembers:
    """
    AC3: View Group Details with Members
    - GET /api/v1/groups/{id} includes:
      - Group metadata
      - List of user_ids in group
      - Count of users
      - List of accessible repos
      - Count of repos
    """

    def test_get_group_includes_user_ids_list(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} includes list of user_ids in group."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.assign_user_to_group("alice", admins.id, "admin_user")
        group_manager.assign_user_to_group("bob", admins.id, "admin_user")

        response = test_client.get(f"/api/v1/groups/{admins.id}")
        data = response.json()

        assert "user_ids" in data
        assert isinstance(data["user_ids"], list)
        assert "alice" in data["user_ids"]
        assert "bob" in data["user_ids"]

    def test_get_group_includes_user_count(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} includes count of users."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.assign_user_to_group("alice", admins.id, "admin_user")
        group_manager.assign_user_to_group("bob", admins.id, "admin_user")

        response = test_client.get(f"/api/v1/groups/{admins.id}")
        data = response.json()

        assert "user_count" in data
        assert data["user_count"] == 2

    def test_get_group_includes_accessible_repos(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} includes list of accessible repos."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("repo1", admins.id, "admin_user")
        group_manager.grant_repo_access("repo2", admins.id, "admin_user")

        response = test_client.get(f"/api/v1/groups/{admins.id}")
        data = response.json()

        assert "accessible_repos" in data
        assert isinstance(data["accessible_repos"], list)
        assert "repo1" in data["accessible_repos"]
        assert "repo2" in data["accessible_repos"]

    def test_get_group_includes_repo_count(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} includes count of repos."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("repo1", admins.id, "admin_user")
        group_manager.grant_repo_access("repo2", admins.id, "admin_user")

        response = test_client.get(f"/api/v1/groups/{admins.id}")
        data = response.json()

        assert "repo_count" in data
        # +1 for cidx-meta which is always included
        assert data["repo_count"] >= 2

    def test_get_group_empty_group_has_empty_user_ids(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} returns empty user_ids for group with no users."""
        users_group = group_manager.get_group_by_name("users")

        response = test_client.get(f"/api/v1/groups/{users_group.id}")
        data = response.json()

        assert "user_ids" in data
        assert data["user_ids"] == []
        assert data["user_count"] == 0

    def test_get_group_cidx_meta_always_in_repos(self, test_client, group_manager):
        """Test GET /api/v1/groups/{id} always includes cidx-meta in accessible_repos."""
        users_group = group_manager.get_group_by_name("users")

        response = test_client.get(f"/api/v1/groups/{users_group.id}")
        data = response.json()

        assert "cidx-meta" in data["accessible_repos"]
