"""
Test login request input validation.

These tests verify that login endpoint properly validates username and password
inputs before attempting authentication.
"""

from fastapi.testclient import TestClient
from fastapi import status

from src.code_indexer.server.app import create_app


class TestLoginValidation:
    """Test login request input validation."""

    def setup_method(self):
        """Setup test client for each test."""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_login_with_empty_username(self):
        """Test login request with empty username is rejected."""
        response = self.client.post(
            "/auth/login", json={"username": "", "password": "admin"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()
        assert "detail" in error_data

        # Check that the error mentions username validation
        errors = error_data["detail"]
        username_error = next(
            (e for e in errors if "username" in e.get("loc", [])), None
        )
        assert username_error is not None

    def test_login_with_whitespace_only_username(self):
        """Test login request with whitespace-only username is rejected."""
        response = self.client.post(
            "/auth/login", json={"username": "   ", "password": "admin"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check validation error details
        errors = error_data["detail"]
        username_error = next(
            (e for e in errors if "username" in e.get("loc", [])), None
        )
        assert username_error is not None

    def test_login_with_empty_password(self):
        """Test login request with empty password is rejected."""
        response = self.client.post(
            "/auth/login", json={"username": "admin", "password": ""}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check that the error mentions password validation
        errors = error_data["detail"]
        password_error = next(
            (e for e in errors if "password" in e.get("loc", [])), None
        )
        assert password_error is not None

    def test_login_with_whitespace_only_password(self):
        """Test login request with whitespace-only password is rejected."""
        response = self.client.post(
            "/auth/login", json={"username": "admin", "password": "   "}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check validation error details
        errors = error_data["detail"]
        password_error = next(
            (e for e in errors if "password" in e.get("loc", [])), None
        )
        assert password_error is not None

    def test_login_with_missing_username(self):
        """Test login request with missing username field is rejected."""
        response = self.client.post("/auth/login", json={"password": "admin"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check that the error mentions missing username
        errors = error_data["detail"]
        username_error = next(
            (e for e in errors if "username" in e.get("loc", [])), None
        )
        assert username_error is not None

    def test_login_with_missing_password(self):
        """Test login request with missing password field is rejected."""
        response = self.client.post("/auth/login", json={"username": "admin"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check that the error mentions missing password
        errors = error_data["detail"]
        password_error = next(
            (e for e in errors if "password" in e.get("loc", [])), None
        )
        assert password_error is not None

    def test_login_with_null_values(self):
        """Test login request with null values is rejected."""
        response = self.client.post(
            "/auth/login", json={"username": None, "password": None}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Should have validation errors for both fields
        errors = error_data["detail"]
        assert len(errors) >= 2

    def test_login_with_extremely_long_username(self):
        """Test login request with extremely long username is rejected."""
        long_username = "a" * 256  # 256 characters
        response = self.client.post(
            "/auth/login", json={"username": long_username, "password": "admin"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check validation error for username length
        errors = error_data["detail"]
        username_error = next(
            (e for e in errors if "username" in e.get("loc", [])), None
        )
        assert username_error is not None

    def test_login_with_extremely_long_password(self):
        """Test login request with extremely long password is rejected."""
        long_password = "a" * 1001  # 1001 characters
        response = self.client.post(
            "/auth/login", json={"username": "admin", "password": long_password}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Check validation error for password length
        errors = error_data["detail"]
        password_error = next(
            (e for e in errors if "password" in e.get("loc", [])), None
        )
        assert password_error is not None

    def test_login_with_valid_credentials_passes_validation(self):
        """Test login with valid credentials passes validation (even if auth fails)."""
        response = self.client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "admin",  # This is the default admin password
            },
        )
        # Should pass validation and return either success or 401 (not 422)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
        ]
        assert response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_validation_error_structure(self):
        """Test that validation errors follow proper FastAPI structure."""
        response = self.client.post(
            "/auth/login", json={"username": "", "password": ""}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()

        # Verify FastAPI validation error structure
        assert "detail" in error_data
        assert isinstance(error_data["detail"], list)

        for error in error_data["detail"]:
            assert "loc" in error
            assert "msg" in error
            assert "type" in error
            assert isinstance(error["loc"], list)
