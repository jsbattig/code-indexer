"""
Unit tests for authentication lifecycle management.

Tests token blacklist, logout, status checking, validation, and user updates.
"""

import pytest
import uuid
from unittest.mock import MagicMock

from src.code_indexer.server.auth.jwt_manager import JWTManager


class TestTokenBlacklist:
    """Test token blacklist functionality."""

    def test_blacklist_token_adds_jti(self):
        """Test that blacklist_token adds JTI to blacklist."""
        from src.code_indexer.server.app import blacklist_token, token_blacklist

        # Clear blacklist
        token_blacklist.clear()

        # Add a token JTI
        test_jti = str(uuid.uuid4())
        blacklist_token(test_jti)

        # Verify it's in the blacklist
        assert test_jti in token_blacklist

    def test_is_token_blacklisted_returns_true_for_blacklisted(self):
        """Test that is_token_blacklisted returns True for blacklisted tokens."""
        from src.code_indexer.server.app import (
            blacklist_token,
            is_token_blacklisted,
            token_blacklist,
        )

        # Clear blacklist
        token_blacklist.clear()

        # Add a token JTI
        test_jti = str(uuid.uuid4())
        blacklist_token(test_jti)

        # Verify check returns True
        assert is_token_blacklisted(test_jti) is True


class TestJWTWithJTI:
    """Test JWT tokens include JTI claim for blacklist support."""

    def test_jwt_token_includes_jti_claim(self):
        """Test that JWT tokens created by JWTManager include JTI claim."""
        # Create JWT manager
        jwt_manager = JWTManager(secret_key="test-secret", token_expiration_minutes=10)

        # Create token with user data
        user_data = {
            "username": "testuser",
            "role": "standard",
            "created_at": "2024-01-01T00:00:00Z",
        }

        token = jwt_manager.create_token(user_data)

        # Validate and get payload
        payload = jwt_manager.validate_token(token)

        # Verify JTI exists and is a valid UUID
        assert "jti" in payload
        assert payload["jti"] is not None
        # Verify it's a valid UUID format
        uuid.UUID(payload["jti"])  # This will raise if not valid UUID

    def test_get_current_user_checks_blacklist(self):
        """Test that get_current_user rejects blacklisted tokens."""
        from src.code_indexer.server.auth.dependencies import get_current_user
        from src.code_indexer.server.auth.user_manager import User, UserRole
        from src.code_indexer.server.app import blacklist_token, token_blacklist
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        # Clear blacklist
        token_blacklist.clear()

        # Create test managers
        test_jwt_manager = JWTManager(secret_key="test-secret")
        test_user_manager = MagicMock()
        test_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            created_at="2024-01-01T00:00:00Z",
            email="test@example.com",
            password_hash="fakehash",
        )
        test_user_manager.get_user.return_value = test_user

        # Set global managers
        import src.code_indexer.server.auth.dependencies as deps

        deps.jwt_manager = test_jwt_manager
        deps.user_manager = test_user_manager

        # Create token
        token = test_jwt_manager.create_token(
            {"username": "testuser", "role": "normal_user"}
        )

        # Verify token works initially
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = get_current_user(credentials)
        assert user.username == "testuser"

        # Get JTI and blacklist it
        payload = test_jwt_manager.validate_token(token)
        jti = payload["jti"]
        blacklist_token(jti)

        # Now token should be rejected
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials)

        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()


class TestLogoutEndpoint:
    """Test POST /api/auth/logout endpoint."""

    def test_logout_endpoint_exists(self):
        """Test that logout endpoint is defined."""
        from fastapi.testclient import TestClient
        from src.code_indexer.server.app import create_app

        app = create_app()
        client = TestClient(app)

        # Try to access the endpoint (will fail auth but confirms endpoint exists)
        response = client.post("/api/auth/logout")

        # Should be 403 (no bearer token) not 404
        assert response.status_code in [401, 403]  # Not 404

    def test_logout_returns_success_message(self):
        """Test that logout endpoint returns success message."""
        from fastapi.testclient import TestClient
        from src.code_indexer.server.app import create_app
        from src.code_indexer.server.auth.user_manager import User, UserRole

        # Mock the get_current_user dependency to bypass auth
        mock_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            created_at="2024-01-01T00:00:00Z",
            email="test@example.com",
            password_hash="fakehash",
        )

        app = create_app()

        # Override the dependency
        from src.code_indexer.server.auth.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)

        # Call logout (auth bypassed)
        response = client.post("/api/auth/logout")

        # Should return 200
        assert response.status_code == 200
        assert "logged out" in response.json()["message"].lower()

    def test_logout_blacklists_jti(self):
        """Test that logout actually blacklists the token JTI."""
        from fastapi.testclient import TestClient
        from fastapi import Request
        from src.code_indexer.server.app import create_app, token_blacklist
        from src.code_indexer.server.auth.user_manager import User, UserRole

        # Clear blacklist
        token_blacklist.clear()

        # Create a mock user
        mock_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            created_at="2024-01-01T00:00:00Z",
            email="test@example.com",
            password_hash="fakehash",
        )

        # Create JWT manager and token with JTI
        test_jwt_manager = JWTManager(secret_key="test-secret")
        token = test_jwt_manager.create_token(
            {"username": "testuser", "role": "normal_user"}
        )

        # Get JTI from token
        payload = test_jwt_manager.validate_token(token)
        jti = payload["jti"]

        # Create app first, THEN set the global jwt_manager
        app = create_app()

        import src.code_indexer.server.app as app_module

        original_jwt = app_module.jwt_manager
        app_module.jwt_manager = test_jwt_manager

        # Create a custom dependency that extracts the token
        def mock_get_current_user_with_token(request: Request):
            # Store the token for the logout endpoint to use
            request.state.token = token
            return mock_user

        app.dependency_overrides[
            __import__(
                "src.code_indexer.server.auth.dependencies",
                fromlist=["get_current_user"],
            ).get_current_user
        ] = mock_get_current_user_with_token

        client = TestClient(app)

        # Call logout with the token
        response = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )

        # Should return 200
        assert response.status_code == 200

        # JTI should be blacklisted now
        assert jti in token_blacklist

        # Restore original jwt_manager
        app_module.jwt_manager = original_jwt

    def test_logout_uses_auth_header_token(self):
        """Test that logout uses the actual Authorization header token."""
        from fastapi.testclient import TestClient
        from src.code_indexer.server.app import create_app, token_blacklist
        from src.code_indexer.server.auth.user_manager import User, UserRole

        # Clear blacklist
        token_blacklist.clear()

        # Create JWT manager and token with JTI
        test_jwt_manager = JWTManager(secret_key="test-secret")
        token = test_jwt_manager.create_token(
            {"username": "testuser", "role": "normal_user"}
        )

        # Get JTI from token
        payload = test_jwt_manager.validate_token(token)
        jti = payload["jti"]

        # Create app first
        app = create_app()

        # Set the global jwt_manager
        import src.code_indexer.server.app as app_module

        original_jwt = app_module.jwt_manager
        app_module.jwt_manager = test_jwt_manager

        # Create a mock user
        mock_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            created_at="2024-01-01T00:00:00Z",
            email="test@example.com",
            password_hash="fakehash",
        )

        # Override get_current_user to return mock user but NOT set request.state.token
        def mock_get_current_user():
            # Don't set request.state.token, so it must use the actual header
            return mock_user

        app.dependency_overrides[
            __import__(
                "src.code_indexer.server.auth.dependencies",
                fromlist=["get_current_user"],
            ).get_current_user
        ] = mock_get_current_user

        client = TestClient(app)

        # Call logout with the token
        response = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )

        # Should return 200
        assert response.status_code == 200

        # JTI should be blacklisted from the actual header
        assert jti in token_blacklist

        # Restore
        app_module.jwt_manager = original_jwt
