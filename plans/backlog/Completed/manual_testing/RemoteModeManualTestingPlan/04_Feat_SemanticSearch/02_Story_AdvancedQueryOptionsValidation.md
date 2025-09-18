# Story 4.2: Advanced Query Options Validation

## 🎯 **Story Intent**

Validate advanced semantic search options and filtering capabilities in remote mode through systematic manual testing procedures.

[Conversation Reference: "Advanced query options validation"]

## 📋 **Story Description**

**As a** Developer
**I want to** use advanced query options and filters in remote semantic search
**So that** I can perform precise and targeted code searches with sophisticated filtering

[Conversation Reference: "Each test story specifies exact python -m code_indexer.cli commands to execute"]

## 🔧 **Test Procedures**

### Test 4.2.1: Language-Specific Filtering
**Command to Execute:**
```bash
# Test against code-indexer repository with Python filter
python -m code_indexer.cli query "authentication function" --language python
```

**Expected Results:**
- Query executes against remote repository index
- Results filtered to only Python files (.py extension)
- Should find code-indexer authentication files like:
  - `src/code_indexer/server/auth/jwt_manager.py`
  - `src/code_indexer/server/auth/user_manager.py`
  - `src/code_indexer/remote/health_checker.py`
- Response time comparable to local mode (within 2x)

**Pass/Fail Criteria:**
- ✅ PASS: Language filtering works correctly, only Python results returned
- ❌ FAIL: Language filtering fails or includes non-Python files

[Conversation Reference: "Clear pass/fail criteria for manual verification"]

### Test 4.2.2: Path Pattern Filtering
**Command to Execute:**
```bash
# Test path filtering against code-indexer src directory
python -m code_indexer.cli query "qdrant vector database" --path "*/src/*"
```

**Expected Results:**
- Query searches only within src directories and subdirectories
- Results limited to files matching the specified path pattern
- Should find code-indexer database files like:
  - `src/code_indexer/services/qdrant.py` (vector database operations)
  - `src/code_indexer/services/vector_calculation_manager.py` (database integration)
- Path filtering applied correctly across repository structure

**Pass/Fail Criteria:**
- ✅ PASS: Path filtering works, only files from src directories included
- ❌ FAIL: Path filtering ineffective or includes files from wrong directories

### Test 4.2.3: Result Limit and Scoring
**Command to Execute:**
```bash
# Test scoring and limits against code-indexer error handling
python -m code_indexer.cli query "error handling patterns" --limit 20 --min-score 0.8
```

**Expected Results:**
- Query returns exactly 20 results (or fewer if not available)
- All results have similarity scores ≥ 0.8
- Results ranked by semantic similarity score (highest first)
- Should find high-relevance code-indexer error handling like:
  - `src/code_indexer/server/middleware/error_formatters.py` (score ~0.9+)
  - `src/code_indexer/cli_error_display.py` (score ~0.8+)
- Score threshold filtering applied correctly

**Pass/Fail Criteria:**
- ✅ PASS: Result limiting and score filtering work as specified
- ❌ FAIL: Wrong number of results or scores below threshold included

### Test 4.2.4: Combined Filter Options
**Command to Execute:**
```bash
# Test combined filters against code-indexer test suite
python -m code_indexer.cli query "authentication test" --language python --path "*/tests/*" --limit 10
```

**Expected Results:**
- Multiple filters applied simultaneously and correctly
- Results meet all criteria: Python files, in test directories, authentication-related
- Should find code-indexer authentication test files like:
  - `tests/unit/server/auth/test_jwt_authentication.py`
  - `tests/unit/server/auth/test_password_change_security.py`
  - `tests/unit/server/test_auth_endpoints.py`
- Limit of 10 results respected
- Semantic relevance maintained despite multiple constraints

**Pass/Fail Criteria:**
- ✅ PASS: All filters work together correctly, results meet all criteria
- ❌ FAIL: Filter combination fails or produces incorrect results

### Test 4.2.5: Advanced Accuracy Modes
**Command to Execute:**
```bash
# Test high accuracy mode against code-indexer architecture patterns
python -m code_indexer.cli query "progress callback pattern" --accuracy high
```

**Expected Results:**
- High accuracy mode provides more precise semantic matching
- Response time may be slower but results are more relevant
- Should find code-indexer progress callback implementations like:
  - `src/code_indexer/services/file_chunking_manager.py` (progress callbacks)
  - `src/code_indexer/services/branch_aware_indexer.py` (callback patterns)
- Better semantic understanding of complex multi-word queries
- Results demonstrate higher precision in pattern matching

**Pass/Fail Criteria:**
- ✅ PASS: High accuracy mode produces noticeably better results
- ❌ FAIL: No discernible improvement in result quality or mode fails

### Test 4.2.6: Query Performance with Filters
**Command to Execute:**
```bash
# Test performance with filters against code-indexer configuration
python -m code_indexer.cli query "configuration management" --language python --limit 15
```

**Expected Results:**
- Query execution time is measured and displayed
- Response time remains within acceptable limits (<4 seconds for remote)
- Should find code-indexer configuration files like:
  - `src/code_indexer/config.py` (main configuration)
  - `src/code_indexer/server/utils/config_manager.py` (server config)
- Filtering doesn't significantly impact query performance
- Timing information helps validate performance requirements

**Pass/Fail Criteria:**
- ✅ PASS: Query completes within time limits with accurate timing data
- ❌ FAIL: Excessive query time or timing information unavailable

### Test 4.2.7: Invalid Filter Combinations
**Command to Execute:**
```bash
python -m code_indexer.cli query "test function" --language invalidlanguage --path "badpattern["
```

**Expected Results:**
- Clear error messages for invalid language specification
- Helpful suggestions for valid language options
- Path pattern validation with error guidance
- Graceful handling without query execution

**Pass/Fail Criteria:**
- ✅ PASS: Invalid filters caught with helpful error messages
- ❌ FAIL: Poor error handling or query attempts with invalid filters

## 📊 **Success Metrics**

- **Filter Accuracy**: 100% correct application of language and path filters
- **Query Performance**: Advanced queries complete within 4 seconds
- **Score Precision**: Min-score filtering works accurately across all result sets
- **User Experience**: Complex filter combinations work intuitively

[Conversation Reference: "Performance Requirements: Query responses within 2 seconds for typical operations"]

## 🎯 **Acceptance Criteria**

- [ ] Language filtering correctly limits results to specified programming languages
- [ ] Path pattern filtering accurately constrains search to matching directories
- [ ] Result limiting and score thresholds work precisely as specified
- [ ] Multiple filters can be combined effectively in single queries
- [ ] Advanced accuracy modes provide improved semantic precision
- [ ] Query timing information is available for performance validation
- [ ] Invalid filter options are handled with clear error messages and suggestions
- [ ] All advanced query options maintain acceptable performance levels

[Conversation Reference: "Clear acceptance criteria for manual assessment"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- CIDX remote mode initialized and authenticated
- Repository linked with comprehensive codebase (multiple languages)
- Remote server responsive and fully indexed
- Understanding of repository structure and available languages

**Test Environment Setup:**
1. Verify repository contains multiple programming languages
2. Confirm repository has diverse directory structure (src, tests, docs, etc.)
3. Prepare timing measurement capability
4. Have examples of valid and invalid filter parameters ready

**Post-Test Validation:**
1. Verify filter results by manually checking file types and paths
2. Confirm semantic relevance of filtered results
3. Validate performance meets established requirements
4. Test filter combinations produce logically correct intersections

[Conversation Reference: "Manual execution environment with python -m code_indexer.cli CLI"]