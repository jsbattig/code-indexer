# Story 2.0: RPyC Performance PoC [CANCELLED]

## Story Overview

**Story Points:** 3 (1 day)
**Priority:** CRITICAL - BLOCKING
**Dependencies:** None
**Risk:** High (Architecture validation)
**Status:** ❌ CANCELLED
**Cancellation Date:** 2025-10-26

**Cancellation Reason:**
Acceptable performance achieved with Story 1.1 parallel execution (15-30% improvement, 175-265ms saved per query). ThreadPoolExecutor overhead (7-16%) deemed acceptable for the benefit. RPyC daemon complexity, ongoing maintenance burden, and architectural risk not justified for potentially incremental additional gains beyond parallel execution.

**As a** technical architect
**I need to** validate that the RPyC daemon architecture delivers promised performance gains
**So that** we can proceed with confidence or pivot to alternative solutions

## PoC Objectives

### Primary Goals
1. **Validate Performance Hypothesis:** Confirm ≥30% speedup is achievable
2. **Measure RPC Overhead:** Ensure <100ms communication overhead
3. **Verify Stability:** Test 100+ consecutive queries without issues
4. **Confirm Import Savings:** Validate 1.86s startup elimination

### Secondary Goals
- Assess RPyC learning curve and complexity
- Evaluate debugging/troubleshooting difficulty
- Test fallback mechanism reliability
- Measure memory footprint of daemon

## Success Criteria (GO/NO-GO Decision Points)

### GO Criteria (All must be met)
- [ ] **Performance:** ≥30% overall query speedup achieved
- [ ] **RPC Overhead:** <100ms communication overhead measured
- [ ] **Stability:** 100 consecutive queries without failure
- [ ] **Import Savings:** Startup time reduced from 1.86s to <100ms

### NO-GO Criteria (Any triggers pivot)
- [ ] Performance gain <30% (not worth complexity)
- [ ] RPC overhead >100ms (defeats purpose)
- [ ] Daemon crashes >1% of queries (unstable)
- [ ] Memory growth >100MB per 100 queries (leak)

## PoC Implementation Plan

### Phase 1: Minimal Daemon Service (4 hours)
```python
# poc_daemon.py
import rpyc
import time
from rpyc.utils.server import ThreadedServer

class PoCDaemonService(rpyc.Service):
    def on_connect(self, conn):
        # Pre-import heavy modules
        import rich
        import argparse
        from code_indexer.cli import main
        self.start_time = time.time()

    def exposed_query(self, query, project_path):
        # Simulate query with timing
        start = time.perf_counter()

        # Simulate index loading (would be cached)
        time.sleep(0.005)  # 5ms cache hit

        # Real embedding generation
        embedding_time = 0.792  # Measured from conversation

        # Simulate search
        search_time = 0.062

        total = time.perf_counter() - start
        return {
            "results": ["mock_result_1", "mock_result_2"],
            "timing": {
                "cache_hit": 0.005,
                "embedding": embedding_time,
                "search": search_time,
                "total": total
            }
        }

# Start daemon
server = ThreadedServer(PoCDaemonService, port=18812)
server.start()
```

### Phase 2: Minimal Client (2 hours)
```python
# poc_client.py
import rpyc
import time

def query_via_daemon(query, project_path):
    start = time.perf_counter()

    # Connect to daemon
    conn = rpyc.connect("localhost", 18812)
    connection_time = time.perf_counter() - start

    # Execute query
    result = conn.root.query(query, project_path)
    query_time = time.perf_counter() - start - connection_time

    conn.close()

    return {
        "result": result,
        "timing": {
            "connection": connection_time,
            "query": query_time,
            "total": time.perf_counter() - start
        }
    }

# Benchmark
for i in range(100):
    result = query_via_daemon("test query", "/path/to/project")
    print(f"Query {i}: {result['timing']['total']:.3f}s")
```

### Phase 3: Performance Measurements (2 hours)

#### Test 1: Baseline Measurement (No Daemon)
```bash
#!/bin/bash
# baseline_test.sh

echo "=== BASELINE TEST (No Daemon) ==="
for i in {1..10}; do
    start=$(date +%s%N)
    python -c "
import time
start = time.perf_counter()

# Simulate imports
import rich  # 200ms
import argparse  # 50ms
time.sleep(0.460)  # Other imports

# Simulate index loading
time.sleep(0.376)  # Index load time

# Simulate embedding + search
time.sleep(0.854)  # Processing time

print(f'Total: {time.perf_counter() - start:.3f}s')
"
done
```

#### Test 2: Daemon Cold Start
```python
# Test first query to daemon (cold cache)
def test_cold_start():
    # Start fresh daemon
    daemon = start_daemon()
    time.sleep(2)  # Let daemon initialize

    # First query (cold)
    result = query_via_daemon("test", "/project")
    assert result['timing']['total'] < 1.5  # Should be faster

    daemon.stop()
```

#### Test 3: Daemon Warm Cache
```python
# Test subsequent queries (warm cache)
def test_warm_cache():
    daemon = start_daemon()

    # Warm up
    query_via_daemon("warmup", "/project")

    # Measure warm queries
    times = []
    for i in range(10):
        result = query_via_daemon(f"query {i}", "/project")
        times.append(result['timing']['total'])

    avg_time = sum(times) / len(times)
    assert avg_time < 1.0  # Target: <1s with cache
```

#### Test 4: RPC Overhead
```python
def test_rpc_overhead():
    # Measure pure RPC round-trip
    conn = rpyc.connect("localhost", 18812)

    times = []
    for i in range(100):
        start = time.perf_counter()
        conn.root.exposed_ping()  # Minimal RPC call
        times.append(time.perf_counter() - start)

    avg_overhead = sum(times) / len(times)
    assert avg_overhead < 0.010  # <10ms overhead
```

### Phase 4: Stability Testing (2 hours)

```python
def test_stability():
    """Run 100 consecutive queries."""
    daemon = start_daemon()
    failures = 0

    for i in range(100):
        try:
            result = query_via_daemon(f"query {i}", "/project")
            assert result is not None
        except Exception as e:
            failures += 1
            print(f"Query {i} failed: {e}")

    success_rate = (100 - failures) / 100
    assert success_rate >= 0.99  # 99% success required
```

### Phase 5: Memory Profiling
```python
import psutil
import os

def test_memory_growth():
    """Monitor memory growth over queries."""
    daemon_pid = start_daemon_get_pid()
    process = psutil.Process(daemon_pid)

    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Run 100 queries
    for i in range(100):
        query_via_daemon(f"query {i}", f"/project{i % 10}")

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    growth = final_memory - initial_memory

    assert growth < 100  # <100MB growth acceptable
```

## PoC Deliverables

### Required Measurements
1. **Baseline Performance**
   - Current: 3.09s per query
   - Components: Startup (1.86s) + Processing (1.23s)

2. **Daemon Performance**
   - Cold start: Target <1.5s
   - Warm cache: Target <1.0s
   - Connection overhead: Target <50ms

3. **Stability Metrics**
   - Success rate over 100 queries
   - Memory growth pattern
   - CPU utilization

4. **Comparison Matrix**
```
| Metric              | Baseline | Daemon Cold | Daemon Warm | Improvement |
|---------------------|----------|-------------|-------------|-------------|
| Total Time          | 3.09s    | 1.5s        | 0.9s        | 71% (warm)  |
| Startup             | 1.86s    | 0.05s       | 0.05s       | 97%         |
| Index Load          | 0.376s   | 0.376s      | 0.005s      | 99% (cached)|
| Embedding           | 0.792s   | 0.792s      | 0.792s      | 0%          |
| Search              | 0.062s   | 0.062s      | 0.062s      | 0%          |
| RPC Overhead        | 0        | 0.02s       | 0.02s       | N/A         |
```

## GO/NO-GO Decision Framework

### Decision Meeting Agenda
1. Review performance measurements
2. Assess stability test results
3. Evaluate complexity/maintainability
4. Vote on GO/NO-GO decision

### IF GO:
- Proceed to Story 2.1 (Full daemon implementation)
- Commit to 2-week implementation timeline
- Assign resources for development

### IF NO-GO:
- Document why approach failed
- Consider alternatives:
  - Simple file-based caching
  - Background pre-loading service
  - Accept current performance
- Update epic with new approach

## Alternative Approaches (If NO-GO)

### Option 1: File-Based Index Cache
- Pre-compute and cache index files in optimized format
- Use mmap for fast loading
- Simpler but less performant

### Option 2: Background Pre-loader
- Service that pre-loads indexes for active projects
- No RPC complexity
- Higher memory usage

### Option 3: Accept Current Performance
- Focus on Story 1.1 (parallelization) only
- Document performance limitations
- Consider for future optimization

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| RPyC too complex | Keep PoC simple, assess maintainability |
| Performance insufficient | Define clear NO-GO criteria upfront |
| Stability issues | Extensive testing in PoC phase |
| Memory leaks | Profile memory during PoC |

## Definition of Done

- [ ] PoC daemon service implemented
- [ ] PoC client implemented
- [ ] All measurements collected and documented
- [ ] GO/NO-GO criteria evaluated
- [ ] Decision documented with rationale
- [ ] If NO-GO: Alternative approach selected
- [ ] If GO: Team briefed on implementation plan

## References

**Conversation Context:**
- "Validate daemon architecture before full implementation"
- "Measure: baseline vs daemon (cold/warm), RPyC overhead, import savings"
- "Decision criteria: ≥30% speedup, <100ms RPC overhead"
- "BLOCKING: Must complete before other daemon stories"