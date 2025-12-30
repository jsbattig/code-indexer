"""
Server Configuration Management for CIDX Server.

Handles server configuration creation, validation, environment variable overrides,
and directory structure setup for the CIDX server installation.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class PasswordSecurityConfig:
    """Password strength validation configuration."""

    min_length: int = 12
    max_length: int = 128
    required_char_classes: int = 4
    min_entropy_bits: int = 50
    check_common_passwords: bool = True
    check_personal_info: bool = True
    check_keyboard_patterns: bool = True
    check_sequential_chars: bool = True


@dataclass
class CacheConfig:
    """Cache configuration for HNSW and FTS indexes."""

    # HNSW index cache settings
    index_cache_ttl_minutes: float = 10.0
    index_cache_cleanup_interval: int = 60
    index_cache_max_size_mb: Optional[int] = None

    # FTS index cache settings
    fts_cache_ttl_minutes: float = 10.0
    fts_cache_cleanup_interval: int = 60
    fts_cache_max_size_mb: Optional[int] = None
    fts_cache_reload_on_access: bool = True


@dataclass
class ReindexingConfig:
    """Reindexing trigger and analysis configuration."""

    change_percentage_threshold: float = 10.0
    accuracy_threshold: float = 0.85
    max_index_age_days: int = 30
    batch_size: int = 100
    max_analysis_time_seconds: int = 300
    max_memory_usage_mb: int = 512
    enable_structural_analysis: bool = True
    enable_config_change_detection: bool = True
    enable_corruption_detection: bool = True
    enable_periodic_check: bool = True
    parallel_analysis: bool = True


@dataclass
class ServerResourceConfig:
    """
    Resource limits and timeout configuration for CIDX server.

    All previously hardcoded magic numbers are now externalized here.
    All limits are disabled (set to very high values) to remove constraints.
    """

    # Git operation timeouts (in seconds) - lenient values
    git_clone_timeout: int = 3600  # 1 hour for git clone validation
    git_pull_timeout: int = 3600  # 1 hour for git pull
    git_refresh_timeout: int = 3600  # 1 hour for git refresh
    git_init_conflict_timeout: int = 1800  # 30 minutes for init conflict resolution
    git_service_conflict_timeout: int = (
        1800  # 30 minutes for service conflict resolution
    )
    git_service_cleanup_timeout: int = 300  # 5 minutes for service cleanup
    git_service_wait_timeout: int = 180  # 3 minutes for service cleanup wait
    git_process_check_timeout: int = 30  # 30 seconds for process check
    git_untracked_file_timeout: int = 60  # 1 minute for untracked file check

    # Refresh scheduler timeouts (in seconds)
    cow_clone_timeout: int = 600  # 10 minutes for CoW clone of large repos (11GB)
    git_update_index_timeout: int = 300  # 5 minutes for git update-index --refresh
    git_restore_timeout: int = 300  # 5 minutes for git restore .
    cidx_fix_config_timeout: int = 60  # 1 minute for cidx fix-config
    cidx_index_timeout: int = 3600  # 1 hour for cidx index on large repos

    # NOTE: Artificial resource limits (max_golden_repos, max_repo_size_bytes, max_jobs_per_user)
    # have been REMOVED from the codebase. They were nonsensical limitations that served no purpose.


@dataclass
class OmniSearchConfig:
    """Omni-Search configuration for cross-repository search."""

    max_workers: int = 10
    per_repo_timeout_seconds: int = 300
    cache_max_entries: int = 100
    cache_ttl_seconds: int = 300
    default_limit: int = 10
    max_limit: int = 1000
    default_aggregation_mode: str = "global"
    max_results_per_repo: int = 100
    max_total_results_before_aggregation: int = 10000
    pattern_metacharacters: str = "*?[]^$+|"


@dataclass
class OIDCProviderConfig:
    """Single external OIDC provider configuration."""

    enabled: bool = False
    provider_name: str = "SSO"
    issuer_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list = None
    email_claim: str = "email"
    username_claim: str = "preferred_username"
    use_pkce: bool = True
    require_email_verification: bool = True
    enable_jit_provisioning: bool = True
    default_role: str = "normal_user"

    def __post_init__(self):
        if self.scopes is None:
            self.scopes = ["openid", "profile", "email"]


@dataclass
class ServerConfig:
    """
    Server configuration data structure.

    Contains all configurable server settings including networking,
    authentication, logging, cache, reindexing, and resource configurations.
    """

    server_dir: str
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 4
    jwt_expiration_minutes: int = 10
    log_level: str = "INFO"
    password_security: Optional[PasswordSecurityConfig] = None
    resource_config: Optional[ServerResourceConfig] = None
    cache_config: Optional[CacheConfig] = None
    reindexing_config: Optional[ReindexingConfig] = None
    omni_search_config: Optional[OmniSearchConfig] = None
    oidc_provider_config: Optional[OIDCProviderConfig] = None

    # Claude CLI integration settings
    anthropic_api_key: Optional[str] = None
    max_concurrent_claude_cli: int = 4
    description_refresh_interval_hours: int = 24

    def __post_init__(self):
        """Initialize nested config objects if not provided."""
        if self.password_security is None:
            self.password_security = PasswordSecurityConfig()
        if self.resource_config is None:
            self.resource_config = ServerResourceConfig()
        if self.cache_config is None:
            self.cache_config = CacheConfig()
        if self.reindexing_config is None:
            self.reindexing_config = ReindexingConfig()
        if self.omni_search_config is None:
            self.omni_search_config = OmniSearchConfig()
        if self.oidc_provider_config is None:
            self.oidc_provider_config = OIDCProviderConfig()


class ServerConfigManager:
    """
    Manages CIDX server configuration.

    Handles configuration creation, validation, file persistence,
    environment variable overrides, and server directory setup.
    """

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize server configuration manager.

        Args:
            server_dir_path: Path to server directory (defaults to ~/.cidx-server)
        """
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        self.config_file_path = self.server_dir / "config.json"

    def create_default_config(self) -> ServerConfig:
        """
        Create default server configuration.

        Returns:
            ServerConfig with default values
        """
        return ServerConfig(server_dir=str(self.server_dir))

    def save_config(self, config: ServerConfig) -> None:
        """
        Save configuration to file.

        Args:
            config: ServerConfig object to save
        """
        # Ensure server directory exists
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Convert config to dictionary and save as JSON
        config_dict = asdict(config)

        with open(self.config_file_path, "w") as f:
            json.dump(config_dict, f, indent=2)

    def load_config(self) -> Optional[ServerConfig]:
        """
        Load configuration from file.

        Returns:
            ServerConfig if file exists and is valid, None otherwise

        Raises:
            ValueError: If configuration file is malformed
        """
        if not self.config_file_path.exists():
            return None

        try:
            with open(self.config_file_path, "r") as f:
                config_dict = json.load(f)

            # Ensure server_dir is set if missing from file
            if "server_dir" not in config_dict:
                config_dict["server_dir"] = str(self.server_dir)

            # Convert nested password_security dict to PasswordSecurityConfig
            if "password_security" in config_dict and isinstance(
                config_dict["password_security"], dict
            ):
                config_dict["password_security"] = PasswordSecurityConfig(
                    **config_dict["password_security"]
                )

            # Convert nested resource_config dict to ServerResourceConfig
            if "resource_config" in config_dict and isinstance(
                config_dict["resource_config"], dict
            ):
                config_dict["resource_config"] = ServerResourceConfig(
                    **config_dict["resource_config"]
                )

            # Convert nested cache_config dict to CacheConfig
            if "cache_config" in config_dict and isinstance(
                config_dict["cache_config"], dict
            ):
                config_dict["cache_config"] = CacheConfig(**config_dict["cache_config"])

            # Convert nested reindexing_config dict to ReindexingConfig
            if "reindexing_config" in config_dict and isinstance(
                config_dict["reindexing_config"], dict
            ):
                config_dict["reindexing_config"] = ReindexingConfig(
                    **config_dict["reindexing_config"]
                )

            # Convert nested omni_search_config dict to OmniSearchConfig
            if "omni_search_config" in config_dict and isinstance(
                config_dict["omni_search_config"], dict
            ):
                config_dict["omni_search_config"] = OmniSearchConfig(
                    **config_dict["omni_search_config"]
                )

            # Convert nested oidc_provider_config dict to OIDCProviderConfig
            if "oidc_provider_config" in config_dict and isinstance(
                config_dict["oidc_provider_config"], dict
            ):
                config_dict["oidc_provider_config"] = OIDCProviderConfig(
                    **config_dict["oidc_provider_config"]
                )

            return ServerConfig(**config_dict)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse configuration file: {e}")
        except TypeError as e:
            raise ValueError(f"Invalid configuration format: {e}")

    def apply_env_overrides(self, config: ServerConfig) -> ServerConfig:
        """
        Apply environment variable overrides to configuration.

        Supported environment variables:
        - CIDX_SERVER_HOST: Override host setting
        - CIDX_SERVER_PORT: Override port setting
        - CIDX_JWT_EXPIRATION_MINUTES: Override JWT expiration
        - CIDX_LOG_LEVEL: Override log level

        Args:
            config: Base configuration to apply overrides to

        Returns:
            Updated configuration with environment overrides
        """
        # Host override
        if host_env := os.environ.get("CIDX_SERVER_HOST"):
            config.host = host_env

        # Port override
        if port_env := os.environ.get("CIDX_SERVER_PORT"):
            try:
                config.port = int(port_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_SERVER_PORT environment variable value '{port_env}'. Using default port {config.port}"
                )

        # JWT expiration override
        if jwt_exp_env := os.environ.get("CIDX_JWT_EXPIRATION_MINUTES"):
            try:
                config.jwt_expiration_minutes = int(jwt_exp_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_JWT_EXPIRATION_MINUTES environment variable value '{jwt_exp_env}'. Using default {config.jwt_expiration_minutes} minutes"
                )

        # Log level override
        if log_level_env := os.environ.get("CIDX_LOG_LEVEL"):
            config.log_level = log_level_env.upper()

        return config

    def validate_config(self, config: ServerConfig) -> None:
        """
        Validate configuration settings.

        Args:
            config: Configuration to validate

        Raises:
            ValueError: If any configuration value is invalid
        """
        # Validate port range
        if not (1 <= config.port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {config.port}")

        # Validate JWT expiration
        if config.jwt_expiration_minutes <= 0:
            raise ValueError(
                f"JWT expiration must be greater than 0, got {config.jwt_expiration_minutes}"
            )

        # Validate log level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if config.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Log level must be one of {valid_log_levels}, got {config.log_level}"
            )

        # Validate max_concurrent_claude_cli
        if config.max_concurrent_claude_cli < 1:
            raise ValueError(
                f"max_concurrent_claude_cli must be greater than 0, got {config.max_concurrent_claude_cli}"
            )

        # Validate description_refresh_interval_hours
        if config.description_refresh_interval_hours < 1:
            raise ValueError(
                f"description_refresh_interval_hours must be greater than 0, got {config.description_refresh_interval_hours}"
            )

        # Validate OIDC configuration
        if config.oidc_provider_config.enabled:
            if not config.oidc_provider_config.issuer_url:
                raise ValueError("OIDC issuer_url is required when OIDC is enabled")
            if not config.oidc_provider_config.client_id:
                raise ValueError("OIDC client_id is required when OIDC is enabled")
            # Validate issuer_url format
            if not config.oidc_provider_config.issuer_url.startswith(("http://", "https://")):
                raise ValueError(f"OIDC issuer_url must start with http:// or https://, got {config.oidc_provider_config.issuer_url}")

    def create_server_directories(self) -> None:
        """
        Create necessary server directories.

        Creates:
        - Main server directory
        - logs/ subdirectory
        - data/ subdirectory
        """
        # Create main server directory
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Create logs directory
        logs_dir = self.server_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Create data directory
        data_dir = self.server_dir / "data"
        data_dir.mkdir(exist_ok=True)
