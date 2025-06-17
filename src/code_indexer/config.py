"""Configuration management for Code Indexer."""

import json
from pathlib import Path
from typing import List, Optional, Any

from pydantic import BaseModel, Field, field_validator


class OllamaConfig(BaseModel):
    """Configuration for Ollama service."""

    host: str = Field(default="http://localhost:11434", description="Ollama API host")
    model: str = Field(default="nomic-embed-text", description="Embedding model name")
    timeout: int = Field(default=30, description="Request timeout in seconds")


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
- Check the main documentation for advanced configuration

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
