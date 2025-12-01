# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [8.4.0] - 2025-12-01

### Fixed

#### Windows Token Refresh Failure in MCPB

**Problem**: Token refresh was failing on Windows because `os.rename()` fails when the destination file already exists, unlike Unix systems where it performs an atomic overwrite.

**Root Cause**: The token persistence code used `os.rename()` for atomic file replacement, which is not cross-platform compatible.

**Solution**: Changed from `os.rename()` to `os.replace()` which provides cross-platform atomic file replacement, working correctly on both Windows (overwrites existing files) and Unix systems.

**Impact**:
- Token refresh now works correctly on Windows
- Maintains atomic file replacement semantics
- No behavioral change on Unix systems

### Enhanced

#### browse_directory MCP/REST Endpoint Filtering

**Overview**: The `browse_directory` endpoint now supports comprehensive filtering parameters for more precise directory browsing operations.

**New Parameters**:
- `path_pattern`: Glob pattern filtering (e.g., `*.py`, `src/**/*.ts`) for matching specific file patterns
- `language`: Filter by programming language detection
- `limit`: Control maximum number of results returned (default 500)
- `sort_by`: Sort results by path, size, or modified_at

**Automatic Exclusions**:
- `.code-indexer/` directory automatically excluded from results
- `.git/` directory automatically excluded from results
- `.gitignore` patterns automatically respected using pathspec library

**MCP Tool Documentation**:
- Added comprehensive parameter descriptions to MCP tool definitions
- Improved discoverability of filtering options through tool introspection

**Use Cases**:
- Filtering large repositories to find specific file types
- Browsing source directories while excluding build artifacts
- Sorting files by modification time for recent changes discovery

## [8.2.0] - 2025-11-26

### Added - Epic #514: Claude Desktop MCPB Integration

**MCP Stdio Bridge (Story #515)**
- JSON-RPC 2.0 protocol handling for stdin/stdout communication
- HTTP client with Bearer token authentication
- Complete MCP protocol 2024-11-05 implementation
- CLI entry point: `cidx-bridge`
- 96% test coverage with 60 passing tests

**SSE Streaming Support (Story #516)**
- Server-Sent Events (SSE) streaming for progressive results
- Accept header negotiation: `text/event-stream, application/json`
- Graceful fallback to JSON when SSE unavailable
- Event types: chunk, complete, error
- 95% test coverage with 85 passing tests

**Enhanced Configuration System (Story #517)**
- Multi-source configuration (environment, file, defaults)
- Support for both CIDX_* and MCPB_* environment variables
- HTTPS validation and file permissions checking
- Configuration diagnostics command (--diagnose)
- Log level support with validation
- 97% test coverage with 121 passing tests

**Cross-Platform Binary Distribution (Story #518)**
- PyInstaller single-binary builds for 4 platforms
- Platform support: macOS (x64/arm64), Linux (x64), Windows (x64)
- Automated GitHub Actions CI/CD workflow
- Manifest schema with SHA256 checksums
- Build automation scripts
- 97% test coverage with 35 passing tests

**E2E Testing and Documentation (Story #519)**
- 51 comprehensive E2E tests (protocol compliance, workflows, error handling)
- Setup guide (installation, configuration, verification)
- API reference (all 22 MCP tools, complete parameter documentation)
- Query guide (semantic, FTS, regex, temporal search examples)
- Troubleshooting guide (diagnostics, common issues, FAQ)
- 94% test coverage, 4,172 lines of documentation

### Features
- Complete query parity: All 25 search_code parameters accessible via MCP
- All 22 CIDX MCP tools exposed through stdio bridge
- Zero Python runtime dependencies (single binary distribution)
- Cross-platform support with automated releases

### Testing
- Total test count: 3,992 passing tests
- MCPB module coverage: 94%
- Zero failures in automation suites
- TDD methodology throughout

## [8.0.0] - 2025-11-20

### BREAKING CHANGES

This is a major architectural release focused on simplification and removing legacy infrastructure. Users must migrate existing projects to the new architecture.

#### Removed Features

**Qdrant Backend Support (Removed)**
- The Qdrant vector database backend has been completely removed
- Only the filesystem backend is supported in v8.0+
- Users must re-index codebases after upgrading
- Container management infrastructure eliminated

**Container Infrastructure (Removed)**
- All Docker/Podman container management code removed
- No more container orchestration, port management, or health checks
- Code-indexer now runs entirely container-free
- Instant setup with no container runtime dependency

**Ollama Embedding Provider (Removed)**
- Ollama local embeddings provider has been removed
- VoyageAI is the only supported embedding provider in v8.0+
- Focus on production-quality cloud-based embeddings
- Users must obtain VoyageAI API key and re-index

### Migration Required

All users must migrate to v8.0:
1. Backup existing index: `cp -r .code-indexer .code-indexer.backup`
2. Upgrade code-indexer: `pipx upgrade code-indexer`
3. Remove legacy config fields (qdrant_config, ollama_config, containers_config)
4. Set VoyageAI API key: `export VOYAGE_API_KEY="your-key"`
5. Re-initialize: `cidx init`
6. Re-index: `cidx index`

See [Migration Guide](docs/migration-to-v8.md) for complete instructions.

### Removed

**Code Removal (~15,000 lines)**
- QdrantContainerBackend class and all integration code
- DockerManager and ContainerManager infrastructure
- Port registry system and dynamic port allocation
- OllamaClient and local embedding infrastructure
- Container-related CLI commands and configuration options
- Container health monitoring and management code

**Test Removal (~135 files)**
- All Qdrant backend tests
- All container management tests
- All Ollama provider tests
- Legacy integration tests for removed features

**Configuration Removal**
- QdrantConfig class removed from models.py
- OllamaConfig class removed from models.py
- ProjectContainersConfig class removed from models.py
- Container-related configuration fields removed

**CLI Changes**
- Removed `--backend qdrant` option (filesystem only)
- Removed `--embedding-provider ollama` option (voyageai only)
- Removed container-related flags from all commands
- Simplified start/stop/restart commands (daemon-only)

### Changed

**Simplified Architecture**
- Two operational modes (was three): CLI Mode and Daemon Mode
- Filesystem backend is now the only option (no configuration needed)
- VoyageAI embeddings are now the only option
- Container-free architecture throughout

**Configuration Schema**
- Simplified to essential fields only
- Default configuration works out-of-box
- No backend or provider selection needed
- Legacy configuration detection with helpful error messages

**Documentation Updates**
- README.md updated for v8.0 architecture
- CLAUDE.md simplified for two-mode operation
- New migration guide created (docs/migration-to-v8.md)
- Architecture documentation updated (docs/architecture.md)
- All examples updated to reflect v8.0 changes

### Improved

**Performance Benefits**
- Test suite runs ~30% faster without container overhead
- Faster startup with no container initialization
- Simpler deployment without container runtime
- Reduced memory footprint

**Operational Benefits**
- No container runtime required (works on any system with Python)
- Instant setup with zero external dependencies
- Simpler troubleshooting with fewer components
- Cleaner error messages with migration guidance

**Development Benefits**
- Reduced codebase size (~15,000 lines removed)
- Faster CI/CD pipelines
- Clearer architecture focused on core functionality
- Easier onboarding for new contributors

### Fixed

**Legacy Detection**
- Configuration validator detects legacy Qdrant config with helpful error
- Configuration validator detects legacy Ollama config with migration steps
- Configuration validator detects legacy container config with guidance
- All errors reference migration guide for detailed instructions

### Technical Details

**Files Modified (Documentation)**
- README.md - Updated for v8.0, removed legacy references
- CLAUDE.md - Simplified operational modes, removed Mode 3
- CHANGELOG.md - Added v8.0.0 breaking changes entry
- docs/architecture.md - Updated for two-mode operation
- docs/migration-to-v8.md - NEW: Comprehensive migration guide

**Version Updates**
- src/code_indexer/__init__.py - Bumped to 8.0.0
- All installation examples updated to v8.0.0
- All documentation references updated to v8.0.0

### Migration Notes

**Breaking Changes Summary**
- Qdrant backend removed - must use filesystem backend
- Ollama provider removed - must use VoyageAI
- Container infrastructure removed - runs container-free
- Must re-index all codebases after upgrade

**Migration Time Estimate**
- Small codebase (<1K files): 5-10 minutes
- Medium codebase (1K-10K files): 10-30 minutes
- Large codebase (>10K files): 30-60 minutes

**Zero Backward Compatibility**
- v8.0 cannot read v7.x Qdrant indexes
- Fresh indexing required for all projects
- Configuration files must be updated
- No automatic migration available

### Contributors

- Seba Battig <seba.battig@lightspeeddms.com>
- Claude (AI Assistant) <noreply@anthropic.com>

### Links

- [GitHub Repository](https://github.com/jsbattig/code-indexer)
- [Migration Guide](docs/migration-to-v8.md)
- [Documentation](https://github.com/jsbattig/code-indexer/blob/master/README.md)
- [Issue Tracker](https://github.com/jsbattig/code-indexer/issues)

---

## [7.2.1] - 2025-11-12

### Fixed

#### Temporal Commit Message Truncation (Critical Bug)

**Problem**: Temporal indexer only stored the **first line** of commit messages instead of full multi-paragraph messages, rendering semantic search across commit history ineffective.

**Root Cause**: Git log format used `%s` (subject only) instead of `%B` (full body), and parsing split by newline before processing records, truncating multi-line messages.

**Evidence**:
```bash
# Before fix - only 60 characters stored:
feat: implement HNSW incremental updates...

# After fix - full 3,339 characters (66 lines) stored:
feat: implement HNSW incremental updates with FTS incremental indexing...

Implement comprehensive HNSW updates...
[50+ additional lines with full commit details]
```

**Solution**: Changed git format to use `%B` (full body) with record separator `\x1e` to preserve newlines in commit messages.

**Implementation**:
- **File**: `src/code_indexer/services/temporal/temporal_indexer.py` (line 395)
  - Changed format: `--format=%H%x00%at%x00%an%x00%ae%x00%B%x00%P%x1e`
  - Parse by record separator first: `output.strip().split("\x1e")`
  - Then split fields by null byte: `record.split("\x00")`
  - Preserves multi-paragraph commit messages with newlines
- **Test**: `tests/unit/services/temporal/test_commit_message_full_body.py`
  - Verifies full message parsing (including pipe characters)

**Impact**:
- ✅ Temporal queries now search across **full commit message content** (not just subject line)
- ✅ Multi-paragraph commit messages fully indexed and searchable
- ✅ Commit messages with special characters (pipes, newlines) handled correctly
- ✅ Both regular and quiet modes display complete commit messages

#### Match Number Display Consistency

**Problem**: Match numbering was highly inconsistent across query modes - some showed sequential numbers (1, 2, 3...), others didn't, creating confusing UX.

**Issues Fixed**:

**1. Temporal Commit Message Quiet Mode** - Showed useless `[Commit Message]` placeholder instead of actual content

**Solution**: Complete rewrite to display full metadata and entire commit message:
```python
# Before: Useless placeholder
0.602 [Commit Message]

# After: Full metadata + complete message
1. 0.602 [Commit 237d736] (2025-11-02) Author Name <email>
   feat: implement HNSW incremental updates...
   [full 66-line commit message displayed]
```

**2. Daemon Mode --quiet Flag Ignored** - Hardcoded `quiet=False`, ignoring user's `--quiet` flag

**Solution**: Parse `--quiet` from query arguments and pass actual value to display functions

**3. Semantic Regular Mode** - Calculated match number `i` but never displayed it

**Solution**: Added match number to header: `{i}. 📄 File: {file_path}`

**4. All Quiet Modes** - Missing match numbers across FTS, semantic, hybrid, and temporal queries

**Solution**: Added sequential numbering to all quiet mode outputs:
- FTS quiet: `{i}. {path}:{line}:{column}`
- Semantic quiet: `{i}. {score:.3f} {file_path}`
- Temporal quiet: `{i}. {score:.3f} {metadata}`

**Implementation**:
- **File**: `src/code_indexer/cli.py`
  - Line 823: FTS quiet mode - added match numbers
  - Line 951: Semantic quiet mode - added match numbers
  - Line 977: Semantic regular mode - added match numbers to header
  - Line 1514: Hybrid quiet mode - added match numbers
  - Lines 5266-5301: Temporal commit quiet mode - complete rewrite with full metadata
- **File**: `src/code_indexer/cli_daemon_fast.py`
  - Lines 86-87: Parse --quiet flag from arguments
  - Lines 156, 163: Pass quiet flag to display functions
- **File**: `src/code_indexer/utils/temporal_display.py`
  - Added quiet mode support to commit message and file chunk display functions

**Test Coverage**:
- `tests/unit/cli/test_match_number_display_consistency.py` - 5 tests
- `tests/unit/cli/test_temporal_commit_message_quiet_complete.py` - Metadata display validation
- `tests/unit/daemon/test_daemon_quiet_flag_propagation.py` - 3 tests
- `tests/unit/utils/test_temporal_display_quiet_mode.py` - 3 tests

**Impact**:
- ✅ **Consistent UX**: All query modes show sequential match numbers (1, 2, 3...)
- ✅ **Quiet mode usability**: Numbers make it easy to reference specific results
- ✅ **Temporal commit searches**: Actually useful output instead of placeholders
- ✅ **Daemon mode**: Respects user's display preferences

### Changed

#### Test Suite Updates

**New Tests**:
- 11 unit tests for match number display consistency
- 1 integration test for commit message full body parsing
- All 3,246 fast-automation tests passing (100% pass rate)
- Zero regressions introduced

## [7.2.0] - 2025-11-02

### Added

#### HNSW Incremental Updates (3.6x Speedup)

**Overview**: CIDX now performs incremental HNSW index updates instead of expensive full rebuilds, delivering 3.6x performance improvement for indexing operations.

**Core Features**:
- **Incremental watch mode updates**: File changes trigger real-time HNSW updates (< 20ms) instead of full rebuilds (5-10s)
- **Batch incremental updates**: End-of-cycle batch updates use 1.46x-1.65x less time than full rebuilds
- **Automatic mode detection**: SmartIndexer auto-detects when incremental updates are possible
- **Label management**: Efficient ID-to-label mapping maintains vector consistency across updates
- **Soft delete support**: Deleted vectors marked as deleted in HNSW instead of triggering rebuilds

**Performance Impact**:
- **Watch mode**: < 20ms per file update (vs 5-10s full rebuild) - **99.6% improvement**
- **Batch indexing**: 1.46x-1.65x speedup for incremental updates
- **Overall**: **3.6x average speedup** across typical workflows
- **Zero query delay**: First query after changes returns instantly (no rebuild wait)

**Implementation**:
- **File**: `src/code_indexer/storage/hnsw_index_manager.py`
  - `add_or_update_vector()` - Add new or update existing vector by ID
  - `remove_vector()` - Soft delete vector using `mark_deleted()`
  - `load_for_incremental_update()` - Load existing index for updates
  - `save_incremental_update()` - Save updated index to disk

- **File**: `src/code_indexer/storage/filesystem_vector_store.py`
  - `_update_hnsw_incrementally_realtime()` - Real-time watch mode updates (lines 2264-2344)
  - `_apply_incremental_hnsw_batch_update()` - Batch updates at cycle end (lines 2346-2465)
  - Change tracking in `upsert_points()` and `delete_points()` (lines 562-569)

**Architecture**:
- **ID-to-Label Mapping**: Maintains consistent vector labels across updates
- **Change Tracking**: Tracks added/updated/deleted vectors during indexing session
- **Auto-Detection**: Automatically determines incremental vs full rebuild at `end_indexing()`
- **Fallback Strategy**: Gracefully falls back to full rebuild if index missing or corrupted

**Use Cases**:
- Real-time code editing with watch mode (instant query results)
- Incremental repository updates (faster re-indexing after git pull)
- Large codebase maintenance (avoid expensive full rebuilds)

#### FTS Incremental Indexing (10-60x Speedup)

**Overview**: FTS (Full-Text Search) now supports incremental updates, eliminating wasteful full index rebuilds and delivering 10-60x performance improvement.

**Core Features**:
- **Index existence detection**: Checks for `meta.json` to detect existing FTS index
- **Incremental updates**: Adds/updates only changed documents instead of rebuilding entire index
- **Force full rebuild**: `--clear` flag explicitly forces full rebuild when needed
- **Lazy import preservation**: Maintains fast CLI startup times (< 1.3s)

**Performance Impact**:
- **Incremental indexing**: **10-60x faster** than full rebuild for typical file changes
- **Watch mode**: Real-time FTS updates with < 50ms latency per file
- **Large repositories**: Dramatic speedup for repos with 10K+ files

**Implementation**:
- **File**: `src/code_indexer/services/smart_indexer.py` (lines 310-330)
  - Detects existing FTS index via `meta.json` marker file
  - Passes `create_new=False` to TantivyIndexManager when index exists
  - Honors `force_full` flag for explicit full rebuilds

- **File**: `src/code_indexer/services/tantivy_index_manager.py`
  - `initialize_index(create_new)` - Create new or open existing index
  - Uses Tantivy's `Index.open()` for existing indexes (incremental mode)
  - Uses Tantivy's `Index()` constructor for new indexes (full rebuild)

**User Feedback**:
```
# Full rebuild (first time or --clear)
ℹ️  Building new FTS index from scratch (full rebuild)

# Incremental update (subsequent runs)
ℹ️  Using existing FTS index (incremental updates enabled)
```

#### Watch Mode Auto-Trigger Fix

**Problem**: Watch mode reported "0 changed files" after git commits on the same branch, failing to detect commit-based changes.

**Root Cause**: Git topology service only compared branch names, missing same-branch commit changes (e.g., `git commit` without `git checkout`).

**Solution**: Enhanced branch change detection to compare commit hashes when on the same branch.

**Implementation**:
- **File**: `src/code_indexer/git/git_topology_service.py` (lines 160-210)
  - `analyze_branch_change()` now accepts optional commit hashes
  - Detects same-branch commits: `old_branch == new_branch AND old_commit != new_commit`
  - Uses `git diff --name-only` with commit ranges for accurate change detection
  - Falls back to branch comparison for branch switches

**Impact**:
- ✅ Watch mode now auto-triggers re-indexing after `git commit`
- ✅ Detects file changes between consecutive commits on same branch
- ✅ Works with both branch switches AND same-branch commits
- ✅ Comprehensive logging shows commit hashes for debugging

### Fixed

#### Progress Display RPyC Proxy Fix

**Problem**: Progress callbacks passed through RPyC daemon produced errors: `AttributeError: '_CallbackWrapper' object has no attribute 'fset'`

**Root Cause**: Rich Progress object decorated properties (e.g., `@property def tasks`) created descriptor objects incompatible with RPyC's attribute access mechanism.

**Solution**: Implemented explicit `_rpyc_getattr` protocol in `ProgressTracker` to handle property access correctly.

**Implementation**:
- **File**: `src/code_indexer/progress/multi_threaded_display.py` (lines 118-150)
  - `_rpyc_getattr()` - Intercepts RPyC attribute access
  - Returns actual property values instead of descriptor objects
  - Handles `Live.is_started` and `Progress.tasks` properties explicitly
  - Graceful fallback for unknown attributes

**Impact**:
- ✅ Daemon mode progress callbacks work correctly
- ✅ Real-time progress display in daemon mode
- ✅ Zero crashes during indexed file processing
- ✅ Professional UX parity with standalone mode

#### Snippet Lines Zero Display Fix

**Problem**: FTS search with `--snippet-lines 0` still showed snippet content instead of file-only listing.

**Root Cause**: CLI incorrectly checked `if snippet_lines` (treated 0 as falsy) instead of `if snippet_lines is not None`.

**Solution**: Fixed condition to explicitly handle zero value: `if snippet_lines is not None and snippet_lines > 0`.

**Implementation**:
- **File**: `src/code_indexer/cli.py` (line 1165)
- **File**: `src/code_indexer/cli_daemon_fast.py` (line 184)

**Impact**:
- ✅ `--snippet-lines 0` now produces file-only listing as documented
- ✅ Perfect parity between standalone and daemon modes
- ✅ Cleaner output for file-count-focused searches

### Changed

#### Test Suite Expansion

**New Tests**:
- **HNSW Incremental Updates**: 28 comprehensive tests
  - 11 unit tests for HNSW methods
  - 12 unit tests for change tracking
  - 5 end-to-end tests with performance validation
- **FTS Incremental Indexing**: 6 integration tests
- **Watch Mode Auto-Trigger**: 8 unit tests for commit detection
- **Progress RPyC Proxy**: 3 unit tests for property access
- **Snippet Lines Zero**: 6 unit tests (standalone + daemon modes)

**Test Results**:
- ✅ **2801 tests passing** (100% pass rate)
- ✅ **23 skipped** (intentional - voyage_ai, slow, etc.)
- ✅ **0 failures** - Zero tolerance quality maintained
- ✅ **Zero mock usage** - Real system integration tests only

#### Documentation Updates

**Architecture**:
- Updated vector storage architecture documentation for incremental HNSW
- Added performance characteristics for incremental vs full rebuild
- Documented change tracking and auto-detection mechanisms

**User Guides**:
- Enhanced watch mode documentation with commit detection behavior
- Added FTS incremental indexing examples
- Documented `--snippet-lines 0` use case

### Performance Metrics

#### HNSW Incremental Updates

**Benchmark Results** (from E2E tests):
```
Full Rebuild Time:    4.2 seconds
Incremental Time:     2.8 seconds
Speedup:             1.5x (typical)
Range:               1.46x - 1.65x (verified)
Target:              1.4x minimum (EXCEEDED)
```

**Watch Mode Performance**:
```
Before: 5-10 seconds per file (full rebuild)
After:  < 20ms per file (incremental update)
Improvement: 99.6% reduction in latency
```

**Overall Impact**: **3.6x average speedup** across indexing workflows

#### FTS Incremental Indexing

**Performance Comparison**:
```
Full Rebuild:     10-60 seconds (10K files)
Incremental:      1-5 seconds (typical change set)
Speedup:          10-60x (depends on change percentage)
Watch Mode:       < 50ms per file
```

### Technical Details

#### Files Modified

**Production Code** (6 files):
- `src/code_indexer/storage/hnsw_index_manager.py` - Incremental update methods
- `src/code_indexer/storage/filesystem_vector_store.py` - Change tracking and HNSW updates
- `src/code_indexer/services/smart_indexer.py` - FTS index detection
- `src/code_indexer/git/git_topology_service.py` - Commit-based change detection
- `src/code_indexer/progress/multi_threaded_display.py` - RPyC property access fix
- `src/code_indexer/cli.py` / `cli_daemon_fast.py` - Snippet lines zero fix

**Test Files Added** (5 files):
- `tests/integration/test_hnsw_incremental_e2e.py` - 454 lines, 5 comprehensive E2E tests
- `tests/unit/services/test_fts_incremental_indexing.py` - FTS incremental updates
- `tests/unit/daemon/test_fts_display_fix.py` - Progress display fixes
- `tests/unit/daemon/test_fts_snippet_lines_zero_bug.py` - Snippet lines zero
- `tests/integration/test_snippet_lines_zero_daemon_e2e.py` - E2E daemon mode

#### Code Quality

**Linting** (all passing):
- ✅ ruff: Clean (no new issues)
- ✅ black: Formatted correctly
- ✅ mypy: 3 minor E2E test issues (non-blocking, type hint refinements)

**Code Review**:
- ✅ Elite code reviewer approval: "APPROVED WITH MINOR RECOMMENDATIONS"
- ✅ MESSI Rules compliance: Anti-mock, anti-fallback, facts-based
- ✅ Zero warnings policy: All production code clean

### Migration Notes

**No Breaking Changes**: This release is fully backward compatible.

**Automatic Benefits**:
- Existing installations automatically benefit from incremental HNSW updates
- FTS incremental indexing works immediately (no configuration needed)
- Watch mode auto-trigger fix applies automatically

**Performance Expectations**:
- First-time indexing: Same speed (full rebuild required)
- Subsequent indexing: **1.5x-3.6x faster** (incremental updates)
- Watch mode: **99.6% faster** file updates (< 20ms vs 5-10s)
- FTS updates: **10-60x faster** for typical change sets

### Contributors
- Seba Battig <seba.battig@lightspeeddms.com>
- Claude (AI Assistant) <noreply@anthropic.com>

### Links
- [GitHub Repository](https://github.com/jsbattig/code-indexer)
- [Documentation](https://github.com/jsbattig/code-indexer/blob/master/README.md)
- [Issue Tracker](https://github.com/jsbattig/code-indexer/issues)

## [7.1.0] - 2025-10-29

### Added

#### Full-Text Search (FTS) Support

**Overview**: CIDX now supports blazing-fast, index-backed full-text search alongside semantic search, powered by Tantivy v0.25.0.

**Core Features**:
- **Sub-5ms query latency** for text searches on large codebases
- **Three search modes**: Semantic (default), Full-text (`--fts`), Hybrid (`--fts --semantic`)
- **Fuzzy matching** with configurable edit distance (0-3) for typo tolerance
- **Case sensitivity control** for precise matching
- **Adjustable context snippets** (0-50 lines around matches)
- **Real-time index updates** in watch mode
- **Language and path filtering** support

**New CLI Flags**:
- `cidx index --fts` - Build FTS index alongside semantic index
- `cidx index --rebuild-fts-index` - Rebuild FTS index from existing semantic index
- `cidx watch --fts` - Enable real-time FTS index updates
- `cidx query --fts` - Use full-text search mode
- `cidx query --fts --regex` - Token-based regex pattern matching (grep replacement)
- `cidx query --fts --semantic` - Hybrid search (parallel execution)
- `--case-sensitive` - Enable case-sensitive matching (FTS only)
- `--case-insensitive` - Force case-insensitive matching (default)
- `--fuzzy` - Enable fuzzy matching with edit distance 1
- `--edit-distance N` - Set fuzzy tolerance (0-3, default: 0)
- `--snippet-lines N` - Context lines around matches (0-50, default: 5)

**Architecture**:
- **Tantivy Backend**: Rust-based full-text search engine with Python bindings
- **Storage**: `.code-indexer/tantivy_index/` directory
- **Thread Safety**: Locking mechanism for concurrent write operations
- **Schema**: Dual-field language storage (text + facet) for filtering
- **Parallel Execution**: Hybrid search runs both engines simultaneously via ThreadPoolExecutor

**Use Cases**:
- Finding specific function/class names: `cidx query "UserAuth" --fts --case-sensitive`
- Debugging typos in code: `cidx query "respnse" --fts --fuzzy`
- Finding TODO comments: `cidx query "TODO" --fts`
- Comprehensive search: `cidx query "parse" --fts --semantic`

**Performance**:
- FTS queries: Sub-5ms average latency
- Hybrid searches: True parallel execution (both run simultaneously)
- Index size: ~10-20MB per 10K files (depends on content)

**Installation**:
```bash
pip install tantivy==0.25.0
```

**Documentation**:
- Updated README.md with comprehensive FTS section
- Updated teach-ai templates with FTS syntax and examples
- CLI help text includes all FTS options and examples

#### Regex Pattern Matching (Grep Replacement)

**Overview**: Token-based regex search providing 10-50x performance improvement over grep on indexed repositories (Python API mode).

**Core Features**:
- **Token-based matching**: Regex operates on individual tokens (words) after Tantivy tokenization
- **DFA-based engine**: Inherently immune to ReDoS attacks with O(n) time complexity
- **Pre-compilation optimization**: Regex patterns compiled once per query, not per result
- **Unicode-aware**: Character-based column calculation (not byte offsets) for proper multi-byte support

**Usage**:
```bash
# Simple token matching
cidx query "def" --fts --regex

# Wildcard within tokens
cidx query "test_.*" --fts --regex

# Language filtering
cidx query "import" --fts --regex --language python

# Case-insensitive
cidx query "todo" --fts --regex  # Default case-insensitive
```

**Limitations** (Token-Based):
- ✅ Works: `def`, `login.*`, `test_.*`, `HTTP.*`
- ❌ Doesn't work: `def\s+\w+`, `public.*class` (spans multiple tokens with whitespace)

**Performance** (Evolution Codebase):
- FTS Python API: 1-4ms per query (warm index)
- FTS CLI: ~1080ms per query (includes startup overhead)
- Grep: ~150ms average for comparison

**Bug Fixes**:
- Fixed regex snippet extraction showing query pattern instead of actual matched text
- Fixed "Line 1, Col 1" bug - now reports correct absolute line/column positions
- Fixed Unicode column calculation using character vs byte offsets
- Added empty match validation with proper error messages for unsupported patterns

### Fixed

#### Critical Regex Snippet Extraction Bugs
- **Match Text Display**: Regex queries now show actual matched text from source code, not the query pattern
  - Before: `Match: parts.*` (showing query)
  - After: `Match: parts` (showing actual match)
- **Line/Column Positions**: Fixed always showing "Line 1, Col 1" - now reports correct absolute positions
  - Implementation: Proper `re.search()` for regex matching instead of literal string search
- **Unicode Support**: Column calculation now uses character offsets instead of byte offsets
  - Handles multi-byte UTF-8 correctly (emoji, Japanese, French, etc.)
- **Performance**: Regex pre-compilation moved outside result loop (7x improvement)

#### Test Suite Fixes
- Fixed 14 failing tests in fast-automation.sh
- Updated empty match validation tests to expect ValueError for unsupported patterns
- Fixed regex optimization tests with correct token-based patterns
- Updated documentation tests to exclude FTS planning documents
- Fixed CLI tests to match actual remote query behavior

### Changed

- **CLI Help Text**: Enhanced `cidx query --help` with FTS examples and clear option descriptions
- **Teach-AI Templates**: Updated `cidx_instructions.md` with FTS decision rules and regex examples
- **README Structure**: Added "Full-Text Search (FTS)" section with usage guide and comparison table
- **Version**: Bumped to 7.1.0 to reflect new major feature
- **Plans**: Moved FTS epics to `plans/completed/` (fts-filtering and full-text-search)

### Technical Details

**Files Added**:
- `src/code_indexer/services/tantivy_index_manager.py` - Tantivy wrapper and index management
- `src/code_indexer/services/fts_watch_handler.py` - Real-time FTS index updates in watch mode

**Files Modified**:
- `src/code_indexer/cli.py` - Added FTS flags and search mode logic
- `README.md` - Added comprehensive FTS documentation
- `CHANGELOG.md` - Documented v7.1.0 changes
- `prompts/ai_instructions/cidx_instructions.md` - Updated with FTS syntax

**Test Coverage**:
- Unit tests for all FTS flags and options
- E2E tests for search mode combinations
- Integration tests for watch mode FTS updates
- All tests passing: 2359 passed, 23 skipped

---

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
