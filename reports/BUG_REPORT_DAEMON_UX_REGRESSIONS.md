# BUG REPORT: Daemon Mode UX Regressions

**Date:** 2025-10-31
**Severity:** CRITICAL
**Category:** User Experience Regression
**Impact:** Daemon mode provides significantly degraded UX compared to standalone mode

---

## Executive Summary

The daemon implementation introduces **severe UX regressions** that make daemon mode objectively worse than standalone mode for users. While daemon mode is faster (~130ms vs ~1000ms), the output quality and user experience are dramatically degraded.

**Bottom Line:** Users will disable daemon mode because the UX is broken, negating all performance benefits.

---

## Comparison: Standalone vs Daemon Mode

### Test Command
```bash
cidx query "voyage-ai query rest" --limit 2
```

---

## REGRESSION #1: Missing Query Context Information

### Standalone Mode Output (CORRECT)
```
🔍 Executing local query in: /home/jsbattig/Dev/code-indexer
🤖 Using voyage-ai with model: voyage-code-3
📂 Git repository: code-indexer
🌿 Current branch: feature/cidx-daemonization
🔍 Searching for: 'voyage-ai query rest'
📊 Limit: 2
🤖 Filtering by model: voyage-code-3
🔍 Applying git-aware filtering...
```

### Daemon Mode Output (BROKEN)
```
(NOTHING - completely missing)
```

**Impact:**
- Users don't know what model is being used
- Users don't know what repository is being searched
- Users don't know what branch they're on
- Users don't know if git-aware filtering is active
- **Complete loss of context awareness**

**Severity:** HIGH - Users lose critical operational visibility

---

## REGRESSION #2: Missing Performance Timing Breakdown

### Standalone Mode Output (CORRECT)
```
⏱️  Query Timing:
------------------------------------------------------------
  • Parallel load (embedding + index)      748ms ( 79.1%)

      ├─ Embedding generation (concurrent)      734ms
      ├─ HNSW index load (concurrent)       13ms
      ├─ ID index load (concurrent)       25ms
      └─ Threading overhead            14ms ( 1.8% overhead)

  • Vector search                         3ms (  0.4%)
  • Git-aware filtering                 195ms ( 20.6%)

  Search path: ⚡ hnsw_index
------------------------------------------------------------
  Total query time                    946ms (100.0%)
```

### Daemon Mode Output (BROKEN)
```
(COMPLETELY MISSING - no timing information at all)
```

**Impact:**
- Users cannot diagnose performance issues
- Users don't know where time is spent
- Users cannot optimize their queries
- Users cannot tell if caching is working
- **Complete loss of performance visibility**

**Severity:** HIGH - Critical for performance debugging and understanding

---

## REGRESSION #3: Truncated Content Display

### Standalone Mode Output (CORRECT)
```
📄 File: src/code_indexer/services/voyage_ai.py:1-109 | 🏷️  Language: py | 📊 Score: 0.607 | 🟢 Fresh
📏 Size: 13637 bytes | 🕒 Indexed: 2025-10-31T02:06:56.529774+00:00Z | 🌿 Branch: feature/cidx-daemonization | 📦 Commit: 41924c19... | 🏗️  Project: code-indexer

📖 Content (Lines 1-109):
──────────────────────────────────────────────────
  1: """VoyageAI API client for embeddings generation."""
  2:
  3: import os
  4: import time
  5: from typing import List, Dict, Any, Optional
  6: import httpx
  7: from rich.console import Console
  8: import yaml  # type: ignore
  9: from pathlib import Path
 10:
 11: # Suppress tokenizers parallelism warning
 12: os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
 13:
... (full chunk continues for 109 lines)
```

### Daemon Mode Output (BROKEN)
```
1. src/code_indexer/services/voyage_ai.py:1 (score: 0.607)
   """VoyageAI API client for embeddings generation."""

import os
import time
from typing import Li...
```

**Issues:**
- ❌ Missing metadata header (file info, language, freshness, size, indexed timestamp, branch, commit, project)
- ❌ Missing content separator line
- ❌ **Content truncated with "..."** instead of showing full chunk
- ❌ Missing line numbers in content
- ❌ Missing syntax highlighting
- ❌ No visual separation between results

**Impact:**
- Users cannot see the full context they need
- Users cannot copy/paste the full code
- Users lose git metadata (branch, commit, freshness)
- Users lose file metadata (size, language, indexed time)
- **Severely degraded result quality**

**Severity:** CRITICAL - This makes daemon mode unusable for actual work

---

## REGRESSION #4: Missing Result Summary

### Standalone Mode Output (CORRECT)
```
✅ Found 2 results:
================================================================================
(followed by results)
```

### Daemon Mode Output (BROKEN)
```
1. (result)
2. (result)
(no header, no summary, no separator)
```

**Impact:**
- Users don't get confirmation of result count
- No visual structure
- Harder to parse output

**Severity:** LOW - Cosmetic but reduces professionalism

---

## REGRESSION #5: Index Command - No Progress Display

### Standalone Mode Output (CORRECT)
```
📂 Git repository detected
🌿 Current branch: feature/cidx-daemonization
📦 Project ID: code-indexer
🧵 Vector calculation threads: 8 (from config.json)
🧹 Force full reindex requested
ℹ️  🗑️ Cleared collection 'voyage-code-3'
ℹ️  🔍 Discovering files in repository...
ℹ️  📁 Found 1334 files for indexing
ℹ️  🌿 Analyzing git repository structure...
ℹ️  ⚙️ Initializing parallel processing threads...
🔍 Hashing  ━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% • 0:00:05 • 1334/1334 files
🚀 Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% • 0:02:45 • 1334/1334 files
✅ Indexing complete!
📄 Files processed: 1334
⏱️  Duration: 3:12.5
🚀 Throughput: 412.3 files/min
```

### Daemon Mode Output (BROKEN)
```
✓ Indexing started in daemon background
Tip: Run queries or check status to monitor progress
```

**Impact:**
- **NO progress bar** (critical UX loss)
- Users don't know how many files
- Users don't know current progress
- Users don't know throughput
- Users don't know when it's complete
- **Have to run separate `cidx status` command**
- Completely non-transparent operation

**Severity:** CRITICAL - Makes daemon mode much worse than standalone for indexing

---

## REGRESSION #6: Status Command Shows Nothing During Indexing

**Issue:** Even when running `cidx status` during active indexing, there's no indication of:
- How many files have been processed
- Current file being indexed
- Progress percentage
- Estimated time remaining
- Throughput

**Current output:** Just shows `indexing_running: True` - no details

**Expected:** Should show real-time indexing progress like standalone mode does

**Severity:** HIGH - Users have no visibility into long-running operations

---

## REGRESSION #7: Missing Git-Aware Filtering Feedback

### Standalone Mode (CORRECT)
```
🔍 Applying git-aware filtering...
```

### Daemon Mode (BROKEN)
```
(missing - users don't know filtering is happening)
```

---

## ROOT CAUSE ANALYSIS

### For Query Command

**Problem Location:** `src/code_indexer/cli_daemon_fast.py` - `_display_results()` function

**Current Implementation:**
```python
def _display_results(result, console):
    """Minimal result display."""
    for i, r in enumerate(result, 1):
        payload = r.get("payload", {})
        path = payload.get("path", "unknown")
        line = payload.get("line_start", 0)
        score = r.get("score", 0)
        content = payload.get("content", "")[:100]  # TRUNCATED!
        console.print(f"{i}. {path}:{line} (score: {score:.3f})")
        console.print(f"   {content}...")  # TRUNCATED!
```

**Should Use:** The SAME display function as standalone mode (from cli.py)
- Full chunk content (not truncated)
- Rich metadata header
- Syntax highlighting
- Line numbers
- Git information

### For Index Command

**Problem Location:** `src/code_indexer/daemon/service.py` - `exposed_index()`

**Current Implementation:**
```python
# Returns immediately
return {"status": "started", "message": "Indexing started in background"}
```

**Missing:**
- Progress callbacks to client
- RPyC callback streaming
- Rich progress bar updates
- Real-time file count/throughput

**Story 2.4 was supposed to implement this but it's not working**

---

## IMPACT ASSESSMENT

### User Experience Impact

| Aspect | Standalone | Daemon | Regression |
|--------|-----------|--------|------------|
| Query context info | ✅ Full | ❌ None | **100% loss** |
| Performance timing | ✅ Detailed | ❌ None | **100% loss** |
| Result content | ✅ Full chunks | ❌ Truncated | **~90% loss** |
| Result metadata | ✅ Complete | ❌ Minimal | **~80% loss** |
| Index progress | ✅ Real-time bar | ❌ None | **100% loss** |
| Index completion | ✅ Statistics | ❌ None | **100% loss** |

**Overall UX Degradation: ~85%**

### Performance vs UX Trade-off

**Performance Gain:** 7-10x faster (946ms → 130ms)
**UX Loss:** 85% of information and feedback removed

**User Perception:** "It's faster but I can't see what it's doing or understand the results"

---

## CRITICAL FINDING

**The daemon mode is objectively WORSE for users despite being faster.**

Users need:
1. **Transparency** - Know what's happening
2. **Context** - Understand the results
3. **Feedback** - See progress for long operations
4. **Completeness** - Get full information, not summaries

**Current daemon mode provides:**
1. ❌ No transparency (missing context info)
2. ❌ No context (truncated results)
3. ❌ No feedback (no progress bars)
4. ❌ No completeness (truncated content)

---

## RECOMMENDATIONS

### Priority 1: Fix Query Output (CRITICAL)

**Reuse standalone display code:**
```python
# In cli_daemon_fast.py
def _display_results(result, console):
    # Import and use the SAME function as standalone mode
    from .cli import _display_semantic_results
    _display_semantic_results(result, quiet=False, console=console)
```

**This ensures:**
- ✅ Full chunk content
- ✅ Rich metadata
- ✅ Syntax highlighting
- ✅ Timing information
- ✅ Git information

### Priority 2: Fix Index Progress (CRITICAL)

**Implement Story 2.4 properly:**
1. Client creates ClientProgressHandler with Rich progress bar
2. Client passes callback to daemon via `exposed_index(callback=...)`
3. Daemon calls callback for each file
4. RPyC streams updates back to client
5. Client updates progress bar in real-time
6. **Looks identical to standalone mode**

### Priority 3: Add Missing Context Info (HIGH)

Display before results:
- Model being used
- Repository/branch/commit
- Query text
- Filters applied

---

## TESTING REQUIREMENTS

**Before claiming "daemon mode works":**

1. **Visual Diff Test:**
   ```bash
   cidx config --no-daemon
   cidx query "test" --limit 3 > /tmp/standalone.txt

   cidx config --daemon
   cidx query "test" --limit 3 > /tmp/daemon.txt

   diff /tmp/standalone.txt /tmp/daemon.txt
   # Should show MINIMAL differences (only timing differences acceptable)
   ```

2. **Index Progress Test:**
   ```bash
   cidx index --clear
   # Should show: Progress bar, file count, percentage, current file, throughput
   # Should NOT show: "Started in background" with no feedback
   ```

3. **Output Completeness Test:**
   - Full chunk content displayed (not truncated)
   - All metadata fields present
   - Timing breakdown shown
   - Git information displayed

---

## ACCEPTANCE CRITERIA

**Daemon mode is acceptable when:**

1. ✅ Query output identical to standalone (except timing values)
2. ✅ Full chunk content displayed (no truncation)
3. ✅ Progress bars work during index
4. ✅ All metadata fields present
5. ✅ Performance timing shown
6. ✅ Git information displayed
7. ✅ Users cannot tell if daemon is on/off (except for speed)

**Current Status:** 0/7 criteria met

---

## FILES REQUIRING FIXES

1. **src/code_indexer/cli_daemon_fast.py**
   - `_display_results()` - Rewrite to use standalone display function
   - Add query context information display
   - Add timing information display

2. **src/code_indexer/daemon/service.py**
   - `exposed_index()` - Actually implement progress callbacks (Story 2.4)
   - Stream progress to client in real-time

3. **src/code_indexer/cli_daemon_delegation.py**
   - `_query_via_daemon()` - Add timing capture and display
   - Add context information display

---

## ESTIMATED FIX EFFORT

- **Query output fix:** 2-3 hours (reuse existing display code)
- **Index progress fix:** 4-6 hours (implement Story 2.4 properly)
- **Testing/validation:** 2 hours (verify all output matches)

**Total:** 8-11 hours to restore UX parity

---

## PRIORITY

**BLOCKER** - Daemon mode is currently not ready for users due to severe UX degradation. Performance improvements are meaningless if users can't understand or use the output.

**Recommendation:** DO NOT merge daemon mode until UX parity is achieved with standalone mode.

---

## ADDITIONAL REGRESSIONS DISCOVERED

### Watch Command
- **Standalone:** Shows file watching status, updates in real-time
- **Daemon:** Unknown - not tested
- **Severity:** Unknown

### Clean Commands
- **Standalone:** Shows what's being cleaned
- **Daemon:** Unknown - not tested
- **Severity:** Unknown

### Status Command
- **Standalone:** Rich table with complete information
- **Daemon:** N/A (correctly falls back to full CLI)
- **Severity:** None (working correctly)

---

## CONCLUSION

The daemon implementation focused on **performance** and **architecture** but completely neglected **user experience**. The result is a system that is technically sound but **unusable in practice**.

**Critical Path to Production:**
1. Fix query output to match standalone
2. Fix index progress to match standalone
3. Validate watch command works
4. Test all commands for UX parity

**Do not claim daemon mode is "complete" until users cannot tell the difference between daemon and standalone modes (except for the speed).**
