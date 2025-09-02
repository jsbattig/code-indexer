# Code Indexer

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

## Version 4.0.0

Multi-user server functionality with FastAPI, JWT authentication, and role-based access control.

## Features

### Core Search Capabilities
- **Semantic Search** - Find code by meaning using vector embeddings and fixed-size chunking
- **Multiple Providers** - Local (Ollama) or cloud (VoyageAI) embeddings  
- **Smart Indexing** - Incremental updates, git-aware, multi-project support
- **Search Filtering** - Filter by programming language, file paths, file extensions, and similarity scores
- **Multi-Language Support** - Universal text processing for Python, JavaScript, TypeScript, Java, C#, Go, Kotlin, Groovy, Pascal/Delphi, SQL, C, C++, Rust, Swift, Ruby, Lua, HTML, CSS, YAML, XML

### Multi-User Server
- **REST API** - FastAPI-based web service
- **JWT Authentication** - Token-based authentication
- **User Management** - Admin-controlled user creation and role assignment
- **Golden Repositories** - Centralized code repository management
- **Repository Activation** - Copy-on-Write cloning for user workspaces
- **Semantic Query Endpoints** - Search with filtering capabilities
- **Background Processing** - Async job system for heavy operations
- **Health Monitoring** - System status and performance metrics

### Traditional CLI Interface
- **CLI Interface** - Simple commands with progress indicators
- **AI Analysis** - Integrates with Claude CLI for code analysis with semantic search
- **Privacy Options** - Full local processing or cloud for better performance

## Installation

### pipx (Recommended)
```bash
# Install the package
pipx install git+https://github.com/jsbattig/code-indexer.git@v4.0.0.0

# Setup global registry (standalone command - requires sudo)
cidx setup-global-registry
```

### pip with virtual environment
```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git@v4.0.0.0

# Setup global registry (standalone command - requires sudo)
code-indexer setup-global-registry
```

### Requirements

- **Python 3.9+**
- **Container Engine**: Docker or Podman (for containerized services)
- **Memory**: 4GB+ RAM recommended
- **Disk Space**: ~500MB for base containers + vector data storage

### Docker vs Podman Support

Code Indexer supports both Docker and Podman container engines:

- **Auto-detection**: Automatically detects and uses available container engine
- **Podman preferred**: Uses Podman by default when available (better rootless support)
- **Force Docker**: Use `--force-docker` flag to force Docker usage
- **Rootless containers**: Fully supports rootless container execution

**Global Port Registry**: The `setup-global-registry` command configures system-wide port coordination at `/var/lib/code-indexer/port-registry`, preventing conflicts when running multiple code-indexer projects simultaneously. This is required for proper multi-project support.

## Quick Start

```bash
# 1. Setup global registry (once per system)
cidx setup-global-registry

# 2. Navigate to your project
cd /path/to/your/project

# 3. Start services and index code
code-indexer start     # Auto-creates config if needed
code-indexer index     # Smart incremental indexing

# 4. Search semantically
code-indexer query "authentication logic"

# 5. Search with filtering
code-indexer query "user" --language python --min-score 0.7
code-indexer query "save" --path "*/models/*" --limit 20

# 6. AI-powered analysis (requires Claude CLI)
code-indexer claude "How does auth work in this app?"
```

### Alternative: Custom Configuration

```bash
# Optional: Initialize with custom settings first
code-indexer init --embedding-provider voyage-ai --max-file-size 2000000
code-indexer start
code-indexer index
```

## Multi-User Server

The CIDX server provides a FastAPI-based multi-user semantic code search service with JWT authentication and role-based access control.

### Server Quick Start

```bash
# 1. Install and setup (same as CLI)
pipx install git+https://github.com/jsbattig/code-indexer.git@v4.0.0.0
cidx setup-global-registry

# 2. Start the server
cd /path/to/your/server/data/directory
python -m src.code_indexer.server.main --host 127.0.0.1 --port 8090

# 3. Access the API documentation
# Visit: http://localhost:8090/docs
```

### Server Features

- **JWT Authentication**: Token-based authentication system
- **User Roles**: Admin, power_user, and normal_user with different permissions
- **Golden Repositories**: Centralized repository management
- **Repository Activation**: Copy-on-Write cloning for user workspaces  
- **Advanced Search**: Semantic search with file extension filtering
- **Background Jobs**: Async processing for indexing and heavy operations
- **Health Monitoring**: System status and performance endpoints

### API Endpoints Overview

- **Authentication**: `POST /auth/login` - JWT token authentication
- **User Management**: `POST /users/create` - Admin-only user creation
- **Golden Repos**: `GET|POST|DELETE /repositories/golden/*` - Repository management
- **Activation**: `POST|DELETE /repositories/activate/*` - User repository activation
- **Search**: `POST /query/*` - Semantic search with filtering
- **Jobs**: `GET /jobs/*` - Background job status monitoring
- **Health**: `GET /health` - System health and metrics

### Authentication & Roles

```bash
# Login and get JWT token
curl -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Use token in subsequent requests
curl -X GET http://localhost:8090/repositories/golden \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Default Users** (for testing):
- **Admin**: `admin` / `admin123` - Full system access
- **Power User**: `power_user` / `power123` - Repository and search access
- **Normal User**: `normal_user` / `normal123` - Search-only access

### Example Usage

```bash
# 1. Login as admin
TOKEN=$(curl -s -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | jq -r '.access_token')

# 2. Add a golden repository
curl -X POST http://localhost:8090/repositories/golden \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"repository_path": "/path/to/your/repo", "alias": "my-repo"}'

# 3. Activate repository for user
curl -X POST http://localhost:8090/repositories/activate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"golden_alias": "my-repo", "user_alias": "my-workspace"}'

# 4. Semantic search
curl -X POST http://localhost:8090/query/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query_text": "authentication logic", "file_extensions": [".py", ".js"]}'
```

## Complete CLI Reference

### Setup Commands

```bash
# Global system setup
code-indexer setup-global-registry              # Setup global port registry (requires sudo)
code-indexer setup-global-registry --test-access --quiet  # Test registry access

# Project initialization
code-indexer init                               # Initialize with default settings
code-indexer init --embedding-provider voyage-ai  # Use VoyageAI instead of Ollama
code-indexer init --max-file-size 2000000       # Set 2MB file size limit
code-indexer init --setup-global-registry       # Init + setup registry (legacy)
code-indexer init --create-override-file        # Create .code-indexer-override.yaml
```

### Service Management

```bash
# Service lifecycle
code-indexer start                      # Start services (smart detection)
code-indexer start --force-docker       # Force Docker instead of Podman
code-indexer start --force-recreate     # Force recreate containers
code-indexer start --quiet              # Silent mode
code-indexer start -m all-minilm-l6-v2  # Different Ollama model

code-indexer status                     # Check service status
code-indexer status --force-docker      # Check Docker status specifically

code-indexer stop                       # Stop services (preserve data)
code-indexer stop --force-docker        # Stop Docker services specifically
```

### Indexing Commands

```bash
# Standard indexing
code-indexer index                      # Smart incremental indexing
code-indexer index --clear              # Force full reindex
code-indexer index --reconcile          # Reconcile disk vs database
code-indexer index --detect-deletions   # Handle deleted files
code-indexer index --batch-size 25      # Custom batch size
code-indexer index --files-count-to-process 100  # Limit file count
code-indexer index --threads 4          # Custom thread count

# Real-time monitoring
code-indexer watch                      # Git-aware file watching
code-indexer watch --debounce 5.0       # Custom debounce delay
code-indexer watch --initial-sync       # Full sync before watching
```

### Search Commands

```bash
# Basic search
code-indexer query "search terms"      # Semantic search
code-indexer query "auth" --limit 20   # More results
code-indexer query "function" --quiet  # Only results, no headers

# Advanced filtering
code-indexer query "user" --language python  # Filter by language
code-indexer query "save" --path "*/models/*" # Filter by path pattern
code-indexer query "function" --min-score 0.7  # Higher confidence matches
code-indexer query "database" --limit 15     # More results
code-indexer query "test" --min-score 0.8     # High-confidence matches

# Short alias
cidx query "search terms"              # Same as code-indexer query
```

### AI Analysis Commands

```bash
# Standard analysis
code-indexer claude "How does auth work?"     # AI-powered analysis
code-indexer claude "Debug this" --limit 15   # Custom search limit
code-indexer claude "Analyze" --context-lines 200  # More context
code-indexer claude "Quick check" --quiet     # Minimal output
code-indexer claude "Review code" --no-stream # No streaming output

# Advanced options
code-indexer claude "Test" --include-file-list  # Include project file list
code-indexer claude "Legacy" --rag-first       # Use legacy RAG-first approach

# Debugging
code-indexer claude "Test" --dry-run-show-claude-prompt  # Show prompt without execution
code-indexer claude "Analyze" --show-claude-plan        # Show tool usage tracking
```

### Data Management Commands

```bash
# Quick cleanup (recommended)
code-indexer clean-data                 # Clear current project data
code-indexer clean-data --all-projects  # Clear all projects data
code-indexer clean-data --force-docker  # Use Docker for cleanup

# Complete removal
code-indexer uninstall                  # Remove current project completely
code-indexer uninstall --force-docker   # Use Docker for removal
code-indexer uninstall --wipe-all       # DANGEROUS: Complete system wipe

# Migration and maintenance
code-indexer clean-legacy               # Migrate from legacy containers
code-indexer optimize                   # Optimize vector database
code-indexer force-flush                # Force flush to disk (deprecated)
code-indexer force-flush --collection mycoll  # Flush specific collection
```

### Configuration Commands

```bash
# Configuration repair
code-indexer fix-config                 # Fix corrupted configuration
code-indexer fix-config --dry-run       # Preview fixes
code-indexer fix-config --verbose       # Detailed fix information
code-indexer fix-config --force         # Apply without confirmation

# Claude integration setup
code-indexer set-claude-prompt          # Set CIDX instructions in project CLAUDE.md
code-indexer set-claude-prompt --user-prompt  # Set in global ~/.claude/CLAUDE.md
```

### Global Options

```bash
# Available on most commands
--force-docker          # Force Docker instead of Podman
--verbose, -v           # Verbose output
--config, -c PATH       # Custom config file path
--path, -p PATH         # Custom project directory

# Special global options
--use-cidx-prompt       # Generate AI integration prompt
--format FORMAT         # Output format (text, markdown, compact, comprehensive)
--output FILE           # Save output to file
--compact               # Generate compact prompt
```

### Command Aliases

- `cidx` → `code-indexer` (shorter alias for all commands)
- Use `cidx` for faster typing: `cidx start`, `cidx query "search"`, etc.

## Configuration

### Embedding Providers

**Ollama (Default - Local)**
```bash
code-indexer init --embedding-provider ollama
```

**VoyageAI (Cloud)**
```bash
export VOYAGE_API_KEY="your-key"
code-indexer init --embedding-provider voyage-ai
```

**Performance Status Indicators (VoyageAI only)**

During indexing, VoyageAI shows real-time performance status in the progress bar:
- ⚡ **Full speed** - Running at maximum throughput
- 🔴 **Server throttling** - VoyageAI API rate limits detected

Example: `15/100 files (15%) | 8.3 emb/s ⚡ | 8 threads | main.py`

The system runs at full speed by default. If rate limits are encountered, an error is displayed asking to reduce parallel_requests.

### Configuration File
Configuration is stored in `.code-indexer/config.json`:
- `file_extensions`: File types to index
- `exclude_dirs`: Directories to skip  
- `embedding_provider`: ollama or voyage-ai (determines chunk size automatically)
- `max_file_size`: Maximum file size in bytes (default: 1MB)
- `chunk_size`: Legacy setting (ignored, chunker uses model-aware sizing)
- `chunk_overlap`: Legacy setting (ignored, chunker uses 15% of chunk size)

### Model-Aware Chunking Strategy

Code Indexer uses a **model-aware fixed-size chunking approach** optimized for different embedding models:

**How it works:**
- **Model-optimized chunk sizes**: Automatically selects optimal chunk size based on embedding model capabilities
- **Consistent overlap**: 15% overlap between adjacent chunks (across all models)
- **Simple arithmetic**: Next chunk starts at (chunk_size - overlap_size) from current start position
- **Token optimization**: Uses larger chunk sizes for models with higher token capacity

**Model-Specific Chunk Sizes:**
- **voyage-code-3**: 4,096 characters (leverages 32K token capacity)
- **voyage-code-2**: 4,096 characters (leverages 16K token capacity)  
- **voyage-large-2**: 4,096 characters (leverages large context capacity)
- **nomic-embed-text**: 2,048 characters (512 tokens - Ollama limitation)
- **Unknown models**: 1,000 characters (conservative fallback)

**Example chunking (voyage-code-3):**
```
Chunk 1: characters 0-4095     (4096 chars)
Chunk 2: characters 3482-7577  (4096 chars, overlaps 614 chars with Chunk 1) 
Chunk 3: characters 6964-11059 (4096 chars, overlaps 614 chars with Chunk 2)
```

**Benefits:**
- **Model optimization**: Uses larger chunks for high-capacity models (VoyageAI: 4096, Ollama: 2048)
- **Better context**: More complete code sections per chunk
- **Efficiency**: Fewer total chunks reduce storage requirements
- **Model utilization**: Takes advantage of each model's token capacity

## Supported Languages

Code Indexer provides fixed-size chunking with intelligent text processing for all supported languages:

| Language | File Extensions | Text Processing |
|----------|----------------|-------------------|
| **Python** | `.py` | Fixed-size chunks with consistent overlap |
| **JavaScript** | `.js`, `.jsx` | Fixed-size chunks with consistent overlap |
| **TypeScript** | `.ts`, `.tsx` | Fixed-size chunks with consistent overlap |
| **Java** | `.java` | Fixed-size chunks with consistent overlap |
| **C#** | `.cs` | Fixed-size chunks with consistent overlap |
| **Go** | `.go` | Fixed-size chunks with consistent overlap |
| **Kotlin** | `.kt`, `.kts` | Fixed-size chunks with consistent overlap |
| **Groovy** | `.groovy`, `.gradle`, `.gvy`, `.gy` | Fixed-size chunks with consistent overlap |
| **Pascal/Delphi** | `.pas`, `.pp`, `.dpr`, `.dpk`, `.inc` | Fixed-size chunks with consistent overlap |
| **SQL** | `.sql` | Fixed-size chunks with consistent overlap |
| **C** | `.c`, `.h` | Fixed-size chunks with consistent overlap |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | Fixed-size chunks with consistent overlap |
| **Rust** | `.rs` | Fixed-size chunks with consistent overlap |
| **Swift** | `.swift` | Fixed-size chunks with consistent overlap |
| **Ruby** | `.rb`, `.rake`, `.gemspec` | Fixed-size chunks with consistent overlap |
| **Lua** | `.lua` | Fixed-size chunks with consistent overlap |
| **HTML** | `.html`, `.htm` | Fixed-size chunks with consistent overlap |
| **CSS** | `.css`, `.scss`, `.sass` | Fixed-size chunks with consistent overlap |
| **YAML** | `.yaml`, `.yml` | Fixed-size chunks with consistent overlap |
| **XML** | `.xml`, `.xsd`, `.xsl`, `.xslt` | Fixed-size chunks with consistent overlap |

**Model-Aware Chunking Benefits:**
- **Optimized chunk sizes**: Each model gets its optimal chunk size (voyage-code-3: 4096, nomic-embed-text: 2048)
- **Consistent overlap**: 15% overlap between adjacent chunks (across all models)
- **Fast processing**: No complex parsing overhead, pure arithmetic operations
- **Complete search results**: Full code sections without truncation
- **Model efficiency**: Leverages each embedding model's capabilities

### Containerized Services

Code Indexer uses the following containerized services:

- **Qdrant**: Vector database for storing code embeddings
- **Ollama** (optional): Local language model service for embeddings when not using VoyageAI
- **Data Cleaner**: Containerized service for cleaning root-owned files during data removal operations

## Development

### Developer Onboarding

Code Indexer uses a comprehensive test infrastructure organized into three main categories for optimal maintainability and execution speed:

#### Test Directory Structure

```bash
tests/
├── unit/              # Fast unit tests organized by functionality
│   ├── parsers/       # Language parser tests
│   ├── chunking/      # Text chunking logic tests
│   ├── config/        # Configuration management tests
│   ├── services/      # Service layer unit tests
│   ├── cli/           # CLI unit tests
│   ├── git/           # Git operations tests
│   ├── infrastructure/ # Core infrastructure tests
│   └── bugfixes/      # Bug fix regression tests
├── integration/       # Integration tests with real services
│   ├── performance/   # Performance and throughput tests
│   ├── docker/        # Docker integration tests
│   ├── multiproject/  # Multi-project workflow tests
│   ├── services/      # Service integration tests
│   └── cli/           # CLI integration tests
├── e2e/              # End-to-end workflow tests
│   ├── git_workflows/ # Git workflow e2e tests
│   ├── payload_indexes/ # Payload indexing e2e tests
│   ├── providers/     # Provider switching tests
│   ├── semantic_search/ # Search capability tests
│   ├── claude_integration/ # Claude integration tests
│   ├── display/       # UI and display tests
│   └── infrastructure/ # Infrastructure e2e tests
├── shared/           # Shared test utilities and fixtures
└── fixtures/         # Test data and fixtures
```

#### Test Safety and Container Categories

Tests are categorized by container requirements using pytest markers:

- **`@pytest.mark.shared_safe`** - Can use either Docker or Podman containers, data-only operations
- **`@pytest.mark.docker_only`** - Requires Docker-specific features or configurations  
- **`@pytest.mark.podman_only`** - Requires Podman-specific features or rootless containers
- **`@pytest.mark.destructive`** - Manipulates containers directly, requires isolation

#### Dual-Container Architecture

Code Indexer supports both Docker and Podman with intelligent container management:

- **Production containers**: `code-indexer-ollama`, `code-indexer-qdrant` (ports 11434, 6333)
- **Test containers**: `code-indexer-test-*-docker/podman` (ports 50000+)
- **Automatic isolation**: Test containers use different names, ports, and networks
- **Safety measures**: Tests never interfere with production container setups

### Test Running Instructions

#### Quick Development Tests (Fast)
```bash
# Run fast unit tests and integration tests
./ci-github.sh

# Run specific test categories
pytest tests/unit/ -v                    # Unit tests only
pytest tests/integration/ -v             # Integration tests only
pytest tests/e2e/ -v                     # E2E tests only
```

#### Comprehensive Testing (Slow)
```bash
# Run all tests including slow e2e tests
./full-automation.sh

# Run tests by container category
pytest -m shared_safe -v                 # Shared-safe tests only
pytest -m docker_only -v                 # Docker-specific tests only
pytest -m "not destructive" -v           # Non-destructive tests only
```

#### Development Setup
```bash
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer
pip install -e ".[dev]"

# Run quick tests to verify setup
./ci-github.sh

# Optional: Run comprehensive tests (requires Docker/Podman)
./full-automation.sh
```

#### Test Infrastructure Features

- **Service persistence**: Tests keep services running between executions for speed
- **Prerequisite validation**: Tests ensure required services are available at startup
- **Clean data isolation**: Uses `clean-data` for test isolation, not service shutdown
- **Automatic categorization**: Tests are automatically categorized by container requirements
- **Shared fixtures**: Common test utilities available via `tests.shared.test_infrastructure`

### Linting and Code Quality

```bash
# Run linting (includes ruff, black, mypy)
./lint.sh

# Check for import issues and syntax errors
python -m py_compile src/code_indexer/**/*.py
```

## License

MIT License

## Contributing

Issues and pull requests welcome!
