"""Tests for OIDC routes implementation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestOIDCRoutes:
    """Test OIDC authentication routes."""

    def test_sso_login_endpoint_exists(self):
        """Test that /auth/sso/login endpoint is registered."""
        from code_indexer.server.auth.oidc.routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Attempt to access the endpoint (will fail because OIDC not configured, but endpoint should exist)
        response = client.get("/auth/sso/login")

        # Should not be 404 (not found), but 404 with specific message about SSO not configured
        assert response.status_code == 404
        assert "SSO not configured" in response.json()["detail"]

    def test_sso_login_redirects_to_authorization_url(self):
        """Test that /auth/sso/login redirects to OIDC provider when configured."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize?client_id=test"
        )

        # Create state manager
        state_mgr = StateManager()

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

        # Make request
        response = client.get("/auth/sso/login", follow_redirects=False)

        # Should redirect
        assert response.status_code == 302
        assert response.headers["location"].startswith("https://example.com/authorize")

    def test_sso_login_uses_state_manager(self):
        """Test that /auth/sso/login uses state_manager to create state token."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager with mocked create_state
        state_mgr = StateManager()
        state_mgr.create_state = Mock(return_value="test-state-token")

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

        # Make request
        client.get("/auth/sso/login", follow_redirects=False)

        # Verify state_manager.create_state was called
        state_mgr.create_state.assert_called_once()

        # Verify the state data contains code_verifier
        call_args = state_mgr.create_state.call_args[0][0]
        assert "code_verifier" in call_args
        assert isinstance(call_args["code_verifier"], str)
        assert len(call_args["code_verifier"]) > 0

    def test_sso_login_passes_state_to_authorization_url(self):
        """Test that /auth/sso/login passes the state token to get_authorization_url()."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager that returns a known token
        state_mgr = StateManager()
        state_mgr.create_state = Mock(return_value="known-state-token-123")

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

        # Make request
        client.get("/auth/sso/login", follow_redirects=False)

        # Verify get_authorization_url was called with the state token
        oidc_mgr.provider.get_authorization_url.assert_called_once()
        call_args = oidc_mgr.provider.get_authorization_url.call_args[0]

        # First argument should be the state token
        assert call_args[0] == "known-state-token-123"

    def test_sso_login_generates_pkce_challenge(self):
        """Test that /auth/sso/login generates and passes PKCE code_challenge."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock
        import hashlib
        import base64

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager
        state_mgr = StateManager()

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

        # Make request
        client.get("/auth/sso/login", follow_redirects=False)

        # Verify get_authorization_url was called
        oidc_mgr.provider.get_authorization_url.assert_called_once()
        call_args = oidc_mgr.provider.get_authorization_url.call_args[0]

        # Third argument should be the code_challenge
        code_challenge = call_args[2]

        # Verify code_challenge format (base64url encoded, no padding)
        assert isinstance(code_challenge, str)
        assert (
            len(code_challenge) == 43
        )  # SHA256 base64url encoded without padding is 43 chars
        assert "=" not in code_challenge  # No padding

        # Verify code_verifier was stored in state with matching challenge
        state_token = call_args[0]
        state_data = state_mgr.validate_state(state_token)
        assert state_data is not None
        assert "code_verifier" in state_data

        # Verify challenge matches verifier (S256 method)
        code_verifier = state_data["code_verifier"]
        expected_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        assert code_challenge == expected_challenge

    def test_sso_login_uses_callback_url(self):
        """Test that /auth/sso/login uses proper callback URL."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager
        state_mgr = StateManager()

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

        # Make request
        client.get("/auth/sso/login", follow_redirects=False)

        # Verify get_authorization_url was called
        oidc_mgr.provider.get_authorization_url.assert_called_once()
        call_args = oidc_mgr.provider.get_authorization_url.call_args[0]

        # Second argument should be the callback URL
        callback_url = call_args[1]

        # Verify callback URL points to sso_callback endpoint
        assert isinstance(callback_url, str)
        assert callback_url.endswith("/auth/sso/callback")

    def test_sso_login_stores_redirect_uri_in_state(self):
        """Test that /auth/sso/login stores redirect_uri in state for post-auth redirect."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager
        state_mgr = StateManager()

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

        # Make request with custom redirect_uri
        client.get("/auth/sso/login?redirect_uri=/custom/path", follow_redirects=False)

        # Get the state token from the call
        call_args = oidc_mgr.provider.get_authorization_url.call_args[0]
        state_token = call_args[0]

        # Validate state and check redirect_uri
        state_data = state_mgr.validate_state(state_token)
        assert state_data is not None
        assert "redirect_uri" in state_data
        assert state_data["redirect_uri"] == "/custom/path"

    def test_sso_login_uses_default_redirect_uri(self):
        """Test that /auth/sso/login uses /admin as default redirect_uri."""
        from code_indexer.server.auth.oidc.routes import router
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.auth.oidc.state_manager import StateManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        # Create configured OIDC manager
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
        )
        oidc_mgr = OIDCManager(config, None, None)
        oidc_mgr.provider = Mock(spec=OIDCProvider)
        oidc_mgr.provider.get_authorization_url = Mock(
            return_value="https://example.com/authorize"
        )

        # Create state manager
        state_mgr = StateManager()

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

        # Make request without redirect_uri
        client.get("/auth/sso/login", follow_redirects=False)

        # Get the state token from the call
        call_args = oidc_mgr.provider.get_authorization_url.call_args[0]
        state_token = call_args[0]

        # Validate state and check default redirect_uri
        state_data = state_mgr.validate_state(state_token)
        assert state_data is not None
        assert "redirect_uri" in state_data
        assert state_data["redirect_uri"] == "/admin"

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
            provider_name="TestSSO",
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
            provider_name="TestSSO",
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
