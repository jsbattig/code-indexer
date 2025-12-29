"""
Unit tests for File CRUD REST API endpoints.

Tests the 3 file CRUD endpoints:
- POST /api/v1/repos/{alias}/files (create_file)
- PATCH /api/v1/repos/{alias}/files/{path:path} (edit_file)
- DELETE /api/v1/repos/{alias}/files/{path:path} (delete_file)
"""

import pytest
from datetime import datetime, timezone
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.file_crud_service import HashMismatchError


@pytest.fixture
def app():
    """Create test FastAPI app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Create mock authenticated user."""
    return User(
        username="testuser",
        password_hash="hash",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def mock_admin_user():
    """Create mock admin user."""
    return User(
        username="admin",
        password_hash="hash",
        role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc)
    )


class TestCreateFileEndpoint:
    """Tests for POST /api/v1/repos/{alias}/files endpoint."""

    def test_create_file_endpoint_success(self, app, client, mock_user):
        """Test successful file creation."""
        from code_indexer.server.auth.dependencies import get_current_user

        # Override FastAPI dependency
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
                # Mock service response
                mock_service = MockService.return_value
                mock_service.create_file.return_value = {
                    "success": True,
                    "file_path": "src/test.py",
                    "content_hash": "abc123",
                    "size_bytes": 100,
                    "created_at": "2025-12-27T12:00:00Z"
                }

                # Make request
                response = client.post(
                    "/api/v1/repos/test-repo/files",
                    json={"file_path": "src/test.py", "content": "print('hello')"}
                )

                # Assertions
                assert response.status_code == status.HTTP_201_CREATED
                data = response.json()
                assert data["success"] is True
                assert data["file_path"] == "src/test.py"
                assert data["content_hash"] == "abc123"
                assert data["size_bytes"] == 100

                # Verify service was called correctly
                mock_service.create_file.assert_called_once_with(
                    repo_alias="test-repo",
                    file_path="src/test.py",
                    content="print('hello')",
                    username="testuser"
                )
        finally:
            # Clean up dependency override
            app.dependency_overrides.clear()

    def test_create_file_endpoint_unauthorized(self, client):
        """Test create file without authentication returns 401."""
        response = client.post(
            "/api/v1/repos/test-repo/files",
            json={"file_path": "src/test.py", "content": "print('hello')"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "WWW-Authenticate" in response.headers

    def test_create_file_endpoint_git_blocked(self, app, client, mock_user):
        """Test create file in .git/ directory returns 403."""
        from code_indexer.server.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
                mock_service = MockService.return_value
                mock_service.create_file.side_effect = PermissionError("Cannot modify .git/ directory")

                response = client.post(
                    "/api/v1/repos/test-repo/files",
                    json={"file_path": ".git/config", "content": "bad"}
                )

                assert response.status_code == status.HTTP_403_FORBIDDEN
                assert "git" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_file_endpoint_already_exists(self, app, client, mock_user):
        """Test create file that already exists returns 409."""
        from code_indexer.server.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
                mock_service = MockService.return_value
                mock_service.create_file.side_effect = FileExistsError("File already exists")

                response = client.post(
                    "/api/v1/repos/test-repo/files",
                    json={"file_path": "src/existing.py", "content": "code"}
                )

                assert response.status_code == status.HTTP_409_CONFLICT
                assert "already exists" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_file_endpoint_invalid_request(self, app, client, mock_user):
        """Test create file with missing parameters returns 422."""
        from code_indexer.server.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            # Missing content field
            response = client.post(
                "/api/v1/repos/test-repo/files",
                json={"file_path": "src/test.py"}
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    def test_create_file_endpoint_repo_not_found(self, app, client, mock_user):
        """Test create file in non-existent repo returns 404."""
        from code_indexer.server.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("code_indexer.server.routers.files.FileCRUDService") as MockService:
                mock_service = MockService.return_value
                mock_service.create_file.side_effect = FileNotFoundError("Repository not found")

                response = client.post(
                    "/api/v1/repos/nonexistent/files",
                    json={"file_path": "src/test.py", "content": "code"}
                )

                assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()
