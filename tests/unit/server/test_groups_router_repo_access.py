"""
Unit tests for Groups Router - Repository Access Endpoints.

Story #706: Repository-to-Group Access Mapping with Auto-Assignment

This file covers AC7: API Endpoints for Repo Access Management:
- POST /api/v1/groups/{id}/repos - Add repo to group (201 Created)
- DELETE /api/v1/groups/{id}/repos/{repo} - Remove repo from group (204 No Content)
- DELETE cidx-meta returns 400 Bad Request (cannot revoke)

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
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
    from fastapi import FastAPI
    from code_indexer.server.routers.groups import router, set_group_manager
    from code_indexer.server.routers.groups import get_group_manager
    from code_indexer.server.auth.dependencies import (
        get_current_admin_user,
        get_current_user,
    )

    app = FastAPI()
    app.include_router(router)

    # Set the group manager
    set_group_manager(group_manager)

    # Override auth dependencies using FastAPI's dependency_overrides
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_group_manager] = lambda: group_manager

    yield TestClient(app)

    # Clear overrides after test
    app.dependency_overrides.clear()


class TestAddRepoToGroup:
    """Tests for POST /api/v1/groups/{id}/repos endpoint."""

    def test_add_repo_to_group_returns_201(self, test_client, group_manager):
        """Test that adding repo to group returns 201 Created."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repo_name": "test-repo"},
        )

        assert response.status_code == 201

    def test_add_repo_to_group_creates_access(self, test_client, group_manager):
        """Test that adding repo to group creates access record."""
        admins = group_manager.get_group_by_name("admins")

        test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repo_name": "new-repo"},
        )

        repos = group_manager.get_group_repos(admins.id)
        assert "new-repo" in repos

    def test_add_repo_to_nonexistent_group_returns_404(self, test_client):
        """Test that adding repo to nonexistent group returns 404."""
        response = test_client.post(
            "/api/v1/groups/99999/repos",
            json={"repo_name": "test-repo"},
        )

        assert response.status_code == 404

    def test_add_repo_records_granted_by(self, test_client, group_manager):
        """Test that adding repo records the admin who granted access."""
        admins = group_manager.get_group_by_name("admins")

        test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repo_name": "test-repo"},
        )

        record = group_manager.get_repo_access("test-repo", admins.id)
        assert record is not None
        assert record.granted_by == "admin_user"

    def test_add_duplicate_repo_returns_200(self, test_client, group_manager):
        """Test that adding duplicate repo is idempotent (200 OK)."""
        admins = group_manager.get_group_by_name("admins")

        # Add first time
        test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repo_name": "test-repo"},
        )

        # Add second time - should be idempotent
        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repo_name": "test-repo"},
        )

        assert response.status_code == 200


class TestRemoveRepoFromGroup:
    """Tests for DELETE /api/v1/groups/{id}/repos/{repo} endpoint."""

    def test_remove_repo_from_group_returns_204(self, test_client, group_manager):
        """Test that removing repo from group returns 204 No Content."""
        admins = group_manager.get_group_by_name("admins")

        # First add the repo
        group_manager.grant_repo_access("test-repo", admins.id, "admin")

        response = test_client.delete(f"/api/v1/groups/{admins.id}/repos/test-repo")

        assert response.status_code == 204

    def test_remove_repo_from_group_removes_access(self, test_client, group_manager):
        """Test that removing repo from group removes access record."""
        admins = group_manager.get_group_by_name("admins")

        # First add the repo
        group_manager.grant_repo_access("test-repo", admins.id, "admin")
        assert "test-repo" in group_manager.get_group_repos(admins.id)

        test_client.delete(f"/api/v1/groups/{admins.id}/repos/test-repo")

        repos = group_manager.get_group_repos(admins.id)
        assert "test-repo" not in repos

    def test_remove_nonexistent_repo_returns_404(self, test_client, group_manager):
        """Test that removing nonexistent repo returns 404."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.delete(
            f"/api/v1/groups/{admins.id}/repos/nonexistent-repo"
        )

        assert response.status_code == 404

    def test_remove_cidx_meta_returns_400(self, test_client, group_manager):
        """Test that removing cidx-meta returns 400 Bad Request."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.delete(f"/api/v1/groups/{admins.id}/repos/cidx-meta")

        assert response.status_code == 400
        assert "cidx-meta" in response.json()["detail"].lower()

    def test_remove_from_nonexistent_group_returns_404(self, test_client):
        """Test that removing from nonexistent group returns 404."""
        response = test_client.delete("/api/v1/groups/99999/repos/test-repo")

        assert response.status_code == 404
