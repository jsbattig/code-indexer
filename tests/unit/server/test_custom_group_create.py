"""
Unit tests for Story #709: Custom Group Management - AC1 and AC2.

TDD Tests covering:
- AC1: Create Custom Group (POST /api/v1/groups)
- AC2: Custom Groups Start Empty (no repo access except cidx-meta)

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


# Constants
NONEXISTENT_GROUP_ID = 99999
MAX_GROUP_NAME_LENGTH = 100


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


class TestAC1CreateCustomGroup:
    """AC1: POST /api/v1/groups creates new group with name, description."""

    def test_post_groups_creates_custom_group(
        self, client, admin_auth_token, group_manager
    ):
        """Test POST /api/v1/groups creates a new custom group."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "frontend-team", "description": "Frontend developers"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "frontend-team"
        assert data["description"] == "Frontend developers"
        assert data["is_default"] is False

    def test_post_groups_returns_201_created(
        self, client, admin_auth_token, group_manager
    ):
        """Test POST /api/v1/groups returns 201 Created status."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "backend-team", "description": "Backend developers"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        assert response.status_code == 201

    def test_post_groups_returns_group_details(
        self, client, admin_auth_token, group_manager
    ):
        """Test POST /api/v1/groups returns complete group details."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "qa-team", "description": "QA testers"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "description" in data
        assert "is_default" in data
        assert "created_at" in data

    def test_post_groups_is_default_false(
        self, client, admin_auth_token, group_manager
    ):
        """Test that custom groups have is_default=FALSE."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "devops-team", "description": "DevOps engineers"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )

        data = response.json()
        assert data["is_default"] is False

    def test_post_groups_requires_admin(self, client, mock_user_manager, group_manager):
        """Test POST /api/v1/groups requires admin role."""
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

        response = client.post(
            "/api/v1/groups",
            json={"name": "test-group", "description": "Test"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    def test_post_groups_validates_name_not_empty(
        self, client, admin_auth_token, group_manager
    ):
        """Test group name validation: cannot be empty."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "", "description": "Empty name test"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        assert response.status_code == 422

    def test_post_groups_validates_name_max_length(
        self, client, admin_auth_token, group_manager
    ):
        """Test group name validation: max 100 characters."""
        long_name = "a" * (MAX_GROUP_NAME_LENGTH + 1)
        response = client.post(
            "/api/v1/groups",
            json={"name": long_name, "description": "Long name test"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        assert response.status_code == 422

    def test_create_group_manager_sets_is_default_false(self, temp_db_path):
        """Test GroupAccessManager.create_group() sets is_default=FALSE."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("custom-group", "A custom group")

        assert group.is_default is False
        assert group.name == "custom-group"


class TestAC2CustomGroupsStartEmpty:
    """AC2: New custom groups have no repository access (except implicit cidx-meta)."""

    def test_new_custom_group_has_only_cidx_meta_access(
        self, client, admin_auth_token, group_manager
    ):
        """Test new custom group only has cidx-meta access."""
        # Create a custom group
        response = client.post(
            "/api/v1/groups",
            json={"name": "empty-group", "description": "Should start empty"},
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        group_id = response.json()["id"]

        # Get group details
        detail_response = client.get(
            f"/api/v1/groups/{group_id}",
            headers={"Authorization": f"Bearer {admin_auth_token}"},
        )
        data = detail_response.json()

        # Only cidx-meta should be accessible (implicit)
        assert data["accessible_repos"] == ["cidx-meta"]

    def test_no_repo_group_access_records_for_new_group(self, temp_db_path):
        """Test no repo_group_access records exist for new custom groups."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("test-group", "Test group")

        # Check database directly for repo_group_access records
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group.id,)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "New custom group should have no repo_group_access records"

    def test_get_group_repos_returns_only_cidx_meta_for_new_group(self, temp_db_path):
        """Test get_group_repos returns only cidx-meta for new custom group."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("new-team", "New team")

        repos = manager.get_group_repos(group.id)

        # cidx-meta is implicit, no other repos
        assert repos == ["cidx-meta"]
