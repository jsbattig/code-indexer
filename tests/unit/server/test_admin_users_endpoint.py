"""
Unit tests for GET /api/admin/users/{username} endpoint - Story #492.

Tests single-user lookup functionality:
- GET /api/admin/users/{username} - retrieve specific user details
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.mark.e2e
class TestGetUserByUsernameEndpoint:
    """Test GET /api/admin/users/{username} endpoint for retrieving specific user."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_get_user_by_username_success_returns_200(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test getting user by username with valid admin returns 200 with user details."""
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock the user being looked up
        target_user = User(
            username="testuser",
            password_hash="$2b$12$targethash",
            role=UserRole.POWER_USER,
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        mock_app_user_manager.get_user.return_value = target_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.get("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        # Verify response structure
        assert "username" in response_data
        assert "role" in response_data
        assert "created_at" in response_data

        # Verify response values
        assert response_data["username"] == "testuser"
        assert response_data["role"] == "power_user"
        assert response_data["created_at"] is not None

        # Verify get_user was called correctly
        mock_app_user_manager.get_user.assert_called_once_with("testuser")

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_get_user_by_username_not_found_returns_404(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test getting non-existent user returns 404."""
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock user not found
        mock_app_user_manager.get_user.return_value = None

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.get("/api/admin/users/nonexistent", headers=headers)

        assert response.status_code == 404
        response_data = response.json()

        assert "detail" in response_data
        assert "not found" in response_data["detail"].lower()
        assert "nonexistent" in response_data["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_get_user_by_username_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test getting user as non-admin returns 403."""
        # Setup authentication for power user
        mock_jwt_manager.validate_token.return_value = {
            "username": "poweruser",
            "role": "power_user",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = power_user

        headers = {"Authorization": "Bearer power.jwt.token"}
        response = client.get("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 403
        response_data = response.json()

        assert "detail" in response_data

    def test_get_user_by_username_no_auth_returns_401(self, client):
        """Test getting user without authentication returns 401 per MCP spec (RFC 9728)."""
        # No authentication headers
        response = client.get("/api/admin/users/testuser")

        # Should return 401 per MCP spec (RFC 9728) with WWW-Authenticate header
        assert response.status_code == 401
        assert "www-authenticate" in response.headers

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_get_user_by_username_invalid_token_returns_401(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test getting user with invalid token returns 401."""
        from code_indexer.server.auth.jwt_manager import InvalidTokenError

        # Mock invalid token
        mock_jwt_manager.validate_token.side_effect = InvalidTokenError("Invalid token")

        headers = {"Authorization": "Bearer invalid.token"}
        response = client.get("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 401

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_get_user_does_not_expose_password_hash(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test that user lookup does not expose password hash."""
        # Setup authentication for admin
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock user with password hash
        target_user = User(
            username="testuser",
            password_hash="$2b$12$secrethash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_app_user_manager.get_user.return_value = target_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.get("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        # Verify password_hash is NOT in response
        assert "password_hash" not in response_data
        assert "password" not in response_data
        assert "$2b$12$secrethash" not in str(response_data)
