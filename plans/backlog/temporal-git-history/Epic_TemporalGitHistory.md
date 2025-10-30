# Epic: Temporal Git History Semantic Search

## Epic Overview

**Problem Statement:**
AI coding agents (like Claude Code) need semantic search across git history to find removed code, understand pattern evolution, prevent regressions, and debug with historical context. Current tools (git blame, git log) only provide text-based or current-state views.

**Target Users:**
- Claude Code and other AI coding agents working on codebases
- Developers needing historical context for debugging
- Teams tracking code evolution patterns

**Success Criteria:**
- Semantic temporal queries working across full git history
- Code evolution visualization with commit messages and diffs
- 80% storage savings via git blob deduplication
- Query performance <300ms on 40K+ repos
- Backward compatibility maintained (space-only search unchanged)

## Features

### 01_Feat_TemporalIndexing
**Purpose:** Build and maintain temporal index of git history
**Stories:**
- 01_Story_GitHistoryIndexingWithBlobDedup: Index repository git history with deduplication
- 02_Story_IncrementalIndexingWithWatch: Incremental indexing with watch mode integration

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

-- Performance indexes for 40K+ repos
CREATE INDEX idx_trees_blob_commit ON trees(blob_hash, commit_hash);
CREATE INDEX idx_commits_date_hash ON commits(date, hash);
CREATE INDEX idx_trees_commit ON trees(commit_hash);
```

**Blob Registry** (`.code-indexer/index/temporal/blob_registry.json`):
- Maps blob_hash → point_ids from existing vectors
- Start with JSON, auto-migrate to SQLite if >100MB
- Lazy loading with in-memory caching

**Temporal Metadata** (`.code-indexer/index/temporal/temporal_meta.json`):
- Tracks last_indexed_commit, indexing state, statistics

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

3. **No Default Commit Limits:**
   - Index ALL commits by default
   - Optional --max-commits and --since-date for control

4. **Error Handling:**
   - Graceful fallback to space-only search
   - Clear warnings and suggested actions

5. **Backward Compatibility:**
   - All temporal features opt-in via flags
   - Existing functionality unchanged

### Implementation Order
1. Story 1 (Feature 01): Git History Indexing (Foundation)
2. Story 2 (Feature 01): Incremental Indexing (Optimization)
3. Story 1 (Feature 02): Time-Range Filtering (Core Query)
4. Story 2 (Feature 02): Point-in-Time Query (Advanced)
5. Story 1 (Feature 03): Evolution Display (Visualization)
6. Story 1 (Feature 04): Golden Repo Registration with Temporal (API Server)
7. Story 1 (Feature 05): Temporal Query Parameters via API (API Server)

## Acceptance Criteria

### Functional Requirements
- [ ] Temporal indexing with `cidx index --index-commits`
- [ ] Time-range queries with `--time-range`
- [ ] Point-in-time queries with `--at-commit`
- [ ] Evolution display with `--show-evolution`
- [ ] Incremental indexing on re-runs
- [ ] Watch mode integration with config

### Performance Requirements
- [ ] Query performance <300ms on 40K+ repos
- [ ] 80% storage savings via deduplication
- [ ] SQLite indexes optimized for scale

### Quality Requirements
- [ ] Graceful error handling with fallback
- [ ] Lazy loading preserves startup time
- [ ] All tests passing including E2E

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite performance at scale | High | Compound indexes, WAL mode, tuning |
| Storage growth | Medium | Blob deduplication, JSON→SQLite migration |
| Module import overhead | High | Mandatory lazy loading pattern |
| Git operations slow | Medium | Incremental indexing, caching |
| Breaking changes | High | All features opt-in via flags |

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
- No default commit limits (index everything)
- Graceful degradation critical
- MANDATORY lazy loading from CLAUDE.md