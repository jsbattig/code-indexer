"""
Configuration management for the CIDX test application.

This module handles loading configuration from various sources,
environment variables, and provides typed configuration objects.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


class Environment(Enum):
    """Application environment types."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(Enum):
    """Logging level options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class DatabaseConfig:
    """Database configuration settings."""

    url: str = "sqlite:///./app.db"
    pool_size: int = 5
    pool_timeout: int = 30
    echo_sql: bool = False
    migrate_on_startup: bool = True


@dataclass
class AuthConfig:
    """Authentication configuration settings."""

    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    token_expiry_minutes: int = 60
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15


@dataclass
class ApiConfig:
    """API configuration settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    reload: bool = False
    workers: int = 1
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_credentials: bool = True
    request_timeout: int = 30
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_minutes: int = 1


@dataclass
class SearchConfig:
    """Search engine configuration settings."""

    vector_dimension: int = 1024
    similarity_threshold: float = 0.1
    max_results: int = 100
    cache_size: int = 1000
    index_batch_size: int = 100
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class LoggingConfig:
    """Logging configuration settings."""

    level: LogLevel = LogLevel.INFO
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    console_output: bool = True


@dataclass
class AppConfig:
    """Main application configuration."""

    app_name: str = "CIDX Test Application"
    app_version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug_mode: bool = False

    # Component configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Additional settings
    data_dir: str = "./data"
    temp_dir: str = "./tmp"
    upload_max_size: int = 100 * 1024 * 1024  # 100MB

    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Ensure directories exist
        Path(self.data_dir).mkdir(exist_ok=True)
        Path(self.temp_dir).mkdir(exist_ok=True)

        # Validate configuration
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration settings."""
        if self.environment == Environment.PRODUCTION:
            if self.auth.secret_key == "dev-secret-key-change-in-production":
                raise ValueError("Must set secure secret key in production")

            if self.api.debug:
                raise ValueError("Debug mode must be disabled in production")

            if self.database.echo_sql:
                raise ValueError("SQL echo must be disabled in production")

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == Environment.TESTING

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment.value,
            "debug_mode": self.debug_mode,
            "database": {
                "url": self.database.url,
                "pool_size": self.database.pool_size,
                "pool_timeout": self.database.pool_timeout,
                "echo_sql": self.database.echo_sql,
                "migrate_on_startup": self.database.migrate_on_startup,
            },
            "auth": {
                "algorithm": self.auth.algorithm,
                "token_expiry_minutes": self.auth.token_expiry_minutes,
                "password_min_length": self.auth.password_min_length,
                "max_login_attempts": self.auth.max_login_attempts,
                "lockout_duration_minutes": self.auth.lockout_duration_minutes,
            },
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "debug": self.api.debug,
                "reload": self.api.reload,
                "workers": self.api.workers,
                "allowed_origins": self.api.allowed_origins,
                "cors_credentials": self.api.cors_credentials,
                "request_timeout": self.api.request_timeout,
                "rate_limit_enabled": self.api.rate_limit_enabled,
                "rate_limit_requests": self.api.rate_limit_requests,
                "rate_limit_window_minutes": self.api.rate_limit_window_minutes,
            },
            "search": {
                "vector_dimension": self.search.vector_dimension,
                "similarity_threshold": self.search.similarity_threshold,
                "max_results": self.search.max_results,
                "cache_size": self.search.cache_size,
                "index_batch_size": self.search.index_batch_size,
                "embedding_model": self.search.embedding_model,
            },
            "logging": {
                "level": self.logging.level.value,
                "format": self.logging.format,
                "file_path": self.logging.file_path,
                "max_file_size": self.logging.max_file_size,
                "backup_count": self.logging.backup_count,
                "console_output": self.logging.console_output,
            },
            "data_dir": self.data_dir,
            "temp_dir": self.temp_dir,
            "upload_max_size": self.upload_max_size,
        }


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""

    pass


class ConfigLoader:
    """Configuration loading and management functionality."""

    def __init__(self):
        """Initialize configuration loader."""
        self.env_prefix = "CIDX_"

    def load_configuration(
        self, config_path: Optional[Union[str, Path]] = None
    ) -> AppConfig:
        """
        Load configuration from multiple sources.

        Args:
            config_path: Optional path to configuration file

        Returns:
            Loaded application configuration
        """
        # Start with default configuration
        config_data = {}

        # Load from configuration file if provided
        if config_path:
            file_config = self._load_config_file(config_path)
            config_data.update(file_config)

        # Load from environment variables (highest priority)
        env_config = self._load_env_config()
        config_data.update(env_config)

        # Create configuration object
        try:
            return self._create_config_object(config_data)
        except Exception as e:
            raise ConfigurationError(f"Failed to create configuration: {e}")

    def _load_config_file(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from JSON/YAML file."""
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            if config_path.suffix.lower() == ".json":
                with open(config_path, "r") as f:
                    return json.load(f)
            elif config_path.suffix.lower() in [".yml", ".yaml"]:
                try:
                    import yaml  # type: ignore

                    with open(config_path, "r") as f:
                        return yaml.safe_load(f)
                except ImportError:
                    raise ConfigurationError(
                        "PyYAML is required for YAML configuration files"
                    )
            else:
                raise ConfigurationError(
                    f"Unsupported configuration file format: {config_path.suffix}"
                )

        except (json.JSONDecodeError, Exception) as e:
            raise ConfigurationError(f"Failed to parse configuration file: {e}")

    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        env_config = {}

        # Map environment variables to configuration structure
        env_mappings = {
            f"{self.env_prefix}APP_NAME": "app_name",
            f"{self.env_prefix}APP_VERSION": "app_version",
            f"{self.env_prefix}ENVIRONMENT": "environment",
            f"{self.env_prefix}DEBUG": "debug_mode",
            # Database settings
            f"{self.env_prefix}DATABASE_URL": "database.url",
            f"{self.env_prefix}DATABASE_POOL_SIZE": "database.pool_size",
            f"{self.env_prefix}DATABASE_ECHO_SQL": "database.echo_sql",
            # Auth settings
            f"{self.env_prefix}SECRET_KEY": "auth.secret_key",
            f"{self.env_prefix}TOKEN_EXPIRY": "auth.token_expiry_minutes",
            f"{self.env_prefix}PASSWORD_MIN_LENGTH": "auth.password_min_length",
            # API settings
            f"{self.env_prefix}API_HOST": "api.host",
            f"{self.env_prefix}API_PORT": "api.port",
            f"{self.env_prefix}API_DEBUG": "api.debug",
            f"{self.env_prefix}API_WORKERS": "api.workers",
            # Search settings
            f"{self.env_prefix}VECTOR_DIMENSION": "search.vector_dimension",
            f"{self.env_prefix}SIMILARITY_THRESHOLD": "search.similarity_threshold",
            f"{self.env_prefix}MAX_RESULTS": "search.max_results",
            # Logging settings
            f"{self.env_prefix}LOG_LEVEL": "logging.level",
            f"{self.env_prefix}LOG_FILE": "logging.file_path",
            # Directory settings
            f"{self.env_prefix}DATA_DIR": "data_dir",
            f"{self.env_prefix}TEMP_DIR": "temp_dir",
        }

        for env_var, config_key in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert value to appropriate type
                converted_value = self._convert_env_value(env_value)
                self._set_nested_config(env_config, config_key, converted_value)

        return env_config

    def _convert_env_value(self, value: str) -> Union[str, int, float, bool]:
        """Convert environment variable string to appropriate type."""
        # Boolean conversion
        if value.lower() in ["true", "1", "yes", "on"]:
            return True
        elif value.lower() in ["false", "0", "no", "off"]:
            return False

        # Number conversion
        try:
            if "." in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass

        # Return as string
        return value

    def _set_nested_config(self, config: Dict[str, Any], key: str, value: Any) -> None:
        """Set nested configuration value using dot notation."""
        keys = key.split(".")
        current = config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def _create_config_object(self, config_data: Dict[str, Any]) -> AppConfig:
        """Create AppConfig object from configuration data."""
        # Create nested configuration objects
        database_config = DatabaseConfig()
        auth_config = AuthConfig()
        api_config = ApiConfig()
        search_config = SearchConfig()
        logging_config = LoggingConfig()

        # Update configurations with provided data
        if "database" in config_data:
            self._update_dataclass(database_config, config_data["database"])

        if "auth" in config_data:
            self._update_dataclass(auth_config, config_data["auth"])

        if "api" in config_data:
            self._update_dataclass(api_config, config_data["api"])

        if "search" in config_data:
            self._update_dataclass(search_config, config_data["search"])

        if "logging" in config_data:
            self._update_dataclass(logging_config, config_data["logging"])

        # Create main configuration
        app_config = AppConfig(
            database=database_config,
            auth=auth_config,
            api=api_config,
            search=search_config,
            logging=logging_config,
        )

        # Update main config fields
        main_fields = [
            "app_name",
            "app_version",
            "environment",
            "debug_mode",
            "data_dir",
            "temp_dir",
            "upload_max_size",
        ]

        for config_field in main_fields:
            if config_field in config_data:
                if config_field == "environment":
                    setattr(
                        app_config, config_field, Environment(config_data[config_field])
                    )
                else:
                    setattr(app_config, config_field, config_data[config_field])

        return app_config

    def _update_dataclass(self, obj: Any, data: Dict[str, Any]) -> None:
        """Update dataclass object with dictionary data."""
        for key, value in data.items():
            if hasattr(obj, key):
                current_value = getattr(obj, key)

                # Handle enum fields
                if hasattr(current_value, "__class__") and issubclass(
                    current_value.__class__, Enum
                ):
                    if isinstance(value, str):
                        enum_class = current_value.__class__
                        setattr(obj, key, enum_class(value))
                    else:
                        setattr(obj, key, value)
                else:
                    setattr(obj, key, value)


# Global configuration loader instance
_config_loader = ConfigLoader()


def load_configuration(config_path: Optional[Union[str, Path]] = None) -> AppConfig:
    """
    Load application configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Application configuration object
    """
    return _config_loader.load_configuration(config_path)


def create_test_config() -> AppConfig:
    """Create configuration optimized for testing."""
    config = AppConfig(
        environment=Environment.TESTING,
        debug_mode=True,
        database=DatabaseConfig(
            url="sqlite:///:memory:", echo_sql=False, migrate_on_startup=True
        ),
        auth=AuthConfig(
            secret_key="test-secret-key",
            token_expiry_minutes=5,  # Short expiry for testing
        ),
        api=ApiConfig(
            debug=True,
            port=0,  # Random available port
            rate_limit_enabled=False,  # Disable for testing
        ),
        logging=LoggingConfig(
            level=LogLevel.DEBUG,
            console_output=True,
            file_path=None,  # No file logging in tests
        ),
    )

    return config


def create_production_config() -> AppConfig:
    """Create secure production configuration template."""
    config = AppConfig(
        environment=Environment.PRODUCTION,
        debug_mode=False,
        database=DatabaseConfig(
            url="postgresql://user:pass@localhost/cidx_prod",
            pool_size=20,
            echo_sql=False,
            migrate_on_startup=False,  # Manual migrations in production
        ),
        auth=AuthConfig(
            secret_key="CHANGE-THIS-IN-PRODUCTION",
            token_expiry_minutes=30,
            password_min_length=12,
            max_login_attempts=3,
            lockout_duration_minutes=30,
        ),
        api=ApiConfig(
            host="0.0.0.0",
            port=8000,
            debug=False,
            reload=False,
            workers=4,
            allowed_origins=["https://yourdomain.com"],
            rate_limit_enabled=True,
            rate_limit_requests=50,
            rate_limit_window_minutes=1,
        ),
        logging=LoggingConfig(
            level=LogLevel.INFO, file_path="/var/log/cidx/app.log", console_output=False
        ),
    )

    return config
