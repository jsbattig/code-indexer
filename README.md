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
- **Branch Topology Aware** - Smart incremental indexing across git branches with O(δ) complexity
- **Working Directory Support** - Index staged and unstaged files for comprehensive coverage
- **Filtering** - Filter by language, path, similarity score
- **CLI Interface** - Terminal interface with progress bars
- **Configurable** - Configuration options for different use cases
- **Multi-Project Support** - Index multiple projects simultaneously without port conflicts
- **Auto Project Detection** - Derives project names from git repositories or folder names
- **AI-Powered Analysis** - Integrates with Claude CLI for intelligent code analysis using RAG

## Quick Start

### Installation

Choose an installation method:

#### Option 1: Using pipx
```bash
# Install pipx if not already installed (Ubuntu/Debian)
sudo apt update && sudo apt install pipx

# Install code-indexer using pipx (from latest release)
pipx install https://github.com/jsbattig/code-indexer/releases/download/v0.1.0.0/code_indexer-0.1.0.0-py3-none-any.whl

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
pip install https://github.com/jsbattig/code-indexer/releases/download/v0.1.0.0/code_indexer-0.1.0.0-py3-none-any.whl

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

# Step 1: Initialize configuration (OPTIONAL - start creates defaults if skipped)
code-indexer init

# Step 2: Start services (creates default config if init was skipped)
code-indexer start

# Step 3: Index your codebase
code-indexer index

# Step 4: Search your code
code-indexer query "authentication logic"

# Step 5: AI-powered code analysis (requires Claude CLI)
# Install Claude CLI: https://docs.anthropic.com/en/docs/claude-code
code-indexer claude "How does authentication work in this app?"

# Smart incremental indexing (automatically detects changes)
code-indexer index

# Watch for changes and auto-update (real-time)
code-indexer watch
```

**Alternative flows:**

```bash
# Quick start (skip init - uses defaults: Ollama + default settings)
code-indexer start
code-indexer index
code-indexer query "search terms"

# VoyageAI configuration (cloud embeddings)
export VOYAGE_API_KEY="your-api-key"
code-indexer init --embedding-provider voyage-ai --embedding-model voyage-code-3
code-indexer start
code-indexer index

# Interactive configuration
code-indexer init --interactive  # Guided configuration with prompts
code-indexer start
```

## Usage

> **🔥 Tip**: Use the short alias `cidx` instead of `code-indexer` for faster typing!  
> Examples: `cidx start`, `cidx index`, `cidx query "search terms"`

### Commands

#### Start Services
```bash
code-indexer start [--model MODEL_NAME] [--force-recreate] [--parallel-requests N] [--max-models N] [--queue-size N]

# Performance Examples:
code-indexer start --parallel-requests 2 --max-models 1  # Higher throughput
code-indexer start --queue-size 1024                    # Larger request queue
code-indexer start --force-docker                       # Force Docker instead of Podman
```

#### Index Codebase
```bash
code-indexer index [--clear] [--reconcile] [--batch-size 50]

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
  --accuracy TEXT        Search accuracy profile: fast, balanced (default), high
  --quiet, -q             Quiet mode - only show results, no headers
```

#### AI-Powered Code Analysis
```bash
code-indexer claude "your question about the code" [OPTIONS]

Options:
  --limit, -l INTEGER          Number of semantic search results (default: 10)
  --context-lines, -c INTEGER  Lines of context around matches (default: 500)
  --language TEXT              Filter by programming language
  --path TEXT                  Filter by file path pattern
  --min-score FLOAT            Minimum similarity score (0.0-1.0)
  --accuracy TEXT              Search accuracy profile: fast, balanced (default), high
  --max-turns INTEGER          Maximum Claude conversation turns (default: 5)
  --no-explore                 Disable file exploration in Claude prompt
  --no-stream                  Disable streaming (show results all at once)
  --show-claude-plan           Show real-time tool usage and generate summary of Claude's problem-solving approach
  --quiet, -q                  Quiet mode - only show results, no headers
```

#### Check Status
```bash
code-indexer status [--force-docker]
```


#### Watch for Changes
```bash
code-indexer watch [--debounce FLOAT] [--batch-size INT] [--initial-sync]
```

#### Database Management
```bash
code-indexer optimize    # Optimize vector database storage and performance
code-indexer schema      # Check and manage database schema version
code-indexer schema --migrate  # Perform schema migration if needed
```

#### Cleanup
```bash
code-indexer clean-data [--all-projects]  # Clear project data without stopping containers
code-indexer stop                         # Stop services while preserving data  
code-indexer uninstall                    # Complete removal of containers and data
```

### Search Examples

```bash
# Find authentication-related code
code-indexer query "user authentication login"

# Find React components
code-indexer query "component props state" --language typescript

# Find server-side database code
code-indexer query "database query" --path "*/server/*"

# High-precision search
code-indexer query "error handling" --min-score 0.8

# Get more results
code-indexer query "api endpoint" --limit 20

# Quiet mode - just score, path, and content
code-indexer query "function definition" --quiet

# Fast search for quick exploration
code-indexer query "caching mechanisms" --accuracy fast --limit 30

# High-accuracy search for precise analysis
code-indexer query "security vulnerability" --accuracy high --min-score 0.8
```

### Claude AI Analysis Examples

```bash
# Ask about code architecture
code-indexer claude "How does authentication work in this application?"

# Get implementation guidance
code-indexer claude "How do I add a new API endpoint?" --language python

# Debug issues
code-indexer claude "Why might this error handling pattern fail?"

# Analyze specific areas
code-indexer claude "Explain the database schema design" --path */models/*

# Security analysis
code-indexer claude "Find potential security vulnerabilities" --min-score 0.8

# Code patterns and best practices
code-indexer claude "What design patterns are used here?"

# Quiet mode - just the analysis, no headers or metadata
code-indexer claude "Explain this function" --quiet

# High-accuracy analysis for complex code
code-indexer claude "Analyze optimization opportunities" --accuracy high --language cpp

# Debug mode - show the prompt that would be sent to Claude (for prompt iteration)
code-indexer claude "Test question" --dry-run-show-claude-prompt

# Show Claude's problem-solving approach with tool usage tracking
code-indexer claude "How does authentication work?" --show-claude-plan
```

## Claude AI Integration

Code Indexer integrates with Claude CLI to provide AI-powered code analysis using RAG (Retrieval-Augmented Generation). This combines semantic search with Claude's advanced reasoning to answer complex questions about your codebase.

### Setup Claude Integration

```bash
# Install Claude CLI
# Follow instructions at: https://docs.anthropic.com/en/docs/claude-code

# Ensure your codebase is indexed
code-indexer start
code-indexer index

# Start asking questions about your code
code-indexer claude "How does this application handle user authentication?"
```

### How It Works

1. **Semantic Search**: Your question is converted to a vector embedding and searched against your indexed codebase
2. **Context Extraction**: Relevant code sections are extracted with configurable context (default: 500 lines around each match)
3. **RAG Analysis**: The context and your question are sent to Claude for intelligent analysis
4. **Enhanced Exploration**: Claude can perform additional semantic searches to explore related concepts

### Features

- **Natural Language Queries**: Ask questions in plain English about your code
- **Code-Aware Responses**: Claude understands code structure, patterns, and relationships
- **Streaming Support**: Responses stream by default (use `--no-stream` to disable)
- **Smart Context**: Automatically extracts relevant code with proper context
- **File Exploration**: Claude can explore referenced files for comprehensive analysis
- **Git-Aware**: Respects your current branch and project context

### Claude Analysis Capabilities

- **Architecture Understanding**: "How is this application structured?"
- **Implementation Guidance**: "How do I add a new feature to the user management system?"
- **Code Review**: "What are potential issues with this error handling approach?"
- **Security Analysis**: "Find potential security vulnerabilities in authentication"
- **Best Practices**: "What design patterns are used and how can they be improved?"
- **Debugging Help**: "Why might this code be causing memory leaks?"
- **Cross-file Analysis**: "How do these components interact across the codebase?"

### Claude Problem-Solving Insights

Code Indexer now includes real-time tool usage tracking to show how Claude approaches your code analysis:

```bash
# Enable real-time tool tracking and summary generation
code-indexer claude "How does authentication work?" --show-claude-plan
```

**What You'll See:**
- **Real-time Status Line**: Live updates showing Claude's current activity
- **Visual Cues**: 🔍✨ for semantic search (cidx), 😞 for text search (grep)  
- **Tool Usage Counters**: Running count of different search methods used
- **Comprehensive Summary**: Detailed analysis of Claude's problem-solving approach

**Example Output:**
```
🔍✨ Semantic search: 'authentication' | 📖 Reading: src/auth.py | 🔍✨ 3 😞 1

🤖 Claude's Problem-Solving Approach
────────────────────────────────────────────────────────────────────────────────

✅ **Preferred Approach**: Used semantic search (3x) with `cidx` for intelligent code discovery
   • Semantic search: 'authentication logic'
   • Semantic search: 'user login flow'
   • Semantic search: 'session management'

📖 **Code Exploration**: Accessed 5 files for detailed analysis

⏱️ **Performance**: Average tool execution time 1.2s

## 📊 Tool Usage Statistics
• **Total Operations**: 8
• **Tools Used**: Bash, Read, Grep
• **Completed Successfully**: 8
• **Average Duration**: 1.20s

**Operation Breakdown**:
• 🔍✨ cidx_semantic_search: 3
• 📄 file_operation: 5
```

### Advanced Options

```bash
# Focus on specific areas
code-indexer claude "Explain the API design" --path */api/* --language python

# High-precision analysis
code-indexer claude "Find security issues" --min-score 0.9 --context-lines 800

# Long analysis with tool tracking (streaming by default)
code-indexer claude "Perform a complete architecture review" --show-claude-plan --max-turns 10

# Disable file exploration for focused answers
code-indexer claude "What does this function do?" --no-explore --limit 3

# Show the exact prompt that would be sent to Claude (debugging/iteration)
code-indexer claude "How does this work?" --dry-run-show-claude-prompt
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

## Branch Topology-Aware Indexing

Code Indexer now features advanced branch topology understanding for efficient incremental indexing across git branches. This enables O(δ) complexity indexing that only processes changed files when switching branches.

### How It Works

When you switch between git branches, Code Indexer automatically:

1. **Analyzes Branch Changes**: Compares the current branch with the previous branch to identify:
   - Files that changed between branches (require full reindexing)
   - Files that are unchanged but need branch metadata updates
   - Staged files (uncommitted changes in the index)
   - Unstaged files (working directory modifications)

2. **Smart Incremental Processing**: 
   - **Reindexes only changed files** between branches for content updates
   - **Batch updates metadata** for unchanged files (fast operation)
   - **Indexes working directory files** with special status tracking
   - **Maintains branch ancestry** for topology-aware queries

3. **Performance Optimization**:
   - Uses git merge-base analysis for efficient change detection
   - Leverages Qdrant payload indexes for fast branch filtering
   - Implements batch git operations to reduce subprocess overhead
   - Achieves O(δ) complexity instead of O(n) for branch switches

### Branch-Aware Querying

Searches automatically include branch topology context:

```bash
# Search includes current branch + ancestry + working directory
code-indexer query "authentication logic"

# Claude analysis respects branch context
code-indexer claude "How does auth work in this feature branch?"
```

### Working Directory Support

The indexer now tracks and indexes:

- **Staged files**: Changes added to git index but not committed
- **Unstaged files**: Working directory modifications not yet staged
- **File change types**: Added, modified, deleted, renamed

### Branch Lifecycle Management

```bash
# Create feature branch and add files
git checkout -b feature/new-auth
echo "def new_auth(): pass" > new_auth.py
git add new_auth.py && git commit -m "Add new auth"

# Smart indexing only processes the new file
code-indexer index

# Query sees both main branch code and new feature code
code-indexer query "authentication"

# Switch back to main
git checkout main
code-indexer index  # Smart metadata updates only

# Delete feature branch - associated data is cleaned up
git branch -D feature/new-auth
```

### Advanced Features

- **Branch Ancestry Tracking**: Maintains parent-child relationships for topology queries
- **Working Directory Indexing**: Searches work-in-progress code before committing
- **Metadata Schema Evolution**: Backwards-compatible schema versioning
- **Performance Monitoring**: Detailed statistics on indexing operations
- **Batch Operations**: Optimized git operations for large codebases

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
- **Automated integration**: Continuous index updates in development environments

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
    "py", "js", "ts", "tsx", "java", "c", "cpp", "h", "hpp", "go", "rs", "rb",
    "php", "sh", "bash", "html", "css", "md", "json", "yaml", "yml", "toml",
    "sql", "swift", "kt", "scala", "dart", "vue", "jsx"
  ],
  "exclude_dirs": [
    "node_modules", "venv", "__pycache__", ".git", "dist", "build",
    "target", ".idea", ".vscode", ".gradle", "bin", "obj", "coverage",
    ".next", ".nuxt", "dist-*", ".code-indexer"
  ],
  "indexing": {
    "chunk_size": 1500,
    "chunk_overlap": 150,
    "max_file_size": 1048576,
    "index_comments": true
  },
  "embedding_provider": "ollama",
  "ollama": {
    "host": "http://localhost:11434",
    "model": "nomic-embed-text",
    "timeout": 30,
    "num_parallel": 1,
    "max_loaded_models": 1,
    "max_queue": 512
  },
  "voyage_ai": {
    "model": "voyage-code-3",
    "parallel_requests": 8,
    "batch_size": 128,
    "requests_per_minute": 300,
    "tokens_per_minute": null,
    "max_retries": 3,
    "retry_delay": 1.0
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

Configure Ollama performance through start command parameters:

- **--parallel-requests**: Number of parallel requests Ollama can handle (default: 1)
  - Config setting: `num_parallel`
- **--max-models**: Maximum models to keep loaded in memory (default: 1)
  - Config setting: `max_loaded_models`
- **--queue-size**: Maximum request queue size (default: 512)
  - Config setting: `max_queue`

```bash
# Conservative (low resource usage)
code-indexer start --parallel-requests 1 --max-models 1 --queue-size 256

# Balanced (recommended for most users)
code-indexer start --parallel-requests 2 --max-models 1 --queue-size 512

# High throughput (powerful machines)
code-indexer start --parallel-requests 4 --max-models 1 --queue-size 1024
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

# Or use interactive mode for guided configuration
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
- **Model Tracking**: Search results include embedding model metadata
- **Migration**: Gradual migration between providers without losing existing data

```bash
# Different projects can use different providers and models
# Provider/model information is automatically tracked in metadata

# Check current project's model configuration
code-indexer status
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
│   ├── config.json          # Project configuration
│   ├── README.md            # Configuration documentation
│   └── metadata.json        # Index metadata (optional)
├── .gitignore              # Add .code-indexer/ to ignore
└── (your project files)

~/.code-indexer/global/      # Global shared data directory
├── qdrant/                  # Vector database storage
├── ollama/                  # Ollama model data
└── logs/                    # Operation logs
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

# Option 1: Modern approach (recommended)
pip install -e ".[dev]"

# Option 2: Traditional requirements.txt approach
pip install -r requirements-dev.txt
pip install -e .

# Install pre-commit hooks
pre-commit install
```

#### Quick Development Setup

For a faster setup with traditional requirements files:

```bash
# Install all development dependencies
pip install -r requirements-dev.txt

# Install the package in editable mode
pip install -e .
```

### Run Tests

```bash
pytest
pytest --cov=code_indexer  # With coverage
```

### Code Quality

```bash
# Run all linting checks (recommended)
./lint.sh

# Or run individual tools
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
code-indexer clean-data
code-indexer start
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

**Local Processing (Ollama):**
- All processing happens locally
- No code sent to external services
- Models run in isolated containers

**Cloud Processing (VoyageAI - Optional):**
- Code sent to VoyageAI API for embedding generation
- Follow VoyageAI's privacy policy and terms of service

**Both Providers:**
- Embeddings stored locally in Qdrant
- No persistent storage of code on external services

## License

MIT License

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
