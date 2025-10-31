# CODE REVIEW: Daemon UX Parity Fixes

**Reviewer:** Claude Code (Code Review Agent)
**Date:** 2025-10-31
**Review Type:** CRITICAL - UX Regression Validation
**Branch:** feature/cidx-daemonization
**Files Reviewed:**
- src/code_indexer/cli_daemon_fast.py
- src/code_indexer/cli_daemon_delegation.py
- src/code_indexer/daemon/service.py

---

## EXECUTIVE SUMMARY

**VERDICT: REJECT - CRITICAL ISSUES REMAIN**

The tdd-engineer's fixes are **partially implemented** but contain **critical flaws** that violate the UX parity requirement. While the code attempts to reuse standalone display logic, it **DUPLICATES CODE** instead of actually calling the standalone functions, and the index command has a **BLOCKING IMPLEMENTATION** that will hang the CLI.

**Bottom Line:** This implementation will create NEW bugs while attempting to fix the UX regressions.

---

## DETAILED FINDINGS

### 1. QUERY COMMAND - CONTENT DUPLICATION (CRITICAL)

**Location:** `cli_daemon_fast.py` lines 93-239

**Issue:** The `_display_results()` function **DUPLICATES** the entire standalone display logic instead of calling the existing function.

**Evidence:**

**Daemon Implementation (cli_daemon_fast.py:132-239):**
```python
def _display_results(results: Any, console: Console, timing_info: Optional[Dict[str, Any]] = None) -> None:
    # Lines 132-239 - COMPLETELY REIMPLEMENTED standalone display logic
    # - Creates header with file info (lines 166-175)
    # - Displays metadata info (lines 178-206)
    # - Displays full content with line numbers (lines 208-238)
```

**Standalone Implementation (cli.py:5022-5166):**
```python
# Lines 5022-5166 - ORIGINAL display logic
# - Creates header with file info
# - Displays metadata info
# - Displays full content with line numbers
# EXACT SAME LOGIC BUT NOT REUSED
```

**Problem:**
1. **Code Duplication:** 107 lines of duplicated display logic
2. **Maintenance Nightmare:** Two copies to maintain when logic changes
3. **Divergence Risk:** Already shows differences (daemon uses emojiless styling on line 236, standalone doesn't)
4. **NOT True Code Reuse:** Claiming to reuse but actually reimplementing

**Correct Implementation Should Be:**
```python
def _display_results(results: Any, console: Console, timing_info: Optional[Dict[str, Any]] = None) -> None:
    """Display query results using IDENTICAL standalone formatting."""
    # Import standalone display logic and CALL IT
    from .cli import _display_semantic_results_internal  # New refactored function
    _display_semantic_results_internal(results, console, quiet=False, timing_info=timing_info)
```

**Severity:** **CRITICAL** - Violates DRY principle, creates technical debt

**Risk Level:** **HIGH** - Will diverge over time, already shows minor differences

---

### 2. INDEX COMMAND - BLOCKING IMPLEMENTATION WILL HANG CLI (BLOCKER)

**Location:** `daemon/service.py` lines 161-268, `cli_daemon_delegation.py` lines 664-804

**Issue:** The index command **BLOCKS** the daemon service thread, making it unavailable for queries during indexing.

**Evidence:**

**Service Implementation (daemon/service.py:198-228):**
```python
def exposed_index(self, project_path: str, callback: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
    """Perform BLOCKING indexing with progress callbacks for UX parity."""
    # ... setup code ...

    # Execute indexing SYNCHRONOUSLY (BLOCKS until complete)
    stats = indexer.smart_index(
        force_full=kwargs.get('force_full', False),
        batch_size=kwargs.get('batch_size', 50),
        progress_callback=callback,  # Streams to client in real-time
        quiet=False,  # Show progress
        enable_fts=kwargs.get('enable_fts', False),
    )
```

**Client Implementation (cli_daemon_delegation.py:728-734):**
```python
# Execute indexing (BLOCKS until complete, streams progress via callback)
# RPyC automatically handles callback streaming to client
result = conn.root.exposed_index(
    project_path=str(Path.cwd()),
    callback=progress_callback,  # Real-time progress streaming
    **daemon_kwargs,
)
```

**Critical Problems:**

1. **Daemon Unavailable During Indexing**
   - RPyC service thread is blocked executing `smart_index()`
   - Cannot handle ANY other RPC calls (queries, status, etc.)
   - Users cannot query while indexing is in progress
   - Defeats the PURPOSE of daemon mode

2. **RPyC Callback Streaming Assumption is WRONG**
   - RPyC does NOT automatically stream callbacks in real-time
   - Callbacks execute in the daemon's thread context
   - Client waits for entire RPC to complete before receiving updates
   - Progress bar will NOT update in real-time

3. **Architecture Violation**
   - Story 2.4 explicitly required BACKGROUND indexing
   - This implementation makes indexing SYNCHRONOUS
   - Removes parallelism benefit of daemon architecture

**What Was Expected (Story 2.4):**
```python
def exposed_index(self, ...):
    # Start indexing in BACKGROUND thread
    self.indexing_thread = threading.Thread(
        target=self._run_indexing_background,
        args=(project_path, callback, kwargs)
    )
    self.indexing_thread.start()

    # Return IMMEDIATELY (non-blocking)
    return {"status": "started", "message": "Indexing started"}

# Client polls for progress via separate RPC calls
```

**Severity:** **BLOCKER** - Breaks daemon architecture and makes service unavailable

**Risk Level:** **CRITICAL** - Will cause user-visible hangs and failures

---

### 3. QUERY DISPLAY - NO TIMING INFORMATION (HIGH PRIORITY)

**Location:** `cli_daemon_fast.py` line 114

**Issue:** Timing information display is called but the standalone function may not exist.

**Evidence:**
```python
# Display timing information if available
if timing_info and not timing_info.get("quiet", False):
    _display_query_timing(console, timing_info)  # Line 114
```

**Problems:**
1. Function `_display_query_timing()` is imported from `cli.py` (line 109)
2. But daemon doesn't capture or provide timing information
3. `timing_info` parameter comes from daemon but daemon doesn't track timing
4. Daemon service doesn't return timing information in results

**Missing Implementation:**
- Daemon service needs to track query timing
- Return timing in result dictionary
- Pass timing to `_display_results()`

**Severity:** **HIGH** - Missing critical performance visibility (Regression #2)

**Risk Level:** **MEDIUM** - Feature partially implemented but incomplete

---

### 4. MISSING QUERY CONTEXT INFORMATION (HIGH PRIORITY)

**Location:** `cli_daemon_fast.py` lines 283-308

**Issue:** Query context is displayed ONLY in the fast path, not in delegation path.

**Evidence:**

**Fast Path Has Context (cli_daemon_fast.py:283-308):**
```python
# DISPLAY QUERY CONTEXT (identical to standalone mode)
project_root = Path.cwd()
console.print(f"🔍 Executing local query in: {project_root}", style="dim")
# ... displays branch, query text, filters, limit ...
```

**Delegation Path Missing Context (cli_daemon_delegation.py:326-336):**
```python
def _query_via_daemon(query_text: str, daemon_config: Dict, ...):
    # ... connects to daemon ...
    # NO context display before executing query
    # Result display function is called but no preamble
```

**Problem:**
- Users calling via delegation path (majority of users) get NO context info
- Only direct fast path shows context (less common path)
- Violates UX parity requirement (Regression #1)

**Severity:** **HIGH** - Major UX regression remains unfixed

**Risk Level:** **MEDIUM** - Inconsistent user experience

---

### 5. CODE QUALITY ISSUES

#### 5.1 Inconsistent Import Patterns

**Location:** Throughout `cli_daemon_fast.py`

**Issue:** Lazy imports mixed with top-level imports inconsistently.

```python
# Top-level imports (lines 15-16)
from rpyc.utils.factory import unix_connect
from rich.console import Console

# Lazy imports inside function (lines 109-110, 119-129)
from .cli import _display_query_timing
from pathlib import Path
import subprocess
```

**Problem:** No clear pattern for when to use lazy imports vs top-level imports.

**Severity:** **LOW** - Code organization issue

---

#### 5.2 Duplicate Git Branch Detection

**Location:** `cli_daemon_fast.py` lines 118-130 and lines 288-301

**Issue:** Git branch detection code is duplicated in two places.

```python
# First occurrence (lines 118-130)
try:
    import subprocess
    git_result = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], ...)
    if git_result.returncode == 0:
        current_display_branch = git_result.stdout.strip()
except Exception:
    pass

# Second occurrence (lines 288-301) - EXACT SAME CODE
try:
    import subprocess
    git_result = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], ...)
    if git_result.returncode == 0:
        current_branch = git_result.stdout.strip()
except Exception:
    pass
```

**Severity:** **LOW** - Minor code duplication

---

#### 5.3 Incomplete Error Handling

**Location:** `cli_daemon_delegation.py` lines 786-804

**Issue:** Progress manager cleanup may fail silently.

```python
except Exception as e:
    # Clean up progress display on error
    try:
        progress_manager.stop_progress()
        rich_live_manager.stop_display()
    except Exception:
        pass  # Silent failure - no logging
```

**Problem:** If cleanup fails, no indication to user or logs.

**Severity:** **LOW** - Minor robustness issue

---

### 6. POSITIVE FINDINGS

#### 6.1 Full Content Display (FIXED)

**Location:** `cli_daemon_fast.py` lines 208-238

**Status:** ✅ **CORRECTLY IMPLEMENTED**

The display function now shows FULL content without truncation:
```python
# Display full content (no syntax highlighting in daemon fast path for speed)
console.print(content_with_line_numbers)
```

No "[:100]" truncation, no "..." suffix. Content is displayed completely.

---

#### 6.2 Metadata Completeness (FIXED)

**Location:** `cli_daemon_fast.py` lines 159-206

**Status:** ✅ **CORRECTLY IMPLEMENTED**

All metadata fields are displayed:
- File path with line numbers (lines 166-157)
- Language (line 168)
- Score (line 169)
- Staleness indicator (lines 172-174)
- File size (line 178)
- Indexed timestamp (line 178)
- Staleness details (lines 181-194)
- Git branch (lines 196-203)
- Git commit (lines 198-203)
- Project ID (lines 205-206)

This matches standalone mode's metadata display.

---

#### 6.3 Line Number Display (FIXED)

**Location:** `cli_daemon_fast.py` lines 222-236

**Status:** ✅ **CORRECTLY IMPLEMENTED**

Content includes line number prefixes:
```python
# Add line number prefixes if we have line start info
if line_start is not None:
    numbered_lines = []
    for j, line in enumerate(content_lines):
        line_num = line_start + j
        numbered_lines.append(f"{line_num:3}: {line}")
    content_with_line_numbers = "\n".join(numbered_lines)
```

Identical to standalone implementation (cli.py:5146-5150).

---

## ACCEPTANCE CRITERIA ASSESSMENT

**Original Bug Report Requirements:**

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 1. Query output identical to standalone | ❌ **FAIL** | Code duplication, not true reuse |
| 2. Full chunk content displayed | ✅ **PASS** | No truncation found (lines 208-238) |
| 3. Progress bars work during index | ❌ **FAIL** | Blocking implementation will not work |
| 4. All metadata fields present | ✅ **PASS** | Complete metadata display (lines 159-206) |
| 5. Performance timing shown | ❌ **FAIL** | Timing not captured or displayed |
| 6. Git information displayed | ✅ **PASS** | Branch, commit shown (lines 196-203) |
| 7. Users cannot tell daemon is on/off | ❌ **FAIL** | Missing context info, timing issues |

**Overall Score: 3/7 (43%) - FAILING**

---

## CRITICAL BUGS INTRODUCED

### Bug #1: Daemon Hangs During Indexing

**Severity:** **BLOCKER**

**Impact:** Daemon becomes unresponsive to queries while indexing.

**Reproduction Steps:**
1. Start daemon: `cidx start`
2. Start indexing: `cidx index --clear`
3. Try to query: `cidx query "test"` (in separate terminal)
4. **RESULT:** Query hangs waiting for daemon to respond
5. **EXPECTED:** Query should work while indexing runs in background

**Root Cause:** `exposed_index()` blocks the RPyC service thread (daemon/service.py:222-228)

---

### Bug #2: Progress Callbacks Don't Actually Stream

**Severity:** **CRITICAL**

**Impact:** Progress bar will not update during indexing.

**Root Cause:** RPyC callback execution is synchronous in daemon thread context. Client receives updates AFTER indexing completes, not during.

**Expected Behavior:** Progress bar updates in real-time as files are indexed.

**Actual Behavior:** CLI will appear frozen until indexing completes, then show all updates at once.

---

### Bug #3: Code Divergence Already Starting

**Severity:** **HIGH**

**Impact:** Maintenance burden increases, bugs will differ between modes.

**Evidence:**
- Line 236 daemon: `console.print(content_with_line_numbers)` (no syntax highlighting)
- Lines 5156-5164 standalone: Attempts syntax highlighting first

This is a **minor** difference now, but demonstrates the problem: two codebases will diverge.

---

## ARCHITECTURAL CONCERNS

### Violation of Daemon Design Principles

**Problem:** The index command implementation violates the core daemon architecture.

**Daemon Purpose:**
1. Keep expensive resources loaded (indexes, embeddings)
2. Handle multiple operations concurrently
3. Allow background processing while remaining responsive

**Current Implementation:**
1. ✅ Keeps indexes loaded
2. ❌ Cannot handle concurrent operations (blocks on index)
3. ❌ Background processing broken (synchronous execution)

**Impact:** Daemon is no better than standalone mode for indexing operations.

---

### RPyC Callback Misunderstanding

**Problem:** The code assumes RPyC will stream callbacks to client in real-time.

**Reality:** RPyC executes callbacks synchronously in the server thread. Client code blocks on RPC call. Callbacks execute remotely and don't update client UI until RPC completes.

**Solution Required:**
1. Use polling mechanism (client repeatedly calls daemon to get progress)
2. Or use separate RPC methods for progress updates
3. Or redesign to use RPyC's async features (complex)

**Recommended:** Polling mechanism (client calls `exposed_get_index_progress()` every 200ms)

---

## RECOMMENDATIONS

### Priority 1: Fix Index Blocking Issue (BLOCKER)

**Required Changes:**

**1.1 Daemon Service (daemon/service.py):**

```python
def exposed_index(self, project_path: str, **kwargs) -> Dict[str, Any]:
    """Start indexing in BACKGROUND thread, return immediately."""

    with self.indexing_lock_internal:
        if self.indexing_thread and self.indexing_thread.is_alive():
            return {"status": "already_running"}

        # Start background thread
        self.indexing_thread = threading.Thread(
            target=self._run_indexing_background,
            args=(project_path, kwargs)
        )
        self.indexing_thread.start()

        return {"status": "started", "message": "Indexing started"}

def exposed_get_index_progress(self) -> Dict[str, Any]:
    """Get current indexing progress (for polling)."""
    with self.indexing_lock_internal:
        if not self.indexing_thread or not self.indexing_thread.is_alive():
            return {"status": "not_running"}

        return {
            "status": "running",
            "current": self.indexing_progress_current,
            "total": self.indexing_progress_total,
            "file_path": self.indexing_progress_file,
            "info": self.indexing_progress_info,
        }
```

**1.2 Client Delegation (cli_daemon_delegation.py):**

```python
def _index_via_daemon(force_reindex: bool = False, **kwargs) -> int:
    """Delegate indexing to daemon with POLLING for progress updates."""

    # Start indexing
    result = conn.root.exposed_index(project_path=str(Path.cwd()), **daemon_kwargs)

    if result["status"] != "started":
        # Handle already running or error
        ...

    # Poll for progress in loop
    progress_manager = MultiThreadedProgressManager()
    rich_live_manager = RichLiveManager(progress_manager)
    rich_live_manager.start_display()

    while True:
        time.sleep(0.2)  # Poll every 200ms
        progress = conn.root.exposed_get_index_progress()

        if progress["status"] == "not_running":
            break  # Indexing completed

        # Update progress bar
        progress_manager.update_progress(
            current_file=progress["current"],
            total_files=progress["total"],
            current_file_path=progress["file_path"],
            info=progress["info"],
        )

    # Get final statistics
    stats = conn.root.exposed_get_index_stats()

    # Display completion
    ...
```

---

### Priority 2: Refactor Display Code to Eliminate Duplication (CRITICAL)

**Required Changes:**

**2.1 Extract Standalone Display Logic (cli.py):**

```python
def _display_semantic_results_internal(
    results: List[Dict[str, Any]],
    console: Console,
    quiet: bool = False,
    timing_info: Optional[Dict[str, Any]] = None,
    current_display_branch: str = "unknown"
) -> None:
    """Internal result display logic (reusable by daemon and standalone)."""

    # Display timing if provided
    if timing_info and not quiet:
        _display_query_timing(console, timing_info)

    # Display results (FULL IMPLEMENTATION - lines 5022-5166 refactored)
    for i, result in enumerate(results, 1):
        payload = result["payload"]
        score = result["score"]
        # ... (existing display logic)
```

**2.2 Update Daemon Display (cli_daemon_fast.py):**

```python
def _display_results(results: Any, console: Console, timing_info: Optional[Dict[str, Any]] = None) -> None:
    """Display query results using IDENTICAL standalone formatting."""

    # Import standalone display function
    from .cli import _display_semantic_results_internal

    # Get current branch for context
    current_display_branch = _get_current_branch()  # Extract to helper

    # CALL standalone logic (not reimplementing)
    _display_semantic_results_internal(
        results=results,
        console=console,
        quiet=False,
        timing_info=timing_info,
        current_display_branch=current_display_branch
    )
```

**Benefits:**
- Single source of truth for display logic
- Zero duplication
- Guaranteed consistency
- Easy to maintain

---

### Priority 3: Implement Timing Capture (HIGH)

**Required Changes:**

**3.1 Daemon Service (daemon/service.py):**

```python
def exposed_query(self, project_path: str, query: str, limit: int = 10, **kwargs) -> Dict[str, Any]:
    """Execute semantic search with caching and timing."""

    # Track timing
    timing_start = time.perf_counter()

    with self.cache_lock:
        cache_load_start = time.perf_counter()
        self._ensure_cache_loaded(project_path)
        cache_load_ms = (time.perf_counter() - cache_load_start) * 1000

        search_start = time.perf_counter()
        results = self._execute_semantic_search(project_path, query, limit, **kwargs)
        search_ms = (time.perf_counter() - search_start) * 1000

    total_ms = (time.perf_counter() - timing_start) * 1000

    # Return results WITH timing
    return {
        "results": results,
        "timing": {
            "total_ms": total_ms,
            "cache_load_ms": cache_load_ms,
            "search_ms": search_ms,
        }
    }
```

**3.2 Client Display (cli_daemon_fast.py or cli_daemon_delegation.py):**

```python
# Extract timing from result
timing_info = result.get("timing", {})

# Pass to display function
_display_results(result["results"], console, timing_info=timing_info)
```

---

### Priority 4: Add Query Context Display (HIGH)

**Required Changes:**

**4.1 Delegation Path (cli_daemon_delegation.py:326-336):**

```python
def _query_via_daemon(query_text: str, daemon_config: Dict, ...):
    # Display context BEFORE executing query (matching standalone)
    console.print(f"🔍 Executing local query in: {Path.cwd()}", style="dim")
    console.print(f"🌿 Current branch: {_get_current_branch()}", style="dim")
    console.print(f"🔍 Searching for: '{query_text}'", style="dim")
    if languages:
        console.print(f"🏷️  Language filter: {languages}", style="dim")
    console.print(f"📊 Limit: {limit}", style="dim")

    # Now execute query
    result = conn.root.exposed_query(...)

    # Display results
    _display_results(result, query_time)
```

---

## TESTING REQUIREMENTS

### Test 1: Daemon Responsiveness During Indexing

```bash
# Terminal 1: Start indexing
cidx config --daemon
cidx index --clear

# Terminal 2: Try to query while indexing
cidx query "test" --limit 3

# EXPECTED: Query completes in <500ms
# ACTUAL (with current code): Query hangs until indexing completes
```

**Pass Criteria:** Query must complete while indexing is in progress.

---

### Test 2: Progress Bar Real-Time Updates

```bash
# Watch for progress updates
cidx index --clear

# EXPECTED: Progress bar updates smoothly every 200ms
# ACTUAL (with current code): CLI freezes, then shows all updates at once
```

**Pass Criteria:** Progress bar must update continuously during indexing.

---

### Test 3: Visual Output Diff

```bash
# Standalone mode
cidx config --no-daemon
cidx query "test" --limit 3 > /tmp/standalone.txt

# Daemon mode
cidx config --daemon
cidx query "test" --limit 3 > /tmp/daemon.txt

# Compare
diff /tmp/standalone.txt /tmp/daemon.txt
```

**Pass Criteria:**
- Only timing values should differ
- Content, metadata, structure must be identical
- No truncation differences
- No missing fields

---

### Test 4: Code Reuse Validation

```bash
# Grep for duplicated display logic
grep -n "📄 File:" src/code_indexer/cli_daemon_fast.py
grep -n "📄 File:" src/code_indexer/cli.py

# EXPECTED: Only ONE implementation
# ACTUAL: TWO implementations (duplication)
```

**Pass Criteria:** Display logic should exist in ONLY ONE place.

---

## ESTIMATED REWORK EFFORT

| Task | Priority | Effort | Risk |
|------|----------|--------|------|
| Fix index blocking (background thread) | P1 - BLOCKER | 6-8 hours | HIGH |
| Implement progress polling mechanism | P1 - BLOCKER | 4-6 hours | MEDIUM |
| Refactor display to eliminate duplication | P2 - CRITICAL | 3-4 hours | LOW |
| Add timing capture and display | P3 - HIGH | 2-3 hours | LOW |
| Add query context to delegation path | P4 - HIGH | 1-2 hours | LOW |
| Testing and validation | - | 4-6 hours | LOW |

**Total Estimated Effort:** 20-29 hours

**Critical Path:** P1 items must be completed first (index blocking + polling mechanism)

---

## SECURITY CONSIDERATIONS

### No Security Issues Found

The code changes do not introduce security vulnerabilities:
- ✅ No new authentication/authorization paths
- ✅ No sensitive data exposure
- ✅ No injection vulnerabilities
- ✅ No privilege escalation risks

---

## PERFORMANCE CONSIDERATIONS

### Performance Regression Risk: Progress Polling

**Issue:** Polling every 200ms adds RPC overhead.

**Impact Analysis:**
- Each poll: ~1-5ms RPC round-trip
- 5 polls/second = 5-25ms overhead/second
- Over 3-minute indexing: 0.9-4.5 seconds total overhead (0.5-2.5% of total time)

**Mitigation:** Acceptable overhead for UX benefit.

---

## FINAL VERDICT

**REJECT - CRITICAL ISSUES REQUIRE REWORK**

### Issues Requiring Fixes Before Approval:

1. **BLOCKER:** Index command blocks daemon thread (daemon/service.py:161-268)
2. **BLOCKER:** Progress callbacks won't stream in real-time (architecture misunderstanding)
3. **CRITICAL:** Display code duplicated instead of reused (cli_daemon_fast.py:93-239)
4. **HIGH:** Missing timing information capture and display
5. **HIGH:** Missing query context in delegation path

### What Was Done Well:

1. ✅ Full content display (no truncation)
2. ✅ Complete metadata display
3. ✅ Line number formatting
4. ✅ Git information display
5. ✅ Attempt to address user concerns

### Recommendation:

**DO NOT MERGE** until the following are completed:

1. Rewrite index command to use background threading + polling
2. Refactor display code to eliminate duplication
3. Implement timing capture in daemon service
4. Add query context display to delegation path
5. Complete testing per Test 1-4 above

**Estimated Time to Fix:** 20-29 hours of focused development

---

## ARCHITECTURAL GUIDANCE FOR REWORK

### Daemon Design Pattern to Follow

```
┌─────────────────────────────────────────────────────────┐
│                      Daemon Service                      │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐             │
│  │ Query Thread │◄────────┤ Cache Entry  │             │
│  │ (Responsive) │         │ (Loaded)     │             │
│  └──────────────┘         └──────────────┘             │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐             │
│  │ Index Thread │◄────────┤ Progress     │             │
│  │ (Background) │         │ State        │             │
│  └──────────────┘         └──────────────┘             │
│          ▲                        ▲                      │
│          │                        │                      │
└──────────┼────────────────────────┼──────────────────────┘
           │                        │
           │                        │
┌──────────▼────────────────────────▼──────────────────────┐
│                     Client Polling                        │
│                                                          │
│  • Calls exposed_query() → Returns immediately          │
│  • Calls exposed_get_index_progress() → Returns state   │
│  • Updates local progress bar                           │
└──────────────────────────────────────────────────────────┘
```

**Key Points:**
- Query operations NEVER block (cache loaded in background)
- Index operations run in SEPARATE thread (daemon remains responsive)
- Client POLLS for progress (not streaming callbacks)
- Both operations can run CONCURRENTLY

---

## CONCLUSION

The tdd-engineer made a **valiant effort** to address the UX regressions, but the implementation has **critical architectural flaws** that will create new bugs. The code demonstrates **understanding of the problem** but **misunderstanding of the solution architecture**.

**Most Critical Issue:** The blocking index implementation fundamentally breaks the daemon's purpose.

**Next Steps:**
1. Pause development
2. Review architectural guidance above
3. Implement background threading + polling pattern
4. Refactor display code for reuse (not duplication)
5. Re-submit for review

**User Trust:** The user specifically requested extreme scrutiny because trust was lost. This review validates that concern - the implementation is not ready for production.

---

**Review Conducted With:**
- Deep code analysis (3 files, 1,200+ lines reviewed)
- Architecture validation against design patterns
- Bug report cross-reference
- UX parity assessment
- Security and performance review

**Review Completeness:** Comprehensive - All claimed fixes validated against requirements
