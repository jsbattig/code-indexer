"""
Unit tests for Story #709: Custom Group Management - AC3 and AC4.

TDD Tests covering:
- AC3: Read Custom Group (GET /api/v1/groups/{id})
- AC4: Update Custom Group (PUT /api/v1/groups/{id})

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
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


# Constants
NONEXISTENT_GROUP_ID = 99999


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


class TestAC3ReadCustomGroup:
    """AC3: GET /api/v1/groups/{id} returns group details."""

    def test_get_custom_group_returns_all_fields(
        self, client, admin_auth_token, group_manager
    ):
        """Test GET returns id, name, description, is_default, created_at."""
        # Create a custom group first
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "readable-group", "description": "For reading"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Get the group
        response = client.get(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == group_id
        assert data["name"] == "readable-group"
        assert data["description"] == "For reading"
        assert data["is_default"] is False
        assert "created_at" in data

    def test_get_custom_group_includes_user_count(
        self, client, admin_auth_token, group_manager
    ):
        """Test GET returns count of users in the group."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "group-with-users", "description": "Has users"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Assign some users
        group_manager.assign_user_to_group("user1", group_id, "admin")
        group_manager.assign_user_to_group("user2", group_id, "admin")

        # Get group details
        response = client.get(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        data = response.json()

        assert data["user_count"] == 2

    def test_get_custom_group_includes_accessible_repos(
        self, client, admin_auth_token, group_manager
    ):
        """Test GET returns list of accessible repos."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "group-with-repos", "description": "Has repos"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Grant access to some repos
        group_manager.grant_repo_access("repo-a", group_id, "admin")
        group_manager.grant_repo_access("repo-b", group_id, "admin")

        # Get group details
        response = client.get(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        data = response.json()

        # cidx-meta always first, then granted repos
        assert "cidx-meta" in data["accessible_repos"]
        assert "repo-a" in data["accessible_repos"]
        assert "repo-b" in data["accessible_repos"]

    def test_get_returns_404_for_nonexistent_group(
        self, client, admin_auth_token, group_manager
    ):
        """Test GET returns 404 for nonexistent group ID."""
        response = client.get(
            f"/api/v1/groups/{NONEXISTENT_GROUP_ID}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 404


class TestAC4UpdateCustomGroup:
    """AC4: PUT /api/v1/groups/{id} updates name and/or description."""

    def test_put_updates_group_name(self, client, admin_auth_token, group_manager):
        """Test PUT /api/v1/groups/{id} updates group name."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "original-name", "description": "Original description"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Update name
        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "updated-name"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "updated-name"

    def test_put_updates_group_description(
        self, client, admin_auth_token, group_manager
    ):
        """Test PUT /api/v1/groups/{id} updates group description."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "desc-update-group", "description": "Original"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Update description
        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"description": "Updated description"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"

    def test_put_updates_both_name_and_description(
        self, client, admin_auth_token, group_manager
    ):
        """Test PUT /api/v1/groups/{id} updates both fields."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "both-update-group", "description": "Original"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Update both
        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "new-name", "description": "New description"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new-name"
        assert data["description"] == "New description"

    def test_put_preserves_is_default_false(
        self, client, admin_auth_token, group_manager
    ):
        """Test PUT cannot change is_default (remains FALSE)."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "is-default-test", "description": "Test"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Update (is_default should remain FALSE)
        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "updated-is-default-test"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_default"] is False

    def test_put_returns_200_with_updated_details(
        self, client, admin_auth_token, group_manager
    ):
        """Test PUT returns 200 OK with updated details."""
        # Create group
        create_response = client.post(
            "/api/v1/groups",
            json={"name": "status-test-group", "description": "Test"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = create_response.json()["id"]

        # Update
        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "updated-status-test-group"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "description" in data
        assert "is_default" in data

    def test_put_requires_admin(self, client, mock_user_manager, group_manager):
        """Test PUT /api/v1/groups/{id} requires admin role."""
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
            json={"name": "admin-test-group", "description": "Test"},
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

        response = client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "hacked-name"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    def test_put_returns_404_for_nonexistent_group(
        self, client, admin_auth_token, group_manager
    ):
        """Test PUT returns 404 for nonexistent group ID."""
        response = client.put(
            f"/api/v1/groups/{NONEXISTENT_GROUP_ID}",
            json={"name": "new-name"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 404

    def test_update_group_manager_method(self, temp_db_path):
        """Test GroupAccessManager.update_group() method."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("test-update", "Original")

        # Update using manager method
        updated = manager.update_group(
            group.id, name="updated-name", description="Updated"
        )

        assert updated.name == "updated-name"
        assert updated.description == "Updated"
        assert updated.is_default is False

    def test_update_group_partial_update_name_only(self, temp_db_path):
        """Test update_group with only name."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("partial-test", "Original description")

        updated = manager.update_group(group.id, name="new-name-only")

        assert updated.name == "new-name-only"
        assert updated.description == "Original description"

    def test_update_group_partial_update_description_only(self, temp_db_path):
        """Test update_group with only description."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("desc-only-test", "Original")

        updated = manager.update_group(group.id, description="New description only")

        assert updated.name == "desc-only-test"
        assert updated.description == "New description only"
