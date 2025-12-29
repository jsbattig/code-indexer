"""
Unit tests for git status/inspection router endpoints.

Tests git_status, git_diff, and git_log endpoints with mocked GitOperationsService.
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


class TestGitStatus:
    """Tests for GET /api/v1/repos/{alias}/git/status endpoint."""

    def test_git_status_success(self, client, mock_git_service):
        """Test successful git status retrieval."""
        mock_git_service.get_status.return_value = {
            "success": True,
            "staged": ["file1.py"],
            "unstaged": ["file2.py"],
            "untracked": ["file3.py"],
        }

        response = client.get("/api/v1/repos/test-repo/git/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["staged"]) == 1
        mock_git_service.get_status.assert_called_once()

    def test_git_status_repo_not_found(self, client, mock_git_service):
        """Test git status with non-existent repository."""
        mock_git_service.get_status.side_effect = FileNotFoundError("Repository not found")

        response = client.get("/api/v1/repos/nonexistent/git/status")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_git_status_internal_error(self, client, mock_git_service):
        """Test git status with internal error."""
        mock_git_service.get_status.side_effect = Exception("Internal error")

        response = client.get("/api/v1/repos/test-repo/git/status")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGitDiff:
    """Tests for GET /api/v1/repos/{alias}/git/diff endpoint."""

    def test_git_diff_success(self, client, mock_git_service):
        """Test successful git diff retrieval."""
        mock_git_service.get_diff.return_value = {
            "success": True,
            "diff_text": "diff --git a/file1.py b/file1.py...",
            "files_changed": 2,
        }

        response = client.get("/api/v1/repos/test-repo/git/diff")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "diff --git" in data["diff_text"]
        assert data["files_changed"] == 2

    def test_git_diff_with_file_paths(self, client, mock_git_service):
        """Test git diff with specific file paths filter."""
        mock_git_service.get_diff.return_value = {
            "success": True,
            "diff_text": "diff content",
            "files_changed": 1,
        }

        response = client.get("/api/v1/repos/test-repo/git/diff?file_paths=file1.py,file2.py")

        assert response.status_code == status.HTTP_200_OK

    def test_git_diff_repo_not_found(self, client, mock_git_service):
        """Test git diff with non-existent repository."""
        mock_git_service.get_diff.side_effect = FileNotFoundError("Repository not found")

        response = client.get("/api/v1/repos/nonexistent/git/diff")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGitLog:
    """Tests for GET /api/v1/repos/{alias}/git/log endpoint."""

    def test_git_log_success(self, client, mock_git_service):
        """Test successful git log retrieval."""
        mock_git_service.get_log.return_value = {
            "success": True,
            "commits": [
                {
                    "commit_hash": "abc123",
                    "author": "User1",
                    "date": "2025-01-01",
                    "message": "Commit message",
                }
            ],
        }

        response = client.get("/api/v1/repos/test-repo/git/log")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["commits"]) == 1
        assert data["commits"][0]["commit_hash"] == "abc123"

    def test_git_log_with_limit(self, client, mock_git_service):
        """Test git log with limit parameter."""
        mock_git_service.get_log.return_value = {
            "success": True,
            "commits": [],
        }

        response = client.get("/api/v1/repos/test-repo/git/log?limit=5")

        assert response.status_code == status.HTTP_200_OK

    def test_git_log_with_since_date(self, client, mock_git_service):
        """Test git log with since_date filter."""
        mock_git_service.get_log.return_value = {
            "success": True,
            "commits": [],
        }

        response = client.get("/api/v1/repos/test-repo/git/log?since_date=2025-01-01")

        assert response.status_code == status.HTTP_200_OK
