"""
Unit tests for Story #709: Custom Group Management - Uniqueness and List.

This file covers AC8-AC9:
- AC8: Group Name Uniqueness (409 Conflict for duplicate names, case-insensitive)
- AC9: List All Groups (sorted: defaults first, then custom by name)

TDD: These tests are written FIRST, before implementation validation.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from code_indexer.server.services.group_access_manager import GroupAccessManager
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


class TestAC8GroupNameUniqueness:
    """AC8: Group Name Uniqueness - 409 Conflict for duplicate names."""

    def test_create_duplicate_name_returns_409(self, test_client, group_manager):
        """Test that creating group with duplicate name returns 409."""
        group_manager.create_group("unique-name", "First group")
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "unique-name", "description": "Duplicate"},
        )
        assert response.status_code == 409

    def test_create_duplicate_name_case_insensitive(self, test_client, group_manager):
        """Test that name uniqueness is case-insensitive."""
        group_manager.create_group("CamelCase", "First")
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "camelcase", "description": "Different case"},
        )
        assert response.status_code == 409

    def test_create_duplicate_name_uppercase(self, test_client, group_manager):
        """Test that UPPERCASE duplicate is detected."""
        group_manager.create_group("lowercase", "First")
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "LOWERCASE", "description": "Uppercase version"},
        )
        assert response.status_code == 409

    def test_create_duplicate_default_group_name(self, test_client):
        """Test that creating group with default group name fails."""
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "admins", "description": "Fake admins"},
        )
        assert response.status_code == 409

    def test_update_to_duplicate_name_returns_409(self, test_client, group_manager):
        """Test that updating to existing name returns 409."""
        group_manager.create_group("existing", "Existing group")
        to_update = group_manager.create_group("to-update", "To be updated")
        response = test_client.put(
            f"/api/v1/groups/{to_update.id}",
            json={"name": "existing"},
        )
        assert response.status_code == 409

    def test_update_to_duplicate_name_case_insensitive(
        self, test_client, group_manager
    ):
        """Test that update name uniqueness is case-insensitive."""
        group_manager.create_group("Target", "Target group")
        to_update = group_manager.create_group("source", "Source group")
        response = test_client.put(
            f"/api/v1/groups/{to_update.id}",
            json={"name": "TARGET"},
        )
        assert response.status_code == 409

    def test_update_same_name_allowed(self, test_client, group_manager):
        """Test that updating to same name (no-op) is allowed."""
        custom = group_manager.create_group("same-name", "Same name")
        response = test_client.put(
            f"/api/v1/groups/{custom.id}",
            json={"name": "same-name"},
        )
        assert response.status_code == 200

    def test_create_service_layer_duplicate_fails(self, group_manager):
        """Test that create_group raises ValueError for duplicate."""
        group_manager.create_group("svc-dup", "First")
        with pytest.raises(ValueError) as exc_info:
            group_manager.create_group("svc-dup", "Duplicate")
        assert "already exists" in str(exc_info.value).lower()

    def test_update_service_layer_duplicate_fails(self, group_manager):
        """Test that update_group raises ValueError for duplicate name."""
        group_manager.create_group("target-name", "Target")
        source = group_manager.create_group("source-name", "Source")
        with pytest.raises(ValueError) as exc_info:
            group_manager.update_group(source.id, name="target-name")
        assert "already exists" in str(exc_info.value).lower()


class TestAC9ListAllGroups:
    """AC9: List All Groups - sorted: defaults first, then custom by name."""

    def test_list_groups_returns_all_groups(self, test_client, group_manager):
        """Test that GET /api/v1/groups returns all groups."""
        group_manager.create_group("custom-a", "Custom A")
        group_manager.create_group("custom-b", "Custom B")
        response = test_client.get("/api/v1/groups")
        data = response.json()
        assert len(data) == 5  # 3 default + 2 custom

    def test_list_groups_default_groups_first(self, test_client, group_manager):
        """Test that default groups appear before custom groups."""
        group_manager.create_group("aaa-custom", "Alphabetically first custom")
        response = test_client.get("/api/v1/groups")
        data = response.json()
        default_groups = data[:3]
        for group in default_groups:
            assert group["is_default"] is True

    def test_list_groups_custom_sorted_by_name(self, test_client, group_manager):
        """Test that custom groups are sorted alphabetically by name."""
        group_manager.create_group("zebra", "Z group")
        group_manager.create_group("alpha", "A group")
        group_manager.create_group("mid", "M group")
        response = test_client.get("/api/v1/groups")
        data = response.json()
        custom_groups = [g for g in data if not g["is_default"]]
        names = [g["name"] for g in custom_groups]
        assert names == sorted(names)

    def test_list_groups_sorting_comprehensive(self, test_client, group_manager):
        """Test sorting: defaults first, then custom alphabetically."""
        group_manager.create_group("zzz-last", "Last")
        group_manager.create_group("aaa-first", "First custom")
        group_manager.create_group("mmm-middle", "Middle")
        response = test_client.get("/api/v1/groups")
        data = response.json()
        names = [g["name"] for g in data]
        default_names = ["admins", "powerusers", "users"]
        custom_names = ["aaa-first", "mmm-middle", "zzz-last"]
        assert names[:3] == default_names
        assert names[3:] == custom_names

    def test_list_groups_service_layer_sorting(self, group_manager):
        """Test that get_all_groups returns sorted list."""
        group_manager.create_group("zebra", "Z")
        group_manager.create_group("alpha", "A")
        groups = group_manager.get_all_groups()
        default_groups = [g for g in groups if g.is_default]
        custom_groups = [g for g in groups if not g.is_default]
        default_indices = [groups.index(g) for g in default_groups]
        custom_indices = [groups.index(g) for g in custom_groups]
        assert max(default_indices) < min(custom_indices)
        custom_names = [g.name for g in custom_groups]
        assert custom_names == sorted(custom_names)


class TestFullCRUDFlow:
    """Integration test for complete CRUD workflow."""

    def test_create_read_update_delete_flow(self, test_client, group_manager):
        """Test complete CRUD lifecycle of a custom group."""
        # CREATE
        create_response = test_client.post(
            "/api/v1/groups",
            json={"name": "lifecycle-test", "description": "Testing lifecycle"},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        group_id = created["id"]

        # READ
        read_response = test_client.get(f"/api/v1/groups/{group_id}")
        assert read_response.status_code == 200
        read_data = read_response.json()
        assert read_data["name"] == "lifecycle-test"
        assert read_data["user_count"] == 0

        # UPDATE
        update_response = test_client.put(
            f"/api/v1/groups/{group_id}",
            json={"name": "updated-name", "description": "Updated description"},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "updated-name"

        # DELETE
        delete_response = test_client.delete(f"/api/v1/groups/{group_id}")
        assert delete_response.status_code == 204

        # Verify deleted
        verify_response = test_client.get(f"/api/v1/groups/{group_id}")
        assert verify_response.status_code == 404
