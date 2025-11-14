"""
Integration tests for authentication lifecycle management.

Tests the complete flow of authentication, logout, status, validation, and updates.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.code_indexer.server.app import create_app, token_blacklist
from src.code_indexer.server.auth.jwt_manager import JWTManager
from src.code_indexer.server.auth.user_manager import User, UserRole


class TestAuthLifecycleIntegration:
    """Integration tests for complete authentication lifecycle."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test."""
        # Clear blacklist before each test
        token_blacklist.clear()
        yield
        # Clear blacklist after each test
        token_blacklist.clear()

    def test_token_blacklist_prevents_reuse_after_logout(self):
        """Test that blacklisted token cannot be used after logout."""
        from src.code_indexer.server.auth.dependencies import get_current_user
        import src.code_indexer.server.app as app_module
        import src.code_indexer.server.auth.dependencies as deps

        # Create test JWT manager
        test_jwt_manager = JWTManager(secret_key="test-secret")

        # Create a token
        token = test_jwt_manager.create_token({
            "username": "testuser",
            "role": "normal_user"
        })

        # Extract JTI
        payload = test_jwt_manager.validate_token(token)
        jti = payload["jti"]

        # Create app and set managers
        app = create_app()

        # Override managers
        original_jwt = app_module.jwt_manager
        original_deps_jwt = deps.jwt_manager

        try:
            app_module.jwt_manager = test_jwt_manager
            deps.jwt_manager = test_jwt_manager

            # Create mock user manager
            mock_user_manager = MagicMock()
            mock_user = User(
                username="testuser",
                role=UserRole.NORMAL_USER,
                created_at="2024-01-01T00:00:00Z",
                email="test@example.com",
                password_hash="fakehash"
            )
            mock_user_manager.get_user.return_value = mock_user

            original_user = app_module.user_manager
            original_deps_user = deps.user_manager
            app_module.user_manager = mock_user_manager
            deps.user_manager = mock_user_manager

            # Override get_current_user dependency
            app.dependency_overrides[get_current_user] = lambda: mock_user

            client = TestClient(app)

            # First, verify token works
            response = client.get(
                "/api/repos",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200  # Token works

            # Now logout
            response = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            assert jti in token_blacklist

            # Remove the override so it uses real auth with blacklist check
            app.dependency_overrides.clear()

            # Try to use the token again - should fail due to blacklist
            response = client.get(
                "/api/repos",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401  # Token rejected

        finally:
            # Restore managers
            app_module.jwt_manager = original_jwt
            app_module.user_manager = original_user
            deps.jwt_manager = original_deps_jwt
            deps.user_manager = original_deps_user