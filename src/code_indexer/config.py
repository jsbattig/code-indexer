"""Configuration management for Code Indexer."""

import json
import logging
from pathlib import Path
from typing import List, Optional, Any, Literal

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
    use_semantic_chunking: bool = Field(
        default=True,
        description="Use AST-based semantic chunking for supported languages",
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


class Config(BaseModel):
    """Main configuration for Code Indexer."""

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

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None

    def load(self) -> Config:
        """Load configuration from file or create default with dynamic path resolution."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)

                # Handle path resolution for CoW clone compatibility
                if "codebase_dir" in data:
                    # Resolve potentially relative path to absolute
                    resolved_path = self._resolve_relative_path(data["codebase_dir"])
                    data["codebase_dir"] = str(resolved_path)

                self._config = Config(**data)
            except Exception as e:
                raise ValueError(f"Failed to load config from {self.config_path}: {e}")
        else:
            self._config = Config()

        return self._config

    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file with relative paths for CoW support."""
        if config is None:
            config = self._config

        if config is None:
            raise ValueError("No configuration to save")

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path serialization with relative paths
        config_dict = config.model_dump()
        # Store relative path for CoW clone compatibility
        config_dict["codebase_dir"] = self._make_relative_to_config(config.codebase_dir)

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
        # Store relative path for CoW clone compatibility
        config_dict["codebase_dir"] = self._make_relative_to_config(config.codebase_dir)

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
        for path in [current] + list(current.parents):
            config_path = path / ".code-indexer" / "config.json"
            if config_path.exists():
                return config_path

        return None

    @classmethod
    def create_with_backtrack(cls, start_dir: Optional[Path] = None) -> "ConfigManager":
        """Create ConfigManager by finding config through directory backtracking.

        Args:
            start_dir: Directory to start searching from (default: current directory)

        Returns:
            ConfigManager instance with found config path or default path
        """
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
        return cls(config_path)

    def _make_relative_to_config(self, path: Path) -> str:
        """Convert an absolute path to relative path from config location."""
        try:
            # Get the directory containing the config file
            config_dir = self.config_path.parent.parent  # Parent of .code-indexer/

            # If path is already relative or is ".", keep it as is
            if not path.is_absolute() or str(path) == ".":
                return str(path)

            # Try to make the path relative to the config directory
            absolute_path = path.resolve()
            config_root = config_dir.resolve()

            try:
                relative_path = absolute_path.relative_to(config_root)
                return str(relative_path) if str(relative_path) != "." else "."
            except ValueError:
                # Path is not within config directory - store absolute for backward compatibility
                return str(absolute_path)

        except Exception:
            # If anything fails, fall back to absolute path
            return str(path.resolve())

    def _resolve_relative_path(self, path_str: str) -> Path:
        """Resolve a potentially relative path from config to absolute path."""
        path = Path(path_str)

        # If already absolute, return as is
        if path.is_absolute():
            return path

        # If relative, resolve relative to config directory (parent of .code-indexer/)
        config_dir = self.config_path.parent.parent  # Parent of .code-indexer/
        return (config_dir / path).resolve()

    def migrate_to_relative_paths(self) -> bool:
        """
        Migrate existing configuration to use relative paths.

        Returns:
            True if migration was performed, False if no migration needed
        """
        if not self.config_path.exists():
            return False

        try:
            # Load current config
            config = self.load()

            # Check if codebase_dir is absolute and within project
            if config.codebase_dir.is_absolute():
                config_root = self.config_path.parent.parent  # Parent of .code-indexer/

                try:
                    # Try to make relative
                    relative_path = config.codebase_dir.resolve().relative_to(
                        config_root.resolve()
                    )

                    # Update the config with relative path
                    config.codebase_dir = (
                        relative_path if str(relative_path) != "." else Path(".")
                    )

                    # Save the updated config
                    self.save(config)
                    return True

                except ValueError:
                    # Path is outside project root, keep absolute
                    pass

        except Exception as e:
            logger.warning(f"Failed to migrate config to relative paths: {e}")

        return False
