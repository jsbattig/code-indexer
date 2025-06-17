# Code Indexer

🔍 **AI-powered semantic code search with local models**

A Python CLI tool that uses [Ollama](https://ollama.ai/) for embeddings and [Qdrant](https://qdrant.tech/) for vector storage to provide intelligent, semantic code search capabilities across your codebase.

✨ **Features include incremental updates to keep your index current as code changes.**

## Features

- 🧠 **Semantic Search** - Find code by meaning, not just keywords
- 🏠 **Local AI Models** - Uses Ollama for privacy-preserving embeddings
- 🚀 **Fast Vector Search** - Powered by Qdrant vector database
- 📦 **Easy Setup** - Automated Docker container management
- 🔄 **Incremental Updates** - Only re-index changed files
- 🎯 **Smart Filtering** - Filter by language, path, similarity score
- 📊 **Rich CLI** - Beautiful terminal interface with progress bars
- 🔧 **Configurable** - Extensive configuration options
- 🏢 **Multi-Project Support** - Index multiple projects simultaneously without port conflicts
- 🎯 **Auto Project Detection** - Automatically derives project names from git repositories or folder names

## Quick Start

### Installation

```bash
# Install from PyPI
pip install code-indexer

# Install from GitHub (latest development version)
pip install git+https://github.com/jsbattig/code-indexer.git

# Or install from source
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer
pip install -e .
```

### Initialize and Setup

```bash
# Navigate to your codebase
cd /path/to/your/project

# Initialize configuration
python -m code_indexer.cli init

# Start services and download AI model
python -m code_indexer.cli setup

# Index your codebase
python -m code_indexer.cli index

# Search your code
python -m code_indexer.cli query "authentication logic"

# Keep index updated as code changes
python -m code_indexer.cli update

# Watch for changes and auto-update (real-time)
python -m code_indexer.cli watch
```

## Usage

### Commands

#### Initialize Project
```bash
python -m code_indexer.cli init [--codebase-dir PATH] [--force]
```

#### Setup Services
```bash
python -m code_indexer.cli setup [--model MODEL_NAME] [--force-recreate]
```

#### Index Codebase
```bash
python -m code_indexer.cli index [--clear] [--batch-size 50]
```

#### Search Code
```bash
python -m code_indexer.cli query "search terms" [OPTIONS]

Options:
  --limit, -l INTEGER     Number of results (default: 10)
  --language TEXT         Filter by programming language
  --path TEXT            Filter by file path pattern
  --min-score FLOAT      Minimum similarity score (0.0-1.0)
```

#### Check Status
```bash
python -m code_indexer.cli status
```

#### Cleanup
```bash
python -m code_indexer.cli clean [--remove-data]
```

### Search Examples

```bash
# Find authentication-related code
python -m code_indexer.cli query "user authentication login"

# Find React components
python -m code_indexer.cli query "component props state" --language tsx

# Find server-side database code
python -m code_indexer.cli query "database query" --path server

# High-precision search
python -m code_indexer.cli query "error handling" --min-score 0.8

# Get more results
python -m code_indexer.cli query "api endpoint" --limit 20
```

### Incremental Updates

Keep your index current as your codebase evolves:

```bash
# Manual update - indexes only changed files since last index
python -m code_indexer.cli update

# Update with custom timestamp
python -m code_indexer.cli update --since "2024-01-01T00:00:00"

# Real-time watching - automatically updates index when files change
python -m code_indexer.cli watch

# Watch with custom debounce (wait time before processing changes)
python -m code_indexer.cli watch --debounce 5.0
```

**How it works:**
- `update` compares file modification times against the last index timestamp
- Automatically detects and removes deleted files from the index
- Only re-indexes files that have actually changed, making updates fast
- `watch` mode uses file system events for real-time updates
- Batches changes and waits for a debounce period to avoid excessive processing

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

**Efficient resource usage:**
- **Memory**: Bounded change buffer prevents memory leaks during high-activity periods
- **CPU**: Only processes actual changes, not entire codebase
- **I/O**: Batched database operations reduce network overhead
- **AI**: Embedding generation only for changed content

**Scalability considerations:**
- **Large codebases**: Recursive monitoring scales to thousands of files
- **High activity**: Debouncing handles rapid development cycles
- **Network resilience**: Batch operations reduce API call frequency

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

**Ideal for:**
- **Active development**: Keep search current during coding sessions
- **Team environments**: Shared codebase with multiple contributors
- **Large codebases**: Incremental updates much faster than full re-indexing
- **CI/CD integration**: Continuous index updates in development environments

**Best practices:**
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

The watcher provides a seamless "live sync" experience, ensuring your semantic search index is always current with your latest code changes, making development more efficient and search results more relevant.

## Sharing Indexes with Git LFS

Code Indexer supports sharing vector databases across teams using Git LFS, compatible with both **GitHub** and **GitLab**:

### Setup Git LFS (One-time)
```bash
# Install Git LFS (if not already installed)
# On RHEL/Rocky/Fedora: dnf install git-lfs
# On Ubuntu/Debian: apt install git-lfs
# On macOS: brew install git-lfs
git lfs install

# Database files are automatically tracked via included .gitattributes
# Git hooks for clean commits and branch changes
python -m code_indexer.cli git-hooks --install
```

### Workflow
```bash
# Commit and push your index to share with team
git add .code-indexer/
git commit -m "Update semantic search index"
git push origin main

# Team members get latest index
git pull origin main
git lfs pull  # Download large files
```

### Cross-Platform Compatibility
- **Same .gitattributes**: Works on both GitHub and GitLab
- **Universal commands**: Same `git lfs` commands across platforms
- **Easy migration**: Move repositories between platforms seamlessly
- **Team flexibility**: Mix of GitHub/GitLab users in same project

### Git Hooks for Clean Commits

```bash
# Install hooks to ensure database integrity
python -m code_indexer.cli git-hooks --install

# Remove hooks if needed
python -m code_indexer.cli git-hooks --uninstall
```

**What the hooks do:**
- **pre-commit**: Flush Qdrant database before commits (ensures clean state)
- **pre-checkout**: Stop Qdrant before branch changes (prevents file locks)
- **post-checkout**: Restart Qdrant after branch changes (ready for new branch)

### Benefits
- **Branch-specific indexes**: Each branch has its own vector database state
- **Clean commits**: Database buffers are flushed before committing
- **No file conflicts**: Automatic Qdrant management during Git operations
- **Faster onboarding**: New team members get pre-built index
- **Consistent search**: Everyone searches same codebase state
- **Reduced compute**: Share AI embeddings instead of regenerating
- **Version control**: Track index changes alongside code changes

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
    "timeout": 30
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

## Multi-Project Support

Code Indexer automatically supports indexing multiple projects simultaneously without port conflicts:

### Automatic Project Detection
- **Git Repository Name**: Uses the git repository name from `git remote get-url origin`
- **Directory Name**: Falls back to the current directory name if not a git repository
- **Sanitization**: Converts names to Docker-compatible format (lowercase, hyphens only)

### Isolated Containers
Each project gets its own isolated containers:
```bash
# Project: my-app
code-ollama-my-app     # Ollama service for my-app
code-qdrant-my-app     # Qdrant service for my-app

# Project: api-server  
code-ollama-api-server # Ollama service for api-server
code-qdrant-api-server # Qdrant service for api-server
```

### Internal Communication
- **No Port Conflicts**: Containers don't expose ports to the host
- **Docker Networks**: Each project uses its own isolated network
- **Container-to-Container**: Communication happens via `docker exec` commands

### Benefits
- **Work on Multiple Projects**: Index and search different codebases simultaneously
- **No Resource Conflicts**: Each project has dedicated AI models and vector databases
- **Clean Isolation**: Projects can't interfere with each other's data or configuration
- **Zero Configuration**: Project names are detected automatically

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
docker logs code-ollama
docker logs code-qdrant

# Restart services
python -m code_indexer.cli clean
python -m code_indexer.cli setup
```

### Search Not Working
```bash
# Check service status
python -m code_indexer.cli status

# Re-index if needed
python -m code_indexer.cli index --clear
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