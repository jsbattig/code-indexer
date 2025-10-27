# Story 4.1: Basic Query Testing

## 🎯 **Story Intent**

Validate core semantic query functionality to ensure identical user experience between local and remote modes with proper result formatting.

[Conversation Reference: "Basic queries, advanced query options"]

## 📋 **Story Description**

**As a** Developer
**I want to** execute semantic queries against remote repositories
**So that** I can find relevant code with identical experience to local mode

[Conversation Reference: "Identical query UX between local and remote modes"]

## 🔧 **Test Procedures**

### Test 4.1.1: Simple Semantic Query (REAL SERVER)
**Prerequisites:**
```bash
# Ensure server is running and repository is linked
cd /tmp/cidx-test  # Directory with remote config
python -m code_indexer.cli status  # Verify connection health
```

**Command to Execute:**
```bash
# Test semantic search against indexed code-indexer repository
python -m code_indexer.cli query "authentication function"
```

**Expected Results:**
- Query executes successfully (exit code 0)
- Results displayed with relevance scores (0.0-1.0 scale)
- Response time within acceptable range (<2 seconds)
- Results include code-indexer repo files like:
  - `src/code_indexer/server/auth/jwt_manager.py` (JWT authentication)
  - `src/code_indexer/server/auth/user_manager.py` (user authentication)
  - `src/code_indexer/remote/health_checker.py` (server authentication testing)
- Shows server processing time vs network latency

**Pass/Fail Criteria:**
- ✅ PASS: Query succeeds with real results from server
- ❌ FAIL: Query fails, no results, or poor performance

[Conversation Reference: "python -m code_indexer.cli query commands work identically to local mode"]

### Test 4.1.2: Query Result Format Consistency
**Command to Execute:**
```bash
# Test with code-indexer specific content
python -m code_indexer.cli query "qdrant database connection" --limit 5
```

**Expected Results:**
- Results format matches local mode exactly
- Relevance scores displayed consistently (0.0-1.0 scale)
- File paths shown relative to repository root
- Results should include files like:
  - `src/code_indexer/services/qdrant.py` (vector database operations)
  - `src/code_indexer/services/vector_calculation_manager.py` (database integration)
- Code snippets properly highlighted and formatted

**Pass/Fail Criteria:**
- ✅ PASS: Result format identical to local mode
- ❌ FAIL: Format differences from local mode

### Test 4.1.3: Query Performance Validation
**Command to Execute:**
```bash
# Test with code-indexer specific error handling content
time python -m code_indexer.cli query "error handling patterns" --limit 10
```

**Expected Results:**
- Query completes within performance target (2x local time)
- Response time consistently reported
- Network latency vs processing time breakdown shown
- Results should include files like:
  - `src/code_indexer/server/middleware/error_formatters.py` (error formatting)
  - `src/code_indexer/cli_error_display.py` (CLI error handling)
  - `src/code_indexer/services/docker_manager.py` (container error handling)
- Performance acceptable for interactive use

**Pass/Fail Criteria:**
- ✅ PASS: Query performance within 2x local mode
- ❌ FAIL: Unacceptable performance degradation

### Test 4.1.4: Empty Result Handling
**Command to Execute:**
```bash
python -m code_indexer.cli query "nonexistent_very_specific_unique_term_12345"
```

**Expected Results:**
- Query executes without errors
- Clear message indicating no results found
- Helpful suggestions for improving query terms
- Appropriate exit code (0 for successful execution, no results)

**Pass/Fail Criteria:**
- ✅ PASS: Graceful handling of empty results
- ❌ FAIL: Error on empty results or poor messaging

## 📊 **Success Metrics**

- **Response Time**: Queries complete within 2x local query time
- **Result Accuracy**: Relevance scores consistent with local mode
- **Format Consistency**: 100% identical output format to local mode
- **User Experience**: Seamless transition from local to remote querying

[Conversation Reference: "Remote queries complete within 2x local query time"]

## 🎯 **Acceptance Criteria**

- [ ] Basic semantic queries execute successfully in remote mode
- [ ] Query results format exactly matches local mode output
- [ ] Query performance meets acceptable thresholds (2x local time)
- [ ] Empty result scenarios handled gracefully with helpful messages
- [ ] Error conditions provide clear feedback and guidance
- [ ] All query output is properly formatted and user-friendly

[Conversation Reference: "Query results format matches local mode exactly"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Completed Feature 3 (Repository Management) testing
- Linked repository with indexed content available
- Valid authentication session active
- Local mode baseline performance measurements

**Test Environment Setup:**
1. Ensure repository is linked and contains searchable content
2. Have baseline local mode performance data for comparison
3. Prepare various query terms (common, specific, and non-existent)
4. Set up timing measurement tools

**Performance Baseline:**
- Measure local mode query performance first for comparison
- Document network latency to server separately
- Note server processing vs network overhead
- Consider server load during testing

**Post-Test Validation:**
1. All queries return expected results
2. Performance within acceptable ranges
3. Result formatting consistent and readable
4. Error handling appropriate and helpful

**Common Issues:**
- Network latency affecting perceived performance
- Server load impacting query response times
- Result formatting differences due to server processing
- Authentication token issues during query execution

[Conversation Reference: "Primary use case of CIDX remote mode"]