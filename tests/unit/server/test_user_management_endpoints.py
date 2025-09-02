"""
Unit tests for user management API endpoints - Story 3.

Tests CRUD operations for user management:
- POST /api/admin/users (create user)
- GET /api/admin/users (list users) - already exists, will extend
- PUT /api/admin/users/{username} (update user)
- DELETE /api/admin/users/{username} (delete user)
- PUT /api/users/change-password (current user password change)
- PUT /api/admin/users/{username}/change-password (admin password change)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


class TestUserManagementCRUDEndpoints:
    """Test CRUD operations for user management endpoints."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)


class TestCreateUserEndpoint:
    """Test POST /api/admin/users endpoint for creating users."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_create_user_with_valid_admin_data(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with valid admin data returns 201."""
        # Setup authentication
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

        # Mock successful user creation
        new_user = User(
            username="newadmin",
            password_hash="$2b$12$newhash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_app_user_manager.create_user.return_value = new_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "newadmin",
                "password": "SecurePass123!",
                "role": "admin",
            },
        )

        assert response.status_code == 201
        response_data = response.json()

        assert "user" in response_data
        assert response_data["user"]["username"] == "newadmin"
        assert response_data["user"]["role"] == "admin"
        assert "message" in response_data
        assert "created successfully" in response_data["message"]

        # Verify create_user was called correctly
        mock_app_user_manager.create_user.assert_called_once_with(
            username="newadmin", password="SecurePass123!", role=UserRole.ADMIN
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_create_user_with_valid_power_user_data(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating power user with valid data returns 201."""
        # Setup authentication
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

        # Mock successful user creation
        new_user = User(
            username="newpoweruser",
            password_hash="$2b$12$newhash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_app_user_manager.create_user.return_value = new_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "newpoweruser",
                "password": "ComplexPass456!",
                "role": "power_user",
            },
        )

        assert response.status_code == 201
        response_data = response.json()

        assert response_data["user"]["username"] == "newpoweruser"
        assert response_data["user"]["role"] == "power_user"

        mock_app_user_manager.create_user.assert_called_once_with(
            username="newpoweruser",
            password="ComplexPass456!",
            role=UserRole.POWER_USER,
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_create_user_with_valid_normal_user_data(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating normal user with valid data returns 201."""
        # Setup authentication
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

        # Mock successful user creation
        new_user = User(
            username="newnormaluser",
            password_hash="$2b$12$newhash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_app_user_manager.create_user.return_value = new_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "newnormaluser",
                "password": "SimplePass789!",
                "role": "normal_user",
            },
        )

        assert response.status_code == 201
        response_data = response.json()

        assert response_data["user"]["username"] == "newnormaluser"
        assert response_data["user"]["role"] == "normal_user"

        mock_app_user_manager.create_user.assert_called_once_with(
            username="newnormaluser",
            password="SimplePass789!",
            role=UserRole.NORMAL_USER,
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_create_user_with_duplicate_username_returns_400(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with duplicate username returns 400."""
        # Setup authentication
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

        # Mock duplicate user error
        mock_app_user_manager.create_user.side_effect = ValueError(
            "User already exists: existinguser"
        )

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "existinguser",
                "password": "AnyPassword123!",
                "role": "normal_user",
            },
        )

        assert response.status_code == 400
        response_data = response.json()

        assert "detail" in response_data
        assert "User already exists" in response_data["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_with_invalid_role_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with invalid role returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "testuser",
                "password": "ValidPass123!",
                "role": "invalid_role",
            },
        )

        assert response.status_code == 422
        response_data = response.json()
        assert "detail" in response_data

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_with_weak_password_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with weak password returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "testuser", "password": "weak", "role": "normal_user"},
        )

        assert response.status_code == 422
        response_data = response.json()

        assert "detail" in response_data
        # Check that it's a validation error about password
        assert isinstance(response_data["detail"], list)
        assert len(response_data["detail"]) > 0
        assert "password" in response_data["detail"][0]["loc"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_with_missing_username_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with missing username returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={"password": "ValidPass123!", "role": "normal_user"},
        )

        assert response.status_code == 422

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_with_missing_password_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with missing password returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "testuser", "role": "normal_user"},
        )

        assert response.status_code == 422

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_with_missing_role_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user with missing role returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "testuser", "password": "ValidPass123!"},
        )

        assert response.status_code == 422

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_create_user_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test creating user as non-admin returns 403."""
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
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "testuser",
                "password": "ValidPass123!",
                "role": "normal_user",
            },
        )

        assert response.status_code == 403


class TestUpdateUserEndpoint:
    """Test PUT /api/admin/users/{username} endpoint for updating users."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_update_user_role_returns_200(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test updating user role returns 200."""
        # Setup authentication
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

        # Mock successful update
        mock_app_user_manager.update_user_role.return_value = True

        # Mock user exists
        existing_user = User(
            username="testuser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_app_user_manager.get_user.return_value = existing_user

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.put(
            "/api/admin/users/testuser", headers=headers, json={"role": "admin"}
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "updated successfully" in response_data["message"]

        mock_app_user_manager.update_user_role.assert_called_once_with(
            "testuser", UserRole.ADMIN
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_update_nonexistent_user_returns_404(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test updating nonexistent user returns 404."""
        # Setup authentication
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

        # Mock user doesn't exist
        mock_app_user_manager.get_user.return_value = None

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.put(
            "/api/admin/users/nonexistent", headers=headers, json={"role": "power_user"}
        )

        assert response.status_code == 404
        response_data = response.json()

        assert "detail" in response_data
        assert "User not found" in response_data["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_update_user_with_invalid_role_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test updating user with invalid role returns 422."""
        # Setup authentication
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

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.put(
            "/api/admin/users/testuser", headers=headers, json={"role": "invalid_role"}
        )

        assert response.status_code == 422

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_update_user_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test updating user as non-admin returns 403."""
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
        response = client.put(
            "/api/admin/users/testuser", headers=headers, json={"role": "admin"}
        )

        assert response.status_code == 403


class TestDeleteUserEndpoint:
    """Test DELETE /api/admin/users/{username} endpoint for deleting users."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_delete_user_returns_200(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting user returns 200."""
        # Setup authentication
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

        # Mock successful deletion
        mock_app_user_manager.delete_user.return_value = True

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.delete("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "deleted successfully" in response_data["message"]

        mock_app_user_manager.delete_user.assert_called_once_with("testuser")

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_delete_nonexistent_user_returns_404(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting nonexistent user returns 404."""
        # Setup authentication
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

        # Mock user doesn't exist
        mock_app_user_manager.delete_user.return_value = False

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.delete("/api/admin/users/nonexistent", headers=headers)

        assert response.status_code == 404
        response_data = response.json()

        assert "detail" in response_data
        assert "User not found" in response_data["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_delete_user_non_admin_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting user as non-admin returns 403."""
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
        response = client.delete("/api/admin/users/testuser", headers=headers)

        assert response.status_code == 403

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_delete_last_admin_user_returns_400(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting the last admin user returns 400 with proper error message.

        CRITICAL SECURITY TEST: System must prevent deletion of last admin to avoid lockout.
        """
        # Setup authentication
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

        # Mock system with only one admin user
        all_users = [
            User(
                username="admin",
                password_hash="$2b$12$hash",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="poweruser1",
                password_hash="$2b$12$hash2",
                role=UserRole.POWER_USER,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="normaluser1",
                password_hash="$2b$12$hash3",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        # Mock the get_user call for the user being deleted (admin)
        mock_app_user_manager.get_user.return_value = all_users[0]  # admin user
        mock_app_user_manager.get_all_users.return_value = all_users

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.delete("/api/admin/users/admin", headers=headers)

        # Should return 400 Bad Request (or 409 Conflict)
        assert response.status_code in [400, 409]
        response_data = response.json()

        assert "detail" in response_data
        error_message = response_data["detail"].lower()

        # Error message should explain why deletion was prevented
        assert any(
            phrase in error_message
            for phrase in [
                "cannot delete last admin",
                "last admin user",
                "at least one admin",
                "system requires admin",
            ]
        ), f"Error message should explain admin protection, got: {response_data['detail']}"

        # Verify delete_user was NOT called
        mock_app_user_manager.delete_user.assert_not_called()

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_delete_admin_with_multiple_admins_succeeds(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting admin user succeeds when multiple admins exist."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin1",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin1",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_dep_user_manager.get_user.return_value = admin_user

        # Mock system with multiple admin users
        all_users = [
            User(
                username="admin1",
                password_hash="$2b$12$hash",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="admin2",
                password_hash="$2b$12$hash2",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="poweruser1",
                password_hash="$2b$12$hash3",
                role=UserRole.POWER_USER,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        # Mock the get_user call for the user being deleted (admin2)
        mock_app_user_manager.get_user.return_value = all_users[1]  # admin2 user
        mock_app_user_manager.get_all_users.return_value = all_users

        # Mock successful deletion
        mock_app_user_manager.delete_user.return_value = True

        headers = {"Authorization": "Bearer admin1.jwt.token"}
        response = client.delete("/api/admin/users/admin2", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "deleted successfully" in response_data["message"]

        # Verify delete_user was called
        mock_app_user_manager.delete_user.assert_called_once_with("admin2")

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_delete_non_admin_user_succeeds_regardless_of_admin_count(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test deleting non-admin users always succeeds, regardless of admin count."""
        # Setup authentication
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

        # Mock system with only one admin but multiple other users
        all_users = [
            User(
                username="admin",
                password_hash="$2b$12$hash",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="poweruser1",
                password_hash="$2b$12$hash2",
                role=UserRole.POWER_USER,
                created_at=datetime.now(timezone.utc),
            ),
            User(
                username="normaluser1",
                password_hash="$2b$12$hash3",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        # Mock the get_user call for the user being deleted (poweruser1)
        mock_app_user_manager.get_user.return_value = all_users[1]  # poweruser1
        mock_app_user_manager.get_all_users.return_value = all_users

        # Mock successful deletion of non-admin user
        mock_app_user_manager.delete_user.return_value = True

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.delete("/api/admin/users/poweruser1", headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "deleted successfully" in response_data["message"]

        # Verify delete_user was called for the power user
        mock_app_user_manager.delete_user.assert_called_once_with("poweruser1")


class TestChangePasswordEndpoints:
    """Test password change endpoints."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_current_user_change_password_returns_200(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test current user changing own password returns 200."""
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

        # Mock successful password change
        mock_app_user_manager.change_password.return_value = True

        headers = {"Authorization": "Bearer power.jwt.token"}
        response = client.put(
            "/api/users/change-password",
            headers=headers,
            json={"new_password": "NewSecurePass123!"},
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "changed successfully" in response_data["message"]

        mock_app_user_manager.change_password.assert_called_once_with(
            "poweruser", "NewSecurePass123!"
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_current_user_change_password_with_weak_password_returns_422(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test current user changing password with weak password returns 422."""
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
        response = client.put(
            "/api/users/change-password", headers=headers, json={"new_password": "weak"}
        )

        assert response.status_code == 422
        response_data = response.json()

        assert "detail" in response_data
        # Check that it's a validation error about password
        assert isinstance(response_data["detail"], list)
        assert len(response_data["detail"]) > 0
        assert "new_password" in response_data["detail"][0]["loc"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_admin_change_any_user_password_returns_200(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test admin changing any user's password returns 200."""
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

        # Mock successful password change
        mock_app_user_manager.change_password.return_value = True

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.put(
            "/api/admin/users/testuser/change-password",
            headers=headers,
            json={"new_password": "AdminSetPass456!"},
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "message" in response_data
        assert "changed successfully" in response_data["message"]

        mock_app_user_manager.change_password.assert_called_once_with(
            "testuser", "AdminSetPass456!"
        )

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    @patch("code_indexer.server.app.user_manager")
    def test_admin_change_nonexistent_user_password_returns_404(
        self, mock_app_user_manager, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test admin changing nonexistent user's password returns 404."""
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

        # Mock user doesn't exist
        mock_app_user_manager.change_password.return_value = False

        headers = {"Authorization": "Bearer admin.jwt.token"}
        response = client.put(
            "/api/admin/users/nonexistent/change-password",
            headers=headers,
            json={"new_password": "ValidPass123!"},
        )

        assert response.status_code == 404
        response_data = response.json()

        assert "detail" in response_data
        assert "User not found" in response_data["detail"]

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_non_admin_change_other_user_password_returns_403(
        self, mock_dep_user_manager, mock_jwt_manager, client
    ):
        """Test non-admin trying to change other user's password returns 403."""
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
        response = client.put(
            "/api/admin/users/otheruser/change-password",
            headers=headers,
            json={"new_password": "ValidPass123!"},
        )

        assert response.status_code == 403


class TestPasswordComplexityValidation:
    """Test password complexity validation functionality."""

    def test_validate_strong_password_returns_true(self):
        """Test that strong passwords pass validation."""
        # This test will fail until we implement password validation
        from code_indexer.server.auth.password_validator import (
            validate_password_complexity,
        )

        strong_passwords = [
            "SecurePass123!",
            "ComplexP@ssw0rd",
            "MyStr0ng!P@ssw0rd",
            "C0mpl3x!ty#2024",
        ]

        for password in strong_passwords:
            assert validate_password_complexity(
                password
            ), f"Password '{password}' should be valid"

    def test_validate_weak_password_returns_false(self):
        """Test that weak passwords fail validation."""
        from code_indexer.server.auth.password_validator import (
            validate_password_complexity,
        )

        weak_passwords = [
            "weak",  # Too short
            "password",  # No uppercase, digits, or special chars
            "123456",  # Too short, no letters or special chars
            "password123",  # No uppercase or special chars
            "Password",  # No digits or special chars
            "ALLUPPERCASE123",  # No lowercase or special chars
            "alllowercase123",  # No uppercase or special chars
            "NoNumbers!",  # No digits
            "NoSpecial123",  # No special chars
            "Short1!",  # Only 8 chars (we require > 8)
        ]

        for password in weak_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid"

    def test_get_password_requirements_returns_dict(self):
        """Test that password requirements are properly documented."""
        from code_indexer.server.auth.password_validator import (
            get_password_requirements,
        )

        requirements = get_password_requirements()

        assert isinstance(requirements, dict)
        assert "min_length" in requirements
        assert "require_uppercase" in requirements
        assert "require_lowercase" in requirements
        assert "require_digits" in requirements
        assert "require_special_chars" in requirements
        assert "description" in requirements
