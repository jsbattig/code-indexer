"""
Unit tests for ConfigService.

Tests verify that:
1. ConfigService loads and saves configuration correctly
2. Individual settings can be updated
3. Validation is enforced on save
4. Configuration persists to ~/.cidx-server/config.json
"""

import pytest
from pathlib import Path

from code_indexer.server.services.config_service import ConfigService
from code_indexer.server.utils.config_manager import (
    ServerConfig,
    ServerResourceConfig,
    CacheConfig,
    ReindexingConfig,
    PasswordSecurityConfig,
)


class TestConfigServiceInitialization:
    """Test ConfigService initialization and loading."""

    def test_load_config_creates_default_if_not_exists(self, tmp_path):
        """Test that load_config creates default config if none exists."""
        service = ConfigService(server_dir_path=str(tmp_path))
        config = service.load_config()

        assert config is not None
        assert isinstance(config, ServerConfig)
        assert config.host == "127.0.0.1"
        assert config.port == 8000

    def test_load_config_loads_existing_config(self, tmp_path):
        """Test that load_config loads existing configuration."""
        service = ConfigService(server_dir_path=str(tmp_path))

        # Create and save a custom config
        service.load_config()
        service.update_setting("server", "port", 9000)

        # Create a new service instance and verify it loads the saved config
        new_service = ConfigService(server_dir_path=str(tmp_path))
        config = new_service.load_config()

        assert config.port == 9000

    def test_get_config_loads_if_not_cached(self, tmp_path):
        """Test that get_config loads config if not already cached."""
        service = ConfigService(server_dir_path=str(tmp_path))

        # Call get_config without prior load_config
        config = service.get_config()

        assert config is not None
        assert isinstance(config, ServerConfig)


class TestConfigServiceGetAllSettings:
    """Test ConfigService.get_all_settings()."""

    def test_get_all_settings_returns_structured_dict(self, tmp_path):
        """Test that get_all_settings returns properly structured dictionary."""
        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        # Verify structure
        assert "server" in settings
        assert "cache" in settings
        assert "reindexing" in settings
        assert "timeouts" in settings
        assert "password_security" in settings

    def test_get_all_settings_contains_server_settings(self, tmp_path):
        """Test that server settings are included."""
        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        assert "host" in settings["server"]
        assert "port" in settings["server"]
        assert "workers" in settings["server"]
        assert "log_level" in settings["server"]
        assert "jwt_expiration_minutes" in settings["server"]

    def test_get_all_settings_contains_cache_settings(self, tmp_path):
        """Test that cache settings are included."""
        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        assert "index_cache_ttl_minutes" in settings["cache"]
        assert "fts_cache_ttl_minutes" in settings["cache"]
        assert "fts_cache_reload_on_access" in settings["cache"]

    def test_get_all_settings_contains_reindexing_settings(self, tmp_path):
        """Test that reindexing settings are included."""
        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        assert "change_percentage_threshold" in settings["reindexing"]
        assert "accuracy_threshold" in settings["reindexing"]
        assert "batch_size" in settings["reindexing"]


class TestConfigServiceUpdateSetting:
    """Test ConfigService.update_setting()."""

    def test_update_server_host(self, tmp_path):
        """Test updating server host setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("server", "host", "0.0.0.0")

        config = service.get_config()
        assert config.host == "0.0.0.0"

    def test_update_server_port(self, tmp_path):
        """Test updating server port setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("server", "port", 9000)

        config = service.get_config()
        assert config.port == 9000

    def test_update_log_level(self, tmp_path):
        """Test updating log level setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("server", "log_level", "DEBUG")

        config = service.get_config()
        assert config.log_level == "DEBUG"

    def test_update_cache_ttl(self, tmp_path):
        """Test updating cache TTL setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("cache", "index_cache_ttl_minutes", 30.0)

        config = service.get_config()
        assert config.cache_config.index_cache_ttl_minutes == 30.0

    def test_update_reindexing_threshold(self, tmp_path):
        """Test updating reindexing threshold."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("reindexing", "change_percentage_threshold", 15.0)

        config = service.get_config()
        assert config.reindexing_config.change_percentage_threshold == 15.0

    def test_update_timeout_setting(self, tmp_path):
        """Test updating timeout setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("timeouts", "git_clone_timeout", 7200)

        config = service.get_config()
        assert config.resource_config.git_clone_timeout == 7200

    def test_update_password_security_setting(self, tmp_path):
        """Test updating password security setting."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("password_security", "min_length", 16)

        config = service.get_config()
        assert config.password_security.min_length == 16

    def test_update_invalid_category_raises_error(self, tmp_path):
        """Test that invalid category raises ValueError."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="Unknown category"):
            service.update_setting("invalid_category", "key", "value")

    def test_update_invalid_key_raises_error(self, tmp_path):
        """Test that invalid key raises ValueError."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="Unknown server setting"):
            service.update_setting("server", "invalid_key", "value")


class TestConfigServiceValidation:
    """Test ConfigService validation."""

    def test_invalid_port_fails_validation(self, tmp_path):
        """Test that invalid port fails validation."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="Port must be between"):
            service.update_setting("server", "port", 70000)

    def test_invalid_log_level_fails_validation(self, tmp_path):
        """Test that invalid log level fails validation."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="Log level must be one of"):
            service.update_setting("server", "log_level", "INVALID")

    def test_zero_jwt_expiration_fails_validation(self, tmp_path):
        """Test that zero JWT expiration fails validation."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="JWT expiration must be greater than 0"):
            service.update_setting("server", "jwt_expiration_minutes", 0)


class TestConfigServicePersistence:
    """Test ConfigService persistence."""

    def test_settings_persist_to_file(self, tmp_path):
        """Test that settings persist to config.json file."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("server", "port", 9000)
        service.update_setting("cache", "index_cache_ttl_minutes", 30.0)

        # Verify file exists
        config_file = tmp_path / "config.json"
        assert config_file.exists()

        # Load with new service instance
        new_service = ConfigService(server_dir_path=str(tmp_path))
        config = new_service.load_config()

        assert config.port == 9000
        assert config.cache_config.index_cache_ttl_minutes == 30.0

    def test_save_all_settings(self, tmp_path):
        """Test save_all_settings saves multiple settings at once."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        settings = {
            "server": {"port": 9000, "log_level": "DEBUG"},
            "cache": {"index_cache_ttl_minutes": 20.0},
        }

        service.save_all_settings(settings)

        config = service.get_config()
        assert config.port == 9000
        assert config.log_level == "DEBUG"
        assert config.cache_config.index_cache_ttl_minutes == 20.0

    def test_get_config_file_path(self, tmp_path):
        """Test get_config_file_path returns correct path."""
        service = ConfigService(server_dir_path=str(tmp_path))

        path = service.get_config_file_path()

        assert path == str(tmp_path / "config.json")


class TestNewConfigDataclasses:
    """Test new CacheConfig and ReindexingConfig dataclasses."""

    def test_cache_config_defaults(self):
        """Test CacheConfig has correct defaults."""
        config = CacheConfig()

        assert config.index_cache_ttl_minutes == 10.0
        assert config.index_cache_cleanup_interval == 60
        assert config.index_cache_max_size_mb is None
        assert config.fts_cache_ttl_minutes == 10.0
        assert config.fts_cache_reload_on_access is True

    def test_reindexing_config_defaults(self):
        """Test ReindexingConfig has correct defaults."""
        config = ReindexingConfig()

        assert config.change_percentage_threshold == 10.0
        assert config.accuracy_threshold == 0.85
        assert config.max_index_age_days == 30
        assert config.batch_size == 100
        assert config.parallel_analysis is True

    def test_server_config_includes_new_configs(self):
        """Test ServerConfig includes cache and reindexing configs."""
        config = ServerConfig(server_dir="/tmp/test")

        assert config.cache_config is not None
        assert config.reindexing_config is not None
        assert isinstance(config.cache_config, CacheConfig)
        assert isinstance(config.reindexing_config, ReindexingConfig)

    def test_server_config_workers_default(self):
        """Test ServerConfig has workers field with default value."""
        config = ServerConfig(server_dir="/tmp/test")

        assert config.workers == 4


class TestOIDCConfigSettings:
    """Test OIDC configuration settings."""

    def test_update_oidc_enabled_true(self, tmp_path):
        """Test updating OIDC enabled to true."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "enabled", "true")

        config = service.get_config()
        assert config.oidc_provider_config.enabled is True

    def test_update_oidc_enabled_false(self, tmp_path):
        """Test updating OIDC enabled to false."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "enabled", "false")

        config = service.get_config()
        assert config.oidc_provider_config.enabled is False

    def test_update_oidc_provider_name(self, tmp_path):
        """Test updating OIDC provider name."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "provider_name", "MySSO")

        config = service.get_config()
        assert config.oidc_provider_config.provider_name == "MySSO"

    def test_update_oidc_issuer_url(self, tmp_path):
        """Test updating OIDC issuer URL."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "issuer_url", "https://auth.example.com")

        config = service.get_config()
        assert config.oidc_provider_config.issuer_url == "https://auth.example.com"

    def test_update_oidc_client_id(self, tmp_path):
        """Test updating OIDC client ID."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "client_id", "my-client-id")

        config = service.get_config()
        assert config.oidc_provider_config.client_id == "my-client-id"

    def test_update_oidc_client_secret(self, tmp_path):
        """Test updating OIDC client secret."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "client_secret", "my-secret")

        config = service.get_config()
        assert config.oidc_provider_config.client_secret == "my-secret"

    def test_update_oidc_client_secret_empty_preserves_existing(self, tmp_path):
        """Test that empty client secret doesn't overwrite existing value."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set initial secret
        service.update_setting("oidc", "client_secret", "original-secret")

        # Try to update with empty string
        service.update_setting("oidc", "client_secret", "")

        config = service.get_config()
        # Should still have original secret
        assert config.oidc_provider_config.client_secret == "original-secret"

    def test_update_oidc_scopes(self, tmp_path):
        """Test updating OIDC scopes."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "scopes", "openid profile email groups")

        config = service.get_config()
        assert config.oidc_provider_config.scopes == ["openid", "profile", "email", "groups"]

    def test_update_oidc_email_claim(self, tmp_path):
        """Test updating OIDC email claim."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "email_claim", "user_email")

        config = service.get_config()
        assert config.oidc_provider_config.email_claim == "user_email"

    def test_update_oidc_username_claim(self, tmp_path):
        """Test updating OIDC username claim."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "username_claim", "sub")

        config = service.get_config()
        assert config.oidc_provider_config.username_claim == "sub"

    def test_update_oidc_use_pkce(self, tmp_path):
        """Test updating OIDC use_pkce."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "use_pkce", "false")

        config = service.get_config()
        assert config.oidc_provider_config.use_pkce is False

    def test_update_oidc_require_email_verification(self, tmp_path):
        """Test updating OIDC require_email_verification."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "require_email_verification", "false")

        config = service.get_config()
        assert config.oidc_provider_config.require_email_verification is False

    def test_update_oidc_enable_jit_provisioning(self, tmp_path):
        """Test updating OIDC enable_jit_provisioning."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "enable_jit_provisioning", "false")

        config = service.get_config()
        assert config.oidc_provider_config.enable_jit_provisioning is False

    def test_update_oidc_default_role(self, tmp_path):
        """Test updating OIDC default_role."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        service.update_setting("oidc", "default_role", "admin")

        config = service.get_config()
        assert config.oidc_provider_config.default_role == "admin"

    def test_update_unknown_oidc_setting_raises_error(self, tmp_path):
        """Test that updating unknown OIDC setting raises ValueError."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        with pytest.raises(ValueError, match="Unknown OIDC setting: invalid_key"):
            service.update_setting("oidc", "invalid_key", "value")


class TestOIDCConfigValidation:
    """Test OIDC configuration validation."""

    def test_validation_rejects_empty_issuer_url_when_enabled(self, tmp_path):
        """Test that empty issuer_url is rejected when OIDC is enabled."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set required fields first
        service.update_setting("oidc", "issuer_url", "http://localhost:8180/realms/test")
        service.update_setting("oidc", "client_id", "test-client")

        # Enable OIDC
        service.update_setting("oidc", "enabled", "true")

        # Try to clear issuer_url - should fail validation
        with pytest.raises(ValueError, match="OIDC issuer_url is required when OIDC is enabled"):
            service.update_setting("oidc", "issuer_url", "")

    def test_validation_rejects_invalid_issuer_url_format(self, tmp_path):
        """Test that invalid issuer_url format is rejected."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set valid fields first
        service.update_setting("oidc", "issuer_url", "http://localhost:8180/realms/test")
        service.update_setting("oidc", "client_id", "test-client")

        # Enable OIDC
        service.update_setting("oidc", "enabled", "true")

        # Try to set invalid issuer_url - should fail validation
        with pytest.raises(ValueError, match="OIDC issuer_url must start with http:// or https://"):
            service.update_setting("oidc", "issuer_url", "invalid-url")

    def test_validation_allows_empty_issuer_url_when_disabled(self, tmp_path):
        """Test that empty issuer_url is allowed when OIDC is disabled."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Disable OIDC
        service.update_setting("oidc", "enabled", "false")

        # Clear issuer_url - should succeed because OIDC is disabled
        service.update_setting("oidc", "issuer_url", "")

        config = service.get_config()
        assert config.oidc_provider_config.issuer_url == ""

    def test_validation_requires_email_claim_when_jit_enabled(self, tmp_path):
        """Test that email_claim is required when JIT provisioning is enabled."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set required OIDC fields
        service.update_setting("oidc", "issuer_url", "http://localhost:8180/realms/test")
        service.update_setting("oidc", "client_id", "test-client")
        service.update_setting("oidc", "enabled", "true")

        # Enable JIT provisioning
        service.update_setting("oidc", "enable_jit_provisioning", "true")

        # Try to clear email_claim - should fail validation
        with pytest.raises(ValueError, match="OIDC email_claim is required when JIT provisioning is enabled"):
            service.update_setting("oidc", "email_claim", "")

    def test_validation_requires_username_claim_when_jit_enabled(self, tmp_path):
        """Test that username_claim is required when JIT provisioning is enabled."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set required OIDC fields
        service.update_setting("oidc", "issuer_url", "http://localhost:8180/realms/test")
        service.update_setting("oidc", "client_id", "test-client")
        service.update_setting("oidc", "enabled", "true")

        # Enable JIT provisioning
        service.update_setting("oidc", "enable_jit_provisioning", "true")

        # Try to clear username_claim - should fail validation
        with pytest.raises(ValueError, match="OIDC username_claim is required when JIT provisioning is enabled"):
            service.update_setting("oidc", "username_claim", "")

    def test_validation_allows_empty_claims_when_jit_disabled(self, tmp_path):
        """Test that empty email_claim and username_claim are allowed when JIT is disabled."""
        service = ConfigService(server_dir_path=str(tmp_path))
        service.load_config()

        # Set required OIDC fields
        service.update_setting("oidc", "issuer_url", "http://localhost:8180/realms/test")
        service.update_setting("oidc", "client_id", "test-client")
        service.update_setting("oidc", "enabled", "true")

        # Disable JIT provisioning
        service.update_setting("oidc", "enable_jit_provisioning", "false")

        # Clear email_claim and username_claim - should succeed
        service.update_setting("oidc", "email_claim", "")
        service.update_setting("oidc", "username_claim", "")

        config = service.get_config()
        assert config.oidc_provider_config.email_claim == ""
        assert config.oidc_provider_config.username_claim == ""
