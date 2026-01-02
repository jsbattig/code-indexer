"""Tests for OIDC routes implementation."""

import os
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestOIDCRoutes:
    """Test OIDC authentication routes."""

    def test_sso_callback_endpoint_exists(self):
        """Test that /auth/sso/callback endpoint is registered."""
        from code_indexer.server.auth.oidc.routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Attempt to access the endpoint without parameters (should fail with validation error, not 404)
        response = client.get("/auth/sso/callback")

        # Should not be 404 (not found) - endpoint exists but requires parameters
        assert response.status_code == 422  # Validation error (missing required params)

    def test_sso_callback_rejects_invalid_state(self):
        """Test that /auth/sso/callback returns 400 for invalid state token."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.state_manager import StateManager

        # Create state manager
        state_mgr = StateManager()

        # Inject state manager into routes module
        import code_indexer.server.auth.oidc.routes as routes_module

        routes_module.state_manager = state_mgr

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Make request with invalid state token
        response = client.get(
            "/auth/sso/callback?code=test-code&state=invalid-state-token"
        )

        # Should return 400 Bad Request
        assert response.status_code == 400
        assert "Invalid state" in response.json()["detail"]

    def test_sso_callback_successful_flow(self):
        """Test complete successful OIDC callback flow."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCUserInfo,
        )
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from code_indexer.server.auth.user_manager import User, UserRole
        from unittest.mock import Mock, AsyncMock
        from datetime import datetime, timezone

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)

        # Mock provider methods
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.exchange_code_for_token = AsyncMock(
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
            }
        )
        oidc_mgr.provider.get_user_info = AsyncMock(
            return_value=OIDCUserInfo(
                subject="test-subject-123",
                email="test@example.com",
                email_verified=True,
            )
        )

        # Mock OIDCManager methods
        test_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            password_hash="",
            created_at=datetime.now(timezone.utc),
            email="test@example.com",
        )
        oidc_mgr.match_or_create_user = AsyncMock(return_value=test_user)
        oidc_mgr.create_jwt_session = Mock(return_value="test-jwt-token")

        # Create state manager with valid state
        state_mgr = StateManager()
        state_token = state_mgr.create_state(
            {"code_verifier": "test-code-verifier", "redirect_uri": None}
        )

        # Inject managers into routes module
        import code_indexer.server.auth.oidc.routes as routes_module
        from code_indexer.server.utils.config_manager import ServerConfig

        routes_module.oidc_manager = oidc_mgr
        routes_module.state_manager = state_mgr
        routes_module.server_config = ServerConfig(
            server_dir="/tmp", host="localhost", port=8090
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Make callback request
        response = client.get(
            f"/auth/sso/callback?code=test-auth-code&state={state_token}",
            follow_redirects=False,
        )

        # Verify redirect - Phase 5: Smart redirect based on user role
        # Normal users go to /user/api-keys, admins go to /admin/
        assert response.status_code == 302
        assert response.headers["location"] == "/user/api-keys"

        # Verify session cookie is set (same as password login)
        assert "session" in response.cookies

        # Verify provider methods were called
        oidc_mgr.provider.exchange_code_for_token.assert_called_once()
        oidc_mgr.provider.get_user_info.assert_called_once_with("test-access-token")
        oidc_mgr.match_or_create_user.assert_called_once()

    def test_sso_callback_handles_match_or_create_user_returning_none(self):
        """Test that sso_callback handles case where match_or_create_user returns None (JIT disabled, no match)."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCUserInfo,
        )
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock, AsyncMock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)

        # Mock provider methods
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.exchange_code_for_token = AsyncMock(
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
            }
        )
        oidc_mgr.provider.get_user_info = AsyncMock(
            return_value=OIDCUserInfo(
                subject="test-subject-123",
                email="test@example.com",
                email_verified=True,
            )
        )

        # Mock match_or_create_user to return None (JIT disabled, no matching user)
        oidc_mgr.match_or_create_user = AsyncMock(return_value=None)

        # Create state manager with valid state
        state_mgr = StateManager()
        state_token = state_mgr.create_state(
            {"code_verifier": "test-code-verifier", "redirect_uri": "/admin"}
        )

        # Inject managers into routes module
        import code_indexer.server.auth.oidc.routes as routes_module
        from code_indexer.server.utils.config_manager import ServerConfig

        routes_module.oidc_manager = oidc_mgr
        routes_module.state_manager = state_mgr
        routes_module.server_config = ServerConfig(
            server_dir="/tmp", host="localhost", port=8090
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Make callback request
        response = client.get(
            f"/auth/sso/callback?code=test-auth-code&state={state_token}",
            follow_redirects=False,
        )

        # Should return 403 Forbidden (authentication succeeded but authorization failed)
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()


    def test_sso_callback_uses_cidx_issuer_url_when_set(self):
        """Test that /auth/sso/callback uses CIDX_ISSUER_URL for token exchange when set."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCUserInfo,
        )
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from code_indexer.server.auth.user_manager import User, UserRole
        from unittest.mock import Mock, AsyncMock
        from datetime import datetime, timezone

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)

        # Mock provider methods
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.exchange_code_for_token = AsyncMock(
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
            }
        )
        oidc_mgr.provider.get_user_info = AsyncMock(
            return_value=OIDCUserInfo(
                subject="test-subject-123",
                email="test@example.com",
                email_verified=True,
            )
        )

        # Mock OIDCManager methods
        test_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            password_hash="",
            created_at=datetime.now(timezone.utc),
            email="test@example.com",
        )
        oidc_mgr.match_or_create_user = AsyncMock(return_value=test_user)
        oidc_mgr.create_jwt_session = Mock(return_value="test-jwt-token")

        # Create state manager with valid state
        state_mgr = StateManager()
        state_token = state_mgr.create_state(
            {"code_verifier": "test-code-verifier", "redirect_uri": None}
        )

        # Inject managers into routes module
        import code_indexer.server.auth.oidc.routes as routes_module
        from code_indexer.server.utils.config_manager import ServerConfig

        routes_module.oidc_manager = oidc_mgr
        routes_module.state_manager = state_mgr
        routes_module.server_config = ServerConfig(
            server_dir="/tmp", host="localhost", port=8090
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Set CIDX_ISSUER_URL environment variable
        with patch.dict(
            os.environ, {"CIDX_ISSUER_URL": "https://linner.ddns.net:8383"}
        ):
            # Make callback request
            response = client.get(
                f"/auth/sso/callback?code=test-auth-code&state={state_token}",
                follow_redirects=False,
            )

            # Verify redirect succeeds
            assert response.status_code == 302

            # Verify exchange_code_for_token was called with CIDX_ISSUER_URL-based callback
            oidc_mgr.provider.exchange_code_for_token.assert_called_once()
            call_args = oidc_mgr.provider.exchange_code_for_token.call_args

            # Third argument should be the callback URL using CIDX_ISSUER_URL
            callback_url = call_args[0][2]  # positional arg 2
            assert callback_url == "https://linner.ddns.net:8383/auth/sso/callback"

    def test_sso_callback_uses_request_url_when_cidx_issuer_url_not_set(self):
        """Test that /auth/sso/callback falls back to request.url_for() when CIDX_ISSUER_URL not set."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCUserInfo,
        )
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from code_indexer.server.auth.user_manager import User, UserRole
        from unittest.mock import Mock, AsyncMock
        from datetime import datetime, timezone

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)

        # Mock provider methods
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.exchange_code_for_token = AsyncMock(
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
            }
        )
        oidc_mgr.provider.get_user_info = AsyncMock(
            return_value=OIDCUserInfo(
                subject="test-subject-123",
                email="test@example.com",
                email_verified=True,
            )
        )

        # Mock OIDCManager methods
        test_user = User(
            username="testuser",
            role=UserRole.NORMAL_USER,
            password_hash="",
            created_at=datetime.now(timezone.utc),
            email="test@example.com",
        )
        oidc_mgr.match_or_create_user = AsyncMock(return_value=test_user)
        oidc_mgr.create_jwt_session = Mock(return_value="test-jwt-token")

        # Create state manager with valid state
        state_mgr = StateManager()
        state_token = state_mgr.create_state(
            {"code_verifier": "test-code-verifier", "redirect_uri": None}
        )

        # Inject managers into routes module
        import code_indexer.server.auth.oidc.routes as routes_module
        from code_indexer.server.utils.config_manager import ServerConfig

        routes_module.oidc_manager = oidc_mgr
        routes_module.state_manager = state_mgr
        routes_module.server_config = ServerConfig(
            server_dir="/tmp", host="localhost", port=8090
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Ensure CIDX_ISSUER_URL is not set
        with patch.dict(os.environ, {}, clear=False):
            if "CIDX_ISSUER_URL" in os.environ:
                del os.environ["CIDX_ISSUER_URL"]

            # Make callback request
            response = client.get(
                f"/auth/sso/callback?code=test-auth-code&state={state_token}",
                follow_redirects=False,
            )

            # Verify redirect succeeds
            assert response.status_code == 302

            # Verify exchange_code_for_token was called with request-based callback
            oidc_mgr.provider.exchange_code_for_token.assert_called_once()
            call_args = oidc_mgr.provider.exchange_code_for_token.call_args

            # Third argument should be the callback URL from request.url_for()
            callback_url = call_args[0][2]  # positional arg 2
            assert callback_url.endswith("/auth/sso/callback")
            # Should be http://testserver (TestClient default)
            assert callback_url.startswith("http://testserver")
