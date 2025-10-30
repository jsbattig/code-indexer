# Integration Tests - CIDX Daemonization

## Overview
**Test Classification:** Integration Tests (Cross-Feature Validation)
**Test Count:** 15 tests
**Estimated Time:** 30-40 minutes
**Purpose:** Validate complex scenarios combining multiple daemon features

## Test Execution Order
Execute tests sequentially TC071 → TC085. These tests combine multiple features and validate end-to-end workflows.

---

## Section 1: Query + Progress + Cache Integration (TC071-TC075)

### TC071: End-to-End Query Workflow with Progress
**Classification:** Integration
**Dependencies:** Smoke + Regression tests passed
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon configured but stopped
- Repository with ~50+ files for meaningful indexing time

**Test Scenario:**
Validate complete workflow: daemon auto-start → indexing with progress → query with cache → performance verification

**Test Steps:**
1. Ensure daemon stopped, cache empty
   ```bash
   cidx stop 2>/dev/null || true
   cidx clean-data
   ```
   - **Expected:** Clean state
   - **Verification:** No daemon, no cache

2. Index repository (triggers auto-start + progress callbacks)
   ```bash
   time cidx index 2>&1 | tee /tmp/index_progress.txt
   ```
   - **Expected:** Daemon auto-starts, progress displayed, indexing completes
   - **Verification:** Progress bar shown, success message

3. Verify daemon started and cache populated
   ```bash
   cidx daemon status | tee /tmp/daemon_after_index.txt
   ```
   - **Expected:** Daemon running, indexes cached
   - **Verification:** running: true, semantic_cached: true

4. Execute query (cache hit)
   ```bash
   time cidx query "authentication login" 2>&1 | tee /tmp/query_result.txt
   ```
   - **Expected:** Fast execution (<1s), results returned
   - **Verification:** Query time recorded, results displayed

5. Verify cache hit performance
   ```bash
   # Parse timing from query output
   cat /tmp/query_result.txt | grep -i "time\|completed"
   ```
   - **Expected:** Sub-1s execution time
   - **Verification:** Performance meets targets

6. Execute FTS query (cache hit)
   ```bash
   time cidx query "def authenticate" --fts
   ```
   - **Expected:** Very fast (<100ms)
   - **Verification:** FTS cache utilized

**Pass Criteria:**
- Complete workflow executes successfully
- Daemon auto-starts on first operation
- Progress callbacks stream during indexing
- Cache populated automatically
- Queries hit cache (fast execution)
- Both semantic and FTS caches working

**Fail Criteria:**
- Any step in workflow fails
- Daemon doesn't auto-start
- Progress not displayed
- Cache not populated
- Slow query performance (cache miss)

---

### TC072: Hybrid Search with Cache Warming
**Classification:** Integration
**Dependencies:** TC071
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Repository indexed

**Test Scenario:**
Validate hybrid search utilizes both caches efficiently, merges results correctly, and maintains performance

**Test Steps:**
1. Cold start - restart daemon
   ```bash
   cidx stop && sleep 2 && cidx start
   ```
   - **Expected:** Clean daemon, empty caches
   - **Verification:** Daemon running, cache_empty: true

2. First hybrid query (cache miss, loads both indexes)
   ```bash
   time cidx query "authentication" --fts --semantic --limit 10 2>&1 | tee /tmp/hybrid_cold.txt
   ```
   - **Expected:** Slower execution (load indexes), results merged
   - **Verification:** Time recorded, combined results

3. Verify both caches populated
   ```bash
   cidx daemon status | grep -E "(semantic_cached|fts_cached)"
   ```
   - **Expected:** Both caches active
   - **Verification:** semantic_cached: true, fts_cached: true

4. Second hybrid query (cache hit, both caches warm)
   ```bash
   time cidx query "payment" --fts --semantic --limit 10 2>&1 | tee /tmp/hybrid_warm.txt
   ```
   - **Expected:** Fast execution (<200ms), results merged
   - **Verification:** Much faster than first query

5. Analyze result merging
   ```bash
   cat /tmp/hybrid_warm.txt | grep -E "(semantic_score|fts_score|combined_score)" | head -5
   ```
   - **Expected:** Results show score breakdown
   - **Verification:** Three score types visible

6. Verify concurrent search execution
   ```bash
   # Hybrid uses ThreadPoolExecutor for parallel search
   # Check that both searches completed
   cat /tmp/hybrid_warm.txt | grep -i "result"
   ```
   - **Expected:** Results from both search types
   - **Verification:** Merged result set

**Pass Criteria:**
- Hybrid search executes both searches
- Results properly merged with combined scoring
- Both caches warm after first query
- Second query utilizes both caches (fast)
- Parallel execution working (ThreadPoolExecutor)

**Fail Criteria:**
- Only one search type executes
- Results not merged correctly
- Cache not utilized
- Slow performance on warm cache
- Scoring incorrect

---

### TC073: Indexing Progress Streaming via Daemon
**Classification:** Integration
**Dependencies:** TC071
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Repository with uncommitted changes

**Test Scenario:**
Validate progress callbacks stream correctly from daemon to client during indexing operations

**Test Steps:**
1. Add multiple new files for indexing
   ```bash
   for i in {1..10}; do
       echo "def test_function_$i(): pass" > test_file_$i.py
   done
   git add test_file_*.py && git commit -m "Add test files"
   ```
   - **Expected:** 10 new files committed
   - **Verification:** Git log shows commit

2. Index with progress monitoring
   ```bash
   cidx index 2>&1 | tee /tmp/index_with_progress.txt
   ```
   - **Expected:** Real-time progress display
   - **Verification:** Progress bar updates, file counts shown

3. Verify progress callback details
   ```bash
   cat /tmp/index_with_progress.txt | grep -E "(\d+/\d+|files|progress|indexing)"
   ```
   - **Expected:** Progress messages with file counts
   - **Verification:** X/Y file format, progress indicators

4. Verify callback routing through daemon
   ```bash
   # Progress should stream via RPyC callback, not local display
   cat /tmp/index_with_progress.txt | head -20
   ```
   - **Expected:** Progress format consistent with daemon streaming
   - **Verification:** No local indexer messages

5. Check indexing completion
   ```bash
   tail -10 /tmp/index_with_progress.txt | grep -i "complete\|success\|done"
   ```
   - **Expected:** Completion message
   - **Verification:** Indexing finished successfully

6. Verify new files queryable
   ```bash
   cidx query "test_function_5" --fts
   ```
   - **Expected:** New file found
   - **Verification:** test_file_5.py in results

7. Cleanup
   ```bash
   git rm test_file_*.py && git commit -m "Cleanup test files"
   ```

**Pass Criteria:**
- Progress callbacks stream in real-time
- File counts accurate (X/Y format)
- Progress displayed correctly on client
- RPyC callback routing working
- Indexing completes successfully
- New files immediately queryable

**Fail Criteria:**
- No progress display
- Inaccurate file counts
- Callback errors
- Indexing failures
- New files not queryable

---

### TC074: Multi-Client Concurrent Query Performance
**Classification:** Integration
**Dependencies:** TC071
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Scenario:**
Validate multiple clients can query concurrently with Reader-Writer lock allowing parallel reads

**Test Steps:**
1. Warm cache with initial query
   ```bash
   cidx query "test" >/dev/null
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache warm
   - **Verification:** semantic_cached: true

2. Execute 5 concurrent queries
   ```bash
   time (
       cidx query "authentication" >/dev/null 2>&1 &
       cidx query "payment" >/dev/null 2>&1 &
       cidx query "user" >/dev/null 2>&1 &
       cidx query "database" >/dev/null 2>&1 &
       cidx query "service" >/dev/null 2>&1 &
       wait
   ) 2>&1 | tee /tmp/concurrent_timing.txt
   ```
   - **Expected:** All queries complete successfully
   - **Verification:** Time for all 5 queries

3. Calculate concurrent performance
   ```bash
   TOTAL_TIME=$(cat /tmp/concurrent_timing.txt | grep real | awk '{print $2}')
   echo "5 concurrent queries completed in: $TOTAL_TIME"
   echo "Expected: <3x single query time (due to parallel reads)"
   ```
   - **Expected:** Total time < 3x single query
   - **Verification:** Parallel execution benefit visible

4. Execute 10 concurrent FTS queries (even faster)
   ```bash
   time (
       for i in {1..10}; do
           cidx query "def" --fts >/dev/null 2>&1 &
       done
       wait
   ) 2>&1 | tee /tmp/concurrent_fts.txt
   ```
   - **Expected:** All complete quickly
   - **Verification:** Total time < 1s

5. Verify daemon handled concurrent load
   ```bash
   cidx daemon status | grep access_count
   ```
   - **Expected:** access_count incremented by 15
   - **Verification:** Count reflects all queries

6. Test semantic + FTS concurrent mix
   ```bash
   time (
       cidx query "auth" >/dev/null 2>&1 &
       cidx query "pay" --fts >/dev/null 2>&1 &
       cidx query "user" >/dev/null 2>&1 &
       cidx query "func" --fts >/dev/null 2>&1 &
       wait
   )
   ```
   - **Expected:** Mixed workload completes successfully
   - **Verification:** No errors, all queries succeed

**Pass Criteria:**
- All concurrent queries complete successfully
- No race conditions or deadlocks
- Reader-Writer lock allows parallel reads
- Performance benefits from concurrency (not serialized)
- Access count accurate
- Mixed semantic/FTS workload works

**Fail Criteria:**
- Queries fail with concurrent access
- Serialized execution (no performance benefit)
- Deadlocks or hangs
- Access count incorrect
- Cache corruption

---

### TC075: Query Result Cache with Different Parameters
**Classification:** Integration
**Dependencies:** TC071
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running with warm index cache

**Test Scenario:**
Validate query result caching provides additional speedup for identical queries while correctly handling parameter variations

**Test Steps:**
1. Execute baseline query
   ```bash
   time cidx query "authentication" --limit 10 2>&1 | tee /tmp/query1.txt
   ```
   - **Expected:** Query completes (index cache hit)
   - **Verification:** Time recorded

2. Execute identical query (result cache hit)
   ```bash
   time cidx query "authentication" --limit 10 2>&1 | tee /tmp/query2.txt
   ```
   - **Expected:** Significantly faster (result cached)
   - **Verification:** Time < query1 time

3. Verify results identical
   ```bash
   diff <(grep "result" /tmp/query1.txt) <(grep "result" /tmp/query2.txt) || echo "Results match"
   ```
   - **Expected:** "Results match"
   - **Verification:** Identical output

4. Execute query with different limit (different cache key)
   ```bash
   time cidx query "authentication" --limit 5 2>&1 | tee /tmp/query3.txt
   ```
   - **Expected:** Slower than query2 (different cache key)
   - **Verification:** New query execution

5. Execute query with different term (different cache key)
   ```bash
   time cidx query "payment" --limit 10 2>&1 | tee /tmp/query4.txt
   ```
   - **Expected:** Slower than query2 (different query)
   - **Verification:** New query execution

6. Verify query cache size
   ```bash
   cidx daemon status | grep query_cache_size
   ```
   - **Expected:** query_cache_size > 0 (tracking cached results)
   - **Verification:** Multiple results cached

7. Test query cache TTL (60 seconds)
   ```bash
   echo "Waiting 65 seconds for query cache expiry..."
   sleep 65
   time cidx query "authentication" --limit 10
   ```
   - **Expected:** Slower (cache expired)
   - **Verification:** Result re-executed

**Pass Criteria:**
- Identical queries use result cache (faster)
- Different parameters trigger new execution
- Results accurate and consistent
- Query cache TTL enforced (60s)
- Cache size reported correctly

**Fail Criteria:**
- No result caching benefit
- Incorrect cache key handling
- Stale results returned
- Cache TTL not enforced
- Cache size incorrect

---

## Section 2: Configuration + Lifecycle + Delegation Integration (TC076-TC080)

### TC076: Complete Daemon Lifecycle with Configuration Persistence
**Classification:** Integration
**Dependencies:** Smoke tests passed
**Estimated Time:** 4 minutes

**Prerequisites:**
- Fresh repository or clean state

**Test Scenario:**
Validate complete daemon lifecycle from initialization through multiple restarts with configuration persistence

**Test Steps:**
1. Initialize with daemon mode
   ```bash
   cd ~/tmp/cidx-lifecycle-test
   git init
   cidx init --daemon
   ```
   - **Expected:** Daemon configuration created
   - **Verification:** Config exists with daemon.enabled: true

2. Customize configuration
   ```bash
   jq '.daemon.ttl_minutes = 20 | .daemon.auto_shutdown_on_idle = true' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Configuration customized
   - **Verification:** Settings updated in file

3. First daemon start (auto-start via query)
   ```bash
   echo "def test(): pass" > test.py
   git add test.py && git commit -m "Test"
   cidx index
   ```
   - **Expected:** Daemon auto-starts, indexes repository
   - **Verification:** Socket created, indexing completes

4. Verify custom configuration applied
   ```bash
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Shows ttl_minutes: 20
   - **Verification:** Custom TTL applied

5. Manual stop and restart
   ```bash
   cidx stop
   sleep 2
   cidx start
   ```
   - **Expected:** Clean stop and restart
   - **Verification:** Daemon restarts successfully

6. Verify configuration persisted
   ```bash
   cidx daemon status | grep ttl_minutes
   cidx config --show | grep "auto_shutdown_on_idle"
   ```
   - **Expected:** Custom settings still applied
   - **Verification:** ttl_minutes: 20, auto_shutdown_on_idle: true

7. Toggle daemon mode off and on
   ```bash
   cidx config --daemon false
   cidx query "test"  # Runs standalone
   cidx config --daemon true
   cidx query "test"  # Auto-starts daemon
   ```
   - **Expected:** Mode toggle works seamlessly
   - **Verification:** Query adapts to mode

8. Final verification
   ```bash
   cidx daemon status
   ls -la .code-indexer/daemon.sock
   ```
   - **Expected:** Daemon operational, socket exists
   - **Verification:** System healthy

**Pass Criteria:**
- Complete lifecycle executes successfully
- Configuration persists across restarts
- Custom settings applied correctly
- Mode toggle seamless
- Auto-start working
- Manual start/stop working

**Fail Criteria:**
- Configuration lost on restart
- Settings not applied
- Mode toggle fails
- Lifecycle steps fail
- Inconsistent state

---

### TC077: Crash Recovery with Configuration Integrity
**Classification:** Integration
**Dependencies:** TC076, TC044-TC047
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon configured and running
- Custom configuration settings

**Test Scenario:**
Validate crash recovery maintains configuration integrity and applies settings after restart

**Test Steps:**
1. Set custom configuration
   ```bash
   jq '.daemon.ttl_minutes = 15 | .daemon.retry_delays_ms = [50, 200, 500, 1000]' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   cidx stop && cidx start
   ```
   - **Expected:** Custom config applied
   - **Verification:** Settings visible in status

2. Warm cache
   ```bash
   cidx query "test"
   cidx daemon status | tee /tmp/status_before_crash.txt
   ```
   - **Expected:** Cache populated
   - **Verification:** semantic_cached: true

3. Simulate crash (kill -9)
   ```bash
   pkill -9 -f rpyc.*daemon
   sleep 1
   ```
   - **Expected:** Daemon killed
   - **Verification:** Process terminated

4. Execute query (triggers crash recovery)
   ```bash
   cidx query "test" 2>&1 | tee /tmp/crash_recovery_config.txt
   ```
   - **Expected:** Crash detected, daemon restarted, query succeeds
   - **Verification:** Restart attempt message, results returned

5. Verify configuration intact after recovery
   ```bash
   cidx daemon status | grep ttl_minutes
   jq '.daemon' .code-indexer/config.json
   ```
   - **Expected:** Custom settings still applied
   - **Verification:** ttl_minutes: 15, custom retry delays

6. Verify daemon operational with correct settings
   ```bash
   cidx daemon status | tee /tmp/status_after_recovery.txt
   diff <(grep ttl_minutes /tmp/status_before_crash.txt) <(grep ttl_minutes /tmp/status_after_recovery.txt) || echo "Settings match"
   ```
   - **Expected:** "Settings match"
   - **Verification:** Configuration persistent through crash

7. Test second crash (exhaust restart attempts)
   ```bash
   pkill -9 -f rpyc.*daemon
   sleep 1
   cidx query "test" 2>&1 | tee /tmp/second_crash.txt
   pkill -9 -f rpyc.*daemon  # Kill during recovery
   sleep 1
   cidx query "test" 2>&1 | tee /tmp/fallback_with_config.txt
   ```
   - **Expected:** Two restart attempts, then fallback
   - **Verification:** Fallback message, query completes standalone

8. Verify configuration still intact after fallback
   ```bash
   jq '.daemon.ttl_minutes' .code-indexer/config.json
   ```
   - **Expected:** Still shows 15
   - **Verification:** Configuration file untouched by crashes

**Pass Criteria:**
- Configuration persists through crashes
- Custom settings applied after recovery
- Crash recovery respects configuration
- Fallback doesn't corrupt configuration
- Config file integrity maintained

**Fail Criteria:**
- Configuration lost on crash
- Settings reset to defaults
- Config file corrupted
- Recovery ignores configuration
- Settings inconsistent

---

### TC078: Storage Commands with Cache Coherence
**Classification:** Integration
**Dependencies:** TC025, TC026, TC036-TC038
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Scenario:**
Validate storage management commands (clean, clean-data, index) maintain cache coherence and never serve stale data

**Test Steps:**
1. Establish warm cache baseline
   ```bash
   cidx query "test"
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache populated
   - **Verification:** semantic_cached: true

2. Query and record result
   ```bash
   cidx query "authentication" --fts | tee /tmp/query_before_clean.txt
   ```
   - **Expected:** Results returned from cache
   - **Verification:** File results visible

3. Execute clean operation (cache invalidation required)
   ```bash
   cidx clean 2>&1 | tee /tmp/clean_operation.txt
   ```
   - **Expected:** Cache invalidated before clean
   - **Verification:** Cache invalidation message

4. Verify cache cleared
   ```bash
   cidx daemon status | grep -E "(cache_empty|semantic_cached)"
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true OR semantic_cached: false

5. Re-index and verify cache rebuilds
   ```bash
   cidx index
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Indexing completes, cache rebuilds
   - **Verification:** semantic_cached: true

6. Query after clean/re-index
   ```bash
   cidx query "authentication" --fts | tee /tmp/query_after_clean.txt
   ```
   - **Expected:** Results returned (cache hit on rebuilt index)
   - **Verification:** Results visible

7. Compare results (should match)
   ```bash
   diff /tmp/query_before_clean.txt /tmp/query_after_clean.txt || echo "Results consistent"
   ```
   - **Expected:** "Results consistent"
   - **Verification:** No data loss

8. Execute clean-data (complete cache invalidation)
   ```bash
   cidx clean-data 2>&1 | tee /tmp/clean_data_operation.txt
   ```
   - **Expected:** Cache invalidated, data removed
   - **Verification:** Success message

9. Verify cache empty and data gone
   ```bash
   cidx daemon status | grep cache
   ls .code-indexer/index/code_vectors/ 2>&1 || echo "Data removed"
   ```
   - **Expected:** Cache empty, index data removed
   - **Verification:** cache_empty: true, directory empty or missing

10. Re-index from scratch
    ```bash
    cidx index
    cidx query "authentication"
    ```
    - **Expected:** Full re-index, query succeeds
    - **Verification:** Complete recovery

**Pass Criteria:**
- Storage commands route to daemon
- Cache invalidated before storage operations
- No stale cache served after storage changes
- Cache coherence maintained throughout
- Complete recovery possible
- Data integrity preserved

**Fail Criteria:**
- Storage commands run locally (bypass daemon)
- Cache not invalidated (stale data served)
- Cache coherence broken
- Data corruption
- Recovery fails

---

### TC079: Status Command Integration Across Modes
**Classification:** Integration
**Dependencies:** TC027, TC076
**Estimated Time:** 3 minutes

**Prerequisites:**
- Repository configured

**Test Scenario:**
Validate status command provides appropriate information in different daemon states and modes

**Test Steps:**
1. Daemon mode enabled, daemon stopped
   ```bash
   cidx config --daemon true
   cidx stop 2>/dev/null || true
   cidx status 2>&1 | tee /tmp/status_enabled_stopped.txt
   ```
   - **Expected:** Status shows daemon configured but not running
   - **Verification:** Configuration visible, daemon not running message

2. Start daemon and check status
   ```bash
   cidx start
   sleep 2
   cidx status | tee /tmp/status_enabled_running.txt
   ```
   - **Expected:** Complete status (daemon + storage)
   - **Verification:** Both sections visible

3. Warm cache and check status
   ```bash
   cidx query "test"
   cidx status | tee /tmp/status_cache_warm.txt
   ```
   - **Expected:** Cache status visible in daemon section
   - **Verification:** semantic_cached: true, access_count > 0

4. Compare status detail
   ```bash
   cat /tmp/status_cache_warm.txt | grep -A 20 "Daemon"
   ```
   - **Expected:** Comprehensive daemon statistics
   - **Verification:** Cache status, access count, TTL, etc.

5. Disable daemon mode
   ```bash
   cidx config --daemon false
   cidx status | tee /tmp/status_disabled.txt
   ```
   - **Expected:** Status shows storage only (no daemon section)
   - **Verification:** Daemon section missing or shows "disabled"

6. Re-enable and compare
   ```bash
   cidx config --daemon true
   cidx query "test"  # Auto-start
   cidx status | tee /tmp/status_reenabled.txt
   ```
   - **Expected:** Daemon section returns
   - **Verification:** Full status with daemon info

7. Test status with watch active
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 2
   cidx status | tee /tmp/status_with_watch.txt
   kill -INT $WATCH_PID
   wait $WATCH_PID 2>/dev/null || true
   ```
   - **Expected:** Watch status included
   - **Verification:** watching: true or watch info shown

**Pass Criteria:**
- Status adapts to daemon state (stopped/running)
- Status adapts to daemon mode (enabled/disabled)
- Daemon section shows comprehensive information when active
- Storage section always present
- Watch status integrated when active
- Status information accurate

**Fail Criteria:**
- Status doesn't reflect actual state
- Missing information in any mode
- Incorrect status reported
- Daemon section shown when disabled
- Status command fails

---

### TC080: Configuration Changes with Active Daemon
**Classification:** Integration
**Dependencies:** TC054-TC057
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Scenario:**
Validate configuration changes require daemon restart to take effect, with clear user feedback

**Test Steps:**
1. Verify current daemon configuration
   ```bash
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Shows current TTL (default 10)
   - **Verification:** ttl_minutes: 10

2. Modify configuration while daemon running
   ```bash
   jq '.daemon.ttl_minutes = 5' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** File updated
   - **Verification:** Config file shows 5

3. Check daemon status (should still show old value)
   ```bash
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Still shows 10 (running daemon not affected)
   - **Verification:** ttl_minutes: 10 (unchanged)

4. Restart daemon to apply changes
   ```bash
   cidx stop && sleep 2 && cidx start
   ```
   - **Expected:** Clean restart
   - **Verification:** Daemon restarted

5. Verify new configuration applied
   ```bash
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Shows new TTL (5)
   - **Verification:** ttl_minutes: 5

6. Test that old config behavior is gone
   ```bash
   cidx query "test"
   # Cache would evict after 5 minutes, not 10
   ```
   - **Expected:** New TTL in effect
   - **Verification:** Configuration applied

7. Restore defaults
   ```bash
   jq '.daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   cidx stop && cidx start
   ```
   - **Expected:** Defaults restored
   - **Verification:** ttl_minutes: 10

**Pass Criteria:**
- Running daemon uses configuration at startup
- Configuration changes don't affect running daemon
- Restart required to apply changes
- New configuration applied after restart
- Clear behavior (no partial application)

**Fail Criteria:**
- Configuration changes applied while running (inconsistent state)
- Restart doesn't apply changes
- Daemon crashes on config change
- Configuration behavior unclear

---

## Section 3: Watch + Daemon + Query Integration (TC081-TC085)

### TC081: Watch Mode Cache Updates with Live Queries
**Classification:** Integration
**Dependencies:** TC065, TC069
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running

**Test Scenario:**
Validate watch mode updates cache in-memory while concurrent queries continue to work with latest data

**Test Steps:**
1. Start watch mode in background
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch running inside daemon
   - **Verification:** Process active

2. Execute baseline query
   ```bash
   cidx query "baseline_function" --fts | tee /tmp/query_before_update.txt
   ```
   - **Expected:** No results (function doesn't exist yet)
   - **Verification:** Empty results or "not found"

3. Add file with target function
   ```bash
   echo "def baseline_function(): pass" >> auth.py
   sleep 3  # Wait for watch to detect and process
   ```
   - **Expected:** File change detected by watch
   - **Verification:** Wait completes

4. Query immediately after change
   ```bash
   cidx query "baseline_function" --fts | tee /tmp/query_after_update.txt
   ```
   - **Expected:** New function found immediately
   - **Verification:** Results include auth.py

5. Verify cache remained warm (not invalidated)
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache still warm (watch updates, doesn't invalidate)
   - **Verification:** semantic_cached: true

6. Execute concurrent queries during watch
   ```bash
   (
       echo "def concurrent_test_1(): pass" >> payment.py
       sleep 1
       cidx query "concurrent_test_1" --fts &
       echo "def concurrent_test_2(): pass" >> auth.py
       sleep 1
       cidx query "concurrent_test_2" --fts &
       wait
   ) | tee /tmp/concurrent_watch_queries.txt
   ```
   - **Expected:** Both queries find their functions
   - **Verification:** Both results successful

7. Verify no query failures during updates
   ```bash
   cat /tmp/concurrent_watch_queries.txt | grep -i "error\|fail" || echo "No errors"
   ```
   - **Expected:** "No errors"
   - **Verification:** Clean concurrent operation

8. Stop watch and cleanup
   ```bash
   cidx watch-stop
   git checkout auth.py payment.py
   ```
   - **Expected:** Watch stops cleanly
   - **Verification:** Statistics displayed

**Pass Criteria:**
- Watch updates cache in-memory
- Queries during watch return latest data immediately
- No cache invalidation (remains warm)
- Concurrent queries during watch work correctly
- No query failures during cache updates
- Cache coherence maintained

**Fail Criteria:**
- Stale results returned
- Cache invalidated (performance loss)
- Query failures during watch updates
- Concurrent query issues
- Cache coherence broken

---

### TC082: Watch Mode with Progress Callbacks and Query Concurrency
**Classification:** Integration
**Dependencies:** TC081, TC067
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running

**Test Scenario:**
Validate watch mode progress callbacks stream correctly while concurrent queries continue to execute

**Test Steps:**
1. Start watch with visible progress
   ```bash
   cidx watch 2>&1 | tee /tmp/watch_with_progress.txt &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch started, progress visible
   - **Verification:** Watch started message

2. Make file change while watching progress
   ```bash
   echo "def progress_test_1(): pass" >> auth.py
   sleep 2
   ```
   - **Expected:** Progress callback fires
   - **Verification:** File processing message in output

3. Execute query during watch update
   ```bash
   cidx query "progress_test_1" --fts &
   QUERY_PID=$!
   ```
   - **Expected:** Query executes concurrently with watch
   - **Verification:** Query doesn't block watch

4. Make another file change
   ```bash
   echo "def progress_test_2(): pass" >> payment.py
   sleep 2
   ```
   - **Expected:** Second progress callback
   - **Verification:** Processing message

5. Wait for query and verify result
   ```bash
   wait $QUERY_PID
   ```
   - **Expected:** Query succeeded during watch activity
   - **Verification:** Results returned

6. Make rapid changes (stress test)
   ```bash
   for i in {1..5}; do
       echo "# Change $i" >> auth.py
       sleep 1
       cidx query "test" >/dev/null &
   done
   wait
   sleep 3  # Let watch catch up
   ```
   - **Expected:** All queries succeed, watch processes all changes
   - **Verification:** No errors

7. Check progress output
   ```bash
   kill -INT $WATCH_PID
   wait $WATCH_PID 2>&1 | tee -a /tmp/watch_with_progress.txt
   cat /tmp/watch_with_progress.txt | grep -i "process\|update\|file" | head -10
   ```
   - **Expected:** Progress messages visible
   - **Verification:** File processing events logged

8. Verify statistics
   ```bash
   tail -10 /tmp/watch_with_progress.txt | grep -E "(files_processed|updates_applied)"
   ```
   - **Expected:** Statistics show activity
   - **Verification:** files_processed >= 7, updates_applied > 0

9. Cleanup
   ```bash
   git checkout auth.py payment.py
   ```

**Pass Criteria:**
- Watch progress callbacks stream correctly
- Concurrent queries execute during watch
- No blocking between watch and queries
- Progress display accurate
- All operations complete successfully
- Statistics reflect all activity

**Fail Criteria:**
- Progress callbacks blocked by queries
- Queries blocked by watch updates
- Missing progress messages
- Operation failures
- Statistics incorrect

---

### TC083: Complete Crash Recovery During Watch
**Classification:** Integration
**Dependencies:** TC052, TC081
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running

**Test Scenario:**
Validate complete system recovery when daemon crashes during active watch mode with ongoing queries

**Test Steps:**
1. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch active
   - **Verification:** Process running

2. Verify watch status
   ```bash
   cidx daemon status | grep -i watch
   ```
   - **Expected:** Watch status shown
   - **Verification:** watching: true

3. Start concurrent query in background
   ```bash
   (
       while true; do
           cidx query "test" >/dev/null 2>&1
           sleep 2
       done
   ) &
   QUERY_LOOP_PID=$!
   sleep 2
   ```
   - **Expected:** Queries running continuously
   - **Verification:** Loop started

4. Kill daemon during active watch + queries
   ```bash
   pkill -9 -f rpyc.*daemon
   sleep 2
   ```
   - **Expected:** Daemon killed
   - **Verification:** Process terminated

5. Execute query (triggers crash recovery)
   ```bash
   cidx query "recovery_test" 2>&1 | tee /tmp/crash_during_watch.txt
   ```
   - **Expected:** Crash detected, daemon restarts, query succeeds
   - **Verification:** Restart message, results returned

6. Verify watch stopped (doesn't auto-resume)
   ```bash
   cidx daemon status | grep -i watch || echo "Watch not running (expected)"
   ```
   - **Expected:** Watch not running after crash
   - **Verification:** No watch status

7. Verify daemon operational
   ```bash
   cidx daemon status | grep running
   ```
   - **Expected:** Daemon running
   - **Verification:** running: true

8. Stop query loop and cleanup
   ```bash
   kill $QUERY_LOOP_PID 2>/dev/null || true
   kill $WATCH_PID 2>/dev/null || true
   wait 2>/dev/null || true
   ```
   - **Expected:** Cleanup successful
   - **Verification:** Processes stopped

9. Verify system fully recovered
   ```bash
   cidx query "test"
   cidx daemon status
   ```
   - **Expected:** All operations work
   - **Verification:** Query succeeds, status returns

**Pass Criteria:**
- Crash detected during watch + queries
- Daemon restarts successfully (2 attempts)
- Watch doesn't auto-resume (expected)
- Queries resume working after recovery
- System reaches stable operational state
- No persistent issues

**Fail Criteria:**
- Crash not detected
- Restart fails
- Watch auto-resumes (wrong behavior)
- Queries fail after recovery
- System in inconsistent state
- Persistent errors

---

### TC084: TTL Eviction with Active Watch
**Classification:** Integration
**Dependencies:** TC039, TC081
**Estimated Time:** 12 minutes (includes wait time)

**Prerequisites:**
- Daemon configured with short TTL for testing

**Test Scenario:**
Validate TTL eviction doesn't interfere with active watch mode, and watch can continue operating after eviction

**Test Steps:**
1. Configure short TTL
   ```bash
   jq '.daemon.ttl_minutes = 2' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   cidx stop && cidx start
   ```
   - **Expected:** TTL set to 2 minutes
   - **Verification:** Configuration applied

2. Warm cache
   ```bash
   cidx query "test"
   cidx daemon status | tee /tmp/status_before_watch.txt
   ```
   - **Expected:** Cache populated
   - **Verification:** semantic_cached: true, last_accessed recorded

3. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch running
   - **Verification:** Process active

4. Wait for TTL expiry (3 minutes for safety)
   ```bash
   echo "Waiting 3 minutes for TTL expiry while watch active..."
   sleep 180
   ```
   - **Expected:** TTL expires
   - **Verification:** Wait completes

5. Check if cache evicted (may not evict if watch keeps accessing)
   ```bash
   cidx daemon status | tee /tmp/status_after_ttl.txt
   cat /tmp/status_after_ttl.txt | grep -E "(cache|last_accessed)"
   ```
   - **Expected:** Either cache evicted OR last_accessed recent (watch activity)
   - **Verification:** Status shows current state

6. Make file change during/after TTL period
   ```bash
   echo "def post_ttl_test(): pass" >> auth.py
   sleep 3
   ```
   - **Expected:** Watch processes change
   - **Verification:** Update processed

7. Query for new function
   ```bash
   cidx query "post_ttl_test" --fts
   ```
   - **Expected:** New function found
   - **Verification:** Results returned

8. Verify watch still operational
   ```bash
   cidx daemon status | grep -i watch
   ```
   - **Expected:** Watch still running
   - **Verification:** watching: true

9. Stop watch and cleanup
   ```bash
   cidx watch-stop
   git checkout auth.py
   jq '.daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Clean stop and config restore
   - **Verification:** Watch stopped, TTL reset

**Pass Criteria:**
- Watch continues operating during TTL period
- Cache eviction doesn't crash watch
- Watch updates continue working
- TTL eviction check doesn't interfere with watch
- System remains stable

**Fail Criteria:**
- Watch crashes during TTL eviction
- Cache eviction breaks watch
- Watch stops working
- System instability

---

### TC085: Complete End-to-End Workflow Integration
**Classification:** Integration
**Dependencies:** All previous tests
**Estimated Time:** 5 minutes

**Prerequisites:**
- Fresh repository or clean state

**Test Scenario:**
Validate complete real-world workflow combining all daemon features: initialization, indexing, queries, watch mode, cache management, crash recovery

**Test Steps:**
1. Initialize fresh repository with daemon
   ```bash
   mkdir -p ~/tmp/cidx-e2e-test
   cd ~/tmp/cidx-e2e-test
   git init
   echo "def authenticate(user, password): return True" > auth.py
   echo "def process_payment(amount): return {'status': 'success'}" > payment.py
   echo "def get_user_data(user_id): return {}" > database.py
   git add . && git commit -m "Initial commit"
   cidx init --daemon
   ```
   - **Expected:** Repository initialized, daemon configured
   - **Verification:** Config created

2. Index repository (daemon auto-starts)
   ```bash
   time cidx index 2>&1 | tee /tmp/e2e_index.txt
   ```
   - **Expected:** Auto-start, progress display, indexing complete
   - **Verification:** Socket created, indexing successful

3. Execute diverse query workload
   ```bash
   cidx query "authentication login" | tee /tmp/e2e_query1.txt
   cidx query "payment" --fts | tee /tmp/e2e_query2.txt
   cidx query "user data" --fts --semantic | tee /tmp/e2e_query3.txt
   ```
   - **Expected:** All queries succeed, varied results
   - **Verification:** Three different result sets

4. Verify cache performance
   ```bash
   time cidx query "authentication login"
   ```
   - **Expected:** Fast execution (<100ms)
   - **Verification:** Cache hit performance

5. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch started in daemon
   - **Verification:** Process active

6. Make changes while watch active
   ```bash
   echo "def new_feature(): pass" >> auth.py
   sleep 3
   cidx query "new_feature" --fts
   ```
   - **Expected:** Change detected, immediately queryable
   - **Verification:** Results include new_feature

7. Execute concurrent queries during watch
   ```bash
   cidx query "authentication" &
   cidx query "payment" --fts &
   cidx query "user" &
   wait
   ```
   - **Expected:** All succeed concurrently
   - **Verification:** No errors

8. Simulate crash and recovery
   ```bash
   pkill -9 -f rpyc.*daemon
   sleep 1
   cidx query "test" 2>&1 | tee /tmp/e2e_recovery.txt
   ```
   - **Expected:** Crash detected, restart attempt, query succeeds
   - **Verification:** Recovery message, results returned

9. Check system health post-recovery
   ```bash
   cidx daemon status | tee /tmp/e2e_final_status.txt
   ```
   - **Expected:** Daemon operational, cache status shown
   - **Verification:** running: true, healthy state

10. Execute storage operations
    ```bash
    cidx clean
    cidx index
    cidx query "authentication"
    ```
    - **Expected:** Complete cycle works
    - **Verification:** Clean, re-index, query all succeed

11. Final verification
    ```bash
    cidx status
    ls -la .code-indexer/
    ps aux | grep rpyc
    ```
    - **Expected:** Complete system operational
    - **Verification:** All components healthy

12. Cleanup
    ```bash
    kill $WATCH_PID 2>/dev/null || true
    cidx stop
    cd ~
    rm -rf ~/tmp/cidx-e2e-test
    ```
    - **Expected:** Clean shutdown and cleanup
    - **Verification:** Resources released

**Pass Criteria:**
- Complete workflow executes successfully
- All daemon features working together
- No conflicts between features
- Performance targets met
- Crash recovery successful
- System reaches stable operational state
- Clean shutdown possible

**Fail Criteria:**
- Any workflow step fails
- Feature conflicts
- Performance degraded
- Recovery fails
- Persistent issues
- Cleanup problems

---

## Integration Test Summary

### Test Coverage Matrix

| Integration Area | Tests | Features Combined |
|------------------|-------|-------------------|
| Query + Progress + Cache | TC071-TC075 (5) | Indexing, queries, caching, performance |
| Config + Lifecycle + Delegation | TC076-TC080 (5) | Configuration, restart, storage, status |
| Watch + Daemon + Query | TC081-TC085 (5) | Watch mode, cache updates, concurrency, recovery |

**Total Tests:** 15
**Total Scenarios:** Complete end-to-end workflows

### Expected Results Summary
- **Complete Workflows:** All executing successfully
- **Feature Integration:** No conflicts, seamless operation
- **Performance:** Targets met in integrated scenarios
- **Crash Recovery:** Working during complex operations
- **Cache Coherence:** Maintained across all features
- **Concurrency:** Multiple features working simultaneously

### Test Execution Time
- **Section 1 (Query Integration):** ~16 minutes
- **Section 2 (Config Integration):** ~18 minutes
- **Section 3 (Watch Integration):** ~29 minutes (includes wait times)
- **Total Estimated Time:** ~63 minutes

### Success Criteria
For integration tests to pass:
- [ ] All 15 tests pass without failures
- [ ] No feature conflicts observed
- [ ] Performance maintained in integrated scenarios
- [ ] System stability demonstrated
- [ ] Real-world workflows validated

### Common Integration Issues
1. **Cache Coherence:** Storage operations during watch
2. **Concurrency:** Multiple queries during cache updates
3. **Recovery:** Crash during watch + queries
4. **Configuration:** Changes during active operations
5. **Performance:** Degradation under combined load

### Next Steps
- If all integration tests pass → **Feature validation complete**
- If failures found → Investigate cross-feature interactions
- Document any integration limitations discovered
- Prepare for production deployment

### Production Readiness Checklist
After completing all test suites:
- [ ] Smoke tests: 20/20 passing
- [ ] Regression tests: 50/50 passing
- [ ] Integration tests: 15/15 passing
- [ ] Performance benchmarks met
- [ ] Crash recovery validated
- [ ] Configuration persistence confirmed
- [ ] Cache coherence demonstrated
- [ ] Concurrent access working
- [ ] Watch mode integration stable
- [ ] Documentation complete

**Total Test Coverage:** 85 manual test cases validating CIDX Daemonization feature
