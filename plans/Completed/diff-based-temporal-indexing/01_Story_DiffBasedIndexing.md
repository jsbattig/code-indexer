# Story 1: Rewrite Temporal Indexing to Index Diffs Only

## Context

Current temporal indexing uses `git ls-tree` to index entire file blobs for each commit, causing files that didn't change to appear in temporal queries marked as `[NO CHANGES IN CHUNK]`. This creates massive noise and defeats the purpose of temporal queries.

**Root Cause**: Line 240 in `temporal_indexer.py`:
```python
all_blobs = self.blob_scanner.get_blobs_for_commit(commit.hash)
```

This returns ALL files in the commit tree (entire codebase state), not just changed files.

## User Story

**As a developer**, I want temporal queries to return ONLY files that actually changed in the queried time range, **so that** I can see what code was added/modified/deleted without noise from unchanged files.

## Requirements

### Core Behavior Change

**Old Behavior**:
```bash
cidx query "qdrant connection" --time-range 2025-11-03..2025-11-03
# Returns: src/code_indexer/services/qdrant.py [NO CHANGES IN CHUNK]
#   (file exists in commit but wasn't changed)
```

**New Behavior**:
```bash
cidx query "qdrant connection" --time-range 2025-11-03..2025-11-03
# Returns: ONLY files where "qdrant connection" code was ADDED/MODIFIED/DELETED
#   (if qdrant.py didn't change on Nov 3, it won't appear)
```

### Diff-Based Indexing Strategy

For each commit, index the **diff** (what changed):

1. **New Files**: Full content as additions
   - Use `git show --diff-filter=A <commit> <file>` to get full content
   - Mark as `diff_type: "added"`

2. **Deleted Files**: Full content as deletions
   - Use `git show <commit>^:<file>` to get content from parent
   - Mark as `diff_type: "deleted"`

3. **Modified Files**: Only the diff (+ and - lines)
   - Use `git show <commit> -- <file>` to get unified diff
   - Mark as `diff_type: "modified"`
   - Include context lines for readability (git default is 3 lines)

4. **Renamed Files**: Generate "fake file" showing move
   - Create text: "File renamed from old_path to new_path"
   - Include diff if content also changed
   - Mark as `diff_type: "renamed"`

5. **Binary Files**: Generate metadata-only "fake file"
   - Create text: "Binary file added/modified/deleted: <filename>"
   - Mark as `diff_type: "binary"`

### Files to DELETE

Remove these files entirely (no fallback, no migration):

1. **`src/code_indexer/services/temporal/temporal_blob_scanner.py`**
   - Uses `git ls-tree` (wrong approach)
   - Replaced by diff scanner

2. **`src/code_indexer/services/temporal/blob_registry.py`**
   - Tracks blob deduplication
   - No longer needed (no blob deduplication in diff approach)

3. **`src/code_indexer/services/temporal/git_blob_reader.py`**
   - Reads full blob content
   - No longer needed (read diffs instead)

### SQLite Removal

**CRITICAL**: Remove ALL SQLite usage from temporal indexing. Store metadata in JSON payloads instead.

**Files to modify**:
1. **`src/code_indexer/services/temporal/temporal_indexer.py`**
   - Remove `import sqlite3`
   - Remove `self.commits_db_path` initialization
   - Remove `_initialize_commits_database()` method entirely
   - Remove `_store_commit_tree()` method entirely (lines ~400-450)
   - Remove `_store_commit_branch_metadata()` method entirely (lines ~373-419)
   - NO MORE SQLite database files created

**Why SQLite is obsolete**:
- Old approach: Query `trees` table to map blob_hash → commits → time filtering
- New approach: Each diff is standalone with commit metadata in JSON payload
- Entry point: HNSW index (filters which JSON files to load)
- Time filtering: Check `commit_timestamp` field in payload (no SQL query needed)

**Benefits**:
- Simpler architecture (no database schema, no migrations)
- Faster queries (no SQL joins, just JSON payload filtering)
- Same data access pattern as regular indexing
- Git is the source of truth for branch/commit metadata

### Files to CREATE

1. **`src/code_indexer/services/temporal/temporal_diff_scanner.py`**

```python
"""TemporalDiffScanner - Gets file changes (diffs) per commit."""

from dataclasses import dataclass
from pathlib import Path
from typing import List
import subprocess

@dataclass
class DiffInfo:
    """Information about a file change in a commit."""
    file_path: str
    diff_type: str  # "added", "deleted", "modified", "renamed", "binary"
    commit_hash: str
    diff_content: str  # The actual diff text to index
    old_path: str = ""  # For renames only

class TemporalDiffScanner:
    """Discovers file changes (diffs) in git commit history."""

    def __init__(self, codebase_dir: Path):
        self.codebase_dir = Path(codebase_dir)

    def get_diffs_for_commit(self, commit_hash: str) -> List[DiffInfo]:
        """Get all file changes in a commit as diffs.

        Returns list of DiffInfo with diff_content ready for chunking/embedding.
        """
        # Step 1: Get list of changed files with status
        # git show --name-status --format="" <commit>

        # Step 2: For each file, generate appropriate diff content

        # Step 3: Return list of DiffInfo objects
        pass
```

### Files to MODIFY

1. **`src/code_indexer/services/temporal/temporal_indexer.py`**

**Changes**:
- Remove import: `from .temporal_blob_scanner import TemporalBlobScanner`
- Remove import: `from .blob_registry import BlobRegistry`
- Remove import: `from .git_blob_reader import GitBlobReader`
- Add import: `from .temporal_diff_scanner import TemporalDiffScanner`

- Line 81: Replace `self.blob_scanner = TemporalBlobScanner(self.codebase_dir)`
  - With: `self.diff_scanner = TemporalDiffScanner(self.codebase_dir)`

- Line 83: Remove `self.blob_registry = BlobRegistry(self.temporal_dir / "blob_registry.db")`

- Line 82: Remove `self.blob_reader = GitBlobReader(self.codebase_dir)`

- Lines 238-323: Replace entire commit processing loop
  ```python
  # OLD (WRONG):
  all_blobs = self.blob_scanner.get_blobs_for_commit(commit.hash)
  new_blobs = [b for b in all_blobs if not self.blob_registry.has_blob(b.blob_hash)]
  for blob_info in new_blobs:
      content = self.blob_reader.read_blob_content(blob_info.blob_hash)
      chunks = self.chunker.chunk_text(content, Path(blob_info.file_path))
      # ... embedding and storage

  # NEW (CORRECT):
  diffs = self.diff_scanner.get_diffs_for_commit(commit.hash)
  for diff_info in diffs:
      # diff_info.diff_content is the diff text, ready to chunk
      chunks = self.chunker.chunk_text(diff_info.diff_content, Path(diff_info.file_path))
      # ... embedding and storage with updated payload
  ```

- Lines 284-294: Update payload structure with commit metadata
  ```python
  payload = {
      "type": "commit_diff",  # Changed from "file_chunk"
      "commit_hash": commit.hash,
      "commit_timestamp": commit.timestamp,  # NEW: For time filtering (no SQLite needed)
      "commit_date": commit.date_str,  # NEW: Human-readable date (YYYY-MM-DD)
      "commit_message": commit.message,  # NEW: For display
      "author_name": commit.author_name,  # NEW: For display
      "file_path": diff_info.file_path,
      "diff_type": diff_info.diff_type,  # NEW: added/deleted/modified/renamed/binary
      "chunk_index": j,
      "project_id": project_id,
      "line_start": chunk.get("line_start", 0),
      "line_end": chunk.get("line_end", 0),
      # NO blob_hash - not relevant for diffs
      # NO SQL database - all metadata in payload
  }
  ```

- Remove all blob registry operations (lines 304-306)
- Remove all SQLite database operations (_store_commit_tree, _store_commit_branch_metadata)

2. **`src/code_indexer/services/temporal/models.py`**

```python
# Remove BlobInfo dataclass
# Add DiffInfo dataclass (or import from temporal_diff_scanner.py)
```

### Parallel Processing Architecture

**CRITICAL**: Use queue-based parallel processing (same pattern as file indexing in `high_throughput_processor.py`).

**Architecture**:
1. **Phase 1**: Fast commit discovery (git log --all ~9ms for 366 commits)
   ```python
   commits = self._get_commit_history(all_branches, max_commits, since_date)
   total_commits = len(commits)  # Know upfront for progress
   ```

2. **Phase 2**: Preload queue with ALL commits
   ```python
   commit_queue = Queue()
   for commit in commits:
       commit_queue.put(commit)
   ```

3. **Phase 3**: Spawn N diff processor threads (configurable, default 8-10)
   ```python
   def diff_processor_worker(commit_queue, vector_manager, progress_lock, completed_commits):
       while True:
           try:
               commit = commit_queue.get_nowait()
           except Empty:
               break

           # Get changed files for THIS commit (sequential within thread)
           changed_files = git_show_name_status(commit.hash)  # ~10ms

           # Extract diffs and submit for vectorization (sequential)
           for file_path, change_type in changed_files:
               diff_content = extract_diff(commit.hash, file_path, change_type)
               chunks = chunk_text(diff_content)
               vector_manager.submit_batch_task(chunks)  # Downstream parallel

           # Update progress (thread-safe)
           with progress_lock:
               completed_commits[0] += 1
               report_progress(completed_commits[0], total_commits)

           commit_queue.task_done()

   with ThreadPoolExecutor(max_workers=thread_count) as executor:
       futures = [executor.submit(diff_processor_worker, ...) for _ in range(thread_count)]
       for future in as_completed(futures):
           future.result()
   ```

**Progress Reporting** (same model as file indexing):
```python
# Format: "{completed}/{total} commits ({pct}%) | {rate} commits/s | {threads} threads | {commit_hash} - {file}"
info = f"{completed}/{total} commits ({100*completed//total}%) | {commits_per_sec:.1f} commits/s | {thread_count} threads | 📝 {commit_hash[:8]} - {file_path}"
```

**Key Points**:
- Commits processed OUT OF ORDER (multiple threads working in parallel)
- Progress shows COUNT not chronological order (145/366 commits)
- Vector storage doesn't care about commit order
- No SQLite = no concurrent write issues
- Diff extraction within commit is SEQUENTIAL (parallelism comes from multi-commit processing)

## Acceptance Criteria

### Indexing Behavior
- [ ] `cidx index --index-commits` uses `git show` to get diffs, not `git ls-tree`
- [ ] Only changed files are indexed per commit
- [ ] New files: Full content indexed as additions
- [ ] Deleted files: Full content indexed as deletions
- [ ] Modified files: Only diff (+/-) lines indexed
- [ ] Renamed files: Metadata file created showing rename
- [ ] Binary files: Metadata file created (not actual binary content)

### Storage Reduction
- [ ] Vector count reduced by ~90-95% vs old approach
- [ ] For test repository (12 commits), expect ~50-100 vectors instead of 500+
- [ ] No `blob_registry.db` file created
- [ ] No `commits.db` file created (SQLite completely removed)
- [ ] All commit metadata stored in JSON payloads

### Parallel Processing
- [ ] Commits preloaded into queue upfront (git log ~9ms for 366 commits)
- [ ] Configurable thread count for diff processing (default 8-10)
- [ ] Progress reporting shows: "{completed}/{total} commits ({pct}%) | {rate} commits/s | {threads} threads"
- [ ] Commits processed out of order (parallel workers)
- [ ] No SQLite concurrent write issues (no database)

### Files Deleted
- [ ] `temporal_blob_scanner.py` removed
- [ ] `blob_registry.py` removed
- [ ] `git_blob_reader.py` removed
- [ ] No references to these files remain in codebase

### Files Created
- [ ] `temporal_diff_scanner.py` exists
- [ ] Implements `get_diffs_for_commit()` method
- [ ] Returns `List[DiffInfo]` with diff_content ready for chunking

### Payload Structure
- [ ] `type` field: `"commit_diff"` (not `"file_chunk"`)
- [ ] `diff_type` field: one of `"added"`, `"deleted"`, `"modified"`, `"renamed"`, `"binary"`
- [ ] `commit_hash` field: commit where change occurred
- [ ] `commit_timestamp` field: Unix timestamp for time filtering (NO SQLite query needed)
- [ ] `commit_date` field: Human-readable date (YYYY-MM-DD)
- [ ] `commit_message` field: For display in query results
- [ ] `author_name` field: For display in query results
- [ ] `file_path` field: path of changed file
- [ ] NO `blob_hash` field (not relevant for diffs)
- [ ] NO SQL database (all metadata in payload)

### No Artificial Limits
- [ ] Large diffs (500+ lines) are indexed without truncation
- [ ] No max file size limits
- [ ] No artificial sampling or skipping

## Manual Test Plan

### Setup: Use Story 0 Test Repository

```bash
# Test repository from Story 0
cd /tmp/cidx-test-repo
git log --oneline  # Verify 12 commits exist
```

### Test Case 1: Index Test Repository

**Step 1**: Initialize cidx in test repository
```bash
cd /tmp/cidx-test-repo
rm -rf .code-indexer
cidx init
```

**Expected**: `.code-indexer/` directory created

**Step 2**: Run temporal indexing
```bash
cidx index --index-commits --all-branches
```

**Expected**:
- Progress bar shows commit processing
- Output: "Total commits indexed: 12"
- Output: "Unique blobs processed: ~30-50" (way less than old approach)

**Step 3**: Verify temporal collection
```bash
find .code-indexer/index/code-indexer-temporal -name "*.json" -type f ! -name "collection_meta.json" | wc -l
```

**Expected**: ~50-100 vector files (not 500+ like old approach)

**Step 4**: Verify no SQLite databases
```bash
test ! -f .code-indexer/index/temporal/blob_registry.db && echo "PASS: No blob registry"
test ! -f .code-indexer/index/temporal/commits.db && echo "PASS: No commits database"
ls .code-indexer/index/temporal/*.db 2>/dev/null || echo "PASS: No SQLite files"
```

**Expected**:
- "PASS: No blob registry"
- "PASS: No commits database"
- "PASS: No SQLite files"

**Step 5**: Verify commit metadata in JSON payloads
```bash
# Pick a random vector JSON file and check payload structure
find .code-indexer/index/code-indexer-temporal -name "*.json" -type f ! -name "collection_meta.json" | head -1 | xargs cat | jq '.payload | keys'
```

**Expected**: Shows fields like `commit_hash`, `commit_timestamp`, `commit_date`, `commit_message`, `author_name`, `diff_type`, `file_path` (NO `blob_hash`)

### Test Case 2: Verify Diff Content Indexed

**Step 1**: Check specific commit indexing (Commit 6 - auth refactor)
```bash
# Get commit 6 hash
COMMIT_6=$(git log --oneline | grep "Refactor authentication" | awk '{print $1}')

# Check what was indexed for this commit (from JSON payloads, not SQLite)
find .code-indexer/index/code-indexer-temporal -name "*.json" -type f ! -name "collection_meta.json" -exec grep -l "$COMMIT_6" {} \; | head -1 | xargs cat | jq '.payload.commit_message'
```

**Expected**: "Refactor authentication"

**Step 2**: Verify only auth.py was indexed (not all files)
```bash
# Check actual file changes in commit 6
git show --name-only $COMMIT_6

# Should show ONLY: src/auth.py
```

**Expected**: Only src/auth.py in output

**Step 3**: Verify diff content format
```bash
# Get actual diff from commit
git show $COMMIT_6 src/auth.py | head -50
```

**Expected**: Shows +/- lines with context (unified diff format)

### Test Case 3: Verify Deletion Handling (Commit 8)

**Step 1**: Get deletion commit
```bash
COMMIT_8=$(git log --oneline | grep "Delete old database" | awk '{print $1}')
```

**Step 2**: Verify file was deleted
```bash
git show --name-status $COMMIT_8 | grep "database.py"
```

**Expected**: `D src/database.py`

**Step 3**: Check indexed content
```bash
# Deletion should be indexed as full content removal
# Verify in temporal collection that database.py deletion exists
```

**Expected**: Deletion indexed with diff_type="deleted"

### Test Case 4: Verify Rename Handling (Commit 9)

**Step 1**: Get rename commit
```bash
COMMIT_9=$(git log --oneline | grep "Rename db_new" | awk '{print $1}')
```

**Step 2**: Verify rename detection
```bash
git show --name-status $COMMIT_9
```

**Expected**: `R100 src/db_new.py src/database.py`

**Step 3**: Check indexed content
```bash
# Should have metadata file showing rename
```

**Expected**: Rename indexed with diff_type="renamed", old_path set

### Test Case 5: Verify Binary File Handling (Commit 11)

**Step 1**: Get binary file commit
```bash
COMMIT_11=$(git log --oneline | grep "Binary file" | awk '{print $1}')
```

**Step 2**: Verify binary detection
```bash
git show --stat $COMMIT_11 | grep "architecture.png"
```

**Expected**: `Bin 0 -> XXX bytes`

**Step 3**: Check indexed content
```bash
# Should have metadata file, not actual binary content
```

**Expected**: Binary file indexed with diff_type="binary"

### Test Case 6: Verify Large Diff Handling (Commit 12)

**Step 1**: Get large refactoring commit
```bash
COMMIT_12=$(git log --oneline | grep "Large refactoring" | awk '{print $1}')
```

**Step 2**: Count diff lines
```bash
git show $COMMIT_12 --stat
```

**Expected**: Shows 500+ lines changed in api.py

**Step 3**: Verify no truncation
```bash
# Check that full diff was indexed (all 500+ lines)
```

**Expected**: Complete diff indexed, no artificial limits

### Test Case 7: Verify Storage Reduction

**Step 1**: Count total vectors
```bash
find .code-indexer/index/code-indexer-temporal -name "*.json" -type f ! -name "collection_meta.json" | wc -l
```

**Expected**: ~50-100 vectors (not 500+ like old blob-based approach)

**Step 2**: Check collection metadata
```bash
cat .code-indexer/index/code-indexer-temporal/collection_meta.json | grep vector_count
```

**Expected**: Vector count significantly lower than old approach

## Implementation Notes

### Git Commands for Diff Extraction

**Get list of changed files**:
```bash
git show --name-status --format="" <commit>
# Output: M src/auth.py, A src/config.py, D src/old.py
```

**Get diff for modified file**:
```bash
git show <commit> -- <file>
# Output: Unified diff with +/- lines
```

**Get full content of new file**:
```bash
git show <commit>:<file>
# Output: Full file content (treat as "all additions")
```

**Get full content of deleted file**:
```bash
git show <commit>^:<file>
# Output: Full file content from parent (treat as "all deletions")
```

**Detect renames**:
```bash
git show --name-status --find-renames <commit>
# Output: R100 old_path new_path (100 = no content change)
```

### Diff Content Format

For modified files, the diff_content will be:
```
@@ -10,5 +10,8 @@ def login(username, password):
-    if username == "admin" and password == "admin":
-        return True
+    token = create_token(username)
+    if token:
+        return token
     return False
```

This is what gets chunked and embedded. Semantic search on "create_token" will match this diff.

### Performance Considerations

**Old approach**: 366 commits × 50 files/commit × 10 chunks/file = ~183,000 vectors
**New approach**: 366 commits × 5 changed files/commit × 10 chunks/file = ~18,300 vectors

**90% reduction** in vector count.

## Success Criteria

- [ ] Story 0 test repository successfully indexed
- [ ] Only changed files appear in temporal collection
- [ ] Vector count reduced by 90%+
- [ ] All 3 deleted files removed from codebase
- [ ] Diff scanner created and working
- [ ] Temporal indexer modified to use diff scanner
- [ ] All manual tests pass
- [ ] Fast-automation tests pass (update as needed)

## Dependencies

- **Story 0**: Test repository must exist
- **Breaking Change**: This completely rewrites temporal indexing, no backward compatibility

## Estimated Effort

**8-12 hours**: Core rewrite, testing, validation

## Notes

**CRITICAL**: This is a complete rewrite. We're deleting the old approach entirely, no fallback, no migration. Users will need to re-run `cidx index --index-commits` to rebuild temporal index.

**Next Story**: Story 2 will update query service to work with diff-based payloads.
