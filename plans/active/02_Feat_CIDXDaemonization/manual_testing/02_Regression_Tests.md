# Regression Tests - CIDX Daemonization

## Overview
**Test Classification:** Regression Tests (Comprehensive Feature Validation)
**Test Count:** 50 tests
**Estimated Time:** 45-60 minutes
**Purpose:** Validate all daemon features, edge cases, and error handling

## Test Execution Order
Execute tests sequentially TC021 → TC070. Continue on non-critical failures to maximize coverage.

---

## Section 1: Command Routing Validation (TC021-TC033)

### TC021: Query Command Routing
**Classification:** Regression
**Dependencies:** Smoke tests passed
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon enabled and running
- Repository indexed

**Test Steps:**
1. Execute semantic query and capture delegation
   ```bash
   cidx query "authentication" 2>&1 | tee /tmp/query_output.txt
   ```
   - **Expected:** Query executes via daemon
   - **Verification:** Check daemon logs or status for access_count increment

2. Verify no standalone fallback
   ```bash
   cat /tmp/query_output.txt | grep -i "standalone\|fallback" || echo "No fallback"
   ```
   - **Expected:** No fallback messages
   - **Verification:** "No fallback" displayed

3. Check daemon handled query
   ```bash
   cidx daemon status | grep access_count
   ```
   - **Expected:** access_count incremented
   - **Verification:** Count > previous value

**Pass Criteria:**
- Query routed to daemon successfully
- No fallback to standalone
- Daemon statistics updated

**Fail Criteria:**
- Query runs standalone despite daemon enabled
- Fallback messages appear
- Daemon statistics not updated

---

### TC022: Index Command Routing
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Repository with uncommitted changes

**Test Steps:**
1. Add new files
   ```bash
   echo "def test1(): pass" > test1.py
   git add test1.py && git commit -m "Test file"
   ```
   - **Expected:** File committed
   - **Verification:** Git log shows commit

2. Index via daemon
   ```bash
   cidx index 2>&1 | tee /tmp/index_output.txt
   ```
   - **Expected:** Indexing completes, cache invalidated
   - **Verification:** Progress shown, success message

3. Verify routing to daemon
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache invalidated and rebuilt
   - **Verification:** Status shows fresh cache state

**Pass Criteria:**
- Index command routes to daemon
- Cache properly invalidated
- New files indexed correctly

**Fail Criteria:**
- Indexing fails
- Cache not invalidated
- Daemon crashes during indexing

---

### TC023: Watch Command Routing
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start watch via daemon
   ```bash
   timeout 5 cidx watch 2>&1 | head -20
   ```
   - **Expected:** Watch starts inside daemon process
   - **Verification:** Watch started message, no local watch

2. Verify watch in daemon
   ```bash
   cidx daemon status | grep watch
   ```
   - **Expected:** Watching status shown
   - **Verification:** watching: true or watch info displayed

3. Stop watch
   ```bash
   cidx watch-stop
   ```
   - **Expected:** Watch stops
   - **Verification:** Statistics displayed

**Pass Criteria:**
- Watch runs inside daemon (not locally)
- Daemon reports watch status
- Watch stops cleanly

**Fail Criteria:**
- Watch runs locally instead of daemon
- Daemon doesn't report watch status
- Watch fails to stop

---

### TC024: Watch-Stop Command Routing
**Classification:** Regression
**Dependencies:** TC023
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running
- Watch not currently running

**Test Steps:**
1. Execute watch-stop when watch not running
   ```bash
   cidx watch-stop
   ```
   - **Expected:** Graceful message (watch not running)
   - **Verification:** Exit code 1 or warning message

2. Start watch and stop immediately
   ```bash
   cidx watch >/dev/null 2>&1 &
   sleep 2
   cidx watch-stop
   ```
   - **Expected:** Watch stops, statistics shown
   - **Verification:** Files processed count displayed

**Pass Criteria:**
- Watch-stop handles "not running" case
- Successfully stops running watch
- Statistics reported correctly

**Fail Criteria:**
- Command crashes on "not running"
- Fails to stop running watch
- No statistics displayed

---

### TC025: Clean Command Routing
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep cached
   ```
   - **Expected:** Caches active
   - **Verification:** semantic_cached: true

2. Execute clean via daemon
   ```bash
   cidx clean 2>&1 | tee /tmp/clean_output.txt
   ```
   - **Expected:** Clean routes to daemon
   - **Verification:** Output mentions cache invalidation

3. Verify cache cleared
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true or semantic_cached: false

**Pass Criteria:**
- Clean routes to daemon
- Cache invalidated before clean
- Clean operation succeeds

**Fail Criteria:**
- Clean runs locally
- Cache not invalidated
- Clean fails

---

### TC026: Clean-Data Command Routing
**Classification:** Regression
**Dependencies:** TC025
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Execute clean-data via daemon
   ```bash
   cidx clean-data 2>&1 | tee /tmp/clean_data_output.txt
   ```
   - **Expected:** Routes to daemon
   - **Verification:** Cache invalidation message

2. Verify data cleared
   ```bash
   ls .code-indexer/index/
   ```
   - **Expected:** Index directory empty or minimal
   - **Verification:** Vector data removed

3. Verify cache cleared
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true

**Pass Criteria:**
- Clean-data routes to daemon
- Data removed successfully
- Cache invalidated

**Fail Criteria:**
- Command runs locally
- Data not removed
- Cache not invalidated

---

### TC027: Status Command Routing
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Execute status command
   ```bash
   cidx status 2>&1 | tee /tmp/status_output.txt
   ```
   - **Expected:** Comprehensive status with daemon info
   - **Verification:** Shows daemon and storage sections

2. Verify daemon info included
   ```bash
   cat /tmp/status_output.txt | grep -i "daemon"
   ```
   - **Expected:** Daemon section visible
   - **Verification:** Contains daemon statistics

3. Verify mode indicator
   ```bash
   cat /tmp/status_output.txt | grep "mode:"
   ```
   - **Expected:** Shows mode: daemon
   - **Verification:** Correct mode displayed

**Pass Criteria:**
- Status routes to daemon
- Daemon info included
- Mode correctly identified

**Fail Criteria:**
- Status shows only storage info
- Daemon section missing
- Mode incorrect

---

### TC028: Daemon Status Command
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Execute daemon status
   ```bash
   cidx daemon status | tee /tmp/daemon_status.txt
   ```
   - **Expected:** Daemon-specific status
   - **Verification:** Shows running, cache status, access count

2. Verify all status fields
   ```bash
   cat /tmp/daemon_status.txt | grep -E "(running|cached|access_count|ttl_minutes)"
   ```
   - **Expected:** All key fields present
   - **Verification:** Complete status information

**Pass Criteria:**
- Daemon status command works
- All status fields displayed
- Information accurate

**Fail Criteria:**
- Command fails
- Missing status fields
- Incorrect information

---

### TC029: Daemon Clear-Cache Command
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache active
   - **Verification:** true value

2. Clear cache
   ```bash
   cidx daemon clear-cache
   ```
   - **Expected:** Cache cleared successfully
   - **Verification:** Success message

3. Verify cache empty
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true

**Pass Criteria:**
- Clear-cache command works
- Cache actually cleared
- Daemon remains running

**Fail Criteria:**
- Command fails
- Cache not cleared
- Daemon crashes

---

### TC030: FTS Query Routing
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running
- FTS index available

**Test Steps:**
1. Execute FTS query
   ```bash
   time cidx query "def authenticate" --fts
   ```
   - **Expected:** Routes to daemon, FTS results
   - **Verification:** Exact text matches returned

2. Verify FTS cache usage
   ```bash
   cidx daemon status | grep fts
   ```
   - **Expected:** FTS cache active
   - **Verification:** fts_cached: true, fts_available: true

**Pass Criteria:**
- FTS query routes correctly
- FTS cache utilized
- Fast execution (<100ms warm)

**Fail Criteria:**
- Query fails
- Cache not used
- Slow execution

---

### TC031: Hybrid Query Routing
**Classification:** Regression
**Dependencies:** TC021, TC030
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running
- Both caches warm

**Test Steps:**
1. Execute hybrid query
   ```bash
   cidx query "authentication" --fts --semantic
   ```
   - **Expected:** Both searches executed, results merged
   - **Verification:** Combined results with scores

2. Verify both caches used
   ```bash
   cidx daemon status
   ```
   - **Expected:** Both caches active
   - **Verification:** semantic_cached and fts_cached both true

**Pass Criteria:**
- Hybrid query routes correctly
- Results properly merged
- Both caches utilized

**Fail Criteria:**
- Only one search type executes
- Results not merged
- Caches not used

---

### TC032: Start Command
**Classification:** Regression
**Dependencies:** None
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon configured but stopped

**Test Steps:**
1. Start daemon manually
   ```bash
   cidx start
   ```
   - **Expected:** Daemon starts successfully
   - **Verification:** Success message, socket created

2. Verify daemon responsive
   ```bash
   cidx daemon status
   ```
   - **Expected:** Status returned
   - **Verification:** running: true

3. Test duplicate start
   ```bash
   cidx start
   ```
   - **Expected:** Message that daemon already running
   - **Verification:** No error, graceful handling

**Pass Criteria:**
- Start command works
- Daemon becomes operational
- Duplicate start handled gracefully

**Fail Criteria:**
- Start fails
- Daemon unresponsive
- Duplicate start crashes

---

### TC033: Stop Command
**Classification:** Regression
**Dependencies:** TC032
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Stop daemon
   ```bash
   cidx stop
   ```
   - **Expected:** Graceful shutdown
   - **Verification:** Success message, socket removed

2. Verify daemon stopped
   ```bash
   ps aux | grep rpyc | grep -v grep || echo "Daemon stopped"
   ```
   - **Expected:** No daemon process
   - **Verification:** "Daemon stopped" message

3. Test duplicate stop
   ```bash
   cidx stop
   ```
   - **Expected:** Message that daemon not running
   - **Verification:** No error, graceful handling

**Pass Criteria:**
- Stop command works
- Daemon fully terminates
- Duplicate stop handled gracefully

**Fail Criteria:**
- Stop fails
- Process remains running
- Duplicate stop crashes

---

## Section 2: Cache Behavior Validation (TC034-TC043)

### TC034: Cache Hit Performance
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Repository indexed

**Test Steps:**
1. Execute first query (cache miss)
   ```bash
   cidx stop && cidx start
   time cidx query "authentication"
   ```
   - **Expected:** Slower execution (load indexes)
   - **Verification:** Time recorded

2. Execute identical query (cache hit)
   ```bash
   time cidx query "authentication"
   ```
   - **Expected:** Much faster execution
   - **Verification:** Time < first query

3. Measure performance improvement
   ```bash
   # Compare times from above
   echo "Cache hit should be <100ms"
   ```
   - **Expected:** Cache hit <100ms
   - **Verification:** Significant speedup

**Pass Criteria:**
- Cache hit dramatically faster
- Sub-100ms cache hit performance
- Consistent cache hit performance

**Fail Criteria:**
- No performance improvement
- Cache hit >500ms
- Variable performance

---

### TC035: Query Result Caching
**Classification:** Regression
**Dependencies:** TC034
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Execute query twice with same parameters
   ```bash
   time cidx query "authentication" --limit 10
   time cidx query "authentication" --limit 10
   ```
   - **Expected:** Second query even faster (result cache)
   - **Verification:** Second execution <50ms

2. Execute query with different parameters
   ```bash
   time cidx query "authentication" --limit 5
   ```
   - **Expected:** Slightly slower (different query key)
   - **Verification:** Time similar to first query

3. Verify query cache status
   ```bash
   cidx daemon status | grep query_cache
   ```
   - **Expected:** Query cache size shown
   - **Verification:** query_cache_size > 0

**Pass Criteria:**
- Identical queries cached (60s TTL)
- Result cache provides additional speedup
- Query cache size reported

**Fail Criteria:**
- No query result caching
- Same execution time for identical queries
- Query cache not working

---

### TC036: Cache Invalidation on Index
**Classification:** Regression
**Dependencies:** TC022
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** semantic_cached: true
   - **Verification:** Cache active

2. Add new file and index
   ```bash
   echo "def new_test(): pass" > new_test.py
   git add new_test.py && git commit -m "New test"
   cidx index
   ```
   - **Expected:** Indexing completes
   - **Verification:** Progress shown

3. Verify cache invalidated
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache cleared and rebuilt
   - **Verification:** Fresh cache state

4. Verify new file queryable
   ```bash
   cidx query "new_test" --fts
   ```
   - **Expected:** New file found
   - **Verification:** new_test.py in results

**Pass Criteria:**
- Cache invalidated on index
- New content immediately available
- No stale cache issues

**Fail Criteria:**
- Cache not invalidated
- Stale results returned
- New content not queryable

---

### TC037: Cache Invalidation on Clean
**Classification:** Regression
**Dependencies:** TC025
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Populate cache
   ```bash
   cidx query "test"
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache populated
   - **Verification:** semantic_cached: true

2. Execute clean
   ```bash
   cidx clean
   ```
   - **Expected:** Cache invalidated
   - **Verification:** Cache cleared message

3. Verify cache empty
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true or semantic_cached: false

**Pass Criteria:**
- Cache invalidated before clean
- Cache actually cleared
- Cache coherence maintained

**Fail Criteria:**
- Cache not invalidated
- Stale cache remains
- Cache coherence broken

---

### TC038: Cache Invalidation on Clean-Data
**Classification:** Regression
**Dependencies:** TC026
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Populate cache
   ```bash
   cidx query "test"
   ```
   - **Expected:** Cache populated
   - **Verification:** Query succeeds

2. Execute clean-data
   ```bash
   cidx clean-data
   ```
   - **Expected:** Cache invalidated
   - **Verification:** Success message

3. Verify cache empty
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true

**Pass Criteria:**
- Cache invalidated before data removal
- No stale cache pointing to deleted data
- Cache coherence maintained

**Fail Criteria:**
- Cache not invalidated
- Daemon tries to use deleted data
- Crashes or errors

---

### TC039: TTL-Based Cache Eviction
**Classification:** Regression
**Dependencies:** TC034
**Estimated Time:** 12 minutes (includes wait time)

**Prerequisites:**
- Daemon running
- TTL configured to 10 minutes (default)

**Test Steps:**
1. Set TTL to 2 minutes for faster testing
   ```bash
   # Edit config: daemon.ttl_minutes: 2
   jq '.daemon.ttl_minutes = 2' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   cidx stop && cidx start
   ```
   - **Expected:** Config updated, daemon restarted
   - **Verification:** TTL set to 2 minutes

2. Populate cache
   ```bash
   cidx query "test"
   cidx daemon status | grep last_accessed
   ```
   - **Expected:** Cache populated, last_accessed recorded
   - **Verification:** Timestamp shown

3. Wait for TTL expiry
   ```bash
   echo "Waiting 3 minutes for TTL expiry..."
   sleep 180
   ```
   - **Expected:** TTL expires
   - **Verification:** Wait completes

4. Check cache evicted
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache evicted (empty)
   - **Verification:** cache_empty: true or semantic_cached: false

5. Restore TTL
   ```bash
   jq '.daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** TTL restored
   - **Verification:** Config updated

**Pass Criteria:**
- Cache evicted after TTL expiry
- Eviction check runs every 60 seconds
- Cache rebuilds on next query

**Fail Criteria:**
- Cache not evicted after TTL
- Memory leak (cache never evicted)
- Eviction thread not running

---

### TC040: Cache Persistence Across Queries
**Classification:** Regression
**Dependencies:** TC034
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Execute multiple different queries
   ```bash
   cidx query "authentication"
   cidx query "payment"
   cidx query "user"
   cidx query "database"
   ```
   - **Expected:** All queries succeed
   - **Verification:** Results returned for each

2. Verify cache remains warm
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache still active
   - **Verification:** semantic_cached: true

3. Check access count incremented
   ```bash
   cidx daemon status | grep access_count
   ```
   - **Expected:** access_count reflects all queries
   - **Verification:** Count >= 4

**Pass Criteria:**
- Cache persists across multiple queries
- Access count tracks all queries
- No cache thrashing

**Fail Criteria:**
- Cache cleared between queries
- Access count incorrect
- Performance degraded

---

### TC041: FTS Cache Behavior
**Classification:** Regression
**Dependencies:** TC030
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running
- FTS index available

**Test Steps:**
1. Execute first FTS query (cache miss)
   ```bash
   cidx stop && cidx start
   time cidx query "authenticate" --fts
   ```
   - **Expected:** Slower (load Tantivy index)
   - **Verification:** Time recorded

2. Execute second FTS query (cache hit)
   ```bash
   time cidx query "payment" --fts
   ```
   - **Expected:** Much faster (<100ms)
   - **Verification:** Significant speedup

3. Verify FTS cache status
   ```bash
   cidx daemon status | grep fts
   ```
   - **Expected:** FTS cache active
   - **Verification:** fts_cached: true

**Pass Criteria:**
- FTS cache hit <100ms
- Tantivy searcher cached in memory
- Consistent FTS performance

**Fail Criteria:**
- No FTS caching
- Slow FTS queries (>500ms)
- Cache not utilized

---

### TC042: Concurrent Cache Access
**Classification:** Regression
**Dependencies:** TC034
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Execute multiple concurrent queries
   ```bash
   cidx query "authentication" &
   cidx query "payment" &
   cidx query "user" &
   cidx query "database" &
   wait
   ```
   - **Expected:** All queries complete successfully
   - **Verification:** No errors, all results returned

2. Verify daemon handled concurrent access
   ```bash
   cidx daemon status | grep access_count
   ```
   - **Expected:** Access count reflects all queries
   - **Verification:** Count incremented properly

3. Test concurrent read performance
   ```bash
   time (cidx query "test" & cidx query "test" & cidx query "test" & wait)
   ```
   - **Expected:** Fast concurrent execution
   - **Verification:** Total time < 3x single query

**Pass Criteria:**
- Concurrent queries execute correctly
- Reader-Writer lock allows concurrent reads
- No race conditions or errors

**Fail Criteria:**
- Queries fail with concurrent access
- Deadlocks or hangs
- Cache corruption

---

### TC043: Cache Manual Clear and Rebuild
**Classification:** Regression
**Dependencies:** TC029
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache active
   - **Verification:** semantic_cached: true

2. Clear cache manually
   ```bash
   cidx daemon clear-cache
   ```
   - **Expected:** Cache cleared
   - **Verification:** Success message

3. Execute query to rebuild
   ```bash
   time cidx query "test"
   ```
   - **Expected:** Cache rebuilds automatically
   - **Verification:** Slightly slower (load time)

4. Verify cache rebuilt
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache active again
   - **Verification:** semantic_cached: true

**Pass Criteria:**
- Manual clear works correctly
- Cache rebuilds on next query
- No persistent issues

**Fail Criteria:**
- Clear fails
- Cache doesn't rebuild
- Errors after clear

---

## Section 3: Crash Recovery & Error Handling (TC044-TC053)

### TC044: Daemon Crash Detection
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Get daemon process ID
   ```bash
   PID=$(ps aux | grep rpyc | grep daemon | grep -v grep | awk '{print $2}')
   echo "Daemon PID: $PID"
   ```
   - **Expected:** PID found
   - **Verification:** PID printed

2. Kill daemon process (simulate crash)
   ```bash
   kill -9 $PID
   sleep 1
   ```
   - **Expected:** Daemon killed
   - **Verification:** Process terminated

3. Execute query (should trigger crash recovery)
   ```bash
   cidx query "test" 2>&1 | tee /tmp/crash_recovery.txt
   ```
   - **Expected:** Crash detected, restart attempted
   - **Verification:** "attempting restart" in output

4. Verify recovery successful
   ```bash
   cat /tmp/crash_recovery.txt | grep -i "restart\|recovery"
   cidx daemon status
   ```
   - **Expected:** Daemon restarted, query completed
   - **Verification:** Daemon running, results returned

**Pass Criteria:**
- Crash detected automatically
- Restart attempt initiated
- Query completes successfully

**Fail Criteria:**
- Crash not detected
- No restart attempt
- Query fails permanently

---

### TC045: First Restart Attempt
**Classification:** Regression
**Dependencies:** TC044
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Kill daemon
   ```bash
   pkill -9 -f rpyc.*daemon
   ```
   - **Expected:** Daemon killed
   - **Verification:** Process terminated

2. Execute query and watch restart attempt
   ```bash
   cidx query "test" 2>&1 | tee /tmp/restart1.txt
   ```
   - **Expected:** First restart attempt (1/2)
   - **Verification:** "attempting restart (1/2)" in output

3. Verify daemon restarted
   ```bash
   ps aux | grep rpyc | grep -v grep
   cidx daemon status
   ```
   - **Expected:** Daemon running
   - **Verification:** Process exists, status returns

**Pass Criteria:**
- First restart attempt succeeds
- Message indicates "(1/2)"
- Daemon operational after restart

**Fail Criteria:**
- Restart fails
- No restart message
- Daemon not running

---

### TC046: Second Restart Attempt
**Classification:** Regression
**Dependencies:** TC045
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Kill daemon twice quickly
   ```bash
   pkill -9 -f rpyc.*daemon
   sleep 1
   cidx query "test" >/dev/null 2>&1 &  # Triggers first restart
   sleep 2
   pkill -9 -f rpyc.*daemon  # Kill again before query completes
   ```
   - **Expected:** Daemon killed twice
   - **Verification:** Second crash during recovery

2. Execute query to trigger second restart
   ```bash
   cidx query "test" 2>&1 | tee /tmp/restart2.txt
   ```
   - **Expected:** Second restart attempt (2/2)
   - **Verification:** "attempting restart (2/2)" in output

3. Verify daemon restarted
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon running
   - **Verification:** Status returns successfully

**Pass Criteria:**
- Second restart attempt succeeds
- Message indicates "(2/2)"
- System recovers after two crashes

**Fail Criteria:**
- Second restart fails
- Premature fallback
- Daemon not running

---

### TC047: Fallback After Two Restart Failures
**Classification:** Regression
**Dependencies:** TC046
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon configured
- Ability to prevent daemon startup

**Test Steps:**
1. Make socket path unwritable (prevent daemon start)
   ```bash
   sudo chown root:root .code-indexer/
   ```
   - **Expected:** Directory ownership changed
   - **Verification:** Cannot write to directory

2. Kill daemon and attempt query
   ```bash
   pkill -9 -f rpyc.*daemon
   cidx query "test" 2>&1 | tee /tmp/fallback.txt
   ```
   - **Expected:** Two restart attempts, then fallback
   - **Verification:** "fallback to standalone" in output

3. Verify fallback to standalone mode
   ```bash
   cat /tmp/fallback.txt | grep -i "standalone"
   ```
   - **Expected:** Standalone mode message
   - **Verification:** Query completes despite daemon failure

4. Restore permissions
   ```bash
   sudo chown $USER:$USER .code-indexer/
   ```
   - **Expected:** Permissions restored
   - **Verification:** Can write to directory again

**Pass Criteria:**
- Two restart attempts made
- Fallback to standalone after failures
- Query completes successfully in standalone

**Fail Criteria:**
- More than 2 restart attempts
- No fallback mechanism
- Query fails completely

---

### TC048: Exponential Backoff Retry
**Classification:** Regression
**Dependencies:** TC044
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Configure retry delays in config
   ```bash
   jq '.daemon.retry_delays_ms = [100, 500, 1000, 2000]' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Config updated
   - **Verification:** Retry delays configured

2. Stop daemon and remove socket
   ```bash
   cidx stop
   rm -f .code-indexer/daemon.sock
   ```
   - **Expected:** Clean state
   - **Verification:** No daemon, no socket

3. Attempt connection (should retry with backoff)
   ```bash
   time cidx query "test" 2>&1 | tee /tmp/backoff.txt &
   sleep 1
   # Start daemon after first retry
   cidx start
   wait
   ```
   - **Expected:** Retries with exponential backoff
   - **Verification:** Query eventually succeeds

4. Analyze retry timing
   ```bash
   # Check that retries occurred with delays
   cat /tmp/backoff.txt
   ```
   - **Expected:** Multiple retry attempts
   - **Verification:** Evidence of backoff delays

**Pass Criteria:**
- Exponential backoff implemented
- Retry delays: 100ms, 500ms, 1000ms, 2000ms
- Connection eventually succeeds

**Fail Criteria:**
- No retry mechanism
- Fixed delay instead of exponential
- Connection fails despite retries

---

### TC049: Stale Socket Cleanup
**Classification:** Regression
**Dependencies:** TC002
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon stopped
- Stale socket file exists

**Test Steps:**
1. Create stale socket file
   ```bash
   touch .code-indexer/daemon.sock
   ls -la .code-indexer/daemon.sock
   ```
   - **Expected:** Stale socket exists
   - **Verification:** File visible

2. Attempt to start daemon
   ```bash
   cidx start 2>&1 | tee /tmp/stale_socket.txt
   ```
   - **Expected:** Stale socket detected and cleaned
   - **Verification:** Daemon starts successfully

3. Verify socket replaced with valid socket
   ```bash
   ls -la .code-indexer/daemon.sock
   file .code-indexer/daemon.sock
   ```
   - **Expected:** Valid socket file
   - **Verification:** File type is "socket"

**Pass Criteria:**
- Stale socket detected automatically
- Cleanup performed before daemon start
- New valid socket created

**Fail Criteria:**
- Daemon fails due to stale socket
- No cleanup mechanism
- Socket conflict errors

---

### TC050: Connection Refused Handling
**Classification:** Regression
**Dependencies:** TC021
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon configured

**Test Steps:**
1. Stop daemon but leave socket
   ```bash
   cidx stop
   # Manually create socket file (not actual socket)
   touch .code-indexer/daemon.sock
   ```
   - **Expected:** Socket exists but no daemon
   - **Verification:** File exists, no process

2. Attempt query
   ```bash
   cidx query "test" 2>&1 | tee /tmp/conn_refused.txt
   ```
   - **Expected:** Connection refused, retry or fallback
   - **Verification:** Graceful handling, query completes

3. Verify recovery mechanism
   ```bash
   cat /tmp/conn_refused.txt | grep -i "retry\|fallback\|restart"
   ```
   - **Expected:** Recovery attempted
   - **Verification:** Recovery messages present

**Pass Criteria:**
- Connection refusal handled gracefully
- Retry or fallback mechanism triggered
- Query completes (via recovery or fallback)

**Fail Criteria:**
- Immediate failure on connection refused
- No error handling
- Query fails completely

---

### TC051: Daemon Crash During Query
**Classification:** Regression
**Dependencies:** TC044
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start long-running query
   ```bash
   cidx query "test" --limit 100 &
   QUERY_PID=$!
   sleep 1
   ```
   - **Expected:** Query started
   - **Verification:** Process running

2. Kill daemon during query
   ```bash
   pkill -9 -f rpyc.*daemon
   ```
   - **Expected:** Daemon killed mid-query
   - **Verification:** Process terminated

3. Wait for query to complete
   ```bash
   wait $QUERY_PID 2>&1 | tee /tmp/crash_during.txt
   ```
   - **Expected:** Query handles crash, recovers or falls back
   - **Verification:** Query completes (may be via fallback)

4. Verify error handling
   ```bash
   cat /tmp/crash_during.txt
   ```
   - **Expected:** Appropriate error messages
   - **Verification:** Crash detected, recovery attempted

**Pass Criteria:**
- Mid-query crash detected
- Recovery or fallback mechanism activated
- Query completes successfully (or fails gracefully)

**Fail Criteria:**
- Query hangs indefinitely
- No error handling
- Silent failure

---

### TC052: Watch Mode Crash Recovery
**Classification:** Regression
**Dependencies:** TC023, TC044
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running with watch active

**Test Steps:**
1. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch running
   - **Verification:** Process active

2. Kill daemon while watch running
   ```bash
   pkill -9 -f rpyc.*daemon
   ```
   - **Expected:** Daemon and watch terminated
   - **Verification:** Processes killed

3. Execute query (triggers recovery)
   ```bash
   cidx query "test"
   ```
   - **Expected:** Daemon restarts
   - **Verification:** Query succeeds

4. Verify watch stopped
   ```bash
   cidx daemon status | grep watch || echo "Watch not running"
   ```
   - **Expected:** Watch not running after crash
   - **Verification:** No active watch

5. Cleanup
   ```bash
   kill $WATCH_PID 2>/dev/null || true
   ```

**Pass Criteria:**
- Daemon recovers after crash during watch
- Watch doesn't auto-resume (expected behavior)
- System returns to operational state

**Fail Criteria:**
- Daemon fails to recover
- System in inconsistent state
- Watch issues prevent recovery

---

### TC053: Error Message Clarity
**Classification:** Regression
**Dependencies:** TC047
**Estimated Time:** 2 minutes

**Prerequisites:**
- Various error scenarios tested above

**Test Steps:**
1. Review error messages from previous tests
   ```bash
   cat /tmp/crash_recovery.txt /tmp/restart1.txt /tmp/fallback.txt
   ```
   - **Expected:** Clear, actionable messages
   - **Verification:** Messages explain what happened

2. Check for troubleshooting tips
   ```bash
   grep -i "tip\|help\|check" /tmp/*.txt
   ```
   - **Expected:** Helpful guidance provided
   - **Verification:** Troubleshooting suggestions present

3. Verify no misleading messages
   ```bash
   # Manually review messages for accuracy
   cat /tmp/*.txt | grep -i "error\|warning\|failed"
   ```
   - **Expected:** Accurate error descriptions
   - **Verification:** No false positives

**Pass Criteria:**
- Error messages clear and accurate
- Troubleshooting tips provided
- User can understand what went wrong

**Fail Criteria:**
- Cryptic error messages
- No guidance provided
- Misleading information

---

## Section 4: Configuration & Lifecycle (TC054-TC063)

### TC054: Daemon Enable/Disable Toggle
**Classification:** Regression
**Dependencies:** TC019
**Estimated Time:** 3 minutes

**Prerequisites:**
- Repository configured

**Test Steps:**
1. Disable daemon
   ```bash
   cidx config --daemon false
   ```
   - **Expected:** Daemon disabled
   - **Verification:** Success message

2. Verify queries run standalone
   ```bash
   cidx query "test" 2>&1 | grep -i "daemon\|standalone" || echo "Running standalone"
   ```
   - **Expected:** No daemon usage
   - **Verification:** Standalone mode

3. Re-enable daemon
   ```bash
   cidx config --daemon true
   ```
   - **Expected:** Daemon re-enabled
   - **Verification:** Success message

4. Verify queries use daemon again
   ```bash
   cidx query "test"
   cidx daemon status
   ```
   - **Expected:** Daemon auto-starts, query delegated
   - **Verification:** Daemon running, status returns

**Pass Criteria:**
- Toggle works correctly
- Mode switch is seamless
- No errors during transition

**Fail Criteria:**
- Toggle fails
- Mode doesn't change
- Errors during transition

---

### TC055: TTL Configuration
**Classification:** Regression
**Dependencies:** TC039
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon configured

**Test Steps:**
1. Set custom TTL
   ```bash
   jq '.daemon.ttl_minutes = 5' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Config updated
   - **Verification:** TTL set to 5 minutes

2. Restart daemon to apply
   ```bash
   cidx stop && cidx start
   ```
   - **Expected:** Daemon restarted
   - **Verification:** Daemon running

3. Verify TTL applied
   ```bash
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Shows ttl_minutes: 5
   - **Verification:** Custom TTL visible

4. Restore default
   ```bash
   jq '.daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** TTL restored
   - **Verification:** Config updated

**Pass Criteria:**
- Custom TTL configurable
- TTL setting respected
- Configuration persistent

**Fail Criteria:**
- TTL setting ignored
- Configuration not applied
- Errors with custom TTL

---

### TC056: Auto-Shutdown Configuration
**Classification:** Regression
**Dependencies:** TC039
**Estimated Time:** 12 minutes (includes wait time)

**Prerequisites:**
- Daemon configured

**Test Steps:**
1. Enable auto-shutdown with short TTL
   ```bash
   jq '.daemon.auto_shutdown_on_idle = true | .daemon.ttl_minutes = 2' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   cidx stop && cidx start
   ```
   - **Expected:** Config updated, daemon restarted
   - **Verification:** Settings applied

2. Populate cache
   ```bash
   cidx query "test"
   ```
   - **Expected:** Cache populated
   - **Verification:** Query succeeds

3. Wait for TTL + eviction check
   ```bash
   echo "Waiting 3 minutes for TTL + auto-shutdown..."
   sleep 180
   ```
   - **Expected:** Wait completes
   - **Verification:** Time elapsed

4. Verify daemon auto-shutdown
   ```bash
   ps aux | grep rpyc | grep -v grep || echo "Daemon auto-shutdown"
   ls .code-indexer/daemon.sock 2>&1 || echo "Socket removed"
   ```
   - **Expected:** Daemon stopped, socket removed
   - **Verification:** No daemon process, no socket

5. Disable auto-shutdown
   ```bash
   jq '.daemon.auto_shutdown_on_idle = false | .daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Config restored
   - **Verification:** Auto-shutdown disabled

**Pass Criteria:**
- Auto-shutdown triggers after TTL expiry
- Daemon and socket cleaned up
- Configuration setting respected

**Fail Criteria:**
- Daemon doesn't auto-shutdown
- Socket remains after shutdown
- Auto-shutdown triggers prematurely

---

### TC057: Retry Delays Configuration
**Classification:** Regression
**Dependencies:** TC048
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon configured

**Test Steps:**
1. Set custom retry delays
   ```bash
   jq '.daemon.retry_delays_ms = [50, 200, 500, 1000]' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Config updated
   - **Verification:** Custom delays set

2. Restart daemon
   ```bash
   cidx stop && cidx start
   ```
   - **Expected:** Daemon restarted with new config
   - **Verification:** Daemon running

3. Verify configuration
   ```bash
   jq '.daemon.retry_delays_ms' .code-indexer/config.json
   ```
   - **Expected:** Shows custom delays
   - **Verification:** [50, 200, 500, 1000]

4. Restore defaults
   ```bash
   jq '.daemon.retry_delays_ms = [100, 500, 1000, 2000]' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Defaults restored
   - **Verification:** Config updated

**Pass Criteria:**
- Custom retry delays configurable
- Settings applied correctly
- Configuration persistent

**Fail Criteria:**
- Custom delays ignored
- Configuration errors
- Settings not applied

---

### TC058: Daemon Status After Restart
**Classification:** Regression
**Dependencies:** TC020
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Capture status before restart
   ```bash
   cidx daemon status > /tmp/status_before.txt
   ```
   - **Expected:** Status captured
   - **Verification:** File contains status

2. Restart daemon
   ```bash
   cidx stop && sleep 2 && cidx start
   ```
   - **Expected:** Clean restart
   - **Verification:** Daemon running

3. Capture status after restart
   ```bash
   cidx daemon status > /tmp/status_after.txt
   ```
   - **Expected:** Status captured
   - **Verification:** File contains status

4. Compare status (should show clean state)
   ```bash
   diff /tmp/status_before.txt /tmp/status_after.txt || echo "Status differs (expected)"
   cat /tmp/status_after.txt | grep -E "(access_count|cache)"
   ```
   - **Expected:** access_count reset, cache empty
   - **Verification:** Clean daemon state

**Pass Criteria:**
- Status reflects clean daemon state
- Access count reset to 0
- Cache empty after restart

**Fail Criteria:**
- Status shows stale data
- Access count not reset
- Cache incorrectly populated

---

### TC059: Multiple Start Attempts
**Classification:** Regression
**Dependencies:** TC032
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon already running

**Test Steps:**
1. Verify daemon running
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon operational
   - **Verification:** Status returns

2. Attempt second start
   ```bash
   cidx start 2>&1 | tee /tmp/double_start.txt
   ```
   - **Expected:** Graceful message (already running)
   - **Verification:** No error, informative message

3. Verify only one daemon process
   ```bash
   ps aux | grep rpyc | grep daemon | grep -v grep | wc -l
   ```
   - **Expected:** Count is 1
   - **Verification:** Single daemon process

4. Verify daemon still responsive
   ```bash
   cidx daemon status
   ```
   - **Expected:** Status returns correctly
   - **Verification:** Daemon operational

**Pass Criteria:**
- Multiple start attempts handled gracefully
- Socket binding prevents duplicate daemons
- Daemon remains stable

**Fail Criteria:**
- Multiple daemons start
- Error on second start attempt
- Daemon becomes unstable

---

### TC060: Multiple Stop Attempts
**Classification:** Regression
**Dependencies:** TC033
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon stopped

**Test Steps:**
1. Stop daemon
   ```bash
   cidx stop
   ```
   - **Expected:** Daemon stops
   - **Verification:** Success message

2. Attempt second stop
   ```bash
   cidx stop 2>&1 | tee /tmp/double_stop.txt
   ```
   - **Expected:** Graceful message (not running)
   - **Verification:** No error, informative message

3. Verify no daemon process
   ```bash
   ps aux | grep rpyc | grep -v grep || echo "No daemon"
   ```
   - **Expected:** No daemon process
   - **Verification:** "No daemon" message

**Pass Criteria:**
- Multiple stop attempts handled gracefully
- No errors on second stop
- System in consistent state

**Fail Criteria:**
- Errors on second stop
- Inconsistent state
- Socket issues

---

### TC061: Configuration Persistence Across Sessions
**Classification:** Regression
**Dependencies:** TC054
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon configured

**Test Steps:**
1. Configure daemon settings
   ```bash
   cidx config --daemon true
   jq '.daemon.ttl_minutes = 15' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```
   - **Expected:** Configuration saved
   - **Verification:** Settings in config file

2. Stop daemon and simulate session end
   ```bash
   cidx stop
   # Simulate logout/reboot by closing terminal or waiting
   sleep 2
   ```
   - **Expected:** Clean shutdown
   - **Verification:** Daemon stopped

3. Start new session and verify config
   ```bash
   cidx config --show | grep -A 5 "daemon"
   ```
   - **Expected:** Configuration persisted
   - **Verification:** Settings unchanged

4. Start daemon and verify settings applied
   ```bash
   cidx start
   cidx daemon status | grep ttl_minutes
   ```
   - **Expected:** Custom TTL applied
   - **Verification:** ttl_minutes: 15

5. Restore defaults
   ```bash
   jq '.daemon.ttl_minutes = 10' .code-indexer/config.json > /tmp/config.json
   mv /tmp/config.json .code-indexer/config.json
   ```

**Pass Criteria:**
- Configuration persists across daemon restarts
- Settings survive session changes
- Daemon uses persisted configuration

**Fail Criteria:**
- Configuration lost on restart
- Settings revert to defaults
- Configuration file corrupted

---

### TC062: Socket Path Consistency
**Classification:** Regression
**Dependencies:** TC002
**Estimated Time:** 2 minutes

**Prerequisites:**
- Repository with configuration

**Test Steps:**
1. Verify socket path from config location
   ```bash
   CONFIG_DIR=$(dirname $(find . -name config.json -path "*/.code-indexer/*" | head -1))
   echo "Config dir: $CONFIG_DIR"
   echo "Expected socket: $CONFIG_DIR/daemon.sock"
   ```
   - **Expected:** Socket path calculated correctly
   - **Verification:** Path is next to config.json

2. Start daemon and verify socket location
   ```bash
   cidx start
   ls -la $CONFIG_DIR/daemon.sock
   ```
   - **Expected:** Socket at expected location
   - **Verification:** Socket file exists at correct path

3. Test from subdirectory
   ```bash
   mkdir -p subdir/nested
   cd subdir/nested
   cidx query "test"
   ls -la ../../.code-indexer/daemon.sock
   ```
   - **Expected:** Socket still at root .code-indexer/
   - **Verification:** Socket path consistent

4. Cleanup
   ```bash
   cd ../..
   rmdir subdir/nested subdir
   ```

**Pass Criteria:**
- Socket always at .code-indexer/daemon.sock
- Socket path consistent regardless of CWD
- Config backtracking works correctly

**Fail Criteria:**
- Socket in wrong location
- Multiple sockets created
- Path inconsistency

---

### TC063: Daemon Process Cleanup on Exit
**Classification:** Regression
**Dependencies:** TC008
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Get daemon PID and socket
   ```bash
   PID=$(ps aux | grep rpyc | grep daemon | grep -v grep | awk '{print $2}')
   echo "Daemon PID: $PID"
   ls -la .code-indexer/daemon.sock
   ```
   - **Expected:** PID and socket found
   - **Verification:** Both exist

2. Stop daemon gracefully
   ```bash
   cidx stop
   ```
   - **Expected:** Graceful shutdown
   - **Verification:** Success message

3. Verify process fully terminated
   ```bash
   ps -p $PID >/dev/null 2>&1 && echo "Process still running" || echo "Process terminated"
   ```
   - **Expected:** "Process terminated"
   - **Verification:** Process no longer exists

4. Verify socket removed
   ```bash
   ls .code-indexer/daemon.sock 2>&1 || echo "Socket cleaned up"
   ```
   - **Expected:** "Socket cleaned up"
   - **Verification:** Socket file removed

5. Verify no orphaned resources
   ```bash
   lsof | grep daemon.sock || echo "No orphaned handles"
   ```
   - **Expected:** "No orphaned handles"
   - **Verification:** Clean shutdown

**Pass Criteria:**
- Process fully terminated on stop
- Socket file removed
- No orphaned resources

**Fail Criteria:**
- Process remains running
- Socket not cleaned up
- Resource leaks

---

## Section 5: Watch Mode Integration (TC064-TC070)

### TC064: Watch Mode Runs Inside Daemon
**Classification:** Regression
**Dependencies:** TC023
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 3
   ```
   - **Expected:** Watch started
   - **Verification:** Process running

2. Check daemon status shows watch
   ```bash
   cidx daemon status | grep -i "watch"
   ```
   - **Expected:** Watch status included
   - **Verification:** watching: true or watch info shown

3. Verify watch inside daemon (not separate process)
   ```bash
   # Watch thread should be inside daemon process
   ps aux | grep watch | grep -v grep | wc -l
   ```
   - **Expected:** Only main watch command, no separate watch process
   - **Verification:** Watch runs as daemon thread

4. Stop watch
   ```bash
   kill -INT $WATCH_PID
   wait $WATCH_PID
   ```
   - **Expected:** Watch stops gracefully
   - **Verification:** Statistics displayed

**Pass Criteria:**
- Watch runs inside daemon process (thread, not separate process)
- Daemon reports watch status
- Watch integrates with daemon architecture

**Fail Criteria:**
- Watch runs as separate process
- Daemon unaware of watch
- Watch doesn't integrate with daemon

---

### TC065: Watch Updates Cache Directly
**Classification:** Regression
**Dependencies:** TC064
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running with watch active

**Test Steps:**
1. Start watch and verify cache warm
   ```bash
   cidx query "test"  # Warm cache
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Cache warm, watch running
   - **Verification:** Query succeeds

2. Modify file
   ```bash
   echo "def new_watch_test(): pass" >> auth.py
   sleep 3  # Give watch time to detect
   ```
   - **Expected:** File change detected
   - **Verification:** Watch processes update

3. Query immediately (should reflect change)
   ```bash
   cidx query "new_watch_test" --fts
   ```
   - **Expected:** New function found immediately
   - **Verification:** Results include new function

4. Verify cache updated (not reloaded from disk)
   ```bash
   cidx daemon status | grep access_count
   ```
   - **Expected:** Access count incremented (cache hit)
   - **Verification:** No index reload delay

5. Stop watch and cleanup
   ```bash
   kill -INT $WATCH_PID
   wait $WATCH_PID
   git checkout auth.py
   ```

**Pass Criteria:**
- File changes reflected immediately in queries
- Cache updated in-memory (no disk reload)
- Watch mode provides instant index updates

**Fail Criteria:**
- Queries return stale results
- Cache requires disk reload
- Watch updates not reflected

---

### TC066: Watch Stop Without Daemon Stop
**Classification:** Regression
**Dependencies:** TC015
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with watch active

**Test Steps:**
1. Start watch
   ```bash
   cidx watch >/dev/null 2>&1 &
   sleep 2
   ```
   - **Expected:** Watch running
   - **Verification:** Process active

2. Stop watch using watch-stop
   ```bash
   cidx watch-stop
   ```
   - **Expected:** Watch stops, daemon continues
   - **Verification:** Statistics displayed

3. Verify daemon still running
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon operational, watch stopped
   - **Verification:** running: true, watching: false

4. Verify queries still work
   ```bash
   cidx query "test"
   ```
   - **Expected:** Query succeeds
   - **Verification:** Results returned

**Pass Criteria:**
- Watch stops independently of daemon
- Daemon remains operational
- Queries continue working

**Fail Criteria:**
- Daemon stops with watch
- Queries fail after watch stop
- System in inconsistent state

---

### TC067: Watch Progress Callbacks
**Classification:** Regression
**Dependencies:** TC064
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start watch with visible output
   ```bash
   timeout 10 cidx watch 2>&1 | tee /tmp/watch_output.txt &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Watch started with progress display
   - **Verification:** Watch started message

2. Modify file to trigger update
   ```bash
   echo "# Watch test" >> auth.py
   sleep 5  # Allow time for processing
   ```
   - **Expected:** File change detected and processed
   - **Verification:** Progress callback fired

3. Check progress output
   ```bash
   kill -INT $WATCH_PID 2>/dev/null || true
   wait $WATCH_PID 2>/dev/null || true
   cat /tmp/watch_output.txt | grep -i "process\|update\|file"
   ```
   - **Expected:** Progress messages visible
   - **Verification:** File processing reported

4. Cleanup
   ```bash
   git checkout auth.py
   ```

**Pass Criteria:**
- Progress callbacks stream to client
- File processing reported in real-time
- Progress display matches watch activity

**Fail Criteria:**
- No progress output
- Progress not real-time
- Callbacks not working

---

### TC068: Watch Statistics on Stop
**Classification:** Regression
**Dependencies:** TC023
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start watch
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Watch running
   - **Verification:** Process active

2. Make several file changes
   ```bash
   echo "# Change 1" >> auth.py
   sleep 2
   echo "# Change 2" >> payment.py
   sleep 2
   echo "# Change 3" >> auth.py
   sleep 2
   ```
   - **Expected:** Multiple changes detected
   - **Verification:** Files modified

3. Stop watch and capture statistics
   ```bash
   cidx watch-stop 2>&1 | tee /tmp/watch_stats.txt
   ```
   - **Expected:** Statistics displayed
   - **Verification:** Files processed count shown

4. Verify statistics content
   ```bash
   cat /tmp/watch_stats.txt | grep -E "(files_processed|updates_applied)"
   ```
   - **Expected:** Key statistics present
   - **Verification:** files_processed > 0, updates_applied > 0

5. Cleanup
   ```bash
   git checkout auth.py payment.py
   kill $WATCH_PID 2>/dev/null || true
   ```

**Pass Criteria:**
- Statistics displayed on watch stop
- Statistics include files_processed and updates_applied
- Counts are accurate

**Fail Criteria:**
- No statistics displayed
- Statistics missing or incorrect
- Counts don't match activity

---

### TC069: Watch Mode Cache Coherence
**Classification:** Regression
**Dependencies:** TC065
**Estimated Time:** 4 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Warm cache with queries
   ```bash
   cidx query "authentication"
   cidx query "payment"
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache populated
   - **Verification:** semantic_cached: true

2. Start watch mode
   ```bash
   cidx watch >/dev/null 2>&1 &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Watch started
   - **Verification:** Process running

3. Modify file and query immediately
   ```bash
   echo "def cache_coherence_test(): pass" >> auth.py
   sleep 3
   cidx query "cache_coherence_test" --fts
   ```
   - **Expected:** New function found immediately
   - **Verification:** Results include new function

4. Verify cache remained warm (not invalidated)
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache still warm
   - **Verification:** semantic_cached: true (watch updates cache, doesn't invalidate)

5. Stop watch and cleanup
   ```bash
   cidx watch-stop
   git checkout auth.py
   ```

**Pass Criteria:**
- Watch updates maintain cache coherence
- Queries reflect latest changes immediately
- Cache not unnecessarily invalidated

**Fail Criteria:**
- Stale results returned
- Cache invalidated on watch updates (performance loss)
- Cache coherence broken

---

### TC070: Watch Mode Fallback When Daemon Disabled
**Classification:** Regression
**Dependencies:** TC054
**Estimated Time:** 3 minutes

**Prerequisites:**
- Repository configured

**Test Steps:**
1. Disable daemon mode
   ```bash
   cidx config --daemon false
   cidx stop 2>/dev/null || true
   ```
   - **Expected:** Daemon disabled and stopped
   - **Verification:** Configuration updated

2. Start watch (should run locally)
   ```bash
   timeout 5 cidx watch 2>&1 | tee /tmp/watch_local.txt &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Watch runs locally (not in daemon)
   - **Verification:** Watch started message

3. Verify watch running locally
   ```bash
   ps aux | grep watch | grep -v grep
   ```
   - **Expected:** Local watch process visible
   - **Verification:** Process exists

4. Verify no daemon involved
   ```bash
   ps aux | grep rpyc | grep -v grep || echo "No daemon (expected)"
   ```
   - **Expected:** "No daemon (expected)"
   - **Verification:** No daemon process

5. Stop watch and re-enable daemon
   ```bash
   kill -INT $WATCH_PID 2>/dev/null || true
   wait $WATCH_PID 2>/dev/null || true
   cidx config --daemon true
   ```
   - **Expected:** Clean stop, daemon re-enabled
   - **Verification:** Configuration updated

**Pass Criteria:**
- Watch runs locally when daemon disabled
- Fallback to local watch seamless
- No errors during local watch

**Fail Criteria:**
- Watch fails when daemon disabled
- Errors during fallback
- Watch requires daemon

---

## Regression Test Summary

### Test Coverage Matrix

| Feature Area | Tests | Coverage |
|--------------|-------|----------|
| Command Routing | TC021-TC033 (13) | All 13 routed commands |
| Cache Behavior | TC034-TC043 (10) | Hit/miss, TTL, invalidation, concurrency |
| Crash Recovery | TC044-TC053 (10) | Detection, restart, fallback, error handling |
| Configuration | TC054-TC063 (10) | Enable/disable, TTL, persistence, lifecycle |
| Watch Integration | TC064-TC070 (7) | Daemon watch, cache updates, coherence |

**Total Tests:** 50
**Total Coverage:** Comprehensive validation of all daemon features

### Expected Results Summary
- **All Command Routes:** Working correctly
- **Cache Performance:** <100ms hit time
- **Crash Recovery:** 2 restart attempts, graceful fallback
- **TTL Eviction:** Working after expiry
- **Watch Mode:** Integrated with daemon, cache coherence maintained
- **Configuration:** Persistent and functional

### Next Steps
- If all regression tests pass → Proceed to **03_Integration_Tests.md**
- If failures found → Document, investigate, and fix before integration testing
- Track failure patterns for potential systemic issues

### Performance Benchmarks Expected

| Operation | Target | Acceptable | Fail |
|-----------|--------|------------|------|
| Cache Hit Query | <50ms | <100ms | >500ms |
| FTS Query (warm) | <50ms | <100ms | >500ms |
| Daemon Start | <1s | <2s | >5s |
| Crash Recovery | <2s | <5s | >10s |
| Index Load (cold) | <500ms | <1s | >3s |
| TTL Eviction Check | ~60s | ±10s | >90s |

### Common Issues and Solutions

1. **Cache Not Hitting:** Ensure daemon restarted after config changes
2. **Slow Queries:** Check VoyageAI API latency, network issues
3. **Crash Recovery Failures:** Verify socket cleanup between attempts
4. **Watch Mode Issues:** Ensure git repository, file system events working
5. **TTL Not Evicting:** Check eviction thread running (60s intervals)

### Test Execution Time Tracking

| Section | Tests | Est. Time | Actual Time | Status |
|---------|-------|-----------|-------------|---------|
| Command Routing | TC021-TC033 | 25 min | | |
| Cache Behavior | TC034-TC043 | 32 min | | |
| Crash Recovery | TC044-TC053 | 30 min | | |
| Configuration | TC054-TC063 | 25 min | | |
| Watch Integration | TC064-TC070 | 22 min | | |
| **TOTAL** | **50 tests** | **134 min** | | |

**Note:** Actual times may vary due to system performance, API latency, and wait times for TTL/eviction tests. TC039 and TC056 include significant wait times (10+ minutes each).
