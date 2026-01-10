"""
Unit tests for Admin Bulk Repository Operations.

Story #710: Admin User and Group Management Interface

This file covers:
- AC4: Bulk Add Repos to Group - POST /api/v1/groups/{id}/repos with {"repos": [...]}
- AC5: Bulk Remove Repos from Group - DELETE /api/v1/groups/{id}/repos with {"repos": [...]}

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


class TestAC4BulkAddReposToGroup:
    """
    AC4: Bulk Add Repos to Group
    - POST /api/v1/groups/{id}/repos with {"repos": ["a", "b", "c"]}
    - Adds all repos to group access
    - Returns count of repos added
    - Skips already-accessible repos (no error)
    """

    def test_bulk_add_repos_returns_success(self, test_client, group_manager):
        """Test POST /api/v1/groups/{id}/repos with bulk payload returns success."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2", "repo3"]},
        )

        assert response.status_code in [200, 201]

    def test_bulk_add_repos_adds_all_repos(self, test_client, group_manager):
        """Test POST /api/v1/groups/{id}/repos adds all repos to group."""
        admins = group_manager.get_group_by_name("admins")

        test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2", "repo3"]},
        )

        repos = group_manager.get_group_repos(admins.id)
        assert "repo1" in repos
        assert "repo2" in repos
        assert "repo3" in repos

    def test_bulk_add_repos_returns_count_added(self, test_client, group_manager):
        """Test POST /api/v1/groups/{id}/repos returns count of repos added."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2", "repo3"]},
        )
        data = response.json()

        assert "added" in data
        assert data["added"] == 3

    def test_bulk_add_repos_skips_existing_no_error(self, test_client, group_manager):
        """Test POST /api/v1/groups/{id}/repos skips already-accessible repos."""
        admins = group_manager.get_group_by_name("admins")

        # Pre-add repo1
        group_manager.grant_repo_access("repo1", admins.id, "admin_user")

        # Try to add repo1 + repo2
        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": ["repo1", "repo2"]}
        )

        # Should succeed without error
        assert response.status_code in [200, 201]
        data = response.json()
        # Only repo2 should be newly added
        assert data["added"] == 1

    def test_bulk_add_repos_nonexistent_group_returns_404(self, test_client):
        """Test POST /api/v1/groups/{id}/repos returns 404 for nonexistent group."""
        response = test_client.post(
            "/api/v1/groups/99999/repos", json={"repos": ["repo1", "repo2"]}
        )

        assert response.status_code == 404

    def test_bulk_add_empty_list_returns_validation_error(
        self, test_client, group_manager
    ):
        """Test POST /api/v1/groups/{id}/repos with empty list returns 422."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.post(
            f"/api/v1/groups/{admins.id}/repos", json={"repos": []}
        )

        # Empty list is invalid input - fail fast
        assert response.status_code == 422


class TestAC5BulkRemoveReposFromGroup:
    """
    AC5: Bulk Remove Repos from Group
    - DELETE /api/v1/groups/{id}/repos with {"repos": ["a", "b"]}
    - Removes all repos from group access
    - cidx-meta cannot be removed (silently skipped)
    - Returns count removed
    """

    def test_bulk_remove_repos_returns_200(self, test_client, group_manager):
        """Test DELETE /api/v1/groups/{id}/repos with bulk payload returns 200."""
        admins = group_manager.get_group_by_name("admins")

        # First add some repos
        group_manager.grant_repo_access("repo1", admins.id, "admin_user")
        group_manager.grant_repo_access("repo2", admins.id, "admin_user")

        response = test_client.request(
            "DELETE",
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2"]},
        )

        assert response.status_code == 200

    def test_bulk_remove_repos_removes_all_repos(self, test_client, group_manager):
        """Test DELETE /api/v1/groups/{id}/repos removes all specified repos."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("repo1", admins.id, "admin_user")
        group_manager.grant_repo_access("repo2", admins.id, "admin_user")

        test_client.request(
            "DELETE",
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2"]},
        )

        repos = group_manager.get_group_repos(admins.id)
        assert "repo1" not in repos
        assert "repo2" not in repos

    def test_bulk_remove_repos_returns_count_removed(self, test_client, group_manager):
        """Test DELETE /api/v1/groups/{id}/repos returns count of repos removed."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("repo1", admins.id, "admin_user")
        group_manager.grant_repo_access("repo2", admins.id, "admin_user")

        response = test_client.request(
            "DELETE",
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "repo2"]},
        )
        data = response.json()

        assert "removed" in data
        assert data["removed"] == 2

    def test_bulk_remove_cidx_meta_silently_skipped(self, test_client, group_manager):
        """Test DELETE /api/v1/groups/{id}/repos silently skips cidx-meta."""
        admins = group_manager.get_group_by_name("admins")

        group_manager.grant_repo_access("repo1", admins.id, "admin_user")

        # Try to remove both repo1 and cidx-meta
        response = test_client.request(
            "DELETE",
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["repo1", "cidx-meta"]},
        )

        # Should succeed without error
        assert response.status_code == 200
        data = response.json()
        # Only repo1 should be removed
        assert data["removed"] == 1

        # cidx-meta should still be accessible
        repos = group_manager.get_group_repos(admins.id)
        assert "cidx-meta" in repos

    def test_bulk_remove_nonexistent_repos_no_error(self, test_client, group_manager):
        """Test DELETE /api/v1/groups/{id}/repos handles nonexistent repos."""
        admins = group_manager.get_group_by_name("admins")

        response = test_client.request(
            "DELETE",
            f"/api/v1/groups/{admins.id}/repos",
            json={"repos": ["nonexistent1", "nonexistent2"]},
        )

        # Should succeed without error
        assert response.status_code == 200
        data = response.json()
        assert data["removed"] == 0

    def test_bulk_remove_nonexistent_group_returns_404(self, test_client):
        """Test DELETE /api/v1/groups/{id}/repos returns 404 for nonexistent group."""
        response = test_client.request(
            "DELETE", "/api/v1/groups/99999/repos", json={"repos": ["repo1"]}
        )

        assert response.status_code == 404
