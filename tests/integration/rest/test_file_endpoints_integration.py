"""
Integration tests for File CRUD REST endpoints (Story #629).

These are integration tests using:
- Real FastAPI TestClient making actual HTTP requests
- Mocked service layer methods (following codebase pattern)
- Authentication bypass for testing

Tests 3 endpoints:
- POST /api/v1/repos/{alias}/files (create_file)
- PATCH /api/v1/repos/{alias}/files/{path:path} (edit_file)
- DELETE /api/v1/repos/{alias}/files/{path:path} (delete_file)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from code_indexer.server.app import create_app
from code_indexer.server.auth.dependencies import get_current_user


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def mock_user():
    """Create mock User object for authentication bypass."""
    user = Mock()
    user.username = "testuser"
    user.role = "user"
    return user


@pytest.fixture(scope="module")
def test_app(mock_user):
    """Create FastAPI test app with authentication bypass."""

    def mock_get_current_user_dep():
        return mock_user

    # Create app
    app = create_app()

    # Override authentication dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user_dep

    yield app

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client(test_app):
    """Create TestClient for making HTTP requests."""
    return TestClient(test_app)


# ============================================================================
# INTEGRATION TESTS - FILE CRUD ENDPOINTS
# ============================================================================


def test_create_file_integration(client):
    """
    Integration test: POST /api/v1/repos/{alias}/files

    Tests full HTTP request → router → service layer flow.
    """
    # Mock the service method
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.create_file.return_value = {
            "success": True,
            "file_path": "src/test.py",
            "content_hash": "abc123hash",
            "size_bytes": 15,
            "created_at": "2025-01-15T10:00:00Z",
        }

        # Make HTTP request
        response = client.post(
            "/api/v1/repos/test-repo/files",
            json={"file_path": "src/test.py", "content": "print('hello')"},
        )

    # Verify HTTP response
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["file_path"] == "src/test.py"
    assert data["content_hash"] == "abc123hash"
    assert data["size_bytes"] == 15
    assert "created_at" in data

    # Verify service was called with correct parameters
    mock_service.create_file.assert_called_once_with(
        repo_alias="test-repo",
        file_path="src/test.py",
        content="print('hello')",
        username="testuser",
    )


def test_edit_file_integration(client):
    """
    Integration test: PATCH /api/v1/repos/{alias}/files/{path:path}

    Tests full HTTP request → router → service layer flow.
    """
    # Mock the service method
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.edit_file.return_value = {
            "success": True,
            "file_path": "src/test.py",
            "content_hash": "def456hash",
            "modified_at": "2025-01-15T10:05:00Z",
            "changes_made": 1,
        }

        # Make HTTP request
        response = client.patch(
            "/api/v1/repos/test-repo/files/src/test.py",
            json={
                "old_string": "hello",
                "new_string": "world",
                "content_hash": "abc123",
                "replace_all": False,
            },
        )

    # Verify HTTP response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_path"] == "src/test.py"
    assert data["content_hash"] == "def456hash"
    assert data["changes_made"] == 1
    assert "modified_at" in data

    # Verify service was called with correct parameters
    mock_service.edit_file.assert_called_once_with(
        repo_alias="test-repo",
        file_path="src/test.py",
        old_string="hello",
        new_string="world",
        content_hash="abc123",
        replace_all=False,
        username="testuser",
    )


def test_delete_file_integration(client):
    """
    Integration test: DELETE /api/v1/repos/{alias}/files/{path:path}

    Tests full HTTP request → router → service layer flow.
    """
    # Mock the service method
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.delete_file.return_value = {
            "success": True,
            "file_path": "src/test.py",
            "deleted_at": "2025-01-15T10:10:00Z",
        }

        # Make HTTP request
        response = client.delete("/api/v1/repos/test-repo/files/src/test.py")

    # Verify HTTP response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_path"] == "src/test.py"
    assert "deleted_at" in data

    # Verify service was called with correct parameters
    mock_service.delete_file.assert_called_once_with(
        repo_alias="test-repo",
        file_path="src/test.py",
        content_hash=None,
        username="testuser",
    )


def test_delete_file_with_content_hash(client):
    """
    Integration test: DELETE /api/v1/repos/{alias}/files/{path:path}?content_hash=X

    Verify content_hash parameter is passed when provided.
    """
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.delete_file.return_value = {
            "success": True,
            "file_path": "src/test.py",
            "deleted_at": "2025-01-15T10:10:00Z",
        }

        response = client.delete(
            "/api/v1/repos/test-repo/files/src/test.py?content_hash=abc123def"
        )

    assert response.status_code == 200
    assert response.json()["success"] is True

    # Verify content_hash was passed to service
    mock_service.delete_file.assert_called_once_with(
        repo_alias="test-repo",
        file_path="src/test.py",
        content_hash="abc123def",  # Should pass hash, not None
        username="testuser",
    )


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================


def test_create_file_repository_not_found(client):
    """Integration test: Verify 404 when repository doesn't exist."""
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.create_file.side_effect = FileNotFoundError("Repository not found")

        response = client.post(
            "/api/v1/repos/nonexistent-repo/files",
            json={"file_path": "test.py", "content": "test"},
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_file_already_exists(client):
    """Integration test: Verify 409 when file already exists."""
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.create_file.side_effect = FileExistsError("File already exists")

        response = client.post(
            "/api/v1/repos/test-repo/files",
            json={"file_path": "existing.py", "content": "test"},
        )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_create_file_git_directory_blocked(client):
    """Integration test: Verify 403 when attempting to create file in .git/ directory."""
    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.create_file.side_effect = PermissionError(
            ".git/ directory access blocked"
        )

        response = client.post(
            "/api/v1/repos/test-repo/files",
            json={"file_path": ".git/config", "content": "malicious"},
        )

    assert response.status_code == 403
    detail = response.json()["detail"].lower()
    assert "blocked" in detail or "permission" in detail or ".git" in detail


def test_edit_file_hash_mismatch(client):
    """Integration test: Verify 409 when content hash doesn't match."""
    # Import custom exception
    from code_indexer.server.services.file_crud_service import HashMismatchError

    with patch(
        "code_indexer.server.routers.files.FileCRUDService"
    ) as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.edit_file.side_effect = HashMismatchError("Hash mismatch")

        response = client.patch(
            "/api/v1/repos/test-repo/files/test.py",
            json={
                "old_string": "old",
                "new_string": "new",
                "content_hash": "wronghash",
                "replace_all": False,
            },
        )

    assert response.status_code == 409
    assert "mismatch" in response.json()["detail"].lower()
