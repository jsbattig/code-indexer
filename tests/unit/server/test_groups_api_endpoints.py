"""
Unit tests for Groups API endpoints.

Tests for AC5: API Endpoints for Group Operations
- GET /api/v1/groups - Returns list of all groups
- GET /api/v1/groups/{id} - Returns group details including user count and accessible repos

Also tests:
- AC2: DELETE /api/v1/groups/{id} - Default groups cannot be deleted
- POST /api/v1/groups/{id}/members - User group assignment

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.group_access_manager import GroupAccessManager
from code_indexer.server.routers.groups import set_group_manager


@pytest.fixture
def temp_groups_db():
    """Create a temporary database for groups testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def initialized_group_manager(temp_groups_db):
    """Create and initialize a GroupAccessManager for testing."""
    manager = GroupAccessManager(temp_groups_db)
    set_group_manager(manager)
    yield manager
    # Cleanup: reset the global manager
    set_group_manager(None)


class TestGroupsListEndpoint:
    """Tests for GET /api/v1/groups endpoint."""

    @pytest.fixture
    def client(self, initialized_group_manager):
        """Create FastAPI test client with initialized group manager."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager for authentication."""
        with (
            patch("code_indexer.server.app.user_manager") as app_mock,
            patch("code_indexer.server.auth.dependencies.user_manager") as deps_mock,
        ):
            # Both mocks should behave the same
            yield app_mock, deps_mock

    @pytest.fixture
    def auth_token(self, client, mock_user_manager):
        """Get authentication token for requests."""
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

    def test_list_groups_returns_200(self, client, auth_token):
        """Test GET /api/v1/groups returns 200 status."""
        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200

    def test_list_groups_returns_array(self, client, auth_token):
        """Test GET /api/v1/groups returns an array of groups."""
        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        assert isinstance(data, list)

    def test_list_groups_returns_default_groups(self, client, auth_token):
        """Test GET /api/v1/groups returns the three default groups."""
        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()

        group_names = {g["name"] for g in data}
        assert "admins" in group_names
        assert "powerusers" in group_names
        assert "users" in group_names

    def test_list_groups_response_structure(self, client, auth_token):
        """Test GET /api/v1/groups returns groups with expected fields."""
        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()

        for group in data:
            assert "id" in group
            assert "name" in group
            assert "description" in group
            assert "is_default" in group
            assert "created_at" in group

    def test_list_groups_requires_authentication(self, client):
        """Test GET /api/v1/groups requires authentication."""
        response = client.get("/api/v1/groups")
        assert response.status_code == 401

    def test_list_groups_accessible_by_power_user(self, client, mock_user_manager):
        """Test GET /api/v1/groups is accessible by power users."""
        app_mock, deps_mock = mock_user_manager
        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        app_mock.authenticate_user.return_value = power_user
        deps_mock.get_user.return_value = power_user

        login_response = client.post(
            "/auth/login", json={"username": "poweruser", "password": "password"}
        )
        token = login_response.json()["access_token"]

        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {token}"}
        )
        # Power users should be able to list groups
        assert response.status_code == 200

    def test_list_groups_accessible_by_normal_user(self, client, mock_user_manager):
        """Test GET /api/v1/groups is accessible by normal users."""
        app_mock, deps_mock = mock_user_manager
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

        response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {token}"}
        )
        # Normal users should be able to list groups
        assert response.status_code == 200


class TestGroupDetailsEndpoint:
    """Tests for GET /api/v1/groups/{id} endpoint."""

    @pytest.fixture
    def client(self, initialized_group_manager):
        """Create FastAPI test client with initialized group manager."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager for authentication."""
        with (
            patch("code_indexer.server.app.user_manager") as app_mock,
            patch("code_indexer.server.auth.dependencies.user_manager") as deps_mock,
        ):
            yield app_mock, deps_mock

    @pytest.fixture
    def auth_token(self, client, mock_user_manager):
        """Get authentication token for requests."""
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

    def test_get_group_returns_200_for_valid_id(self, client, auth_token):
        """Test GET /api/v1/groups/{id} returns 200 for valid group ID."""
        # First get the list to find a valid ID
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        valid_id = groups[0]["id"]

        response = client.get(
            f"/api/v1/groups/{valid_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

    def test_get_group_returns_404_for_invalid_id(self, client, auth_token):
        """Test GET /api/v1/groups/{id} returns 404 for nonexistent ID."""
        response = client.get(
            "/api/v1/groups/99999", headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 404

    def test_get_group_response_includes_basic_fields(self, client, auth_token):
        """Test GET /api/v1/groups/{id} returns group with basic fields."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        valid_id = groups[0]["id"]

        response = client.get(
            f"/api/v1/groups/{valid_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert "id" in data
        assert "name" in data
        assert "description" in data
        assert "is_default" in data
        assert "created_at" in data

    def test_get_group_response_includes_user_count(self, client, auth_token):
        """Test GET /api/v1/groups/{id} returns count of users in the group."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        valid_id = groups[0]["id"]

        response = client.get(
            f"/api/v1/groups/{valid_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert "user_count" in data
        assert isinstance(data["user_count"], int)
        assert data["user_count"] >= 0

    def test_get_group_response_includes_accessible_repos(self, client, auth_token):
        """Test GET /api/v1/groups/{id} returns list of repos accessible by group."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        valid_id = groups[0]["id"]

        response = client.get(
            f"/api/v1/groups/{valid_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert "accessible_repos" in data
        assert isinstance(data["accessible_repos"], list)

    def test_get_group_requires_authentication(self, client):
        """Test GET /api/v1/groups/{id} requires authentication."""
        response = client.get("/api/v1/groups/1")
        assert response.status_code == 401

    def test_get_admins_group_details(self, client, auth_token):
        """Test getting admins group returns correct details."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        admins = next(g for g in groups if g["name"] == "admins")

        response = client.get(
            f"/api/v1/groups/{admins['id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert data["name"] == "admins"
        assert data["is_default"] is True

    def test_get_powerusers_group_details(self, client, auth_token):
        """Test getting powerusers group returns correct details."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        powerusers = next(g for g in groups if g["name"] == "powerusers")

        response = client.get(
            f"/api/v1/groups/{powerusers['id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert data["name"] == "powerusers"
        assert data["is_default"] is True

    def test_get_users_group_details(self, client, auth_token):
        """Test getting users group returns correct details."""
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        users_group = next(g for g in groups if g["name"] == "users")

        response = client.get(
            f"/api/v1/groups/{users_group['id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = response.json()

        assert data["name"] == "users"
        assert data["is_default"] is True


class TestGroupMembershipEndpoints:
    """Tests for group membership and deletion API endpoints."""

    @pytest.fixture
    def client(self, initialized_group_manager):
        """Create FastAPI test client with initialized group manager."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager for authentication."""
        with (
            patch("code_indexer.server.app.user_manager") as app_mock,
            patch("code_indexer.server.auth.dependencies.user_manager") as deps_mock,
        ):
            yield app_mock, deps_mock

    @pytest.fixture
    def auth_token(self, client, mock_user_manager):
        """Get authentication token for requests."""
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

    def test_assign_user_to_group_requires_admin(self, client, mock_user_manager):
        """Test that assigning users to groups requires admin role."""
        app_mock, deps_mock = mock_user_manager
        # Login as power user
        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        app_mock.authenticate_user.return_value = power_user
        deps_mock.get_user.return_value = power_user

        login_response = client.post(
            "/auth/login", json={"username": "poweruser", "password": "password"}
        )
        token = login_response.json()["access_token"]

        # Try to assign user to group - should fail with 403
        response = client.post(
            "/api/v1/groups/1/members",
            json={"user_id": "testuser"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_delete_default_group_via_api_fails(self, client, auth_token):
        """Test that deleting default groups via API returns appropriate error."""
        # Get the admins group ID
        list_response = client.get(
            "/api/v1/groups", headers={"Authorization": f"Bearer {auth_token}"}
        )
        groups = list_response.json()
        admins = next(g for g in groups if g["name"] == "admins")

        # Try to delete the admins group
        response = client.delete(
            f"/api/v1/groups/{admins['id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should return 400 with error message
        assert response.status_code == 400
        data = response.json()
        error_msg = data.get("detail", "").lower()
        assert "default" in error_msg or "cannot be deleted" in error_msg
