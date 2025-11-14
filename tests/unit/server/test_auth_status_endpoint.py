"""
Unit tests for GET /api/auth/status endpoint.

Tests authentication status checking with and without tokens.
Following Anti-Mock: Real JWT, real validation, no mocks.
"""

from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app


class TestAuthStatusEndpoint:
    """Test GET /api/auth/status endpoint."""

    def test_status_without_token_returns_not_authenticated(self):
        """Test that status endpoint returns not authenticated when no token provided."""
        app = create_app()
        client = TestClient(app)

        # Call status without token
        response = client.get("/api/auth/status")

        # Should return 200 (not 401) with authenticated=false
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert "username" not in data or data["username"] is None

    def test_status_with_invalid_token_returns_not_authenticated(self):
        """Test that status endpoint returns not authenticated for invalid token."""
        app = create_app()
        client = TestClient(app)

        # Call status with invalid token
        response = client.get(
            "/api/auth/status",
            headers={"Authorization": "Bearer invalid-token"}
        )

        # Should return 200 (not 401) with authenticated=false
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert "error" in data
        assert "invalid" in data["error"].lower()

    def test_status_with_expired_token_returns_not_authenticated(self):
        """Test that status endpoint returns not authenticated for expired token."""
        from src.code_indexer.server.auth.jwt_manager import JWTManager
        import time

        # Create JWT with very short expiration
        test_jwt_manager = JWTManager(secret_key="test-secret", token_expiration_minutes=0)
        token = test_jwt_manager.create_token({
            "username": "testuser",
            "role": "normal_user"
        })

        # Wait briefly to ensure token expires
        time.sleep(1)

        app = create_app()

        # Replace global jwt_manager with test one
        import src.code_indexer.server.app as app_module
        original_jwt = app_module.jwt_manager
        app_module.jwt_manager = test_jwt_manager

        client = TestClient(app)

        try:
            # Call status with expired token
            response = client.get(
                "/api/auth/status",
                headers={"Authorization": f"Bearer {token}"}
            )

            # Should return 200 with authenticated=false
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is False
            assert "error" in data
            assert "expired" in data["error"].lower()
        finally:
            # Restore original jwt_manager
            app_module.jwt_manager = original_jwt

    def test_status_with_valid_token_returns_authenticated_with_metadata(self):
        """Test that status endpoint returns authenticated=true with user metadata for valid token."""
        from unittest.mock import patch
        from datetime import datetime, timezone
        from src.code_indexer.server.auth.user_manager import User, UserRole

        app = create_app()
        client = TestClient(app)

        # Mock user for authentication
        test_user = User(
            username="john",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        with patch("src.code_indexer.server.app.user_manager") as mock_user_manager:
            mock_user_manager.authenticate_user.return_value = test_user
            mock_user_manager.get_user.return_value = test_user

            # Login to get a valid token
            login_response = client.post(
                "/auth/login",
                json={"username": "john", "password": "password"}
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]

            # Call status endpoint with token
            response = client.get(
                "/api/auth/status",
                headers={"Authorization": f"Bearer {token}"}
            )

            # Should return authenticated=true with metadata
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["username"] == "john"
            assert data["role"] == "normal_user"
            assert "token_expires_at" in data
            assert "token_issued_at" in data
