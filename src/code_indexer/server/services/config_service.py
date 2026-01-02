"""
Configuration Service for CIDX Server Admin UI.

Provides a high-level interface for reading and updating server configuration.
All settings persist to ~/.cidx-server/config.json via ServerConfigManager.
"""

import logging
from typing import Any, Dict, Optional

from ..utils.config_manager import (
    ServerConfigManager,
    ServerConfig,
)

logger = logging.getLogger(__name__)


class ConfigService:
    """
    Service for managing server configuration.

    Provides methods for loading, updating, and saving server configuration
    with validation. All changes persist to ~/.cidx-server/config.json.
    """

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize the configuration service.

        Args:
            server_dir_path: Optional path to server directory.
                           Defaults to ~/.cidx-server
        """
        self.config_manager = ServerConfigManager(server_dir_path)
        self._config: Optional[ServerConfig] = None

    def load_config(self) -> ServerConfig:
        """
        Load configuration from disk or create default.

        Returns:
            ServerConfig object with current settings
        """
        config = self.config_manager.load_config()
        if config is None:
            config = self.config_manager.create_default_config()
            # Save the default config so it persists
            self.config_manager.save_config(config)

        self._config = config
        return config

    def get_config(self) -> ServerConfig:
        """
        Get current configuration, loading if necessary.

        Returns:
            ServerConfig object
        """
        if self._config is None:
            self.load_config()
        return self._config

    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all settings as a flat dictionary for UI display.

        Returns:
            Dictionary with all settings flattened for easy access
        """
        config = self.get_config()

        settings = {
            # Server settings
            "server": {
                "host": config.host,
                "port": config.port,
                "workers": config.workers,
                "log_level": config.log_level,
                "jwt_expiration_minutes": config.jwt_expiration_minutes,
            },
            # Cache settings
            "cache": {
                "index_cache_ttl_minutes": config.cache_config.index_cache_ttl_minutes,
                "index_cache_cleanup_interval": config.cache_config.index_cache_cleanup_interval,
                "index_cache_max_size_mb": config.cache_config.index_cache_max_size_mb,
                "fts_cache_ttl_minutes": config.cache_config.fts_cache_ttl_minutes,
                "fts_cache_cleanup_interval": config.cache_config.fts_cache_cleanup_interval,
                "fts_cache_max_size_mb": config.cache_config.fts_cache_max_size_mb,
                "fts_cache_reload_on_access": config.cache_config.fts_cache_reload_on_access,
            },
            # Reindexing settings
            "reindexing": {
                "change_percentage_threshold": config.reindexing_config.change_percentage_threshold,
                "accuracy_threshold": config.reindexing_config.accuracy_threshold,
                "max_index_age_days": config.reindexing_config.max_index_age_days,
                "batch_size": config.reindexing_config.batch_size,
                "max_analysis_time_seconds": config.reindexing_config.max_analysis_time_seconds,
                "max_memory_usage_mb": config.reindexing_config.max_memory_usage_mb,
                "enable_structural_analysis": config.reindexing_config.enable_structural_analysis,
                "enable_config_change_detection": config.reindexing_config.enable_config_change_detection,
                "enable_corruption_detection": config.reindexing_config.enable_corruption_detection,
                "enable_periodic_check": config.reindexing_config.enable_periodic_check,
                "parallel_analysis": config.reindexing_config.parallel_analysis,
            },
            # Git operation timeouts
            "timeouts": {
                "git_clone_timeout": config.resource_config.git_clone_timeout,
                "git_pull_timeout": config.resource_config.git_pull_timeout,
                "git_refresh_timeout": config.resource_config.git_refresh_timeout,
                "cidx_index_timeout": config.resource_config.cidx_index_timeout,
            },
            # Password security
            "password_security": {
                "min_length": config.password_security.min_length,
                "max_length": config.password_security.max_length,
                "required_char_classes": config.password_security.required_char_classes,
                "min_entropy_bits": config.password_security.min_entropy_bits,
            },
            # Claude CLI integration
            "claude_cli": {
                "anthropic_api_key": "sk-ant-***" if config.anthropic_api_key else None,
                "max_concurrent_claude_cli": config.max_concurrent_claude_cli,
                "description_refresh_interval_hours": config.description_refresh_interval_hours,
            },
            # OIDC/SSO authentication
            "oidc": {
                "enabled": config.oidc_provider_config.enabled,
                "provider_name": config.oidc_provider_config.provider_name,
                "issuer_url": config.oidc_provider_config.issuer_url,
                "client_id": config.oidc_provider_config.client_id,
                "client_secret": config.oidc_provider_config.client_secret,
                "scopes": config.oidc_provider_config.scopes,
                "email_claim": config.oidc_provider_config.email_claim,
                "username_claim": config.oidc_provider_config.username_claim,
                "use_pkce": config.oidc_provider_config.use_pkce,
                "require_email_verification": config.oidc_provider_config.require_email_verification,
                "enable_jit_provisioning": config.oidc_provider_config.enable_jit_provisioning,
                "default_role": config.oidc_provider_config.default_role,
            },
            # SCIP workspace cleanup (Story #647)
            "scip_cleanup": {
                "scip_workspace_retention_days": config.scip_workspace_retention_days,
            },
        }

        return settings

    def update_setting(
        self, category: str, key: str, value: Any, skip_validation: bool = False
    ) -> None:
        """
        Update a single setting.

        Args:
            category: Setting category (server, cache, reindexing, timeouts, password_security)
            key: Setting key within the category
            value: New value for the setting
            skip_validation: If True, skip validation and save (for batch updates)

        Raises:
            ValueError: If category or key is invalid, or value fails validation
        """
        config = self.get_config()

        if category == "server":
            self._update_server_setting(config, key, value)
        elif category == "cache":
            self._update_cache_setting(config, key, value)
        elif category == "reindexing":
            self._update_reindexing_setting(config, key, value)
        elif category == "timeouts":
            self._update_timeout_setting(config, key, value)
        elif category == "password_security":
            self._update_password_security_setting(config, key, value)
        elif category == "claude_cli":
            self._update_claude_cli_setting(config, key, value)
        elif category == "oidc":
            self._update_oidc_setting(config, key, value)
        elif category == "scip_cleanup":
            self._update_scip_cleanup_setting(config, key, value)
        else:
            raise ValueError(f"Unknown category: {category}")

        # Validate and save (unless skipping for batch updates)
        if not skip_validation:
            self.config_manager.validate_config(config)
            self.config_manager.save_config(config)
            logger.info("Updated setting %s.%s to %s", category, key, value)
        else:
            # Just update in memory, don't validate or save yet
            logger.debug(
                "Updated setting %s.%s to %s (validation deferred)",
                category,
                key,
                value,
            )

    def _update_server_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a server setting."""
        if key == "host":
            config.host = str(value)
        elif key == "port":
            config.port = int(value)
        elif key == "workers":
            config.workers = int(value)
        elif key == "log_level":
            config.log_level = str(value).upper()
        elif key == "jwt_expiration_minutes":
            config.jwt_expiration_minutes = int(value)
        else:
            raise ValueError(f"Unknown server setting: {key}")

    def _update_cache_setting(self, config: ServerConfig, key: str, value: Any) -> None:
        """Update a cache setting."""
        cache = config.cache_config
        if key == "index_cache_ttl_minutes":
            cache.index_cache_ttl_minutes = float(value)
        elif key == "index_cache_cleanup_interval":
            cache.index_cache_cleanup_interval = int(value)
        elif key == "index_cache_max_size_mb":
            cache.index_cache_max_size_mb = int(value) if value else None
        elif key == "fts_cache_ttl_minutes":
            cache.fts_cache_ttl_minutes = float(value)
        elif key == "fts_cache_cleanup_interval":
            cache.fts_cache_cleanup_interval = int(value)
        elif key == "fts_cache_max_size_mb":
            cache.fts_cache_max_size_mb = int(value) if value else None
        elif key == "fts_cache_reload_on_access":
            cache.fts_cache_reload_on_access = bool(value)
        else:
            raise ValueError(f"Unknown cache setting: {key}")

    def _update_reindexing_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a reindexing setting."""
        reindex = config.reindexing_config
        if key == "change_percentage_threshold":
            reindex.change_percentage_threshold = float(value)
        elif key == "accuracy_threshold":
            reindex.accuracy_threshold = float(value)
        elif key == "max_index_age_days":
            reindex.max_index_age_days = int(value)
        elif key == "batch_size":
            reindex.batch_size = int(value)
        elif key == "max_analysis_time_seconds":
            reindex.max_analysis_time_seconds = int(value)
        elif key == "max_memory_usage_mb":
            reindex.max_memory_usage_mb = int(value)
        elif key == "enable_structural_analysis":
            reindex.enable_structural_analysis = bool(value)
        elif key == "enable_config_change_detection":
            reindex.enable_config_change_detection = bool(value)
        elif key == "enable_corruption_detection":
            reindex.enable_corruption_detection = bool(value)
        elif key == "enable_periodic_check":
            reindex.enable_periodic_check = bool(value)
        elif key == "parallel_analysis":
            reindex.parallel_analysis = bool(value)
        else:
            raise ValueError(f"Unknown reindexing setting: {key}")

    def _update_timeout_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a timeout setting."""
        timeouts = config.resource_config
        if key == "git_clone_timeout":
            timeouts.git_clone_timeout = int(value)
        elif key == "git_pull_timeout":
            timeouts.git_pull_timeout = int(value)
        elif key == "git_refresh_timeout":
            timeouts.git_refresh_timeout = int(value)
        elif key == "cidx_index_timeout":
            timeouts.cidx_index_timeout = int(value)
        else:
            raise ValueError(f"Unknown timeout setting: {key}")

    def _update_password_security_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a password security setting."""
        pwd = config.password_security
        if key == "min_length":
            pwd.min_length = int(value)
        elif key == "max_length":
            pwd.max_length = int(value)
        elif key == "required_char_classes":
            pwd.required_char_classes = int(value)
        elif key == "min_entropy_bits":
            pwd.min_entropy_bits = int(value)
        else:
            raise ValueError(f"Unknown password security setting: {key}")

    def _update_claude_cli_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a Claude CLI setting."""
        if key == "anthropic_api_key":
            config.anthropic_api_key = str(value) if value else None
        elif key == "max_concurrent_claude_cli":
            config.max_concurrent_claude_cli = int(value)
        elif key == "description_refresh_interval_hours":
            config.description_refresh_interval_hours = int(value)
        else:
            raise ValueError(f"Unknown claude_cli setting: {key}")

    def _update_oidc_setting(self, config: ServerConfig, key: str, value: Any) -> None:
        """Update an OIDC setting."""
        oidc = config.oidc_provider_config
        if key == "enabled":
            oidc.enabled = value in ["true", True]
        elif key == "provider_name":
            oidc.provider_name = str(value)
        elif key == "issuer_url":
            oidc.issuer_url = str(value)
        elif key == "client_id":
            oidc.client_id = str(value)
        elif key == "client_secret":
            # Only update if value is provided (not empty)
            if value:
                oidc.client_secret = str(value)
        elif key == "scopes":
            # Convert space-separated string to list
            oidc.scopes = (
                str(value).split() if value else ["openid", "profile", "email"]
            )
        elif key == "email_claim":
            oidc.email_claim = str(value)
        elif key == "username_claim":
            oidc.username_claim = str(value)
        elif key == "use_pkce":
            oidc.use_pkce = value in ["true", True]
        elif key == "require_email_verification":
            oidc.require_email_verification = value in ["true", True]
        elif key == "enable_jit_provisioning":
            oidc.enable_jit_provisioning = value in ["true", True]
        elif key == "default_role":
            oidc.default_role = str(value)
        else:
            raise ValueError(f"Unknown OIDC setting: {key}")

    def _update_scip_cleanup_setting(
        self, config: ServerConfig, key: str, value: Any
    ) -> None:
        """Update a SCIP cleanup setting (Story #647)."""
        if key == "scip_workspace_retention_days":
            config.scip_workspace_retention_days = int(value)
        else:
            raise ValueError(f"Unknown SCIP cleanup setting: {key}")

    def save_all_settings(self, settings: Dict[str, Dict[str, Any]]) -> None:
        """
        Save all settings at once.

        Args:
            settings: Dictionary with category -> {key: value} structure

        Raises:
            ValueError: If any setting fails validation
        """
        config = self.get_config()

        for category, category_settings in settings.items():
            for key, value in category_settings.items():
                if category == "server":
                    self._update_server_setting(config, key, value)
                elif category == "cache":
                    self._update_cache_setting(config, key, value)
                elif category == "reindexing":
                    self._update_reindexing_setting(config, key, value)
                elif category == "timeouts":
                    self._update_timeout_setting(config, key, value)
                elif category == "password_security":
                    self._update_password_security_setting(config, key, value)
                elif category == "claude_cli":
                    self._update_claude_cli_setting(config, key, value)

        # Validate and save
        self.config_manager.validate_config(config)
        self.config_manager.save_config(config)
        logger.info("Saved all settings")

    def get_config_file_path(self) -> str:
        """Get the path to the configuration file."""
        return str(self.config_manager.config_file_path)


# Global service instance
_config_service: Optional[ConfigService] = None


def get_config_service() -> ConfigService:
    """Get or create the global ConfigService instance."""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service


def reset_config_service() -> None:
    """
    Reset the global ConfigService singleton.

    This is primarily used for testing to ensure each test gets a fresh
    config service instance with its own server directory.
    """
    global _config_service
    _config_service = None
