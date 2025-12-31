"""Tests for OIDC configuration in ServerConfig."""

from code_indexer.server.utils.config_manager import (
    OIDCProviderConfig,
    ServerConfig,
)


class TestOIDCProviderConfig:
    """Test OIDC provider configuration."""

    def test_oidc_config_default_values(self):
        """Test that OIDCProviderConfig has correct default values."""
        config = OIDCProviderConfig()

        assert config.enabled is False
        assert config.provider_name == "SSO"
        assert config.issuer_url == ""

    def test_server_config_includes_oidc_provider_config(self):
        """Test that ServerConfig includes oidc_provider_config field."""
        config = ServerConfig(server_dir="/tmp/test")

        assert hasattr(config, "oidc_provider_config")
        assert config.oidc_provider_config is not None
        assert isinstance(config.oidc_provider_config, OIDCProviderConfig)

    def test_oidc_config_email_verification_settings(self):
        """Test email verification configuration options."""
        config = OIDCProviderConfig()

        # Default should require email verification (secure default)
        assert config.require_email_verification is True
        assert config.email_claim == "email"

    def test_oidc_config_jit_provisioning_settings(self):
        """Test JIT provisioning configuration."""
        config = OIDCProviderConfig()

        assert config.enable_jit_provisioning is True
        assert config.default_role == "normal_user"

    def test_oidc_config_client_credentials(self):
        """Test that OIDCProviderConfig supports OAuth client credentials."""
        config = OIDCProviderConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        assert config.client_id == "test-client-id"
        assert config.client_secret == "test-client-secret"
