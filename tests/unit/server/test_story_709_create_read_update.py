"""
Unit tests for Story #709: Custom Group Management - Create, Read, Update.

This file covers AC1-AC4:
- AC1: Create Custom Group (POST returns 201, is_default=FALSE)
- AC2: Custom Groups Start Empty (only cidx-meta accessible)
- AC3: Read Custom Group (GET returns full details with user_count)
- AC4: Update Custom Group (PUT updates name/description, returns 200)

TDD: These tests are written FIRST, before implementation validation.
"""

import pytest
import tempfile
import sqlite3
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


class TestAC1CreateCustomGroup:
    """AC1: Create Custom Group - POST returns 201, is_default=FALSE."""

    def test_create_group_returns_201(self, test_client):
        """Test that POST /api/v1/groups returns 201 Created."""
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "developers", "description": "Development team"},
        )
        assert response.status_code == 201

    def test_create_group_sets_is_default_false(self, test_client):
        """Test that created custom groups have is_default=FALSE."""
        response = test_client.post(
            "/api/v1/groups",
            json={"name": "custom-group", "description": "A custom group"},
        )
        data = response.json()
        assert data["is_default"] is False

    def test_create_group_persists_in_database(self, test_client, group_manager):
        """Test that created group is persisted in database."""
        test_client.post(
            "/api/v1/groups",
            json={"name": "persisted-group", "description": "Should persist"},
        )
        group = group_manager.get_group_by_name("persisted-group")
        assert group is not None
        assert group.is_default is False

    def test_create_group_service_layer(self, group_manager):
        """Test create_group service method sets is_default=FALSE."""
        group = group_manager.create_group("service-test", "Service layer test")
        assert group.is_default is False


class TestAC2CustomGroupsStartEmpty:
    """AC2: Custom Groups Start Empty - only cidx-meta accessible."""

    def test_new_custom_group_only_has_cidx_meta(self, group_manager):
        """Test that new custom group only has cidx-meta accessible."""
        custom = group_manager.create_group("empty-custom", "Empty group")
        repos = group_manager.get_group_repos(custom.id)
        assert repos == ["cidx-meta"]

    def test_new_custom_group_no_explicit_repo_grants(
        self, group_manager, temp_db_path
    ):
        """Test that new custom group has no explicit repo grants."""
        custom = group_manager.create_group("no-grants", "No grants group")
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?",
            (custom.id,),
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0


class TestAC3ReadCustomGroup:
    """AC3: Read Custom Group - GET returns full details with user_count."""

    def test_get_custom_group_returns_200(self, test_client, group_manager):
        """Test that GET /api/v1/groups/{id} returns 200."""
        custom = group_manager.create_group("readable", "Readable group")
        response = test_client.get(f"/api/v1/groups/{custom.id}")
        assert response.status_code == 200

    def test_get_custom_group_returns_full_details(self, test_client, group_manager):
        """Test that GET returns all required fields."""
        custom = group_manager.create_group("detailed", "Detailed group")
        response = test_client.get(f"/api/v1/groups/{custom.id}")
        data = response.json()
        assert data["id"] == custom.id
        assert data["name"] == "detailed"
        assert "user_count" in data
        assert "accessible_repos" in data

    def test_get_custom_group_user_count_initially_zero(
        self, test_client, group_manager
    ):
        """Test that new custom group has user_count of 0."""
        custom = group_manager.create_group("zero-users", "No users yet")
        response = test_client.get(f"/api/v1/groups/{custom.id}")
        data = response.json()
        assert data["user_count"] == 0

    def test_get_nonexistent_group_returns_404(self, test_client):
        """Test that GET for nonexistent group returns 404."""
        response = test_client.get("/api/v1/groups/99999")
        assert response.status_code == 404


class TestAC4UpdateCustomGroup:
    """AC4: Update Custom Group - PUT updates name/description, returns 200."""

    def test_update_custom_group_name_returns_200(self, test_client, group_manager):
        """Test that PUT with new name returns 200."""
        custom = group_manager.create_group("old-name", "Description")
        response = test_client.put(
            f"/api/v1/groups/{custom.id}",
            json={"name": "new-name"},
        )
        assert response.status_code == 200

    def test_update_custom_group_name_changes_name(self, test_client, group_manager):
        """Test that PUT with new name actually changes the name."""
        custom = group_manager.create_group("rename-me", "Description")
        response = test_client.put(
            f"/api/v1/groups/{custom.id}",
            json={"name": "renamed"},
        )
        data = response.json()
        assert data["name"] == "renamed"

    def test_update_nonexistent_group_returns_404(self, test_client):
        """Test that PUT for nonexistent group returns 404."""
        response = test_client.put(
            "/api/v1/groups/99999",
            json={"name": "wont-work"},
        )
        assert response.status_code == 404

    def test_update_default_group_returns_400(self, test_client, group_manager):
        """Test that PUT for default group returns 400."""
        admins = group_manager.get_group_by_name("admins")
        response = test_client.put(
            f"/api/v1/groups/{admins.id}",
            json={"name": "new-admins"},
        )
        assert response.status_code == 400

    def test_update_service_layer_default_group_fails(self, group_manager):
        """Test that update_group fails for default groups."""
        admins = group_manager.get_group_by_name("admins")
        with pytest.raises(ValueError) as exc_info:
            group_manager.update_group(admins.id, name="new-admins")
        assert "default" in str(exc_info.value).lower()

    def test_update_custom_group_description_only(self, test_client, group_manager):
        """Test that PUT with only description updates it."""
        custom = group_manager.create_group("desc-test", "Original")
        response = test_client.put(
            f"/api/v1/groups/{custom.id}",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["name"] == "desc-test"  # Name unchanged
