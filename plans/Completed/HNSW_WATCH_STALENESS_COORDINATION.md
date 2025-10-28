# HNSW Watch Staleness Coordination

## Problem Statement

**Current Issue:** The `cidx watch` command rebuilds the entire HNSW index after every batch of file changes, making it unusable for large codebases (5-10 seconds per rebuild for 10K+ files).

**Root Cause:** Watch process calls `end_indexing()` which unconditionally rebuilds HNSW, even for incremental file updates.

**Impact:**
- Watch performance: 100ms file processing + 5-10 seconds HNSW rebuild = unusable
- User experience: Watch becomes unresponsive during rebuilds
- Resource waste: Rebuilding entire index for single file changes

**Code Evidence:**
- `high_throughput_processor.py:905-910` - Always calls `end_indexing()` which rebuilds HNSW
- `filesystem_vector_store.py:211-217` - `end_indexing()` unconditionally calls `rebuild_from_vectors()`
- `hnsw_index_manager.py:249-309` - Scans ALL vector files to rebuild index

---

## Solution: File Lock Coordination with Staleness Tracking

**Strategy:** Decouple HNSW rebuild from watch, move rebuild responsibility to query time using file locking for cross-process coordination.

**Process Architecture Understanding:**
- `cidx watch` = Long-running daemon process (monitors file changes)
- `cidx query` = Short-lived CLI process (executes queries)
- **No shared memory** - must communicate via filesystem
- **OS-level event buffering** - inotify/FSEvents queue events even when process is blocked

**Key Insight:** File locking is necessary and sufficient for cross-process coordination. Watch blocking during query rebuild is acceptable because OS buffers file change events.

---

## Architecture

### **Metadata Flag: `is_stale`**

Add staleness flag to `collection_meta.json`:

```json
{
  "hnsw_index": {
    "version": 1,
    "vector_count": 1234,
    "is_stale": false,           // NEW: Staleness flag
    "last_rebuild": "2025-10-27T19:45:00Z",
    "last_marked_stale": "2025-10-27T19:46:00Z",  // NEW: When marked stale
    "vector_dim": 1536,
    "M": 16,
    "ef_construction": 200,
    "space": "cosine",
    "file_size_bytes": 52428800,
    "id_mapping": {...}
  }
}
```

### **File Locking Protocol**

**Lock File:** `.metadata.lock` (already exists in codebase)

**Lock Operations:**
1. **Mark Stale** (Watch): Acquire `LOCK_EX`, set `is_stale=true`, release
2. **Rebuild HNSW** (Query): Acquire `LOCK_EX`, rebuild, set `is_stale=false`, release
3. **Read Staleness** (Query): Read without lock (safe - atomic flag check)

**Blocking Behavior:**
- Watch tries to mark stale while query rebuilds → **Watch blocks** (5-10 seconds)
- OS queues file change events → **No events lost**
- Watch resumes after query releases lock → **Catches up**

---

## Workflow

### **Scenario 1: Watch Detects File Changes**

```
T=0s   Watch: File modified → OS queues event
T=1s   Watch: Process file → upsert vectors to filesystem
T=2s   Watch: Acquire LOCK_EX on .metadata.lock
       Watch: Set is_stale=true in collection_meta.json
       Watch: Release lock
       Watch: DONE (no HNSW rebuild!)
```

**Result:** Watch completes in ~2 seconds (was 10+ seconds)

### **Scenario 2: Query with Fresh HNSW**

```
T=0s   Query: cidx query "authentication"
       Query: Read collection_meta.json (no lock)
       Query: is_stale=false → HNSW is valid
       Query: Load hnsw_index.bin
       Query: Execute search
       Query: Return results (~50ms total)
```

**Result:** Query uses cached HNSW, fast response

### **Scenario 3: Query with Stale HNSW**

```
T=0s   Query: cidx query "authentication"
       Query: Read collection_meta.json (no lock)
       Query: is_stale=true → HNSW needs rebuild

T=1s   Query: Acquire LOCK_EX on .metadata.lock
       Query: Rebuild HNSW from all vectors (5-10 seconds)
       Query: Set is_stale=false
       Query: Release lock
       Query: Execute search with fresh HNSW
       Query: Return results (~10 seconds first query)
```

**Result:** First query after watch changes pays rebuild cost

### **Scenario 4: Watch Blocked by Query Rebuild**

```
T=0s   Query: Rebuilding HNSW (holds LOCK_EX)

T=2s   User: Edits 3 files
       OS: Queues 3 file change events (inotify buffer)
       Watch: Detects events, processes files, upserts vectors
       Watch: Tries to mark stale → fcntl.flock() BLOCKS

T=10s  Query: Rebuild complete, releases lock

T=10s  Watch: Lock acquired!
       Watch: Mark is_stale=true
       Watch: Release lock
       Watch: Continue monitoring (catches up on queued events)
```

**Result:** Watch temporarily blocked, but no events lost

---

## Implementation Details

### **1. Add Staleness Tracking to HNSWIndexManager**

**File:** `src/code_indexer/storage/hnsw_index_manager.py`

**New Method: `mark_stale()`**
```python
def mark_stale(self, collection_path: Path) -> None:
    """Mark HNSW index as stale (needs rebuild).

    Uses file locking for cross-process coordination between watch and query.

    Args:
        collection_path: Path to collection directory
    """
    import fcntl

    lock_file = collection_path / ".metadata.lock"
    lock_file.touch(exist_ok=True)

    with open(lock_file, "r") as lock_f:
        # Acquire exclusive lock (blocks if query is rebuilding)
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            meta_file = collection_path / "collection_meta.json"

            # Load metadata
            if meta_file.exists():
                with open(meta_file) as f:
                    metadata = json.load(f)
            else:
                return  # No metadata = nothing to mark stale

            # Mark HNSW index as stale
            if "hnsw_index" in metadata:
                metadata["hnsw_index"]["is_stale"] = True
                metadata["hnsw_index"]["last_marked_stale"] = (
                    datetime.now(timezone.utc).isoformat()
                )

            # Write updated metadata
            with open(meta_file, "w") as f:
                json.dump(metadata, f, indent=2)

        finally:
            # Release lock
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
```

**Update `_update_metadata()` to Initialize Flags**

Modify line 365 to add staleness flags:
```python
metadata["hnsw_index"] = {
    "version": 1,
    "vector_count": vector_count,
    "is_stale": False,  # NEW: Fresh after rebuild
    "last_rebuild": datetime.now(timezone.utc).isoformat(),
    "last_marked_stale": None,  # NEW: No stale marking yet
    "vector_dim": self.vector_dim,
    "M": M,
    "ef_construction": ef_construction,
    "space": self.space,
    "file_size_bytes": index_file_size,
    "id_mapping": id_mapping,
}
```

### **2. Add `is_stale()` Check to HNSWIndexManager**

**New Method:**
```python
def is_stale(self, collection_path: Path) -> bool:
    """Check if HNSW index needs rebuilding.

    Uses vector count comparison as primary detection method.
    Reads metadata without locking (atomic boolean check is safe).

    Args:
        collection_path: Path to collection directory

    Returns:
        True if HNSW needs rebuild, False if valid
    """
    meta_file = collection_path / "collection_meta.json"

    if not meta_file.exists():
        return True  # No metadata = needs build

    try:
        with open(meta_file) as f:
            metadata = json.load(f)

        hnsw_info = metadata.get("hnsw_index")
        if not hnsw_info:
            return True  # No HNSW metadata = needs build

        # Check explicit staleness flag
        if hnsw_info.get("is_stale", True):
            return True

        # Additional check: Compare vector counts
        # (catches staleness from process restarts)
        hnsw_count = hnsw_info.get("vector_count", 0)

        # Count actual vectors on disk
        vector_files = list(collection_path.rglob("vector_*.json"))
        actual_count = len(vector_files)

        # If counts don't match, index is stale
        if hnsw_count != actual_count:
            return True

        return False  # Index is fresh

    except Exception as e:
        # If we can't determine staleness, assume stale
        return True
```

### **3. Modify FilesystemVectorStore.end_indexing()**

**File:** `src/code_indexer/storage/filesystem_vector_store.py`

**Add `skip_hnsw_rebuild` Parameter:**

```python
def end_indexing(
    self,
    collection_name: str,
    progress_callback: Optional[Any] = None,
    skip_hnsw_rebuild: bool = False  # NEW PARAMETER
) -> Dict[str, Any]:
    """Finalize indexing by rebuilding HNSW and ID indexes.

    Args:
        collection_name: Name of collection
        progress_callback: Optional progress callback
        skip_hnsw_rebuild: If True, skip HNSW rebuild and mark stale instead
                          (used by watch mode for performance)

    Returns:
        Status dictionary with operation result
    """
    collection_path = self.base_path / collection_name

    if skip_hnsw_rebuild:
        # Watch mode: Just mark HNSW as stale (instant)
        self.logger.info(f"Skipping HNSW rebuild, marking stale for '{collection_name}'")

        from .hnsw_index_manager import HNSWIndexManager
        vector_size = self._get_vector_size(collection_name)
        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")
        hnsw_manager.mark_stale(collection_path)

    else:
        # Normal mode: Rebuild HNSW index (existing logic)
        self.logger.info(f"Finalizing indexes for collection '{collection_name}'...")

        vector_size = self._get_vector_size(collection_name)

        from .hnsw_index_manager import HNSWIndexManager
        hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")
        hnsw_manager.rebuild_from_vectors(
            collection_path=collection_path, progress_callback=progress_callback
        )

    # Save ID index (always needed)
    from .id_index_manager import IDIndexManager
    id_manager = IDIndexManager()

    with self._id_index_lock:
        if collection_name in self._id_index:
            id_manager.save_index(collection_path, self._id_index[collection_name])

    vector_count = len(self._id_index.get(collection_name, {}))

    self.logger.info(
        f"Indexing finalized for '{collection_name}': {vector_count} vectors indexed"
    )

    return {
        "status": "ok",
        "vectors_indexed": vector_count,
        "collection": collection_name,
        "hnsw_skipped": skip_hnsw_rebuild,  # NEW: Indicate if HNSW was skipped
    }
```

### **4. Add HNSW Staleness Check to search()**

**File:** `src/code_indexer/storage/filesystem_vector_store.py`

**Insert Before Line 1287 (before loading HNSW):**

```python
def search(
    self,
    collection_name: str,
    query: str,
    embedding_provider: Any,
    limit: int = 10,
    return_timing: bool = False,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
    """Search for similar vectors using parallel execution.

    Automatically rebuilds HNSW index if stale (marked by watch process).
    """
    timing: Dict[str, Any] = {}

    collection_path = self.base_path / collection_name

    if not collection_path.exists():
        raise ValueError(f"Collection '{collection_name}' does not exist")

    # === NEW: CHECK HNSW STALENESS ===
    from .hnsw_index_manager import HNSWIndexManager

    meta_file = collection_path / "collection_meta.json"
    with open(meta_file) as f:
        metadata = json.load(f)

    vector_size = metadata.get("vector_size", 1536)
    hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

    # Check if HNSW needs rebuild
    if hnsw_manager.is_stale(collection_path):
        self.logger.info(
            f"HNSW index is stale for '{collection_name}', rebuilding..."
        )

        # Report to user via progress callback
        if return_timing:
            timing["hnsw_rebuild_triggered"] = True

        # Rebuild HNSW with locking (blocks watch if it tries to mark stale)
        rebuild_start = time.time()
        hnsw_manager.rebuild_from_vectors(
            collection_path=collection_path,
            progress_callback=None  # No progress for query rebuilds
        )
        rebuild_ms = (time.time() - rebuild_start) * 1000

        if return_timing:
            timing["hnsw_rebuild_ms"] = rebuild_ms

        self.logger.info(
            f"HNSW rebuild complete for '{collection_name}' ({rebuild_ms:.0f}ms)"
        )

    # === CONTINUE WITH NORMAL SEARCH LOGIC ===
    # (existing parallel loading and search code)
    ...
```

### **5. Update SmartIndexer to Pass skip_hnsw_rebuild**

**File:** `src/code_indexer/services/smart_indexer.py`

**Modify `process_files_incrementally()` at lines 1900-1955:**

Add `watch_mode` parameter and pass `skip_hnsw_rebuild=True` when in watch mode.

**Updated method signature:**
```python
def process_files_incrementally(
    self,
    file_paths: List[str],
    force_reprocess: bool = False,
    quiet: bool = False,
    vector_thread_count: Optional[int] = None,
    watch_mode: bool = False,  # Already exists
) -> ProcessingStats:
```

**Update finally block at line 1022:**
```python
finally:
    # CRITICAL: Always finalize indexes, even on exception
    if progress_callback:
        progress_callback(0, 0, Path(""), info="Finalizing indexing session...")

    # NEW: Skip HNSW rebuild in watch mode
    end_result = self.qdrant_client.end_indexing(
        collection_name,
        progress_callback,
        skip_hnsw_rebuild=watch_mode  # NEW: Skip rebuild if watch mode
    )

    if watch_mode:
        logger.info(f"Watch mode: HNSW marked stale (skipped rebuild)")
    else:
        logger.info(f"Index finalization complete: {end_result.get('vectors_indexed', 0)} vectors indexed")
```

**Repeat for other `end_indexing()` calls:**
- Line 718 - `index_repository()`
- Line 1463 - `reconcile_index()`
- Line 1593 - `resume_indexing()`

All should pass `skip_hnsw_rebuild=False` (normal rebuild behavior).

### **6. Update HighThroughputProcessor**

**File:** `src/code_indexer/services/high_throughput_processor.py`

**Add `watch_mode` parameter to `process_branch_changes_high_throughput()`:**

```python
def process_branch_changes_high_throughput(
    self,
    old_branch: str,
    new_branch: str,
    changed_files: List[str],
    unchanged_files: List[str],
    collection_name: str,
    progress_callback: Optional[Callable] = None,
    vector_thread_count: Optional[int] = None,
    watch_mode: bool = False,  # NEW PARAMETER
) -> BranchIndexingResult:
```

**Update finally block at line 909:**
```python
finally:
    # CRITICAL: Always finalize indexes, even on exception
    if progress_callback:
        progress_callback(0, 0, Path(""), info="Finalizing indexing session...")

    end_result = self.qdrant_client.end_indexing(
        collection_name,
        progress_callback,
        skip_hnsw_rebuild=watch_mode  # NEW: Skip rebuild in watch mode
    )

    if watch_mode:
        logger.info("Watch mode: HNSW marked stale")
    else:
        logger.info(f"Index finalization complete: {end_result.get('vectors_indexed', 0)} vectors indexed")
```

### **7. Propagate watch_mode Through Call Chain**

**SmartIndexer.process_files_incrementally() → HighThroughputProcessor:**

Line 1901, update:
```python
branch_result = self.process_branch_changes_high_throughput(
    old_branch="",
    new_branch=current_branch,
    changed_files=relative_files,
    unchanged_files=[],
    collection_name=collection_name,
    progress_callback=None,
    vector_thread_count=vector_thread_count,
    watch_mode=watch_mode,  # NEW: Pass through
)
```

---

## Testing Requirements

### **Unit Tests**

**File:** `tests/unit/storage/test_hnsw_staleness.py` (NEW)

```python
def test_mark_stale_sets_flag():
    """Test marking HNSW as stale."""

def test_mark_stale_uses_file_locking():
    """Test file locking during mark_stale()."""

def test_is_stale_detects_flag():
    """Test staleness detection from flag."""

def test_is_stale_detects_count_mismatch():
    """Test staleness detection from vector count mismatch."""

def test_is_stale_returns_true_for_missing_index():
    """Test staleness when HNSW index doesn't exist."""
```

**File:** `tests/unit/storage/test_filesystem_vector_store_staleness.py` (NEW)

```python
def test_end_indexing_skip_hnsw_marks_stale():
    """Test skip_hnsw_rebuild marks stale instead of rebuilding."""

def test_end_indexing_normal_rebuilds_hnsw():
    """Test normal end_indexing rebuilds HNSW."""

def test_search_rebuilds_if_stale():
    """Test search auto-rebuilds stale HNSW."""

def test_search_uses_fresh_hnsw():
    """Test search uses fresh HNSW without rebuild."""
```

### **Integration Tests**

**File:** `tests/integration/test_watch_query_coordination.py` (NEW)

```python
def test_watch_marks_stale_query_rebuilds():
    """Test watch marks stale, query rebuilds on first search."""
    # 1. Index files normally
    # 2. Start watch
    # 3. Modify file
    # 4. Verify watch marked stale
    # 5. Run query
    # 6. Verify query rebuilt HNSW
    # 7. Verify query returned correct results

def test_watch_blocked_during_query_rebuild():
    """Test watch blocks when query is rebuilding HNSW."""
    # 1. Index files
    # 2. Mark stale manually
    # 3. Start query (rebuilds HNSW)
    # 4. During rebuild, start watch and modify file
    # 5. Verify watch blocks until query finishes
    # 6. Verify watch marks stale after unblocking

def test_multiple_watch_changes_single_rebuild():
    """Test multiple watch changes result in single query rebuild."""
    # 1. Index files
    # 2. Start watch
    # 3. Modify 10 files
    # 4. Verify watch processed all 10 (fast)
    # 5. Run query
    # 6. Verify single HNSW rebuild
    # 7. Run second query
    # 8. Verify no rebuild (uses fresh HNSW)
```

### **End-to-End Tests**

**File:** `tests/e2e/test_watch_performance.py` (NEW)

```python
def test_watch_performance_with_hnsw_skip():
    """Test watch performance without HNSW rebuilds."""
    # Measure: Watch processing time for single file change
    # Expected: < 2 seconds (was 10+ seconds)

def test_query_latency_with_fresh_hnsw():
    """Test query latency with fresh HNSW (no rebuild)."""
    # Measure: Query execution time with valid HNSW
    # Expected: < 100ms

def test_query_latency_with_stale_hnsw():
    """Test query latency with stale HNSW (triggers rebuild)."""
    # Measure: Query execution time with stale HNSW
    # Expected: 5-10 seconds (acceptable for first query)
```

---

## Acceptance Criteria

### **Performance Requirements**

1. ✅ **Watch File Processing Time**
   - **Current:** 10+ seconds per file change (with HNSW rebuild)
   - **Target:** < 2 seconds per file change (no HNSW rebuild)
   - **Measurement:** Time from file change detection to watch ready for next event

2. ✅ **Query Latency with Fresh HNSW**
   - **Target:** < 100ms
   - **Measurement:** `cidx query` execution time when HNSW is valid

3. ✅ **Query Latency with Stale HNSW**
   - **Target:** 5-10 seconds (acceptable for first query after watch changes)
   - **Measurement:** `cidx query` execution time when HNSW needs rebuild

### **Correctness Requirements**

4. ✅ **No Events Lost**
   - Watch must process ALL file change events, even when blocked by query
   - OS event buffering ensures no events lost during blocking

5. ✅ **HNSW Always Valid for Queries**
   - Query must always use valid HNSW (auto-rebuild if stale)
   - No stale query results

6. ✅ **File Locking Prevents Corruption**
   - Concurrent watch and query operations must not corrupt metadata
   - File locking ensures atomic updates

### **User Experience Requirements**

7. ✅ **Watch Remains Responsive**
   - Watch responds to file changes within 2 seconds
   - Acceptable: Temporary blocking during query rebuild (5-10 seconds max)

8. ✅ **Predictable Query Latency**
   - Users understand first query after watch changes may be slow
   - Subsequent queries fast (use cached HNSW)

### **Edge Cases**

9. ✅ **Process Restart Handling**
   - If watch crashes, query still detects stale HNSW via count mismatch
   - Staleness persists across process restarts (filesystem-based)

10. ✅ **Concurrent Watch Processes**
    - Multiple watch processes can mark stale (file locking prevents corruption)
    - Last writer wins (acceptable behavior)

---

## Migration Strategy

### **Backward Compatibility**

**Existing Metadata:** Old `collection_meta.json` files don't have `is_stale` flag.

**Handling:**
```python
# In is_stale() method
is_stale_flag = hnsw_info.get("is_stale", True)  # Default to True if missing
```

**First query after upgrade:** Will rebuild HNSW (acceptable one-time cost).

### **Deployment**

1. **Deploy Code:** New version with staleness tracking
2. **Existing Indexes:** Continue working (rebuild triggered on first query)
3. **New Indexes:** Use staleness tracking from creation
4. **Watch Upgrade:** Immediately benefits from skipped rebuilds

**No manual migration needed** - automatic on first use.

---

## Success Metrics

### **Before (Current State)**

- Watch processing time: **10+ seconds** per file change
- Watch usability: **Unusable** for large codebases
- HNSW rebuilds: After **every** watch batch

### **After (Target State)**

- Watch processing time: **< 2 seconds** per file change
- Watch usability: **Usable** for large codebases
- HNSW rebuilds: **Only on first query** after changes

### **Expected Improvement**

- **5-10x faster watch processing**
- **Watch becomes practical for real-world usage**
- **Query latency remains predictable**

---

## Technical Notes

### **Why File Locking is Necessary**

- Separate processes (`cidx watch` daemon, `cidx query` CLI)
- No shared memory communication
- Filesystem is only IPC mechanism
- File locking ensures atomic metadata updates

### **Why OS Event Buffering is Reliable**

- inotify (Linux): Kernel-level event queue (16KB-512KB buffer)
- FSEvents (macOS): Persistent event stream (survives process blocks)
- Watchdog library: User-space event queue on top of OS
- Events queued even when handler is busy/blocked

### **Why Count Mismatch is Fallback**

- In-memory staleness flag lost on process restart
- Count comparison provides persistent staleness detection
- Handles edge cases: crashes, forced kills, power loss

### **Alternative Approaches Considered**

1. ❌ **In-memory dirty flag:** Doesn't work across separate processes
2. ❌ **Incremental HNSW updates:** HNSW library doesn't support (requires full rebuild)
3. ❌ **Linear scan fallback:** Too slow for large codebases (defeats purpose of HNSW)
4. ✅ **Lazy rebuild with file locking:** Correct solution for this architecture

---

## References

**Code Locations:**
- HNSW Index Manager: `src/code_indexer/storage/hnsw_index_manager.py`
- Filesystem Vector Store: `src/code_indexer/storage/filesystem_vector_store.py`
- Smart Indexer: `src/code_indexer/services/smart_indexer.py`
- High-Throughput Processor: `src/code_indexer/services/high_throughput_processor.py`
- Watch Handler: `src/code_indexer/services/git_aware_watch_handler.py`

**Related Issues:**
- Watch performance degradation with large indexes
- HNSW rebuild overhead on incremental updates
- Cross-process coordination requirements

**Documentation:**
- [fcntl file locking](https://docs.python.org/3/library/fcntl.html)
- [inotify man page](https://man7.org/linux/man-pages/man7/inotify.7.html)
- [Watchdog library](https://pythonhosted.org/watchdog/)
- [HNSW algorithm](https://arxiv.org/abs/1603.09320)
