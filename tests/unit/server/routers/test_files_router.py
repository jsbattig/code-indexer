"""
Unit tests for files router endpoints.

Tests REST API endpoints for file CRUD operations following TDD methodology:
- POST /api/v1/repos/{alias}/files (create_file)

Test coverage (incremental approach):
- Phase 1: create_file endpoint tests
- Phase 2: edit_file endpoint tests (to be added)
- Phase 3: delete_file endpoint tests (to be added)
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from code_indexer.server.app import app
from code_indexer.server.auth.dependencies import get_current_user


@pytest.fixture(scope="module")
def mock_user():
    """Create mock User object for authentication."""
    user = Mock()
    user.username = "testuser"
    return user


@pytest.fixture(scope="module")
def test_client(mock_user):
    """Create test client with mocked authentication."""

    def mock_get_current_user_dep():
        return mock_user

    # Override get_current_user dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user_dep

    client = TestClient(app)
    yield client

    # Clean up after all tests in module
    app.dependency_overrides.clear()


# ============================================================================
# TEST GROUP 1: POST /api/v1/repos/{alias}/files (create_file)
# ============================================================================


def test_create_file_endpoint_success(test_client):
    """POST /files should successfully create a file."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service response
        mock_instance.create_file.return_value = {
            "success": True,
            "file_path": "src/new_file.py",
            "content_hash": "abc123",
            "size_bytes": 100,
            "created_at": "2025-01-01T00:00:00Z",
        }

        response = test_client.post(
            "/api/v1/repos/my-repo/files",
            json={"file_path": "src/new_file.py", "content": "def hello(): pass"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["file_path"] == "src/new_file.py"
        assert data["content_hash"] == "abc123"

        # Verify service was called correctly
        mock_instance.create_file.assert_called_once_with(
            repo_alias="my-repo",
            file_path="src/new_file.py",
            content="def hello(): pass",
            username="testuser",
        )


def test_create_file_endpoint_unauthorized():
    """POST /files should return 401 without authentication."""
    # Save and temporarily remove the auth override
    saved_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/repos/my-repo/files",
            json={"file_path": "test.py", "content": "test"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    finally:
        # Restore overrides for subsequent tests
        app.dependency_overrides.update(saved_overrides)


def test_create_file_endpoint_git_blocked(test_client):
    """POST /files should return 403 for .git/ directory access."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising PermissionError
        mock_instance.create_file.side_effect = PermissionError(
            ".git directory access blocked"
        )

        response = test_client.post(
            "/api/v1/repos/my-repo/files",
            json={"file_path": ".git/config", "content": "malicious"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert ".git" in response.json()["detail"].lower()


def test_create_file_endpoint_already_exists(test_client):
    """POST /files should return 409 if file already exists."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising FileExistsError
        mock_instance.create_file.side_effect = FileExistsError(
            "File already exists: existing.py"
        )

        response = test_client.post(
            "/api/v1/repos/my-repo/files",
            json={"file_path": "existing.py", "content": "content"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "existing.py" in response.json()["detail"]


def test_create_file_endpoint_invalid_request(test_client):
    """POST /files should return 422 for invalid request body."""
    # Missing required field 'content'
    response = test_client.post(
        "/api/v1/repos/my-repo/files", json={"file_path": "test.py"}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_file_endpoint_repo_not_found(test_client):
    """POST /files should return 404 if repository not found."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising FileNotFoundError for repo not found
        mock_instance.create_file.side_effect = FileNotFoundError(
            "Repository not found: nonexistent"
        )

        response = test_client.post(
            "/api/v1/repos/nonexistent/files",
            json={"file_path": "test.py", "content": "content"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


# ============================================================================
# TEST GROUP 2: PATCH /api/v1/repos/{alias}/files/{path:path} (edit_file)
# ============================================================================


def test_edit_file_endpoint_success(test_client):
    """PATCH /files/{path} should successfully edit a file."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service response
        mock_instance.edit_file.return_value = {
            "success": True,
            "file_path": "src/example.py",
            "content_hash": "new_hash_456",
            "modified_at": "2025-01-01T00:00:00Z",
            "changes_made": 1,
        }

        response = test_client.patch(
            "/api/v1/repos/my-repo/files/src/example.py",
            json={
                "old_string": "return 42",
                "new_string": "return 100",
                "content_hash": "old_hash_123",
                "replace_all": False,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["file_path"] == "src/example.py"
        assert data["content_hash"] == "new_hash_456"
        assert data["changes_made"] == 1

        # Verify service was called correctly
        mock_instance.edit_file.assert_called_once_with(
            repo_alias="my-repo",
            file_path="src/example.py",
            old_string="return 42",
            new_string="return 100",
            content_hash="old_hash_123",
            replace_all=False,
            username="testuser",
        )


def test_edit_file_endpoint_hash_mismatch(test_client):
    """PATCH /files/{path} should return 409 for hash mismatch."""
    from code_indexer.server.services.file_crud_service import HashMismatchError

    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising HashMismatchError
        mock_instance.edit_file.side_effect = HashMismatchError(
            "Content hash mismatch - file was modified"
        )

        response = test_client.patch(
            "/api/v1/repos/my-repo/files/src/test.py",
            json={
                "old_string": "old",
                "new_string": "new",
                "content_hash": "wrong_hash",
                "replace_all": False,
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "hash" in response.json()["detail"].lower()


def test_edit_file_endpoint_file_not_found(test_client):
    """PATCH /files/{path} should return 404 if file doesn't exist."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising FileNotFoundError
        mock_instance.edit_file.side_effect = FileNotFoundError(
            "File not found: nonexistent.py"
        )

        response = test_client.patch(
            "/api/v1/repos/my-repo/files/nonexistent.py",
            json={
                "old_string": "old",
                "new_string": "new",
                "content_hash": "hash",
                "replace_all": False,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


# ============================================================================
# TEST GROUP 3: DELETE /api/v1/repos/{alias}/files/{path:path} (delete_file)
# ============================================================================


def test_delete_file_endpoint_success(test_client):
    """DELETE /files/{path} should successfully delete a file."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service response
        mock_instance.delete_file.return_value = {
            "success": True,
            "file_path": "src/obsolete.py",
            "deleted_at": "2025-01-01T00:00:00Z",
        }

        response = test_client.delete("/api/v1/repos/my-repo/files/src/obsolete.py")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["file_path"] == "src/obsolete.py"
        assert "deleted_at" in data

        # Verify service was called correctly
        mock_instance.delete_file.assert_called_once_with(
            repo_alias="my-repo",
            file_path="src/obsolete.py",
            content_hash=None,
            username="testuser",
        )


def test_delete_file_endpoint_file_not_found(test_client):
    """DELETE /files/{path} should return 404 if file doesn't exist."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising FileNotFoundError
        mock_instance.delete_file.side_effect = FileNotFoundError(
            "File not found: nonexistent.py"
        )

        response = test_client.delete("/api/v1/repos/my-repo/files/nonexistent.py")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


def test_delete_file_endpoint_permission_denied(test_client):
    """DELETE /files/{path} should return 403 for .git/ directory access."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service raising PermissionError
        mock_instance.delete_file.side_effect = PermissionError(
            ".git directory access blocked"
        )

        response = test_client.delete("/api/v1/repos/my-repo/files/.git/config")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert ".git" in response.json()["detail"].lower()


def test_delete_file_endpoint_path_with_slashes(test_client):
    """DELETE /files/{path} should handle paths with slashes correctly."""
    with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
        mock_instance = Mock()
        MockService.return_value = mock_instance

        # Mock service response
        mock_instance.delete_file.return_value = {
            "success": True,
            "file_path": "deep/nested/path/file.py",
            "deleted_at": "2025-01-01T00:00:00Z",
        }

        response = test_client.delete(
            "/api/v1/repos/my-repo/files/deep/nested/path/file.py"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_path"] == "deep/nested/path/file.py"

        # Verify service was called with correct path
        mock_instance.delete_file.assert_called_once_with(
            repo_alias="my-repo",
            file_path="deep/nested/path/file.py",
            content_hash=None,
            username="testuser",
        )
