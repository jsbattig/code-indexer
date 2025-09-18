# Story 3.1: Transparent Remote Query Execution

## 🎯 **Story Intent**

Validate that remote query execution provides identical user experience to local mode, with transparent JWT authentication, proper result formatting, and performance within acceptable limits.

## 📋 **User Story**

**As a** Developer
**I want to** execute semantic queries against remote repositories using familiar commands
**So that** I can search code without learning new syntax or managing local infrastructure

## 🔧 **Test Setup**

### Prerequisites
- CIDX initialized in remote mode with valid credentials
- Server has indexed repositories matching local git origin
- Network connectivity to server
- Both simple and complex test queries prepared

### Test Environment
```bash
# Verify remote mode active
cidx status | grep "Mode: Remote"

# Note current branch for branch matching tests
git branch --show-current

# Prepare test queries
echo "Simple query: 'function'"
echo "Complex query: 'async database connection'"
echo "Filtered query: 'error handling' --language python --limit 10"
```

## 📊 **Test Scenarios**

### Scenario 1: Simple Query Execution
**Test ID**: 3.1.1
**Priority**: Critical
**Duration**: 5 minutes

**Steps:**
1. Execute simple query: `cidx query "function"`
2. Note execution time and results format
3. Compare with local mode output format (if available)

**Expected Results:**
- ✅ Query executes without authentication prompts
- ✅ Results appear within 2 seconds
- ✅ Output format matches local mode:
  ```
  Found X results in repository Y:

  1. [score: 0.95] path/to/file.py:42
     def function_name():
         # Implementation

  2. [score: 0.89] another/file.py:15
     async def another_function():
  ```
- ✅ Similarity scores displayed
- ✅ File paths relative to repository root

**Validation:**
```bash
# Measure execution time
time cidx query "function" | head -20

# Verify output structure
cidx query "function" | grep -E "^\[score: [0-9\.]+\]" | wc -l
# Should match result count
```

---

### Scenario 2: Complex Query with Filters
**Test ID**: 3.1.2
**Priority**: High
**Duration**: 5 minutes

**Steps:**
1. Execute filtered query: `cidx query "async database connection" --language python --limit 10`
2. Verify filters are applied
3. Count results to confirm limit

**Expected Results:**
- ✅ Only Python files in results
- ✅ Maximum 10 results returned
- ✅ Results semantically related to query
- ✅ Execution time <2 seconds for filtered query

**Validation:**
```bash
# Verify language filter
cidx query "database" --language python | grep -v "\.py:" | wc -l
# Should be 0 (only Python files)

# Verify limit
cidx query "function" --limit 5 | grep "^\[score:" | wc -l
# Should be ≤5
```

---

### Scenario 3: JWT Token Lifecycle
**Test ID**: 3.1.3
**Priority**: Critical
**Duration**: 15 minutes

**Steps:**
1. Execute first query (triggers token acquisition): `cidx query "test"`
2. Execute second query immediately: `cidx query "another test"`
3. Wait for token expiration (10+ minutes)
4. Execute query after expiration: `cidx query "final test"`

**Expected Results:**
- ✅ First query may take slightly longer (token acquisition)
- ✅ Second query faster (uses cached token)
- ✅ No authentication prompts during valid token period
- ✅ Automatic re-authentication after expiration
- ✅ No user intervention required

**Validation:**
```bash
# Monitor token acquisition (verbose mode)
cidx query "test" --verbose 2>&1 | grep -i "token\|auth"

# Test concurrent queries (should share token)
for i in {1..5}; do
  cidx query "test $i" &
done
wait
# All should succeed without multiple auth requests
```

---

### Scenario 4: Query Result Staleness Indicators
**Test ID**: 3.1.4
**Priority**: Medium
**Duration**: 5 minutes

**Steps:**
1. Modify a local file: `echo "// New comment" >> src/main.py`
2. Execute query that includes modified file: `cidx query "main function"`
3. Observe staleness indicators in results

**Expected Results:**
- ✅ Modified file shows staleness indicator (⚠️)
- ✅ Fresh files show freshness indicator (✓)
- ✅ Indicators align properly in output
- ✅ Summary shows staleness statistics

**Example Output:**
```
Found 3 results:

1. ⚠️ [score: 0.92] src/main.py:10 (local file newer)
   def main():

2. ✓ [score: 0.87] src/utils.py:25 (up to date)
   def main_helper():

Staleness Summary: 1 stale, 2 fresh
```

---

### Scenario 5: Network Error During Query
**Test ID**: 3.1.5
**Priority**: High
**Duration**: 5 minutes

**Steps:**
1. Start query execution
2. Interrupt network connection (disable WiFi/ethernet)
3. Observe error handling

**Expected Results:**
- ✅ Clear error message about network issue
- ✅ No partial results displayed
- ✅ Suggestion to check connectivity
- ✅ No corruption of cached credentials

**Recovery Test:**
1. Restore network connection
2. Retry same query
3. Should succeed without re-initialization

---

### Scenario 6: Query Performance Benchmarking
**Test ID**: 3.1.6
**Priority**: Medium
**Duration**: 10 minutes

**Steps:**
1. Execute series of queries with timing:
```bash
# Simple query
time cidx query "function"

# Complex semantic query
time cidx query "implement user authentication with JWT tokens"

# Large result set
time cidx query "class" --limit 100

# Filtered query
time cidx query "error" --language python --path "*/services/*"
```

**Expected Results:**
- ✅ Simple query: <500ms
- ✅ Complex query: <2s
- ✅ Large result set: <3s
- ✅ Filtered query: <1s
- ✅ Performance consistent across runs (±20%)

**Performance Matrix:**
| Query Type | Target | Run 1 | Run 2 | Run 3 | Average |
|------------|--------|-------|-------|-------|---------|
| Simple | <500ms | | | | |
| Complex | <2s | | | | |
| Large | <3s | | | | |
| Filtered | <1s | | | | |

---

### Scenario 7: Identical UX Validation
**Test ID**: 3.1.7
**Priority**: Critical
**Duration**: 10 minutes

**Steps:**
1. Document local mode query behavior (if available):
   - Command syntax
   - Output format
   - Error messages
   - Help text

2. Compare with remote mode:
   - Same commands work
   - Same parameters accepted
   - Same output structure
   - Same error handling

**Validation Checklist:**
- [ ] `cidx query --help` shows same options
- [ ] Query results format identical
- [ ] Error messages consistent
- [ ] No mode-specific parameters required
- [ ] Keyboard shortcuts work (Ctrl+C to cancel)

## 🔍 **Validation Checklist**

### Functional Validation
- [ ] Queries execute without authentication prompts
- [ ] Results format matches local mode
- [ ] All query parameters work correctly
- [ ] Staleness indicators display properly
- [ ] Performance within acceptable limits

### Security Validation
- [ ] JWT token acquired automatically
- [ ] Token cached and reused efficiently
- [ ] Automatic re-authentication works
- [ ] No token leakage in output
- [ ] Credentials remain encrypted

### UX Validation
- [ ] Identical command syntax
- [ ] Clear error messages
- [ ] Consistent output formatting
- [ ] No learning curve from local mode
- [ ] Help documentation accurate

## 📈 **Performance Metrics**

| Metric | Target | Actual | Pass/Fail |
|--------|--------|--------|-----------|
| First query (with auth) | <2s | | |
| Subsequent queries | <500ms | | |
| Complex semantic query | <2s | | |
| Network retry delay | <30s | | |
| Token refresh time | <200ms | | |

## 🐛 **Issues Found**

| Issue | Severity | Description | Resolution |
|-------|----------|-------------|------------|
| | | | |

## ✅ **Sign-Off**

**Tester**: _____________________
**Date**: _____________________
**Test Result**: [ ] PASS [ ] FAIL [ ] BLOCKED
**Notes**: _____________________