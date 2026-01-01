"""Tests for OIDC provider implementation."""

import pytest


class TestOIDCMetadata:
    """Test OIDC metadata dataclass."""

    def test_oidc_metadata_creation(self):
        """Test that OIDCMetadata can be created with required fields."""
        from code_indexer.server.auth.oidc.oidc_provider import OIDCMetadata

        metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
        )

        assert metadata.issuer == "https://example.com"
        assert metadata.authorization_endpoint == "https://example.com/auth"
        assert metadata.token_endpoint == "https://example.com/token"


class TestOIDCUserInfo:
    """Test OIDC user info dataclass."""

    def test_oidc_user_info_creation_with_required_fields(self):
        """Test that OIDCUserInfo can be created with required subject field."""
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo

        user_info = OIDCUserInfo(subject="oidc-user-12345")

        assert user_info.subject == "oidc-user-12345"

    def test_oidc_user_info_with_optional_email_fields(self):
        """Test that OIDCUserInfo supports optional email and email_verified fields."""
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo

        user_info = OIDCUserInfo(
            subject="oidc-user-12345",
            email="user@example.com",
            email_verified=True,
        )

        assert user_info.subject == "oidc-user-12345"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True


class TestOIDCProvider:
    """Test OIDC provider class."""

    def test_oidc_provider_initialization(self):
        """Test that OIDCProvider can be initialized with config."""
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        provider = OIDCProvider(config)

        assert provider.config == config
        assert provider._metadata is None

    @pytest.mark.asyncio
    async def test_discover_metadata_fetches_from_well_known_endpoint(
        self, monkeypatch
    ):
        """Test that discover_metadata fetches OIDC metadata from well-known endpoint."""
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        provider = OIDCProvider(config)

        # Mock HTTP response
        mock_response = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
        }

        async def mock_get(*args, **kwargs):
            class MockResponse:
                def json(self):
                    return mock_response

                def raise_for_status(self):
                    pass  # No error for success case

            return MockResponse()

        # Mock httpx.AsyncClient
        import httpx

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                return await mock_get(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", lambda: MockAsyncClient())

        metadata = await provider.discover_metadata()

        assert metadata.issuer == "https://example.com"
        assert metadata.authorization_endpoint == "https://example.com/authorize"
        assert metadata.token_endpoint == "https://example.com/token"

    @pytest.mark.asyncio
    async def test_get_authorization_url_builds_url_with_pkce(self, monkeypatch):
        """Test that get_authorization_url builds correct authorization URL with PKCE."""
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCMetadata,
        )
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        provider = OIDCProvider(config)

        # Set metadata manually (skip discovery for this test)
        provider._metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
        )

        state = "test-state-token"
        redirect_uri = "https://app.example.com/callback"
        code_challenge = "test-code-challenge"

        auth_url = provider.get_authorization_url(state, redirect_uri, code_challenge)

        # Verify URL contains required OIDC parameters
        assert "https://example.com/authorize?" in auth_url
        assert "client_id=" in auth_url
        assert "response_type=code" in auth_url
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in auth_url
        assert "state=test-state-token" in auth_url
        assert "code_challenge=test-code-challenge" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert "scope=" in auth_url

    @pytest.mark.asyncio
    async def test_get_authorization_url_uses_default_scopes(self):
        """Test that get_authorization_url uses default scopes from config."""
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCMetadata,
        )
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        provider = OIDCProvider(config)
        provider._metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
        )

        auth_url = provider.get_authorization_url(
            "state", "https://callback", "challenge"
        )

        # Verify default scopes are used
        assert "scope=openid+profile+email" in auth_url

    @pytest.mark.asyncio
    async def test_get_authorization_url_uses_custom_scopes(self):
        """Test that get_authorization_url uses custom scopes from config."""
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCMetadata,
        )
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            scopes=["openid", "profile", "email", "groups"],
        )

        provider = OIDCProvider(config)
        provider._metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
        )

        auth_url = provider.get_authorization_url(
            "state", "https://callback", "challenge"
        )

        # Verify custom scopes are used
        assert "scope=openid+profile+email+groups" in auth_url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_returns_tokens(self, monkeypatch):
        """Test that exchange_code_for_token exchanges authorization code for tokens."""
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCMetadata,
        )
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        provider = OIDCProvider(config)

        # Set metadata manually
        provider._metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
        )

        # Mock HTTP response
        mock_token_response = {
            "access_token": "test-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": "test-id-token",
        }

        async def mock_post(*args, **kwargs):
            class MockResponse:
                def json(self):
                    return mock_token_response

                def raise_for_status(self):
                    pass  # No error for success case

            return MockResponse()

        # Mock httpx.AsyncClient
        import httpx

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, *args, **kwargs):
                return await mock_post(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", lambda: MockAsyncClient())

        code = "test-authorization-code"
        code_verifier = "test-code-verifier"
        redirect_uri = "https://app.example.com/callback"

        tokens = await provider.exchange_code_for_token(
            code, code_verifier, redirect_uri
        )

        assert tokens["access_token"] == "test-access-token"
        assert tokens["token_type"] == "Bearer"
        assert tokens["id_token"] == "test-id-token"

    @pytest.mark.asyncio
    async def test_get_user_info_extracts_user_info(self, monkeypatch):
        """Test that get_user_info extracts user information from access token."""
        from code_indexer.server.auth.oidc.oidc_provider import (
            OIDCProvider,
            OIDCMetadata,
        )
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        provider = OIDCProvider(config)

        # Set metadata manually
        provider._metadata = OIDCMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
        )

        # Mock userinfo response
        mock_userinfo = {
            "sub": "oidc-user-12345",
            "email": "user@example.com",
            "email_verified": True,
        }

        async def mock_get(*args, **kwargs):
            class MockResponse:
                def json(self):
                    return mock_userinfo

                def raise_for_status(self):
                    pass  # No error for success case

            return MockResponse()

        # Mock httpx.AsyncClient
        import httpx

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                return await mock_get(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", lambda: MockAsyncClient())

        access_token = "test-access-token"
        user_info = await provider.get_user_info(access_token)

        assert user_info.subject == "oidc-user-12345"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True
