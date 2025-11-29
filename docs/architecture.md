# Code Indexer Architecture (v8.0+)

This document describes the high-level architecture and design decisions for Code Indexer (CIDX) version 8.0 and later.

## Version 8.0 Architectural Changes

Version 8.0 represents a major architectural simplification:
- **Removed**: Qdrant backend, container infrastructure, Ollama embeddings
- **Consolidated**: Filesystem-only backend, VoyageAI-only embeddings
- **Simplified**: Two operational modes (was three in v7.x)
- **Result**: Container-free, instant setup, reduced complexity

See [Migration Guide](migration-to-v8.md) for upgrading from v7.x.

## Operating Modes

CIDX has **two operational modes** (simplified from three in v7.x), each optimized for different use cases.

### Mode 1: CLI Mode (Direct, Local)

**Purpose**: Direct command-line tool for local semantic code search

**Storage**: FilesystemVectorStore in `.code-indexer/index/` (container-free)

**Use Case**: Individual developers, single-user workflows

**Characteristics**:
- Indexes code locally in project directory
- No daemon, no server, no network
- Vectors stored as JSON files on filesystem
- Each query loads indexes from disk
- Container-free, instant setup

### Mode 2: Daemon Mode (Local, Cached)

**Purpose**: Local RPyC-based background service for faster queries

**Storage**: Same FilesystemVectorStore + in-memory cache

**Use Case**: Developers wanting faster repeated queries and watch mode

**Characteristics**:
- Caches HNSW/FTS indexes in memory (daemon process)
- Auto-starts on first query when enabled
- Unix socket communication (`.code-indexer/daemon.sock`)
- Faster queries (~5ms cached vs ~1s from disk)
- Watch mode for real-time file change indexing
- Container-free, runs as local process

## Vector Storage Architecture (v7.0+)

### HNSW Graph-Based Indexing

Code Indexer v7.0 introduced **HNSW (Hierarchical Navigable Small World)** graph-based indexing for blazing-fast semantic search with **O(log N)** complexity.

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

## Incremental HNSW Updates (v7.2+)

Code Indexer v7.2 introduced **incremental HNSW index updates**, eliminating expensive full rebuilds.

**Performance:**
- **Watch mode updates**: < 20ms per file (vs 5-10s full rebuild) - **99.6% improvement**
- **Batch indexing**: 1.46x-1.65x speedup for incremental updates
- **Zero query delay**: First query after changes returns instantly
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

## Performance Decision Analysis

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

## Parallel Processing Architecture

Code Indexer uses slot-based parallel file processing for efficient throughput:

**Architecture:**
- **Dual thread pool design** - Frontend file processing (threadcount+2 workers) feeds backend vectorization (threadcount workers)
- **File-level parallelism** - Multiple files processed concurrently with dedicated slot allocation
- **Slot-based allocation** - Fixed-size display array (threadcount+2 slots) with natural worker slot reuse
- **Real-time progress** - Individual file status visible during processing (starting → chunking → vectorizing → finalizing → complete)

**Thread Configuration:**
- **VoyageAI default**: 8 vectorization threads → 10 file processing workers (8+2)
- **Ollama default**: 1 vectorization thread → 3 file processing workers (1+2)
- **Frontend thread pool**: threadcount+2 workers handle file reading, chunking, and coordination
- **Backend thread pool**: threadcount workers handle vector embedding calculations
- **Pipeline design**: Frontend stays ahead of backend, ensuring continuous vector thread utilization

## Model-Aware Chunking Strategy

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
- **Model optimization**: Uses larger chunks for high-capacity models
- **Better context**: More complete code sections per chunk
- **Efficiency**: Fewer total chunks reduce storage requirements
- **Model utilization**: Takes advantage of each model's token capacity

## Full-Text Search (FTS) Architecture

CIDX integrates Tantivy-based full-text search alongside semantic search.

**Performance:**
- **1.36x faster than grep** on indexed codebases
- **Parallel execution** in hybrid mode (both searches run simultaneously)
- **Real-time index updates** in watch mode
- **Storage**: `.code-indexer/tantivy_index/`

**FTS Incremental Indexing (v7.2+):**
- **FileFinder integration**: 30-36x faster rebuild (6.3s vs 3+ minutes)
- **Incremental updates**: Tantivy updates only changed documents
- **Automatic detection**: Checks for `meta.json` to detect existing index

## Git History Search (Temporal Indexing)

CIDX can index and semantically search entire git commit history:

**What Gets Indexed:**
- Commit messages (full text, not truncated)
- Code diffs for each commit
- Commit metadata (author, date, hash)
- Branch information

**Query Capabilities:**
- Search entire git history semantically
- Filter by time ranges (specific dates or `--time-range-all`)
- Filter by chunk type (`commit_message` or `commit_diff`)
- Filter by author
- Combine with language and path filters

**Use Cases:**
- Code archaeology - when was code introduced
- Bug history research
- Feature evolution tracking
- Author code analysis

## MCP Protocol Integration

**Protocol Version**: `2025-06-18` (Model Context Protocol)

**Initialize Handshake** (CRITICAL for Claude Code connection):
- Method: `initialize` - MUST be first client-server interaction
- Server Response: `{ "protocolVersion": "2025-06-18", "capabilities": { "tools": {} }, "serverInfo": { "name": "CIDX", "version": "7.3.0" } }`
- Required for OAuth flow completion - Claude Code calls `initialize` after authentication

**Version Notes**:
- Updated from `2024-11-05` to `2025-06-18` for Claude Desktop compatibility
- 2025-06-18 breaking changes: Removed JSON-RPC batching support
- 2025-06-18 new features: Structured tool output, OAuth resource parameter (RFC 8707), elicitation/create for server-initiated user input
- Current implementation: Version updated, feature audit pending

**Tool Response Format** (CRITICAL for Claude Code compatibility):
- All tool results MUST return `content` as an **array of content blocks**, NOT a string
- Each content block must have: `{ "type": "text", "text": "actual content here" }`
- Empty content should be `[]`, NOT `""` or missing
- Error responses must also include `content: []` (empty array is valid)

## Vector Storage Backends

### Filesystem Backend (Default)

Container-free vector storage using the local filesystem:

**Features:**
- **No containers required** - Stores vector data directly in `.code-indexer/index/`
- **Zero setup overhead** - Works immediately without Docker/Podman
- **Lightweight** - Minimal resource footprint
- **Portable** - Vector data travels with your repository

**When to use**: Development environments, CI/CD pipelines, container-restricted systems

### Qdrant Backend (Legacy)

Container-based vector storage using Docker/Podman + Qdrant vector database:

**Features:**
- **High performance** - Optimized vector similarity search with HNSW indexing
- **Advanced filtering** - Complex queries and metadata filtering
- **Horizontal scaling** - Suitable for large codebases
- **Container isolation** - Clean separation of concerns

**When to use**: Production deployments, large teams, advanced vector search requirements

## Related Documentation

- **[v5.0.0 Architecture Summary](v5.0.0-architecture-summary.md)** - Server Mode architecture details
- **[v7.2.0 Incremental Updates](v7.2.0-architecture-incremental-updates.md)** - Incremental HNSW implementation
- **[Algorithms](algorithms.md)** - Detailed algorithm descriptions and complexity analysis
- **[Technical Details](technical-details.md)** - Deep dives into implementation specifics
