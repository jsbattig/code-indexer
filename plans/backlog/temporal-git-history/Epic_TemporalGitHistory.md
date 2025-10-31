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

**Blob Registry** (`.code-indexer/index/temporal/blob_registry.json`):
- Maps blob_hash → point_ids from existing vectors
- Start with JSON, auto-migrate to SQLite if >100MB
- Lazy loading with in-memory caching

**Temporal Metadata** (`.code-indexer/index/temporal/temporal_meta.json`):
- Tracks last_indexed_commit, indexing state, statistics
- Records indexed_branches (list of branch names/patterns)
- Stores indexing_mode ('single-branch' or 'all-branches')
- Branch-specific stats: commits_per_branch, deduplication_ratio

### Component Architecture

**New Components:**
1. `TemporalIndexer` - Orchestrates git history indexing
2. `TemporalSearchService` - Handles temporal queries
3. `TemporalFormatter` - Formats temporal results with Rich

**Integration Points:**
- CLI: New flags for index and query commands
- Config: `enable_temporal` setting
- Watch Mode: Maintains temporal index if enabled

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

### Functional Requirements
- [ ] Temporal indexing with `cidx index --index-commits` (defaults to current branch)
- [ ] Multi-branch indexing with `cidx index --index-commits --all-branches`
- [ ] Selective branch indexing with `cidx index --index-commits --branches "feature/*,bugfix/*"`
- [ ] Time-range queries with `--time-range` showing branch context
- [ ] Point-in-time queries with `--at-commit` with branch information
- [ ] Evolution display with `--show-evolution` including branch visualization
- [ ] Incremental indexing on re-runs preserving branch metadata
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

## Dependencies

- Existing: FilesystemVectorStore, HNSW index, HighThroughputProcessor
- New: sqlite3 (lazy), difflib (lazy), git commands
- Configuration: enable_temporal setting
- Feature 04 depends on Features 01-03 (CLI temporal implementation must exist)
- Feature 05 depends on Feature 04 (temporal index must be created during registration)
- Both API features integrate with existing server architecture (GoldenRepoManager, SemanticSearchService)

## Testing Strategy

### Unit Tests
- TemporalIndexer blob registry building
- TemporalSearchService filtering logic
- SQLite performance with mock data

### Integration Tests
- End-to-end temporal indexing
- Query filtering accuracy
- Watch mode temporal updates

### Manual Tests
- Each story has specific manual test scenarios
- Performance validation on large repos
- Error handling verification

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