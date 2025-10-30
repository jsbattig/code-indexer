# Story: Incremental Indexing with Watch Mode Integration

## Story Description

**As a** developer using cidx in watch mode
**I want** the temporal index to update automatically as I make commits
**So that** my historical searches always include the latest changes without manual re-indexing

**Conversation Context:**
- User specified watch mode should read `enable_temporal` from config
- If enabled, watch maintains temporal index on new commits
- Incremental indexing critical for performance

## Acceptance Criteria

- [ ] Running `cidx index --index-commits` again only processes new commits since last index
- [ ] Tracks last indexed commit in `temporal_meta.json`
- [ ] Watch mode reads `enable_temporal` from config
- [ ] When enabled, watch mode automatically updates temporal index on new commits
- [ ] Progress shows: "Processing 5 new commits..." for incremental updates
- [ ] Handles branch switches and rebases correctly
- [ ] No duplicate processing of already-indexed commits
- [ ] Updates blob registry with new blobs from new commits

## Technical Implementation

### Incremental Indexing Logic
```python
class TemporalIndexer:
    def index_commits(self, max_commits: Optional[int] = None,
                      since_date: Optional[str] = None,
                      incremental: bool = True) -> IndexingResult:
        """Index commits with incremental support"""

        # Load metadata to check last indexed commit
        last_commit = None
        if incremental:
            last_commit = self._load_last_indexed_commit()

        # Get commit history
        if last_commit:
            # Only get new commits
            commits = self._get_commits_since(last_commit, max_commits)
            if not commits:
                return IndexingResult(
                    total_commits=0,
                    message="No new commits to index"
                )
            self.progress_callback(0, 0, Path(""),
                                 info=f"Processing {len(commits)} new commits...")
        else:
            # Full indexing
            commits = self._get_commit_history(max_commits, since_date)

        # Rest of indexing logic...
        # [Previous implementation continues]

    def _load_last_indexed_commit(self) -> Optional[str]:
        """Load last indexed commit from metadata"""
        meta_path = Path(".code-indexer/index/temporal/temporal_meta.json")
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
                return meta.get("last_indexed_commit")
        return None

    def _get_commits_since(self, last_commit: str,
                          max_commits: Optional[int]) -> List[CommitInfo]:
        """Get commits since last indexed commit"""
        # Check if last_commit still exists (handles rebases)
        try:
            subprocess.run(["git", "rev-parse", last_commit],
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # Last commit no longer exists (rebase/reset), need full reindex
            logger.warning(f"Last indexed commit {last_commit} not found. "
                         "Full reindex required.")
            return self._get_commit_history(max_commits, None)

        # Get new commits
        cmd = ["git", "rev-list", "--reverse", f"{last_commit}..HEAD"]
        if max_commits:
            cmd.extend(["--max-count", str(max_commits)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        commit_hashes = result.stdout.strip().split("\n")

        # Get full commit info for each
        commits = []
        for hash in commit_hashes:
            if hash:
                commit_info = self._get_commit_info(hash)
                commits.append(commit_info)

        return commits
```

### Watch Mode Integration
```python
# In services/fts_watch_handler.py (extend for temporal)
class FTSWatchHandler(FileSystemEventHandler):
    def __init__(self, config_manager: ConfigManager, ...):
        super().__init__()
        self.config_manager = config_manager
        self.enable_temporal = config_manager.get_config().indexing.enable_temporal

    def _check_for_new_commits(self):
        """Check if new commits exist and index them"""
        if not self.enable_temporal:
            return

        # Lazy import
        from .temporal_indexer import TemporalIndexer

        temporal = TemporalIndexer(self.config_manager, self.vector_store)
        last_commit = temporal._load_last_indexed_commit()

        # Check current HEAD
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()

        if last_commit != current_head:
            # New commits detected
            logger.info("New commits detected, updating temporal index...")
            result = temporal.index_commits(incremental=True)
            if result.total_commits > 0:
                logger.info(f"Indexed {result.total_commits} new commits")
```

### Configuration Schema
```python
# In config.py
class IndexingConfig(BaseModel):
    """Indexing configuration"""
    enable_temporal: bool = Field(
        default=False,
        description="Enable temporal indexing in watch mode"
    )
    temporal_check_interval: int = Field(
        default=30,
        description="Seconds between temporal index checks in watch mode"
    )
```

### Watch Mode Periodic Check
```python
# In smart_indexer.py watch mode
def start_watch_mode(self):
    """Start watching for changes"""
    # ... existing code ...

    if self.config.indexing.enable_temporal:
        # Start periodic temporal check
        self._start_temporal_monitor()

def _start_temporal_monitor(self):
    """Monitor for new commits periodically"""
    import threading

    def check_commits():
        while self.watching:
            try:
                # Lazy import
                from .temporal_indexer import TemporalIndexer
                temporal = TemporalIndexer(self.config_manager, self.vector_store)

                # Check for new commits
                result = temporal.index_commits(incremental=True)
                if result.total_commits > 0:
                    logger.info(f"Temporal index updated: "
                              f"{result.total_commits} new commits")

            except Exception as e:
                logger.error(f"Temporal monitor error: {e}")

            # Wait for next check
            time.sleep(self.config.indexing.temporal_check_interval)

    monitor_thread = threading.Thread(target=check_commits, daemon=True)
    monitor_thread.start()
```

### Metadata Updates
```python
def _save_temporal_metadata(self, last_commit: str, total_commits: int,
                           unique_blobs: int, new_blobs: int):
    """Save temporal indexing metadata"""
    meta_path = Path(".code-indexer/index/temporal/temporal_meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing or create new
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
    else:
        meta = {}

    # Update metadata
    meta.update({
        "last_indexed_commit": last_commit,
        "index_version": "1.0",
        "total_commits": total_commits,
        "total_unique_blobs": unique_blobs,
        "last_updated": datetime.now().isoformat(),
        "incremental_updates": meta.get("incremental_updates", 0) + 1
    })

    # Calculate deduplication ratio
    if unique_blobs > 0:
        meta["deduplication_ratio"] = 1 - (new_blobs / unique_blobs)

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
```

## Test Scenarios

### Manual Test Plan

1. **Initial Index:**
   ```bash
   cidx index --index-commits
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.last_indexed_commit'
   ```

2. **Make New Commits:**
   ```bash
   echo "test" > test.txt
   git add test.txt
   git commit -m "Test commit 1"

   echo "test2" > test2.txt
   git add test2.txt
   git commit -m "Test commit 2"
   ```

3. **Incremental Index:**
   ```bash
   cidx index --index-commits
   # Should show: "Processing 2 new commits..."
   ```

4. **Verify Only New Commits Processed:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db \
     "SELECT hash, message FROM commits ORDER BY date DESC LIMIT 2"
   # Should show the two new test commits
   ```

5. **Test Watch Mode:**
   ```bash
   # Enable temporal in config
   echo '{"indexing": {"enable_temporal": true}}' > .code-indexer/config.json

   # Start watch mode
   cidx start --watch

   # In another terminal, make commits
   echo "watch test" > watch.txt
   git add watch.txt
   git commit -m "Watch mode test"

   # Check logs for: "Temporal index updated: 1 new commits"
   ```

6. **Test Branch Switch:**
   ```bash
   git checkout -b test-branch
   echo "branch" > branch.txt
   git add branch.txt
   git commit -m "Branch commit"

   cidx index --index-commits
   # Should process the branch commit

   git checkout main
   git merge test-branch
   cidx index --index-commits
   # Should handle the merge correctly
   ```

### Automated Tests
```python
def test_incremental_temporal_indexing():
    """Test incremental indexing only processes new commits"""
    with temp_git_repo() as repo_path:
        # Create initial commits
        create_test_commits(repo_path, count=5)

        # Initial index
        temporal = TemporalIndexer(config_manager, vector_store)
        result1 = temporal.index_commits()
        assert result1.total_commits == 5

        # Create more commits
        create_test_commits(repo_path, count=3)

        # Incremental index
        result2 = temporal.index_commits(incremental=True)
        assert result2.total_commits == 3  # Only new commits

        # Verify database
        conn = sqlite3.connect(".code-indexer/index/temporal/commits.db")
        total = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        assert total == 8  # All commits present

def test_watch_mode_temporal_integration():
    """Test watch mode updates temporal index"""
    with temp_git_repo() as repo_path:
        # Enable temporal in config
        config = config_manager.get_config()
        config.indexing.enable_temporal = True
        config_manager.save_config(config)

        # Start watch mode
        watcher = SmartIndexer(config_manager)
        watcher.start_watch_mode()

        # Make commits
        time.sleep(1)  # Let watch mode initialize
        create_test_commits(repo_path, count=2)
        time.sleep(config.indexing.temporal_check_interval + 1)

        # Check temporal index updated
        meta_path = Path(".code-indexer/index/temporal/temporal_meta.json")
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
            assert meta["incremental_updates"] > 0
```

## Error Scenarios

1. **Last commit not found (rebase/reset):**
   - Warning: "Last indexed commit not found. Full reindex required."
   - Action: Perform full reindex automatically

2. **Concurrent indexing:**
   - Use file lock on temporal_meta.json
   - Wait for other process or skip update

3. **Watch mode git operations fail:**
   - Log error but don't crash watch mode
   - Retry on next interval

4. **Config change during watch:**
   - Detect config reload
   - Enable/disable temporal monitoring accordingly

## Performance Considerations

- Only check for new commits periodically (default: 30s)
- Use git rev-list for efficient new commit detection
- Batch process new commits (up to 100 at a time)
- Skip check if no file changes detected
- Cache blob registry updates in memory

## Dependencies

- Git CLI (for rev-list, rev-parse)
- Existing watch mode infrastructure
- Configuration system
- Temporal indexer from Story 1

## Notes

**Conversation Requirements:**
- Watch mode reads enable_temporal from config
- Maintains temporal index automatically when enabled
- Shows clear progress for incremental updates
- No manual intervention required