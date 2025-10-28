# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0.1] - 2025-10-28

### Fixed

#### Critical: fix-config Filesystem Backend Compatibility

**Problem**: The `fix-config` command was not respecting the filesystem backend setting when fixing CoW (Copy-on-Write) clones. It would:
- Lose the `vector_store.provider = "filesystem"` configuration
- Force regeneration of Qdrant-specific ports and container names
- Attempt to initialize Qdrant client and create CoW symlinks
- Result: Filesystem backend projects would fail with "Permission denied: podman-compose" errors

**Root Cause**:
- Line 836 in `config_fixer.py` only preserved `embedding_provider`, not `vector_store`
- Steps 4-7 always executed Qdrant operations regardless of backend type
- No conditional logic to skip Qdrant operations for filesystem backend

**Solution (Option A: Conditional Container Configuration)**:
1. **Preserve vector_store** in config dict (lines 837-840)
2. **Detect backend type** before Qdrant operations (lines 453-456)
3. **Skip Qdrant client initialization** if filesystem backend (line 459-460)
4. **Skip CoW symlink creation** if filesystem backend (lines 474-477)
5. **Skip collection checks** if filesystem backend (lines 486-489)
6. **Skip port/container regeneration** if filesystem backend (lines 951-954)

**Impact**:
- ✅ Fixes claude-server CoW clone issue where `vector_store` configuration was lost
- ✅ Eliminates unnecessary Qdrant configuration for filesystem backend
- ✅ Reduces `fix-config` execution time and resource usage
- ✅ Maintains backward compatibility with Qdrant backend

**Testing Results**:
- Before: `fix-config` applied 8 fixes (included Qdrant port/container regeneration)
- After: `fix-config` applies 3 fixes (path, project name, git commit only)
- Verification: `vector_store.provider` preserved as `"filesystem"`
- Verification: `project_ports` and `project_containers` remain `null` (not regenerated)
- Verification: `cidx start` and `cidx query` work correctly after `fix-config`

**Files Modified**:
- `src/code_indexer/services/config_fixer.py` (35 insertions, 14 deletions)

---

## [7.0.0] - 2025-10-28

### 🎉 Major Release: Filesystem-Based Architecture with HNSW Indexing

This is a **major architectural release** featuring a complete rewrite of the vector storage system, introducing a filesystem-based backend with HNSW graph indexing for 300x query performance improvements while eliminating container dependencies.

### Added

#### Filesystem Vector Store (Epic - 9 Stories)
- **Zero-Container Architecture**: Filesystem-based vector storage eliminates Qdrant container dependency
- **Git-Trackable Storage**: JSON format stored in `.code-indexer/index/` for version control
- **Path-as-Vector Quantization**: 4-level directory depth using projection matrix (64-dim → 4 levels)
- **Smart Git-Aware Storage**:
  - Clean files: Store only git blob hash (space efficient)
  - Dirty files: Store full chunk_text (captures uncommitted changes)
  - Non-git repos: Store full chunk_text
- **Hash-Based Staleness Detection**: SHA256 hashing for precise change detection (more accurate than mtime)
- **3-Tier Content Retrieval Fallback**:
  1. Current file (if unchanged)
  2. Git blob lookup (if file modified/moved)
  3. Error with recovery guidance
- **Complete QdrantClient API Compatibility**: Drop-in replacement for existing workflows
- **Backward Compatibility**: Old configurations default to Qdrant backend
- **CLI Integration**:
  - `cidx init --vector-store filesystem` (default)
  - `cidx init --vector-store qdrant` (opt-in containers)
  - Seamless no-op operations for start/stop with filesystem backend

**Performance (Django validation - 7,575 vectors, 3,501 files)**:
- Indexing: 7m 20s (476.8 files/min)
- Storage: 147 MB (space-efficient with git blob hashes)
- Queries: ~6s (5s API call + <1s filesystem search)

#### HNSW Graph-Based Indexing
- **300x Query Speedup**: ~20ms queries (vs 6+ seconds with binary index)
- **HNSW Algorithm**: Hierarchical Navigable Small World graph for approximate nearest neighbor search
  - **Complexity**: O(log N) average case (vs O(N) linear scan)
  - **Configuration**: M=16 connections, ef_construction=200, ef_query=50
  - **Space**: 154 MB for 37K vectors
- **Automatic Rebuilding**: `--rebuild-index` flag for manual rebuilds, automatic rebuild on watch mode staleness
- **Staleness Coordination**: File locking system for watch mode integration
  - Watch mode marks index stale (instant, no rebuild)
  - Query rebuilds on first use (amortized cost)
  - **Performance**: 99%+ improvement (0ms vs 10+ seconds per file change)

#### Binary ID Index with mmap
- **Fast Lookups**: <20ms cached loads using memory-mapped files
- **Format**: Binary packed format `[num_entries:uint32][id_len:uint16, id:utf8, path_len:uint16, path:utf8]...`
- **Thread-Safe**: RLock for concurrent access
- **Incremental Updates**: Append-only design with corruption detection
- **Tandem Building**: Built alongside HNSW during indexing

#### Parallel Query Execution
- **2-Thread Architecture**:
  - Thread 1: Load HNSW + ID index (I/O bound)
  - Thread 2: Generate query embedding (CPU/Network bound)
- **Performance Gains**: 15-30% latency reduction (175-265ms typical savings)
- **Overhead Reporting**: Transparent threading overhead display (7-16%)
- **Always Parallel**: Simplified code path, removed conditional execution

#### CLI Exclusion Filters
- **Language Exclusion**: `--exclude-language javascript` with multi-language support
- **Path Exclusion**: `--exclude-path "*/tests/*"` with glob pattern matching
- **Conflict Detection**: Automatic detection of contradictory filters with helpful warnings
- **Multiple Filter Support**: Combine inclusions and exclusions seamlessly
- **26 Common Patterns**: Documented exclusion patterns for tests, dependencies, build artifacts
- **Performance**: <0.01ms overhead per filter (500x better than 5ms requirement)
- **Comprehensive Testing**: 111 tests (370% of requirements)

#### teach-ai Command
- **Multi-Platform Support**: Claude, Codex, Gemini, OpenCode, Q, Junie
- **Template System**: Markdown templates in `prompts/ai_instructions/`
- **Smart Merging**: Uses Claude CLI for intelligent CIDX section updates
- **Scope Options**:
  - `--project`: Install in project root
  - `--global`: Install in platform's global config location
  - `--show-only`: Preview without writing
- **Non-Technical Editing**: Template files editable by non-developers
- **KISS Principle**: Simple text file updates instead of complex parsing

#### Status Command Enhancement
- **Index Validation**: Check HNSW index health and staleness
- **Recovery Guidance**: Actionable recommendations for index issues
- **Backend-Aware Display**: Show appropriate status for filesystem vs Qdrant
- **Storage Statistics**: Display index size, vector count, dimension info

### Changed

#### Breaking Changes
- **Default Backend Changed**: Filesystem backend is now default (was Qdrant)
- **FilesystemVectorStore.search() API**: Now requires `query + embedding_provider` instead of pre-computed `query_vector`
  - Old API: `search(query_vector=vec, ...)`
  - New API: `search(query="text", embedding_provider=provider, ...)`
  - QdrantClient maintains old API for backward compatibility
- **Matrix Multiplication Service Removed**: Replaced by binary caching and HNSW indexing
  - Removed resident HTTP service for matrix operations
  - Removed YAML matrix format
  - Performance now achieved through HNSW graph indexing

#### Improvements
- **Timing Display Optimization**:
  - Breakdown now appears after "Vector search" line (not after git filtering)
  - Fixed double-counting in total time calculation
  - Added threading overhead transparency
  - Shows actual wall clock time vs work time
- **CLI Streamlining**: Removed Data Cleaner status for filesystem backend (Qdrant-only service)
- **Language Filter Enhancement**: Added `multiple=True` to `--language` flag for multi-language queries
- **Import Optimization**: Eliminated 440-630ms voyageai library import overhead with embedded tokenizer

### Technical Architecture

#### Vector Storage System
```
.code-indexer/index/<collection>/
├── hnsw_index.bin              # HNSW graph (O(log N) search)
├── id_index.bin                # Binary mmap ID→path mapping
├── collection_meta.json        # Metadata + staleness tracking
└── vectors/                    # Quantized path structure
    └── <level1>/<level2>/<level3>/<level4>/
        └── vector_<uuid>.json  # Individual vector + payload
```

#### Query Algorithm Complexity
- **Overall**: O(log N + K) where K = limit * 2, K << N
- **HNSW Graph Search**: O(log N) average case
  - Hierarchical graph navigation (M=16 connections per node)
  - Greedy search with backtracking (ef=50 candidates)
- **Candidate Loading**: O(K) for top-K results
  - Load K candidate vectors from filesystem
  - Apply filters and exact cosine similarity scoring
- **Practical Performance**: ~20ms for 37K vectors (300x faster than O(N) linear scan)

#### Search Strategy Evolution
```
Version 6.x: Linear Scan O(N)
- Load all N vectors into memory
- Calculate similarity for all vectors
- Sort and return top-K
- Time: 6+ seconds for 7K vectors

Version 7.0: HNSW Graph O(log N)
- Load HNSW graph index
- Navigate graph to find K approximate nearest neighbors
- Load only K candidate vectors
- Apply exact scoring and filters
- Time: ~20ms for 37K vectors (300x faster)
```

#### Performance Decision Analysis

**Why HNSW over Alternatives**:
1. **vs FAISS**: HNSW simpler to integrate, no external dependencies, better for small-medium datasets (<100K vectors)
2. **vs Annoy**: HNSW provides better accuracy-speed tradeoff, dynamic updates possible
3. **vs Product Quantization**: HNSW maintains full precision, no accuracy loss from quantization
4. **vs Brute Force**: 300x speedup justifies ~150MB index overhead

**Quantization Strategy**:
- **64-dim projection**: Optimal balance of accuracy vs path depth (tested 32, 64, 128, 256)
- **4-level depth**: Enables 64^4 = 16.8M unique paths (sufficient for large codebases)
- **2-bit quantization**: Further reduces from 64 to 4 levels per dimension

**Parallel Execution Trade-offs**:
- **Threading overhead**: 7-16% acceptable cost for 175-265ms latency reduction
- **2 threads optimal**: More threads add coordination overhead without I/O benefit
- **Always parallel**: Removed conditional logic for code simplicity

**Storage Format Trade-offs**:
- **JSON vs Binary**: JSON chosen for git-trackability and debuggability despite 3-5x size overhead
- **Individual files vs single file**: Individual files enable incremental updates, git tracking
- **Binary ID index exception**: Performance-critical component where binary format justified

### Fixed
- **Critical Qdrant Backend Stub Bug**: Fixed stub implementation causing crashes when Qdrant containers unavailable
- **Git Branch Filtering**: Corrected to check file existence (not branch name match) for accurate filtering
- **Storage Duplication**: Fixed bug where both blob hash AND content were stored (should be either/or)
- **Timing Display**: Fixed placement of breakdown timing (now appears after "Vector search" line)
- **teach-ai f-string**: Removed unnecessary f-string prefix causing linter warnings
- **Path Exclusion Tests**: Updated 8 test assertions for correct metadata key ("path" not "file_path")

### Deprecated
- **Matrix Multiplication Resident Service**: Removed in favor of HNSW indexing
- **YAML Matrix Format**: Removed with matrix service
- **FilesystemVectorStore query_vector parameter**: Use `query + embedding_provider` instead

### Performance Metrics

#### Query Performance Comparison
```
Version 6.5.0 (Binary Index):
- 7K vectors: ~6 seconds
- Algorithm: O(N) linear scan

Version 7.0.0 (HNSW Index):
- 37K vectors: ~20ms (300x faster)
- Algorithm: O(log N) graph search
- Parallel execution: 175-265ms latency reduction
```

#### Storage Efficiency
```
Django Codebase (3,501 files → 7,575 vectors):
- Total Storage: 147 MB
- Average per vector: 19.4 KB
- Space Savings: 60-70% from git blob hash storage
```

#### Indexing Performance
```
Django Codebase (3,501 files):
- Indexing Time: 7m 20s
- Throughput: 476.8 files/min
- HNSW Build: Included in indexing time
- ID Index Build: Tandem with HNSW (no overhead)
```

### Documentation
- Added 140-line "Exclusion Filters" section to README with 26 common patterns
- Added CIDX semantic search instructions to project CLAUDE.md
- Enhanced epic documentation with comprehensive unit test requirements
- Added query performance optimization epic with TDD validation
- Documented backend switching workflow (destroy → reinit → reindex)
- Added command behavior matrix for transparent no-ops

### Testing
- **Total Tests**: 2,291 passing (was ~2,180)
- **New Test Coverage**:
  - 111 exclusion filter tests (path, language, integration)
  - 72 filesystem vector store tests
  - 21 backend abstraction tests
  - 21 status monitoring tests
  - 12 parallel execution tests
  - Comprehensive HNSW, ID index, and integration tests
- **Performance Tests**: Validated 300x speedup and <20ms queries
- **Platform Testing**: teach-ai command tested across 6 AI platforms

### Migration Guide

#### From Version 6.x to 7.0.0

**Automatic Migration (Recommended)**:
New installations default to filesystem backend. Existing installations continue using Qdrant unless explicitly switched.

**Manual Migration to Filesystem Backend**:
```bash
# 1. Backup existing index (optional)
cidx backup  # If available

# 2. Destroy existing Qdrant index
cidx clean --all-collections

# 3. Reinitialize with filesystem backend
cidx init --vector-store filesystem

# 4. Start services (no-op for filesystem, but safe to run)
cidx start

# 5. Reindex your codebase
cidx index

# 6. Verify
cidx status
cidx query "your test query"
```

**Stay on Qdrant (No Action Required)**:
If you prefer containers, your existing configuration continues working. To explicitly use Qdrant for new projects:
```bash
cidx init --vector-store qdrant
```

**Breaking API Changes**:
If you have custom code calling `FilesystemVectorStore.search()` directly:
```python
# OLD (no longer works):
results = store.search(query_vector=embedding, collection_name="main")

# NEW (required):
results = store.search(
    query="your search text",
    embedding_provider=voyage_client,
    collection_name="main"
)
```

### Contributors
- Seba Battig <seba.battig@lightspeeddms.com>
- Claude (AI Assistant) <noreply@anthropic.com>

### Links
- [GitHub Repository](https://github.com/jsbattig/code-indexer)
- [Documentation](https://github.com/jsbattig/code-indexer/blob/master/README.md)
- [Issue Tracker](https://github.com/jsbattig/code-indexer/issues)

---

## [6.5.0] - 2025-10-24

### Initial Release
(Version 6.5.0 and earlier changes not documented in this CHANGELOG)
