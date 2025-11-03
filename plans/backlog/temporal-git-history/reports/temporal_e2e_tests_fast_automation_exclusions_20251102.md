# Temporal Epic E2E Tests - fast-automation.sh Exclusion Analysis

**Date:** November 2, 2025
**Epic:** Temporal Git History Semantic Search
**Purpose:** Ensure E2E/Integration tests are excluded from fast-automation.sh

---

## Executive Summary

**Finding:** Stories contain **Daemon Mode Integration Tests** that will be SLOW and must be excluded from fast-automation.sh

**Stories with Integration/E2E Tests:**
1. ✅ Story 1: Git History Indexing (5 daemon mode tests)
2. ✅ Story 2: Incremental Indexing (daemon mode tests)
3. ✅ Story 3: Selective Branch Indexing (daemon mode tests)
4. ✅ Time-Range Filtering (daemon mode tests)
5. ✅ Point-in-Time Query (daemon mode tests)
6. ✅ Evolution Display (daemon mode tests)
7. ✅ API Server stories (inherently integration tests)

**Action Required:** Add temporal test exclusions to fast-automation.sh

---

## Test Categories in Temporal Stories

### Unit Tests (FAST - Include in fast-automation.sh)
- Test individual components in isolation
- No daemon mode
- No real git operations on large repos
- Use small test fixtures
- Example: `test_git_history_indexing_with_deduplication()`

**Location Pattern:** `tests/unit/services/test_temporal_*.py`
**Speed:** <1 second per test
**Verdict:** ✅ KEEP in fast-automation.sh

---

### Integration Tests - Daemon Mode (SLOW - Exclude from fast-automation.sh)
- Test daemon delegation
- Require daemon startup/shutdown
- Test progress streaming over RPyC
- Test cache invalidation
- Example: `test_temporal_indexing_daemon_delegation()`

**Location Pattern:** `tests/integration/daemon/test_temporal_*.py`
**Speed:** 5-30 seconds per test (daemon startup overhead)
**Verdict:** ❌ EXCLUDE from fast-automation.sh

---

### Integration Tests - Real Git Repos (SLOW - Exclude from fast-automation.sh)
- Use real git repositories (not mocks)
- Process actual commit history
- Test blob extraction with git cat-file
- Example: `test_temporal_indexing_on_real_repo()`

**Location Pattern:** `tests/integration/temporal/test_*.py`
**Speed:** 10-60 seconds per test (git operations)
**Verdict:** ❌ EXCLUDE from fast-automation.sh

---

### Manual Tests (NOT AUTOMATED - No exclusion needed)
- Manual test plans in stories
- Executed by humans, not pytest
- No automated test files

**Location:** Story markdown files only
**Verdict:** N/A (not automated)

---

## Expected Test File Structure

### Story 1: Git History Indexing

**Unit Tests (FAST):**
```
tests/unit/services/test_temporal_indexer.py
tests/unit/services/test_temporal_blob_scanner.py
tests/unit/services/test_git_blob_reader.py
tests/unit/storage/test_blob_registry_sqlite.py
```

**Integration Tests (SLOW):**
```
tests/integration/daemon/test_temporal_indexing_daemon.py
tests/integration/temporal/test_git_history_indexing_e2e.py
```

---

### Story 2: Incremental Indexing

**Unit Tests (FAST):**
```
tests/unit/services/test_incremental_temporal_indexing.py
```

**Integration Tests (SLOW):**
```
tests/integration/daemon/test_incremental_temporal_daemon.py
tests/integration/temporal/test_watch_mode_temporal_updates.py
```

---

### Story 3: Selective Branch Indexing

**Unit Tests (FAST):**
```
tests/unit/services/test_branch_pattern_matching.py
tests/unit/services/test_cost_estimation.py
```

**Integration Tests (SLOW):**
```
tests/integration/daemon/test_selective_branch_daemon.py
tests/integration/temporal/test_multi_branch_indexing_e2e.py
```

---

### Query Stories (Time-Range, Point-in-Time, Evolution)

**Unit Tests (FAST):**
```
tests/unit/services/test_temporal_search_service.py
tests/unit/services/test_temporal_formatter.py
```

**Integration Tests (SLOW):**
```
tests/integration/daemon/test_temporal_query_daemon.py
tests/integration/temporal/test_time_range_query_e2e.py
tests/integration/temporal/test_point_in_time_query_e2e.py
tests/integration/temporal/test_evolution_display_e2e.py
```

---

### API Server Stories

**All tests are Integration Tests (SLOW):**
```
tests/integration/server/test_temporal_registration_api.py
tests/integration/server/test_temporal_query_api.py
tests/integration/server/test_async_job_queue.py
```

**Reason:** API tests require server startup, HTTP requests, real indexing

**Verdict:** ❌ EXCLUDE from fast-automation.sh

---

## Required fast-automation.sh Exclusions

### Current Exclusions (Existing Pattern)
```bash
pytest \
    --ignore=tests/unit/server/ \
    --ignore=tests/unit/infrastructure/ \
    --ignore=tests/unit/api_clients/test_*_real.py \
    ...
```

### NEW Exclusions for Temporal Epic

**Add to fast-automation.sh:**
```bash
pytest \
    # Existing exclusions...
    --ignore=tests/unit/server/ \
    --ignore=tests/unit/infrastructure/ \

    # NEW: Temporal integration tests (daemon mode)
    --ignore=tests/integration/daemon/test_temporal_*.py \

    # NEW: Temporal E2E tests (real git operations)
    --ignore=tests/integration/temporal/ \

    # NEW: API server temporal tests
    --ignore=tests/integration/server/test_temporal_*.py \
    --ignore=tests/integration/server/test_async_job_queue.py \

    # Run all unit tests (fast)
    tests/unit/
```

---

## Detailed Test Identification

### Story 1: Git History Indexing - Test Analysis

**From Story (lines 1849-1975):**

**Unit Tests (FAST):**
- `test_git_history_indexing_with_deduplication()` - Small temp repo
  - File: `tests/unit/services/test_temporal_indexer.py`
  - Speed: <1 second
  - Verdict: ✅ KEEP

**Integration Tests (SLOW):**
- `test_temporal_indexing_daemon_delegation()` - Daemon startup/delegation
  - File: `tests/integration/daemon/test_temporal_indexing_daemon.py`
  - Speed: 5-10 seconds (daemon overhead)
  - Verdict: ❌ EXCLUDE

- `test_temporal_indexing_daemon_cache_invalidation()` - Cache invalidation
  - File: `tests/integration/daemon/test_temporal_indexing_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

- `test_temporal_indexing_progress_streaming()` - Progress over RPyC
  - File: `tests/integration/daemon/test_temporal_indexing_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

- `test_temporal_indexing_fallback_to_standalone()` - Daemon failure fallback
  - File: `tests/integration/daemon/test_temporal_indexing_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

---

### Query Stories - Test Analysis

**From Story (Time-Range Filtering, lines 601+):**

**Daemon Mode Integration Tests:**
- `test_time_range_query_daemon_mode()` - Query delegation to daemon
  - File: `tests/integration/daemon/test_temporal_query_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

- `test_point_in_time_query_daemon_mode()` - Point-in-time via daemon
  - File: `tests/integration/daemon/test_temporal_query_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

- `test_evolution_display_daemon_mode()` - Evolution display via daemon
  - File: `tests/integration/daemon/test_temporal_query_daemon.py`
  - Speed: 5-10 seconds
  - Verdict: ❌ EXCLUDE

---

## Why These Tests Are Slow

### Daemon Mode Tests
**Overhead:**
- Daemon startup: 2-3 seconds
- RPyC connection setup: 0.5-1 second
- Cache warming: 1-2 seconds
- Daemon shutdown: 0.5-1 second
- **Total per test:** 5-10 seconds minimum

**fast-automation.sh goal:** <2.5 minutes total
**Impact:** 10 daemon tests × 8 seconds = 80 seconds (50% of budget!)

**Verdict:** Must exclude to keep fast-automation.sh fast

---

### Real Git Operation Tests
**Overhead:**
- Git repo setup with history: 2-5 seconds
- git ls-tree on 100 commits: 5 seconds
- git cat-file for blobs: 2-3 seconds
- Embedding generation (real API): 10-30 seconds (if not mocked)
- **Total per test:** 20-45 seconds

**fast-automation.sh goal:** <2.5 minutes total
**Impact:** 5 git tests × 30 seconds = 150 seconds (100% of budget!)

**Verdict:** Must exclude to keep fast-automation.sh fast

---

## Recommended fast-automation.sh Update

### Current Structure
```bash
#!/bin/bash
# ... setup ...

# Run fast unit tests only
pytest \
    --ignore=tests/unit/server/ \
    --ignore=tests/unit/infrastructure/ \
    --ignore=tests/unit/api_clients/test_*_real.py \
    tests/unit/
```

### UPDATED Structure (Add Temporal Exclusions)

```bash
#!/bin/bash
# ... setup ...

# Run fast unit tests only
pytest \
    # Existing exclusions (server, infrastructure, real API clients)
    --ignore=tests/unit/server/ \
    --ignore=tests/unit/infrastructure/ \
    --ignore=tests/unit/api_clients/test_base_cidx_remote_api_client_real.py \
    --ignore=tests/unit/api_clients/test_remote_query_client_real.py \
    --ignore=tests/unit/api_clients/test_business_logic_integration_real.py \
    # ... (existing exclusions) ...

    # NEW: Temporal Epic - Daemon mode integration tests (SLOW)
    --ignore=tests/integration/daemon/test_temporal_indexing_daemon.py \
    --ignore=tests/integration/daemon/test_temporal_query_daemon.py \
    --ignore=tests/integration/daemon/test_incremental_temporal_daemon.py \
    --ignore=tests/integration/daemon/test_selective_branch_daemon.py \

    # NEW: Temporal Epic - Real git operation E2E tests (SLOW)
    --ignore=tests/integration/temporal/ \

    # NEW: Temporal Epic - API server tests (SLOW)
    --ignore=tests/integration/server/test_temporal_registration_api.py \
    --ignore=tests/integration/server/test_temporal_query_api.py \
    --ignore=tests/integration/server/test_async_job_queue.py \

    # Run all unit tests (fast)
    tests/unit/
```

**Simpler Alternative (Exclude Entire Directories):**
```bash
pytest \
    --ignore=tests/integration/daemon/ \
    --ignore=tests/integration/temporal/ \
    --ignore=tests/integration/server/ \
    tests/unit/
```

---

## Verification Checklist

After implementing temporal stories, verify:

**1. Test Files Created:**
```bash
find tests/ -name "*temporal*.py" -o -name "*daemon*.py" | sort
```

**2. Check Exclusions Work:**
```bash
./fast-automation.sh
# Should complete in <2.5 minutes
# Should NOT run daemon/temporal integration tests
```

**3. Verify Fast Tests Run:**
```bash
pytest tests/unit/services/test_temporal_*.py -v
# Should run unit tests only
# Should complete in seconds
```

**4. Verify Slow Tests Excluded:**
```bash
pytest tests/integration/daemon/ -v
# Should run all daemon integration tests
# Will be SLOW (5-10 seconds per test)
# Only run in full-automation.sh
```

---

## full-automation.sh Behavior

**No exclusions needed in full-automation.sh:**
```bash
#!/bin/bash
# ... setup ...

# Run ALL tests (including slow integration tests)
pytest tests/
```

**Purpose:**
- Run complete test suite
- Include daemon mode tests
- Include real git operation tests
- Include API server tests
- Complete validation before releases

**Expected Runtime:**
- fast-automation.sh: <2.5 minutes (unit tests only)
- full-automation.sh: 10-15 minutes (all tests)

---

## Summary

**Action Required:** ✅ YES - Add temporal test exclusions to fast-automation.sh

**Test Categories:**
- ✅ Unit tests: KEEP in fast-automation.sh
- ❌ Daemon mode integration tests: EXCLUDE from fast-automation.sh
- ❌ Real git operation tests: EXCLUDE from fast-automation.sh
- ❌ API server tests: EXCLUDE from fast-automation.sh

**Exclusion Pattern (Recommended):**
```bash
--ignore=tests/integration/daemon/ \
--ignore=tests/integration/temporal/ \
--ignore=tests/integration/server/test_temporal_*.py \
```

**Estimated Impact:**
- Without exclusions: fast-automation.sh would take 10-15 minutes (SLOW)
- With exclusions: fast-automation.sh remains <2.5 minutes (FAST)

**Verification:**
- Check after implementing each story
- Ensure fast-automation.sh stays fast
- Run full-automation.sh for complete validation

---

**END OF REPORT**
