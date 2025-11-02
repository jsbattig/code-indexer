# User Story: Watch Mode Real-Time HNSW Updates

**Epic**: HNSW Incremental Updates
**Story ID**: HNSW-001
**Priority**: HIGH
**Estimate**: 8 story points

---

## Story Description

**As a** developer using `cidx watch`
**I want** HNSW index to be updated incrementally as each file is indexed
**So that** query results reflect latest code changes instantly without 5-10 second rebuild delays

---

## Current Behavior (Problem)

**Watch Mode Flow Today**:
```
File Changed → Debounce (2s) → Index File → Write Vector JSON → Mark HNSW Stale → Return
                                                                        ↓
User Queries → Detect Stale HNSW → **FULL REBUILD (5-10s delay)** → Query → Results
```

**Problems**:
1. ❌ **First query after file changes blocks for 5-10 seconds** (full HNSW rebuild)
2. ❌ **Poor developer experience** - watch mode feels "laggy" despite being "real-time"
3. ❌ **Wasted CPU** - rebuilds entire HNSW index (10K vectors) when only 1-10 files changed
4. ❌ **Query timeout risk** - large indexes can timeout on first query after changes

**Evidence**:
- `FilesystemVectorStore.search()` lines 1296-1315: Detects staleness, blocks query for full rebuild
- `GitAwareWatchHandler._process_pending_changes()` line 254: Passes `watch_mode=True` which triggers `skip_hnsw_rebuild=True`
- Manual test TC081: Documents cache invalidation and query delays

---

## Desired Behavior (Solution)

**Watch Mode Flow After This Story**:
```
File Changed → Debounce (2s) → Index File → Write Vector JSON → **Update HNSW Incrementally (10-50ms)** → Return
                                                                              ↓
User Queries → Use Fresh HNSW → Query → **Instant Results (no delay)**
```

**Benefits**:
1. ✅ **Zero query delay** - HNSW always fresh, no rebuild needed
2. ✅ **Real-time experience** - queries return instantly after file changes
3. ✅ **Efficient CPU usage** - only add changed vectors (1-10 files vs 10K vectors)
4. ✅ **Better scalability** - works for large indexes without query timeouts

---

## Acceptance Criteria

### AC1: File-by-File HNSW Updates During Watch Mode
**GIVEN** watch mode is running
**WHEN** a file is indexed (created, modified, or deleted)
**THEN** HNSW index is updated incrementally **immediately after vector generation**
**AND** update completes in < 100ms per file
**AND** no "stale" flag is set (HNSW remains fresh)

**Implementation Requirements**:
- Call `hnsw_manager.add_or_update_vector()` in `FilesystemVectorStore.upsert_points()` when `watch_mode=True`
- Use readers-writer lock pattern: `write_lock` + `read_lock` (nested)
- Blocks concurrent queries for ~10-50ms during `add_items()` operation
- Update both daemon cache (in-memory) AND disk (standalone mode)

### AC2: Concurrent Query Support with Readers-Writer Lock
**GIVEN** watch mode is updating HNSW index
**WHEN** user issues query during update
**THEN** query **waits for write operation to complete** (~10-50ms)
**AND** query executes successfully after write completes
**AND** no errors or crashes occur
**AND** results include newly indexed vector

**Implementation Requirements**:
- Use `CacheEntry.write_lock` for exclusive HNSW write access
- Nest `CacheEntry.read_lock` inside write lock to prevent concurrent queries
- Thread-safe implementation per hnswlib requirements
- Graceful handling of lock contention

### AC3: Daemon Cache In-Memory Updates (No Invalidation)
**GIVEN** daemon mode with cached HNSW index
**AND** watch mode is running
**WHEN** file is indexed and HNSW updated
**THEN** daemon cache HNSW index is **updated in-memory** (not invalidated)
**AND** subsequent queries use cached index (warm cache)
**AND** no cache reload/rebuild occurs

**Implementation Requirements**:
- Detect daemon mode: check if `cache_entry` exists
- Update `cache_entry.hnsw_index` directly via `add_items()`
- Do NOT call `cache_entry.invalidate()`
- Manual test TC081 pass criteria: "Watch updates cache in-memory, queries return latest data, no cache invalidation"

### AC4: Standalone Mode File Persistence
**GIVEN** standalone mode (no daemon)
**WHEN** file is indexed in watch mode
**THEN** HNSW index is **loaded from disk**, updated, and **saved back to disk**
**AND** subsequent watch cycles load updated index (cumulative updates)
**AND** index file size grows appropriately

**Implementation Requirements**:
- Load existing HNSW index via `hnsw_manager.load_index()`
- Update via `add_items()`
- Save via `index.save_index()`
- Update metadata (vector count, file size, last_update timestamp)

### AC5: Deletion Handling via Soft Delete
**GIVEN** watch mode detects file deletion
**WHEN** file's vectors are removed from vector store
**THEN** corresponding HNSW entries are **soft-deleted** via `mark_deleted()`
**AND** deleted entries are excluded from query results automatically
**AND** no full rebuild occurs

**Implementation Requirements**:
- Track deleted point IDs in `FilesystemVectorStore.delete_points()`
- Call `hnsw_index.mark_deleted(label)` for each deleted point
- hnswlib automatically excludes from `knn_query()` results
- Post-query filter: if file doesn't exist, skip result (safety check)

### AC6: Label Management and ID Mapping Consistency
**GIVEN** HNSW index with existing vectors
**WHEN** new file is indexed (first time)
**THEN** new label is assigned: `label = len(id_mapping)`
**WHEN** existing file is re-indexed (modified)
**THEN** existing label is reused: `label = id_mapping[point_id]`
**AND** HNSW update replaces vector at same label

**Implementation Requirements**:
- Maintain `id_mapping: Dict[point_id, label]` in `HNSWIndexManager`
- Load mapping from metadata on index load
- Save mapping to metadata on index save
- Atomic updates: check ID → get/create label → add_items() → save mapping

---

## Technical Implementation Details

### Modified Files

#### 1. `src/code_indexer/storage/hnsw_index_manager.py`

**New Methods**:
```python
def load_for_incremental_update(
    self,
    collection_path: Path,
    max_elements: int = 100000
) -> None:
    """Load existing HNSW index for incremental updates.

    If index doesn't exist, creates new one.
    Loads ID→label mapping from metadata.
    """

def add_or_update_vector(
    self,
    point_id: str,
    vector: np.ndarray
) -> None:
    """Add new vector or update existing one.

    Args:
        point_id: Unique vector ID
        vector: Vector array (shape: (vector_dim,))

    Implementation:
        - Check if point_id in id_mapping
        - If exists: reuse label (update)
        - If new: create new label = len(id_mapping)
        - Call self.index.add_items(vector.reshape(1, -1), [label])
    """

def remove_vector(
    self,
    point_id: str
) -> None:
    """Soft delete vector from index.

    Args:
        point_id: Vector ID to delete

    Implementation:
        - Get label from id_mapping
        - Call self.index.mark_deleted(label)
        - Keep in id_mapping for potential undelete
    """

def save_incremental_update(
    self,
    collection_path: Path
) -> None:
    """Save incrementally updated index to disk.

    Implementation:
        - Save HNSW index: self.index.save_index()
        - Update metadata with new vector count
        - Save ID mapping to metadata
    """
```

#### 2. `src/code_indexer/storage/filesystem_vector_store.py`

**Modified Method**:
```python
def upsert_points(
    self,
    collection_name: str,
    points: List[Dict],
    watch_mode: bool = False  # NEW PARAMETER
) -> Dict:
    """Upsert vectors with optional real-time HNSW updates.

    Args:
        collection_name: Collection name
        points: List of vectors to upsert
        watch_mode: If True, update HNSW incrementally (NEW)

    Implementation:
        # Phase 1: Write vectors to disk (existing code)
        for point in points:
            # ... existing code to write vector JSON ...

            if watch_mode:
                new_point_ids.append(point_id)
                vectors_to_add.append(vector)

        # Phase 2: Incremental HNSW update (NEW)
        if watch_mode and vectors_to_add:
            self._update_hnsw_incrementally_realtime(
                collection_name=collection_name,
                point_ids=new_point_ids,
                vectors=vectors_to_add,
            )

        return {"status": "ok", "count": len(points)}
    """
```

**New Helper Methods**:
```python
def _update_hnsw_incrementally_realtime(
    self,
    collection_name: str,
    point_ids: List[str],
    vectors: List[np.ndarray],
) -> None:
    """Update HNSW index incrementally with locking (watch mode).

    Implementation:
        if daemon mode (cache_entry exists):
            with cache_entry.write_lock:
                with cache_entry.read_lock:  # Prevent concurrent queries
                    if cache_entry.hnsw_index is None:
                        # Load index into cache
                    self._add_vectors_to_hnsw(...)
        else:  # Standalone mode
            manager = HNSWIndexManager(...)
            index = manager.load_index(collection_path)
            id_mapping = manager._load_id_mapping(collection_path)

            self._add_vectors_to_hnsw(index, id_mapping, point_ids, vectors)

            # Save updated index
            index.save_index(...)
            manager._update_metadata(...)
    """

def _add_vectors_to_hnsw(
    self,
    hnsw_index: Any,
    id_mapping: Dict[str, int],
    point_ids: List[str],
    vectors: List[np.ndarray],
) -> None:
    """Add vectors to HNSW index with label management.

    Implementation:
        labels = []
        for point_id in point_ids:
            if point_id in id_mapping:
                label = id_mapping[point_id]  # Update existing
            else:
                label = len(id_mapping)  # New label
                id_mapping[point_id] = label
            labels.append(label)

        vectors_array = np.array(vectors, dtype=np.float32)
        labels_array = np.array(labels, dtype=np.int64)
        hnsw_index.add_items(vectors_array, labels_array)
    """
```

#### 3. `src/code_indexer/services/git_aware_watch_handler.py`

**Modified Method**:
```python
def _process_pending_changes(self, final_cleanup: bool = False):
    """Process file changes and update HNSW incrementally.

    Implementation Changes:
        # Existing code for processing files...
        stats = self.smart_indexer.process_files_incrementally(
            relative_paths,
            force_reprocess=False,
            quiet=False,
            watch_mode=True,  # ← ALREADY PASSED
        )

        # NEW: Verify HNSW was updated (not marked stale)
        # Log info message confirming incremental update
    """
```

#### 4. `src/code_indexer/services/smart_indexer.py`

**Modified Method**:
```python
def process_files_incrementally(
    self,
    files: List[str],
    force_reprocess: bool = False,
    quiet: bool = False,
    watch_mode: bool = False,  # ALREADY EXISTS
) -> ProcessingStats:
    """Process files incrementally (used by watch mode).

    Implementation Changes:
        # ... existing processing logic ...

        # Pass watch_mode to qdrant_client.upsert_points()
        success = self.qdrant_client.upsert_points(
            points=points_data,
            collection_name=collection_name,
            watch_mode=watch_mode,  # NEW: Enable real-time HNSW
        )

        # Note: end_indexing() NOT called during watch incremental processing
        # (only called during full index cycles)
    """
```

### Integration Flow

**Watch Mode Execution Path**:
```
GitAwareWatchHandler.on_modified(file)
  ↓
GitAwareWatchHandler._add_pending_change(file, "modified")
  ↓ (debounce 2s)
GitAwareWatchHandler._process_pending_changes()
  ↓
SmartIndexer.process_files_incrementally(files, watch_mode=True)
  ↓
FileChunkingManager.process_file_batch(...)
  ↓
FilesystemVectorStore.upsert_points(points, watch_mode=True)
  ↓
FilesystemVectorStore._update_hnsw_incrementally_realtime(...)
  ↓
[Daemon Mode]
  with cache_entry.write_lock:
    with cache_entry.read_lock:
      cache_entry.hnsw_index.add_items(vectors, labels)  # ← IN-MEMORY UPDATE
  ↓
[Standalone Mode]
  hnsw_manager.load_index()
  hnsw_index.add_items(vectors, labels)
  hnsw_index.save_index()  # ← DISK UPDATE
```

---

## Testing Requirements

### Unit Tests

**File**: `tests/unit/storage/test_hnsw_incremental_updates.py`

```python
def test_add_or_update_new_vector():
    """Test adding new vector assigns new label."""
    manager = HNSWIndexManager(vector_dim=128)
    manager.load_for_incremental_update(tmp_path)

    vector = np.random.randn(128).astype(np.float32)
    manager.add_or_update_vector("new_vector_id", vector)

    assert "new_vector_id" in manager.id_mapping
    assert manager.id_mapping["new_vector_id"] == 0  # First label

def test_add_or_update_existing_vector_reuses_label():
    """Test updating existing vector reuses same label."""
    manager = HNSWIndexManager(vector_dim=128)
    manager.load_for_incremental_update(tmp_path)

    # Add first time
    vector1 = np.random.randn(128).astype(np.float32)
    manager.add_or_update_vector("vec_id", vector1)
    original_label = manager.id_mapping["vec_id"]

    # Update with new vector
    vector2 = np.random.randn(128).astype(np.float32)
    manager.add_or_update_vector("vec_id", vector2)

    assert manager.id_mapping["vec_id"] == original_label  # Same label

def test_remove_vector_soft_delete():
    """Test soft deletion marks vector as deleted."""
    manager = HNSWIndexManager(vector_dim=128)
    manager.load_for_incremental_update(tmp_path)

    # Add vector
    vector = np.random.randn(128).astype(np.float32)
    manager.add_or_update_vector("vec_id", vector)

    # Soft delete
    manager.remove_vector("vec_id")

    # Vector should still be in ID mapping but marked deleted
    assert "vec_id" in manager.id_mapping
    # Query should not return it (hnswlib excludes marked_deleted)

def test_watch_mode_updates_hnsw_incrementally():
    """Test watch mode triggers incremental HNSW updates."""
    store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
    store.create_collection("test_coll", vector_size=128)

    # Initial index
    points = [...]
    store.begin_indexing("test_coll")
    store.upsert_points("test_coll", points)
    store.end_indexing("test_coll", skip_hnsw_rebuild=False)

    # Watch mode: add new vectors with watch_mode=True
    new_points = [...]
    store.upsert_points("test_coll", new_points, watch_mode=True)

    # HNSW should be fresh (not stale)
    hnsw_manager = HNSWIndexManager(vector_dim=128, space="cosine")
    assert not hnsw_manager.is_stale(tmp_path / "test_coll")

    # Query should return new vectors immediately
    results = store.search("test query", embedding_provider, "test_coll")
    assert len(results) > 0
```

### Integration Tests

**File**: `tests/integration/test_watch_mode_hnsw_realtime.py`

```python
def test_watch_mode_realtime_hnsw_updates_no_query_delay(tmpdir):
    """Test watch mode updates HNSW in real-time without query delays."""
    # Setup: Index initial files
    # Start watch mode
    # Modify file
    # Wait for debounce + processing
    # Issue query
    # Assert: Query returns instantly (< 500ms), includes new content

def test_watch_mode_concurrent_queries_during_updates(tmpdir):
    """Test concurrent queries work during HNSW updates (readers-writer lock)."""
    # Setup: Start watch mode
    # Thread 1: Modify files continuously (trigger HNSW updates)
    # Thread 2: Issue queries continuously
    # Assert: No crashes, no errors, queries succeed, results include latest changes

def test_watch_mode_daemon_cache_remains_warm(tmpdir):
    """Test daemon cache HNSW is updated in-memory (TC081)."""
    # Setup: Start daemon, index files, start watch
    # Query: cache loads HNSW
    # Modify file in watch mode
    # Query again
    # Assert: No cache invalidation logged, query instant, result includes new content
```

### Manual Testing (TC081 Enhancement)

**Update Existing Test** in `plans/active/02_Feat_CIDXDaemonization/manual_testing/02_Regression_Tests.md`:

**TC081: Watch mode cache updates**:
```markdown
Pass Criteria (UPDATED):
- Watch updates cache in-memory (HNSW index updated, not invalidated)
- Queries during watch return latest data immediately (< 500ms)
- No cache invalidation (remains warm)
- **NEW**: First query after file change completes in < 500ms (no rebuild delay)
- **NEW**: Subsequent queries complete in < 100ms (cached HNSW)
```

---

## Edge Cases and Error Handling

### Edge Case 1: HNSW Index Capacity Exceeded
**Scenario**: Adding vectors exceeds `max_elements`
**Handling**:
- Call `index.resize_index(new_max_elements)` before `add_items()`
- Set `new_max_elements = current_count * 1.5` (50% growth)
- Log warning: "HNSW index resized"

### Edge Case 2: Lock Timeout (Concurrent Operations)
**Scenario**: Write lock held too long, queries time out
**Handling**:
- Set lock timeout: `write_lock.acquire(timeout=10.0)`
- If timeout, raise `RuntimeError("HNSW update timeout")`
- Log error with context

### Edge Case 3: Index Corruption During Update
**Scenario**: `add_items()` raises exception
**Handling**:
- Catch exception in `_update_hnsw_incrementally_realtime()`
- Log error: "HNSW incremental update failed, marking stale"
- Call `hnsw_manager.mark_stale()` (fallback to rebuild)
- Continue processing (don't crash watch mode)

### Edge Case 4: Standalone Mode Index Load Failure
**Scenario**: HNSW index file corrupted, can't load
**Handling**:
- Catch `RuntimeError` from `load_index()`
- Log warning: "HNSW index corrupted, rebuilding from vectors"
- Fall back to `rebuild_from_vectors()` (full rebuild once)
- Mark index fresh after rebuild

---

## Performance Expectations

### Timing Targets
- **Single vector add**: < 10ms (target), < 50ms (acceptable)
- **Batch add (10 vectors)**: < 50ms (target), < 100ms (acceptable)
- **Query during write**: +10-50ms latency (lock wait time)
- **First query after change**: < 500ms (no rebuild)

### Scalability
- **Small index** (1K vectors): ~5ms per vector add
- **Medium index** (10K vectors): ~10ms per vector add
- **Large index** (100K vectors): ~50ms per vector add
- **Very large index** (1M+ vectors): May need batch optimization

---

## Rollout Plan

### Phase 1: Core Implementation
1. Implement `HNSWIndexManager` incremental methods
2. Implement `FilesystemVectorStore._update_hnsw_incrementally_realtime()`
3. Add `watch_mode` parameter to `upsert_points()`
4. Write unit tests

### Phase 2: Integration
1. Modify `SmartIndexer.process_files_incrementally()` to pass `watch_mode`
2. Test with `GitAwareWatchHandler`
3. Write integration tests

### Phase 3: Daemon Mode
1. Test with daemon cache (in-memory updates)
2. Verify TC081 passes
3. Test concurrent queries

### Phase 4: Validation
1. Run manual tests
2. Performance benchmarking
3. Edge case testing
4. Documentation updates

---

## Related Work

- **Story HNSW-002**: Incremental Index Batch HNSW Updates (end-of-cycle batch)
- **Manual Test TC081**: Watch mode cache updates
- **Manual Test TC082**: Watch progress callbacks with concurrent queries

---

## Success Metrics

**Before** (watch mode today):
- First query after file change: 5-10 seconds (full rebuild)
- Developer experience: "Laggy", "frustrating"
- CPU usage: 100% for 5-10s (rebuild)

**After** (with this story):
- First query after file change: < 500ms (instant)
- Developer experience: "Real-time", "responsive"
- CPU usage: < 1% per file change (incremental)

---

**End of User Story HNSW-001**
