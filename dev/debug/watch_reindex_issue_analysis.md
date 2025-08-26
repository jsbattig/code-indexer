# Watch Re-indexing Issue Analysis

## Problem Summary

Files indexed by watch mode are being re-indexed by subsequent reconcile operations, even though they haven't changed. This defeats the purpose of timestamp-based change detection.

## Root Causes Identified

### 1. FileIdentifier Type Mismatch (Minor Issue)
- **FileIdentifier** (`file_identifier.py:281`) returns `int(stat.st_mtime)` - truncating to integer
- **BranchAwareIndexer** (`branch_aware_indexer.py:636`) uses `stat.st_mtime` directly - keeping as float
- **SmartIndexer reconcile** (`smart_indexer.py:810`) uses `stat().st_mtime` - getting float

This truncation loses fractional seconds but is partially mitigated by the 1-second tolerance in reconcile.

### 2. Force Reprocess Flag in Watch (Main Issue)
- **GitAwareWatchHandler** (`git_aware_watch_handler.py:277`) calls `process_files_incrementally` with `force_reprocess=True`
- This flag is meant to force re-indexing regardless of timestamps
- However, the `force_reprocess` parameter is defined but NOT actually used in the implementation

### 3. Possible Missing Implementation
The `force_reprocess` parameter in `process_files_incrementally` is not being used to skip timestamp checks when True.

## Evidence

1. **Test Expectation**: `test_watch_timestamp_update_e2e.py:243-246` expects reconcile to NOT re-index watch-indexed files
2. **Debug Output**: The reconcile debug messages show timestamp comparisons happening
3. **BranchAwareIndexer**: Correctly stores `file_mtime` in ContentMetadata
4. **Reconcile Query**: Correctly retrieves `file_mtime` from database (priority 1 in query)

## Recommended Solutions

### Solution 1: Remove force_reprocess=True from watch handler
```python
# In git_aware_watch_handler.py:275-280
stats = self.smart_indexer.process_files_incrementally(
    relative_paths,
    force_reprocess=False,  # Changed from True
    quiet=False,
    watch_mode=True,
)
```

### Solution 2: Fix FileIdentifier timestamp type
```python
# In file_identifier.py:281
return {"file_mtime": stat.st_mtime, "file_size": stat.st_size}  # Keep as float
```

### Solution 3: Implement force_reprocess logic (if needed)
If force_reprocess is actually needed for watch mode, implement it properly in `process_files_incrementally` to skip timestamp checks when True.

## Testing

Run these tests to verify the fix:
1. `pytest tests/test_watch_timestamp_update_e2e.py -v`
2. `pytest tests/test_timestamp_comparison_e2e.py -v`
3. Manual test: Start watch, modify a file, stop watch, run reconcile - should show "0 files to index"