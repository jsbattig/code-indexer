"""
Configuration management for re-indexing decision engine.

Provides configuration classes for managing re-indexing thresholds,
triggers, and behavior customization.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Set, Optional, Callable, Union


@dataclass
class ReindexingConfig:
    """Configuration for re-indexing decision engine."""

    # Trigger thresholds
    change_percentage_threshold: float = 0.3  # 30%
    accuracy_threshold: float = 0.8  # 80%
    max_index_age_days: int = 30

    # Feature toggles
    enable_structural_change_detection: bool = True
    enable_config_change_detection: bool = True
    enable_corruption_detection: bool = True
    enable_periodic_reindex: bool = True

    # Performance settings
    batch_size: int = 100
    max_analysis_time_seconds: int = 300  # 5 minutes
    parallel_analysis: bool = True
    max_memory_usage_mb: int = 1024  # 1GB

    # File patterns
    config_file_patterns: Set[str] = field(
        default_factory=lambda: {
            ".cidx-config",
            ".gitignore",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "requirements-dev.txt",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "tsconfig.json",
            "Pipfile",
            "Pipfile.lock",
            ".env",
            ".env.example",
            "tox.ini",
            "pytest.ini",
            "setup.cfg",
            "Makefile",
            "CMakeLists.txt",
        }
    )

    # Structural change detection
    structural_change_threshold: int = 5  # Number of directories added/removed
    max_file_moves_threshold: int = 10  # Number of file moves
    structural_indicators: Set[str] = field(
        default_factory=lambda: {
            "__init__.py",
            "index.js",
            "main.py",
            "app.py",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
        }
    )

    def __post_init__(self):
        """Validate configuration values."""
        self._validate()

    def _validate(self):
        """Validate configuration values."""
        if not 0.0 <= self.change_percentage_threshold <= 1.0:
            raise ValueError(
                f"Change percentage threshold must be between 0.0 and 1.0, "
                f"got {self.change_percentage_threshold}"
            )

        if not 0.0 <= self.accuracy_threshold <= 1.0:
            raise ValueError(
                f"Accuracy threshold must be between 0.0 and 1.0, "
                f"got {self.accuracy_threshold}"
            )

        if self.max_index_age_days < 0:
            raise ValueError(
                f"Max index age days cannot be negative, got {self.max_index_age_days}"
            )

        if self.batch_size <= 0:
            raise ValueError(f"Batch size must be positive, got {self.batch_size}")

        if self.max_analysis_time_seconds <= 0:
            raise ValueError(
                f"Max analysis time must be positive, got {self.max_analysis_time_seconds}"
            )

        if self.max_memory_usage_mb <= 0:
            raise ValueError(
                f"Max memory usage must be positive, got {self.max_memory_usage_mb}"
            )

    @classmethod
    def from_dict(cls, config_data: Dict[str, Any]) -> "ReindexingConfig":
        """Create configuration from dictionary."""
        # Handle set fields specially
        instance_data = config_data.copy()

        # Convert lists to sets for set fields
        if "config_file_patterns" in instance_data:
            instance_data["config_file_patterns"] = set(
                instance_data["config_file_patterns"]
            )

        if "structural_indicators" in instance_data:
            instance_data["structural_indicators"] = set(
                instance_data["structural_indicators"]
            )

        # Filter to only known fields
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in instance_data.items() if k in field_names}

        return cls(**filtered_data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        result = {}

        for field_name, field_def in self.__dataclass_fields__.items():
            value = getattr(self, field_name)

            # Convert sets to lists for JSON serialization
            if isinstance(value, set):
                value = list(value)

            result[field_name] = value

        return result

    @classmethod
    def from_cidx_config(cls, cidx_config) -> "ReindexingConfig":
        """Create configuration from CIDX configuration object."""
        # Extract reindexing section if it exists
        if hasattr(cidx_config, "reindexing") and cidx_config.reindexing:
            reindexing_data = cidx_config.reindexing
            if isinstance(reindexing_data, dict):
                return cls.from_dict(reindexing_data)
            else:
                # Convert object to dict
                reindexing_dict = {}
                for attr in dir(reindexing_data):
                    if not attr.startswith("_"):
                        reindexing_dict[attr] = getattr(reindexing_data, attr)
                return cls.from_dict(reindexing_dict)

        # No reindexing section - use defaults
        return cls()

    @classmethod
    def from_environment(cls) -> "ReindexingConfig":
        """Create configuration from environment variables."""
        env_mapping: Dict[str, tuple[str, Callable[[str], Union[float, int, bool]]]] = {
            "CIDX_REINDEX_CHANGE_THRESHOLD": ("change_percentage_threshold", float),
            "CIDX_REINDEX_ACCURACY_THRESHOLD": ("accuracy_threshold", float),
            "CIDX_REINDEX_MAX_AGE_DAYS": ("max_index_age_days", int),
            "CIDX_REINDEX_BATCH_SIZE": ("batch_size", int),
            "CIDX_REINDEX_MAX_ANALYSIS_TIME": ("max_analysis_time_seconds", int),
            "CIDX_REINDEX_MAX_MEMORY_MB": ("max_memory_usage_mb", int),
            "CIDX_REINDEX_ENABLE_STRUCTURAL": (
                "enable_structural_change_detection",
                cls._parse_bool,
            ),
            "CIDX_REINDEX_ENABLE_CONFIG": (
                "enable_config_change_detection",
                cls._parse_bool,
            ),
            "CIDX_REINDEX_ENABLE_CORRUPTION": (
                "enable_corruption_detection",
                cls._parse_bool,
            ),
            "CIDX_REINDEX_ENABLE_PERIODIC": (
                "enable_periodic_reindex",
                cls._parse_bool,
            ),
            "CIDX_REINDEX_PARALLEL": ("parallel_analysis", cls._parse_bool),
        }

        config_data = {}

        for env_var, (config_key, converter) in env_mapping.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                try:
                    config_data[config_key] = converter(env_value)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid value for {env_var}: {env_value}. Error: {e}"
                    )

        return cls.from_dict(config_data)

    @classmethod
    def from_cidx_config_with_env_overrides(cls, cidx_config) -> "ReindexingConfig":
        """Create configuration from CIDX config with environment variable overrides."""
        # Start with CIDX config
        config = cls.from_cidx_config(cidx_config)

        # Apply environment overrides
        env_config = cls.from_environment()
        env_dict = env_config.to_dict()

        # Only override non-default values from environment
        default_dict = cls().to_dict()

        for key, env_value in env_dict.items():
            if env_value != default_dict[key]:  # Environment has non-default value
                setattr(config, key, env_value)

        return config

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse boolean value from string."""
        if isinstance(value, bool):
            return value

        lower_value = str(value).lower()
        if lower_value in ("true", "1", "yes", "on", "enabled"):
            return True
        elif lower_value in ("false", "0", "no", "off", "disabled"):
            return False
        else:
            raise ValueError(f"Invalid boolean value: {value}")

    def is_config_file(self, file_path: str) -> bool:
        """Check if a file path matches configuration file patterns."""
        import logging
        import pathspec
        from pathlib import Path

        logger = logging.getLogger(__name__)
        file_name = Path(file_path).name

        # Direct match
        if file_name in self.config_file_patterns:
            return True

        # Pattern matching using pathspec (gitignore-style matching)
        # This correctly handles ** as "zero or more directories"
        for pattern in self.config_file_patterns:
            try:
                spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
                if spec.match_file(file_name):
                    return True
            except Exception as e:
                # Log pattern parsing errors for debugging
                logger.debug(f"Pattern '{pattern}' failed to parse: {e}", extra={"correlation_id": get_correlation_id()})
                # Skip pattern on parse error
                continue

        return False

    def is_structural_indicator(self, file_path: str) -> bool:
        """Check if a file path indicates structural changes."""
        from pathlib import Path

        file_name = Path(file_path).name
        return file_name in self.structural_indicators

    def estimate_reindex_time_minutes(
        self,
        total_files: int,
        repository_size_mb: float,
        previous_time_minutes: Optional[float] = None,
    ) -> int:
        """Estimate time for full re-indexing based on repository characteristics."""
        # Base estimates per file and per MB
        time_per_file_seconds = 0.1  # 100ms per file
        time_per_mb_seconds = 2.0  # 2 seconds per MB

        # Calculate base time
        file_time = total_files * time_per_file_seconds
        size_time = repository_size_mb * time_per_mb_seconds
        base_time_seconds = max(file_time, size_time)

        # Apply adjustments
        if self.parallel_analysis:
            base_time_seconds *= 0.6  # 40% reduction with parallel processing

        # Use historical data if available
        if previous_time_minutes:
            # Weight 70% historical, 30% calculated
            historical_seconds = previous_time_minutes * 60
            base_time_seconds = (historical_seconds * 0.7) + (base_time_seconds * 0.3)

        # Convert to minutes and add buffer
        estimated_minutes = int((base_time_seconds / 60) * 1.2)  # 20% buffer

        return max(1, estimated_minutes)  # At least 1 minute
