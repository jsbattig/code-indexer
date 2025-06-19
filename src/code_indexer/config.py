"""Configuration management for Code Indexer."""

import json
from pathlib import Path
from typing import List, Optional, Any

from pydantic import BaseModel, Field, field_validator


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


class QdrantConfig(BaseModel):
    """Configuration for Qdrant vector database."""

    host: str = Field(default="http://localhost:6333", description="Qdrant API host")
    collection: str = Field(default="code_index", description="Collection name")
    vector_size: int = Field(default=768, description="Vector dimension size")


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
        default=180, description="Service startup timeout in seconds"
    )
    service_shutdown: int = Field(
        default=30, description="Service shutdown timeout in seconds"
    )
    port_release: int = Field(default=15, description="Port release timeout in seconds")
    cleanup_validation: int = Field(
        default=30, description="Cleanup validation timeout in seconds"
    )
    health_check: int = Field(default=60, description="Health check timeout in seconds")
    data_cleaner_startup: int = Field(
        default=60, description="Data cleaner startup timeout in seconds"
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
            "h",
            "hpp",
            "go",
            "rs",
            "rb",
            "php",
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
            "scala",
            "dart",
            "vue",
            "jsx",
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

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)

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
        """Load configuration from file or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                self._config = Config(**data)
            except Exception as e:
                raise ValueError(f"Failed to load config from {self.config_path}: {e}")
        else:
            self._config = Config()

        return self._config

    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file."""
        if config is None:
            config = self._config

        if config is None:
            raise ValueError("No configuration to save")

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path serialization
        config_dict = config.model_dump()
        config_dict["codebase_dir"] = str(config.codebase_dir)

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

        # Convert to dict and handle Path serialization
        config_dict = config.model_dump()
        config_dict["codebase_dir"] = str(config.codebase_dir)

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
