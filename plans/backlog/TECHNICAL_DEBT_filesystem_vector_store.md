# Technical Debt: Filesystem Vector Store Epic

**Epic:** Filesystem-Based Vector Database Backend (EPIC-FS-VEC-001)
**Status:** Implementation Complete, Epic Moved to Completed
**Date:** 2025-10-24
**Total Items:** 13 (3 High, 5 Medium, 5 Low)

---

## HIGH PRIORITY (Fix Within 1-2 Sprints)

### 1. Performance Investigation - Severe Slowdown in Small Repositories

**Issue:** Indexing performance degrades catastrophically for small repositories
- Django (3,501 files): 476 files/min ✅
- Requests (63 files): **13.2 files/min** ❌ (36x slower!)

**Expected Behavior:**
- 172 chunks in 2 batches should take ~4 seconds
- Actual: 236 seconds (59x slower)

**Root Cause:** Unknown - requires investigation
- Batching appears broken (0 threads active during indexing)
- Matrix service working correctly (211 requests processed)
- No obvious errors in logs

**Action Items:**
1. Add debug logging to VoyageAI batch processing
2. Investigate thread pool behavior for small repositories
3. Check if high-throughput processor has minimum batch size issues
4. Add performance regression tests to CI/CD

**Priority:** 🔴 CRITICAL
**Estimated Effort:** 2-4 days
**Blocking:** Production deployment for small repositories

---

### 2. FilesystemVectorStore File Size Violation

**Issue:** Single file exceeds MESSI Anti-File-Bloat limit
- File: `src/code_indexer/storage/filesystem_vector_store.py`
- Size: 1,200+ lines
- MESSI Limit: 500 lines per module

**Impact:** Code maintainability, readability

**Recommended Refactoring:**
```
filesystem_vector_store.py (1,200 lines)
    ↓ split into ↓
├── filesystem_vector_store.py (300 lines) - Core interface
├── git_aware_storage_manager.py (400 lines) - Git operations
└── filesystem_search_engine.py (500 lines) - Search/scroll operations
```

**Action Items:**
1. Design module split boundaries
2. Extract git-aware storage logic
3. Extract search/scroll logic
4. Update imports across codebase
5. Verify all tests still pass

**Priority:** 🔴 HIGH
**Estimated Effort:** 3-5 days
**Blocking:** Future feature additions (module too complex)

---

### 3. Fast-Automation.sh Hanging Issue

**Issue:** Test suite hangs after ~2 hours instead of completing in minutes
- Expected: 5-10 minutes (fast tests only)
- Actual: Hangs indefinitely at test #1470/2167

**Root Cause:** Unknown (not related to epic code - pre-existing issue)

**Impact:** Cannot verify full regression suite

**Action Items:**
1. Identify which test causes hang (run with --lf or --verbose)
2. Check for infinite loops or deadlocks in test code
3. Add timeout to individual tests
4. Consider splitting fast-automation into smaller suites

**Priority:** 🔴 HIGH (blocks CI/CD confidence)
**Estimated Effort:** 1-2 days investigation
**Blocking:** Automated regression testing

---

## MEDIUM PRIORITY (Fix Within 2-3 Sprints)

### 4. Test Coverage Below Target

**Issue:** FilesystemVectorStore at 77% coverage (target: 90%)
- Gap: 13 percentage points
- Uncovered: 31 lines (mostly error handling paths)

**Missing Test Scenarios:**
- Git operation timeouts
- Corrupted JSON recovery in ID index
- Gitignore creation errors
- Matrix service startup failures in edge cases

**Action Items:**
1. Add negative test cases for git timeout scenarios
2. Add corrupted data recovery tests
3. Add filesystem permission error tests
4. Target: Increase to 90%+ coverage

**Priority:** 🟡 MEDIUM
**Estimated Effort:** 2-3 days
**Blocking:** Production confidence for edge cases

---

### 5. Missing Performance Benchmarks

**Issue:** Story 9 claims "30-50% indexing speedup" without validation
- Violates MESSI Rule #10 (Fact-Verification)
- No automated tests verify this claim

**Action Items:**
1. Create performance benchmark test suite
2. Measure indexing with vs without matrix service
3. Validate claimed 30-50% speedup
4. Add regression tests to CI/CD
5. Remove or qualify performance claims if not validated

**Priority:** 🟡 MEDIUM
**Estimated Effort:** 2-3 days
**Blocking:** Marketing claims, performance regression detection

---

### 6. Memory Management Missing

**Issue:** No explicit memory limits or monitoring
- FilesystemVectorStore search loads all candidates into RAM
- Matrix service cache unbounded (relies only on TTL)
- 100K vectors = ~500 MB RAM during search

**Concerns:**
- Large repositories could cause OOM
- No warning when approaching memory limits
- No cache eviction strategy beyond TTL

**Action Items:**
1. Add memory monitoring to matrix service
2. Implement max cache size limit (e.g., 500 MB)
3. Add pagination/streaming to search() for large result sets
4. Add memory usage warnings in CLI

**Priority:** 🟡 MEDIUM
**Estimated Effort:** 3-4 days
**Blocking:** Large repository support (>100K vectors)

---

### 7. YAML Matrix Format Size Overhead

**Issue:** YAML format 3-5x larger than binary .npy
- Binary: 513 KB
- YAML: 1.6 MB (3.1x larger in practice)
- Git-friendly benefit vs storage cost trade-off

**Current Behavior:**
- Automatic .npy → .yaml conversion on first load
- Both files kept (safety)
- Service loads YAML (slower parsing)

**Options:**
1. **Accept trade-off** (current) - Git-friendliness worth the cost
2. **Compress YAML** - gzip reduces to ~600 KB
3. **Binary for service** - Service uses .npy, .yaml for git only
4. **User choice** - Config flag for format preference

**Action Items:**
1. Measure actual YAML parsing overhead (currently unmeasured)
2. Add compression option if overhead is significant
3. Document trade-offs in README

**Priority:** 🟡 MEDIUM
**Estimated Effort:** 1-2 days
**Blocking:** Large matrix files (>1024 dimensions)

---

### 8. QdrantContainerBackend Incomplete

**Issue:** QdrantContainerBackend is stub implementation
- Coverage: 50% (many methods return hardcoded values)
- Not integrated with actual DockerManager
- Backward compatibility works but Qdrant backend selection doesn't

**Current State:**
- FilesystemBackend: Fully functional ✅
- QdrantContainerBackend: Stub only ⚠️

**Action Items:**
1. Integrate QdrantContainerBackend with existing DockerManager
2. Implement actual start/stop/health_check with containers
3. Add integration tests with real Docker operations
4. Achieve >90% coverage

**Priority:** 🟡 MEDIUM
**Estimated Effort:** 5-7 days
**Blocking:** Users wanting to explicitly use Qdrant backend via --vector-store qdrant

---

## LOW PRIORITY (Fix When Convenient)

### 9. Minor Linting in Test Files

**Issue:** 10 cosmetic linting violations in test files
- F401: Unused imports (pytest, shutil)
- F841: Unused variables
- E741: Ambiguous variable names

**Impact:** None (functional), code hygiene only

**Action Items:**
- Run `ruff check --fix tests/` to auto-fix

**Priority:** 🟢 LOW
**Estimated Effort:** 15 minutes

---

### 10. Evolution Repository Performance

**Issue:** Severe performance problem in ~/Dev/evolution directory
- 8.3 MB indexing_progress.json file
- 2.0 MB metadata.json file
- 12G repository size with only 199 code files

**Root Cause:** Suspected: Huge progress tracking files causing I/O overhead

**Action Items:**
1. Investigate why progress files are so large
2. Check for progress file corruption or accumulation bug
3. Add max file size limits to progress tracking
4. Consider compressing or rotating large progress files

**Priority:** 🟢 LOW (don't use in that repo)
**Estimated Effort:** 1-2 days investigation

---

### 11. README Documentation Gaps

**Issue:** Missing documentation for matrix multiplication service
- Service exists and runs automatically
- No user-facing documentation
- Users won't know how to monitor or troubleshoot

**Action Items:**
1. Add "Matrix Multiplication Service" section to README
2. Document auto-start behavior
3. Document manual management commands (stats, shutdown)
4. Document fallback behavior and troubleshooting

**Priority:** 🟢 LOW
**Estimated Effort:** 1 hour

---

### 12. Directory Path Utilization Question

**Issue:** Only using 8 of 32 hex chars for directory structure
- Quantization produces: 32 hex characters
- Directory path uses: 8 hex chars (4 levels × 2 chars)
- Remaining: 24 hex chars in filename

**Question:** Could we improve distribution by using more levels?

**Options:**
1. **Keep current** (depth_factor=4, proven by POC)
2. **Increase depth** (depth_factor=6 or 8, use more hex chars)
3. **Investigate** if current distribution causes hotspots

**Action Items:**
1. Analyze actual directory distribution in Django index
2. Check if any directories have excessive file counts
3. Benchmark query performance with deeper paths
4. Decision: Keep or adjust

**Priority:** 🟢 LOW (current design validated by POC)
**Estimated Effort:** 1-2 days analysis

---

### 13. Concurrent Access Testing Gap

**Issue:** Limited testing of multiple cidx processes accessing same index
- File locking: Basic (atomic writes only)
- Concurrent reads: Assumed safe (untested)
- Concurrent writes: Thread-safe within process, not tested across processes

**Action Items:**
1. Add test: Multiple cidx index processes simultaneously
2. Add test: Query during indexing
3. Add file locking if conflicts detected
4. Document concurrent access limitations

**Priority:** 🟢 LOW (unlikely scenario for dev tool)
**Estimated Effort:** 2-3 days

---

## Summary Statistics

**Total Technical Debt Items:** 13
- 🔴 High Priority: 3 (must fix before production)
- 🟡 Medium Priority: 5 (fix within 2-3 sprints)
- 🟢 Low Priority: 5 (fix when convenient)

**Estimated Total Effort:** 20-35 days

**Critical Path:** Items 1, 2, 3 block production deployment
**Quick Wins:** Items 9, 11 (1-2 hours each)

---

## Prioritized Action Plan

### Sprint 1 (Immediate)
1. 🔴 **Item #1** - Investigate batching performance issue (CRITICAL)
2. 🟡 **Item #5** - Add performance benchmarks (validate claims)
3. 🟢 **Item #9** - Fix test linting (quick win)

### Sprint 2
4. 🔴 **Item #3** - Fix fast-automation.sh hang
5. 🟡 **Item #4** - Increase test coverage to 90%
6. 🟢 **Item #11** - Update README (quick win)

### Sprint 3
7. 🔴 **Item #2** - Refactor FilesystemVectorStore
8. 🟡 **Item #6** - Add memory limits and monitoring
9. 🟡 **Item #8** - Complete QdrantContainerBackend

### Future Sprints
10-13. Medium/Low priority items as capacity allows

---

## Tracking

**Created:** 2025-10-24
**Epic Reference:** plans/Completed/epic-filesystem-vector-store/
**Review Document:** plans/Completed/epic-filesystem-vector-store/ARCHITECTURAL_REVIEW.md
**Owner:** TBD
**Status:** OPEN

---

## Notes

- All items discovered during epic implementation and architectural review
- No blockers for merging epic to master (with caveats)
- Item #1 (performance issue) discovered during final testing
- Recommend addressing High Priority items before production deployment
