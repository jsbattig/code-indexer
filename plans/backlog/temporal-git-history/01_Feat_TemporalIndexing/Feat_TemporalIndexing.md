# Feature: Temporal Indexing

## Feature Overview

**Purpose:** Build and maintain a temporal index of git history that enables semantic search across all commits while optimizing storage through blob deduplication.

**User Value:** Enable AI agents and developers to search across the entire history of a codebase, finding code that has been removed, understanding how patterns evolved, and leveraging historical context for better decision-making.

## User Stories

### Story 1: Git History Indexing with Blob Deduplication
**Priority:** P0 (Foundation)
**Effort:** L (Large)
**Description:** Index the complete git history of a repository, building a SQLite database of commits and file trees while deduplicating storage by reusing existing vectors for unchanged blobs.

### Story 2: Incremental Indexing with Watch Mode Integration
**Priority:** P0 (Critical)
**Effort:** M (Medium)
**Description:** Enable incremental indexing that only processes new commits and integrate with watch mode to maintain the temporal index automatically.

## Technical Design

### Components

**TemporalIndexer** (`src/code_indexer/services/temporal_indexer.py`):
```python
class TemporalIndexer:
    def __init__(self, config_manager: ConfigManager, vector_store: FilesystemVectorStore):
        self.config_manager = config_manager
        self.vector_store = vector_store
        self.db_path = Path(".code-indexer/index/temporal/commits.db")

    def index_commits(self, max_commits: Optional[int] = None,
                      since_date: Optional[str] = None) -> IndexingResult:
        """Main entry point for temporal indexing"""

    def _build_blob_registry(self) -> Dict[str, List[str]]:
        """Scan FilesystemVectorStore to build blob_hash → point_ids mapping"""

    def _get_commit_history(self, max_commits: Optional[int],
                           since_date: Optional[str]) -> List[CommitInfo]:
        """Execute git log to get commit history"""

    def _process_commit(self, commit_hash: str) -> ProcessedCommit:
        """Process single commit - get metadata and tree"""

    def _store_commit_data(self, commits: List[ProcessedCommit]):
        """Store commit data in SQLite with transactions"""

    def _identify_missing_blobs(self, all_blobs: Set[str]) -> Set[str]:
        """Identify blobs not in current HEAD that need embedding"""

    def _index_missing_blobs(self, missing_blobs: Set[str]):
        """Use HighThroughputProcessor to embed missing blobs"""
```

### Storage Design

**SQLite Schema:**
- `commits` table: Stores commit metadata
- `trees` table: Maps commits to file paths and blob hashes
- Compound indexes for performance at scale

**Blob Registry:**
- JSON format initially: `{"blob_hash": ["point_id1", "point_id2"]}`
- Auto-migration to SQLite when >100MB
- In-memory LRU cache for performance

**Temporal Metadata:**
```json
{
    "last_indexed_commit": "abc123def",
    "index_version": "1.0",
    "total_commits": 5000,
    "total_unique_blobs": 15000,
    "deduplication_ratio": 0.82,
    "last_updated": "2024-01-15T10:30:00Z"
}
```

### Integration Points

**CLI Integration:**
```python
# In cli.py index command
@click.option("--index-commits", is_flag=True, help="Index git commit history")
@click.option("--max-commits", type=int, help="Maximum commits to index")
@click.option("--since-date", help="Index commits since date (YYYY-MM-DD)")
```

**Config Integration:**
```python
class IndexingConfig(BaseModel):
    enable_temporal: bool = Field(default=False,
                                 description="Enable temporal indexing in watch mode")
```

**Watch Mode Integration:**
- Read `enable_temporal` from config
- If enabled, run incremental temporal indexing on new commits
- Update temporal_meta.json with latest state

### Performance Optimizations

**SQLite Tuning:**
```python
# Connection setup
conn.execute("PRAGMA journal_mode=WAL")  # Concurrent reads
conn.execute("PRAGMA cache_size=8192")   # 64MB cache
conn.execute("PRAGMA page_size=8192")    # Larger pages
conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
```

**Batch Processing:**
- Process commits in batches of 100
- Use transactions for bulk inserts
- Run ANALYZE after bulk operations

**Lazy Loading:**
```python
# MANDATORY: Lazy import pattern
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3  # Type hints only

def index_commits(self):
    import sqlite3  # Lazy import when actually used
    # ... implementation
```

## Acceptance Criteria

### Story 1: Git History Indexing
- [ ] Creates SQLite database at `.code-indexer/index/temporal/commits.db`
- [ ] Builds blob registry mapping existing vectors
- [ ] Identifies and indexes only missing blobs
- [ ] Stores complete commit metadata and trees
- [ ] Shows progress: "Indexing commits: 500/5000"
- [ ] Handles large repos (40K+ commits) efficiently
- [ ] Achieves >80% storage savings via deduplication

### Story 2: Incremental Indexing
- [ ] Reads last_indexed_commit from temporal_meta.json
- [ ] Only processes new commits since last index
- [ ] Watch mode reads enable_temporal config
- [ ] Updates temporal index automatically on new commits
- [ ] Shows progress: "Processing 5 new commits..."
- [ ] Handles branch switches and rebases correctly

## Testing Requirements

### Unit Tests
- `test_temporal_indexer.py`:
  - Test blob registry building
  - Test commit processing
  - Test SQLite operations
  - Test incremental logic

### Integration Tests
- `test_temporal_indexing_integration.py`:
  - Test full indexing flow
  - Test deduplication ratio
  - Test watch mode integration

### Manual Tests
**Story 1:**
1. Run `cidx index --index-commits` on code-indexer repo
2. Verify `.code-indexer/index/temporal/` created
3. Check SQLite database has commits and trees
4. Verify blob_registry.json created
5. Check deduplication ratio >80%

**Story 2:**
1. Make new commits to repo
2. Run `cidx index --index-commits` again
3. Verify only new commits processed
4. Enable temporal in config
5. Run `cidx start --watch`
6. Make commits and verify auto-update

## Error Handling

**Git Errors:**
- Handle detached HEAD state
- Handle shallow clones (suggest --unshallow)
- Handle missing git binary

**Storage Errors:**
- Handle disk space issues
- Handle SQLite lock timeouts
- Handle corrupted database

**Performance Issues:**
- Warn if >100K commits without --max-commits
- Show progress for long operations
- Allow cancellation with Ctrl+C

## Dependencies

- Git command-line tool
- sqlite3 (lazy loaded)
- Existing: FilesystemVectorStore, HighThroughputProcessor

## Notes

**Conversation Context:**
- User emphasized 40K+ repo support
- No default commit limits (index everything)
- Watch mode configuration-driven
- Storage efficiency critical (80% target)