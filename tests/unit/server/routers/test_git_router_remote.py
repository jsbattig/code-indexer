"""
Unit tests for git remote operation router endpoints.

Tests git_push, git_pull, and git_fetch endpoints with mocked GitOperationsService.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from code_indexer.server.app import app
from code_indexer.server.auth.dependencies import get_current_user


@pytest.fixture
def mock_git_service():
    """Mock GitOperationsService."""
    with patch("code_indexer.server.routers.git.GitOperationsService") as mock:
        service_instance = Mock()
        mock.return_value = service_instance
        yield service_instance


@pytest.fixture
def mock_user():
    """Create mock User object for authentication."""
    user = Mock()
    user.username = "testuser"
    return user


@pytest.fixture
def client(mock_user):
    """Create test client with mocked authentication."""

    def mock_get_current_user_dep():
        return mock_user

    # Override get_current_user dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user_dep

    client = TestClient(app)
    yield client

    # Clean up after tests
    app.dependency_overrides.clear()


class TestGitPush:
    """Tests for POST /api/v1/repos/{alias}/git/push endpoint."""

    def test_git_push_success(self, client, mock_git_service):
        """Test successful push operation."""
        mock_git_service.push.return_value = {
            "success": True,
            "pushed_commits": 5,
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/push",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["pushed_commits"] == 5

    def test_git_push_with_branch(self, client, mock_git_service):
        """Test push to specific branch."""
        mock_git_service.push.return_value = {
            "success": True,
            "pushed_commits": 2,
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/push",
            json={"remote": "origin", "branch": "feature-branch"},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_git_push_auth_failure(self, client, mock_git_service):
        """Test push with authentication failure."""
        mock_git_service.push.side_effect = PermissionError("Authentication failed")

        response = client.post(
            "/api/v1/repos/test-repo/git/push",
            json={"remote": "origin"},
        )

        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


class TestGitPull:
    """Tests for POST /api/v1/repos/{alias}/git/pull endpoint."""

    def test_git_pull_success(self, client, mock_git_service):
        """Test successful pull operation."""
        mock_git_service.pull.return_value = {
            "success": True,
            "updated_files": 3,
            "conflicts": [],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/pull",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["updated_files"] == 3
        assert len(data["conflicts"]) == 0

    def test_git_pull_with_conflicts(self, client, mock_git_service):
        """Test pull with merge conflicts."""
        mock_git_service.pull.return_value = {
            "success": False,
            "updated_files": 0,
            "conflicts": ["file1.py", "file2.py"],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/pull",
            json={"remote": "origin"},
        )

        # Conflicts might return 200 with conflict info or 409
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_409_CONFLICT]

    def test_git_pull_network_error(self, client, mock_git_service):
        """Test pull with network error."""
        mock_git_service.pull.side_effect = ConnectionError("Network unreachable")

        response = client.post(
            "/api/v1/repos/test-repo/git/pull",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGitFetch:
    """Tests for POST /api/v1/repos/{alias}/git/fetch endpoint."""

    def test_git_fetch_success(self, client, mock_git_service):
        """Test successful fetch operation."""
        mock_git_service.fetch.return_value = {
            "success": True,
            "fetched_refs": ["refs/heads/main", "refs/heads/develop"],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/fetch",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["fetched_refs"]) == 2

    def test_git_fetch_no_updates(self, client, mock_git_service):
        """Test fetch with no updates."""
        mock_git_service.fetch.return_value = {
            "success": True,
            "fetched_refs": [],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/fetch",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["fetched_refs"]) == 0

    def test_git_fetch_network_error(self, client, mock_git_service):
        """Test fetch with network error."""
        mock_git_service.fetch.side_effect = ConnectionError("Cannot reach remote")

        response = client.post(
            "/api/v1/repos/test-repo/git/fetch",
            json={"remote": "origin"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
