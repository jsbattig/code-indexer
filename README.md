# Code Indexer

AI-powered semantic code search with local and cloud models

A Python CLI tool that supports multiple embedding providers including [Ollama](https://ollama.ai/) for local models and [VoyageAI](https://www.voyageai.com/) for cloud-based embeddings, with [Qdrant](https://qdrant.tech/) for vector storage to provide semantic code search capabilities across your codebase.

Includes incremental updates to keep your index current as code changes.

## Features

- **Semantic Search** - Find code by meaning, not just keywords
- **Multiple Embedding Providers** - Support for Ollama (local) and VoyageAI (cloud)
- **Local AI Models** - Uses Ollama for privacy-preserving embeddings
- **Cloud AI Models** - VoyageAI for high-quality embeddings with configurable parallel processing
- **Vector Search** - Powered by Qdrant vector database
- **Automated Setup** - Docker container management
- **Incremental Updates** - Only re-index changed files
- **Filtering** - Filter by language, path, similarity score
- **CLI Interface** - Terminal interface with progress bars
- **Configurable** - Configuration options for different use cases
- **Multi-Project Support** - Index multiple projects simultaneously without port conflicts
- **Auto Project Detection** - Derives project names from git repositories or folder names

## Quick Start

### Installation

Choose an installation method:

#### Option 1: Using pipx
```bash
# Install pipx if not already installed (Ubuntu/Debian)
sudo apt update && sudo apt install pipx

# Install code-indexer using pipx (from latest release)
pipx install https://github.com/jsbattig/code-indexer/releases/download/v0.0.24.0/code_indexer-0.0.24.0-py3-none-any.whl

# Or install directly from git (latest development)
pipx install git+https://github.com/jsbattig/code-indexer.git

# Ensure pipx bin directory is in PATH
pipx ensurepath
```

#### Option 2: Using pip in a virtual environment
```bash
# Create and activate a virtual environment
python3 -m venv ~/code-indexer-env
source ~/code-indexer-env/bin/activate

# Install from GitHub releases
pip install https://github.com/jsbattig/code-indexer/releases/download/v0.0.24.0/code_indexer-0.0.24.0-py3-none-any.whl

# Or install directly from git (latest development)
pip install git+https://github.com/jsbattig/code-indexer.git

# Note: Remember to activate the environment before using: source ~/code-indexer-env/bin/activate
```

#### Option 3: Install from source (Development)
```bash
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer

# Using pipx (recommended)
pipx install -e .

# Or using pip in virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

#### Troubleshooting Modern Python Environments

If you encounter the error `externally-managed-environment` on Ubuntu/Debian systems:

- Use pipx (Option 1 above) - designed for CLI applications
- Use a virtual environment (Option 2 above)
- Avoid using `--break-system-packages` which can damage your system Python

pipx automatically manages isolated environments for CLI tools, making `code-indexer` globally available without affecting your system Python.

### Initialize and Setup

```bash
# Navigate to your codebase
cd /path/to/your/project

# Step 1: Initialize configuration (OPTIONAL - setup creates defaults if skipped)
code-indexer init

# Step 2: Start services (creates default config if init was skipped)
code-indexer setup

# Step 3: Index your codebase
code-indexer index

# Step 4: Search your code
code-indexer query "authentication logic"

# Smart incremental indexing (automatically detects changes)
code-indexer index

# Watch for changes and auto-update (real-time)
code-indexer watch
```

**Alternative flows:**

```bash
# Quick start (skip init - uses defaults: Ollama + default settings)
code-indexer setup
code-indexer index
code-indexer query "search terms"

# VoyageAI setup (cloud embeddings)
export VOYAGE_API_KEY="your-api-key"
code-indexer init --embedding-provider voyage-ai --embedding-model voyage-code-3
code-indexer setup
code-indexer index

# Interactive configuration
code-indexer init --interactive  # Guided setup with prompts
code-indexer setup
```

## Usage

> **🔥 Tip**: Use the short alias `cidx` instead of `code-indexer` for faster typing!  
> Examples: `cidx setup`, `cidx index`, `cidx query "search terms"`

### Commands

#### Setup Services
```bash
code-indexer setup [--model MODEL_NAME] [--force-recreate] [--parallel-requests N] [--max-models N] [--queue-size N]

# Performance Examples:
code-indexer setup --parallel-requests 2 --max-models 1  # Higher throughput
code-indexer setup --queue-size 1024                    # Larger request queue
```

#### Index Codebase
```bash
code-indexer index [--clear] [--resume] [--batch-size 50]

# Smart indexing (default):
# - Automatically detects if full or incremental indexing is needed
# - Resumes from interruptions using progressive metadata saving
# - Only processes modified files since last index
# - Handles provider/model changes intelligently

# Reconcile disk vs database and index missing/modified files:
code-indexer index --reconcile  # Compare disk files with database, index differences

# Options:
# --clear: Force full reindex (clears existing data)
# --reconcile: Reconcile disk files with database and index missing/modified files
# --batch-size: Number of files to process in each batch
```

#### Search Code
```bash
code-indexer query "search terms" [OPTIONS]

Options:
  --limit, -l INTEGER     Number of results (default: 10)
  --language TEXT         Filter by programming language
  --path TEXT            Filter by file path pattern
  --min-score FLOAT      Minimum similarity score (0.0-1.0)
```

#### Check Status
```bash
code-indexer status
```


#### Watch for Changes
```bash
code-indexer watch [--debounce FLOAT] [--batch-size INT]
```

#### Cleanup
```bash
code-indexer clean [--remove-data] [--all-projects]
```

### Search Examples

```bash
# Find authentication-related code
code-indexer query "user authentication login"

# Find React components
code-indexer query "component props state" --language tsx

# Find server-side database code
code-indexer query "database query" --path server

# High-precision search
code-indexer query "error handling" --min-score 0.8

# Get more results
code-indexer query "api endpoint" --limit 20
```

## Smart Incremental Indexing

The `index` command now provides intelligent incremental indexing that automatically adapts to your codebase changes:

```bash
# Smart incremental indexing (default) - automatically detects what's needed
code-indexer index

# Force full reindex when needed
code-indexer index --clear

# Real-time watching - automatically updates index when files change
code-indexer watch

# Watch with custom debounce (wait time before processing changes)
code-indexer watch --debounce 5.0
```

**How Smart Indexing Works:**
- **Automatic Detection**: Determines if full or incremental indexing is needed
- **Progressive Metadata**: Saves progress after every file for resumability
- **Change Detection**: Uses git hashes and file timestamps to detect changes
- **Safety Buffer**: 1-minute buffer ensures reliability during rapid development
- **Configuration Aware**: Forces full reindex when provider/model changes
- **Resumable**: Can resume interrupted indexing operations seamlessly
- **Git Integration**: Handles branch changes and repository state intelligently
- **Throughput Monitoring**: Real-time performance metrics with throttling detection
- **Smart Throttling**: Automatically detects and displays rate limiting status

**Real-time Updates:**
- `watch` mode uses file system events for live synchronization
- Batches changes and waits for a debounce period to avoid excessive processing
- Automatically detects and removes deleted files from the index

### Smart Reconciliation

Code Indexer supports intelligent reconciliation that compares your disk files with the database:

```bash
# Start indexing a large codebase
code-indexer index

# Press Ctrl+C to interrupt at any time
^C

# Reconcile by comparing disk vs database with timestamp checking
code-indexer index --reconcile
# ✅ Scans disk, checks database, indexes missing + modified files

# Example output:
# "Reconcile: 1500/2000 files up-to-date, indexing 500 missing + 200 modified"
```

**How Reconciliation Works:**
- **Disk vs Database comparison**: Compares files on disk with database contents
- **Missing file detection**: Finds files that exist on disk but aren't in the database
- **Timestamp-based detection**: For non-git projects, compares file modification times; for git projects, compares against indexing timestamps
- **Cross-session persistence**: Works across different terminal sessions and interruptions
- **No duplicate work**: Only indexes files that are actually missing or modified
- **Filesystem tolerance**: Uses 1-second tolerance to handle filesystem precision differences

**Note**: For git-based projects, reconciliation primarily relies on git hashes for change detection during normal incremental indexing. The `--reconcile` flag is most effective for non-git projects or when you need to ensure database consistency.

## Git-Aware Indexing

Code Indexer provides intelligent git-aware indexing that automatically adapts to your repository state:

### Automatic Git Detection
- **Branch-aware**: Indexes files based on current git branch context
- **Change tracking**: Uses git hashes to detect when files have changed
- **Fallback support**: Works in non-git directories using filesystem metadata

### Smart Re-indexing
```bash
# Smart indexing automatically detects what's needed:
# - Full index if no previous data exists
# - Incremental update if only some files changed
# - Full reindex if provider/model configuration changed
code-indexer index

# Force complete re-index when needed
code-indexer index --clear
```

## File Watcher Deep Dive

The `watch` command provides real-time index synchronization using a sophisticated multi-threaded architecture:

### Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   File System  │───▶│   Event Handler  │───▶│  Change Buffer  │
│   (watchdog)    │    │  (Filter & Queue)│    │  (Debounced)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Vector Store  │◀───│   Index Updater  │◀───│   Processor     │
│   (Qdrant)      │    │  (Batch Upload)   │    │   (Worker)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Thread Architecture

**Three coordinated threads handle different responsibilities:**

1. **Main Thread** (`watch` command)
   - Coordinates startup and shutdown
   - Handles user interruption (Ctrl+C)
   - Manages thread lifecycle

2. **Observer Thread** (watchdog library)
   - Monitors file system events using OS-native APIs
   - Detects file modifications, deletions, creations, and moves
   - Runs the `CodeChangeHandler` callbacks

3. **Processor Thread** (daemon thread)
   - Runs the debounced change processing loop
   - Converts file changes into vector database operations
   - Handles AI embedding generation and batch uploads

### Event Processing Pipeline

#### 1. **File System Monitoring**
```python
# Watches entire codebase recursively
observer.schedule(event_handler, codebase_dir, recursive=True)
```

- Uses `watchdog.observers.Observer` for cross-platform file monitoring
- Leverages OS-native APIs (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows)
- Monitors the entire codebase directory tree recursively

#### 2. **Event Filtering & Queuing**
```python
class CodeChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if file_finder._should_include_file(file_path):
            with change_lock:
                pending_changes.add(file_path)
```

**Intelligent filtering prevents unnecessary processing:**
- **File type filtering**: Only processes configured extensions (`.py`, `.js`, `.ts`, etc.)
- **Directory exclusion**: Ignores `node_modules`, `.git`, `__pycache__`, build directories
- **Size limits**: Skips files exceeding configured size thresholds
- **Duplicate prevention**: Uses a set to automatically deduplicate rapid successive changes

#### 3. **Debounced Processing**
```python
def process_changes():
    while True:
        time.sleep(debounce)  # Default: 2 seconds
        
        with change_lock:
            if not pending_changes:
                continue
            
            changes_to_process = pending_changes.copy()
            pending_changes.clear()
```

**Debouncing prevents thrashing during rapid development:**
- **Batching**: Collects multiple file changes into single processing cycle
- **Configurable delay**: Default 2s, customizable via `--debounce` option
- **Atomic operations**: Thread-safe snapshot and clear of pending changes
- **Development-friendly**: Handles rapid save cycles from IDEs and build tools

#### 4. **Change Categorization**
```python
modified_files = []
deleted_files = []

for file_path in changes_to_process:
    if file_path.exists():
        modified_files.append(file_path)
    else:
        relative_path = str(file_path.relative_to(config.codebase_dir))
        deleted_files.append(relative_path)
```

**Smart differentiation between change types:**
- **Modifications**: Files that exist and need re-indexing
- **Deletions**: Files that no longer exist and need removal from index
- **Moves/Renames**: Detected as deletion + creation

#### 5. **Vector Database Operations**

**For deleted files:**
```python
qdrant_client.delete_by_filter({
    "must": [{"key": "path", "match": {"value": deleted_file}}]
})
```

**For modified files:**
```python
# 1. Remove existing vectors
qdrant_client.delete_by_filter({"must": [{"key": "path", "match": {"value": file_path}}]})

# 2. Re-chunk file content
chunks = text_chunker.chunk_file(file_path)

# 3. Generate embeddings via Ollama
for chunk in chunks:
    embedding = ollama_client.get_embedding(chunk["text"])
    
# 4. Batch upload to Qdrant
qdrant_client.upsert_points(batch_points)
```

### Thread Safety & Synchronization

**Critical sections protected by locks:**
```python
change_lock = threading.Lock()

# Event handler (Observer thread)
with change_lock:
    pending_changes.add(file_path)

# Processor (Processor thread)  
with change_lock:
    changes_to_process = pending_changes.copy()
    pending_changes.clear()
```

**Lock-free design for performance:**
- Minimal lock contention using short critical sections
- Copy-and-clear pattern prevents blocking between threads
- Set data structure provides O(1) deduplication

### Performance Characteristics

**Resource usage:**
- **Memory**: Bounded change buffer prevents memory leaks during high-activity periods
- **CPU**: Only processes actual changes, not entire codebase
- **I/O**: Batched database operations reduce network overhead
- **AI**: Embedding generation only for changed content

**Scalability:**
- **Large codebases**: Recursive monitoring scales to thousands of files
- **High activity**: Debouncing handles rapid development cycles
- **Network**: Batch operations reduce API call frequency

### Configuration Options

```bash
# Default 2-second debounce
python -m code_indexer.cli watch

# Custom debounce for different development patterns
python -m code_indexer.cli watch --debounce 5.0    # Slower, more batching
python -m code_indexer.cli watch --debounce 0.5    # Faster, more responsive

# Custom batch size for network optimization  
python -m code_indexer.cli watch --batch-size 100  # Larger batches, less frequent uploads
python -m code_indexer.cli watch --batch-size 10   # Smaller batches, more frequent uploads
```

### Use Cases & Best Practices

**Use cases:**
- **Active development**: Keep search current during coding sessions
- **Team environments**: Shared codebase with multiple contributors
- **Large codebases**: Incremental updates faster than full re-indexing
- **CI/CD integration**: Continuous index updates in development environments

**Usage patterns:**
- **Development workflow**: Start watcher at beginning of coding session
- **Resource management**: Stop watcher when doing large refactors/imports
- **Debounce tuning**: Increase for build-heavy projects, decrease for pure coding
- **Monitoring**: Watch console output to understand update patterns

**Stopping the watcher:**
```bash
# Graceful shutdown with Ctrl+C
^C
👋 Stopping file watcher...
```

The watcher provides "live sync" functionality, ensuring your semantic search index stays current with code changes.

## Multi-Project Support

Code Indexer automatically supports indexing multiple projects simultaneously without port conflicts:

### Automatic Project Detection
- **Git Repository Name**: Uses the git repository name from `git remote get-url origin`
- **Directory Name**: Falls back to the current directory name if not a git repository
- **Sanitization**: Converts names to Docker-compatible format (lowercase, hyphens only)

### Isolated Storage
Each project gets its own isolated vector database:
```bash
# Project: my-app → Collection: my_app
# Project: api-server → Collection: api_server
```

### Global Services
- **Single Ollama instance**: Shared AI model server for all projects
- **Single Qdrant instance**: Multiple collections in one database
- **No port conflicts**: Projects access services via internal communication
- **Resource usage**: Shared containers reduce memory footprint

### Benefits
- **Multiple projects**: Index and search different codebases simultaneously
- **Isolation**: Projects cannot interfere with each other's data
- **Automatic configuration**: Project names are detected automatically
- **Resource efficiency**: Shared services minimize system resource usage

## Configuration

Code Indexer creates a `.code-indexer/config.json` file in your project directory:

```json
{
  "codebase_dir": ".",
  "file_extensions": [
    "py", "js", "ts", "tsx", "java", "c", "cpp", "go", "rs", "rb",
    "php", "sh", "bash", "html", "css", "md", "json", "yaml", "yml"
  ],
  "exclude_dirs": [
    "node_modules", "venv", "__pycache__", ".git", "dist", "build",
    "target", ".idea", ".vscode", ".gradle", "bin", "obj", "coverage"
  ],
  "indexing": {
    "chunk_size": 1500,
    "chunk_overlap": 150,
    "max_file_size": 1048576,
    "index_comments": true
  },
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
    "collection": "code_index",
    "vector_size": 768
  }
}
```

### Key Settings

- **codebase_dir**: Directory to index
- **file_extensions**: File types to include
- **exclude_dirs**: Directories to skip
- **chunk_size**: Text chunk size for large files
- **ollama.model**: Embedding model (e.g., `nomic-embed-text`, `all-MiniLM-L6-v2`)

### Performance Settings

Configure Ollama performance through setup command parameters:

- **--parallel-requests**: Number of parallel requests Ollama can handle (default: 1)
  - Config setting: `num_parallel`
- **--max-models**: Maximum models to keep loaded in memory (default: 1)
  - Config setting: `max_loaded_models`
- **--queue-size**: Maximum request queue size (default: 512)
  - Config setting: `max_queue`

```bash
# Conservative (low resource usage)
code-indexer setup --parallel-requests 1 --max-models 1 --queue-size 256

# Balanced (recommended for most users)
code-indexer setup --parallel-requests 2 --max-models 1 --queue-size 512

# High throughput (powerful machines)
code-indexer setup --parallel-requests 4 --max-models 1 --queue-size 1024
```

## Embedding Providers

Code Indexer supports multiple embedding providers for generating text embeddings. Choose between local processing with Ollama or cloud-based services like VoyageAI.

### Available Providers

#### Ollama (Default - Local)
- **Privacy**: All processing happens locally
- **Cost**: Free
- **Setup**: Requires Docker to run Ollama service
- **Models**: `nomic-embed-text`, `all-MiniLM-L6-v2`, and others

#### VoyageAI (Cloud)
- **Performance**: High-quality embeddings optimized for code
- **Speed**: Configurable parallel processing (default: 8 concurrent requests)
- **Cost**: Usage-based pricing
- **Models**: `voyage-code-3` (default), `voyage-large-2-instruct`

### Provider Configuration

#### Using Ollama (Default)
```bash
# Initialize with Ollama (default)
code-indexer init --embedding-provider ollama

# Or use interactive mode
code-indexer init --interactive
```

#### Using VoyageAI
```bash
# Set your API key (required)
export VOYAGE_API_KEY="your_api_key_here"

# Initialize with VoyageAI
code-indexer init --embedding-provider voyage-ai

# Or use interactive mode for guided setup
code-indexer init --interactive
```

### Environment Variables

#### VoyageAI API Key Setup
To use VoyageAI, you need to set up your API key. The key must be available in the `VOYAGE_API_KEY` environment variable.

**Temporary Setup (Current Session Only):**
```bash
export VOYAGE_API_KEY="your_api_key_here"
```

**Permanent Setup (Persistent Across Sessions):**

Add the export command to your shell configuration file:

```bash
# For bash users
echo 'export VOYAGE_API_KEY="your_api_key_here"' >> ~/.bashrc
source ~/.bashrc

# For zsh users  
echo 'export VOYAGE_API_KEY="your_api_key_here"' >> ~/.zshrc
source ~/.zshrc

# For fish users
echo 'set -gx VOYAGE_API_KEY "your_api_key_here"' >> ~/.config/fish/config.fish
source ~/.config/fish/config.fish
```

**Verification:**
```bash
# Verify the API key is set
echo $VOYAGE_API_KEY

# Test the connection
code-indexer init --embedding-provider voyage-ai --interactive
```

### Provider-Specific Settings

#### VoyageAI Configuration
```json
{
  "embedding_provider": "voyage-ai",
  "voyage_ai": {
    "model": "voyage-code-3",
    "parallel_requests": 8,
    "batch_size": 64,
    "requests_per_minute": 300,
    "tokens_per_minute": 1000000,
    "retry_delay": 1.0,
    "max_retries": 3
  }
}
```

#### Rate Limiting
VoyageAI includes automatic rate limiting to respect API limits:
- **Request Rate**: 300 requests per minute (configurable)
- **Token Rate**: 1M tokens per minute (configurable)
- **Backoff**: Exponential backoff on rate limit errors
- **Parallel Processing**: Configurable concurrent requests (default: 8) for optimal throughput

### Switching Providers

You can switch embedding providers at any time. Note that this will require re-indexing your codebase since different providers generate different embeddings.

```bash
# Switch to VoyageAI
code-indexer init --embedding-provider voyage-ai --force

# Switch back to Ollama
code-indexer init --embedding-provider ollama --force

# Re-index with new provider
code-indexer index --clear
```

### Multi-Model Support

Each indexed document includes metadata about which embedding model was used. This allows:

- **Provider Coexistence**: Different projects can use different providers
- **Model Filtering**: Search results can be filtered by embedding model
- **Migration**: Gradual migration between providers without losing existing data

```bash
# Query specific to a model
code-indexer query "authentication" --model-filter voyage-code-3

# Check which models are in your index
code-indexer status --show-models
```


## Architecture

### Components
- **Ollama**: Local LLM server for generating embeddings
- **Qdrant**: Vector database for storing and searching embeddings
- **CLI Tool**: Python-based command interface
- **Docker**: Container management for services

### Data Flow
1. **Indexing**: Files → Chunks → Embeddings → Vector Storage
2. **Searching**: Query → Embedding → Vector Search → Results

### File Structure
```
your-project/
├── .code-indexer/
│   ├── config.json          # Configuration
│   ├── metadata.json        # Index metadata
│   ├── ollama/              # Ollama data
│   ├── qdrant/              # Vector database
│   └── logs/                # Operation logs
├── .gitignore              # Add .code-indexer/ to ignore
└── (your project files)
```

## AI Models

### Default Model: `nomic-embed-text`
- **Vector Size**: 768 dimensions
- **Memory Usage**: ~500MB
- **Performance**: Fast inference
- **Quality**: Good semantic understanding

### Alternative Models
Edit `.code-indexer/config.json` to use different models:

- `all-MiniLM-L6-v2` - Faster, smaller (384d)
- `bge-large-en-v1.5` - Higher quality, larger (1024d)

## Requirements

- **Python**: 3.8+
- **Docker**: For running Ollama and Qdrant services
- **Memory**: 4GB+ RAM recommended
- **Storage**: 10GB+ for models and index
- **Platform**: Linux, macOS, Windows (with WSL2)

## Development

### Setup Development Environment

```bash
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Run Tests

```bash
pytest
pytest --cov=code_indexer  # With coverage
```

### Code Quality

```bash
black src/                 # Format code
ruff src/                  # Lint code
mypy src/                  # Type checking
```

## Troubleshooting

### Services Not Starting
```bash
# Check Docker status
docker ps

# View container logs
docker logs code-indexer-ollama
docker logs code-indexer-qdrant

# Restart services
code-indexer clean
code-indexer setup
```

### Search Not Working
```bash
# Check service status
code-indexer status

# Re-index if needed
code-indexer index --clear
```

### Performance Issues
- Reduce `chunk_size` in configuration
- Use smaller embedding model (`all-MiniLM-L6-v2`)
- Add more directories to `exclude_dirs`
- Increase `max_file_size` limit

## Security and Privacy

- All processing happens locally
- No code sent to external services
- Embeddings stored locally in Qdrant
- Models run in isolated containers

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

- 📝 [Issues](https://github.com/jsbattig/code-indexer/issues)
- 📖 [Documentation](https://github.com/jsbattig/code-indexer/wiki)
- 💬 [Discussions](https://github.com/jsbattig/code-indexer/discussions)