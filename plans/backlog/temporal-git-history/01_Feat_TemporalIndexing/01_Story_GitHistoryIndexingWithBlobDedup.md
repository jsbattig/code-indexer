# Story: Git History Indexing with Blob Deduplication and Branch Metadata

## Story Description

**As a** AI coding agent
**I want to** index a repository's git history with storage deduplication and branch awareness
**So that** I can search across historical code cost-effectively while preserving branch context

**Conversation Context:**
- User specified need for semantic search across git history to find removed code
- Emphasized storage efficiency via git blob deduplication (92%+ savings achieved)
- Required to handle 40K+ commit repositories efficiently
- Analysis of Evolution repo (1,135 branches, 89K commits) showed single-branch indexing covers 91.6% of commits
- Default to current branch only, opt-in for all branches to avoid 85% storage increase

## Acceptance Criteria

### Core Functionality
- [ ] Running `cidx index --index-commits` indexes current branch only (default behavior)
- [ ] Running `cidx index --index-commits --all-branches` indexes all branches
- [ ] Creates SQLite database at `.code-indexer/index/temporal/commits.db` with commit graph
- [ ] Creates `commit_branches` table tracking which branches each commit appears in
- [ ] Builds blob registry at `.code-indexer/index/temporal/blob_registry.json` mapping blob_hash → point_ids
- [ ] Reuses existing vectors for blobs already in HEAD (deduplication)
- [ ] Only embeds new blobs not present in current HEAD
- [ ] Stores temporal metadata including branch information in `.code-indexer/index/temporal/temporal_meta.json`

### User Experience
- [ ] Shows progress during indexing: "Indexing commits: 500/5000 (10%) [development branch]"
- [ ] Displays cost warning before indexing all branches: "⚠️ Indexing 715 branches will use ~514MB storage and cost ~$4.74"
- [ ] Requires user confirmation (y/N) for --all-branches in large repos (>50 branches)
- [ ] Shows final statistics: branches indexed, commits per branch, deduplication ratio

### Performance
- [ ] Achieves >92% storage savings through blob deduplication
- [ ] Handles large repositories (40K+ commits, 1000+ branches) without running out of memory
- [ ] Single-branch indexing is fast (similar to current indexing performance)

## Technical Implementation

### Entry Point (CLI)
```python
# In cli.py index command
@click.option("--index-commits", is_flag=True,
              help="Index git commit history for temporal search (current branch only)")
@click.option("--all-branches", is_flag=True,
              help="Index all branches (requires --index-commits, may increase storage significantly)")
@click.option("--max-commits", type=int,
              help="Maximum number of commits to index per branch (default: all)")
@click.option("--since-date",
              help="Index commits since date (YYYY-MM-DD)")
def index(..., index_commits, all_branches, max_commits, since_date):
    if index_commits:
        # Lazy import for performance
        from src.code_indexer.services.temporal_indexer import TemporalIndexer

        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # Cost estimation and warning for all-branches
        if all_branches:
            cost_estimate = temporal_indexer.estimate_all_branches_cost()
            console.print(Panel(
                f"⚠️  [yellow]Indexing all branches will:[/yellow]\n"
                f"  • Process {cost_estimate.additional_commits:,} additional commits\n"
                f"  • Create {cost_estimate.additional_blobs:,} new embeddings\n"
                f"  • Use {cost_estimate.storage_mb:.1f} MB additional storage\n"
                f"  • Cost ~${cost_estimate.api_cost:.2f} in VoyageAI API calls",
                title="Cost Warning",
                border_style="yellow"
            ))

            if cost_estimate.total_branches > 50:
                if not click.confirm("Continue with all-branches indexing?", default=False):
                    console.print("[yellow]Cancelled. Using single-branch mode.[/yellow]")
                    all_branches = False

        result = temporal_indexer.index_commits(
            all_branches=all_branches,
            max_commits=max_commits,
            since_date=since_date
        )
```

### Core Implementation
```python
class TemporalIndexer:
    def index_commits(self, all_branches: bool = False,
                      max_commits: Optional[int] = None,
                      since_date: Optional[str] = None) -> IndexingResult:
        """Index git history with blob deduplication and branch tracking"""

        # Step 1: Build blob registry from existing vectors
        blob_registry = self._build_blob_registry()

        # Step 2: Get commit history from git (with branch info)
        commits = self._get_commit_history(all_branches, max_commits, since_date)
        current_branch = self._get_current_branch()

        # Step 3: Process each commit to get trees
        all_blobs = set()
        commit_data = []
        for commit in commits:
            processed = self._process_commit(commit.hash)
            commit_data.append(processed)
            all_blobs.update(processed.blob_hashes)

            # Progress with branch info
            branch_info = f" [{current_branch}]" if not all_branches else ""
            self._progress_callback(len(commit_data), len(commits), branch_info)

        # Step 4: Store in SQLite (commits + branch metadata)
        self._store_commit_data(commit_data)
        self._store_branch_metadata(commits, all_branches, current_branch)

        # Step 5: Identify missing blobs (not in HEAD)
        missing_blobs = self._identify_missing_blobs(all_blobs, blob_registry)

        # Step 6: Index missing blobs
        if missing_blobs:
            self._index_missing_blobs(missing_blobs)

        # Step 7: Save metadata with branch info
        branch_stats = self._calculate_branch_statistics(commits, all_branches)
        self._save_temporal_metadata(
            last_commit=commits[-1].hash,
            total_commits=len(commits),
            total_blobs=len(all_blobs),
            new_blobs=len(missing_blobs),
            branch_stats=branch_stats,
            indexing_mode='all-branches' if all_branches else 'single-branch'
        )

        return IndexingResult(
            total_commits=len(commits),
            unique_blobs=len(all_blobs),
            new_blobs_indexed=len(missing_blobs),
            deduplication_ratio=1 - (len(missing_blobs) / len(all_blobs)),
            branches_indexed=branch_stats.branches,
            commits_per_branch=branch_stats.per_branch_counts
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

    # NEW: Branch metadata table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commit_branches (
            commit_hash TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            is_head INTEGER DEFAULT 0,
            indexed_at INTEGER NOT NULL,
            PRIMARY KEY (commit_hash, branch_name),
            FOREIGN KEY (commit_hash) REFERENCES commits(hash)
        )
    """)

    # Performance indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_blob_commit ON trees(blob_hash, commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_date_hash ON commits(date, hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_commit ON trees(commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_hash ON commit_branches(commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_name ON commit_branches(branch_name)")

    # Performance tuning
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=8192")

    conn.commit()
    return conn

def _store_branch_metadata(self, commits: List[CommitInfo],
                            all_branches: bool,
                            current_branch: str):
    """Store branch metadata for each commit"""
    import sqlite3
    import time

    conn = sqlite3.connect(self.db_path)
    timestamp = int(time.time())

    for commit in commits:
        if all_branches:
            # Get all branches containing this commit
            branches = self._get_branches_for_commit(commit.hash)
        else:
            # Single branch mode: only record current branch
            branches = [current_branch]

        # Check if this commit is HEAD of current branch
        is_head = (commit.hash == self._get_branch_head(current_branch))

        # Insert branch records
        for branch in branches:
            conn.execute("""
                INSERT OR IGNORE INTO commit_branches
                (commit_hash, branch_name, is_head, indexed_at)
                VALUES (?, ?, ?, ?)
            """, (commit.hash, branch, 1 if is_head and branch == current_branch else 0, timestamp))

    conn.commit()
    conn.close()
```

### Git Integration
```python
def _get_commit_history(self, all_branches: bool,
                       max_commits: Optional[int],
                       since_date: Optional[str]) -> List[CommitInfo]:
    """Get commit history from git with branch awareness"""

    # Build git log command
    cmd = ["git", "log", "--format=%H|%at|%an|%ae|%P", "--reverse"]

    # Add --all flag only if indexing all branches
    if all_branches:
        cmd.append("--all")

    if since_date:
        cmd.extend(["--since", since_date])

    if max_commits:
        cmd.extend(["-n", str(max_commits)])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

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

def _get_current_branch(self) -> str:
    """Get name of current branch"""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip() or "HEAD"

def _get_branches_for_commit(self, commit_hash: str) -> List[str]:
    """Get all branches containing a specific commit"""
    result = subprocess.run(
        ["git", "branch", "--contains", commit_hash, "--format=%(refname:short)"],
        capture_output=True,
        text=True
    )
    branches = [b.strip() for b in result.stdout.split("\n") if b.strip()]
    return branches if branches else ["unknown"]

def _get_branch_head(self, branch_name: str) -> str:
    """Get HEAD commit hash of a branch"""
    result = subprocess.run(
        ["git", "rev-parse", branch_name],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

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

def estimate_all_branches_cost(self) -> CostEstimate:
    """Estimate cost of indexing all branches"""
    import subprocess

    # Count current branch commits
    current_commits = int(subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip())

    # Count all branches commits
    all_commits = int(subprocess.run(
        ["git", "rev-list", "--all", "--count"],
        capture_output=True, text=True
    ).stdout.strip())

    # Count total branches
    total_branches = len(subprocess.run(
        ["git", "branch", "-a"],
        capture_output=True, text=True
    ).stdout.strip().split("\n"))

    additional_commits = all_commits - current_commits

    # Estimate additional blobs (assume 80% of objects are blobs, 10% are new)
    additional_blobs = int(additional_commits * 15 * 0.8 * 0.1)  # 15 files/commit avg

    # Calculate storage
    embedding_size = 1536 * 4  # float32
    storage_mb = (additional_blobs * embedding_size) / (1024 * 1024)

    # Calculate API cost (VoyageAI voyage-code-2)
    tokens_per_blob = 500
    api_cost = (additional_blobs * tokens_per_blob / 1000) * 0.00013

    return CostEstimate(
        total_branches=total_branches,
        additional_commits=additional_commits,
        additional_blobs=additional_blobs,
        storage_mb=storage_mb,
        api_cost=api_cost
    )
```

## Test Scenarios

### Manual Test Plan

#### Test 1: Single Branch Indexing (Default)
1. **Setup:**
   - Use code-indexer repository
   - Ensure clean state: `rm -rf .code-indexer/index/temporal/`
   - Run regular indexing first: `cidx index`

2. **Execute Single-Branch Temporal Indexing:**
   ```bash
   cidx index --index-commits
   # Should show: "Indexing commits: X/Y (%) [development]"
   ```

3. **Verify Database Created:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db ".tables"
   # Should show: commits trees commit_branches

   sqlite3 .code-indexer/index/temporal/commits.db "SELECT COUNT(*) FROM commits"
   # Should show commit count for current branch

   sqlite3 .code-indexer/index/temporal/commits.db "SELECT DISTINCT branch_name FROM commit_branches"
   # Should show only current branch (e.g., "development")
   ```

4. **Verify Blob Registry:**
   ```bash
   jq 'keys | length' .code-indexer/index/temporal/blob_registry.json
   # Should show number of unique blobs
   ```

5. **Check Deduplication and Branch Stats:**
   ```bash
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.deduplication_ratio'
   # Should be > 0.92 (92%)

   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexing_mode'
   # Should show: "single-branch"

   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexed_branches'
   # Should show: ["development"] or similar
   ```

#### Test 2: All Branches Indexing
1. **Execute All-Branches Indexing:**
   ```bash
   cidx index --index-commits --all-branches
   # Should show cost warning dialog
   # After confirmation, should show: "Indexing commits: X/Y (%)"
   ```

2. **Verify All Branches Tracked:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db \
     "SELECT COUNT(DISTINCT branch_name) FROM commit_branches"
   # Should show number matching total branches in repo

   sqlite3 .code-indexer/index/temporal/commits.db \
     "SELECT branch_name, COUNT(*) FROM commit_branches GROUP BY branch_name LIMIT 10"
   # Should show commit counts per branch
   ```

3. **Verify Metadata:**
   ```bash
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexing_mode'
   # Should show: "all-branches"
   ```

#### Test 3: Cost Warning
1. **Test Cost Estimation (on large repo):**
   ```bash
   # On Evolution repo or similar large repo
   cidx index --index-commits --all-branches
   # Should display warning with:
   #   - Number of additional commits
   #   - Storage estimate in MB
   #   - API cost estimate in dollars
   #   - Confirmation prompt (y/N)
   ```

2. **Test Cancellation:**
   - Answer 'N' to confirmation
   - Verify it falls back to single-branch mode

#### Test 4: Limits and Filters
1. **Test with Max Commits:**
   ```bash
   cidx index --index-commits --max-commits 100
   # Should index only 100 commits from current branch
   ```

2. **Test with Date Filter:**
   ```bash
   cidx index --index-commits --since-date 2024-01-01
   # Should index only commits since specified date
   ```

3. **Test Combined Flags:**
   ```bash
   cidx index --index-commits --all-branches --since-date 2024-01-01
   # Should index all branches but only recent commits
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

- **Single-branch mode (default):** Fast indexing, similar to current performance
- **All-branches mode:** Significant increase in processing time but excellent deduplication
- Batch SQLite inserts in transactions of 1000 rows (commits AND branch metadata)
- Use WAL mode for concurrent reads during indexing
- Build blob registry incrementally to avoid memory issues
- Show progress every 100 commits with branch context
- Allow cancellation with Ctrl+C (cleanup partial state)
- Cost estimation runs quickly (uses git commands only, no indexing)

## Dependencies

- Git CLI (version 2.0+)
- sqlite3 Python module (lazy loaded)
- Existing FilesystemVectorStore
- Existing HighThroughputProcessor for embedding

## Notes

**Conversation Requirements:**
- Default to current branch only (cost-effective, 91%+ commit coverage)
- Opt-in for all branches via explicit `--all-branches` flag
- 92%+ storage savings target via blob deduplication
- Must handle 40K+ commit repositories with 1000+ branches
- Progress reporting during long operations with branch context
- Cost transparency: warn users before expensive operations

**Branch Strategy Analysis:**
- Evolution repository analysis (1,135 branches, 89K commits) informed design decisions
- Single branch indexing: 81,733 commits = 91.6% coverage
- All branches indexing: 89,234 commits = 100% coverage but 85.5% storage increase
- Git blob deduplication: 92.4% of blobs shared between branches
- See `.analysis/temporal_indexing_branch_analysis.md` for complete analysis

**Design Decisions:**
1. **Default = Single Branch:** Cost-effective, excellent coverage for most use cases
2. **Explicit Opt-in:** Users must consciously choose `--all-branches` to avoid surprise costs
3. **Branch Metadata Always:** Even single-branch mode tracks which branch (future-proof)
4. **Cost Warnings:** Display storage and API cost estimates before multi-branch indexing
5. **Confirmation Required:** Large repos (>50 branches) require user confirmation for --all-branches