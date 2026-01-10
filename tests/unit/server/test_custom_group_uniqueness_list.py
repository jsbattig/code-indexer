"""
Unit tests for Story #709: Custom Group Management - AC8 and AC9.

TDD Tests covering:
- AC8: Group Name Uniqueness (case-insensitive, 409 Conflict)
- AC9: List All Groups Including Custom (sorted: default first, then by name)

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


class TestAC8GroupNameUniqueness:
    """AC8: Creating duplicate name returns 409 Conflict (case-insensitive)."""

    def test_duplicate_name_returns_409(self, client, admin_auth_token, group_manager):
        """Test creating duplicate name returns 409 Conflict."""
        # Create first group
        client.post(
            "/api/v1/groups",
            json={"name": "unique-team", "description": "First"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Try to create duplicate
        response = client.post(
            "/api/v1/groups",
            json={"name": "unique-team", "description": "Duplicate"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 409

    def test_duplicate_error_message(self, client, admin_auth_token, group_manager):
        """Test error says 'Group name already exists'."""
        # Create first group
        client.post(
            "/api/v1/groups",
            json={"name": "error-message-test", "description": "First"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Try to create duplicate
        response = client.post(
            "/api/v1/groups",
            json={"name": "error-message-test", "description": "Duplicate"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        assert "already exists" in data["detail"].lower()

    def test_case_insensitive_uniqueness(self, client, admin_auth_token, group_manager):
        """Test name uniqueness is case-insensitive."""
        # Create group with lowercase
        client.post(
            "/api/v1/groups",
            json={"name": "case-test", "description": "First"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        # Try uppercase
        response = client.post(
            "/api/v1/groups",
            json={"name": "CASE-TEST", "description": "Should fail"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        assert response.status_code == 409

        # Try mixed case
        response = client.post(
            "/api/v1/groups",
            json={"name": "Case-Test", "description": "Should also fail"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        assert response.status_code == 409

    def test_manager_create_group_case_insensitive(self, temp_db_path):
        """Test GroupAccessManager.create_group() enforces case-insensitive uniqueness."""
        manager = GroupAccessManager(temp_db_path)
        manager.create_group("my-group", "First")

        # Attempting to create with different case should fail
        with pytest.raises(ValueError) as exc_info:
            manager.create_group("MY-GROUP", "Duplicate")

        assert "already exists" in str(exc_info.value).lower()

    def test_update_name_uniqueness(self, client, admin_auth_token, group_manager):
        """Test updating name also enforces uniqueness."""
        # Create two groups
        client.post(
            "/api/v1/groups",
            json={"name": "existing-name", "description": "First"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        create_response = client.post(
            "/api/v1/groups",
            json={"name": "other-name", "description": "Second"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        other_id = create_response.json()["id"]

        # Try to update second to same name as first
        response = client.put(
            f"/api/v1/groups/{other_id}",
            json={"name": "existing-name"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 409

    def test_update_to_same_name_case_insensitive(
        self, client, admin_auth_token, group_manager
    ):
        """Test updating to a name that differs only in case fails."""
        # Create two groups
        client.post(
            "/api/v1/groups",
            json={"name": "first-group", "description": "First"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        create_response = client.post(
            "/api/v1/groups",
            json={"name": "second-group", "description": "Second"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        second_id = create_response.json()["id"]

        # Try to update second to "FIRST-GROUP" (case-insensitive duplicate)
        response = client.put(
            f"/api/v1/groups/{second_id}",
            json={"name": "FIRST-GROUP"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 409


class TestAC9ListAllGroupsSorted:
    """AC9: GET /api/v1/groups returns all groups sorted properly."""

    def test_list_includes_default_groups(
        self, client, admin_auth_token, group_manager
    ):
        """Test list includes default groups."""
        response = client.get(
            "/api/v1/groups",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        names = [g["name"] for g in data]
        assert "admins" in names
        assert "powerusers" in names
        assert "users" in names

    def test_list_includes_custom_groups(self, client, admin_auth_token, group_manager):
        """Test list includes custom groups."""
        # Create custom groups
        client.post(
            "/api/v1/groups",
            json={"name": "custom-a", "description": "A"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        client.post(
            "/api/v1/groups",
            json={"name": "custom-b", "description": "B"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        response = client.get(
            "/api/v1/groups",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        names = [g["name"] for g in data]
        assert "custom-a" in names
        assert "custom-b" in names

    def test_list_sorted_default_groups_first(
        self, client, admin_auth_token, group_manager
    ):
        """Test default groups are listed first."""
        # Create custom groups with names that would sort before defaults alphabetically
        client.post(
            "/api/v1/groups",
            json={"name": "aaa-first-alphabetically", "description": "A"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        response = client.get(
            "/api/v1/groups",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()

        # Find position of default groups vs custom
        default_indices = []
        custom_indices = []
        for i, group in enumerate(data):
            if group["is_default"]:
                default_indices.append(i)
            else:
                custom_indices.append(i)

        # All default groups should come before all custom groups
        if default_indices and custom_indices:
            assert max(default_indices) < min(
                custom_indices
            ), "Default groups should be listed before custom groups"

    def test_list_custom_groups_sorted_by_name(
        self, client, admin_auth_token, group_manager
    ):
        """Test custom groups are sorted alphabetically by name."""
        # Create custom groups in non-alphabetical order
        client.post(
            "/api/v1/groups",
            json={"name": "zebra-team", "description": "Z"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        client.post(
            "/api/v1/groups",
            json={"name": "alpha-team", "description": "A"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        client.post(
            "/api/v1/groups",
            json={"name": "beta-team", "description": "B"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        response = client.get(
            "/api/v1/groups",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        custom_groups = [g for g in data if not g["is_default"]]
        custom_names = [g["name"] for g in custom_groups]

        # Should be alphabetically sorted
        assert custom_names == sorted(custom_names)

    def test_list_response_includes_all_fields(
        self, client, admin_auth_token, group_manager
    ):
        """Test list response includes required fields (id, name, description, is_default)."""
        response = client.get(
            "/api/v1/groups",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        for group in data:
            assert "id" in group
            assert "name" in group
            assert "description" in group
            assert "is_default" in group

    def test_manager_get_all_groups_sorted(self, temp_db_path):
        """Test GroupAccessManager.get_all_groups() returns sorted list."""
        manager = GroupAccessManager(temp_db_path)

        # Create custom groups in non-alphabetical order
        manager.create_group("zebra", "Z group")
        manager.create_group("alpha", "A group")

        groups = manager.get_all_groups()

        # Default groups first, then custom sorted by name
        default_groups = [g for g in groups if g.is_default]
        custom_groups = [g for g in groups if not g.is_default]

        # Verify default groups come first
        default_count = len(default_groups)
        for i in range(default_count):
            assert groups[i].is_default, f"Group at index {i} should be default"

        # Verify custom groups are sorted alphabetically
        custom_names = [g.name for g in custom_groups]
        assert custom_names == sorted(
            custom_names
        ), "Custom groups should be sorted alphabetically"
