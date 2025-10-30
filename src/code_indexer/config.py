"""Configuration management for Code Indexer."""

import json
import logging
import yaml  # type: ignore
from pathlib import Path
from typing import List, Optional, Any, Literal, Tuple, Dict

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class OllamaConfig(BaseModel):
    """Configuration for Ollama service.

    Environment variable references:
    - Ollama FAQ: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
    """

    host: str = Field(default="http://localhost:11434", description="Ollama API host")
    model: str = Field(default="nomic-embed-text", description="Embedding model name")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    # OLLAMA_NUM_PARALLEL: Default 4 or 1 based on memory
    num_parallel: int = Field(default=1, description="Number of parallel request slots")
    # OLLAMA_MAX_LOADED_MODELS: Default 3×GPU count or 3 for CPU
    max_loaded_models: int = Field(
        default=1, description="Maximum number of models to keep loaded"
    )
    # OLLAMA_MAX_QUEUE: Default 512
    max_queue: int = Field(default=512, description="Maximum request queue size")


class VoyageAIConfig(BaseModel):
    """Configuration for VoyageAI embedding service.

    VoyageAI provides high-quality embeddings optimized for code and text.
    API documentation: https://docs.voyageai.com/
    """

    # API configuration - API key should be set via VOYAGE_API_KEY environment variable
    api_endpoint: str = Field(
        default="https://api.voyageai.com/v1/embeddings",
        description="VoyageAI API endpoint URL",
    )
    model: str = Field(
        default="voyage-code-3",
        description="VoyageAI embedding model name (e.g., voyage-code-3, voyage-large-2, voyage-2)",
    )
    timeout: int = Field(default=30, description="Request timeout in seconds")

    # Parallel processing configuration
    parallel_requests: int = Field(
        default=8, description="Number of concurrent requests to VoyageAI API"
    )
    batch_size: int = Field(
        default=128,
        description="Maximum number of texts to send in a single batch request",
    )

    # Retry configuration for server errors and transient failures
    max_retries: int = Field(
        default=3, description="Maximum number of retries for failed requests"
    )
    retry_delay: float = Field(
        default=1.0, description="Initial delay between retries in seconds"
    )
    exponential_backoff: bool = Field(
        default=True, description="Use exponential backoff for retries"
    )


class QdrantConfig(BaseModel):
    """Configuration for Qdrant vector database."""

    host: str = Field(default="http://localhost:6333", description="Qdrant API host")
    collection_base_name: str = Field(
        default="code_index",
        description="Base name for collections (only dynamic part is embedding model)",
    )
    vector_size: int = Field(
        default=768,
        description="Vector dimension size (deprecated - auto-detected from provider)",
    )
    # Collection naming: base_name + model_slug (no provider, no project hash)

    # HNSW search parameters - Phase 1: Search-time optimization
    hnsw_ef: int = Field(
        default=64,
        description="HNSW search parameter for accuracy vs speed tradeoff (higher = more accurate, slower)",
    )

    # HNSW collection parameters - Phase 2: Collection-time optimization
    hnsw_ef_construct: int = Field(
        default=200,
        description="HNSW index construction parameter (higher = better index quality, slower indexing)",
    )
    hnsw_m: int = Field(
        default=32,
        description="HNSW connectivity parameter (higher = better connectivity for large datasets, more memory)",
    )

    # Segment size configuration - Git-friendly storage optimization
    max_segment_size_kb: int = Field(
        default=102400,
        description="Maximum segment size in KB (default: 100MB for optimal performance while staying Git-friendly)",
    )

    # Payload index configuration
    enable_payload_indexes: bool = Field(
        default=True,
        description="Enable payload indexes for faster filtering (uses 100-300MB additional RAM)",
    )

    payload_indexes: List[Tuple[str, str]] = Field(
        default=[
            ("type", "keyword"),
            ("path", "text"),
            ("git_branch", "keyword"),
            ("file_mtime", "integer"),
            ("hidden_branches", "keyword"),
            ("language", "keyword"),
            (
                "embedding_model",
                "keyword",
            ),  # Required for model-specific filtering in non-git projects
        ],
        description="List of (field_name, field_schema) tuples for payload indexes",
    )

    @field_validator("max_segment_size_kb")
    @classmethod
    def validate_segment_size(cls, v: int) -> int:
        """Validate segment size is positive."""
        if v <= 0:
            raise ValueError("Segment size must be positive")
        return v

    @field_validator("payload_indexes")
    @classmethod
    def validate_payload_indexes(
        cls, v: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Validate payload index field schemas."""
        valid_schemas = {"keyword", "text", "integer", "geo", "bool"}
        for field_name, field_schema in v:
            if field_schema not in valid_schemas:
                raise ValueError(
                    f"Invalid field_schema '{field_schema}' for field '{field_name}'"
                )
        return v


class IndexingConfig(BaseModel):
    """Configuration for indexing behavior."""

    chunk_size: int = Field(default=1500, description="Text chunk size in characters")
    chunk_overlap: int = Field(default=150, description="Overlap between chunks")
    max_file_size: int = Field(
        default=1048576, description="Maximum file size to index"
    )
    index_comments: bool = Field(
        default=True, description="Include comments in indexing"
    )


class TimeoutsConfig(BaseModel):
    """Configuration for various timeout settings."""

    service_startup: int = Field(
        default=240, description="Service startup timeout in seconds"
    )
    service_shutdown: int = Field(
        default=30, description="Service shutdown timeout in seconds"
    )
    port_release: int = Field(default=15, description="Port release timeout in seconds")
    cleanup_validation: int = Field(
        default=30, description="Cleanup validation timeout in seconds"
    )
    health_check: int = Field(
        default=180, description="Health check timeout in seconds"
    )
    data_cleaner_startup: int = Field(
        default=180, description="Data cleaner startup timeout in seconds"
    )


class PollingConfig(BaseModel):
    """Configuration for condition polling behavior."""

    initial_interval: float = Field(
        default=0.5, description="Initial polling interval in seconds"
    )
    backoff_factor: float = Field(
        default=1.2, description="Exponential backoff multiplier"
    )
    max_interval: float = Field(
        default=2.0, description="Maximum polling interval in seconds"
    )


class ProjectContainersConfig(BaseModel):
    """Configuration for project-specific container names."""

    project_hash: Optional[str] = Field(
        default=None, description="Hash derived from project path"
    )
    qdrant_name: Optional[str] = Field(
        default=None, description="Qdrant container name"
    )
    ollama_name: Optional[str] = Field(
        default=None, description="Ollama container name"
    )
    data_cleaner_name: Optional[str] = Field(
        default=None, description="Data cleaner container name"
    )


class ProjectPortsConfig(BaseModel):
    """Configuration for project-specific port assignments."""

    qdrant_port: Optional[int] = Field(default=None, description="Qdrant service port")
    ollama_port: Optional[int] = Field(default=None, description="Ollama service port")
    data_cleaner_port: Optional[int] = Field(
        default=None, description="Data cleaner service port"
    )


class OverrideConfig(BaseModel):
    """Override configuration for file inclusion/exclusion rules."""

    add_extensions: List[str] = Field(
        default_factory=list,
        description="Additional file extensions to index (beyond config defaults)",
    )
    remove_extensions: List[str] = Field(
        default_factory=list,
        description="File extensions to exclude (overrides config whitelist)",
    )
    add_exclude_dirs: List[str] = Field(
        default_factory=list,
        description="Additional directories to exclude from indexing",
    )
    add_include_dirs: List[str] = Field(
        default_factory=list, description="Additional directories to force include"
    )
    force_include_patterns: List[str] = Field(
        default_factory=list,
        description="Force include files matching these patterns (overrides gitignore/config)",
    )
    force_exclude_patterns: List[str] = Field(
        default_factory=list,
        description="Force exclude files matching these patterns (absolute exclusion)",
    )


class AutoRecoveryConfig(BaseModel):
    """Configuration for automatic recovery system."""

    enabled: bool = Field(default=True, description="Enable automatic recovery")
    max_recovery_attempts: int = Field(
        default=3, description="Maximum recovery attempts per issue"
    )
    recovery_timeout_minutes: int = Field(
        default=60, description="Recovery timeout in minutes"
    )
    backup_before_full_recovery: bool = Field(
        default=True, description="Create backup before full recovery"
    )
    allow_automatic_full_recovery: bool = Field(
        default=True, description="Allow automatic full recovery"
    )


class VectorStoreConfig(BaseModel):
    """Configuration for vector storage backend.

    Determines which vector storage backend to use:
    - filesystem: Container-free storage using local filesystem
    - qdrant: Container-based storage using Docker/Podman + Qdrant
    """

    provider: Literal["filesystem", "qdrant"] = Field(
        default="filesystem",
        description="Vector storage provider: 'filesystem' for container-free, 'qdrant' for containers",
    )


class DaemonConfig(BaseModel):
    """Configuration for daemon mode (semantic caching daemon)."""

    enabled: bool = Field(default=False, description="Enable daemon mode")
    ttl_minutes: int = Field(
        default=10, description="Cache TTL in minutes (how long to keep indexes in memory)"
    )
    auto_shutdown_on_idle: bool = Field(
        default=True, description="Automatically shutdown daemon when idle"
    )
    max_retries: int = Field(
        default=4, description="Maximum retry attempts for daemon communication"
    )
    retry_delays_ms: List[int] = Field(
        default=[100, 500, 1000, 2000],
        description="Retry delays in milliseconds (exponential backoff)",
    )
    eviction_check_interval_seconds: int = Field(
        default=60, description="How often to check for cache eviction (in seconds)"
    )

    @field_validator("ttl_minutes")
    @classmethod
    def validate_ttl(cls, v: int) -> int:
        """Validate TTL is within reasonable range."""
        if v < 1 or v > 10080:  # 1 week max
            raise ValueError("TTL must be between 1 and 10080 minutes (1 week)")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max retries is reasonable."""
        if v < 0 or v > 10:
            raise ValueError("max_retries must be between 0 and 10")
        return v

    @field_validator("retry_delays_ms")
    @classmethod
    def validate_retry_delays(cls, v: List[int]) -> List[int]:
        """Validate retry delays are positive."""
        if any(d < 0 for d in v):
            raise ValueError("All retry delays must be positive")
        return v


class Config(BaseModel):
    """Main configuration for Code Indexer."""

    # Proxy mode configuration
    proxy_mode: bool = Field(
        default=False,
        description="Enable proxy mode for managing multiple repositories",
    )
    discovered_repos: List[str] = Field(
        default_factory=list,
        description="List of relative paths to discovered repositories in proxy mode",
    )

    codebase_dir: Path = Field(default=Path("."), description="Directory to index")
    file_extensions: List[str] = Field(
        default=[
            "py",
            "js",
            "ts",
            "tsx",
            "java",
            "c",
            "cpp",
            "cs",
            "h",
            "hpp",
            "go",
            "rs",
            "rb",
            "php",
            "pl",
            "pm",
            "pod",
            "t",
            "psgi",
            "sh",
            "bash",
            "html",
            "css",
            "md",
            "json",
            "yaml",
            "yml",
            "toml",
            "sql",
            "swift",
            "kt",
            "kts",
            "scala",
            "dart",
            "vue",
            "jsx",
            "pas",
            "pp",
            "dpr",
            "dpk",
            "inc",
            # Additional language extensions
            "lua",  # Lua
            "xml",  # XML
            "xsd",  # XML Schema
            "xsl",  # XSLT
            "xslt",  # XSLT
            "groovy",  # Groovy
            "gradle",  # Gradle
            "gvy",  # Groovy
            "gy",  # Groovy
            "cxx",  # C++
            "cc",  # C++
            "hxx",  # C++ headers
            "rake",  # Ruby
            "rbw",  # Ruby
            "gemspec",  # Ruby gems
            "htm",  # HTML
            "scss",  # SCSS
            "sass",  # Sass
        ],
        description="File extensions to index",
    )
    exclude_dirs: List[str] = Field(
        default=[
            "node_modules",
            "venv",
            "__pycache__",
            ".git",
            "dist",
            "build",
            "target",
            ".idea",
            ".vscode",
            ".gradle",
            "bin",
            "obj",
            "coverage",
            ".next",
            ".nuxt",
            "dist-*",
            ".code-indexer",
        ],
        description="Directories to exclude from indexing",
    )

    # Embedding provider selection
    embedding_provider: Literal["ollama", "voyage-ai"] = Field(
        default="ollama",
        description="Embedding provider to use: 'ollama' for local Ollama, 'voyage-ai' for VoyageAI API",
    )

    # Vector storage backend selection
    vector_store: Optional[VectorStoreConfig] = Field(
        default=None,
        description="Vector storage backend configuration (default: filesystem)",
    )

    # Provider-specific configurations
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    voyage_ai: VoyageAIConfig = Field(default_factory=VoyageAIConfig)

    # Other service configurations
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)

    # Per-project container configuration
    project_containers: ProjectContainersConfig = Field(
        default_factory=ProjectContainersConfig
    )
    project_ports: ProjectPortsConfig = Field(default_factory=ProjectPortsConfig)

    # Override configuration
    override_config: Optional[OverrideConfig] = Field(
        default=None,
        description="Override configuration for file inclusion/exclusion rules",
    )

    # Auto-recovery configuration
    auto_recovery: Optional[AutoRecoveryConfig] = Field(
        default=None,
        description="Automatic recovery system configuration",
    )

    # Daemon configuration
    daemon: Optional[DaemonConfig] = Field(
        default=None,
        description="Daemon mode configuration for semantic caching",
    )

    @field_validator("codebase_dir", mode="before")
    @classmethod
    def convert_path(cls, v: Any) -> Path:
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        if isinstance(v, Path):
            return v
        raise ValueError(f"Expected str or Path, got {type(v)}")

    @field_validator("file_extensions")
    @classmethod
    def normalize_extensions(cls, v: List[str]) -> List[str]:
        """Remove dots from file extensions."""
        return [ext.lstrip(".") for ext in v]


class ConfigManager:
    """Manages configuration loading, saving, and validation."""

    DEFAULT_CONFIG_PATH = Path(".code-indexer/config.json")

    # Daemon configuration defaults
    DAEMON_DEFAULTS = {
        "enabled": False,
        "ttl_minutes": 10,
        "auto_shutdown_on_idle": True,
        "max_retries": 4,
        "retry_delays_ms": [100, 500, 1000, 2000],
        "eviction_check_interval_seconds": 60,
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None

    def load(self) -> Config:
        """Load configuration from file or create default with dynamic path resolution."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)

                # Ensure absolute path for codebase_dir
                if "codebase_dir" in data:
                    # Convert to absolute path if needed
                    path = Path(data["codebase_dir"])
                    if not path.is_absolute():
                        # If relative, resolve relative to config directory
                        config_dir = self.config_path.parent.parent
                        path = (config_dir / path).resolve()
                    data["codebase_dir"] = str(path)

                self._config = Config(**data)
            except Exception as e:
                raise ValueError(f"Failed to load config from {self.config_path}: {e}")
        else:
            self._config = Config()

        # Try to load override config if available
        if self._config:
            project_root = self._config.codebase_dir
            override_path = _find_override_file(project_root)
            if override_path:
                try:
                    self._config.override_config = _load_override_config(override_path)
                except Exception as e:
                    logger.warning(
                        f"Failed to load override config from {override_path}: {e}"
                    )

        return self._config

    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file."""
        if config is None:
            config = self._config

        if config is None:
            raise ValueError("No configuration to save")

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path serialization with absolute paths
        config_dict = config.model_dump()
        # Store absolute path for clarity and reliability
        config_dict["codebase_dir"] = str(Path(config.codebase_dir).absolute())

        with open(self.config_path, "w") as f:
            json.dump(config_dict, f, indent=2)

    def save_with_documentation(self, config: Optional[Config] = None) -> None:
        """Save configuration with documentation and helpful comments."""
        if config is None:
            config = self._config

        if config is None:
            raise ValueError("No configuration to save")

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path serialization with relative paths
        config_dict = config.model_dump()
        # Store absolute path for clarity and reliability
        config_dict["codebase_dir"] = str(config.codebase_dir.absolute())

        # Create documentation content
        doc_content = """# Code Indexer Configuration Guide

This directory contains your project's code indexing configuration.

## Quick Start

1. **Review** the `config.json` file below
2. **Customize** the settings (especially `exclude_dirs`)
3. **Run** `code-indexer index` to start indexing

## Configuration File: config.json

Edit `config.json` to customize how your codebase is indexed.

### Key Settings

#### `exclude_dirs` - Folders to Skip
Add directory names to exclude from indexing:
```json
"exclude_dirs": [
  "node_modules", "dist", "build",     // Build outputs
  "logs", "cache", "tmp",              // Temporary files  
  "coverage", ".pytest_cache",         // Test artifacts
  "vendor", "third_party",             // Dependencies
  "my_custom_folder"                   // Your custom exclusions
]
```

#### `file_extensions` - File Types to Index
Specify which file types to include:
```json
"file_extensions": ["py", "js", "ts", "java", "cpp", "go", "rs", "md"]
```

#### `max_file_size` - Size Limit (bytes)
Files larger than this are skipped (default: 1MB):
```json
"max_file_size": 2097152  // 2MB limit
```

#### `chunk_size` - Text Processing Size
How text is split for AI processing:
- Larger = more context, slower processing
- Smaller = less context, faster processing
```json
"chunk_size": 1500  // 1500 characters (default)
```

## Performance Configuration

### Ollama Performance Control
Configure request handling and resource usage for the AI embedding model:

```json
"ollama": {
  "host": "http://localhost:11434",
  "model": "nomic-embed-text",
  "timeout": 30,
  "num_parallel": 1,            // Parallel request slots (default: 1)
  "max_loaded_models": 1,       // Max models in memory (default: 1)
  "max_queue": 512              // Max request queue size (default: 512)
}
```

#### Ollama Server Settings
Configuration maps to Ollama environment variables. See: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server

- **`num_parallel`** (→ OLLAMA_NUM_PARALLEL): Maximum concurrent requests Ollama server accepts
  - `1`: Server processes one request at a time
  - `2-4`: Server can handle multiple simultaneous requests from different clients
  - **Default in Ollama**: 4 or 1 based on available memory
  - **Note**: Code-indexer processes files sequentially, so this mainly benefits other clients using the same Ollama instance
- **`max_loaded_models`** (→ OLLAMA_MAX_LOADED_MODELS): Maximum models Ollama keeps loaded in memory
  - `1`: Single model (code-indexer uses one embedding model)
  - `2+`: Multiple models (uses more RAM, not needed for code-indexer)  
  - **Default in Ollama**: 3×GPU count or 3 for CPU
- **`max_queue`** (→ OLLAMA_MAX_QUEUE): Maximum requests Ollama queues when busy
  - `512`: Default queue size
  - Higher values allow more requests to wait when server is at capacity
  - **Default in Ollama**: 512

#### Processing Architecture
Code-indexer processes files sequentially: reads file → chunks text → generates embedding → stores in Qdrant → next file. CPU thread allocation is handled automatically by Ollama and cannot be configured.

#### Configuration Examples
```json
// Single-user development (default)
"ollama": { "num_parallel": 1, "max_queue": 256 }

// Shared Ollama instance (multiple clients)
"ollama": { "num_parallel": 4, "max_queue": 512 }
```

## Embedding Providers

### Ollama (Local)
Uses local AI models for privacy and no API costs:
```json
"embedding_provider": "ollama",
"qdrant": { "vector_size": 768 }  // Ollama models use 768 dimensions
```

### VoyageAI (Cloud, Default)
Uses VoyageAI API for high-quality code embeddings:
```json
"embedding_provider": "voyage-ai",
"qdrant": { "vector_size": 1024 },  // VoyageAI models use 1024 dimensions
"voyage_ai": {
  "model": "voyage-code-3",
  "parallel_requests": 8,
  "tokens_per_minute": 1000000  // Set to avoid rate limiting
}
```

**IMPORTANT**: When switching embedding providers:
1. **Vector size must match**: Ollama = 768, VoyageAI = 1024
2. **Clear existing data**: Run `code-indexer clean --remove-data`
3. **Re-index**: Run `code-indexer index --clear`

**VoyageAI Setup**:
1. Get API key from https://www.voyageai.com/
2. Set environment variable: `export VOYAGE_API_KEY="your_key"`
3. For persistence, add to ~/.bashrc: `echo 'export VOYAGE_API_KEY="your_key"' >> ~/.bashrc`

## Additional Exclusions

The system also respects `.gitignore` patterns automatically.
You can use `.gitignore` for file-level exclusions:

```gitignore
*.log
*.tmp
temp_files/
generated_*
```

## After Making Changes

Run this command to apply your configuration changes:
```bash
code-indexer index --clear
```

## Need Help?

- Run `code-indexer --help` for command documentation
- Run `code-indexer COMMAND --help` for specific command help
- Check the main documentation for additional configuration

"""

        # Write clean JSON config (no comments to avoid parsing issues)
        with open(self.config_path, "w") as f:
            json.dump(config_dict, f, indent=2, sort_keys=True)

        # Create a separate README file with documentation
        readme_path = self.config_path.parent / "README.md"
        with open(readme_path, "w") as f:
            f.write(doc_content)

    def get_config(self) -> Config:
        """Get current configuration, loading if necessary."""
        if self._config is None:
            self.load()
        if self._config is None:
            raise RuntimeError("Failed to load configuration")
        return self._config

    def create_default_config(self, codebase_dir: Path = Path(".")) -> Config:
        """Create a default configuration for the given directory."""
        config = Config(codebase_dir=codebase_dir)
        self._config = config
        self.save()
        return config

    def update_config(self, **kwargs: Any) -> Config:
        """Update configuration with new values."""
        config = self.get_config()

        # Create new config with updated values
        config_dict = config.model_dump()
        config_dict.update(kwargs)

        new_config = Config(**config_dict)
        self._config = new_config
        self.save()
        return new_config

    @staticmethod
    def find_config_path(start_dir: Optional[Path] = None) -> Optional[Path]:
        """Find .code-indexer/config.json by walking up the directory tree.

        Args:
            start_dir: Directory to start searching from (default: current directory)

        Returns:
            Path to config.json if found, None otherwise
        """
        # Safely get current working directory with fallback
        if start_dir:
            current = start_dir
        else:
            try:
                current = Path.cwd()
            except (FileNotFoundError, OSError):
                # Working directory deleted - use temp directory as fallback
                import tempfile

                current = Path(tempfile.gettempdir())

        # Walk up the directory tree looking for .code-indexer/config.json
        # CRITICAL: Must stop at first match to support nested projects
        search_paths = [current] + list(current.parents)
        for path in search_paths:
            config_path = path / ".code-indexer" / "config.json"
            if config_path.exists():
                # DEFENSIVE: Ensure we return immediately at first match
                # This prevents any issues with continued searching
                return config_path

        return None

    @classmethod
    def detect_mode(
        cls, start_path: Optional[Path] = None
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Detect configuration mode (regular/proxy) by walking up directory tree.

        This method implements automatic proxy mode detection by searching for
        .code-indexer/config.json files and checking the proxy_mode flag.

        Args:
            start_path: Directory to start searching from (default: current directory)

        Returns:
            Tuple of (config_root_path, mode) where:
            - config_root_path: Path to directory containing .code-indexer/, or None
            - mode: "proxy" if proxy_mode is true, "regular" if false/missing, None if no config

        Raises:
            ValueError: If configuration file is malformed or cannot be parsed
            PermissionError: If configuration file cannot be read due to permissions
        """
        # Get starting directory
        if start_path:
            current = Path(start_path).resolve()
        else:
            try:
                current = Path.cwd()
            except (FileNotFoundError, OSError):
                # Working directory deleted - use temp directory as fallback
                import tempfile

                current = Path(tempfile.gettempdir())

        # Walk up the directory tree looking for .code-indexer/config.json
        while current != current.parent:
            config_dir = current / ".code-indexer"
            config_file = config_dir / "config.json"

            if config_file.exists():
                # Check if it's actually a file (not a directory)
                if not config_file.is_file():
                    # Skip and continue searching
                    current = current.parent
                    continue

                try:
                    with open(config_file, "r") as f:
                        config_data = json.load(f)

                    # Check proxy_mode flag
                    proxy_mode = config_data.get("proxy_mode", False)

                    if proxy_mode:
                        return current, "proxy"
                    else:
                        return current, "regular"

                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON in configuration file {config_file}: {e}"
                    )
                except PermissionError as e:
                    raise PermissionError(
                        f"Cannot read configuration file {config_file}: {e}"
                    )
                except OSError:
                    # Handle other OS errors (broken symlinks, etc.)
                    if not config_file.exists():
                        # File disappeared during processing (broken symlink, etc.)
                        current = current.parent
                        continue
                    raise

            current = current.parent

        # No config found
        return None, None

    @classmethod
    def create_with_backtrack(cls, start_dir: Optional[Path] = None) -> "ConfigManager":
        """Create ConfigManager by finding config through directory backtracking.

        Args:
            start_dir: Directory to start searching from (default: current directory)

        Returns:
            ConfigManager instance with found config path or default path
        """
        # Check for CODEBASE_DIR environment variable override
        import os

        codebase_dir_env = os.getenv("CODEBASE_DIR")
        if codebase_dir_env:
            # Environment variable override - use that directory for config discovery
            override_dir = Path(codebase_dir_env).resolve()
            logger.debug(
                f"Using CODEBASE_DIR environment variable override: {override_dir}"
            )
            override_config_path = override_dir / ".code-indexer" / "config.json"
            return cls(override_config_path)

        # CRITICAL: Use find_config_path which stops at first match
        config_path = cls.find_config_path(start_dir)
        if config_path is None:
            # If no config found, use default path from the start directory
            if start_dir:
                start = start_dir
            else:
                try:
                    start = Path.cwd()
                except (FileNotFoundError, OSError):
                    # Working directory deleted - use temp directory as fallback
                    import tempfile

                    start = Path(tempfile.gettempdir())
            config_path = start / ".code-indexer" / "config.json"

        # DEFENSIVE: Ensure we always return a ConfigManager with the first found config
        return cls(config_path)

    def enable_daemon(self, ttl_minutes: int = 10) -> None:
        """Enable daemon mode for repository.

        Args:
            ttl_minutes: Cache TTL in minutes (default: 10)

        Raises:
            ValueError: If ttl_minutes is invalid
        """
        # Validate TTL before creating config
        if ttl_minutes < 1:
            raise ValueError("TTL must be positive")
        if ttl_minutes > 10080:
            raise ValueError("TTL must be between 1 and 10080 minutes")

        config = self.get_config()

        # Create daemon config with specified TTL
        daemon_config_dict = {**self.DAEMON_DEFAULTS, "enabled": True, "ttl_minutes": ttl_minutes}

        # Update config with daemon configuration
        config.daemon = DaemonConfig(**daemon_config_dict)

        # Save configuration
        self.save()

    def disable_daemon(self) -> None:
        """Disable daemon mode for repository."""
        config = self.get_config()

        # If no daemon config exists, create one with enabled=False
        if config.daemon is None:
            config.daemon = DaemonConfig(**{**self.DAEMON_DEFAULTS, "enabled": False})
        else:
            # Just update the enabled flag, preserve other settings
            daemon_dict = config.daemon.model_dump()
            daemon_dict["enabled"] = False
            config.daemon = DaemonConfig(**daemon_dict)

        self.save()

    def update_daemon_ttl(self, ttl_minutes: int) -> None:
        """Update daemon cache TTL.

        Args:
            ttl_minutes: Cache TTL in minutes

        Raises:
            ValueError: If ttl_minutes is invalid
        """
        # Validate TTL
        if ttl_minutes < 1 or ttl_minutes > 10080:
            raise ValueError("TTL must be between 1 and 10080 minutes")

        config = self.get_config()

        # If no daemon config exists, create one with new TTL
        if config.daemon is None:
            config.daemon = DaemonConfig(**{**self.DAEMON_DEFAULTS, "ttl_minutes": ttl_minutes})
        else:
            # Update TTL in existing config
            daemon_dict = config.daemon.model_dump()
            daemon_dict["ttl_minutes"] = ttl_minutes
            config.daemon = DaemonConfig(**daemon_dict)

        self.save()

    def get_daemon_config(self) -> Dict[str, Any]:
        """Get daemon configuration with defaults.

        Returns:
            Dictionary containing daemon configuration. If no daemon config exists,
            returns defaults with enabled=False.
        """
        config = self.get_config()

        # If no daemon config, return defaults
        if config.daemon is None:
            return {**self.DAEMON_DEFAULTS}

        # Merge with defaults to ensure all fields present
        daemon_dict = config.daemon.model_dump()
        return {**self.DAEMON_DEFAULTS, **daemon_dict}

    def get_socket_path(self) -> Path:
        """Get daemon socket path.

        Socket is always located at .code-indexer/daemon.sock relative to config.

        Returns:
            Path to daemon socket
        """
        return self.config_path.parent / "daemon.sock"


def _load_override_config(override_path: Path) -> OverrideConfig:
    """Load override configuration from YAML file.

    Args:
        override_path: Path to .code-indexer-override.yaml file

    Returns:
        OverrideConfig instance

    Raises:
        Exception: If YAML parsing fails or required fields are missing
    """
    try:
        with open(override_path, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Override config must be a YAML dictionary")

        # Validate required fields exist
        required_fields = [
            "add_extensions",
            "remove_extensions",
            "add_exclude_dirs",
            "add_include_dirs",
            "force_include_patterns",
            "force_exclude_patterns",
        ]

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"Missing required fields in override config: {missing_fields}"
            )

        return OverrideConfig(
            add_extensions=data["add_extensions"] or [],
            remove_extensions=data["remove_extensions"] or [],
            add_exclude_dirs=data["add_exclude_dirs"] or [],
            add_include_dirs=data["add_include_dirs"] or [],
            force_include_patterns=data["force_include_patterns"] or [],
            force_exclude_patterns=data["force_exclude_patterns"] or [],
        )

    except yaml.YAMLError as e:
        raise Exception(f"Failed to parse override YAML file {override_path}: {e}")
    except Exception as e:
        raise Exception(f"Failed to load override config from {override_path}: {e}")


def _find_override_file(start_dir: Path) -> Optional[Path]:
    """Find .code-indexer-override.yaml by walking up the directory tree.

    Args:
        start_dir: Directory to start searching from

    Returns:
        Path to override file if found, None otherwise
    """
    current = start_dir

    # Walk up the directory tree looking for .code-indexer-override.yaml
    search_paths = [current] + list(current.parents)
    for path in search_paths:
        override_path = path / ".code-indexer-override.yaml"
        if override_path.exists():
            return override_path

    return None
