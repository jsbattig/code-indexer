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

    # Payload cache settings (Story #679)
    payload_preview_size_chars: int = 2000
    payload_max_fetch_size_chars: int = 5000
    payload_cache_ttl_seconds: int = 900
    payload_cleanup_interval_seconds: int = 60


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
class AutoWatchConfig:
    """Auto-watch configuration for server file operations - Story #640."""

    auto_watch_enabled: bool = True
    auto_watch_timeout: int = 300  # Timeout in seconds for auto-stop


@dataclass
class OIDCProviderConfig:
    """Single external OIDC provider configuration."""

    enabled: bool = False
    provider_name: str = "SSO"
    issuer_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: Optional[list] = None
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
class TelemetryConfig:
    """
    OpenTelemetry configuration for CIDX Server (Story #695).

    Controls telemetry export including traces, metrics, and logs to an
    OpenTelemetry collector endpoint. Disabled by default to ensure
    zero overhead on fresh installations.
    """

    # Core settings
    enabled: bool = False
    collector_endpoint: str = "http://localhost:4317"
    collector_protocol: str = "grpc"  # Options: grpc, http
    service_name: str = "cidx-server"

    # Export settings
    export_traces: bool = True
    export_metrics: bool = True
    export_logs: bool = False

    # Machine metrics settings
    machine_metrics_enabled: bool = True
    machine_metrics_interval_seconds: int = 60

    # Trace sampling
    trace_sample_rate: float = 1.0  # 0.0 to 1.0

    # Deployment environment (development, staging, production)
    deployment_environment: str = "development"


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
    auto_watch_config: Optional[AutoWatchConfig] = None
    oidc_provider_config: Optional[OIDCProviderConfig] = None
    telemetry_config: Optional[TelemetryConfig] = None

    # Claude CLI integration settings
    anthropic_api_key: Optional[str] = None
    max_concurrent_claude_cli: int = 4
    description_refresh_interval_hours: int = 24

    # SCIP Workspace Cleanup settings (Story #647)
    scip_workspace_retention_days: int = 7  # Default: 7 days

    # PR Creation Configuration (Story #659)
    enable_pr_creation: bool = True  # Enable automatic PR creation after SCIP fixes
    pr_base_branch: str = "main"  # Default base branch for PRs
    default_branch: str = "main"  # Default branch for repository operations

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
        if self.auto_watch_config is None:
            self.auto_watch_config = AutoWatchConfig()
        if self.oidc_provider_config is None:
            self.oidc_provider_config = OIDCProviderConfig()
        if self.telemetry_config is None:
            self.telemetry_config = TelemetryConfig()


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
            server_dir_path: Path to server directory (defaults to CIDX_SERVER_DATA_DIR env var or ~/.cidx-server)
        """
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            # Honor CIDX_SERVER_DATA_DIR environment variable
            default_dir = os.environ.get(
                "CIDX_SERVER_DATA_DIR", str(Path.home() / ".cidx-server")
            )
            self.server_dir = Path(default_dir)

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

            # Convert nested telemetry_config dict to TelemetryConfig
            if "telemetry_config" in config_dict and isinstance(
                config_dict["telemetry_config"], dict
            ):
                config_dict["telemetry_config"] = TelemetryConfig(
                    **config_dict["telemetry_config"]
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

        # SCIP workspace retention days override (Story #647 - AC1)
        if retention_env := os.environ.get("CIDX_SCIP_WORKSPACE_RETENTION_DAYS"):
            try:
                config.scip_workspace_retention_days = int(retention_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_SCIP_WORKSPACE_RETENTION_DAYS environment variable value '{retention_env}'. Using default {config.scip_workspace_retention_days} days"
                )

        # Telemetry environment variable overrides (Story #695)
        # Assert telemetry_config is not None (guaranteed by __post_init__)
        assert config.telemetry_config is not None
        if telemetry_enabled_env := os.environ.get("CIDX_TELEMETRY_ENABLED"):
            config.telemetry_config.enabled = telemetry_enabled_env.lower() in (
                "true",
                "1",
                "yes",
            )

        if collector_endpoint_env := os.environ.get("CIDX_OTEL_COLLECTOR_ENDPOINT"):
            config.telemetry_config.collector_endpoint = collector_endpoint_env

        if collector_protocol_env := os.environ.get("CIDX_OTEL_COLLECTOR_PROTOCOL"):
            config.telemetry_config.collector_protocol = collector_protocol_env.lower()

        if service_name_env := os.environ.get("CIDX_OTEL_SERVICE_NAME"):
            config.telemetry_config.service_name = service_name_env

        if trace_sample_rate_env := os.environ.get("CIDX_OTEL_TRACE_SAMPLE_RATE"):
            try:
                config.telemetry_config.trace_sample_rate = float(trace_sample_rate_env)
            except ValueError:
                logging.warning(
                    f"Invalid CIDX_OTEL_TRACE_SAMPLE_RATE environment variable value '{trace_sample_rate_env}'. Using default {config.telemetry_config.trace_sample_rate}"
                )

        if deployment_env := os.environ.get("CIDX_DEPLOYMENT_ENVIRONMENT"):
            config.telemetry_config.deployment_environment = deployment_env

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

        # Validate SCIP workspace retention days (Story #647 - AC1)
        if not (1 <= config.scip_workspace_retention_days <= 365):
            raise ValueError(
                f"scip_workspace_retention_days must be between 1 and 365, got {config.scip_workspace_retention_days}"
            )

        # Validate description_refresh_interval_hours
        if config.description_refresh_interval_hours < 1:
            raise ValueError(
                f"description_refresh_interval_hours must be greater than 0, got {config.description_refresh_interval_hours}"
            )

        # Validate OIDC configuration
        if config.oidc_provider_config and config.oidc_provider_config.enabled:
            if not config.oidc_provider_config.issuer_url:
                raise ValueError("OIDC issuer_url is required when OIDC is enabled")
            if not config.oidc_provider_config.client_id:
                raise ValueError("OIDC client_id is required when OIDC is enabled")
            # Validate issuer_url format
            if not config.oidc_provider_config.issuer_url.startswith(
                ("http://", "https://")
            ):
                raise ValueError(
                    f"OIDC issuer_url must start with http:// or https://, got {config.oidc_provider_config.issuer_url}"
                )

            # Validate JIT provisioning requirements
            if config.oidc_provider_config.enable_jit_provisioning:
                if not config.oidc_provider_config.email_claim:
                    raise ValueError(
                        "OIDC email_claim is required when JIT provisioning is enabled"
                    )
                if not config.oidc_provider_config.username_claim:
                    raise ValueError(
                        "OIDC username_claim is required when JIT provisioning is enabled"
                    )

        # Validate telemetry configuration (Story #695)
        if config.telemetry_config:
            # Validate trace_sample_rate (0.0 to 1.0)
            if not (0.0 <= config.telemetry_config.trace_sample_rate <= 1.0):
                raise ValueError(
                    f"trace_sample_rate must be between 0.0 and 1.0, got {config.telemetry_config.trace_sample_rate}"
                )

            # Validate collector_protocol
            valid_protocols = {"grpc", "http"}
            if (
                config.telemetry_config.collector_protocol.lower()
                not in valid_protocols
            ):
                raise ValueError(
                    f"collector_protocol must be one of {valid_protocols}, got {config.telemetry_config.collector_protocol}"
                )

            # Validate machine_metrics_interval_seconds
            if config.telemetry_config.machine_metrics_interval_seconds < 1:
                raise ValueError(
                    f"machine_metrics_interval_seconds must be >= 1, got {config.telemetry_config.machine_metrics_interval_seconds}"
                )

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
