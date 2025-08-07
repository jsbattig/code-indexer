# Complete Configuration Reference

## Configuration Schema Overview

The code-indexer uses a hierarchical configuration system defined in `config.py`. Configuration is stored in `.code-indexer/config.json` and supports both absolute and relative paths for portability.

## Main Configuration Class

### Config (config.py:211-346)

The root configuration object containing all settings.

```python
class Config(BaseModel):
    codebase_dir: Path                    # Directory to index (default: ".")
    file_extensions: List[str]            # File extensions to index
    exclude_dirs: List[str]               # Directories to exclude
    embedding_provider: Literal["ollama", "voyage-ai"]  # Provider selection
    ollama: OllamaConfig                  # Ollama-specific settings
    voyage_ai: VoyageAIConfig             # VoyageAI-specific settings
    qdrant: QdrantConfig                  # Qdrant database settings
    indexing: IndexingConfig              # Indexing behavior settings
    timeouts: TimeoutsConfig              # Various timeout configurations
    polling: PollingConfig                # Polling behavior settings
    project_containers: ProjectContainersConfig  # Container naming
    project_ports: ProjectPortsConfig    # Port assignments
    override_config: Optional[OverrideConfig]  # Override rules
```

## Embedding Provider Configurations

### OllamaConfig (config.py:14-32)

Configuration for local Ollama embedding service.

| Field | Type | Default | Description | Environment Variable |
|-------|------|---------|-------------|---------------------|
| `host` | str | "http://localhost:11434" | Ollama API host URL | - |
| `model` | str | "nomic-embed-text" | Embedding model name | - |
| `timeout` | int | 30 | Request timeout in seconds | - |
| `num_parallel` | int | 1 | Parallel request slots | OLLAMA_NUM_PARALLEL |
| `max_loaded_models` | int | 1 | Max models kept in memory | OLLAMA_MAX_LOADED_MODELS |
| `max_queue` | int | 512 | Maximum request queue size | OLLAMA_MAX_QUEUE |

**Performance Notes:**
- `num_parallel=1`: Sequential processing (recommended for single-user)
- `num_parallel=4`: Allows concurrent requests from multiple clients
- Memory usage scales with `max_loaded_models`

### VoyageAIConfig (config.py:34-71)

Configuration for VoyageAI cloud embedding service.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_endpoint` | str | "https://api.voyageai.com/v1/embeddings" | API endpoint URL |
| `model` | str | "voyage-code-3" | Model name (voyage-code-3, voyage-large-2, voyage-2) |
| `timeout` | int | 30 | Request timeout in seconds |
| `parallel_requests` | int | 8 | Concurrent API requests |
| `batch_size` | int | 128 | Texts per batch request |
| `max_retries` | int | 3 | Maximum retry attempts |
| `retry_delay` | float | 1.0 | Initial retry delay in seconds |
| `exponential_backoff` | bool | True | Use exponential backoff |

**API Key Configuration:**
- Set via environment variable: `VOYAGE_API_KEY`
- Models: voyage-code-3 (optimized for code), voyage-large-2, voyage-2

## Database Configuration

### QdrantConfig (config.py:73-102)

Configuration for Qdrant vector database.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | str | "http://localhost:6333" | Qdrant API host |
| `collection_base_name` | str | "code_index" | Base collection name |
| `vector_size` | int | 768 | Vector dimensions (auto-detected, deprecated) |
| `hnsw_ef` | int | 64 | Search accuracy parameter |
| `hnsw_ef_construct` | int | 200 | Index construction quality |
| `hnsw_m` | int | 32 | Connectivity parameter |

**HNSW Parameters:**
- `hnsw_ef`: Higher values = more accurate search, slower (range: 4-10000)
- `hnsw_ef_construct`: Higher values = better index quality, slower indexing
- `hnsw_m`: Higher values = better for large datasets, more memory

**Collection Naming:**
- Format: `{collection_base_name}_{model_slug}`
- Example: `code_index_nomic_embed_text`

## Indexing Configuration

### IndexingConfig (config.py:104-119)

Controls indexing behavior and chunking strategies.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `chunk_size` | int | 1500 | Text chunk size in characters |
| `chunk_overlap` | int | 150 | Overlap between chunks |
| `max_file_size` | int | 1048576 | Max file size in bytes (1MB) |
| `index_comments` | bool | True | Include comments in indexing |
| `use_semantic_chunking` | bool | True | Use AST-based semantic chunking |

**Chunking Strategy:**
- Semantic chunking: Splits at function/class boundaries when possible
- Character chunking: Falls back to character-based splitting
- Overlap ensures context continuity

## Timeout Configuration

### TimeoutsConfig (config.py:121-140)

Configures various operation timeouts.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `service_startup` | int | 240 | Service startup timeout (seconds) |
| `service_shutdown` | int | 30 | Service shutdown timeout |
| `port_release` | int | 15 | Port release wait time |
| `cleanup_validation` | int | 30 | Cleanup validation timeout |
| `health_check` | int | 180 | Health check timeout |
| `data_cleaner_startup` | int | 180 | Data cleaner startup timeout |

## Polling Configuration

### PollingConfig (config.py:142-154)

Controls condition polling behavior with exponential backoff.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `initial_interval` | float | 0.5 | Initial polling interval (seconds) |
| `backoff_factor` | float | 1.2 | Exponential backoff multiplier |
| `max_interval` | float | 2.0 | Maximum polling interval |

**Backoff Algorithm:**
```
interval = min(initial_interval * (backoff_factor ^ attempt), max_interval)
```

## Project-Specific Configuration

### ProjectContainersConfig (config.py:156-171)

Container naming for project isolation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_hash` | Optional[str] | None | Hash derived from project path |
| `qdrant_name` | Optional[str] | None | Qdrant container name |
| `ollama_name` | Optional[str] | None | Ollama container name |
| `data_cleaner_name` | Optional[str] | None | Data cleaner container name |

**Naming Convention:**
- Format: `{service}_cidx_{project_hash[:8]}`
- Example: `qdrant_cidx_a1b2c3d4`

### ProjectPortsConfig (config.py:173-181)

Dynamic port assignments for project isolation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `qdrant_port` | Optional[int] | None | Qdrant service port |
| `ollama_port` | Optional[int] | None | Ollama service port |
| `data_cleaner_port` | Optional[int] | None | Data cleaner port |

**Port Assignment:**
- Dynamically allocated based on project hash
- No default ports - always project-specific
- Ensures container isolation between projects

## Override Configuration

### OverrideConfig (config.py:183-209)

File inclusion/exclusion override rules loaded from `.code-indexer-override.yaml`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `add_extensions` | List[str] | [] | Additional file extensions to index |
| `remove_extensions` | List[str] | [] | Extensions to exclude |
| `add_exclude_dirs` | List[str] | [] | Additional directories to exclude |
| `add_include_dirs` | List[str] | [] | Directories to force include |
| `force_include_patterns` | List[str] | [] | Force include file patterns |
| `force_exclude_patterns` | List[str] | [] | Force exclude file patterns |

**Override File Format (.code-indexer-override.yaml):**
```yaml
add_extensions: ["log", "txt"]
remove_extensions: ["md"]
add_exclude_dirs: ["temp", "cache"]
add_include_dirs: ["important_configs"]
force_include_patterns: ["*.important"]
force_exclude_patterns: ["*.generated"]
```

## File Extensions

### Default Supported Extensions (config.py:216-277)

The system indexes 60+ file extensions by default:

**Programming Languages:**
- Python: py
- JavaScript/TypeScript: js, ts, tsx, jsx
- Java: java
- C/C++: c, cpp, cc, cxx, h, hpp, hxx
- C#: cs
- Go: go
- Rust: rs
- Ruby: rb, rake, rbw, gemspec
- PHP: php
- Perl: pl, pm, pod, t, psgi
- Swift: swift
- Kotlin: kt, kts
- Scala: scala
- Dart: dart
- Lua: lua
- Groovy: groovy, gradle, gvy, gy
- Pascal/Delphi: pas, pp, dpr, dpk, inc

**Web Technologies:**
- HTML: html, htm
- CSS: css, scss, sass
- Vue: vue

**Data/Config:**
- JSON: json
- YAML: yaml, yml
- TOML: toml
- XML: xml, xsd, xsl, xslt

**Other:**
- Shell: sh, bash
- SQL: sql
- Markdown: md

## Default Excluded Directories (config.py:280-301)

Automatically excluded from indexing:

- **Dependencies:** node_modules, venv, vendor
- **Build Output:** dist, build, target, bin, obj
- **Caches:** __pycache__, .gradle, coverage
- **IDE:** .idea, .vscode
- **Version Control:** .git
- **Framework-specific:** .next, .nuxt, dist-*
- **Code-indexer:** .code-indexer

## Configuration Management

### ConfigManager (config.py:348-761)

Handles configuration loading, saving, and discovery.

**Key Methods:**

| Method | Description |
|--------|-------------|
| `load()` | Load configuration from file or create default |
| `save()` | Save configuration with relative paths |
| `find_config_path()` | Walk up directory tree to find config |
| `create_with_backtrack()` | Create manager with config discovery |
| `migrate_to_relative_paths()` | Convert absolute to relative paths |

**Configuration Discovery:**
1. Searches from current directory upward
2. Stops at first `.code-indexer/config.json` found
3. Supports nested projects with separate configs
4. Uses relative paths for portability

## Environment Variables

### Supported Environment Variables

| Variable | Component | Description |
|----------|-----------|-------------|
| `VOYAGE_API_KEY` | VoyageAI | API authentication key |
| `OLLAMA_NUM_PARALLEL` | Ollama | Parallel request handling |
| `OLLAMA_MAX_LOADED_MODELS` | Ollama | Models kept in memory |
| `OLLAMA_MAX_QUEUE` | Ollama | Request queue size |

## Validation Rules

### Path Validation (config.py:331-339)
- Converts string paths to Path objects
- Resolves relative paths from config directory
- Handles both absolute and relative paths

### Extension Normalization (config.py:341-345)
- Removes leading dots from extensions
- Ensures consistent format

### Override Validation (config.py:763-810)
- Requires all fields in YAML file
- Validates YAML structure
- Falls back gracefully on errors

## Configuration Precedence

1. **Override Config** (highest priority)
   - `.code-indexer-override.yaml` in project root
   - Force include/exclude patterns

2. **Project Config**
   - `.code-indexer/config.json`
   - Main configuration file

3. **Default Values** (lowest priority)
   - Built-in defaults in code

## Best Practices

### Performance Tuning

**For Single User:**
```json
{
  "ollama": {
    "num_parallel": 1,
    "max_loaded_models": 1,
    "max_queue": 256
  },
  "indexing": {
    "chunk_size": 1500,
    "use_semantic_chunking": true
  }
}
```

**For Large Codebases:**
```json
{
  "qdrant": {
    "hnsw_ef": 128,
    "hnsw_ef_construct": 400,
    "hnsw_m": 48
  },
  "indexing": {
    "chunk_size": 2000,
    "max_file_size": 5242880
  }
}
```

**For Shared Infrastructure:**
```json
{
  "ollama": {
    "num_parallel": 4,
    "max_loaded_models": 2,
    "max_queue": 1024
  },
  "voyage_ai": {
    "parallel_requests": 16,
    "batch_size": 256
  }
}
```

### Migration Between Providers

**Switching from Ollama to VoyageAI:**
1. Update `embedding_provider` to "voyage-ai"
2. Set `VOYAGE_API_KEY` environment variable
3. Run `cidx clean --remove-data`
4. Run `cidx index --clear`

**Vector Size Compatibility:**
- Ollama (nomic-embed-text): 768 dimensions
- VoyageAI (voyage-code-3): 1024 dimensions
- Must clear data when switching providers

## Configuration File Examples

### Minimal Configuration
```json
{
  "codebase_dir": ".",
  "embedding_provider": "ollama"
}
```

### Full Configuration
```json
{
  "codebase_dir": ".",
  "file_extensions": ["py", "js", "ts"],
  "exclude_dirs": ["node_modules", "venv", "build"],
  "embedding_provider": "ollama",
  "ollama": {
    "host": "http://localhost:11434",
    "model": "nomic-embed-text",
    "timeout": 30,
    "num_parallel": 1,
    "max_loaded_models": 1,
    "max_queue": 512
  },
  "qdrant": {
    "host": "http://localhost:6333",
    "collection_base_name": "code_index",
    "hnsw_ef": 64,
    "hnsw_ef_construct": 200,
    "hnsw_m": 32
  },
  "indexing": {
    "chunk_size": 1500,
    "chunk_overlap": 150,
    "max_file_size": 1048576,
    "index_comments": true,
    "use_semantic_chunking": true
  },
  "timeouts": {
    "service_startup": 240,
    "service_shutdown": 30,
    "port_release": 15,
    "cleanup_validation": 30,
    "health_check": 180,
    "data_cleaner_startup": 180
  },
  "polling": {
    "initial_interval": 0.5,
    "backoff_factor": 1.2,
    "max_interval": 2.0
  }
}
```

## References

All configuration options are defined in:
- `src/code_indexer/config.py`: Complete configuration schema
- `.code-indexer/config.json`: Project configuration file
- `.code-indexer-override.yaml`: Optional override rules