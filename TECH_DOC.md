# Code-Indexer Technical Documentation

## System Overview

Code-Indexer is a semantic code search system that leverages vector embeddings and Abstract Syntax Tree (AST) parsing to enable AI-powered code discovery. The architecture combines containerized services with sophisticated git-aware processing to maintain an accurate, incremental index of codebases.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface Layer                        │
├─────────────────────────────────────────────────────────────────────┤
│  CLI (cli.py)                                                       │
│  ├── Query Commands      ├── Index Commands     ├── Service Mgmt   │
│  └── Claude Integration  └── Config Management  └── Watch Mode      │
├─────────────────────────────────────────────────────────────────────┤
│                      Core Processing Layer                          │
├───────────────────────┬─────────────────────┬──────────────────────┤
│  SmartIndexer         │  BranchAwareIndexer │ HighThroughputProc   │
│  (smart_indexer.py)   │  (branch_aware.py)  │ (high_throughput.py) │
├───────────────────────┴─────────────────────┴──────────────────────┤
│                        Service Layer                                │
├──────────────┬──────────────┬──────────────┬──────────────────────┤
│ EmbeddingProv│ QdrantClient │ DockerManager│ GlobalPortRegistry   │
│ ├── Ollama   │              │              │ (port_registry.py)   │
│ └── VoyageAI │              │              │                      │
├──────────────┴──────────────┴──────────────┴──────────────────────┤
│                     Infrastructure Layer                            │
├─────────────────────────────────────────────────────────────────────┤
│  Docker/Podman Containers                                          │
│  ├── Ollama (LLM embeddings)      ├── Qdrant (Vector DB)          │
│  └── Data Cleaner (Maintenance)                                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Smart Indexer (`src/code_indexer/services/smart_indexer.py`)

The SmartIndexer orchestrates the entire indexing pipeline with progressive metadata tracking and resumability:

- **Lines 87-114**: Initializes high-throughput processing, git topology services, and branch-aware indexing
- **Lines 115-186**: Implements git delta detection between commits for incremental updates
- **Progressive Metadata**: Tracks indexing state for crash recovery and resumability
- **Git Hook Integration**: Automatically detects branch changes via git hooks

**Key Methods:**
- `index_codebase()`: Main entry point for indexing operations
- `_get_git_deltas_since_commit()`: Calculates file changes between git commits
- `_should_reindex_file()`: Determines if a file needs re-indexing based on metadata

### 2. Branch-Aware Indexer (`src/code_indexer/services/branch_aware_indexer.py`)

Implements graph topology optimization for git-aware content storage:

- **Lines 44-76**: ContentMetadata dataclass with branch visibility tracking
- **Lines 91-150**: Core indexing logic with clean progress reporting API
- **Content Deduplication**: One content point per unique (file, commit) pair
- **Branch Visibility**: Tracks content visibility across branches using hidden_branches array

**Architecture Principles:**
- O(δ) indexing complexity - only processes changed files
- O(1) branch visibility lookup
- Immutable content points with mutable visibility mappings

### 3. High-Throughput Processor (`src/code_indexer/services/high_throughput_processor.py`)

Maximizes worker thread utilization through queue-based processing:

- **Lines 44-62**: Process files with pre-queued chunks for maximum throughput
- **Lines 78-130**: Phase 1 - Pre-process all files to create chunk queue
- **Lines 134-150**: Phase 2 - Process chunks in parallel with worker threads
- **Cancellation Support**: Clean cancellation via request_cancellation()

**Processing Flow:**
1. Pre-process all files to create chunk tasks
2. Submit all chunks to VectorCalculationManager
3. Workers continuously pull from queue (never idle)
4. Collect results asynchronously

### 4. Docker Manager (`src/code_indexer/services/docker_manager.py`)

Manages containerized services with project-specific isolation:

- **Lines 19-40**: Initialize with project detection and port registry integration
- **Lines 50-61**: Generate project-specific container names using hash
- **Lines 86-122**: Load service configuration from YAML files
- **Container Naming**: cidx-{project_hash}-{service} pattern

**Supported Services:**
- Ollama: Local LLM embeddings (default port range: 11434-12434)
- Qdrant: Vector database (default port range: 6333-7333)
- Data Cleaner: Maintenance container (default port range: 8091-9091)

### 5. Global Port Registry (`src/code_indexer/services/global_port_registry.py`)

Coordinates port allocation across multiple projects system-wide:

- **Lines 50-66**: Registry initialization with service port ranges
- **Lines 67-84**: Central registry location at `/var/lib/code-indexer/port-registry`
- **Atomic Operations**: No file locking, uses atomic file operations
- **Self-Healing**: Automatic cleanup of broken softlinks

**Key Features:**
- Cross-project port coordination
- Automatic broken link cleanup
- Cross-filesystem softlink support
- Per-project port allocation tracking

## Container Architecture

The system uses Docker/Podman containers for service isolation:

### Container Lifecycle

1. **Initialization** (`docker_manager.py:_generate_container_names()`)
   - Calculate project hash from path
   - Generate unique container names
   - Allocate ports via GlobalPortRegistry

2. **Service Start** 
   - Create project-specific docker-compose.yaml
   - Start containers with allocated ports
   - Health check until services ready

3. **Port Synchronization**
   - Port allocation stored in project config
   - Health checks read from same config
   - Ensures consistency across operations

### Container Coordination

```
Project Root: /path/to/project
├── .code-indexer/
│   ├── config.json           # Project configuration
│   ├── metadata.json         # Indexing metadata
│   ├── docker-compose.yaml   # Generated compose file
│   └── ports.json           # Allocated ports
│
Global Registry: /var/lib/code-indexer/port-registry/
├── port-allocations.json    # System-wide port map
├── active-projects/         # Softlinks to active projects
│   ├── {hash1} -> /path/to/project1/.code-indexer
│   └── {hash2} -> /path/to/project2/.code-indexer
└── registry.log            # Registry operations log
```

## Git-Aware Processing

### Git Topology Service (`src/code_indexer/services/git_topology_service.py`)

Provides advanced git analysis for incremental indexing:

- **Lines 18-31**: BranchChangeAnalysis dataclass with comprehensive change tracking
- **Lines 58-80**: Git availability detection with caching
- **Branch Analysis**: Tracks merge bases, ancestry, and file changes
- **Working Directory**: Handles staged/unstaged changes

### Processing Flow

1. **Branch Detection**
   - Current branch from git or metadata file
   - Cache results for 5 seconds (reduce git calls)

2. **Change Analysis**
   - Calculate merge base between branches
   - Identify files needing reindex vs metadata update
   - Track working directory modifications

3. **Incremental Updates**
   - Only process changed files (O(δ) complexity)
   - Reuse existing embeddings when possible
   - Update branch visibility metadata

## Data Flow

### Indexing Pipeline

```
Source Files → AST Parser → Semantic Chunker → Embedding Provider → Vector DB
     ↓             ↓              ↓                   ↓                ↓
  Git Status   Language     Chunk Metadata      Embeddings      Qdrant Points
              Detection                         (Ollama/Voyage)
```

### Query Pipeline

```
User Query → Embedding → Vector Search → Branch Filter → Results
    ↓           ↓             ↓              ↓            ↓
 Natural    Query Vector  Qdrant Search  Git Context   Ranked
 Language                                 Filtering     Results
```

## Configuration System

### Config Manager (`src/code_indexer/config.py`)

Hierarchical configuration with multiple sources:

- **Lines 14-33**: OllamaConfig with parallel processing settings
- **Lines 34-72**: VoyageAIConfig with retry and backoff configuration
- **Lines 73-100**: QdrantConfig with HNSW tuning parameters

### Configuration Hierarchy

1. **Project Config** (`.code-indexer/config.json`)
   - Project-specific settings
   - File extensions and exclusions
   - Embedding provider selection

2. **Override Config** (`.code-indexer-override.yaml`)
   - Highest precedence
   - Force include/exclude patterns
   - Extension modifications

3. **Global Config** (`~/.code-indexer/config.yaml`)
   - User defaults
   - API keys and endpoints

## Embedding Providers

### Embedding Factory (`src/code_indexer/services/embedding_factory.py`)

Factory pattern for embedding provider creation:

- **Lines 17-41**: Model slug generation for filesystem-safe names
- **Lines 43-75**: Collection name generation with project isolation
- **Provider Support**: Ollama (local) and VoyageAI (cloud)

### Provider Architecture

**Ollama (Local)**
- Runs in Docker container
- Default model: nomic-embed-text
- Configurable parallelism and queue size

**VoyageAI (Cloud)**
- API-based embedding service
- Models: voyage-code-3, voyage-large-2
- Automatic retry with exponential backoff
- Real-time throttling indicators

## Performance Optimizations

### Vector Calculation Manager (`services/vector_calculation_manager.py`)

Thread pool management for embedding calculations:
- Dynamic thread count based on CPU cores
- Queue-based task distribution
- Batch processing for API providers

### High-Throughput Processing

1. **Pre-queuing**: All chunks queued before processing starts
2. **Worker Saturation**: Threads never idle waiting for work
3. **Async Collection**: Results gathered as completed
4. **Progress Tracking**: Real-time throughput metrics

### Indexing Optimizations

- **Incremental Updates**: Only process changed files
- **Content Deduplication**: Reuse embeddings across branches
- **Parallel Processing**: Multi-threaded embedding generation
- **Batch Operations**: Bulk vector database updates

## Security Considerations

### Port Registry Security

- World-writable directory (777) for multi-user access
- Atomic file operations prevent race conditions
- Softlink validation prevents path traversal

### Container Isolation

- Project-specific containers (no sharing)
- Dynamic port allocation (no hardcoded ports)
- Health checks before service use

### API Key Management

- Environment variables for secrets
- No keys in configuration files
- Secure subprocess execution

## Error Handling

### Resilience Patterns

1. **Retry Logic**: Exponential backoff for transient failures
2. **Progressive Metadata**: Resume from last successful state
3. **Health Checks**: Verify services before operations
4. **Lock Files**: Prevent concurrent indexing corruption

### Recovery Mechanisms

- **Indexing Lock**: Single writer protection (`indexing_lock.py`)
- **Metadata Recovery**: Progressive state restoration
- **Container Restart**: Automatic recovery on failure
- **Registry Cleanup**: Self-healing broken links

## Testing Infrastructure

### Test Categories

1. **Unit Tests**: Component isolation testing
2. **Integration Tests**: Service interaction validation
3. **E2E Tests**: Full pipeline verification
4. **Docker/Podman Tests**: Container compatibility

### Test Optimization

- Containers left running between tests (setup, not teardown)
- Collection cleanup instead of recreation
- Parallel test execution where possible

## Claude Integration

### Claude Integration Service (`services/claude_integration.py`)

Provides AI-powered code analysis:
- Semantic search context injection
- Claude CLI subprocess integration
- Prompt engineering for code understanding
- Tool tracking and metrics

### Integration Flow

1. User query → Semantic search
2. Retrieve relevant code chunks
3. Build context with metadata
4. Submit to Claude CLI
5. Stream response to user

## Monitoring and Observability

### Progress Reporting

- Real-time progress bars with speed metrics
- File processing status indicators
- Throttling detection and display
- ETA calculations with rolling averages

### Logging

- Structured logging via Python logging module
- Debug file output to `~/.tmp/cidx_debug.log`
- Registry operations logged to `/var/lib/code-indexer/port-registry/registry.log`

## Migration Support

### Version Migrations

- Decorator-based migration system (`migration_decorator.py`)
- Automatic schema updates
- Backward compatibility checks
- Collection migration utilities

## File Processing

### AST-Based Parsers (`indexing/` directory)

Language-specific parsers with semantic understanding:
- Tree-sitter based parsing
- Error node handling
- Semantic chunk extraction
- Language feature detection

### Chunking Strategy

1. **Semantic Chunking**: AST-aware boundaries
2. **Size Limits**: Configurable chunk size
3. **Overlap**: Context preservation
4. **Line Tracking**: Source location metadata