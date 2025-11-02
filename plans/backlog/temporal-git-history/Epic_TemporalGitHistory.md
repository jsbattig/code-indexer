# Epic: Temporal Git History Semantic Search

## Epic Overview

**Problem Statement:**
AI coding agents (like Claude Code) need semantic search across git history to find removed code, understand pattern evolution, prevent regressions, and debug with historical context. Current tools (git blame, git log) only provide text-based or current-state views.

**Target Users:**
- Claude Code and other AI coding agents working on codebases
- Developers needing historical context for debugging
- Teams tracking code evolution patterns

**Success Criteria:**
- Semantic temporal queries working across git history
- Code evolution visualization with commit messages, diffs, and branch context
- 92%+ storage savings via git blob deduplication
- Query performance <300ms on 40K+ repos
- Backward compatibility maintained (space-only search unchanged)
- Cost-effective default behavior (single branch) with opt-in for complete multi-branch coverage

**Branch Strategy (Based on Analysis of Evolution Repository):**
- **Default:** Index current branch only (development/main) - provides 91.6% commit coverage
- **Opt-in:** `--all-branches` flag for complete multi-branch history
- **Rationale:** Indexing all branches in large repos increases storage by ~85% for only ~8% more commits
- **Flexibility:** Track branch metadata for all indexed commits to support future branch-aware queries

## Features

### 01_Feat_TemporalIndexing
**Purpose:** Build and maintain temporal index of git history with branch awareness
**Stories:**
- 01_Story_GitHistoryIndexingWithBlobDedup: Index repository git history with deduplication and branch metadata
- 02_Story_IncrementalIndexingWithWatch: Incremental indexing with watch mode integration
- 03_Story_SelectiveBranchIndexing: Selective branch indexing with pattern matching

### 02_Feat_TemporalQueries
**Purpose:** Enable semantic search across git history with temporal filters
**Stories:**
- 01_Story_TimeRangeFiltering: Query with time-range filtering
- 02_Story_PointInTimeQuery: Query at specific commit

### 03_Feat_CodeEvolutionVisualization
**Purpose:** Display code evolution with diffs and commit context
**Stories:**
- 01_Story_EvolutionDisplayWithCommitContext: Display evolution timeline with diffs

### 04_Feat_APIServerTemporalRegistration
**Purpose:** Enable golden repository registration with temporal indexing via API
**Stories:**
- 01_Story_GoldenRepoRegistrationWithTemporal: Admin registers golden repos with enable_temporal flag

### 05_Feat_APIServerTemporalQuery
**Purpose:** Enable temporal search via API with time-range, point-in-time, and evolution queries
**Stories:**
- 01_Story_TemporalQueryParametersViaAPI: Users query with temporal parameters via POST /api/query

## Technical Architecture

### Storage Architecture

**SQLite Database** (`.code-indexer/index/temporal/commits.db`):
```sql
CREATE TABLE commits (
    hash TEXT PRIMARY KEY,
    date INTEGER NOT NULL,
    author_name TEXT,
    author_email TEXT,
    message TEXT,
    parent_hashes TEXT
);

CREATE TABLE trees (
    commit_hash TEXT NOT NULL,
    file_path TEXT NOT NULL,
    blob_hash TEXT NOT NULL,
    PRIMARY KEY (commit_hash, file_path),
    FOREIGN KEY (commit_hash) REFERENCES commits(hash)
);

-- NEW: Branch metadata tracking
CREATE TABLE commit_branches (
    commit_hash TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    is_head INTEGER DEFAULT 0,  -- 1 if this was HEAD when indexed
    indexed_at INTEGER NOT NULL,  -- Unix timestamp
    PRIMARY KEY (commit_hash, branch_name),
    FOREIGN KEY (commit_hash) REFERENCES commits(hash)
);

-- Performance indexes for 40K+ repos
CREATE INDEX idx_trees_blob_commit ON trees(blob_hash, commit_hash);
CREATE INDEX idx_commits_date_hash ON commits(date, hash);
CREATE INDEX idx_trees_commit ON trees(commit_hash);
CREATE INDEX idx_commit_branches_hash ON commit_branches(commit_hash);
CREATE INDEX idx_commit_branches_name ON commit_branches(branch_name);
```

**Blob Registry** (`.code-indexer/index/temporal/blob_registry.db`):
- SQLite database mapping blob_hash → point_ids from existing vectors
- Required for large-scale repos (40K+ files, 10GB+ with history)
- Indexed for fast lookups (microseconds per blob)
- Lazy connection with result caching

**Temporal Metadata** (`.code-indexer/index/temporal/temporal_meta.json`):
- Tracks last_indexed_commit, indexing state, statistics
- Records indexed_branches (list of branch names/patterns)
- Stores indexing_mode ('single-branch' or 'all-branches')
- Branch-specific stats: commits_per_branch, deduplication_ratio

### Component Architecture

**New Components:**
1. `TemporalIndexer` - Orchestrates git history indexing (mode-agnostic)
2. `TemporalBlobScanner` - Discovers blobs in git history via `git ls-tree`
3. `GitBlobReader` - Reads blob content from git object store via `git cat-file`
4. `HistoricalBlobProcessor` - Parallel blob processing (analogous to HighThroughputProcessor)
5. `TemporalSearchService` - Handles temporal queries (mode-agnostic)
6. `TemporalFormatter` - Formats temporal results with Rich

**Integration Points:**
- CLI: New flags for index and query commands
- Config: `enable_temporal` setting
- Watch Mode: Maintains temporal index if enabled
- Daemon Mode: Automatic delegation when `daemon.enabled: true`

### Indexing Pipeline Reuse Strategy (CRITICAL)

**What We Index: Full Blob Versions, NOT Diffs**

Git blobs represent **complete file versions** at specific points in time. We index full blob content for semantic search, not diffs:

```
✅ CORRECT: Index full blob content
Commit abc123: user.py (blob def456)
→ Complete file: class User with all methods and context

❌ WRONG: Index diffs
Commit abc123: user.py diff
→ Partial: +def greet(): ... (no class context)
```

**Why Full Blobs:**
1. **Semantic search requires full context** - can't find code patterns in partial diffs
2. **Users want complete implementations** - "find removed authentication code" needs full class
3. **Git already stores blobs efficiently** - compression + deduplication is built-in
4. **Deduplication works better** - same content across commits = same blob hash = reuse vectors

**Pipeline Component Reuse (85% Reuse Rate):**

**✅ Reused AS-IS (No Changes):**
- `VectorCalculationManager` - Takes text chunks → embeddings (source-agnostic)
- `FilesystemVectorStore` - Writes vector JSON files (already supports blob_hash)
- `FixedSizeChunker` - Add `chunk_text(text)` method for git blobs
- Threading patterns (`ThreadPoolExecutor`, `CleanSlotTracker`)
- Progress callback mechanism (works with any source)

**🆕 New Git-Specific Components:**
- `TemporalBlobScanner` - Replaces FileFinder (walks git history, not disk)
- `GitBlobReader` - Replaces file reads (extracts from git object store)
- `HistoricalBlobProcessor` - Orchestrates: blob → read → chunk → vector → store

**Architecture Comparison:**

```
Workspace Indexing (HEAD):
  Disk Files → FileIdentifier → FixedSizeChunker
    → VectorCalculationManager → FilesystemVectorStore

Git History Indexing (Temporal):
  Git Blobs → GitBlobReader → FixedSizeChunker.chunk_text()
    → VectorCalculationManager → FilesystemVectorStore
           ↑                         ↑
        SAME COMPONENTS REUSED
```

**Deduplication Strategy:**
```python
# For each commit
for commit in commits:
    # 1. Get all blobs in commit (git ls-tree)
    all_blobs = scanner.get_blobs_for_commit(commit)  # 150 blobs

    # 2. Check blob registry (SQLite lookup, microseconds)
    new_blobs = [b for b in all_blobs if not registry.has_blob(b.hash)]
    # Result: ~12 new blobs (92% already have vectors)

    # 3. Process ONLY new blobs (reuse existing for rest)
    if new_blobs:
        processor.process_blobs_high_throughput(new_blobs)
        # Uses VectorCalculationManager + FilesystemVectorStore
```

**Performance Expectations (42K files, 10GB repo):**
- First run: 150K blobs → 92% dedup → 12K new embeddings → 4-7 minutes
- Incremental: Only new commit blobs → <1 minute

**See Analysis Documents:**
- `.analysis/temporal_indexing_pipeline_reuse_strategy.md` - Complete implementation guide
- `.analysis/temporal_blob_registry_sqlite_decision.md` - SQLite rationale

### Daemon Mode Architecture

**CRITICAL: Temporal indexing works identically in standalone and daemon modes.**

**Standalone Mode (daemon.enabled: false):**
- CLI directly instantiates `TemporalIndexer`
- Executes indexing in-process with direct progress callbacks
- Progress bar displayed directly in terminal

**Daemon Mode (daemon.enabled: true):**
- CLI delegates to daemon via `_index_via_daemon()` with `index_commits` flag
- Daemon's `exposed_index_blocking()` instantiates `TemporalIndexer` internally
- Executes indexing synchronously (blocking RPC call)
- Progress callbacks streamed back to CLI over RPyC connection
- Client displays progress bar in real-time (perfect UX parity with standalone)
- Cache automatically invalidated before and after indexing

**Mode Detection:**
- Automatic based on `.code-indexer/config.json` daemon configuration
- Zero code changes needed in `TemporalIndexer` (mode-agnostic design)
- Same progress callback signature in both modes
- Same SQLite/file operations in both modes
- Same git subprocess calls in both modes

**Cache Invalidation (Daemon Mode Only):**
- Temporal indexing adds new vectors to FilesystemVectorStore for historical blobs
- Semantic HNSW index must be rebuilt to include new vectors
- FTS index (if enabled) must include new historical content
- **Already implemented** in `daemon/service.py::exposed_index_blocking()` (lines 195-199)
- No additional cache invalidation code needed

### Query Flow Architecture

**Two-Phase Query:**
1. Semantic Search: Existing HNSW index on FilesystemVectorStore
2. Temporal Filtering: SQLite filtering by time/commit

**Performance Targets:**
- Semantic HNSW search: ~200ms
- SQLite temporal filter: ~50ms
- Total: <300ms for typical queries

## Implementation Guidelines

### Critical Requirements

1. **Lazy Module Loading (MANDATORY from CLAUDE.md):**
   - ALL temporal modules MUST use lazy imports
   - Follow FTS lazy loading pattern from smart_indexer.py
   - Guarantee: `cidx --help` and non-temporal queries unchanged

2. **Storage Optimization:**
   - SQLite with compound indexes for 40K+ repos
   - Blob registry with SQLite migration path

3. **Branch-Aware Indexing Strategy:**
   - Default: Index current branch only (cost-effective, 91%+ coverage)
   - Opt-in: `--all-branches` flag for complete multi-branch indexing
   - Track branch metadata for all commits to enable future branch-aware queries
   - Optional --max-commits and --since-date for control
   - Warn users about storage/API costs before indexing all branches

4. **Error Handling:**
   - Graceful fallback to space-only search
   - Clear warnings and suggested actions

5. **Backward Compatibility:**
   - All temporal features opt-in via flags
   - Existing functionality unchanged

### Implementation Order
1. Story 1 (Feature 01): Git History Indexing with Branch Metadata (Foundation)
2. Story 2 (Feature 01): Incremental Indexing with Branch Tracking (Optimization)
3. Story 3 (Feature 01): Selective Branch Indexing Patterns (Advanced)
4. Story 1 (Feature 02): Time-Range Filtering with Branch Context (Core Query)
5. Story 2 (Feature 02): Point-in-Time Query with Branch Info (Advanced)
6. Story 1 (Feature 03): Evolution Display with Branch Visualization (Visualization)
7. Story 1 (Feature 04): Golden Repo Registration with Temporal (API Server)
8. Story 1 (Feature 05): Temporal Query Parameters via API (API Server)

## Acceptance Criteria

### Functional Requirements (Both Modes)
- [ ] Temporal indexing with `cidx index --index-commits` (defaults to current branch)
- [ ] Multi-branch indexing with `cidx index --index-commits --all-branches`
- [ ] Selective branch indexing with `cidx index --index-commits --branches "feature/*,bugfix/*"`
- [ ] Time-range queries with `--time-range` showing branch context
- [ ] Point-in-time queries with `--at-commit` with branch information
- [ ] Evolution display with `--show-evolution` including branch visualization
- [ ] Incremental indexing on re-runs preserving branch metadata

### Daemon Mode Requirements
- [ ] Temporal indexing works in daemon mode when `daemon.enabled: true`
- [ ] CLI automatically delegates to daemon via `_index_via_daemon()`
- [ ] Progress callbacks stream correctly from daemon to client
- [ ] Progress bar displays identically in both modes (UX parity)
- [ ] Cache invalidation before temporal indexing (daemon mode)
- [ ] Cache automatically cleared after temporal indexing completes
- [ ] Graceful fallback to standalone mode if daemon unavailable
- [ ] All temporal flags passed correctly through delegation layer
- [ ] Watch mode integration with config (respects branch settings)
- [ ] Cost warning before indexing all branches in large repos

### Performance Requirements
- [ ] Query performance <300ms on 40K+ repos (with branch filtering)
- [ ] 92%+ storage savings via blob deduplication
- [ ] SQLite indexes optimized for scale including branch queries
- [ ] Single-branch indexing completes in reasonable time (similar to current indexing)
- [ ] Cost warning displays accurate estimates (storage, API calls) for multi-branch indexing

### Quality Requirements
- [ ] Graceful error handling with fallback
- [ ] Lazy loading preserves startup time
- [ ] All tests passing including E2E

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite performance at scale | High | Compound indexes, WAL mode, tuning, branch-specific indexes |
| Storage growth with all-branches | High | Default to single branch, cost warnings, blob deduplication |
| Module import overhead | High | Mandatory lazy loading pattern |
| Git operations slow | Medium | Incremental indexing, caching, single-branch default |
| Breaking changes | High | All features opt-in via flags |
| Users accidentally index all branches | Medium | Explicit flag required, cost warning with confirmation |
| Branch metadata overhead | Low | Indexed efficiently, minimal query impact |
| Daemon cache coherence | Medium | Automatic cache invalidation already implemented |
| Mode-specific bugs | Medium | Mode-agnostic design, comprehensive testing in both modes |

## Dependencies

- Existing: FilesystemVectorStore, HNSW index, HighThroughputProcessor
- Existing: Daemon mode architecture (cli_daemon_delegation.py, daemon/service.py)
- New: sqlite3 (lazy), difflib (lazy), git commands
- Configuration: enable_temporal setting
- Feature 04 depends on Features 01-03 (CLI temporal implementation must exist)
- Feature 05 depends on Feature 04 (temporal index must be created during registration)
- Both API features integrate with existing server architecture (GoldenRepoManager, SemanticSearchService)
- Daemon integration: No new dependencies (uses existing RPC and cache invalidation)

## Testing Strategy

### Unit Tests (Mode-Agnostic)
- TemporalIndexer blob registry building
- TemporalSearchService filtering logic
- SQLite performance with mock data
- Branch metadata storage and retrieval
- Cost estimation calculations

### Integration Tests (Standalone Mode)
- End-to-end temporal indexing in standalone mode
- Query filtering accuracy
- Watch mode temporal updates
- Single-branch vs all-branches behavior
- Cost warnings and confirmations

### Integration Tests (Daemon Mode)
- **CRITICAL:** All temporal operations must work in daemon mode
- Temporal indexing delegation via `_index_via_daemon()`
- Progress callback streaming from daemon to client
- Cache invalidation before/after temporal indexing
- UX parity verification (progress bar display)
- Graceful fallback to standalone if daemon unavailable
- Daemon remains responsive during long temporal indexing operations

### Manual Tests (Both Modes)
- Each story has specific manual test scenarios
- Performance validation on large repos (40K+ commits, 1000+ branches)
- Error handling verification
- **Test in daemon mode:** Enable daemon, verify identical behavior
- **Test cache coherence:** Query before/after temporal indexing in daemon mode
- **Test progress streaming:** Verify real-time progress in daemon mode

## Documentation Requirements

- Update README.md with temporal search examples
- Add temporal flags to --help
- Document performance tuning for large repos
- Include troubleshooting guide

## Success Metrics

- Query latency <300ms (P95)
- Storage efficiency >80% deduplication
- Zero impact on non-temporal operations
- User adoption by AI coding agents

## Notes

**Conversation Context:**
- User emphasized storage efficiency for 40K+ repos
- Configuration-driven watch mode integration
- Graceful degradation critical
- MANDATORY lazy loading from CLAUDE.md

**Branch Strategy Analysis (Evolution Repository):**
- Analyzed real-world large enterprise codebase (Evolution - 1,135 branches, 89K commits)
- Single branch (development): 81,733 commits = 91.6% coverage
- All branches: 89,234 commits = 100% coverage but 85.5% storage increase
- Deduplication effectiveness: 92.4% (most code shared between branches)
- Recommendation: Default to single branch, opt-in for all branches
- Cost transparency: Warn users before expensive operations
- See `.analysis/temporal_indexing_branch_analysis.md` for complete analysis

**Key Design Decisions:**
1. **Default = Current Branch Only:** Cost-effective, covers 90%+ of real-world use cases
2. **Explicit Opt-in for All Branches:** Users must consciously choose expensive operation
3. **Track Branch Metadata Always:** Even single-branch indexing records which branch
4. **Cost Warnings:** Display storage/API estimates before multi-branch indexing
5. **Future-Proof Schema:** Branch metadata enables future branch-aware queries