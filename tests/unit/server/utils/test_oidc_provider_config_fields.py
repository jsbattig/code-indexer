"""Tests for OIDCProviderConfig fields and deserialization."""

import json
import tempfile
from pathlib import Path


from code_indexer.server.utils.config_manager import (
    OIDCProviderConfig,
    ServerConfigManager,
)


class TestOIDCProviderConfigFields:
    """Test OIDCProviderConfig has all required fields."""

    def test_oidc_provider_config_has_scopes_field(self):
        """Test that OIDCProviderConfig has scopes field."""
        config = OIDCProviderConfig()
        assert hasattr(config, "scopes")
        assert config.scopes == ["openid", "profile", "email"]

    def test_oidc_provider_config_has_username_claim_field(self):
        """Test that OIDCProviderConfig has username_claim field."""
        config = OIDCProviderConfig()
        assert hasattr(config, "username_claim")
        assert config.username_claim == "preferred_username"

    def test_oidc_provider_config_has_use_pkce_field(self):
        """Test that OIDCProviderConfig has use_pkce field."""
        config = OIDCProviderConfig()
        assert hasattr(config, "use_pkce")
        assert config.use_pkce is True


class TestOIDCProviderConfigDeserialization:
    """Test OIDCProviderConfig deserialization from config file."""

    def test_server_config_deserializes_oidc_provider_config_from_dict(self):
        """Test that ServerConfigManager deserializes oidc_provider_config from dict to object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_data = {
                "server_dir": tmpdir,
                "host": "127.0.0.1",
                "port": 8090,
                "oidc_provider_config": {
                    "enabled": True,
                    "issuer_url": "http://localhost:8180/realms/test",
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                    "scopes": ["openid", "profile", "email"],
                    "email_claim": "email",
                    "username_claim": "preferred_username",
                    "use_pkce": True,
                    "require_email_verification": True,
                    "enable_jit_provisioning": True,
                    "default_role": "normal_user",
                },
            }

            config_file.write_text(json.dumps(config_data))

            config_manager = ServerConfigManager(tmpdir)
            config = config_manager.load_config()

            assert config is not None
            assert hasattr(config, "oidc_provider_config")
            assert config.oidc_provider_config is not None

            # Verify it's an OIDCProviderConfig object, not a dict
            assert isinstance(config.oidc_provider_config, OIDCProviderConfig)
            assert not isinstance(config.oidc_provider_config, dict)

            # Verify all fields are accessible
            assert config.oidc_provider_config.enabled is True
            assert (
                config.oidc_provider_config.issuer_url
                == "http://localhost:8180/realms/test"
            )
            assert config.oidc_provider_config.client_id == "test-client"
            assert config.oidc_provider_config.client_secret == "test-secret"
            assert config.oidc_provider_config.scopes == ["openid", "profile", "email"]
            assert config.oidc_provider_config.use_pkce is True
