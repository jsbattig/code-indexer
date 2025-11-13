# Code Indexer (`cidx`)

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

## Version 7.2.1

**New in 7.2.1**: **Git History Search** - Semantically search your entire git commit history! Find when code was introduced, search commit messages by meaning, track feature evolution over time. Use `cidx index --index-commits` to enable, then query with `--time-range-all`. See [Git History Search](#git-history-search) for details. Also includes fix for temporal indexer commit message truncation and match number display consistency.

**Version 7.2.0**: Incremental HNSW indexing (3.6x speedup) and FTS enhancements - see [Performance Improvements](#performance-improvements-72) below.

**Version 7.1.0**: Full-text search (FTS) support with Tantivy backend - see [Full-Text Search](#full-text-search-fts) section below.

## Two Operating Modes

### CLI Mode (`cidx` command)
Traditional command-line interface for individual developers:
- **Direct CLI commands** - `cidx init`, `cidx index`, `cidx query`
- **Local project indexing** - Index your current project directory
- **Real-time progress** - Individual file status progression (starting → chunking → vectorizing → finalizing → complete)
- **Integrated with Claude CLI** - Seamless AI code analysis with semantic search context

### Multi-User Server Mode
FastAPI web service for team environments:
- **REST API** - Web service with authentication and user management
- **JWT Authentication** - Token-based security
- **Golden Repositories** - Centralized code repository management for teams
- **Background Processing** - Async job system for heavy operations
- **Multi-project support** - Team workspace management

## Core Capabilities

### Semantic Search Engine
- **Vector embeddings** - Find code by meaning using fixed-size chunking
- **Git history search** - Search commit history semantically with time-range filtering
- **Multiple providers** - Local (Ollama) or cloud (VoyageAI) embeddings
- **Smart indexing** - Parallel file processing, incremental HNSW/FTS updates (3.6x faster), git-aware
- **Advanced filtering** - Language, file paths, extensions, similarity scores, time ranges, authors
- **Multi-language** - Python, JavaScript, TypeScript, Java, C#, Go, Kotlin, and more

### Parallel Processing Architecture
- **Slot-based file processing** - Real-time state visibility with natural slot reuse
- **Dual thread pools** - Frontend file processing (threadcount+2) feeds backend vectorization (threadcount)
- **Real-time progress** - Individual file status progression (starting → chunking → vectorizing → finalizing → complete)
- **Clean cancellation** - Post-write cancellation preserves file atomicity

## Vector Search Architecture (v7.0)

### HNSW Graph-Based Indexing

Code Indexer v7.0 introduces **HNSW (Hierarchical Navigable Small World)** graph-based indexing for blazing-fast semantic search with **O(log N)** complexity.

**Performance:**
- **300x speedup**: ~20ms queries (vs 6+ seconds with binary index)
- **Scalability**: Tested with 37K vectors, sub-30ms response times
- **Memory efficient**: 154 MB index for 37K vectors (4.2 KB per vector)

**Algorithm Complexity:**
```
Query Time Complexity: O(log N + K)
  - HNSW graph search: O(log N) average case
  - Candidate loading: O(K) where K = limit * 2, K << N
  - Practical: ~20ms for 37K vectors
```

**HNSW Configuration:**
- **M=16**: Connections per node (graph connectivity)
- **ef_construction=200**: Build-time accuracy parameter
- **ef_query=50**: Query-time accuracy parameter
- **Space=cosine**: Cosine similarity distance metric

### Filesystem Vector Store

Container-free vector storage using filesystem + HNSW indexing:

**Storage Structure:**
```
.code-indexer/index/<collection>/
├── hnsw_index.bin              # HNSW graph (O(log N) search)
├── id_index.bin                # Binary mmap ID→path mapping
├── collection_meta.json        # Metadata + staleness tracking
└── vectors/                    # Quantized path structure
    └── <level1>/<level2>/<level3>/<level4>/
        └── vector_<uuid>.json  # Individual vector + payload
```

**Key Features:**
- **Path-as-Vector Quantization**: 64-dim projection → 4-level directory depth
- **Git-Aware Storage**:
  - Clean files: Store only git blob hash (space efficient)
  - Dirty/non-git: Store full chunk_text
- **Hash-Based Staleness**: SHA256 for precise change detection
- **3-Tier Content Retrieval**: Current file → git blob → error

**Binary ID Index:**
- **Format**: Packed binary `[num_entries:uint32][id_len:uint16, id:utf8, path_len:uint16, path:utf8]...`
- **Performance**: <20ms cached loads via memory mapping (mmap)
- **Thread-safe**: RLock for concurrent access

### Parallel Query Execution

**2-Thread Architecture for 15-30% Latency Reduction:**

```
Query Pipeline:
┌─────────────────────────────────────────┐
│  Thread 1: Index Loading (I/O bound)   │
│  - Load HNSW graph (~5-15ms)           │
│  - Load ID index via mmap (<20ms)      │
└─────────────────────────────────────────┘
           ⬇ Parallel Execution ⬇
┌─────────────────────────────────────────┐
│ Thread 2: Embedding (CPU/Network bound)│
│  - Generate query embedding (5s API)   │
└─────────────────────────────────────────┘
           ⬇ Join ⬇
┌─────────────────────────────────────────┐
│  HNSW Graph Search + Filtering         │
│  - Navigate graph: O(log N)            │
│  - Load K candidates: O(K)             │
│  - Apply filters and score             │
│  - Return top-K results                │
└─────────────────────────────────────────┘
```

**Typical Savings:** 175-265ms per query
**Threading Overhead:** 7-16% (transparently reported)

### Search Strategy Evolution

**Version 6.x: Binary Index (O(N) Linear Scan)**
```python
# Load ALL vectors
for vector_id in all_vectors:  # O(N)
    vector = load_vector(vector_id)
    similarity = cosine(query, vector)
    results.append((vector_id, similarity))

results.sort()  # O(N log N)
return results[:limit]

# Performance: 6+ seconds for 7K vectors
```

**Version 7.0: HNSW Index (O(log N) Graph Search)**
```python
# Load HNSW graph index
hnsw = load_hnsw_index()  # O(1)

# Navigate graph to find approximate nearest neighbors
candidates = hnsw.search(query, k=limit*2)  # O(log N)

# Load ONLY candidate vectors
for candidate_id in candidates:  # O(K) where K << N
    vector = load_vector(candidate_id)
    similarity = exact_cosine(query, vector)
    if filter_match(vector.payload):
        results.append((candidate_id, similarity))

results.sort()  # O(K log K)
return results[:limit]

# Performance: ~20ms for 37K vectors (300x faster)
```

### Performance Decision Analysis

**Why HNSW?**
1. **vs FAISS**: Simpler integration, no external C++ dependencies, optimal for small-medium datasets (<100K vectors)
2. **vs Annoy**: Better accuracy-speed tradeoff, superior graph connectivity
3. **vs Product Quantization**: Maintains full precision, no accuracy loss
4. **vs Brute Force**: 300x speedup justifies ~150MB index overhead

**Quantization Strategy:**
- **64-dim projection**: Optimal balance (tested 32, 64, 128, 256 dimensions)
- **4-level depth**: Enables 64^4 = 16.8M unique paths (sufficient for large codebases)
- **2-bit quantization**: Further reduces from 64 to 4 levels per dimension

**Storage Trade-offs:**
- **JSON vs Binary**: JSON chosen for git-trackability and debuggability (3-5x size acceptable)
- **Individual files**: Enable incremental updates and git change tracking
- **Binary exceptions**: ID index and HNSW use binary for performance-critical components

## Performance Improvements (7.2)

### Incremental HNSW Updates (3.6x Speedup)

Code Indexer v7.2 introduces **incremental HNSW index updates**, eliminating expensive full rebuilds and delivering **3.6x average performance improvement** across indexing workflows.

**Performance:**
- **Watch mode updates**: < 20ms per file (vs 5-10s full rebuild) - **99.6% improvement**
- **Batch indexing**: 1.46x-1.65x speedup for incremental updates
- **Zero query delay**: First query after changes returns instantly (no rebuild wait)
- **Overall**: **3.6x average speedup** in typical development workflows

**How It Works:**
- **Change Tracking**: Tracks added/updated/deleted vectors during indexing session
- **Auto-Detection**: SmartIndexer automatically determines incremental vs full rebuild
- **Label Management**: Efficient ID-to-label mapping maintains consistency
- **Soft Delete**: Deleted vectors marked (not removed) to avoid rebuilds

**When Incremental Updates Apply:**
- ✅ **Watch mode**: File changes trigger real-time HNSW updates
- ✅ **Re-indexing**: Subsequent `cidx index` runs use incremental updates
- ✅ **Git workflow**: Changes after `git pull` indexed incrementally
- ❌ **First-time indexing**: Full rebuild required (no existing index)
- ❌ **Force reindex**: `cidx index --clear` explicitly forces full rebuild

**Example Workflow:**
```bash
# First-time indexing (full rebuild)
cidx index
# → 40 seconds for 10K files

# Modify 100 files, then re-index (incremental update)
cidx index
# → 15 seconds (3.6x faster!) - only 100 files processed

# Watch mode (real-time incremental updates)
cidx watch --fts
# → File changes indexed in < 20ms each
```

### FTS Performance and Incremental Indexing

FTS (Full-Text Search) now uses **FileFinder** for efficient file discovery and supports **incremental indexing** for faster rebuild operations.

**Query Performance (Benchmark Results):**
- **Tested on**: 11,859-file codebase (evolution repo)
- **FTS vs grep**: 1.36x faster for text searches
- **grep average**: 1.426s per search
- **FTS average**: 1.046s per search
- **Methodology**: 8 search terms × 5 iterations each

**Rebuild Performance (Story #488):**
- **FileFinder integration**: 30-36x faster rebuild (6.3s vs 3+ minutes)
- **Old method**: Scanned 6,160 vector JSON files
- **New method**: Uses FileFinder with gitignore support
- **Incremental updates**: Tantivy updates only changed documents

**How It Works:**
- **Index Detection**: Checks for `meta.json` to detect existing FTS index
- **Incremental Mode**: Tantivy updates only changed documents (not full rebuild)
- **Automatic**: No configuration needed - automatically uses incremental mode

**Example Output:**
```bash
# First-time indexing (full rebuild with FileFinder)
cidx index --fts
ℹ️  Building new FTS index from scratch (full rebuild)
# → 6.3s for 1,329 files

# Subsequent indexing (incremental update)
cidx index --fts
ℹ️  Using existing FTS index (incremental updates enabled)
# → Updates only changed files

# Force full rebuild if needed
cidx index --fts --clear
ℹ️  Building new FTS index from scratch (full rebuild)
```

### Performance Comparison Table

| Operation | Before (7.1) | After (7.2) | Speedup |
|-----------|-------------|-------------|---------|
| **HNSW watch mode** | 5-10s per file | < 20ms per file | **99.6% faster** |
| **HNSW batch re-index** | 40s (10K files) | 15s (100 changed) | **3.6x faster** |
| **FTS rebuild** | 3+ minutes (vector scan) | 6.3s (FileFinder) | **30-36x faster** |
| **FTS query** | grep: 1.426s | FTS: 1.046s | **1.36x faster** |

**Developer Experience Impact:**
- ✅ **Instant query results**: No 5-10s delay after file changes in watch mode
- ✅ **Faster development cycles**: Re-indexing 3.6x faster during iterative development
- ✅ **Real-time responsiveness**: Watch mode feels truly real-time (< 20ms updates)
- ✅ **Reduced CPU usage**: Incremental updates use < 1% CPU vs 100% for full rebuilds

## How the Indexing Algorithm Works

The code-indexer uses a sophisticated dual-phase parallel processing architecture with git-aware metadata extraction and dynamic VoyageAI batch optimization.

**For detailed technical documentation**, see [`docs/algorithms.md`](docs/algorithms.md) which covers:
- Complete algorithm flow and complexity analysis
- VoyageAI batch processing optimization  
- Slot-based progress tracking architecture
- Git-aware branch isolation and deduplication
- Performance characteristics and implementation details

## Installation

### pipx (Recommended)
```bash
# Install the package
pipx install git+https://github.com/jsbattig/code-indexer.git@v7.2.0

# Setup global registry (standalone command - requires sudo)
cidx setup-global-registry

# If cidx command is not found, add pipx bin directory to PATH:
# export PATH="$HOME/.local/bin:$PATH"
```

### pip with virtual environment
```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git@v7.2.0

# Setup global registry (standalone command - requires sudo)
cidx setup-global-registry
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

### Vector Storage Backends

Code Indexer supports two vector storage backends for different deployment scenarios:

#### Filesystem Backend (Default)
Container-free vector storage using the local filesystem - ideal for environments where containers are restricted or unavailable.

**Features:**
- **No containers required** - Stores vector data directly in `.code-indexer/index/` directory
- **Zero setup overhead** - Works immediately without Docker/Podman
- **Lightweight** - Minimal resource footprint, no container orchestration
- **Portable** - Vector data travels with your repository

**Usage:**
```bash
# Default behavior (no flag needed)
cidx init

# Or explicitly specify filesystem backend
cidx init --vector-store filesystem
```

**Directory Structure:**
```
your-project/
└── .code-indexer/
    ├── config.json
    └── index/           # Vector data stored here
        └── (vector storage files)
```

#### Qdrant Backend
Container-based vector storage using Docker/Podman + Qdrant vector database - provides advanced vector database features and scalability.

**Features:**
- **High performance** - Optimized vector similarity search with HNSW indexing
- **Advanced filtering** - Complex queries and metadata filtering
- **Horizontal scaling** - Suitable for large codebases and production deployments
- **Container isolation** - Clean separation of concerns with containerized services

**Usage:**
```bash
# Initialize with Qdrant backend
cidx init --vector-store qdrant

# Requires: Docker or Podman installed
# Automatically allocates unique ports per project
# Requires global port registry: cidx setup-global-registry
```

**When to use each backend:**
- **Filesystem**: Development environments, CI/CD pipelines, container-restricted systems, quick prototyping
- **Qdrant**: Production deployments, large teams, advanced vector search requirements, high-performance needs

### Switching Between Backends

You can switch between filesystem and Qdrant backends at any time. **Warning:** Switching backends requires destroying existing vector data and re-indexing your codebase. Your source code is never affected - only the vector index data is removed.

**Complete Switching Workflow:**

```bash
# Method 1: Manual step-by-step (recommended for first-time users)
cidx stop                                  # Stop any running services
cidx uninstall --confirm                   # Remove current backend data
cidx init --vector-store <new-backend>     # Initialize new backend (filesystem or qdrant)
cidx start                                 # Start services for new backend
cidx index                                 # Re-index codebase with new backend

# Method 2: Force reinitialize (quick switch, skips uninstall)
cidx init --vector-store <new-backend> --force
cidx start
cidx index
```

**Examples:**

```bash
# Switch from Qdrant to filesystem (container-free)
cidx stop
cidx uninstall --confirm
cidx init --vector-store filesystem
cidx start
cidx index

# Switch from filesystem to Qdrant (containerized)
cidx stop  # No-op for filesystem, safe to run
cidx uninstall --confirm
cidx init --vector-store qdrant
cidx start
cidx index

# Quick switch using --force flag
cidx init --vector-store qdrant --force
cidx start
cidx index
```

**What gets preserved:**
- ✅ All source code files
- ✅ Git repository and history
- ✅ Project structure and dependencies
- ✅ Configuration settings (file exclusions, size limits, etc.)

**What gets removed:**
- ❌ Vector embeddings and index data
- ❌ Cached search results
- ❌ Backend-specific containers (when switching from Qdrant)
- ❌ Backend-specific storage directories

**Safety considerations:**
- The `--confirm` flag skips the confirmation prompt for `uninstall`
- The `--force` flag overwrites existing configuration when using `init`
- Always ensure you have a backup if you've customized your `.code-indexer/config.json`
- Re-indexing time depends on codebase size (typically seconds to minutes)

## Quick Start

```bash
# 1. Setup global registry (once per system)
cidx setup-global-registry

# 2. Navigate to your project
cd /path/to/your/project

# 3. Start services and index code
cidx start     # Auto-creates config if needed
cidx index     # Smart incremental indexing

# 4. Search semantically
cidx query "authentication logic"

# 5. Search with filtering
cidx query "user" --language python --min-score 0.7
cidx query "save" --path-filter "*/models/*" --limit 20

# 6. Teach AI assistants about semantic search (optional)
cidx teach-ai --claude --project
```

### Alternative: Custom Configuration

```bash
# Optional: Initialize with custom settings first
cidx init --embedding-provider voyage-ai --max-file-size 2000000
cidx start
cidx index
```

## Full-Text Search (FTS)

CIDX supports index-backed full-text search alongside semantic search. FTS is perfect for finding exact text matches, specific identifiers, or debugging typos in your codebase.

### Why Use FTS?

- **Faster than grep** - 1.36x speedup on indexed codebases (measured on 11,859-file repo)
- **Exact text matching** for finding specific function names, classes, or identifiers
- **Fuzzy matching** with configurable edit distance for typo tolerance
- **Case sensitivity control** for precise matching
- **Real-time updates** in watch mode

### Building the FTS Index

```bash
# Build both semantic and FTS indexes (recommended)
cidx index --fts

# Enable FTS in watch mode for real-time updates
cidx watch --fts
```

**Note**: FTS requires Tantivy v0.25.0. Install with: `pip install tantivy==0.25.0`

### Search Modes

CIDX supports three search modes:

#### 1. Semantic Search (Default)
AI-powered conceptual search using vector embeddings:
```bash
cidx query "authentication logic"
cidx query "database connection setup"
cidx query "error handling patterns"
```

#### 2. Full-Text Search (--fts)
Fast, exact text matching with optional fuzzy tolerance:
```bash
# Exact text search
cidx query "authenticate_user" --fts

# Case-sensitive search (find exact case)
cidx query "ParseError" --fts --case-sensitive

# Fuzzy matching (typo tolerant)
cidx query "authenticte" --fts --fuzzy  # Finds "authenticate"
cidx query "conection" --fts --edit-distance 2  # Finds "connection"
```

#### 3. Hybrid Search (--fts --semantic)
Run both searches in parallel for comprehensive results:
```bash
cidx query "parse" --fts --semantic
cidx query "login" --fts --semantic --limit 5
```

### FTS-Specific Options

```bash
# Case sensitivity
--case-sensitive      # Enable case-sensitive matching
--case-insensitive    # Force case-insensitive (default)

# Fuzzy matching
--fuzzy               # Enable fuzzy matching (edit distance 1)
--edit-distance N     # Set fuzzy tolerance (0-3, default: 0)
                      # 0=exact, 1=1 typo, 2=2 typos, 3=3 typos

# Context control
--snippet-lines N     # Lines of context around matches (0-50, default: 5)
                      # 0=list files only, no content snippets
```

### FTS Examples

```bash
# Find specific function names
cidx query "authenticate_user" --fts

# Case-sensitive class search
cidx query "UserAuthentication" --fts --case-sensitive

# Fuzzy search for typos
cidx query "respnse" --fts --fuzzy                    # Finds "response"
cidx query "athenticate" --fts --edit-distance 2      # Finds "authenticate"

# Minimal output (list files only)
cidx query "TODO" --fts --snippet-lines 0

# Extended context
cidx query "error" --fts --snippet-lines 10

# Filter by language and path
cidx query "test" --fts --language python --path-filter "*/tests/*"

# Hybrid search (both semantic and exact matching)
cidx query "login" --fts --semantic
```

### FTS Performance

FTS queries use Tantivy index for efficient text search:
- **1.36x faster than grep** on indexed codebases (benchmark: 1.046s vs 1.426s avg)
- **Parallel execution** in hybrid mode (both searches run simultaneously)
- **Real-time index updates** in watch mode
- **Storage**: `.code-indexer/tantivy_index/`

### When to Use Each Mode

| Use Case | Best Mode | Example |
|----------|-----------|---------|
| Finding specific functions/classes | FTS with --case-sensitive | `cidx query "UserAuth" --fts --case-sensitive` |
| Exploring concepts/patterns | Semantic (default) | `cidx query "authentication strategies"` |
| Debugging typos in code | FTS with --fuzzy | `cidx query "respnse" --fts --fuzzy` |
| Comprehensive search | Hybrid | `cidx query "parse" --fts --semantic` |
| Finding TODO comments | FTS | `cidx query "TODO" --fts` |
| Understanding architecture | Semantic | `cidx query "how does caching work"` |

### Regex Pattern Matching

Use `--regex` flag for token-based pattern matching (faster than grep on indexed repos):

```bash
# Find function definitions
cidx query "def" --fts --regex

# Find identifiers starting with "auth"
cidx query "auth.*" --fts --regex --language python

# Find test functions
cidx query "test_.*" --fts --regex --exclude-path "*/vendor/*"

# Find TODO comments (use lowercase for case-insensitive matching)
cidx query "todo" --fts --regex

# Case-sensitive regex (use uppercase for exact case match)
cidx query "ERROR" --fts --regex --case-sensitive
```

**Important Limitation - Token-Based Matching**: Tantivy regex operates on individual TOKENS, not full text:
- ✅ **Works**: `r"def"`, `r"login.*"`, `r"todo"`, `r"test_.*"`
- ❌ **Doesn't work**: `r"def\s+\w+"` (whitespace removed during tokenization)

**Case Sensitivity**: By default, regex searches are case-insensitive (patterns matched against lowercased content). Use `--case-sensitive` flag for exact case matching.

For multi-word patterns spanning whitespace, use exact search instead of regex.

**Performance**: Regex uses Tantivy index for token-based pattern matching (1.36x faster than grep based on FTS benchmarks).

## Multi-User Server

The CIDX server provides a FastAPI-based multi-user semantic code search service with JWT authentication and role-based access control.

### Server Quick Start

```bash
# 1. Install and setup (same as CLI)
pipx install git+https://github.com/jsbattig/code-indexer.git@v7.2.0
cidx setup-global-registry

# 2. Install and configure the server
cidx install-server

# 3. Start the server
cidx server start

# 4. Access the API documentation
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
cidx setup-global-registry              # Setup global port registry (requires sudo)
cidx setup-global-registry --test-access --quiet  # Test registry access

# Project initialization
cidx init                               # Initialize with default settings
cidx init --embedding-provider voyage-ai  # Use VoyageAI instead of Ollama
cidx init --max-file-size 2000000       # Set 2MB file size limit
cidx init --setup-global-registry       # Init + setup registry (legacy)
cidx init --create-override-file        # Create .code-indexer-override.yaml
```

### Service Management

```bash
# Service lifecycle
cidx start                      # Start services (smart detection)
cidx start --force-docker       # Force Docker instead of Podman
cidx start --force-recreate     # Force recreate containers
cidx start --quiet              # Silent mode
cidx start -m all-minilm-l6-v2  # Different Ollama model

cidx status                     # Check service status
cidx status --force-docker      # Check Docker status specifically

cidx stop                       # Stop services (preserve data)
cidx stop --force-docker        # Stop Docker services specifically
```

### Indexing Commands

```bash
# Standard indexing
cidx index                      # Smart incremental indexing
cidx index --clear              # Force full reindex
cidx index --reconcile          # Reconcile disk vs database
cidx index --detect-deletions   # Handle deleted files
cidx index --batch-size 25      # Custom batch size
cidx index --files-count-to-process 100  # Limit file count
cidx index --threads 8          # Custom thread count (configure in config.json)

# Real-time monitoring
cidx watch                      # Git-aware file watching
cidx watch --debounce 5.0       # Custom debounce delay
cidx watch --initial-sync       # Full sync before watching
```

### Search Commands

```bash
# Basic search
cidx query "search terms"      # Semantic search
cidx query "auth" --limit 20   # More results
cidx query "function" --quiet  # Only results, no headers

# Advanced filtering
cidx query "user" --language python  # Filter by language
cidx query "save" --path-filter "*/models/*" # Filter by path pattern
cidx query "function" --min-score 0.7  # Higher confidence matches
cidx query "database" --limit 15     # More results
cidx query "test" --min-score 0.8     # High-confidence matches

# Short alias
cidx query "search terms"              # Same as cidx query
```

### Language Filtering

CIDX supports intelligent language filtering with comprehensive file extension mapping:

```bash
# Friendly language names (recommended)
cidx query "authentication" --language python     # Matches .py, .pyw, .pyi files
cidx query "components" --language javascript     # Matches .js, .jsx files  
cidx query "models" --language typescript         # Matches .ts, .tsx files
cidx query "handlers" --language cpp              # Matches .cpp, .cc, .cxx, .c++ files

# Direct extension usage (also supported)
cidx query "function" --language py               # Matches only .py files
cidx query "component" --language jsx             # Matches only .jsx files
```

**Supported Languages**: python, javascript, typescript, java, csharp, c, cpp, go, rust, php, ruby, swift, kotlin, scala, dart, html, css, vue, markdown, xml, yaml, json, sql, shell, bash, dockerfile, and more.

#### Customizing Language Mappings

You can customize language mappings by editing `.code-indexer/language-mappings.yaml`:

```yaml
# Add custom languages or modify existing mappings
python: [py, pyw, pyi]          # Multiple extensions
mylang: [ml, mli]               # Your custom language  
javascript: [js, jsx]           # Modify existing mappings
```

Changes take effect on the next query execution. The file is automatically created during `cidx init` or on first use.

### Exclusion Filters

CIDX provides powerful exclusion filters to remove unwanted files from your search results. Exclusions always take precedence over inclusions, giving you precise control over your search scope.

#### Excluding Files by Language

Filter out files of specific programming languages using `--exclude-language`:

```bash
# Exclude JavaScript files from results
cidx query "database implementation" --exclude-language javascript

# Exclude multiple languages
cidx query "api handlers" --exclude-language javascript --exclude-language typescript --exclude-language css

# Combine with language inclusion (Python only, no JS)
cidx query "web server" --language python --exclude-language javascript
```

#### Excluding Files by Path Pattern

Use `--exclude-path` with glob patterns to filter out files in specific directories or with certain names:

```bash
# Exclude all test files
cidx query "production code" --exclude-path "*/tests/*" --exclude-path "*_test.py"

# Exclude dependency and cache directories
cidx query "application logic" \
  --exclude-path "*/node_modules/*" \
  --exclude-path "*/vendor/*" \
  --exclude-path "*/__pycache__/*"

# Exclude by file extension
cidx query "source code" --exclude-path "*.min.js" --exclude-path "*.pyc"

# Complex path patterns
cidx query "configuration" --exclude-path "*/build/*" --exclude-path "*/.*"  # Hidden files
```

#### Combining Multiple Filter Types

Create sophisticated queries by combining inclusion and exclusion filters:

```bash
# Python files in src/, excluding tests and cache
cidx query "database models" \
  --language python \
  --path-filter "*/src/*" \
  --exclude-path "*/tests/*" \
  --exclude-path "*/__pycache__/*"

# High-relevance results, no test files or vendored code
cidx query "authentication logic" \
  --min-score 0.8 \
  --exclude-path "*/tests/*" \
  --exclude-path "*/vendor/*" \
  --exclude-language javascript

# API code only, multiple exclusions
cidx query "REST endpoints" \
  --path-filter "*/api/*" \
  --exclude-path "*/tests/*" \
  --exclude-path "*/mocks/*" \
  --exclude-language javascript \
  --exclude-language css
```

#### Common Exclusion Patterns

##### Testing Files
```bash
--exclude-path "*/tests/*"        # Test directories
--exclude-path "*/test/*"         # Alternative test dirs
--exclude-path "*_test.py"        # Python test files
--exclude-path "*_test.go"        # Go test files
--exclude-path "*.test.js"        # JavaScript test files
--exclude-path "*/fixtures/*"     # Test fixtures
--exclude-path "*/mocks/*"        # Mock files
```

##### Dependencies and Vendor Code
```bash
--exclude-path "*/node_modules/*"    # Node.js dependencies
--exclude-path "*/vendor/*"          # Vendor libraries
--exclude-path "*/.venv/*"           # Python virtual environments
--exclude-path "*/site-packages/*"   # Python packages
--exclude-path "*/bower_components/*" # Bower dependencies
```

##### Build Artifacts and Cache
```bash
--exclude-path "*/build/*"        # Build output
--exclude-path "*/dist/*"         # Distribution files
--exclude-path "*/target/*"       # Maven/Cargo output
--exclude-path "*/__pycache__/*"  # Python cache
--exclude-path "*.pyc"            # Python compiled files
--exclude-path "*.pyo"            # Python optimized files
--exclude-path "*.class"          # Java compiled files
--exclude-path "*.o"              # Object files
--exclude-path "*.so"             # Shared libraries
```

##### Generated and Minified Files
```bash
--exclude-path "*.min.js"         # Minified JavaScript
--exclude-path "*.min.css"        # Minified CSS
--exclude-path "*_pb2.py"         # Protocol buffer generated
--exclude-path "*.generated.*"    # Generated files
--exclude-path "*/migrations/*"   # Database migrations
```

#### Filter Conflicts and Warnings

CIDX automatically detects contradictory filters and provides helpful feedback:

```bash
# Language conflict (same language included AND excluded)
cidx query "database" --language python --exclude-language python
# Output: 🚫 Language 'python' is both included and excluded.

# Path conflict (same path included AND excluded)
cidx query "config" --path-filter "*/src/*" --exclude-path "*/src/*"
# Output: 🚫 Path pattern '*/src/*' is both included and excluded.

# Over-exclusion warning (many exclusions without inclusions)
cidx query "code" --exclude-language python --exclude-language javascript \
  --exclude-language typescript --exclude-language java --exclude-language go
# Output: ⚠️  Excluding 5 languages without any inclusion filters may result in unexpected results.
```

#### Performance Notes

- Each exclusion filter adds minimal overhead (typically <2ms)
- Filters are applied during the search phase, not during indexing
- Use specific patterns when possible for better performance
- Complex glob patterns may have slightly higher overhead
- The order of filters does not affect performance

### AI Platform Instructions

The `teach-ai` command generates instruction files that teach AI assistants how to use `cidx` for semantic code search. Instructions are loaded from template files, allowing non-technical users to update content without code changes.

```bash
# Install Claude instructions in project root
cidx teach-ai --claude --project    # Creates ./CLAUDE.md

# Install Claude instructions globally
cidx teach-ai --claude --global     # Creates ~/.claude/CLAUDE.md

# Preview instruction content
cidx teach-ai --claude --show-only  # Show without writing

# Supported AI platforms
cidx teach-ai --claude              # Claude Code
cidx teach-ai --codex               # OpenAI Codex
cidx teach-ai --gemini              # Google Gemini
cidx teach-ai --opencode            # OpenCode
cidx teach-ai --q                   # Q
cidx teach-ai --junie               # Junie

# Combine platform and scope flags
cidx teach-ai --gemini --global     # Gemini global install
cidx teach-ai --codex --project     # Codex project install
```

**Template Location**: `prompts/ai_instructions/{platform}.md`

**Platform File Locations**:
| Platform | Project File | Global File |
|----------|-------------|-------------|
| Claude | `CLAUDE.md` | `~/.claude/CLAUDE.md` |
| Codex | `CODEX.md` | `~/.codex/instructions.md` |
| Gemini | `.gemini/styleguide.md` | N/A (project-only) |
| OpenCode | `AGENTS.md` | `~/.config/opencode/AGENTS.md` |
| Q | `.amazonq/rules/cidx.md` | `~/.aws/amazonq/Q.md` |
| Junie | `.junie/guidelines.md` | N/A (project-only) |

**Safety Features**: Smart update preserves existing content and updates only CIDX sections.

### Data Management Commands

```bash
# Quick cleanup (recommended)
cidx clean-data                 # Clear current project data
cidx clean-data --all-projects  # Clear all projects data
cidx clean-data --force-docker  # Use Docker for cleanup

# Complete removal
cidx uninstall                  # Remove current project completely
cidx uninstall --force-docker   # Use Docker for removal
cidx uninstall --wipe-all       # DANGEROUS: Complete system wipe

# Migration and maintenance
cidx clean-legacy               # Migrate from legacy containers
cidx optimize                   # Optimize vector database
cidx force-flush                # Force flush to disk (deprecated)
cidx force-flush --collection mycoll  # Flush specific collection
```

## Git History Search

CIDX can index and semantically search your entire git commit history, enabling powerful time-based code archaeology:

- **Find when code was introduced** - Search across all historical commits
- **Search commit messages semantically** - Find commits by meaning, not exact text
- **Track feature evolution** - See how code changed over time
- **Filter by time ranges** - Search specific periods or branches
- **Author filtering** - Find commits by specific developers

### Indexing Git History

```bash
# Index git history for temporal search
cidx index --index-commits

# Index all branches (not just current)
cidx index --index-commits --all-branches

# Limit to recent commits
cidx index --index-commits --max-commits 1000

# Index commits since specific date
cidx index --index-commits --since-date 2024-01-01

# Combine options
cidx index --index-commits --all-branches --since-date 2024-01-01
```

**What Gets Indexed:**
- Commit messages (full text, not truncated)
- Code diffs for each commit
- Commit metadata (author, date, hash)
- Branch information

### Querying Git History

```bash
# Search entire git history
cidx query "authentication logic" --time-range-all --quiet

# Search specific time period
cidx query "bug fix" --time-range 2024-01-01..2024-12-31 --quiet

# Search only commit messages
cidx query "refactor database" --time-range-all --chunk-type commit_message --quiet

# Search only code diffs
cidx query "function implementation" --time-range-all --chunk-type commit_diff --quiet

# Filter by author
cidx query "login" --time-range-all --author "john@example.com" --quiet

# Combine with language filters
cidx query "api endpoint" --time-range-all --language python --quiet

# Exclude paths from historical search
cidx query "config" --time-range-all --exclude-path "*/tests/*" --quiet
```

### Chunk Types

When querying git history with `--chunk-type`:

- **`commit_message`** - Search only commit messages
  - Returns: Commit descriptions, not code
  - Metadata: Hash, date, author, files changed count
  - Use for: Finding when features were added, bug fix history

- **`commit_diff`** - Search only code changes
  - Returns: Actual code diffs from commits
  - Metadata: File path, diff type (added/modified/deleted), language
  - Use for: Finding specific code changes, implementation history

- **(default)** - Search both messages and diffs
  - Returns: Mixed results ranked by semantic relevance
  - Use for: General historical code search

### Time Range Formats

```bash
# All history (1970 to 2100)
--time-range-all

# Specific date range
--time-range 2024-01-01..2024-12-31

# Recent timeframe
--time-range 2024-06-01..2024-12-31

# Single year
--time-range 2024-01-01..2024-12-31
```

### Use Cases

**1. Code Archaeology - When Was This Added?**
```bash
# Find when JWT authentication was introduced
cidx query "JWT token authentication" --time-range-all --quiet

# Output shows commit where it was added:
# 1. [Commit abc123] (2024-03-15) John Doe
#    feat: add JWT authentication middleware
```

**2. Bug History Research**
```bash
# Find all bug fixes related to database connections
cidx query "database connection bug" --time-range-all --chunk-type commit_message --quiet
```

**3. Author Code Analysis**
```bash
# Find all authentication-related work by specific developer
cidx query "authentication" --time-range-all --author "sarah@company.com" --quiet
```

**4. Feature Evolution Tracking**
```bash
# See how API endpoints changed over time
cidx query "API endpoint" --time-range 2023-01-01..2024-12-31 --language python --quiet
```

**5. Refactoring History**
```bash
# Find all refactoring work
cidx query "refactor" --time-range-all --chunk-type commit_message --limit 20 --quiet
```

### Server Mode - Golden Repositories with Temporal Indexing

When registering golden repositories via the API server, enable temporal indexing:

```bash
curl -X POST http://localhost:8090/api/admin/golden-repos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/your-org/backend.git",
    "alias": "backend",
    "enable_temporal": true,
    "temporal_options": {
      "max_commits": 1000,
      "since_date": "2024-01-01"
    }
  }'
```

**Temporal Options:**
- `max_commits` (optional): Maximum commits to index per branch (default: unlimited)
- `since_date` (optional): Index only commits after this date (YYYY-MM-DD format)
- `diff_context` (optional): Context lines in diffs (default: 3)

This enables API users to query the repository's git history, not just current code.

### Configuration Commands

```bash
# Configuration repair
cidx fix-config                 # Fix corrupted configuration
cidx fix-config --dry-run       # Preview fixes
cidx fix-config --verbose       # Detailed fix information
cidx fix-config --force         # Apply without confirmation

# Claude integration setup
cidx set-claude-prompt          # Set CIDX instructions in project CLAUDE.md
cidx set-claude-prompt --user-prompt  # Set in global ~/.claude/CLAUDE.md
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
cidx init --embedding-provider ollama
```

**VoyageAI (Cloud)**
```bash
export VOYAGE_API_KEY="your-key"
cidx init --embedding-provider voyage-ai
```

**Real-time Progress Display**

During indexing, the progress display shows:
- File processing progress with counts and percentages
- Performance metrics: files/s, KB/s, active threads  
- Individual file status with processing stages

Example progress: `15/100 files (15%) | 8.3 files/s | 156.7 KB/s | 12 threads`

Individual file status display:
```
├─ main.py (15.2 KB) starting
├─ utils.py (8.3 KB) chunking...  
├─ config.py (4.1 KB) vectorizing...
├─ helpers.py (3.2 KB) finalizing...
├─ models.py (12.5 KB) complete ✓
```

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

### Parallel File Processing

Code Indexer uses slot-based parallel file processing for efficient throughput:

**Architecture:**
- **Dual thread pool design** - Frontend file processing (threadcount+2 workers) feeds backend vectorization (threadcount workers)
- **File-level parallelism** - Multiple files processed concurrently with dedicated slot allocation  
- **Slot-based allocation** - Fixed-size display array (threadcount+2 slots) with natural worker slot reuse
- **Real-time progress** - Individual file status visible during processing (starting → chunking → vectorizing → finalizing → complete)
- **Thread allocation** - Base threadcount configured via `voyage_ai.parallel_requests` in config.json

**Thread Configuration:**
- **VoyageAI default**: 8 vectorization threads → 10 file processing workers (8+2)
- **Ollama default**: 1 vectorization thread → 3 file processing workers (1+2)  
- **Frontend thread pool**: threadcount+2 workers handle file reading, chunking, and coordination (provides preemptive capacity)
- **Backend thread pool**: threadcount workers handle vector embedding calculations
- **Pipeline design**: Frontend stays ahead of backend, ensuring continuous vector thread utilization
- **Custom configuration**: Adjust `parallel_requests` in config.json for optimal performance

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
# Test temporal watch
# Test 2
# Test 3
