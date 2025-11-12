# Smoke Tests - CIDX Daemonization

## Overview
**Test Classification:** Smoke Tests (Critical Path)
**Test Count:** 20 tests
**Estimated Time:** 15-20 minutes
**Purpose:** Validate essential daemon functionality required for basic operation

## Test Execution Order
Execute tests sequentially TC001 → TC020. Stop on critical failure that blocks subsequent tests.

---

## TC001: Daemon Configuration Initialization
**Classification:** Smoke Test
**Dependencies:** None
**Estimated Time:** 2 minutes

**Prerequisites:**
- Fresh test repository created
- No existing `.code-indexer/` directory

**Test Steps:**
1. Create test repository
   ```bash
   mkdir -p ~/tmp/cidx-test-daemon
   cd ~/tmp/cidx-test-daemon
   git init
   ```
   - **Expected:** Git repository created
   - **Verification:** `git status` shows clean repo

2. Initialize CIDX with daemon mode
   ```bash
   cidx init --daemon
   ```
   - **Expected:** Configuration created with daemon enabled
   - **Verification:** `.code-indexer/config.json` exists

3. Verify daemon configuration
   ```bash
   cat .code-indexer/config.json | grep -A 5 '"daemon"'
   ```
   - **Expected:** Shows daemon configuration block
   - **Verification:** Contains `"enabled": true`, `"ttl_minutes": 10`

**Pass Criteria:**
- Configuration file created at `.code-indexer/config.json`
- Daemon configuration present with `enabled: true`
- TTL set to default 10 minutes

**Fail Criteria:**
- Configuration file not created
- Daemon section missing
- Daemon enabled is false

---

## TC002: Socket Path Verification
**Classification:** Smoke Test
**Dependencies:** TC001
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon configuration initialized (TC001 passed)
- Daemon not yet started

**Test Steps:**
1. Verify socket does not exist before daemon start
   ```bash
   ls .code-indexer/daemon.sock
   ```
   - **Expected:** File not found error
   - **Verification:** Exit code is non-zero

2. Check socket path location
   ```bash
   echo "Socket should be at: $(pwd)/.code-indexer/daemon.sock"
   ```
   - **Expected:** Path printed correctly
   - **Verification:** Path is next to config.json

**Pass Criteria:**
- Socket path is `.code-indexer/daemon.sock` (next to config)
- Socket does not exist before daemon starts

**Fail Criteria:**
- Socket exists before daemon start (stale socket)
- Socket path is in wrong location

---

## TC003: Daemon Auto-Start on First Query
**Classification:** Smoke Test
**Dependencies:** TC001, TC002
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon configured but not running
- Test files indexed in repository

**Test Steps:**
1. Create test files
   ```bash
   echo "def authenticate_user(username, password): return True" > auth.py
   echo "def process_payment(amount): return {'status': 'success'}" > payment.py
   git add . && git commit -m "Add test files"
   ```
   - **Expected:** Test files created and committed
   - **Verification:** `git log` shows commit

2. Index repository (first operation)
   ```bash
   cidx index
   ```
   - **Expected:** Daemon auto-starts, indexing completes
   - **Verification:** Indexing progress shown, no errors

3. Verify daemon started automatically
   ```bash
   ls -la .code-indexer/daemon.sock
   ```
   - **Expected:** Socket file exists with correct permissions
   - **Verification:** Socket file visible with `srwxr-xr-x` permissions

4. Verify daemon process running
   ```bash
   ps aux | grep rpyc | grep -v grep
   ```
   - **Expected:** Daemon process visible
   - **Verification:** Process contains "rpyc" and socket path

**Pass Criteria:**
- Daemon starts automatically on first operation
- Socket file created successfully
- Daemon process running in background
- No errors during startup

**Fail Criteria:**
- Daemon fails to auto-start
- Socket file not created
- Errors during daemon startup

---

## TC004: Semantic Query Delegation
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running
- Repository indexed
- VoyageAI API key configured

**Test Steps:**
1. Execute semantic search query
   ```bash
   time cidx query "authentication login user"
   ```
   - **Expected:** Query executes via daemon, results returned
   - **Verification:** Results show auth.py file, execution time displayed

2. Verify query routed to daemon
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon status shows semantic index cached
   - **Verification:** `semantic_cached: true`, `access_count > 0`

3. Execute second query (cache hit)
   ```bash
   time cidx query "payment processing"
   ```
   - **Expected:** Faster execution (cache hit)
   - **Verification:** Execution time <1s, results include payment.py

**Pass Criteria:**
- Semantic queries execute successfully
- Results accurate (relevant files returned)
- Second query faster than first (cache hit)
- Daemon status confirms cache usage

**Fail Criteria:**
- Query fails or times out
- No results returned
- Cache not utilized (same execution time)
- Daemon status shows no cache

---

## TC005: FTS Query Delegation
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running
- Repository indexed with FTS
- Tantivy index available

**Test Steps:**
1. Execute FTS search query
   ```bash
   time cidx query "authenticate_user" --fts
   ```
   - **Expected:** FTS query executes, exact text match returned
   - **Verification:** Results show auth.py with exact function name

2. Verify FTS cache status
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon shows FTS cached
   - **Verification:** `fts_cached: true`, `fts_available: true`

3. Execute second FTS query (cache hit)
   ```bash
   time cidx query "process_payment" --fts
   ```
   - **Expected:** Very fast execution (<100ms)
   - **Verification:** Results show payment.py, sub-100ms time

**Pass Criteria:**
- FTS queries execute successfully
- Exact text matches returned
- Cache hit performance <100ms
- Daemon caches Tantivy searcher

**Fail Criteria:**
- FTS query fails
- Wrong results (semantic instead of exact match)
- Cache not utilized
- Execution time >500ms on cache hit

---

## TC006: Hybrid Search Delegation
**Classification:** Smoke Test
**Dependencies:** TC004, TC005
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with both caches warm
- Repository indexed with semantic + FTS

**Test Steps:**
1. Execute hybrid search query
   ```bash
   time cidx query "authentication" --fts --semantic
   ```
   - **Expected:** Both semantic and FTS results merged
   - **Verification:** Results from both searches combined

2. Verify result merging
   ```bash
   cidx query "auth" --fts --semantic --limit 10
   ```
   - **Expected:** Results show combined scores
   - **Verification:** Output includes semantic_score, fts_score, combined_score

**Pass Criteria:**
- Hybrid queries execute successfully
- Results merged correctly from both sources
- Combined scoring applied
- Execution fast with warm cache

**Fail Criteria:**
- Hybrid query fails
- Only one search type executed
- Results not properly merged
- Execution time excessive

---

## TC007: Daemon Status Command
**Classification:** Smoke Test
**Dependencies:** TC004, TC005
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running
- Queries executed (caches warm)

**Test Steps:**
1. Check daemon status
   ```bash
   cidx daemon status
   ```
   - **Expected:** Complete daemon status displayed
   - **Verification:** Shows running: true, cache status, access count

2. Verify cache information
   ```bash
   cidx daemon status | grep -E "(semantic_cached|fts_cached|access_count)"
   ```
   - **Expected:** Cache status and access metrics shown
   - **Verification:** Both caches true, access_count > 0

**Pass Criteria:**
- Status command executes successfully
- Shows daemon running state
- Displays cache status (semantic + FTS)
- Shows access statistics

**Fail Criteria:**
- Status command fails
- Incomplete information displayed
- Wrong cache state reported

---

## TC008: Manual Daemon Stop
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Stop daemon gracefully
   ```bash
   cidx stop
   ```
   - **Expected:** Daemon stops, socket removed
   - **Verification:** Success message displayed

2. Verify daemon stopped
   ```bash
   ps aux | grep rpyc | grep -v grep
   ```
   - **Expected:** No daemon process found
   - **Verification:** Empty output

3. Verify socket removed
   ```bash
   ls .code-indexer/daemon.sock
   ```
   - **Expected:** File not found
   - **Verification:** Error message (file doesn't exist)

4. Verify process fully terminated
   ```bash
   lsof | grep daemon.sock || echo "Socket fully closed"
   ```
   - **Expected:** No processes holding socket
   - **Verification:** "Socket fully closed" message

**Pass Criteria:**
- Stop command executes successfully
- Daemon process terminated
- Socket file removed
- Clean shutdown (no errors)

**Fail Criteria:**
- Stop command fails
- Daemon process still running
- Socket file remains
- Errors during shutdown

---

## TC009: Manual Daemon Start
**Classification:** Smoke Test
**Dependencies:** TC008
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon stopped (TC008 passed)
- Configuration still enabled

**Test Steps:**
1. Manually start daemon
   ```bash
   cidx start
   ```
   - **Expected:** Daemon starts successfully
   - **Verification:** Success message displayed

2. Verify daemon running
   ```bash
   ps aux | grep rpyc | grep -v grep
   ```
   - **Expected:** Daemon process visible
   - **Verification:** Process running with rpyc

3. Verify socket created
   ```bash
   ls -la .code-indexer/daemon.sock
   ```
   - **Expected:** Socket file exists
   - **Verification:** Socket visible with correct permissions

4. Test daemon responsive
   ```bash
   cidx daemon status
   ```
   - **Expected:** Status returned successfully
   - **Verification:** Shows running: true

**Pass Criteria:**
- Start command executes successfully
- Daemon process starts
- Socket file created
- Daemon responsive to commands

**Fail Criteria:**
- Start command fails
- Daemon doesn't start
- Socket not created
- Daemon unresponsive

---

## TC010: Query After Daemon Restart
**Classification:** Smoke Test
**Dependencies:** TC009
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon freshly started (TC009 passed)
- Repository still indexed

**Test Steps:**
1. Execute query after daemon restart
   ```bash
   time cidx query "authentication"
   ```
   - **Expected:** Query executes (cache miss, reload from disk)
   - **Verification:** Results returned, slightly slower (index load)

2. Execute second query (cache hit)
   ```bash
   time cidx query "payment"
   ```
   - **Expected:** Fast execution (cache hit)
   - **Verification:** Sub-1s execution time

3. Verify cache rebuilt
   ```bash
   cidx daemon status
   ```
   - **Expected:** Caches populated
   - **Verification:** semantic_cached: true, access_count > 0

**Pass Criteria:**
- Queries work after daemon restart
- Cache rebuilds on first query
- Subsequent queries hit cache
- No errors during cache rebuild

**Fail Criteria:**
- Queries fail after restart
- Cache doesn't rebuild
- Performance degraded permanently

---

## TC011: Configuration Display
**Classification:** Smoke Test
**Dependencies:** TC001
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon configuration initialized

**Test Steps:**
1. Display full configuration
   ```bash
   cidx config --show
   ```
   - **Expected:** Complete config displayed
   - **Verification:** Daemon section visible with all settings

2. Verify daemon settings visible
   ```bash
   cidx config --show | grep -A 10 "daemon:"
   ```
   - **Expected:** Daemon configuration block shown
   - **Verification:** Shows enabled, ttl_minutes, retry settings

**Pass Criteria:**
- Config command shows all settings
- Daemon section clearly visible
- All daemon parameters displayed

**Fail Criteria:**
- Config command fails
- Daemon section missing
- Incomplete information shown

---

## TC012: Cache Clear Command
**Classification:** Smoke Test
**Dependencies:** TC010
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache
- Previous queries executed

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Shows semantic_cached: true
   - **Verification:** Cache is active

2. Clear cache manually
   ```bash
   cidx daemon clear-cache
   ```
   - **Expected:** Cache cleared successfully
   - **Verification:** Success message displayed

3. Verify cache empty
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache shows as empty
   - **Verification:** cache_empty: true OR semantic_cached: false

4. Execute query to rebuild cache
   ```bash
   cidx query "test"
   ```
   - **Expected:** Query rebuilds cache
   - **Verification:** Query succeeds, cache repopulates

**Pass Criteria:**
- Clear cache command works
- Cache actually cleared
- Daemon remains running
- Cache rebuilds on next query

**Fail Criteria:**
- Clear command fails
- Cache not cleared
- Daemon crashes during clear

---

## TC013: Indexing Operation
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Repository with files to index

**Test Steps:**
1. Add new file to repository
   ```bash
   echo "def new_function(): pass" > new_file.py
   git add new_file.py && git commit -m "Add new file"
   ```
   - **Expected:** New file committed
   - **Verification:** `git log` shows commit

2. Re-index repository via daemon
   ```bash
   cidx index
   ```
   - **Expected:** Indexing completes, cache invalidated
   - **Verification:** Progress shown, no errors

3. Verify new file queryable
   ```bash
   cidx query "new_function" --fts
   ```
   - **Expected:** New file found in results
   - **Verification:** Results include new_file.py

4. Verify cache invalidated and rebuilt
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache shows rebuilt
   - **Verification:** access_count reset or low value

**Pass Criteria:**
- Indexing via daemon succeeds
- Cache properly invalidated
- New files immediately queryable
- No errors during indexing

**Fail Criteria:**
- Indexing fails
- Cache not invalidated
- New files not queryable
- Daemon crashes during indexing

---

## TC014: Watch Mode Start
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running
- Repository indexed

**Test Steps:**
1. Start watch mode via daemon
   ```bash
   cidx watch &
   WATCH_PID=$!
   sleep 2
   ```
   - **Expected:** Watch starts inside daemon
   - **Verification:** Watch started message displayed

2. Verify watch status
   ```bash
   cidx daemon status | grep watch
   ```
   - **Expected:** Shows watching: true
   - **Verification:** Watch status visible in daemon info

3. Stop watch gracefully
   ```bash
   kill -INT $WATCH_PID
   wait $WATCH_PID
   ```
   - **Expected:** Watch stops cleanly
   - **Verification:** Statistics displayed (files processed, updates applied)

**Pass Criteria:**
- Watch starts successfully via daemon
- Watch status reported correctly
- Watch stops cleanly with statistics

**Fail Criteria:**
- Watch fails to start
- Daemon crashes during watch
- Watch doesn't stop gracefully

---

## TC015: Watch-Stop Command
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Start watch mode in background
   ```bash
   cidx watch >/dev/null 2>&1 &
   sleep 3
   ```
   - **Expected:** Watch running in background
   - **Verification:** Process started

2. Stop watch using watch-stop command
   ```bash
   cidx watch-stop
   ```
   - **Expected:** Watch stops, statistics shown
   - **Verification:** Files processed count displayed

3. Verify daemon still running
   ```bash
   cidx daemon status
   ```
   - **Expected:** Daemon running, watch stopped
   - **Verification:** running: true, watching: false

4. Test queries still work
   ```bash
   cidx query "test"
   ```
   - **Expected:** Query succeeds
   - **Verification:** Results returned

**Pass Criteria:**
- Watch-stop command stops watch without stopping daemon
- Statistics displayed correctly
- Daemon remains operational
- Queries continue to work

**Fail Criteria:**
- Watch-stop fails
- Daemon stops with watch
- Queries broken after watch stop

---

## TC016: Clean Operation with Cache Invalidation
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache
- Repository indexed

**Test Steps:**
1. Verify cache populated
   ```bash
   cidx daemon status | grep semantic_cached
   ```
   - **Expected:** Cache active
   - **Verification:** semantic_cached: true

2. Execute clean operation via daemon
   ```bash
   cidx clean
   ```
   - **Expected:** Vectors cleared, cache invalidated
   - **Verification:** Success message with cache_invalidated: true

3. Verify cache cleared
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty or invalidated
   - **Verification:** semantic_cached: false OR cache_empty: true

4. Re-index and verify recovery
   ```bash
   cidx index
   cidx query "test"
   ```
   - **Expected:** Indexing and querying work
   - **Verification:** Query returns results

**Pass Criteria:**
- Clean operation routes to daemon
- Cache invalidated before clean
- Cache coherence maintained
- System recovers after clean

**Fail Criteria:**
- Clean fails
- Cache not invalidated
- Daemon serves stale cache
- System broken after clean

---

## TC017: Clean-Data Operation with Cache Invalidation
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 2 minutes

**Prerequisites:**
- Daemon running with warm cache
- Repository indexed

**Test Steps:**
1. Execute clean-data via daemon
   ```bash
   cidx clean-data
   ```
   - **Expected:** Project data cleared, cache invalidated
   - **Verification:** Success message with cache_invalidated: true

2. Verify cache cleared
   ```bash
   cidx daemon status
   ```
   - **Expected:** Cache empty
   - **Verification:** cache_empty: true

3. Re-index and verify recovery
   ```bash
   cidx index
   cidx query "test"
   ```
   - **Expected:** Full recovery
   - **Verification:** Indexing and querying work

**Pass Criteria:**
- Clean-data routes to daemon
- Cache invalidated before data removal
- Cache coherence maintained
- Full recovery possible

**Fail Criteria:**
- Clean-data fails
- Cache not invalidated
- Daemon crashes
- Recovery not possible

---

## TC018: Status Command with Daemon Info
**Classification:** Smoke Test
**Dependencies:** TC003
**Estimated Time:** 1 minute

**Prerequisites:**
- Daemon running

**Test Steps:**
1. Execute status command
   ```bash
   cidx status
   ```
   - **Expected:** Shows both daemon and storage status
   - **Verification:** Output contains "Daemon Status" and "Storage Status" sections

2. Verify daemon info included
   ```bash
   cidx status | grep -A 5 "Daemon"
   ```
   - **Expected:** Daemon statistics visible
   - **Verification:** Shows cache status, access count, etc.

**Pass Criteria:**
- Status command shows comprehensive info
- Daemon section included when enabled
- Both daemon and storage info displayed

**Fail Criteria:**
- Status command fails
- Daemon info missing
- Incomplete status information

---

## TC019: Daemon Configuration Toggle
**Classification:** Smoke Test
**Dependencies:** TC001, TC008
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon configured and stopped

**Test Steps:**
1. Disable daemon mode
   ```bash
   cidx config --daemon false
   ```
   - **Expected:** Daemon disabled in config
   - **Verification:** Success message displayed

2. Verify daemon disabled
   ```bash
   cidx config --show | grep "daemon"
   ```
   - **Expected:** Shows enabled: false
   - **Verification:** Configuration updated

3. Execute query in standalone mode
   ```bash
   cidx query "test"
   ```
   - **Expected:** Query runs locally (not via daemon)
   - **Verification:** No daemon startup, query succeeds

4. Re-enable daemon mode
   ```bash
   cidx config --daemon true
   ```
   - **Expected:** Daemon re-enabled
   - **Verification:** enabled: true in config

5. Verify query uses daemon again
   ```bash
   cidx query "test"
   ```
   - **Expected:** Daemon auto-starts, query delegated
   - **Verification:** Socket created, daemon process running

**Pass Criteria:**
- Daemon can be enabled/disabled via config
- Queries adapt to current mode
- Transition between modes seamless

**Fail Criteria:**
- Configuration toggle fails
- Queries fail during mode transition
- Daemon state inconsistent

---

## TC020: Daemon Restart Persistence
**Classification:** Smoke Test
**Dependencies:** TC009
**Estimated Time:** 3 minutes

**Prerequisites:**
- Daemon running
- Queries executed (cache warm)

**Test Steps:**
1. Note daemon status
   ```bash
   cidx daemon status > /tmp/daemon_status_before.txt
   cat /tmp/daemon_status_before.txt
   ```
   - **Expected:** Status captured
   - **Verification:** File contains daemon info

2. Stop and restart daemon
   ```bash
   cidx stop
   sleep 2
   cidx start
   sleep 2
   ```
   - **Expected:** Clean stop and restart
   - **Verification:** No errors, socket recreated

3. Verify daemon operational
   ```bash
   cidx daemon status > /tmp/daemon_status_after.txt
   ```
   - **Expected:** Daemon running, cache empty (cold start)
   - **Verification:** running: true, cache_empty: true OR semantic_cached: false

4. Execute query to warm cache
   ```bash
   cidx query "test"
   ```
   - **Expected:** Cache rebuilds
   - **Verification:** Query succeeds

5. Verify persistent configuration
   ```bash
   cidx config --show | grep "enabled"
   ```
   - **Expected:** Daemon still enabled
   - **Verification:** Configuration persisted across restarts

**Pass Criteria:**
- Daemon survives stop/start cycle
- Configuration persists
- Cache rebuilds correctly
- No data loss

**Fail Criteria:**
- Daemon fails to restart
- Configuration lost
- Cache doesn't rebuild
- Persistent errors after restart

---

## Smoke Test Summary

### Quick Status Check
After completing all smoke tests, verify overall system health:

```bash
# Daemon running
ps aux | grep rpyc | grep -v grep

# Socket exists
ls -la .code-indexer/daemon.sock

# Status healthy
cidx daemon status

# Queries work
cidx query "test" --limit 5

# Configuration correct
cidx config --show | grep daemon
```

### Expected Results Summary
- **Total Tests:** 20
- **Critical Functionality:** All passing
- **Performance:** Query <1s with warm cache
- **Stability:** No crashes during basic operations
- **Configuration:** Persistent and correct

### Next Steps
- If all smoke tests pass → Proceed to **02_Regression_Tests.md**
- If any test fails → Investigate and fix before proceeding
- If critical failure → Stop testing, report issue

### Common Issues Found During Smoke Testing
1. **Socket Permission Errors:** Usually due to previous unclean shutdown
   - **Solution:** `rm .code-indexer/daemon.sock && cidx start`

2. **Cache Not Hitting:** First query always cache miss
   - **Expected Behavior:** Normal, first query loads indexes

3. **Daemon Won't Start:** Port or socket conflict
   - **Solution:** `cidx stop` then verify no stale processes

4. **Query Timeout:** VoyageAI API issues or network problems
   - **Solution:** Check API key, network connectivity

### Test Execution Time Tracking

| Test ID | Test Name | Expected Time | Actual Time | Status |
|---------|-----------|---------------|-------------|---------|
| TC001 | Daemon Configuration Init | 2 min | | |
| TC002 | Socket Path Verification | 1 min | | |
| TC003 | Daemon Auto-Start | 3 min | | |
| TC004 | Semantic Query Delegation | 2 min | | |
| TC005 | FTS Query Delegation | 2 min | | |
| TC006 | Hybrid Search Delegation | 2 min | | |
| TC007 | Daemon Status Command | 1 min | | |
| TC008 | Manual Daemon Stop | 2 min | | |
| TC009 | Manual Daemon Start | 2 min | | |
| TC010 | Query After Restart | 2 min | | |
| TC011 | Configuration Display | 1 min | | |
| TC012 | Cache Clear Command | 2 min | | |
| TC013 | Indexing Operation | 3 min | | |
| TC014 | Watch Mode Start | 2 min | | |
| TC015 | Watch-Stop Command | 2 min | | |
| TC016 | Clean with Cache Invalidation | 2 min | | |
| TC017 | Clean-Data with Cache Invalidation | 2 min | | |
| TC018 | Status with Daemon Info | 1 min | | |
| TC019 | Daemon Configuration Toggle | 3 min | | |
| TC020 | Daemon Restart Persistence | 3 min | | |
| **TOTAL** | | **40 min** | | |

**Note:** Estimated time includes setup, execution, and verification. Actual time may vary based on repository size and system performance.
