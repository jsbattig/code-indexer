# Story 2: Update Temporal Query Service for Diff-Based Results

## Context

After Story 1 rewrites indexing to use diffs instead of full blobs, the query service needs updates to:
1. **REMOVE ALL SQLite** - Use JSON payloads for time filtering (no commits.db)
2. Remove obsolete `filter_timeline_changes()` method (no longer needed)
3. Rewrite `_filter_by_time_range()` to use JSON payloads (no SQL queries)
4. Remove `[NO CHANGES IN CHUNK]` display logic
5. Add diff-type display markers: `[ADDED]`, `[DELETED]`, `[MODIFIED]`, `[RENAMED]`, `[BINARY]`
6. Delete 13 SQLite-dependent test files
7. Delete 4 blob-based helper methods from temporal_search_service.py

**CRITICAL ARCHITECTURAL DECISION:**

Story 1 stores ALL commit metadata in JSON payloads (commit_timestamp, commit_date, commit_message, author_name). This makes SQLite completely unnecessary for querying.

**Old approach:** Semantic search → SQL query commits.db → Filter → Display
**New approach:** Semantic search → Filter JSON payloads in-memory → Display

**Benefits:**
- No database I/O overhead
- Simpler code (no SQL, no schema)
- Faster queries (in-memory filtering)
- Same data access pattern as regular indexing

##User Story

**As a developer**, I want temporal query results to show diff-type markers (`[ADDED]`, `[MODIFIED]`, `[DELETED]`) instead of `[NO CHANGES IN CHUNK]`, **so that** I immediately understand what type of change occurred for each file.

## Requirements

### Query Service Changes

**File**: `src/code_indexer/services/temporal/temporal_search_service.py`

#### 1. Remove `filter_timeline_changes()` Method (Lines 829-927)

**Reason**: With diff-only indexing, every result IS a change by definition. No need to filter "unchanged" chunks because they don't exist in the index.

**Delete entire method**: Lines 829-927

**Update callers**:
- Line 313-316: Remove call to `filter_timeline_changes()`
- Simply use temporal results directly after time range filtering

**Before**:
```python
# Phase 3: Filter timeline changes
temporal_results = self.filter_timeline_changes(
    temporal_results, show_unchanged=show_unchanged
)
```

**After**:
```python
# No timeline filtering needed - all results are changes by definition
# Just sort chronologically (oldest to newest)
temporal_results = sorted(
    temporal_results,
    key=lambda r: r.temporal_context.get("commit_timestamp", 0)
)
```

#### 2. REMOVE ALL SQLite - Use JSON Payloads Instead (Lines 465-641)

**CRITICAL**: Completely eliminate SQLite from temporal_search_service.py. All data is in JSON payloads.

**OLD APPROACH (WRONG - SQLite):**
```python
# Query commits.db for metadata
conn = sqlite3.connect(str(self.commits_db_path))
query = f"""
    SELECT hash, date, message, author_name
    FROM commits
    WHERE hash IN ({placeholders})
      AND date >= ?
      AND date <= ?
"""
cursor = conn.execute(query, params)
# Build commit_lookup from SQL results
```

**NEW APPROACH (CORRECT - JSON Payloads):**
```python
# NO SQLite - filter semantic results in-memory using payload data
start_ts = parse_date_to_timestamp(start_date)
end_ts = parse_date_to_timestamp(end_date)

filtered_results = []
for result in semantic_results:
    payload = result.payload  # or result.get("payload", {})
    commit_ts = payload.get("commit_timestamp")

    # Time filtering using payload timestamp (no SQL needed)
    if commit_ts and start_ts <= commit_ts <= end_ts:
        # Create temporal result with metadata from payload
        temporal_result = TemporalSearchResult(
            file_path=payload.get("file_path"),
            score=result.score,
            content=result.content,
            diff_type=payload.get("diff_type"),
            temporal_context={
                "commit_hash": payload.get("commit_hash"),
                "commit_date": payload.get("commit_date"),
                "commit_message": payload.get("commit_message"),
                "author_name": payload.get("author_name"),
                "commit_timestamp": commit_ts,
            }
        )
        filtered_results.append(temporal_result)

return filtered_results
```

**REMOVE COMPLETELY:**
- All `import sqlite3` statements
- `self.commits_db_path` initialization
- All `sqlite3.connect()` calls
- All SQL queries (commits table, trees table)
- All `blob_data` tracking
- All `first_seen`/`last_seen` logic
- All `blob_hash` grouping

### Detailed Code Removal from temporal_search_service.py

**COMPLETE REWRITE of _filter_by_time_range()** (lines 492-733):

**DELETE:**
- All SQLite connection code
- All SQL queries
- All blob_hash tracking logic
- All first_seen/last_seen tracking
- All HEAD blob comparison logic
- `_get_head_file_blobs()` helper method

**REPLACE WITH:**
```python
def _filter_by_time_range(
    self,
    semantic_results: List[Any],
    start_date: str,
    end_date: str,
    include_removed: bool,
) -> List[TemporalSearchResult]:
    """Filter semantic results by time range using JSON payloads.

    NO SQLite - all data in payloads.
    """
    from datetime import datetime

    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    filtered_results = []
    for result in semantic_results:
        payload = result.payload if hasattr(result, 'payload') else result.get("payload", {})
        commit_ts = payload.get("commit_timestamp")

        # Time filtering using payload timestamp
        if commit_ts and start_ts <= commit_ts <= end_ts:
            temporal_result = TemporalSearchResult(
                file_path=payload.get("file_path"),
                score=result.score,
                content=result.content,
                chunk_index=payload.get("chunk_index", 0),
                metadata=payload,
                diff_type=payload.get("diff_type"),
                temporal_context={
                    "commit_hash": payload.get("commit_hash"),
                    "commit_date": payload.get("commit_date"),
                    "commit_message": payload.get("commit_message"),
                    "author_name": payload.get("author_name"),
                    "commit_timestamp": commit_ts,
                }
            )
            filtered_results.append(temporal_result)

    return filtered_results
```

**DELETE THESE METHODS ENTIRELY:**
- `_fetch_commit_file_changes()` (lines 763-799) - Uses trees table queries
- `_is_new_file()` (lines 814-851) - Uses trees table queries
- `_generate_chunk_diff()` (lines 958-1015) - Uses blob-based logic
- `_get_head_file_blobs()` - Uses git ls-tree (blob-based)

**REMOVE FROM __init__:**
- Line 74: `self.commits_db_path = ...` initialization

#### 3. Remove `--show-unchanged` Flag

**Files to modify**:
- `src/code_indexer/cli.py` - Remove `--show-unchanged` option from query command
- `temporal_search_service.py` - Remove `show_unchanged` parameter from all methods

**Reason**: Flag is meaningless now. Every result is a change.

#### 4. Update Display Logic

**File**: `src/code_indexer/cli.py` (display_temporal_results function)

**Changes**:

Remove `[NO CHANGES IN CHUNK]` detection and display:
```python
# OLD:
if result.metadata.get("display_status") == "no_changes":
    console.print(f"[NO CHANGES IN CHUNK]", style="dim yellow")

# DELETE THIS - no longer applicable
```

Add diff-type markers based on payload:
```python
# NEW:
diff_type = result.metadata.get("diff_type", "unknown")
diff_markers = {
    "added": "[ADDED]",
    "deleted": "[DELETED]",
    "modified": "[MODIFIED]",
    "renamed": "[RENAMED]",
    "binary": "[BINARY]",
}
marker = diff_markers.get(diff_type, "[UNKNOWN]")
marker_color = {
    "added": "green bold",
    "deleted": "red bold",
    "modified": "yellow bold",
    "renamed": "cyan bold",
    "binary": "magenta",
}.get(diff_type, "white")

console.print(f"{marker}", style=marker_color)
```

### Complete SQLite Elimination

**CRITICAL**: Remove ALL SQLite usage from temporal query service. No databases, no SQL queries.

**Source File to Modify:**

1. **`src/code_indexer/services/temporal/temporal_search_service.py`**
   - Remove: `import sqlite3` (line 9)
   - Remove: `self.commits_db_path` initialization (line 74)
   - Remove: All methods that use SQLite:
     - `_filter_by_time_range()` - Rewrite to use JSON payloads (lines 492-733)
     - `_fetch_commit_file_changes()` - DELETE entirely (lines 763-799)
     - `_is_new_file()` - DELETE entirely (lines 814-851)
     - `_generate_chunk_diff()` - DELETE entirely (lines 958-1015)
   - Remove: All `sqlite3.connect()` calls
   - Remove: All SQL queries to commits/trees tables

**Test Files to DELETE** (13 files with SQLite dependencies):

1. `tests/e2e/temporal/test_temporal_indexing_e2e.py` - Tests blob-based SQLite indexing
2. `tests/e2e/temporal/test_temporal_query_e2e.py` - Tests SQLite-based queries
3. `tests/unit/services/temporal/test_temporal_search_service.py` - Tests SQLite filtering
4. `tests/unit/services/temporal/test_temporal_indexer_story2_1.py` - Tests deprecated behavior
5. `tests/unit/services/temporal/test_temporal_search_service_story2_1.py` - Tests old approach
6. `tests/unit/services/temporal/test_temporal_query_type_field_fix.py` - Tests blob-based queries
7. `tests/unit/services/temporal/test_temporal_filter_support.py` - Tests SQLite filtering
8. `tests/unit/services/temporal/test_temporal_query_fix.py` - Tests deprecated queries
9. `tests/unit/services/temporal/test_temporal_index_detection.py` - Tests commits.db detection
10. `tests/services/temporal/test_temporal_indexer.py` - Tests SQLite database creation
11. `tests/services/temporal/test_temporal_indexer_changed_files_only.py` - Tests blob approach
12. `tests/services/temporal/test_temporal_indexer_diff_based.py` - May have SQLite refs
13. `tests/services/temporal/test_temporal_search_service_story2.py` - Tests old SQLite approach

**Replacement Tests** (keep these, created in Story 1):
- `tests/unit/services/temporal/test_temporal_diff_scanner.py` - Tests diff scanner
- `tests/unit/services/temporal/test_temporal_indexer_parallel_processing.py` - Tests parallel indexing
- Any new diff-based query tests (to be created in Story 2)

**Why SQLite is Completely Unnecessary:**

Story 1 decision: All commit metadata stored in JSON payloads.

**Payload contains everything:**
```python
{
    "commit_timestamp": 1730462400,  # For time filtering
    "commit_date": "2025-11-01",     # For display
    "commit_message": "Add auth",    # For display
    "author_name": "Test User",      # For display
    "commit_hash": "abc123",
    "diff_type": "modified",
    "file_path": "src/auth.py"
}
```

**Time filtering:** Check `commit_timestamp` in payload (no SQL query)
**Display:** Use commit_message, author_name from payload (no SQL query)
**Entry point:** HNSW index → semantic search → in-memory payload filtering

**NO database needed.**

### Payload Changes (Already Done in Story 1)

Verify payload structure matches:
```python
{
    "type": "commit_diff",
    "commit_hash": "abc123",
    "file_path": "src/module.py",
    "diff_type": "modified",  # or added/deleted/renamed/binary
    "chunk_index": 0,
    "project_id": "project-name",
    "line_start": 1,
    "line_end": 150,
}
```

## Acceptance Criteria

### Query Behavior
- [ ] Temporal queries return ONLY changed files (no `[NO CHANGES IN CHUNK]`)
- [ ] Results show diff-type markers: `[ADDED]`, `[DELETED]`, `[MODIFIED]`, `[RENAMED]`, `[BINARY]`
- [ ] Time range filtering works correctly
- [ ] Language and path filters work correctly

### SQLite Complete Removal (NEW)
- [ ] No `import sqlite3` in temporal_search_service.py
- [ ] No `self.commits_db_path` initialization
- [ ] No `sqlite3.connect()` calls anywhere
- [ ] No SQL queries (commits table, trees table)
- [ ] `_filter_by_time_range()` uses JSON payloads only (no SQLite)
- [ ] `_fetch_commit_file_changes()` method deleted
- [ ] `_is_new_file()` method deleted
- [ ] `_generate_chunk_diff()` method deleted
- [ ] 13 SQLite-dependent test files deleted

### Code Cleanup
- [ ] `filter_timeline_changes()` method deleted
- [ ] `--show-unchanged` flag removed from CLI
- [ ] No references to `blob_hash` in filtering logic
- [ ] `[NO CHANGES IN CHUNK]` display code removed
- [ ] All blob-based helper methods removed

### Performance
- [ ] Query speed improved (in-memory filtering, no SQL queries)
- [ ] No database I/O overhead
- [ ] Simpler filtering logic (just check payload timestamps)

## Manual Test Plan

### Setup: Use Indexed Test Repository from Story 1

```bash
cd /tmp/cidx-test-repo

# Verify temporal index exists from Story 1
test -d .code-indexer/index/code-indexer-temporal && echo "PASS: Temporal index exists"
```

### Test Case 0: Verify NO SQLite Usage (NEW)

**Step 1**: Verify no SQLite imports in query service
```bash
grep -n "import sqlite3" ~/Dev/code-indexer/src/code_indexer/services/temporal/temporal_search_service.py
```

**Expected**: No output (no sqlite3 imports)

**Step 2**: Verify no commits.db file exists
```bash
test ! -f .code-indexer/index/temporal/commits.db && echo "PASS: No commits database"
ls .code-indexer/index/temporal/*.db 2>/dev/null || echo "PASS: No SQLite files in temporal/"
```

**Expected**:
- "PASS: No commits database"
- "PASS: No SQLite files in temporal/"

**Step 3**: Verify _filter_by_time_range() doesn't use SQLite
```bash
grep -A 20 "def _filter_by_time_range" ~/Dev/code-indexer/src/code_indexer/services/temporal/temporal_search_service.py | grep "sqlite3\|commits_db_path\|conn.execute"
```

**Expected**: No output (no SQLite operations)

**Step 4**: Verify temporal queries work WITHOUT commits.db
```bash
# Ensure commits.db doesn't exist
rm -f .code-indexer/index/temporal/commits.db

# Query should still work (using JSON payloads only)
cidx query "authentication" --time-range 2025-11-01..2025-11-01 --limit 5
```

**Expected**: Query returns results successfully (no "database not found" errors)

### Test Case 1: Query Returns Only Changed Files

**Step 1**: Query for Nov 1 changes
```bash
cidx query "authentication" --time-range 2025-11-01..2025-11-01 --limit 10
```

**Expected**:
- Returns ONLY files changed on Nov 1 (commits 1, 2, 3)
- Shows `src/auth.py` (added in commit 1)
- Shows `src/api.py` (added in commit 2)
- Shows `src/config.py` (added in commit 3)
- Does NOT show files from other dates

**Step 2**: Verify no [NO CHANGES] markers
```bash
cidx query "authentication" --time-range 2025-11-01..2025-11-01 | grep "NO CHANGES"
```

**Expected**: No output (grep finds nothing)

### Test Case 2: Diff-Type Markers Displayed

**Step 1**: Query showing added files
```bash
cidx query "authentication" --time-range 2025-11-01..2025-11-01 --limit 5
```

**Expected**: Shows `[ADDED]` marker for src/auth.py (new file in commit 1)

**Step 2**: Query showing modified files
```bash
cidx query "JWT token" --time-range 2025-11-02..2025-11-02 --limit 5
```

**Expected**: Shows `[MODIFIED]` marker for src/auth.py (refactored in commit 6)

**Step 3**: Query showing deleted files
```bash
cidx query "database connection" --time-range 2025-11-03..2025-11-03 --limit 5
```

**Expected**: Shows `[DELETED]` marker for src/database.py (deleted in commit 8)

**Step 4**: Query showing renamed files
```bash
cidx query "async database" --time-range 2025-11-03..2025-11-03 --limit 5
```

**Expected**: Shows `[RENAMED]` marker for db_new.py → database.py (commit 9)

**Step 5**: Query showing binary files
```bash
cidx query "architecture" --time-range 2025-11-04..2025-11-04 --limit 5
```

**Expected**: Shows `[BINARY]` marker for docs/architecture.png (commit 11)

### Test Case 3: Time Range Filtering Accurate

**Step 1**: Query Nov 1 only
```bash
cidx query "project" --time-range 2025-11-01..2025-11-01
```

**Expected**:
- Returns commits 1, 2, 3 ONLY
- Does NOT return commits from Nov 2, 3, 4

**Step 2**: Query Nov 2 only
```bash
cidx query "authentication" --time-range 2025-11-02..2025-11-02
```

**Expected**:
- Returns commits 4, 5, 6 ONLY
- Shows auth.py refactor (commit 6) with [MODIFIED]

**Step 3**: Query Nov 1-2 range
```bash
cidx query "database" --time-range 2025-11-01..2025-11-02
```

**Expected**:
- Returns commits 1-6
- Shows database.py creation (commit 1) and modifications (commits 2, 3)

**Step 4**: Query all November
```bash
cidx query "API" --time-range 2025-11-01..2025-11-04
```

**Expected**:
- Returns commits 1-12
- Shows complete API evolution

### Test Case 4: Language and Path Filters Work

**Step 1**: Python files only
```bash
cidx query "authentication" --time-range 2025-11-01..2025-11-04 --language python
```

**Expected**:
- Returns only .py files
- Does NOT return .md files

**Step 2**: Exclude test files
```bash
cidx query "database" --time-range 2025-11-01..2025-11-04 --exclude-path "tests/*"
```

**Expected**:
- Returns src/database.py changes
- Does NOT return tests/test_database.py

**Step 3**: Specific directory only
```bash
cidx query "authentication" --time-range 2025-11-01..2025-11-04 --path-filter "src/*.py"
```

**Expected**:
- Returns src/auth.py, src/api.py
- Does NOT return tests/test_auth.py

### Test Case 5: No Unchanged Files Noise

**Step 1**: Query for specific term on Nov 3
```bash
cidx query "qdrant connection" --time-range 2025-11-03..2025-11-03
```

**Expected**:
- If no file containing "qdrant connection" was changed on Nov 3, returns 0 results
- Does NOT return files that mention "qdrant connection" but weren't changed

**Step 2**: Verify focused results
```bash
cidx query "authentication" --time-range 2025-11-02..2025-11-02 --limit 10
```

**Expected**:
- Returns ONLY auth.py refactor (commit 6)
- Does NOT return auth.py from commit 1 (different date)
- All results are from Nov 2

### Test Case 6: Performance Verification

**Step 1**: Time a query
```bash
time cidx query "database" --time-range 2025-11-01..2025-11-04 --limit 20
```

**Expected**:
- Query completes in <2 seconds
- Performance info shows: "semantic: XXXms, temporal filter: XXms"
- Temporal filter should be fast (no complex blob tracking)

**Step 2**: Check query timing breakdown
```bash
cidx query "API" --time-range 2025-11-01..2025-11-04
```

**Expected**: Output shows timing like:
```
⚡ Search completed in 1234ms (semantic: 800ms, temporal filter: 434ms)
```

### Test Case 7: Verify --show-unchanged Flag Removed

**Step 1**: Try using removed flag
```bash
cidx query "test" --time-range 2025-11-01..2025-11-04 --show-unchanged
```

**Expected**: Error: "Unknown option: --show-unchanged"

### Test Case 8: Edge Cases

**Step 1**: Empty result set
```bash
cidx query "nonexistent_term_xyz" --time-range 2025-11-01..2025-11-04
```

**Expected**:
- "Found 0 results"
- No errors or crashes

**Step 2**: Single day with no changes
```bash
# Pick a date with no commits
cidx query "anything" --time-range 2025-10-31..2025-10-31
```

**Expected**:
- "Found 0 results"
- "Temporal index not found" if no commits in range

**Step 3**: All commits in range
```bash
cidx query "project" --time-range-all
```

**Expected**:
- Returns all commits (1-12)
- Shows complete project evolution

## Implementation Notes

### Query Simplification

The query logic becomes much simpler:

**Old approach** (lines 524-641):
- Join commits and trees tables
- Track blob_hash appearances across commits
- Calculate first_seen/last_seen per blob
- Compare blob hashes to detect changes
- Filter out unchanged blobs

**New approach** (simplified):
- Query only commits table
- Check if result's commit_hash is in date range
- Return all matches (they're all changes by definition)

### Display Color Scheme

```python
DIFF_TYPE_COLORS = {
    "added": "green bold",      # New files
    "deleted": "red bold",       # Deleted files
    "modified": "yellow bold",   # Changed files
    "renamed": "cyan bold",      # Moved files
    "binary": "magenta",         # Binary files
}
```

### Error Handling

If payload missing `diff_type` field:
- Default to `"unknown"` and show `[UNKNOWN]` marker
- Log warning for debugging

## Success Criteria

- [ ] All manual tests pass (including Test Case 0 - SQLite verification)
- [ ] Query results show diff-type markers
- [ ] No `[NO CHANGES IN CHUNK]` markers displayed
- [ ] `filter_timeline_changes()` method deleted
- [ ] `--show-unchanged` flag removed
- [ ] Time range filtering accurate (using JSON payloads, no SQLite)
- [ ] Language/path filters work correctly
- [ ] Performance improved vs old approach
- [ ] 13 SQLite-dependent test files deleted
- [ ] No SQLite imports or queries remain in temporal_search_service.py
- [ ] Fast-automation tests pass

## Dependencies

- **Story 1**: Must be completed first (indexing must use diffs)
- **Story 0**: Test repository must exist

## Estimated Effort

**8-12 hours**: Complete SQLite removal, query service rewrite, test deletion, validation

(Updated from 4-6 hours due to complete SQLite elimination scope)

## Notes

**CRITICAL SCOPE EXPANSION**: Story 2 now includes complete SQLite removal from query service (aligned with Story 1 decision).

**Breaking Change**: This completes the diff-based rewrite. After this story:
- Temporal queries return ONLY files that changed in time range
- No SQLite databases used (indexing or querying)
- All metadata from JSON payloads
- 13 old test files deleted (blob/SQLite-based tests)

**Acceptance Criteria Count**: **21 total** (was 12, expanded to include 9 SQLite removal criteria)

**User Benefit**:
- Laser-focused results (actual changes only)
- Faster queries (no database I/O)
- Simpler architecture (no SQL, no schema)

**Migration**: Users must re-index with Story 1 (`cidx index --index-commits`). Old commits.db files can be manually deleted.
