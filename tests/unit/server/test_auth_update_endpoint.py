"""
Unit tests for PUT /api/auth/update endpoint.

Tests user profile updates (username/email).
Following Anti-Mock: Real JWT, real validation, minimal mocking.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import User, UserRole


class TestAuthUpdateEndpoint:
    """Test PUT /api/auth/update endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager."""
        with patch("src.code_indexer.server.app.user_manager") as mock:
            yield mock

    def test_update_username_success(self, client, mock_user_manager):
        """Test that update endpoint successfully updates username."""
        # Mock login
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user
        mock_user_manager.get_user.return_value = admin_user
        mock_user_manager.update_user.return_value = True

        # Login to get a valid token
        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Call update with new username
        response = client.put(
            "/api/auth/update",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "newadmin"},
        )

        # Should return 200 with success message
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "User updated successfully"
        assert mock_user_manager.update_user.called
        # Verify called with correct parameter names
        mock_user_manager.update_user.assert_called_with(
            "admin", new_username="newadmin"
        )

    def test_update_email_success(self, client, mock_user_manager):
        """Test that update endpoint successfully updates email."""
        # Mock login
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user
        mock_user_manager.get_user.return_value = admin_user
        mock_user_manager.update_user.return_value = True

        # Login to get a valid token
        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Call update with new email
        response = client.put(
            "/api/auth/update",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "newemail@example.com"},
        )

        # Should return 200 with success message
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "User updated successfully"
        assert mock_user_manager.update_user.called
        # Verify called with correct parameter names
        mock_user_manager.update_user.assert_called_with(
            "admin", new_email="newemail@example.com"
        )

    def test_update_duplicate_username_returns_400(self, client, mock_user_manager):
        """Test that updating to duplicate username returns 400 error."""
        # Mock login
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user
        mock_user_manager.get_user.return_value = admin_user
        # Mock update_user to raise ValueError for duplicate
        mock_user_manager.update_user.side_effect = ValueError(
            "Username already exists: taken_username"
        )

        # Login to get a valid token
        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Call update with duplicate username
        response = client.put(
            "/api/auth/update",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "taken_username"},
        )

        # Should return 400 with error message
        assert response.status_code == 400
        data = response.json()
        assert "Username already exists" in data["detail"]
