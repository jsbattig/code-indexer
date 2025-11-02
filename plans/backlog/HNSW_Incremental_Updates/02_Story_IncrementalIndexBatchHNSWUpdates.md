# User Story: Incremental Index Batch HNSW Updates

**Epic**: HNSW Incremental Updates
**Story ID**: HNSW-002
**Priority**: HIGH
**Estimate**: 8 story points
**Depends On**: HNSW-001 (shares common HNSW incremental update methods)

---

## Story Description

**As a** developer using `cidx index` for incremental re-indexing
**I want** HNSW index to be updated incrementally with only changed files at end of indexing cycle
**So that** indexing completes faster without rebuilding entire HNSW index from all vectors

---

## Current Behavior (Problem)

**Regular `cidx index` Flow Today**:
```
cidx index (10 files changed out of 10,000 total)
  ↓
SmartIndexer: Process 10 changed files → Generate vectors → Write to disk
  ↓
SmartIndexer.end_indexing()
  ↓
FilesystemVectorStore.end_indexing(skip_hnsw_rebuild=False)  # DEFAULT
  ↓
HNSWIndexManager.rebuild_from_vectors()
  ↓
Scan ALL 10,000 vector JSON files → Load into memory → Build HNSW from scratch (5-10s)
```

**🔴 CRITICAL PROBLEM DISCOVERED**:
- `cidx index` **ALWAYS does full HNSW rebuild**, even for incremental operations
- `skip_hnsw_rebuild` parameter **never passed** by `SmartIndexer` (search confirms: 0 results)
- ALL indexing modes affected: incremental, reconcile, resume, git-aware

**Evidence**:
```bash
$ grep "skip_hnsw_rebuild" src/code_indexer/services/smart_indexer.py
# (no results - parameter not used)
```

**Performance Impact**:
- Index 10 changed files → **rebuilds HNSW from 10,000 vectors** (5-10 seconds wasted)
- Index 100 changed files → **rebuilds HNSW from 10,000 vectors** (same 5-10 seconds)
- No benefit from incremental file detection (waste of smart indexing logic)

**Root Cause**:
- `skip_hnsw_rebuild` was added for watch mode only
- Never integrated into regular `cidx index` command
- `SmartIndexer._do_full_index()`, `_do_reconcile_with_database()`, `smart_index()` all call `end_indexing()` without parameter

---

## Desired Behavior (Solution)

**Regular `cidx index` Flow After This Story**:
```
cidx index (10 files changed out of 10,000 total)
  ↓
SmartIndexer: Process 10 changed files → Track changes (added/updated/deleted)
  ↓
SmartIndexer.end_indexing()
  ↓
FilesystemVectorStore.end_indexing() → Detect incremental session
  ↓
**Incremental HNSW Update** (batch):
  - Load existing HNSW index (< 1s)
  - Add 10 new/updated vectors via add_items() (~100ms)
  - Mark deleted vectors via mark_deleted() (~10ms)
  - Save updated index (< 1s)
  ↓
Total: ~2 seconds (vs 5-10 seconds full rebuild)
```

**Benefits**:
1. ✅ **Faster indexing** - 2-3x speedup for incremental operations
2. ✅ **Scales with changes** - Time proportional to changed files, not total files
3. ✅ **Better resource usage** - Less CPU, less memory
4. ✅ **Preserves git-aware deduplication benefits** - Incremental updates don't negate smart indexing

---

## Acceptance Criteria

### AC1: Track Changed Vectors During Indexing Session
**GIVEN** indexing session starts via `begin_indexing()`
**WHEN** vectors are upserted or deleted
**THEN** changes are tracked in session state: `{'added': set(), 'updated': set(), 'deleted': set()}`
**AND** tracking persists throughout entire indexing session
**AND** tracking is cleared after `end_indexing()` completes

**Implementation Requirements**:
- Add `_indexing_session_changes: Dict[str, Dict[str, Set[str]]]` to `FilesystemVectorStore`
- Initialize in `begin_indexing()`: `self._indexing_session_changes[collection_name] = {'added': set(), 'updated': set(), 'deleted': set()}`
- Track in `upsert_points()`: check if point_id exists → mark as 'updated' or 'added'
- Track in `delete_points()`: add point_ids to 'deleted' set
- Clear in `end_indexing()`: `del self._indexing_session_changes[collection_name]`

### AC2: Incremental HNSW Update at End of Indexing Cycle
**GIVEN** incremental indexing session with N changed files (N < total_files / 2)
**WHEN** `end_indexing()` is called
**THEN** HNSW index is updated **incrementally** (not full rebuild)
**AND** only changed vectors are processed
**AND** update completes in O(N) time, not O(total_files) time

**Implementation Requirements**:
- Detect incremental session: check if `_indexing_session_changes` exists
- Load existing HNSW index from disk
- Batch load changed vectors from disk (read vector JSON files)
- Call `hnsw_index.add_items(vectors, labels)` for added/updated vectors
- Call `hnsw_index.mark_deleted(labels)` for deleted vectors
- Save updated HNSW index
- Update metadata (vector count, last_update, etc.)

### AC3: Refactor SmartIndexer to Support Incremental HNSW
**GIVEN** `SmartIndexer` methods that call `end_indexing()`
**WHEN** incremental indexing operation completes
**THEN** `end_indexing()` is called **without forcing full rebuild**
**AND** incremental HNSW update is triggered automatically

**🔴 CRITICAL REFACTORING REQUIRED**:
- **Affected methods** (4 locations in `smart_indexer.py`):
  - Line 790: `_do_full_index()` → Pass `skip_hnsw_rebuild=False` (force full for initial index)
  - Line 1105: `_do_reconcile_with_database()` → Remove parameter (let `end_indexing()` auto-detect)
  - Line 1547: `smart_index()` → Remove parameter (let `end_indexing()` auto-detect)
  - Line 1683: `process_files_incrementally()` → Already passes `watch_mode=True` (no change needed)

**New Behavior**:
```python
# SmartIndexer methods should NOT pass skip_hnsw_rebuild
# Let FilesystemVectorStore.end_indexing() auto-detect:
#  - If _indexing_session_changes exists → incremental update
#  - If _indexing_session_changes empty/missing → full rebuild (first index)
```

### AC4: Auto-Detection of Incremental vs Full Rebuild
**GIVEN** `end_indexing()` is called
**WHEN** indexing session has tracked changes
**THEN** incremental HNSW update is used automatically
**WHEN** indexing session has no tracked changes (first index, or full index forced)
**THEN** full HNSW rebuild is used

**Implementation Requirements**:
```python
def end_indexing(self, collection_name, progress_callback=None):
    """Auto-detect incremental vs full rebuild."""

    # Check if we have session change tracking
    if hasattr(self, '_indexing_session_changes') and collection_name in self._indexing_session_changes:
        changes = self._indexing_session_changes[collection_name]
        if changes['added'] or changes['updated'] or changes['deleted']:
            # Incremental update path
            self._apply_incremental_hnsw_batch_update(...)
            return

    # Full rebuild path (first index, or watch mode stale)
    hnsw_manager.rebuild_from_vectors(...)
```

### AC5: Performance Improvement Validation
**GIVEN** repository with 10,000 indexed files
**WHEN** 10 files are modified and `cidx index` is run
**THEN** indexing completes in < 5 seconds (incremental HNSW)
**AND** indexing would take > 10 seconds with full rebuild
**AND** speedup is 2-3x

**Measurement Requirements**:
- Benchmark: Time `cidx index` before/after this story
- Report: Log "HNSW incremental update: +X ~Y -Z files in Nms"
- Validate: Query results include changed files

### AC6: Deletion Handling and Soft Delete
**GIVEN** files are deleted from repository
**WHEN** `cidx index` runs with deletion detection
**THEN** deleted files' vectors are removed from vector store
**AND** corresponding HNSW labels are **soft-deleted** via `mark_deleted()`
**AND** deleted vectors are excluded from search results

**Implementation Requirements**:
- Track deletions in `delete_points()`: `self._indexing_session_changes[collection_name]['deleted'].add(point_id)`
- In `_apply_incremental_hnsw_batch_update()`:
  ```python
  for point_id in changes['deleted']:
      if point_id in id_mapping:
          label = id_mapping[point_id]
          hnsw_index.mark_deleted(label)
  ```
- hnswlib automatically excludes `mark_deleted` vectors from `knn_query()`

---

## Technical Implementation Details

### Modified Files

#### 1. `src/code_indexer/storage/filesystem_vector_store.py`

**New Instance Variable**:
```python
class FilesystemVectorStore:
    def __init__(self, ...):
        # ... existing code ...

        # NEW: Track changed vectors during indexing session
        self._indexing_session_changes: Dict[str, Dict[str, Set[str]]] = {}
        # Structure: {collection_name: {'added': set(), 'updated': set(), 'deleted': set()}}
```

**Modified Method: `begin_indexing()`**:
```python
def begin_indexing(self, collection_name: str) -> None:
    """Prepare for batch indexing operations."""
    # ... existing code ...

    # NEW: Initialize session change tracking
    self._indexing_session_changes[collection_name] = {
        'added': set(),
        'updated': set(),
        'deleted': set(),
    }
```

**Modified Method: `upsert_points()`**:
```python
def upsert_points(
    self,
    collection_name: str,
    points: List[Dict],
    watch_mode: bool = False,  # Added in Story HNSW-001
) -> Dict:
    """Upsert vectors and track changes for incremental HNSW."""

    for point in points:
        point_id = point['id']

        # NEW: Track if vector is new or updated
        if hasattr(self, '_indexing_session_changes') and collection_name in self._indexing_session_changes:
            # Check if vector already exists in ID index
            with self._id_index_lock:
                if collection_name in self._id_index and point_id in self._id_index[collection_name]:
                    self._indexing_session_changes[collection_name]['updated'].add(point_id)
                else:
                    self._indexing_session_changes[collection_name]['added'].add(point_id)

        # ... existing upsert code ...

    # Watch mode real-time update (Story HNSW-001)
    if watch_mode and vectors_to_add:
        self._update_hnsw_incrementally_realtime(...)

    return {"status": "ok", "count": len(points)}
```

**Modified Method: `delete_points()`**:
```python
def delete_points(
    self,
    collection_name: str,
    point_ids: List[str]
) -> Dict:
    """Delete vectors and track for incremental HNSW."""

    # ... existing delete code ...

    # NEW: Track deletions for incremental HNSW
    if hasattr(self, '_indexing_session_changes') and collection_name in self._indexing_session_changes:
        for point_id in point_ids:
            self._indexing_session_changes[collection_name]['deleted'].add(point_id)

    return {"status": "ok", "deleted": deleted}
```

**Modified Method: `end_indexing()`**:
```python
def end_indexing(
    self,
    collection_name: str,
    progress_callback: Optional[Any] = None,
) -> Dict:
    """Finalize indexing with auto-detected incremental or full HNSW rebuild."""

    collection_path = self.base_path / collection_name
    vector_size = self._get_vector_size(collection_name)

    from .hnsw_index_manager import HNSWIndexManager
    hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

    # Auto-detect: incremental vs full rebuild
    if hasattr(self, '_indexing_session_changes') and collection_name in self._indexing_session_changes:
        changes = self._indexing_session_changes[collection_name]

        # Check if we have any changes to apply
        if changes['added'] or changes['updated'] or changes['deleted']:
            # INCREMENTAL UPDATE PATH
            if progress_callback:
                progress_callback(0, 0, Path(""), info="🔧 Applying incremental HNSW updates...")

            self._apply_incremental_hnsw_batch_update(
                collection_name=collection_name,
                changes=changes,
                collection_path=collection_path,
                hnsw_manager=hnsw_manager,
                progress_callback=progress_callback,
            )

            # Clear session changes
            del self._indexing_session_changes[collection_name]

            # Save ID index
            self._save_id_index(collection_name)

            return {
                "status": "ok",
                "vectors_indexed": len(self._id_index.get(collection_name, {})),
                "collection": collection_name,
                "hnsw_mode": "incremental",  # NEW
            }

    # FULL REBUILD PATH (first index, or watch mode stale)
    if progress_callback:
        progress_callback(0, 0, Path(""), info="🔨 Building HNSW index from all vectors...")

    hnsw_manager.rebuild_from_vectors(
        collection_path=collection_path,
        progress_callback=progress_callback
    )

    # Save ID index
    self._save_id_index(collection_name)

    return {
        "status": "ok",
        "vectors_indexed": len(self._id_index.get(collection_name, {})),
        "collection": collection_name,
        "hnsw_mode": "full_rebuild",  # NEW
    }
```

**New Method**:
```python
def _apply_incremental_hnsw_batch_update(
    self,
    collection_name: str,
    changes: Dict[str, Set[str]],
    collection_path: Path,
    hnsw_manager: HNSWIndexManager,
    progress_callback: Optional[Any],
) -> None:
    """Apply incremental HNSW updates in batch at end of indexing.

    Args:
        collection_name: Name of collection
        changes: Dict with 'added', 'updated', 'deleted' sets
        collection_path: Path to collection directory
        hnsw_manager: HNSW index manager instance
        progress_callback: Optional progress callback

    Implementation:
        1. Load existing HNSW index
        2. Load ID mapping
        3. Batch load changed vectors from disk
        4. Add/update vectors via add_items()
        5. Soft delete removed vectors via mark_deleted()
        6. Save updated index
        7. Update metadata
    """

    # Load existing HNSW index
    try:
        index = hnsw_manager.load_index(collection_path)
        id_mapping = hnsw_manager._load_id_mapping(collection_path)
    except Exception as e:
        # Index doesn't exist or corrupted → fallback to full rebuild
        self.logger.warning(f"Could not load HNSW index for incremental update: {e}")
        self.logger.info("Falling back to full HNSW rebuild")
        hnsw_manager.rebuild_from_vectors(collection_path, progress_callback)
        return

    # Process additions and updates
    add_update_ids = changes['added'] | changes['updated']
    if add_update_ids:
        if progress_callback:
            progress_callback(0, 0, Path(""), info=f"🔧 Adding/updating {len(add_update_ids)} vectors to HNSW...")

        vectors_to_add = []
        point_ids_to_add = []

        # Load vectors from disk
        with self._id_index_lock:
            id_index = self._id_index.get(collection_name, {})

        for point_id in add_update_ids:
            if point_id in id_index:
                vector_file = id_index[point_id]
                try:
                    with open(vector_file) as f:
                        vector_data = json.load(f)
                    vector = np.array(vector_data['vector'], dtype=np.float32)

                    vectors_to_add.append(vector)
                    point_ids_to_add.append(point_id)
                except Exception as e:
                    self.logger.warning(f"Could not load vector for {point_id}: {e}")
                    continue

        # Add vectors to HNSW (batch operation)
        if vectors_to_add:
            self._add_vectors_to_hnsw(
                hnsw_index=index,
                id_mapping=id_mapping,
                point_ids=point_ids_to_add,
                vectors=vectors_to_add,
            )

    # Process deletions (soft delete)
    if changes['deleted']:
        if progress_callback:
            progress_callback(0, 0, Path(""), info=f"🗑️  Soft-deleting {len(changes['deleted'])} vectors from HNSW...")

        for point_id in changes['deleted']:
            if point_id in id_mapping:
                label = id_mapping[point_id]
                index.mark_deleted(label)

    # Save updated HNSW index
    if progress_callback:
        progress_callback(0, 0, Path(""), info="💾 Saving updated HNSW index...")

    index.save_index(str(collection_path / hnsw_manager.INDEX_FILENAME))

    # Update metadata
    hnsw_manager._update_metadata(
        collection_path=collection_path,
        vector_count=index.get_current_count(),
        M=16,
        ef_construction=200,
        ids=list(id_mapping.keys()),
        index_file_size=(collection_path / hnsw_manager.INDEX_FILENAME).stat().st_size,
    )

    if progress_callback:
        progress_callback(
            0, 0, Path(""),
            info=f"✅ HNSW incremental update complete: +{len(changes['added'])} ~{len(changes['updated'])} -{len(changes['deleted'])}"
        )
```

#### 2. `src/code_indexer/services/smart_indexer.py`

**🔴 CRITICAL REFACTORING** (Remove `skip_hnsw_rebuild` parameter from `end_indexing()` calls):

**Location 1** (`_do_full_index()`, line 790):
```python
# BEFORE (forces full rebuild - KEEP THIS):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)

# AFTER (no change - full index should always rebuild):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)
# Note: Auto-detection will trigger full rebuild (no session changes tracked)
```

**Location 2** (`_do_reconcile_with_database()`, line 1105):
```python
# BEFORE (forces full rebuild - WRONG):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)

# AFTER (let auto-detection decide):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)
# Auto-detection: If reconcile indexed files incrementally → incremental HNSW
# If reconcile did full clear → full rebuild
```

**Location 3** (`smart_index()`, line 1547):
```python
# BEFORE (forces full rebuild - WRONG):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)

# AFTER (let auto-detection decide):
end_result = self.qdrant_client.end_indexing(
    collection_name, progress_callback
)
# Auto-detection: If smart_index detected changes → incremental HNSW
# If first index → full rebuild
```

**Location 4** (`process_files_incrementally()`, line 1683):
```python
# NO CHANGE NEEDED - watch mode already optimized in Story HNSW-001
# Watch mode calls upsert_points(watch_mode=True) for real-time updates
```

---

## Testing Requirements

### Unit Tests

**File**: `tests/unit/storage/test_hnsw_incremental_batch.py`

```python
def test_track_added_vectors_during_session():
    """Test that new vectors are tracked as 'added'."""
    store = FilesystemVectorStore(tmp_path)
    store.create_collection("test_coll", vector_size=128)

    store.begin_indexing("test_coll")
    points = [{"id": "new_vec", "vector": [...], "payload": {...}}]
    store.upsert_points("test_coll", points)

    assert "new_vec" in store._indexing_session_changes["test_coll"]["added"]

def test_track_updated_vectors_during_session():
    """Test that existing vectors are tracked as 'updated'."""
    store = FilesystemVectorStore(tmp_path)
    store.create_collection("test_coll", vector_size=128)

    # Initial index
    store.begin_indexing("test_coll")
    points = [{"id": "existing_vec", "vector": [...], "payload": {...}}]
    store.upsert_points("test_coll", points)
    store.end_indexing("test_coll")

    # Update
    store.begin_indexing("test_coll")
    updated_points = [{"id": "existing_vec", "vector": [...], "payload": {...}}]
    store.upsert_points("test_coll", updated_points)

    assert "existing_vec" in store._indexing_session_changes["test_coll"]["updated"]

def test_track_deleted_vectors_during_session():
    """Test that deleted vectors are tracked."""
    store = FilesystemVectorStore(tmp_path)
    store.create_collection("test_coll", vector_size=128)

    # Setup
    store.begin_indexing("test_coll")
    points = [{"id": "vec_to_delete", "vector": [...], "payload": {...}}]
    store.upsert_points("test_coll", points)
    store.end_indexing("test_coll")

    # Delete
    store.begin_indexing("test_coll")
    store.delete_points("test_coll", ["vec_to_delete"])

    assert "vec_to_delete" in store._indexing_session_changes["test_coll"]["deleted"]

def test_incremental_hnsw_update_vs_full_rebuild():
    """Test incremental update is faster than full rebuild."""
    store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
    store.create_collection("test_coll", vector_size=128)

    # Initial index with 1000 vectors
    initial_points = [...]  # 1000 vectors
    store.begin_indexing("test_coll")
    store.upsert_points("test_coll", initial_points)
    store.end_indexing("test_coll")

    # Incremental update (10 changed vectors)
    store.begin_indexing("test_coll")
    changed_points = [...]  # 10 vectors
    store.upsert_points("test_coll", changed_points)

    import time
    start = time.time()
    result = store.end_indexing("test_coll")
    incremental_time = time.time() - start

    assert result["hnsw_mode"] == "incremental"
    assert incremental_time < 2.0  # Should be fast (< 2 seconds)

def test_auto_detection_full_rebuild_on_first_index():
    """Test full rebuild on first index (no session changes)."""
    store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
    store.create_collection("test_coll", vector_size=128)

    # First index without begin_indexing() (no tracking)
    points = [...]
    store.upsert_points("test_coll", points)
    result = store.end_indexing("test_coll")

    assert result["hnsw_mode"] == "full_rebuild"
```

### Integration Tests

**File**: `tests/integration/test_incremental_hnsw_batch.py`

```python
def test_cidx_index_incremental_uses_incremental_hnsw(tmpdir):
    """Test cidx index with incremental changes uses incremental HNSW."""
    # Setup: Initial full index (1000 files)
    # Modify 10 files
    # Run cidx index
    # Assert:
    #   - Indexing completes in < 5 seconds
    #   - HNSW mode == "incremental"
    #   - Query returns modified files

def test_cidx_index_first_run_uses_full_rebuild(tmpdir):
    """Test cidx index on fresh repo uses full rebuild."""
    # Setup: Fresh repo with 100 files
    # Run cidx index
    # Assert:
    #   - HNSW mode == "full_rebuild"
    #   - All files indexed

def test_cidx_index_with_deletions_soft_deletes_hnsw(tmpdir):
    """Test cidx index with deleted files soft-deletes from HNSW."""
    # Setup: Index 100 files
    # Delete 10 files
    # Run cidx index --detect-deletions
    # Assert:
    #   - Deleted files not in query results
    #   - HNSW soft-deleted (not full rebuild)
```

### Performance Benchmarks

**File**: `scripts/benchmark_hnsw_incremental.py`

```python
def benchmark_incremental_vs_full_rebuild():
    """Benchmark incremental vs full rebuild performance."""

    # Scenario: 10,000 vector index, 10 files changed

    # Measure: Full rebuild
    start = time.time()
    hnsw_manager.rebuild_from_vectors(collection_path)
    full_rebuild_time = time.time() - start

    # Measure: Incremental update
    start = time.time()
    store._apply_incremental_hnsw_batch_update(...)
    incremental_time = time.time() - start

    speedup = full_rebuild_time / incremental_time
    print(f"Full rebuild: {full_rebuild_time:.2f}s")
    print(f"Incremental: {incremental_time:.2f}s")
    print(f"Speedup: {speedup:.1f}x")

    assert speedup > 2.0  # At least 2x faster
```

---

## Edge Cases and Error Handling

### Edge Case 1: HNSW Index Load Failure (Corruption)
**Scenario**: Incremental update tries to load corrupted HNSW index
**Handling**:
- Catch `RuntimeError` from `load_index()`
- Log warning: "HNSW index corrupted, falling back to full rebuild"
- Call `rebuild_from_vectors()` (one-time full rebuild)
- Continue normally

### Edge Case 2: No Changes Detected
**Scenario**: `end_indexing()` called but no vectors changed
**Handling**:
- Check if `changes['added']` and `changes['updated']` and `changes['deleted']` all empty
- Skip incremental update (no work to do)
- Log info: "No HNSW changes detected, skipping update"

### Edge Case 3: Mixed Session (Some Vectors Missing)
**Scenario**: Session tracks changes but some vector files missing on disk
**Handling**:
- Try to load each vector file
- Catch `FileNotFoundError`, log warning, skip that vector
- Continue processing other vectors
- Don't fail entire session

### Edge Case 4: First Index After Migration
**Scenario**: Existing repo with vectors but no HNSW index
**Handling**:
- `load_index()` raises exception (no index file)
- Catch exception, log info: "No HNSW index found, building from scratch"
- Call `rebuild_from_vectors()` (creates index)
- Future runs use incremental updates

---

## Performance Expectations

### Timing Targets
- **Small changes** (10 files in 1K index): < 1 second
- **Medium changes** (100 files in 10K index): < 3 seconds
- **Large changes** (1K files in 10K index): < 10 seconds (still faster than full rebuild)
- **Speedup vs full rebuild**: 2-5x (depends on change ratio)

### Scalability
- **10% changed**: ~3x speedup
- **1% changed**: ~10x speedup
- **0.1% changed**: ~50x speedup
- **50%+ changed**: Approach full rebuild time (but still incremental is faster)

---

## Rollout Plan

### Phase 1: Foundation (Depends on HNSW-001)
1. Reuse `HNSWIndexManager` incremental methods from Story HNSW-001
2. Reuse `_add_vectors_to_hnsw()` helper from Story HNSW-001

### Phase 2: Change Tracking
1. Add `_indexing_session_changes` to `FilesystemVectorStore`
2. Modify `begin_indexing()`, `upsert_points()`, `delete_points()`
3. Write unit tests for change tracking

### Phase 3: Incremental Update Logic
1. Implement `_apply_incremental_hnsw_batch_update()`
2. Modify `end_indexing()` with auto-detection
3. Write unit tests

### Phase 4: SmartIndexer Refactoring (CRITICAL)
1. Remove `skip_hnsw_rebuild` parameters from 3 locations
2. Test all indexing modes: full, incremental, reconcile, resume
3. Write integration tests

### Phase 5: Validation
1. Performance benchmarking
2. Edge case testing
3. Manual testing with real repos
4. Documentation updates

---

## Related Work

- **Story HNSW-001**: Watch Mode Real-Time HNSW Updates (shares common code)
- **Completed Story**: HNSW Watch Staleness Coordination (added `skip_hnsw_rebuild` parameter)

---

## Success Metrics

**Before** (cidx index today):
- Index 10 files (out of 10K): ~12 seconds (10s processing + 2s HNSW rebuild)
- CPU usage: 100% for 12 seconds
- Speedup from git-aware deduplication: Wasted by HNSW full rebuild

**After** (with this story):
- Index 10 files (out of 10K): ~11 seconds (10s processing + 1s incremental HNSW)
- CPU usage: 100% for 10s, then brief spike for HNSW
- Speedup from git-aware deduplication: Preserved (incremental HNSW matches incremental indexing)

**Larger Repos**:
- Index 10 files (out of 100K): ~15 seconds → ~11 seconds (5-10s HNSW savings)
- Index 100 files (out of 100K): ~120 seconds → ~115 seconds (still 5-10s savings)

---

**End of User Story HNSW-002**
