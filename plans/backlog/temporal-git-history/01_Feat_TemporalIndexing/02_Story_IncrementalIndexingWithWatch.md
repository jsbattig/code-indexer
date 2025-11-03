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
        """Get commits since last indexed commit with rebase/force-push handling"""

        # === REBASE/FORCE-PUSH HANDLING (Issue #10) ===
        # Check if last_commit still exists
        try:
            subprocess.run(["git", "rev-parse", last_commit],
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # Last commit no longer exists (rebase/force-push scenario)
            # OPTIMIZATION: Use git reflog to find common ancestor instead of full reindex
            logger.warning(f"Last indexed commit {last_commit} not found (rebase/force-push)")

            # Try to find common ancestor using reflog
            common_ancestor = self._find_common_ancestor_via_reflog(last_commit)

            if common_ancestor:
                logger.info(f"Found common ancestor {common_ancestor[:8]}, "
                          f"reindexing from there instead of full reindex")
                last_commit = common_ancestor
                # Continue with incremental from common ancestor
            else:
                # No common ancestor found, must do full reindex
                logger.warning("No common ancestor found. Full reindex required.")
                return self._get_commit_history(max_commits, None)

        # Get new commits
        cmd = ["git", "rev-list", "--reverse", f"{last_commit}..HEAD"]
        if max_commits:
            cmd.extend(["--max-count", str(max_commits)])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        commit_hashes = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Get full commit info for each
        commits = []
        for hash in commit_hashes:
            if hash:
                commit_info = self._get_commit_info(hash)
                commits.append(commit_info)

        return commits

    def _find_common_ancestor_via_reflog(self, missing_commit: str) -> Optional[str]:
        """
        Find common ancestor when last indexed commit was rebased/force-pushed away.

        Strategy:
        1. Look through reflog for commits that still exist
        2. Find merge-base between reflog commit and current HEAD
        3. Return earliest common ancestor found

        This avoids expensive full reindex after rebase/force-push.
        """
        try:
            # Get reflog entries (last 100 commits should cover most rebases)
            reflog_result = subprocess.run(
                ["git", "reflog", "show", "--format=%H", "-n", "100"],
                capture_output=True, text=True, check=True
            )

            reflog_commits = reflog_result.stdout.strip().split("\n")

            for reflog_commit in reflog_commits:
                if not reflog_commit:
                    continue

                try:
                    # Check if this commit still exists
                    subprocess.run(["git", "rev-parse", reflog_commit],
                                 check=True, capture_output=True)

                    # Find merge-base between this commit and current HEAD
                    merge_base_result = subprocess.run(
                        ["git", "merge-base", reflog_commit, "HEAD"],
                        capture_output=True, text=True, check=True
                    )

                    merge_base = merge_base_result.stdout.strip()

                    if merge_base:
                        # Verify this commit exists in our indexed history
                        # (check temporal_meta.json for indexed commits)
                        if self._is_commit_indexed(merge_base):
                            return merge_base

                except subprocess.CalledProcessError:
                    # This reflog commit no longer exists or merge-base failed
                    continue

            return None

        except Exception as e:
            logger.error(f"Error finding common ancestor via reflog: {e}")
            return None

    def _is_commit_indexed(self, commit_hash: str) -> bool:
        """Check if a commit has been indexed in temporal database"""
        # Query commits.db to see if this commit exists
        commits_db = Path(".code-indexer/index/temporal/commits.db")
        if not commits_db.exists():
            return False

        import sqlite3
        conn = sqlite3.connect(commits_db)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM commits WHERE commit_hash = ?",
                (commit_hash,)
            )
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            conn.close()
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

### Watch Mode Integration Strategy (Issue #9)

**Efficiency Design:**

Watch mode temporal integration is designed for minimal overhead:

**Detection Strategy:**
1. **Git-Native Detection:** Use inotify (Linux) or FSEvents (macOS) on `.git/` directory
2. **Debouncing:** Wait 5 seconds after last `.git/HEAD` change before checking
3. **Batch Processing:** If multiple commits detected, process them in single batch
4. **Smart Checking:** Only query git when `.git/HEAD` or `.git/refs/` changes

**Performance Characteristics:**

| Scenario | Detection Time | Processing Time | Total Overhead |
|----------|---------------|-----------------|----------------|
| No new commits | <1ms | 0ms | <1ms (negligible) |
| Single new commit | <1ms | 1-2s | ~2s per commit |
| Batch (10 commits) | <1ms | 10-15s | ~1.5s per commit |
| Force-push detected | <1ms | 2-5s | Reflog recovery |

**Efficiency Guarantees:**
- **Zero overhead when idle:** No polling when no git changes
- **Debounced rapid commits:** Batch process commits from rebase/cherry-pick
- **Incremental only:** Never re-process already-indexed commits
- **Minimal git calls:** One `git log` check per commit batch

**Configuration for Efficiency:**
```python
watch_config = {
    "debounce_delay": 5,          # Seconds to wait after last change
    "batch_threshold": 10,         # Max commits to batch
    "enable_temporal": True,       # Enable temporal in watch mode
    "temporal_check_interval": 30  # Fallback polling (if inotify unavailable)
}
```

**Implementation Note:** Use existing watch mode infrastructure (file system events) rather than polling. Temporal check triggers ONLY when git directory changes detected.

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

def test_rebase_force_push_handling():
    """Test rebase/force-push scenario with common ancestor recovery (Issue #10)"""
    with temp_git_repo() as repo_path:
        # Create initial commits and index
        create_test_commits(repo_path, count=5)
        temporal = TemporalIndexer(config_manager, vector_store)
        result1 = temporal.index_commits()
        assert result1.total_commits == 5

        # Get last indexed commit
        meta_path = Path(".code-indexer/index/temporal/temporal_meta.json")
        with open(meta_path) as f:
            last_indexed = json.load(f)["last_indexed_commit"]

        # Simulate rebase: Reset to commit 3, create new commits
        subprocess.run(["git", "reset", "--hard", "HEAD~2"], check=True)
        create_test_commits(repo_path, count=3, prefix="rebased")

        # Now last_indexed commit no longer exists
        try:
            subprocess.run(["git", "rev-parse", last_indexed],
                         check=True, capture_output=True)
            assert False, "Last commit should not exist after rebase"
        except subprocess.CalledProcessError:
            pass  # Expected

        # Incremental index should find common ancestor via reflog
        result2 = temporal.index_commits(incremental=True)

        # Should have found common ancestor (commit 3)
        # and indexed commits 4, 5 (rebased versions) = 2 commits
        # Not full 8 commits (would be full reindex)
        assert result2.total_commits < 8, "Should use common ancestor, not full reindex"
        assert result2.total_commits >= 2, "Should index rebased commits"

        # Verify database integrity
        conn = sqlite3.connect(".code-indexer/index/temporal/commits.db")
        total = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        # Should have: 3 original + 3 rebased = 6 commits
        # (commits 4-5 original are gone, replaced by rebased versions)
        assert total >= 6, f"Expected at least 6 commits, got {total}"

def test_force_push_full_reindex_fallback():
    """Test full reindex when common ancestor not found (Issue #10)"""
    with temp_git_repo() as repo_path:
        # Create and index commits
        create_test_commits(repo_path, count=5)
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        # Simulate complete history rewrite (no common ancestor)
        subprocess.run(["git", "checkout", "--orphan", "new-main"], check=True)
        subprocess.run(["git", "rm", "-rf", "."], check=True)
        create_test_commits(repo_path, count=3, prefix="new")

        # Incremental should fall back to full reindex
        result = temporal.index_commits(incremental=True)

        # Should reindex all 3 new commits (full reindex)
        assert result.total_commits == 3
```

## Error Scenarios

1. **Last commit not found with common ancestor (rebase/force-push - Issue #10):**
   - Warning: "Last indexed commit {hash} not found (rebase/force-push)"
   - Action: Search reflog for common ancestor
   - Info: "Found common ancestor {hash}, reindexing from there"
   - Result: Partial reindex from common ancestor (efficient)

2. **Last commit not found without common ancestor:**
   - Warning: "Last indexed commit not found (rebase/reset)"
   - Warning: "No common ancestor found. Full reindex required."
   - Action: Perform full reindex automatically
   - Result: Complete reindex (fallback)

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