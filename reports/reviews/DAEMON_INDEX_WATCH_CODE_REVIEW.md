# Code Review: Daemon Index and Watch Implementation

**Reviewer**: Claude Code (code-reviewer agent)
**Date**: 2025-10-30
**Branch**: feature/cidx-daemonization
**Commits Reviewed**: 30c62b7, 62a1dc3, fcc6cf4
**Files Modified**:
- `src/code_indexer/daemon/service.py` (902 lines)
- `src/code_indexer/cli_daemon_delegation.py` (944 lines)

---

## Executive Summary

**VERDICT**: ❌ **REJECT** - Critical thread safety issues and MESSI rule violations

The implementation successfully solves the RPC timeout problem by moving indexing to background threads, but introduces **HIGH-severity race conditions** and violates **Anti-File-Bloat** rules. The code requires immediate fixes before merge.

**Critical Issues Found**: 6 (1 HIGH, 3 MEDIUM, 2 CRITICAL VIOLATIONS)
**Warnings**: 3 (Anti-Duplication, KISS)
**Strengths**: Good RPC proxy handling, proper cache invalidation strategy, comprehensive error handling

---

## CRITICAL ISSUES (Must Fix Before Merge)

### 1. HIGH SEVERITY: Race Condition in Query/Indexing Cache Access

**Location**: `daemon/service.py:87-95, 252-255`
**Risk Level**: HIGH - Data corruption, NullPointerException crashes

**Problem**:
```python
# Query thread (exposed_query)
def exposed_query(self, project_path, query, limit, **kwargs):
    self._ensure_cache_loaded(project_path)  # Acquires cache_lock, releases

    with self.cache_lock:                     # Re-acquires lock
        if self.cache_entry:
            self.cache_entry.update_access()  # Releases lock

    # 🚨 RACE WINDOW: cache_entry can be invalidated here
    results = self._execute_semantic_search(...)  # Uses cache_entry without lock!
    return results

# Indexing thread (_run_indexing_background)
def _run_indexing_background(self, ...):
    # ... indexing completes ...
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry = None  # 💥 Query thread may be using this!
```

**Attack Scenario**:
1. Query thread calls `exposed_query()`, loads cache, releases lock
2. Query thread proceeds to `_execute_semantic_search()`
3. Indexing thread completes, acquires lock, sets `cache_entry = None`
4. Query thread's `_execute_semantic_search()` accesses `self.cache_entry` → NoneType error
5. **Result**: Query crashes with AttributeError

**Impact**: Production queries will randomly crash during/after indexing operations.

**Fix Required**:
```python
def exposed_query(self, project_path, query, limit, **kwargs):
    self._ensure_cache_loaded(project_path)

    # Hold cache_lock during ENTIRE query execution
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry.update_access()

        # Execute search while holding lock to prevent invalidation
        results = self._execute_semantic_search(project_path, query, limit, **kwargs)

    return results
```

**Alternative**: Use Read-Write lock (RWLock) pattern to allow concurrent queries but block on invalidation.

---

### 2. MEDIUM SEVERITY: TOCTOU Race in exposed_index

**Location**: `daemon/service.py:174-196`
**Risk Level**: MEDIUM - Multiple indexing threads, resource waste

**Problem**:
```python
def exposed_index(self, project_path, callback, **kwargs):
    with self.indexing_lock_internal:
        if self.indexing_thread and self.indexing_thread.is_alive():  # Check
            return {"status": "already_running"}

        # 🚨 Lock released here, but cache invalidation uses different lock
        with self.cache_lock:  # Different lock!
            if self.cache_entry:
                self.cache_entry = None

        # 🚨 Second call could reach here before thread is assigned
        self.indexing_thread = threading.Thread(...)  # Use
        self.indexing_thread.start()
```

**Attack Scenario**:
1. Thread A: Checks `indexing_thread.is_alive()` → False, proceeds
2. Thread A: Releases `indexing_lock_internal`, acquires `cache_lock`
3. Thread B: Checks `indexing_thread.is_alive()` → False (A hasn't assigned yet)
4. Thread A: Creates thread, assigns `self.indexing_thread`, starts
5. Thread B: Creates thread, **overwrites** `self.indexing_thread`, starts
6. **Result**: Two indexing threads running, first thread orphaned (no way to track)

**Impact**: Wasted resources, duplicate indexing work, unpredictable behavior.

**Fix Required**:
```python
def exposed_index(self, project_path, callback, **kwargs):
    with self.indexing_lock_internal:
        if self.indexing_thread and self.indexing_thread.is_alive():
            return {"status": "already_running"}

        # Invalidate cache under SAME lock (nested locking is safe with Lock)
        # Actually, avoid nested locks - move cache invalidation AFTER thread creation

        # Create and start thread atomically under lock
        self.indexing_project_path = project_path
        self.indexing_thread = threading.Thread(
            target=self._run_indexing_background,
            args=(project_path, callback, kwargs),
            daemon=True,
            name="IndexingThread"
        )
        self.indexing_thread.start()

    # Invalidate cache AFTER thread is safely started
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry = None

    return {"status": "started", ...}
```

---

### 3. MEDIUM SEVERITY: Watch State Unsynchronized

**Location**: `daemon/service.py:287-289, 372-373`
**Risk Level**: MEDIUM - Duplicate watch threads, state corruption

**Problem**:
```python
# No lock protection for watch state
def exposed_watch_start(self, project_path, callback, **kwargs):
    # 🚨 Race: Multiple threads can pass this check simultaneously
    if self.watch_handler and self.watch_thread and self.watch_thread.is_alive():
        return {"status": "error", "message": "Watch already running"}

    # ... create watch_handler ...
    self.watch_handler = GitAwareWatchHandler(...)  # 🚨 No lock
    self.watch_handler.start_watching()
    self.watch_thread = self.watch_handler.processing_thread  # 🚨 No lock

def exposed_watch_stop(self, project_path):
    if not self.watch_handler:  # 🚨 Race: could be set to None by another thread
        return {"status": "error", "message": "No watch running"}

    self.watch_handler.stop_watching()
```

**Impact**: Multiple watch threads, state inconsistency, failed stop operations.

**Fix Required**:
```python
def __init__(self):
    # Add watch lock
    self.watch_lock: threading.Lock = threading.Lock()

def exposed_watch_start(self, project_path, callback, **kwargs):
    with self.watch_lock:
        if self.watch_handler and self.watch_thread and self.watch_thread.is_alive():
            return {"status": "error", "message": "Watch already running"}

        # ... create handler ...
        self.watch_handler = handler
        self.watch_thread = handler.processing_thread

    return {"status": "success"}

def exposed_watch_stop(self, project_path):
    with self.watch_lock:
        if not self.watch_handler:
            return {"status": "error"}

        handler = self.watch_handler
        self.watch_handler = None
        self.watch_thread = None

    # Stop AFTER releasing lock to avoid holding lock during blocking operation
    handler.stop_watching()
    return {"status": "success"}
```

---

### 4. CRITICAL: Anti-File-Bloat Violation (MESSI Rule 6)

**Location**: `cli_daemon_delegation.py` (944 lines), `daemon/service.py` (902 lines)
**Rule**: Modules must be ≤500 lines
**Violation**: Both files significantly exceed limit

**Impact**: Code maintainability, reviewability, testability degraded.

**Fix Required**:

**cli_daemon_delegation.py** → Split into:
```
cli_daemon_delegation/
  ├── __init__.py          # Public API
  ├── query.py             # _query_via_daemon, _query_standalone
  ├── storage.py           # _clean_via_daemon, _status_via_daemon, etc.
  ├── indexing.py          # _index_via_daemon, _index_standalone
  ├── watch.py             # _watch_via_daemon, _watch_standalone
  └── common.py            # _connect_to_daemon, _find_config_file, etc.
```

**daemon/service.py** → Split into:
```
daemon/
  ├── service.py           # Main CIDXDaemonService (orchestration only)
  ├── query_handler.py     # exposed_query*, _execute_semantic_search
  ├── indexing_handler.py  # exposed_index, _run_indexing_background
  ├── watch_handler.py     # exposed_watch_*, watch state management
  ├── storage_handler.py   # exposed_clean*, exposed_status
  └── cache_loader.py      # _ensure_cache_loaded, _load_*_indexes
```

**Timeline**: Must complete before merge. This is technical debt that will compound.

---

### 5. CRITICAL: Anti-File-Bloat Violation (Continued)

**Why This Matters**:
- **902-line service.py**: Impossible to understand thread safety model at a glance
- **944-line delegation.py**: Six nearly-identical functions with subtle differences
- **Review Time**: This review took 45+ minutes due to file size
- **Bug Discovery**: Race conditions hidden in 200-line functions spanning multiple locks

**Refactoring Benefits**:
- **Thread safety**: Smaller modules = clearer lock scopes
- **Testing**: Each handler independently testable
- **Debugging**: Stack traces point to specific handlers
- **Code reuse**: Common patterns become obvious

---

## MEDIUM-PRIORITY ISSUES

### 6. Design Issue: Double Cache Invalidation

**Location**: `daemon/service.py:182-187, 251-255`
**Risk Level**: LOW - Performance, potential data corruption

**Current Behavior**:
```python
def exposed_index(...):
    # Invalidate BEFORE indexing
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry = None  # First invalidation

def _run_indexing_background(...):
    # ... indexing work ...

    # Invalidate AFTER indexing completes
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry = None  # Second invalidation
```

**Problem**:
1. First invalidation (before) forces queries during indexing to reload cache
2. Cache reload during indexing → reads **partially-written index files**
3. FilesystemVectorStore is NOT transactional
4. Result: Queries during indexing may see inconsistent data

**Example Failure**:
```
T0: Indexing starts, cache invalidated
T1: Query arrives, _ensure_cache_loaded() executes
T2: Query loads HNSW index (file exists, partially written)
T3: Indexing continues, writes more vectors
T4: Query searches with incomplete index → missing results
```

**Recommendation**:
- **Option A**: Keep ONLY post-indexing invalidation, block queries during indexing
- **Option B**: Use write-ahead logging / atomic index swaps (complex)
- **Option C**: Add "indexing in progress" flag, queue queries until complete

**Current Impact**: Low (race window is small, partial results acceptable for semantic search)

---

## WARNINGS (Should Fix But Not Blocking)

### 7. Anti-Duplication: Standalone Fallback Pattern (4 occurrences)

**Location**: `cli_daemon_delegation.py:195-282, 600-674, 767-841, 285-336`

**Pattern Repeated**:
```python
def _<command>_standalone(...):
    from .mode_detection.command_mode_detector import ...
    import click

    project_root = find_project_root(Path.cwd())
    mode_detector = CommandModeDetector(project_root)
    mode = mode_detector.detect_mode()

    ctx = click.Context(cli_<command>)
    ctx.obj = {"mode": mode, "project_root": project_root, "standalone": True}

    if mode == "local" and project_root:
        config_manager = ConfigManager.create_with_backtrack(project_root)
        ctx.obj["config_manager"] = config_manager

    # ... execute command ...
```

**Recommendation**:
```python
def _setup_standalone_context(command_name: str) -> click.Context:
    """Common context setup for standalone fallback."""
    project_root = find_project_root(Path.cwd())
    mode_detector = CommandModeDetector(project_root)
    mode = mode_detector.detect_mode()

    ctx = click.Context(click.Command(command_name))
    ctx.obj = {"mode": mode, "project_root": project_root, "standalone": True}

    if mode == "local" and project_root:
        config_manager = ConfigManager.create_with_backtrack(project_root)
        ctx.obj["config_manager"] = config_manager

    return ctx

def _query_standalone(query_text, ...):
    ctx = _setup_standalone_context("query")
    # ... specific logic ...
```

**Impact**: Reduces 80+ lines of duplication, improves maintainability.

---

### 8. Anti-Duplication: Daemon Connection Pattern (6 occurrences)

**Location**: All `_*_via_daemon` functions

**Pattern**:
```python
def _<command>_via_daemon(...):
    config_path = _find_config_file()
    if not config_path:
        return _<command>_standalone(...)

    socket_path = _get_socket_path(config_path)

    try:
        conn = _connect_to_daemon(socket_path, daemon_config)
        result = conn.root.exposed_<command>(...)
        # Extract data
        conn.close()
        # Display results
        return 0
    except Exception as e:
        console.print(f"[yellow]Failed: {e}[/yellow]")
        return _<command>_standalone(...)
```

**Recommendation**:
```python
def _execute_via_daemon(
    exposed_method: str,
    args: tuple,
    kwargs: dict,
    display_fn: Callable,
    fallback_fn: Callable
) -> int:
    """Generic daemon execution with fallback."""
    config_path = _find_config_file()
    if not config_path:
        return fallback_fn(**kwargs)

    try:
        conn = _connect_to_daemon(_get_socket_path(config_path), daemon_config)
        result = getattr(conn.root, exposed_method)(*args, **kwargs)
        data = display_fn(result)  # Extract + display
        conn.close()
        return 0
    except Exception as e:
        console.print(f"[yellow]Failed: {e}[/yellow]")
        return fallback_fn(**kwargs)
```

**Impact**: Reduces 200+ lines of duplication, centralizes error handling.

---

### 9. KISS Principle: exposed_index Complexity

**Location**: `daemon/service.py:155-202`

**Complexity Factors**:
- Thread lifecycle management
- Two different locks (cache_lock, indexing_lock_internal)
- Cache invalidation timing
- Background exception handling
- State cleanup in finally block

**Recommendation**: Extract `IndexingCoordinator` class:
```python
class IndexingCoordinator:
    """Manages background indexing thread lifecycle."""

    def __init__(self):
        self.thread: Optional[threading.Thread] = None
        self.project_path: Optional[str] = None
        self.lock: threading.Lock = threading.Lock()

    def is_running(self) -> bool:
        with self.lock:
            return self.thread is not None and self.thread.is_alive()

    def start_indexing(self, project_path: str, ...) -> Dict[str, Any]:
        with self.lock:
            if self.is_running():
                return {"status": "already_running"}

            self.thread = threading.Thread(...)
            self.project_path = project_path
            self.thread.start()
            return {"status": "started"}

    def clear_state(self):
        with self.lock:
            self.thread = None
            self.project_path = None
```

**Impact**: Simplifies service.py, improves testability of thread management.

---

## POSITIVE FINDINGS

### ✅ Correct RPyC Proxy Handling

**Location**: `cli_daemon_delegation.py:730-737, 906-912`

**Excellence**:
```python
# CORRECT: Extract data BEFORE closing connection
result = conn.root.exposed_index(...)
status = result.get("status", "unknown")      # Extract while conn alive
message = result.get("message", "")
project_path = result.get("project_path", "")
conn.close()                                  # Close AFTER extraction

# Display using local variables (not proxies)
console.print(f"Status: {status}")
```

**Why This Matters**: RPyC proxies become invalid after `conn.close()`. This pattern prevents "connection closed" errors. Properly implemented across all delegation functions.

---

### ✅ Cache Invalidation Strategy

**Location**: `daemon/service.py:182-187, 251-255, 443-447, 496-499`

**Excellence**: Cache invalidated before AND after mutations (index, clean, clean_data). Prevents stale cache from serving outdated results.

**Consistency**: All 4 mutation operations follow same pattern.

---

### ✅ Exception Handling in Background Thread

**Location**: `daemon/service.py:257-266`

**Excellence**:
```python
def _run_indexing_background(...):
    try:
        # ... indexing work ...
    except Exception as e:
        logger.error(f"Background indexing failed: {e}")
        logger.error(traceback.format_exc())
    finally:
        # ALWAYS clean up state
        with self.indexing_lock_internal:
            self.indexing_thread = None
```

**Why This Matters**: Background thread exceptions don't propagate to main thread. This catches, logs, and ensures cleanup always runs.

---

### ✅ Watch Thread Validation

**Location**: `daemon/service.py:343-345`

**Excellence**:
```python
self.watch_thread = self.watch_handler.processing_thread

# Verify thread actually started
if not self.watch_thread or not self.watch_thread.is_alive():
    raise RuntimeError("Watch thread failed to start")
```

**Why This Matters**: Detects silent watch failures immediately rather than returning success when watch isn't running.

---

## TESTING ASSESSMENT

### Test Coverage: Adequate But Gaps Exist

**Unit Tests Reviewed**:
- `test_daemon_service.py`: Tests exposed methods with mocks
- `test_critical_bug_fixes.py`: Tests watch thread capture
- `test_daemon_delegation.py`: Tests client-side delegation

**Coverage Gaps**:
1. **Race Conditions**: No tests for concurrent query + indexing
2. **Thread Safety**: No stress tests with multiple clients
3. **Edge Cases**: No tests for index completing during query

**Recommended Tests**:
```python
def test_query_during_indexing_race_condition():
    """Test that queries don't crash when indexing invalidates cache."""
    # Start indexing in background
    # Fire 10 concurrent queries
    # Verify no AttributeError crashes

def test_concurrent_index_calls():
    """Test that duplicate index calls are rejected."""
    # Call exposed_index from 3 threads simultaneously
    # Verify only 1 returns "started", others "already_running"

def test_watch_start_concurrent():
    """Test that duplicate watch starts are rejected."""
    # Call exposed_watch_start from 2 threads simultaneously
    # Verify only 1 succeeds
```

---

## SECURITY ASSESSMENT

### No Security Issues Detected

**Verified**:
- ✅ No shell injection (subprocess calls use list form)
- ✅ No path traversal (Path() objects used)
- ✅ No credential leaks (no secrets in logs)
- ✅ Socket permissions handled by OS (Unix domain sockets)
- ✅ No untrusted deserialization (RPyC uses pickling but in trusted context)

---

## PERFORMANCE ASSESSMENT

### ✅ Background Indexing Achieves Goal

**Problem Solved**: RPC timeout eliminated (0.00s return time vs 240s blocking)
**Trade-off Accepted**: No progress visibility (acceptable for daemon use case)

**Measurements**:
- Index command: Returns immediately (0.00s)
- Watch command: Returns immediately (0.02s)
- Indexing continues in background (~4 min for large repos)

**Recommendation**: Add polling endpoint for progress:
```python
def exposed_get_indexing_status(self) -> Dict[str, Any]:
    """Get current indexing progress."""
    with self.indexing_lock_internal:
        return {
            "running": self.indexing_thread is not None and self.indexing_thread.is_alive(),
            "project_path": self.indexing_project_path,
            # Could add: files_processed, total_files, estimated_time_remaining
        }
```

---

## ARCHITECTURAL ASSESSMENT

### Design Pattern: Background Task Execution

**Pattern Used**: Fire-and-forget background threads with status tracking
**Appropriateness**: ✅ Correct for RPC-based daemon (avoids long-running RPC calls)

**Alternatives Considered** (implicit):
- ❌ Blocking RPC calls: Causes timeouts (original problem)
- ❌ Task queue (Celery): Over-engineering for single-machine use case
- ✅ Background threads: Simplest solution that works

**Recommendation**: Current approach is correct for this use case.

---

### Design Pattern: Cache Coherence

**Pattern Used**: Pessimistic invalidation (invalidate before mutations)
**Correctness**: ✅ Prevents stale data
**Performance**: ⚠️ Double invalidation (before+after) is redundant

**Recommendation**: Move to single post-mutation invalidation + query blocking during indexing.

---

## MESSI RULES COMPLIANCE SUMMARY

| Rule | Status | Details |
|------|--------|---------|
| 1. Anti-Mock | ✅ PASS | Real services, no mocks in production code |
| 2. Anti-Fallback | ✅ PASS | Graceful degradation with user notification |
| 3. KISS | ⚠️ WARNING | `exposed_index` complexity high |
| 4. Anti-Duplication | ⚠️ WARNING | Standalone fallback pattern repeated 4x |
| 5. Anti-File-Chaos | ✅ PASS | Files in correct locations |
| 6. Anti-File-Bloat | ❌ FAIL | 2 files exceed 500-line module limit |
| 7. Domain-Driven | ✅ PASS | Clear domain separation (daemon, CLI) |
| 8. Reviewer Alerts | ⚠️ WARNING | Race conditions, thread safety issues |
| 9. Anti-Divergent | ✅ PASS | Implements exactly what was asked |
| 10. Fact-Verification | ✅ PASS | Evidence-based implementation |

**Score**: 6/10 PASS, 3/10 WARNING, 2/10 FAIL (with 1 HIGH severity)

---

## REQUIRED ACTIONS BEFORE MERGE

### MUST FIX (Blocking)

1. **Fix Race Condition #1**: Hold `cache_lock` during entire query execution
   - **Timeline**: 30 minutes
   - **Files**: `daemon/service.py` lines 87-95
   - **Test**: Add `test_query_during_cache_invalidation()`

2. **Fix Race Condition #2**: Atomic indexing thread creation under single lock
   - **Timeline**: 15 minutes
   - **Files**: `daemon/service.py` lines 174-196
   - **Test**: Add `test_concurrent_index_calls()`

3. **Fix Race Condition #3**: Add `watch_lock` to protect watch state
   - **Timeline**: 20 minutes
   - **Files**: `daemon/service.py` lines 287-289, 372-373
   - **Test**: Add `test_concurrent_watch_start()`

4. **Fix Anti-File-Bloat Violation**: Split large files into modules
   - **Timeline**: 2-3 hours
   - **Files**: Split `cli_daemon_delegation.py` (944→6 files), `daemon/service.py` (902→6 files)
   - **Test**: Verify all existing tests pass after refactor

**Total Timeline**: ~4 hours of focused work

---

### SHOULD FIX (Non-blocking but important)

5. **Refactor Duplication**: Extract common standalone context setup
   - **Timeline**: 30 minutes
   - **Impact**: Removes 80+ lines of duplication

6. **Refactor Duplication**: Abstract daemon connection pattern
   - **Timeline**: 45 minutes
   - **Impact**: Removes 200+ lines of duplication

7. **Simplify exposed_index**: Extract `IndexingCoordinator` class
   - **Timeline**: 45 minutes
   - **Impact**: Improves testability, reduces complexity

**Total Timeline**: ~2 hours

---

## RECOMMENDATION

**Status**: ❌ **REJECT - MUST FIX BEFORE MERGE**

**Reasoning**:
1. **HIGH-severity race condition** will cause production crashes (Issue #1)
2. **MESSI Rule 6 violations** significantly impact maintainability
3. Thread safety issues create unpredictable behavior under load
4. Fixes are straightforward and time-boxed (~4 hours)

**What Works Well**:
- ✅ Background threading solves RPC timeout problem
- ✅ RPyC proxy handling is correct
- ✅ Cache invalidation strategy is sound
- ✅ Error handling in background threads is robust

**What Must Change**:
- 🔴 Fix 3 race conditions (concurrent access bugs)
- 🔴 Split 2 bloated files into modules
- ⚠️ Remove code duplication (6 repeated patterns)

**Path Forward**:
1. Fix race conditions (4 hours) → Re-review → Merge
2. File splitting (optional pre-merge, required within 1 sprint)
3. Deduplication (technical debt, can defer to follow-up PR)

---

## SPECIFIC RECOMMENDATIONS FOR NEXT ITERATION

### Immediate (Pre-Merge)

```python
# 1. Fix query race condition
def exposed_query(self, project_path, query, limit, **kwargs):
    self._ensure_cache_loaded(project_path)

    # Hold lock during entire search to prevent invalidation mid-query
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry.update_access()
        results = self._execute_semantic_search(project_path, query, limit, **kwargs)

    return results

# 2. Fix indexing TOCTOU
def exposed_index(self, project_path, callback, **kwargs):
    with self.indexing_lock_internal:
        if self.indexing_thread and self.indexing_thread.is_alive():
            return {"status": "already_running"}

        self.indexing_project_path = project_path
        self.indexing_thread = threading.Thread(
            target=self._run_indexing_background,
            args=(project_path, callback, kwargs),
            daemon=True
        )
        self.indexing_thread.start()

    # Invalidate cache AFTER thread creation (avoids nested locks)
    with self.cache_lock:
        if self.cache_entry:
            self.cache_entry = None

    return {"status": "started", ...}

# 3. Fix watch synchronization
def __init__(self):
    self.watch_lock = threading.Lock()  # Add lock

def exposed_watch_start(self, project_path, callback, **kwargs):
    with self.watch_lock:
        if self.watch_handler and self.watch_thread and self.watch_thread.is_alive():
            return {"status": "error", "message": "Watch already running"}

        # ... create handler ...
        self.watch_handler = handler
        self.watch_thread = handler.processing_thread
    return {"status": "success"}
```

### Short-Term (Next PR)

4. Split `cli_daemon_delegation.py` into module
5. Split `daemon/service.py` into handler classes
6. Add stress tests for concurrent operations

### Medium-Term (1-2 sprints)

7. Add indexing progress polling endpoint
8. Consider read-write lock for cache (allow concurrent queries)
9. Implement transactional index updates (atomic swaps)

---

## CONCLUSION

The implementation successfully solves the RPC timeout problem and demonstrates solid understanding of threading concepts. However, **critical race conditions and architectural violations** prevent immediate merge.

**Estimated Time to Fix**: 4-6 hours of focused work
**Risk Level After Fixes**: LOW (straightforward concurrency patterns)
**Recommendation**: Fix blocking issues, then merge. File splitting can be follow-up PR if time-constrained.

**Overall Assessment**: Good first iteration on a complex problem. The bones are solid; needs polish on thread safety and code organization.

---

**Report Generated**: 2025-10-30
**Reviewer**: Claude Code (code-reviewer agent)
**Next Review**: After race condition fixes + file splitting
