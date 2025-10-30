# Story: Git History Indexing with Blob Deduplication

## Story Description

**As a** AI coding agent
**I want to** index a repository's complete git history with storage deduplication
**So that** I can search across all historical code without massive storage overhead

**Conversation Context:**
- User specified need for semantic search across git history to find removed code
- Emphasized 80% storage savings via git blob deduplication
- Required to handle 40K+ commit repositories efficiently

## Acceptance Criteria

- [ ] Running `cidx index --index-commits` indexes the repository's git history
- [ ] Creates SQLite database at `.code-indexer/index/temporal/commits.db` with commit graph
- [ ] Builds blob registry at `.code-indexer/index/temporal/blob_registry.json` mapping blob_hash → point_ids
- [ ] Reuses existing vectors for blobs already in HEAD (deduplication)
- [ ] Only embeds new blobs not present in current HEAD
- [ ] Stores temporal metadata in `.code-indexer/index/temporal/temporal_meta.json`
- [ ] Shows progress during indexing: "Indexing commits: 500/5000 (10%)"
- [ ] Achieves >80% storage savings through blob deduplication
- [ ] Handles large repositories (40K+ commits) without running out of memory

## Technical Implementation

### Entry Point (CLI)
```python
# In cli.py index command
@click.option("--index-commits", is_flag=True,
              help="Index git commit history for temporal search")
@click.option("--max-commits", type=int,
              help="Maximum number of commits to index (default: all)")
@click.option("--since-date",
              help="Index commits since date (YYYY-MM-DD)")
def index(..., index_commits, max_commits, since_date):
    if index_commits:
        # Lazy import for performance
        from src.code_indexer.services.temporal_indexer import TemporalIndexer
        temporal_indexer = TemporalIndexer(config_manager, vector_store)
        result = temporal_indexer.index_commits(max_commits, since_date)
```

### Core Implementation
```python
class TemporalIndexer:
    def index_commits(self, max_commits: Optional[int] = None,
                      since_date: Optional[str] = None) -> IndexingResult:
        """Index git history with blob deduplication"""

        # Step 1: Build blob registry from existing vectors
        blob_registry = self._build_blob_registry()

        # Step 2: Get commit history from git
        commits = self._get_commit_history(max_commits, since_date)

        # Step 3: Process each commit to get trees
        all_blobs = set()
        commit_data = []
        for commit in commits:
            processed = self._process_commit(commit.hash)
            commit_data.append(processed)
            all_blobs.update(processed.blob_hashes)
            self._progress_callback(len(commit_data), len(commits))

        # Step 4: Store in SQLite
        self._store_commit_data(commit_data)

        # Step 5: Identify missing blobs (not in HEAD)
        missing_blobs = self._identify_missing_blobs(all_blobs, blob_registry)

        # Step 6: Index missing blobs
        if missing_blobs:
            self._index_missing_blobs(missing_blobs)

        # Step 7: Save metadata
        self._save_temporal_metadata(commits[-1].hash, len(commits),
                                    len(all_blobs), len(missing_blobs))

        return IndexingResult(
            total_commits=len(commits),
            unique_blobs=len(all_blobs),
            new_blobs_indexed=len(missing_blobs),
            deduplication_ratio=1 - (len(missing_blobs) / len(all_blobs))
        )
```

### Blob Registry Building
```python
def _build_blob_registry(self) -> Dict[str, List[str]]:
    """Scan FilesystemVectorStore for existing blob hashes"""
    registry = {}
    collection_path = self.vector_store.collection_path

    # Walk all vector JSON files
    for json_path in collection_path.glob("**/*.json"):
        with open(json_path) as f:
            point_data = json.load(f)
            blob_hash = point_data.get("payload", {}).get("blob_hash")
            if blob_hash:
                if blob_hash not in registry:
                    registry[blob_hash] = []
                registry[blob_hash].append(point_data["id"])

    # Save registry
    registry_path = Path(".code-indexer/index/temporal/blob_registry.json")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w") as f:
        json.dump(registry, f)

    return registry
```

### SQLite Storage
```python
def _initialize_database(self):
    """Create SQLite tables with proper indexes"""
    import sqlite3  # Lazy import

    conn = sqlite3.connect(self.db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            hash TEXT PRIMARY KEY,
            date INTEGER NOT NULL,
            author_name TEXT,
            author_email TEXT,
            message TEXT,
            parent_hashes TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trees (
            commit_hash TEXT NOT NULL,
            file_path TEXT NOT NULL,
            blob_hash TEXT NOT NULL,
            PRIMARY KEY (commit_hash, file_path),
            FOREIGN KEY (commit_hash) REFERENCES commits(hash)
        )
    """)

    # Performance indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_blob_commit ON trees(blob_hash, commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_date_hash ON commits(date, hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_commit ON trees(commit_hash)")

    # Performance tuning
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=8192")

    conn.commit()
    return conn
```

### Git Integration
```python
def _get_commit_history(self, max_commits: Optional[int],
                       since_date: Optional[str]) -> List[CommitInfo]:
    """Get commit history from git"""
    cmd = ["git", "log", "--format=%H|%at|%an|%ae|%P", "--reverse"]

    if since_date:
        cmd.extend(["--since", since_date])

    if max_commits:
        cmd.extend(["-n", str(max_commits)])

    result = subprocess.run(cmd, capture_output=True, text=True)

    commits = []
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split("|")
            commits.append(CommitInfo(
                hash=parts[0],
                timestamp=int(parts[1]),
                author_name=parts[2],
                author_email=parts[3],
                parent_hashes=parts[4]
            ))

    return commits

def _get_commit_tree(self, commit_hash: str) -> List[TreeEntry]:
    """Get file tree for a commit"""
    cmd = ["git", "ls-tree", "-r", commit_hash]
    result = subprocess.run(cmd, capture_output=True, text=True)

    entries = []
    for line in result.stdout.strip().split("\n"):
        if line:
            # Format: mode type hash<tab>path
            parts = line.split("\t")
            mode_type_hash = parts[0].split(" ")
            if mode_type_hash[1] == "blob":  # Only care about files
                entries.append(TreeEntry(
                    path=parts[1],
                    blob_hash=mode_type_hash[2]
                ))

    return entries
```

## Test Scenarios

### Manual Test Plan
1. **Setup:**
   - Use code-indexer repository
   - Ensure clean state: `rm -rf .code-indexer/index/temporal/`
   - Run regular indexing first: `cidx index`

2. **Execute Temporal Indexing:**
   ```bash
   cidx index --index-commits
   ```

3. **Verify Database Created:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db ".tables"
   # Should show: commits trees

   sqlite3 .code-indexer/index/temporal/commits.db "SELECT COUNT(*) FROM commits"
   # Should show commit count
   ```

4. **Verify Blob Registry:**
   ```bash
   jq 'keys | length' .code-indexer/index/temporal/blob_registry.json
   # Should show number of unique blobs
   ```

5. **Check Deduplication:**
   ```bash
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.deduplication_ratio'
   # Should be > 0.8 (80%)
   ```

6. **Test with Limits:**
   ```bash
   cidx index --index-commits --max-commits 100
   cidx index --index-commits --since-date 2024-01-01
   ```

### Automated Tests
```python
def test_git_history_indexing_with_deduplication():
    """Test complete temporal indexing with blob deduplication"""
    # Setup test repo with history
    with temp_git_repo() as repo_path:
        # Create commits
        create_test_commits(repo_path, count=10)

        # Run regular indexing
        indexer = SmartIndexer(config_manager)
        indexer.index_directory(repo_path)

        # Run temporal indexing
        temporal = TemporalIndexer(config_manager, vector_store)
        result = temporal.index_commits()

        # Verify results
        assert result.total_commits == 10
        assert result.deduplication_ratio > 0.5  # Some files unchanged

        # Check database
        conn = sqlite3.connect(".code-indexer/index/temporal/commits.db")
        commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        assert commit_count == 10

        # Check blob registry
        with open(".code-indexer/index/temporal/blob_registry.json") as f:
            registry = json.load(f)
            assert len(registry) > 0
```

## Error Scenarios

1. **No git repository:**
   - Error: "Not a git repository"
   - Action: Display clear error message

2. **Shallow clone:**
   - Warning: "Shallow clone detected. Run 'git fetch --unshallow' for full history"
   - Action: Continue with available commits

3. **Large repository (>100K commits):**
   - Warning: "Repository has 150,000 commits. Consider using --max-commits"
   - Action: Continue but show progress

4. **Disk space issues:**
   - Error: "Insufficient disk space for temporal index"
   - Action: Cleanup partial index, show required space

## Performance Considerations

- Batch SQLite inserts in transactions of 1000 rows
- Use WAL mode for concurrent reads during indexing
- Build blob registry incrementally to avoid memory issues
- Show progress every 100 commits
- Allow cancellation with Ctrl+C (cleanup partial state)

## Dependencies

- Git CLI (version 2.0+)
- sqlite3 Python module (lazy loaded)
- Existing FilesystemVectorStore
- Existing HighThroughputProcessor for embedding

## Notes

**Conversation Requirements:**
- No default commit limits - index everything by default
- 80% storage savings target via deduplication
- Must handle 40K+ commit repositories
- Progress reporting during long operations