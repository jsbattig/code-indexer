# FTS Integration Analysis for CIDX Daemonization Epic

**Date:** 2025-10-29
**Epic:** 02_Feat_CIDXDaemonization
**Purpose:** Analyze FTS integration requirements and incorporate into daemon architecture

---

## Executive Summary

The CIDX daemonization epic must be updated to include Full-Text Search (FTS) support using the Tantivy library. FTS is now a production feature (as of Story 1.1-1.6) that provides fast exact text search alongside semantic search. The daemon architecture needs to support FTS query delegation, index caching, and hybrid search workflows.

**Key Findings:**
- FTS queries are 10-50x faster than semantic (no embedding generation required)
- Tantivy indexes must be loaded separately from HNSW indexes
- Hybrid search executes both FTS and semantic queries in parallel
- FTS filtering (language, path) happens post-search in Python
- Watch mode already supports FTS incremental updates

---

## FTS Architecture Overview

### Current FTS Implementation Status

**Completed Features:**
1. ✅ **FTS Indexing:** Opt-in via `--fts` flag during `cidx index`
2. ✅ **Storage:** `.code-indexer/tantivy_index/` directory structure
3. ✅ **Query Types:** Exact search (`--fts`), fuzzy search (`--fuzzy`), regex (`--regex`)
4. ✅ **Filtering:** Language and path filters with precedence rules
5. ✅ **Hybrid Search:** Parallel execution of semantic + FTS with result merging
6. ✅ **Watch Mode:** Incremental FTS updates via `fts_watch_handler.py`

**Key Components:**
- `TantivyIndexManager` (src/code_indexer/services/tantivy_index_manager.py)
- FTS query execution in CLI (cli.py:775-924)
- Hybrid search parallel execution (cli.py:1050-1200)
- FTS watch handler for incremental updates

### FTS vs Semantic Performance Characteristics

```
Query Type Comparison:
┌────────────────────┬──────────────┬────────────────┬──────────────┐
│ Query Type         │ Startup      │ Embedding Gen  │ Search       │
├────────────────────┼──────────────┼────────────────┼──────────────┤
│ Semantic (current) │ 1.86s        │ 792ms          │ 62ms         │
│ FTS (exact)        │ 1.86s        │ 0ms            │ 5-50ms       │
│ FTS (fuzzy d=1)    │ 1.86s        │ 0ms            │ 10-20ms      │
│ FTS (fuzzy d=2)    │ 1.86s        │ 0ms            │ 30-50ms      │
│ Hybrid (parallel)  │ 1.86s        │ 792ms          │ max(both)+5ms│
└────────────────────┴──────────────┴────────────────┴──────────────┘

Performance Gains with Daemon (10-minute TTL):
┌────────────────────┬──────────────┬────────────────┬──────────────┐
│ Query Type         │ Cold Start   │ Warm Cache     │ Improvement  │
├────────────────────┼──────────────┼────────────────┼──────────────┤
│ Semantic           │ ~1.5s        │ ~900ms         │ 71%          │
│ FTS (exact)        │ ~1.1s        │ ~100ms         │ 95%          │
│ FTS (fuzzy)        │ ~1.1s        │ ~150ms         │ 93%          │
│ Hybrid             │ ~1.5s        │ ~950ms         │ 69%          │
└────────────────────┴──────────────┴────────────────┴──────────────┘
```

**Critical Insight:** FTS queries eliminate embedding generation (792ms), making them exceptionally fast with daemon caching. This amplifies daemon benefits.

---

## Required Changes to Daemon Epic

### 1. Story 2.1: RPyC Daemon Service Updates

**Current Scope:** Caches HNSW indexes and ID mappings for semantic search

**Required FTS Additions:**

#### A. Extended Cache Entry Structure

```python
class CacheEntry:
    def __init__(self, project_path):
        self.project_path = project_path

        # Existing semantic index cache
        self.hnsw_index = None
        self.id_mapping = None

        # NEW: FTS index cache
        self.tantivy_index = None          # Tantivy Index object
        self.tantivy_searcher = None       # Tantivy Searcher (reusable)
        self.fts_available = False         # Flag if FTS index exists

        # Shared metadata for both index types
        self.last_accessed = datetime.now()
        self.ttl_minutes = 10  # Single TTL applies to both semantic and FTS (10 min default)
        self.read_lock = RLock()
        self.write_lock = Lock()
        self.access_count = 0  # Tracks all queries (semantic + FTS)
```

#### B. New Exposed Methods

```python
def exposed_query_fts(
    self,
    project_path: str,
    query: str,
    case_sensitive: bool = False,
    fuzzy: bool = False,
    edit_distance: int = 1,
    regex: bool = False,
    languages: Optional[List[str]] = None,
    exclude_languages: Optional[List[str]] = None,
    path_filters: Optional[List[str]] = None,
    exclude_paths: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Execute FTS query with caching."""
    project_path = Path(project_path).resolve()

    # Get or create cache entry
    with self.cache_lock:
        if str(project_path) not in self.cache:
            self.cache[str(project_path)] = self.CacheEntry(project_path)
        entry = self.cache[str(project_path)]

    # Concurrent read with RLock
    with entry.read_lock:
        # Load Tantivy index if not cached
        if entry.tantivy_index is None:
            self._load_tantivy_index(entry)

        # Check if FTS available
        if not entry.fts_available:
            return {"error": "FTS index not available for this project"}

        # Update access time (shared for both index types)
        entry.last_accessed = datetime.now()
        entry.access_count += 1

        # Perform FTS search
        results = self._execute_fts_search(
            entry.tantivy_searcher,
            query,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            edit_distance=edit_distance,
            regex=regex,
            languages=languages,
            exclude_languages=exclude_languages,
            path_filters=path_filters,
            exclude_paths=exclude_paths,
            limit=limit
        )

    return results

def exposed_query_hybrid(
    self,
    project_path: str,
    query: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Execute hybrid search (semantic + FTS) in parallel.

    CRITICAL: This must match current CLI behavior exactly!
    When user specifies both --fts and --semantic flags, the CLI
    executes both searches in parallel and merges results.

    The daemon MUST replicate this exact behavior - no behavior changes.
    """
    project_path = Path(project_path).resolve()

    # Get cache entry
    with self.cache_lock:
        if str(project_path) not in self.cache:
            self.cache[str(project_path)] = self.CacheEntry(project_path)
        entry = self.cache[str(project_path)]

    # Execute both searches in parallel (matching current CLI behavior)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both searches
        semantic_future = executor.submit(
            self.exposed_query, project_path, query, **kwargs
        )

        fts_future = executor.submit(
            self.exposed_query_fts, project_path, query, **kwargs
        )

        # Wait for both results
        semantic_results = semantic_future.result()
        fts_results = fts_future.result()

    # Merge results using EXISTING CLI merging logic
    # (must import and use exact same function from cli.py)
    merged_results = self._merge_hybrid_results_cli_compatible(
        semantic_results, fts_results
    )

    return {
        "results": merged_results,
        "semantic_count": len(semantic_results),
        "fts_count": len(fts_results),
        "merged_count": len(merged_results)
    }
```

#### C. Index Loading Logic

```python
def _load_tantivy_index(self, entry: CacheEntry):
    """Load Tantivy FTS index into cache."""
    tantivy_index_dir = entry.project_path / ".code-indexer" / "tantivy_index"

    if not tantivy_index_dir.exists():
        logger.warning(f"FTS index not found: {tantivy_index_dir}")
        entry.fts_available = False
        return

    try:
        # Lazy import tantivy
        import tantivy

        # Open existing index
        entry.tantivy_index = tantivy.Index.open(str(tantivy_index_dir))

        # Create reusable searcher (caching this is key performance optimization)
        entry.tantivy_searcher = entry.tantivy_index.searcher()

        entry.fts_available = True
        logger.info(f"Loaded FTS index: {tantivy_index_dir}")

    except ImportError:
        logger.error("Tantivy not installed - FTS unavailable")
        entry.fts_available = False
    except Exception as e:
        logger.error(f"Failed to load FTS index: {e}")
        entry.fts_available = False

def _execute_fts_search(
    self,
    searcher: Any,  # tantivy.Searcher
    query: str,
    case_sensitive: bool,
    fuzzy: bool,
    edit_distance: int,
    regex: bool,
    languages: Optional[List[str]],
    exclude_languages: Optional[List[str]],
    path_filters: Optional[List[str]],
    exclude_paths: Optional[List[str]],
    limit: int
) -> List[Dict[str, Any]]:
    """Execute FTS search with TantivyIndexManager logic."""
    # Use existing TantivyIndexManager.search() implementation
    # This reuses the production-tested filtering and search logic
    from code_indexer.services.tantivy_index_manager import TantivyIndexManager

    # Create temporary manager with cached searcher
    # (avoids re-opening index, uses our cached searcher)
    results = TantivyIndexManager._search_with_searcher(
        searcher,
        query,
        case_sensitive=case_sensitive,
        fuzzy=fuzzy,
        edit_distance=edit_distance,
        regex=regex,
        languages=languages,
        exclude_languages=exclude_languages,
        path_filters=path_filters,
        exclude_paths=exclude_paths,
        limit=limit
    )

    return results
```

#### D. Status Endpoint Extension

```python
def exposed_get_status(self):
    """Return daemon and cache statistics (extended for FTS)."""
    with self.cache_lock:
        status = {
            "running": True,
            "cache_entries": len(self.cache),
            "projects": []
        }

        for path, entry in self.cache.items():
            project_status = {
                "path": path,
                "semantic": {
                    "cached": entry.hnsw_index is not None
                },
                "fts": {
                    "available": entry.fts_available,
                    "cached": entry.tantivy_searcher is not None
                },
                "last_accessed": entry.last_accessed.isoformat(),
                "access_count": entry.access_count,
                "ttl_minutes": entry.ttl_minutes
            }
            status["projects"].append(project_status)

    return status
```

**Acceptance Criteria Updates:**

Add to Story 2.1:
- [ ] FTS indexes cached in memory after first load
- [ ] Cache hit for FTS queries returns results in <20ms (excluding search)
- [ ] Hybrid queries execute semantic + FTS in parallel
- [ ] Status endpoint reports FTS availability per project
- [ ] TTL eviction applies to both semantic and FTS indexes
- [ ] Clear cache endpoint clears both index types

---

### 2. Story 2.3: Client Delegation Updates

**Current Scope:** Lightweight CLI delegates semantic queries to daemon

**Required FTS Additions:**

#### A. FTS Query Delegation

```python
def _query_fts_via_daemon(
    self,
    query: str,
    daemon_config: dict,
    case_sensitive: bool,
    fuzzy: bool,
    edit_distance: int,
    regex: bool,
    languages: List[str],
    exclude_languages: List[str],
    path_filters: List[str],
    exclude_paths: List[str],
    limit: int,
    **kwargs
):
    """Delegate FTS query to daemon."""
    # Connect to daemon (with async import warming)
    connection = self._connect_to_daemon(daemon_config)

    try:
        start_query = time.perf_counter()

        # Call FTS-specific RPC method
        result = connection.root.query_fts(
            project_path=str(Path.cwd()),
            query=query,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            edit_distance=edit_distance,
            regex=regex,
            languages=languages,
            exclude_languages=exclude_languages,
            path_filters=path_filters,
            exclude_paths=exclude_paths,
            limit=limit
        )

        query_time = time.perf_counter() - start_query

        # Display FTS results
        self._display_fts_results(result, query_time)

        connection.close()
        return 0

    except Exception as e:
        self._report_error(e)
        connection.close()
        return 1
```

#### B. Hybrid Search Delegation

```python
def _query_hybrid_via_daemon(
    self,
    query: str,
    daemon_config: dict,
    semantic_weight: float,
    fts_weight: float,
    **kwargs
):
    """Delegate hybrid search to daemon."""
    connection = self._connect_to_daemon(daemon_config)

    try:
        start_query = time.perf_counter()

        # Call hybrid RPC method
        result = connection.root.query_hybrid(
            project_path=str(Path.cwd()),
            query=query,
            semantic_weight=semantic_weight,
            fts_weight=fts_weight,
            **kwargs
        )

        query_time = time.perf_counter() - start_query

        # Display hybrid results with source indicators
        self._display_hybrid_results(result, query_time)

        connection.close()
        return 0

    except Exception as e:
        self._report_error(e)
        connection.close()
        return 1
```

#### C. Query Type Detection

```python
def query(self, query_text: str, **kwargs) -> int:
    """Execute query with daemon delegation (supports semantic, FTS, hybrid)."""
    # Step 1: Quick config check
    daemon_config = self._check_daemon_config()

    # Step 2: Determine query type
    is_fts = kwargs.get('fts', False)
    is_semantic = kwargs.get('semantic', False)
    is_hybrid = is_fts and is_semantic  # Both flags = hybrid

    # Step 3: Route to appropriate handler
    if daemon_config and daemon_config.get("enabled"):
        if is_hybrid:
            return self._query_hybrid_via_daemon(query_text, daemon_config, **kwargs)
        elif is_fts:
            return self._query_fts_via_daemon(query_text, daemon_config, **kwargs)
        else:
            return self._query_via_daemon(query_text, daemon_config, **kwargs)
    else:
        # Fallback to standalone
        return self._query_standalone(query_text, **kwargs)
```

**Acceptance Criteria Updates:**

Add to Story 2.3:
- [ ] CLI delegates FTS queries to daemon when available
- [ ] CLI delegates hybrid queries with parallel execution
- [ ] Fallback works for FTS queries
- [ ] Query type detection (semantic/FTS/hybrid) is automatic
- [ ] FTS results displayed with same formatting as standalone mode

---

### 3. Story 2.4: Progress Callbacks - No Changes Required

**Analysis:** Story 2.4 focuses on indexing progress callbacks. FTS indexing already has progress reporting integrated into `SmartIndexer` and `HighThroughputProcessor`. No additional work needed for this story.

**Recommendation:** Keep Story 2.4 unchanged. Progress callbacks for indexing operations are orthogonal to FTS query delegation.

---

## Performance Projections with FTS + Daemon

### Query Time Breakdown

#### Semantic Query (Current Baseline)
```
Total: 3.09s
├─ Python startup: 1.86s
│  ├─ Import Rich: 200ms
│  ├─ Import argparse: 50ms
│  └─ Other imports: 1610ms
├─ Index loading: 376ms
│  ├─ HNSW index: 180ms
│  └─ ID mapping: 196ms
├─ Embedding generation: 792ms
└─ Vector search: 62ms
```

#### FTS Query (Current Baseline)
```
Total: 2.24s
├─ Python startup: 1.86s
│  └─ (same as semantic)
├─ Tantivy index loading: 300ms (first query)
├─ Embedding generation: 0ms (not needed!)
└─ FTS search: 5-50ms
```

#### With Daemon (Warm Cache)

**Semantic Query:**
```
Total: ~900ms (71% improvement)
├─ CLI startup: 50ms
├─ RPyC connection: 20ms
├─ Index loading: 5ms (cached!)
├─ Embedding generation: 792ms
└─ Vector search: 62ms
```

**FTS Query:**
```
Total: ~100ms (95% improvement!)
├─ CLI startup: 50ms
├─ RPyC connection: 20ms
├─ Index loading: 5ms (cached!)
├─ Embedding generation: 0ms
└─ FTS search: 5-50ms
```

**Hybrid Query:**
```
Total: ~950ms (69% improvement)
├─ CLI startup: 50ms
├─ RPyC connection: 20ms
├─ Parallel execution: 850ms
│  ├─ Semantic: 859ms (cached)
│  └─ FTS: 55ms (cached)
└─ Result merging: 5ms
```

**Key Insight:** FTS queries see the **highest performance gain** (95%) because they eliminate both startup overhead AND embedding generation.

---

## Memory Impact Analysis

### Current Memory Usage (Per Project)

**Semantic Index:**
- HNSW index: ~50-200MB (depends on codebase size)
- ID mapping: ~10-50MB
- **Total:** ~60-250MB per project

**FTS Index:**
- Tantivy index: In-memory searcher is small (~5-20MB)
- Index files on disk: ~30-50% of source code size (mmap'd)
- **Total:** ~10-30MB in-memory per project

**Combined (Semantic + FTS):**
- **Total:** ~70-280MB per project in daemon cache

### Daemon Memory Projections

**Scenario: 10 Active Projects**
- Base daemon process: ~50MB
- 10 semantic indexes: 60-250MB each = 600-2500MB
- 10 FTS indexes: 10-30MB each = 100-300MB
- **Total:** 750-2850MB (~0.7-2.8GB)

**Scenario: 100 Projects (with TTL eviction)**
- Active in cache (20 projects): ~1.4-5.6GB
- Evicted due to TTL: Rest on disk
- **Total:** Reasonable with 60-minute TTL

**Recommendation:** Current TTL-based eviction strategy is sufficient. No hard memory limits needed.

---

## Testing Requirements

### Additional Test Coverage Needed

#### Story 2.1: Daemon Service Tests

**New Unit Tests:**
```python
def test_fts_cache_basic_operations():
    """Test FTS index caching."""
    service = CIDXDaemonService()

    # First FTS query - cache miss
    result1 = service.exposed_query_fts("/project1", "test")
    assert service.cache["/project1"].fts_available
    assert service.cache["/project1"].fts_access_count == 1

    # Second FTS query - cache hit
    result2 = service.exposed_query_fts("/project1", "test")
    assert service.cache["/project1"].fts_access_count == 2

def test_hybrid_search_parallel_execution():
    """Test hybrid search executes semantic + FTS in parallel."""
    service = CIDXDaemonService()

    start = time.perf_counter()
    result = service.exposed_query_hybrid("/project", "test")
    duration = time.perf_counter() - start

    # Parallel execution should be close to max(semantic, fts), not sum
    assert duration < 1.5  # Not 2.5s (sum of both)
    assert result["semantic_count"] > 0
    assert result["fts_count"] > 0

def test_fts_unavailable_graceful_handling():
    """Test daemon handles missing FTS index gracefully."""
    service = CIDXDaemonService()

    # Query project without FTS index
    result = service.exposed_query_fts("/no-fts-project", "test")

    assert "error" in result
    assert "not available" in result["error"]
```

**New Integration Tests:**
```python
def test_real_fts_index_caching():
    """Test with actual Tantivy index files."""
    daemon = start_test_daemon()

    # First FTS query - loads from disk
    start = time.perf_counter()
    result1 = query_fts_daemon("/real/project", "function")
    load_time = time.perf_counter() - start

    # Second FTS query - uses cache
    start = time.perf_counter()
    result2 = query_fts_daemon("/real/project", "function")
    cache_time = time.perf_counter() - start

    assert cache_time < load_time * 0.1  # 90% faster

def test_hybrid_search_result_merging():
    """Test hybrid search merges results correctly."""
    daemon = start_test_daemon()

    result = query_hybrid_daemon("/project", "authentication")

    # Verify both sources represented
    assert result["semantic_count"] > 0
    assert result["fts_count"] > 0

    # Verify merging (some results may overlap)
    assert result["merged_count"] <= result["semantic_count"] + result["fts_count"]
```

#### Story 2.3: Client Delegation Tests

**New Unit Tests:**
```python
def test_fts_query_delegation():
    """Test FTS query routes to daemon."""
    cli = LightweightCLI()

    with patch_daemon_connection() as mock_conn:
        cli.query("test", fts=True)

        # Verify FTS-specific RPC call
        mock_conn.root.query_fts.assert_called_once()

def test_hybrid_query_delegation():
    """Test hybrid query routes to daemon."""
    cli = LightweightCLI()

    with patch_daemon_connection() as mock_conn:
        cli.query("test", fts=True, semantic=True)

        # Verify hybrid RPC call
        mock_conn.root.query_hybrid.assert_called_once()
```

---

## Risk Analysis

### New Risks Introduced by FTS Integration

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Tantivy library unavailable in daemon | High | Low | Graceful degradation, clear error messages |
| FTS index corruption | Medium | Low | Daemon detects and reports, fallback to semantic |
| Memory growth with FTS caching | Medium | Medium | TTL eviction, monitor both index types |
| Hybrid search complexity | Medium | Low | Thorough testing, reuse existing parallel execution |
| Different Tantivy versions | Low | Low | Pin tantivy==0.25.0 in requirements |

### Mitigation Strategies

**Strategy 1: Graceful FTS Degradation**
```python
# In daemon service
if not tantivy_available:
    logger.warning("Tantivy not installed - FTS queries will fail")
    entry.fts_available = False

# In client
if fts_query and not daemon_supports_fts:
    console.print("[yellow]Daemon doesn't support FTS, using standalone[/yellow]")
    return _query_standalone(query, fts=True)
```

**Strategy 2: Index Health Checks**
```python
# In daemon service
def _verify_tantivy_index(self, index_path: Path) -> bool:
    """Verify Tantivy index integrity."""
    try:
        index = tantivy.Index.open(str(index_path))
        searcher = index.searcher()
        doc_count = searcher.num_docs
        return doc_count > 0
    except:
        return False
```

**Strategy 3: Unified Cache Management**
```python
# Single TTL for both index types - simplicity wins
class CacheEntry:
    def __init__(self):
        self.ttl_minutes = 10  # Both semantic and FTS use same TTL (10 min default)
        # Any access to either index type refreshes TTL for both
```

---

## Documentation Requirements

### Updates to Epic Documentation

**Section to Add: "FTS Support"**

```markdown
## FTS Query Support

The daemon service supports Full-Text Search (FTS) queries using Tantivy indexes:

### FTS Query Endpoint
- **Method:** `exposed_query_fts()`
- **Caching:** Tantivy searcher cached in memory
- **Performance:** <100ms with warm cache (95% faster than baseline)
- **Filtering:** Language and path filters supported

### Hybrid Search Endpoint
- **Method:** `exposed_query_hybrid()`
- **Execution:** Parallel semantic + FTS search
- **Result Merging:** Weighted scoring with configurable weights
- **Performance:** ~950ms with warm cache (69% faster than baseline)

### Configuration
```json
{
  "daemon": {
    "enabled": true,
    "ttl_minutes": 10,
    "auto_shutdown_on_idle": true,
    "max_retries": 4,
    "retry_delays_ms": [100, 500, 1000, 2000],
    "eviction_check_interval_seconds": 60
  }
}
```

### Usage Examples

**FTS Query:**
```bash
cidx query "DatabaseManager" --fts --quiet
# With daemon: ~100ms (cached)
# Without daemon: ~2.2s
```

**Hybrid Search:**
```bash
cidx query "authentication" --fts --semantic --quiet
# With daemon: ~950ms (cached)
# Without daemon: ~3.5s
```

### Troubleshooting

**"FTS index not available"**
- Run `cidx index --fts` to create FTS index
- Check `.code-indexer/tantivy_index/` exists
- Verify `tantivy` library installed

**"Daemon doesn't support FTS"**
- Ensure daemon service has tantivy installed
- Check daemon logs for import errors
- Restart daemon with `cidx daemon restart`
```

---

## Implementation Roadmap

### Recommended Approach

**Phase 1: Update Epic Documentation** (1 hour)
- [ ] Update Feat_CIDXDaemonization.md with FTS requirements
- [ ] Add FTS section to architecture diagrams
- [ ] Update performance projections with FTS data
- [ ] Add FTS to success metrics

**Phase 2: Update Story 2.1** (2 hours)
- [ ] Extend CacheEntry with FTS fields
- [ ] Add exposed_query_fts() method
- [ ] Add exposed_query_hybrid() method
- [ ] Update status endpoint
- [ ] Add FTS acceptance criteria

**Phase 3: Update Story 2.3** (1 hour)
- [ ] Add FTS query delegation to LightweightCLI
- [ ] Add hybrid query delegation
- [ ] Update query type detection logic
- [ ] Add FTS acceptance criteria

**Phase 4: Expand Test Coverage** (3 hours)
- [ ] Add FTS caching unit tests
- [ ] Add hybrid search unit tests
- [ ] Add FTS integration tests
- [ ] Add client delegation tests

**Total Estimated Effort:** 7 hours of documentation/planning updates

**Implementation Effort** (when stories are executed):
- Story 2.1 additions: +2 days (10 story points → 12 story points)
- Story 2.3 additions: +0.5 days (5 story points → 6 story points)
- **Total:** +2.5 days to epic timeline

---

## Design Decisions (CONFIRMED)

1. **FTS TTL Strategy:** ✅ Same TTL as semantic indexes
   - Both semantic and FTS use same 10-minute default TTL
   - Simplifies configuration and mental model
   - Single `ttl_minutes` setting applies to both
   - Eviction check runs every 60 seconds

2. **Hybrid Search Behavior:** ✅ Matches current CLI exactly
   - `--fts` alone = FTS-only search
   - `--semantic` alone = semantic-only search (default)
   - `--fts --semantic` together = hybrid search with parallel execution
   - **Daemon must replicate this exact behavior - no changes**
   - Current CLI behavior defines the contract

3. **Fallback Behavior:** ✅ Same as current implementation
   - If FTS query fails, report error (no automatic fallback to semantic)
   - Match existing CLI error handling behavior exactly
   - User explicitly requested FTS, respect that intent
   - 2 restart attempts before fallback to standalone

4. **Socket Architecture:** ✅ Unix sockets only, per-repository
   - Socket at `.code-indexer/daemon.sock`
   - Socket binding as atomic lock (no PID files)
   - One daemon per indexed repository
   - Multi-client concurrent access supported

5. **PoC Story 2.0:** ✅ ACTIVE - Required for validation
   - **Status changed from CANCELLED to ACTIVE**
   - PoC is essential to validate architecture before full implementation
   - Will include FTS query scenarios in performance measurements

---

## Conclusion

**Summary of Required Changes:**

1. **Epic-Level Updates:**
   - Add FTS to architecture overview
   - Update performance projections
   - Add FTS to success metrics

2. **Story 2.1 Updates:** (Core Daemon Service)
   - Extend cache to include Tantivy indexes
   - Add exposed_query_fts() method
   - Add exposed_query_hybrid() method
   - Update status endpoint for FTS

3. **Story 2.3 Updates:** (Client Delegation)
   - Add FTS query delegation
   - Add hybrid query delegation
   - Update query type detection

4. **Testing Updates:**
   - Add 15+ new test cases for FTS caching
   - Add hybrid search integration tests
   - Add client delegation tests

**Impact Assessment:**
- Timeline: +2.5 days to epic
- Complexity: Medium (FTS is production-ready, integration is straightforward)
- Risk: Low (graceful degradation, reuse existing patterns)
- Value: Very High (95% performance gain for FTS queries)

**Recommendation:** Proceed with FTS integration into daemonization epic. The value proposition is extremely strong, especially for FTS queries which see 95% performance improvement with caching.

---

## Next Steps

1. ✅ Review this analysis document
2. ⏳ Discuss questions with stakeholders
3. ⏳ Update epic and story files with FTS requirements
4. ⏳ Re-estimate story points with FTS scope
5. ⏳ Proceed with epic implementation (starting with Story 2.1)
