"""
Unit tests for git staging/commit router endpoints.

Tests git_stage, git_unstage, and git_commit endpoints with mocked GitOperationsService.
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


class TestGitStage:
    """Tests for POST /api/v1/repos/{alias}/git/stage endpoint."""

    def test_git_stage_success(self, client, mock_git_service):
        """Test successful staging of files."""
        mock_git_service.stage_files.return_value = {
            "success": True,
            "staged_files": ["file1.py", "file2.py"],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/stage",
            json={"file_paths": ["file1.py", "file2.py"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["staged_files"]) == 2

    def test_git_stage_empty_list(self, client, mock_git_service):
        """Test staging with empty file list."""
        mock_git_service.stage_files.return_value = {
            "success": True,
            "staged_files": [],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/stage",
            json={"file_paths": []},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_git_stage_repo_not_found(self, client, mock_git_service):
        """Test staging with non-existent repository."""
        mock_git_service.stage_files.side_effect = FileNotFoundError(
            "Repository not found"
        )

        response = client.post(
            "/api/v1/repos/nonexistent/git/stage",
            json={"file_paths": ["file1.py"]},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGitUnstage:
    """Tests for POST /api/v1/repos/{alias}/git/unstage endpoint."""

    def test_git_unstage_success(self, client, mock_git_service):
        """Test successful unstaging of files."""
        mock_git_service.unstage_files.return_value = {
            "success": True,
            "unstaged_files": ["file1.py"],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/unstage",
            json={"file_paths": ["file1.py"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "file1.py" in data["unstaged_files"]

    def test_git_unstage_all(self, client, mock_git_service):
        """Test unstaging all files."""
        mock_git_service.unstage_files.return_value = {
            "success": True,
            "unstaged_files": ["file1.py", "file2.py", "file3.py"],
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/unstage",
            json={"file_paths": []},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["unstaged_files"]) == 3

    def test_git_unstage_repo_not_found(self, client, mock_git_service):
        """Test unstaging with non-existent repository."""
        mock_git_service.unstage_files.side_effect = FileNotFoundError(
            "Repository not found"
        )

        response = client.post(
            "/api/v1/repos/nonexistent/git/unstage",
            json={"file_paths": ["file1.py"]},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGitCommit:
    """Tests for POST /api/v1/repos/{alias}/git/commit endpoint."""

    def test_git_commit_success(self, client, mock_git_service):
        """Test successful commit creation."""
        mock_git_service.create_commit.return_value = {
            "success": True,
            "commit_hash": "abc123def456",
            "message": "Test commit",
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/commit",
            json={"message": "Test commit"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["commit_hash"] == "abc123def456"
        assert data["message"] == "Test commit"

    def test_git_commit_with_author(self, client, mock_git_service):
        """Test commit with custom author info."""
        mock_git_service.create_commit.return_value = {
            "success": True,
            "commit_hash": "def456abc123",
            "message": "Custom author commit",
        }

        response = client.post(
            "/api/v1/repos/test-repo/git/commit",
            json={
                "message": "Custom author commit",
                "author_name": "Test User",
                "author_email": "test@example.com",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_git_commit_empty_message(self, client, mock_git_service):
        """Test commit with empty message (should fail validation)."""
        mock_git_service.create_commit.side_effect = ValueError(
            "Commit message cannot be empty"
        )

        response = client.post(
            "/api/v1/repos/test-repo/git/commit",
            json={"message": ""},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
