# Story 1.1: Parallel Index Loading During Query

## Story Overview

**Story Points:** 3 (1 day)
**Priority:** HIGH - Quick Win
**Dependencies:** None
**Risk:** Low

**As a** developer using CIDX for semantic code search
**I want** index loading and embedding generation to execute in parallel
**So that** my queries complete 376-467ms faster without any API changes

## Current Implementation Analysis

### Sequential Execution Flow (Current)
```python
# filesystem_vector_store.py:1056-1090 (approximate)
def search(self, query: str, limit: int = 10) -> List[SearchResult]:
    # Step 1: Load HNSW index (180ms)
    hnsw_index = self._load_hnsw_index()

    # Step 2: Load ID mapping (196ms)
    id_mapping = self._load_id_mapping()

    # Step 3: Generate embedding (792ms) - WAITS for steps 1&2
    query_embedding = self.embedding_service.generate(query)

    # Step 4: Search index (62ms)
    indices, distances = hnsw_index.search(query_embedding, limit)

    # Step 5: Map results
    results = self._map_results(indices, distances, id_mapping)
    return results
```

**Total Time:** 376ms + 792ms + 62ms = 1230ms

## Proposed Parallel Implementation

### Target Implementation
```python
def search(self, query: str, limit: int = 10) -> List[SearchResult]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Launch parallel operations
        index_future = executor.submit(self._load_indexes_parallel)
        embedding_future = executor.submit(
            self.embedding_service.generate, query
        )

        # Wait for both to complete
        hnsw_index, id_mapping = index_future.result()
        query_embedding = embedding_future.result()

        # Search (sequential - depends on both)
        indices, distances = hnsw_index.search(query_embedding, limit)

        # Map results
        results = self._map_results(indices, distances, id_mapping)
        return results

def _load_indexes_parallel(self) -> Tuple[HNSWIndex, Dict]:
    """Load both indexes in a single thread."""
    hnsw_index = self._load_hnsw_index()
    id_mapping = self._load_id_mapping()
    return hnsw_index, id_mapping
```

**Optimized Time:** max(376ms, 792ms) + 62ms = 854ms
**Time Saved:** 1230ms - 854ms = **376ms (31% reduction)**

## Acceptance Criteria

### Functional Requirements
- [ ] Index loading and embedding generation execute in parallel
- [ ] Query results remain identical to sequential implementation
- [ ] All existing unit tests pass without modification
- [ ] All existing integration tests pass without modification
- [ ] Error handling works correctly for both parallel paths

### Performance Requirements
- [ ] Minimum 350ms reduction in query latency
- [ ] No increase in memory usage beyond thread overhead
- [ ] No thread leaks after 1000 consecutive queries
- [ ] Graceful degradation if ThreadPoolExecutor unavailable

### Code Quality Requirements
- [ ] Thread-safe implementation with proper synchronization
- [ ] Clear comments explaining parallelization strategy
- [ ] Consistent error propagation from both threads
- [ ] Clean resource cleanup on all exit paths

## Implementation Tasks

### Task 1: Refactor Search Method
```python
# Location: filesystem_vector_store.py:1056-1090
# Action: Introduce ThreadPoolExecutor for parallel execution
```

### Task 2: Create Parallel Index Loader
```python
# New method: _load_indexes_parallel()
# Combines HNSW and ID mapping loads in single thread
```

### Task 3: Update Error Handling
```python
# Ensure exceptions from either thread are properly caught and re-raised
# Maintain existing error message format and logging
```

### Task 4: Add Performance Instrumentation
```python
# Add timing measurements for validation
# Log parallel vs sequential timings in debug mode
```

## Testing Approach

### Unit Tests
```python
def test_parallel_index_loading():
    """Verify parallel execution occurs."""
    with patch('ThreadPoolExecutor') as mock_executor:
        # Verify submit called twice
        # Verify result() called on both futures

def test_parallel_error_handling():
    """Test error propagation from both threads."""
    # Test index loading failure
    # Test embedding generation failure
    # Test both failing simultaneously

def test_parallel_performance():
    """Measure performance improvement."""
    # Time sequential execution
    # Time parallel execution
    # Assert ≥350ms improvement
```

### Integration Tests
```python
def test_concurrent_queries():
    """Verify multiple parallel queries work correctly."""
    # Launch 10 concurrent queries
    # Verify all complete successfully
    # Verify no resource leaks
```

### Manual Testing Script
```bash
#!/bin/bash
# Performance validation script

# Baseline measurement (before changes)
echo "Baseline performance (sequential):"
for i in {1..10}; do
    time cidx query "authentication logic" --quiet
done

# Apply changes and re-measure
echo "Optimized performance (parallel):"
for i in {1..10}; do
    time cidx query "authentication logic" --quiet
done

# Calculate average improvement
```

## Edge Cases and Error Scenarios

### Scenario 1: Index File Missing
- **Current:** FileNotFoundError propagated
- **Parallel:** Same error propagated from thread
- **Test:** Verify identical error behavior

### Scenario 2: Embedding Service Failure
- **Current:** Service exception propagated
- **Parallel:** Same exception from embedding thread
- **Test:** Verify identical error behavior

### Scenario 3: Both Operations Fail
- **Current:** First error propagated
- **Parallel:** First completed error propagated
- **Test:** Verify reasonable error (either is acceptable)

### Scenario 4: Thread Pool Exhaustion
- **Mitigation:** Fall back to sequential execution
- **Test:** Verify graceful degradation

## Definition of Done

- [ ] Code implementation complete with parallelization
- [ ] All unit tests passing (including new parallel tests)
- [ ] All integration tests passing
- [ ] Performance improvement validated (≥350ms reduction)
- [ ] Code review completed and approved
- [ ] No memory leaks detected over 1000 queries
- [ ] Documentation updated with parallelization notes
- [ ] Manual testing script confirms improvement

## Technical Notes

### Thread Safety Considerations
- HNSW index loading is read-only (thread-safe)
- ID mapping loading is read-only (thread-safe)
- Embedding service must be thread-safe (verify)
- No shared mutable state between threads

### Performance Measurement Points
```python
# Add timing instrumentation at these points:
start_total = time.perf_counter()
start_loading = time.perf_counter()
# ... parallel execution ...
end_loading = time.perf_counter()
start_search = time.perf_counter()
# ... search execution ...
end_search = time.perf_counter()
end_total = time.perf_counter()

# Log in debug mode:
logger.debug(f"Parallel load: {end_loading - start_loading:.3f}s")
logger.debug(f"Search: {end_search - start_search:.3f}s")
logger.debug(f"Total: {end_total - start_total:.3f}s")
```

## References

**Conversation Context:**
- "ThreadPoolExecutor-based parallelization in filesystem_vector_store.py search()"
- "Thread-safe index loading with locks"
- "Easy win: 467ms saved per query (40% reduction)"
- "Integration points: filesystem_vector_store.py:1056-1090 for parallelization"