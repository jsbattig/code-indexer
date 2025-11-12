# CIDX Daemonization Manual Test Suite

## Test Suite Overview

This directory contains comprehensive manual end-to-end regression tests for the CIDX Daemonization feature (Stories 2.0-2.4). These tests validate the complete RPyC daemon implementation with in-memory caching, crash recovery, and watch mode integration.

## Test Organization

### 01_Smoke_Tests.md
**Critical paths testing** - Essential functionality that must work for basic daemon operation.
- **Test Count:** ~20 tests
- **Execution Time:** ~15-20 minutes
- **Focus:** Daemon lifecycle, basic query delegation, configuration management
- **Run Frequency:** Every build, before any release

### 02_Regression_Tests.md
**Comprehensive feature validation** - All daemon features and edge cases.
- **Test Count:** ~50 tests
- **Execution Time:** ~45-60 minutes
- **Focus:** All 13 routed commands, cache behavior, crash recovery, TTL eviction, concurrent access
- **Run Frequency:** Before releases, after major changes

### 03_Integration_Tests.md
**Cross-feature validation** - Complex scenarios combining multiple features.
- **Test Count:** ~15 tests
- **Execution Time:** ~30-40 minutes
- **Focus:** Daemon + query + progress, watch mode integration, storage coherence
- **Run Frequency:** Release validation, regression testing

## Feature Implementation Summary

**Stories Implemented:**
- **Story 2.0:** RPyC Performance PoC (99.8% improvement validated)
- **Story 2.1:** RPyC Daemon Service (14 exposed methods, in-memory caching)
- **Story 2.2:** Repository Daemon Configuration (`cidx init --daemon`, config management)
- **Story 2.3:** Client Delegation (13 routed commands, crash recovery, exponential backoff)
- **Story 2.4:** Progress Callbacks (real-time streaming via RPyC)

**Key Components:**
- **Socket Path:** `.code-indexer/daemon.sock` (per-repository)
- **Caching:** HNSW + ID mapping + Tantivy FTS indexes (in-memory)
- **TTL:** 10 minutes default (configurable)
- **Concurrency:** Reader-Writer locks for concurrent queries
- **Crash Recovery:** 2 restart attempts with exponential backoff
- **Auto-Start:** Daemon starts automatically on first query

**Routed Commands (13):**
1. `cidx query` → `exposed_query()`
2. `cidx query --fts` → `exposed_query_fts()`
3. `cidx query --fts --semantic` → `exposed_query_hybrid()`
4. `cidx index` → `exposed_index()`
5. `cidx watch` → `exposed_watch_start()`
6. `cidx watch-stop` → `exposed_watch_stop()`
7. `cidx clean` → `exposed_clean()`
8. `cidx clean-data` → `exposed_clean_data()`
9. `cidx status` → `exposed_status()`
10. `cidx daemon status` → `exposed_get_status()`
11. `cidx daemon clear-cache` → `exposed_clear_cache()`
12. `cidx start` → Auto-start daemon
13. `cidx stop` → `exposed_shutdown()`

## Test Execution Prerequisites

### System Requirements
- Linux/macOS (Unix sockets required)
- Python 3.8+
- RPyC library installed (`pip install rpyc`)
- CIDX installed and configured
- VoyageAI API key (for semantic search tests)

### Test Environment Setup
```bash
# 1. Create test repository
mkdir -p ~/tmp/cidx-daemon-test
cd ~/tmp/cidx-daemon-test
git init

# 2. Create test files
echo "def authenticate_user(username, password): pass" > auth.py
echo "def process_payment(amount): pass" > payment.py
git add . && git commit -m "Initial test files"

# 3. Initialize CIDX with daemon mode
cidx init --daemon

# 4. Verify daemon configuration
cidx config --show
# Should show: daemon.enabled: true

# 5. Index repository (daemon auto-starts)
cidx index

# 6. Verify daemon running
ls -la .code-indexer/daemon.sock
# Should show socket file exists
```

### Test Data Requirements
- **Small Repository:** ~10-20 Python files (~2-5KB each)
- **API Access:** VoyageAI API key for semantic search
- **Disk Space:** ~50MB for indexes and test data
- **Network:** Required for embedding generation

## Test Execution Workflow

### Quick Smoke Test Run (~15 min)
```bash
# Execute smoke tests only
cd /home/jsbattig/Dev/code-indexer/plans/active/02_Feat_CIDXDaemonization/manual_testing

# Follow tests in 01_Smoke_Tests.md
# Focus on: TC001-TC020
```

### Full Regression Run (~2 hours)
```bash
# Execute all test files sequentially
# 1. Smoke tests (01_Smoke_Tests.md)
# 2. Regression tests (02_Regression_Tests.md)
# 3. Integration tests (03_Integration_Tests.md)
```

### Continuous Monitoring
```bash
# Monitor daemon status during testing
watch -n 5 'cidx daemon status'

# Monitor socket file
watch -n 5 'ls -la .code-indexer/daemon.sock'

# Monitor daemon process
watch -n 5 'ps aux | grep rpyc'
```

## Pass/Fail Criteria

### Smoke Tests Success Criteria
- All TC001-TC020 tests pass
- No daemon crashes during basic operations
- Query performance <1s with warm cache
- Daemon auto-start working correctly

### Regression Tests Success Criteria
- All TC021-TC070 tests pass
- All 13 routed commands function correctly
- Crash recovery working (2 restart attempts)
- TTL eviction functioning properly
- Cache coherence maintained

### Integration Tests Success Criteria
- All TC071-TC085 tests pass
- Watch mode updates cache correctly
- Progress callbacks stream properly
- Multi-client concurrent access works
- Storage operations maintain cache coherence

## Known Limitations

### Platform Limitations
- **Unix Sockets Only:** No Windows support (TCP/IP not implemented)
- **Per-Repository Daemon:** Each repository has its own daemon process

### Performance Expectations
- **Cold Start:** First query ~3s (index load + embedding generation)
- **Warm Cache:** Subsequent queries <100ms (cache hit)
- **FTS Queries:** <100ms with warm cache (95% improvement)
- **Daemon Startup:** <50ms connection time

### Cache Behavior
- **TTL Default:** 10 minutes (configurable)
- **Eviction Check:** Every 60 seconds
- **Auto-Shutdown:** Optional, disabled by default
- **Memory:** No hard limits (trust OS management)

## Troubleshooting Guide

### Daemon Not Starting
```bash
# Check daemon configuration
cidx config --show

# Verify socket path doesn't exist (no daemon running)
ls .code-indexer/daemon.sock

# Remove stale socket if exists
rm .code-indexer/daemon.sock

# Manually start daemon
cidx start

# Check daemon logs
tail -f ~/.cidx-server/logs/daemon.log
```

### Socket Binding Errors
```bash
# Address already in use - daemon already running
# Option 1: Use existing daemon
cidx daemon status

# Option 2: Stop and restart
cidx stop
cidx start
```

### Cache Not Hitting
```bash
# Clear cache and rebuild
cidx daemon clear-cache
cidx query "test query"

# Verify cache status
cidx daemon status
# Should show: semantic_cached: true
```

### Crash Recovery Failing
```bash
# Check daemon process
ps aux | grep rpyc

# Verify socket cleanup
ls -la .code-indexer/daemon.sock

# Check crash recovery attempts in output
cidx query "test" 2>&1 | grep "attempting restart"
```

## Test Result Tracking

### Test Run Template
```
Test Suite: [Smoke/Regression/Integration]
Date: YYYY-MM-DD
Tester: [Name]
Environment: [Linux/macOS version]
CIDX Version: [version]

Results Summary:
- Total Tests: X
- Passed: Y
- Failed: Z
- Skipped: W

Failed Tests:
- TC###: [Test Name] - [Reason]

Notes:
[Additional observations, issues discovered]
```

### Result Files
Store test results in:
```
manual_testing/results/
├── YYYY-MM-DD_smoke_test_results.md
├── YYYY-MM-DD_regression_test_results.md
└── YYYY-MM-DD_integration_test_results.md
```

## Contributing Test Cases

### Adding New Tests
1. Identify test classification (Smoke/Regression/Integration)
2. Follow test case format (see templates in test files)
3. Include all required sections (Prerequisites, Steps, Expected Results)
4. Add to appropriate test file
5. Update test count in this README

### Test Case Template
```markdown
### TC###: [Test Name]
**Classification:** [Smoke/Regression/Integration]
**Dependencies:** [TC### or "None"]
**Estimated Time:** X minutes

**Prerequisites:**
- [Prerequisite 1]
- [Prerequisite 2]

**Test Steps:**
1. [Step with exact command]
   - **Expected:** [Observable result]
   - **Verification:** [How to verify]

**Pass Criteria:**
- [Measurable criterion 1]
- [Measurable criterion 2]

**Fail Criteria:**
- [What indicates failure]
```

## References

**Feature Documentation:**
- `../Feat_CIDXDaemonization.md` - Complete feature specification
- `../01_Story_RPyCPerformancePoC.md` - Performance benchmarks
- `../02_Story_RPyCDaemonService.md` - Daemon service implementation
- `../03_Story_DaemonConfiguration.md` - Configuration management
- `../04_Story_ClientDelegation.md` - Client delegation and crash recovery
- `../05_Story_ProgressCallbacks.md` - Progress streaming implementation

**Implementation Files:**
- `src/code_indexer/services/rpyc_daemon.py` - Daemon service
- `src/code_indexer/cli.py` - Client delegation logic
- `src/code_indexer/config.py` - Configuration management

## Test Suite Maintenance

**Review Frequency:** Monthly or after major feature changes
**Update Triggers:**
- New commands added
- Performance requirements change
- Bug fixes requiring regression tests
- User-reported issues

**Maintenance Checklist:**
- [ ] Verify all test cases still relevant
- [ ] Update test data/prerequisites
- [ ] Add tests for new features
- [ ] Remove obsolete tests
- [ ] Update pass/fail criteria
- [ ] Refresh troubleshooting guide
