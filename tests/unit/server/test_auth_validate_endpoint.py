"""
Unit tests for POST /api/auth/validate endpoint.

Tests token validation with and without side effects.
Following Anti-Mock: Real JWT, real validation, minimal mocking.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import User, UserRole


class TestAuthValidateEndpoint:
    """Test POST /api/auth/validate endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager for login."""
        with patch("src.code_indexer.server.app.user_manager") as mock:
            yield mock

    def test_validate_with_valid_token_returns_success(self, client, mock_user_manager):
        """Test that validate endpoint returns success for valid token."""
        # Mock login
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user
        mock_user_manager.get_user.return_value = admin_user

        # Login to get a valid token
        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Call validate with valid token
        response = client.post(
            "/api/auth/validate", headers={"Authorization": f"Bearer {token}"}
        )

        # Should return 200 with valid=true
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["username"] == "admin"

    def test_validate_with_expired_token_returns_unauthorized(self, client):
        """Test that validate endpoint returns 401 for expired token."""
        from src.code_indexer.server.auth.jwt_manager import JWTManager
        import src.code_indexer.server.auth.dependencies as deps
        import time

        # Create JWT with very short expiration
        test_jwt_manager = JWTManager(
            secret_key="test-secret", token_expiration_minutes=0
        )
        token = test_jwt_manager.create_token(
            {"username": "testuser", "role": "normal_user"}
        )

        # Wait briefly to ensure token expires
        time.sleep(1)

        # Override JWT manager temporarily
        original_jwt = deps.jwt_manager
        try:
            deps.jwt_manager = test_jwt_manager

            # Call validate with expired token
            response = client.post(
                "/api/auth/validate", headers={"Authorization": f"Bearer {token}"}
            )

            # Should return 401 with error message
            assert response.status_code == 401
            data = response.json()
            assert "expired" in data["detail"].lower()
        finally:
            # Restore original JWT manager
            deps.jwt_manager = original_jwt

    def test_validate_with_revoked_token_returns_unauthorized(
        self, client, mock_user_manager
    ):
        """Test that validate endpoint returns 401 for revoked token."""
        from src.code_indexer.server.app import blacklist_token, token_blacklist

        # Clear blacklist
        token_blacklist.clear()

        # Mock login to get a user
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user
        mock_user_manager.get_user.return_value = admin_user

        # Login to get a valid token
        login_response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Extract JTI and blacklist it
        import src.code_indexer.server.auth.dependencies as deps

        original_jwt = deps.jwt_manager
        payload = original_jwt.validate_token(token)
        jti = payload["jti"]
        blacklist_token(jti)

        # Call validate with revoked token
        response = client.post(
            "/api/auth/validate", headers={"Authorization": f"Bearer {token}"}
        )

        # Should return 401 with revoked message
        assert response.status_code == 401
        data = response.json()
        assert "revoked" in data["detail"].lower()

    def test_validate_with_invalid_token_returns_unauthorized(self, client):
        """Test that validate endpoint returns 401 for invalid token."""
        # Call validate with invalid token
        response = client.post(
            "/api/auth/validate", headers={"Authorization": "Bearer invalid-token-here"}
        )

        # Should return 401
        assert response.status_code == 401

    def test_validate_without_token_returns_forbidden(self, client):
        """Test that validate endpoint returns 403 when no token provided."""
        # Call validate without token
        response = client.post("/api/auth/validate")

        # Should return 403 (not authenticated)
        assert response.status_code == 403
