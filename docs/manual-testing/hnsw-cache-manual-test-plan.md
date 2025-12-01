# Manual Test Plan: HNSW Index Cache Performance (Story #526)

## Overview

This manual test plan validates server-side HNSW index caching performance improvements in real deployment environment. Tests measure actual cache performance with production-scale repositories to verify the expected 100-1800x speedup.

## Prerequisites

### Required Environment

- CIDX server deployed to test environment (192.168.60.30 or other)
- SSH access to test server
- Real repository indexed with HNSW indexes (e.g., code-indexer itself)
- Server mode enabled (cache initialized automatically on server bootstrap)
- Access to server logs and metrics

### Required Tools

- curl (HTTP requests)
- jq (JSON parsing)
- time command (performance measurement)
- SSH client

## Prerequisite Verification: Cache Initialization

**CRITICAL**: Before executing any test scenarios, verify that the HNSW cache is initialized on server startup.

### Verification Steps

1. SSH to test server:
   ```bash
   ssh sebabattig@192.168.60.30
   ```

2. Check server logs for cache initialization:
   ```bash
   sudo journalctl -u cidx-server --since "5 minutes ago" | grep "HNSW index cache initialized"
   ```

   Expected output:
   ```
   HNSW index cache initialized (TTL: 600s)
   ```

3. Verify cache statistics endpoint is accessible:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq .
   ```

   Expected response:
   ```json
   {
     "cached_repositories": 0,
     "total_entries": 0,
     "hit_count": 0,
     "miss_count": 0
   }
   ```

### Acceptance Criteria

- [ ] Server logs show "HNSW index cache initialized" message
- [ ] Cache statistics endpoint returns valid JSON
- [ ] Server is running (systemctl status shows "active")

**STOP**: If prerequisite verification fails, DO NOT proceed with test scenarios. Cache is not initialized and all tests will show degraded performance.

## Test Scenario 1: Cold Query Performance (Cache Miss)

### Objective

Measure baseline query performance when HNSW index must be loaded from disk.

### Setup

1. SSH to test server:
   ```bash
   ssh sebabattig@192.168.60.30
   ```

2. Restart CIDX server to clear cache:
   ```bash
   echo "PASSWORD" | sudo -S systemctl restart cidx-server
   ```

3. Verify server is running:
   ```bash
   systemctl status cidx-server --no-pager
   ```

4. Wait 5 seconds for server to stabilize

### Execution

1. Execute cold query with timing measurement:
   ```bash
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/indexed/repository",
       "query": "authentication login user",
       "limit": 10
     }' | jq .
   ```

2. Record response time from `time` output (real time)

3. Verify query returned results:
   ```bash
   # Check that results array is non-empty
   curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/indexed/repository",
       "query": "authentication login user",
       "limit": 10
     }' | jq '.results | length'
   ```

### Expected Results

- Response time: 200-400ms (OS page cache benefit)
- Results: Non-empty array with 1-10 results
- HTTP status: 200 OK
- No errors in response

### Acceptance Criteria

- [ ] Query completes successfully (HTTP 200)
- [ ] Response time is 200-400ms
- [ ] Results array contains at least 1 result
- [ ] No error messages in server logs

## Test Scenario 2: Warm Query Performance (Cache Hit)

### Objective

Measure query performance when HNSW index is cached in memory.

### Setup

1. Ensure server is still running from Scenario 1 (no restart)
2. Cache should contain HNSW index from previous query

### Execution

1. Execute same query again with timing:
   ```bash
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/indexed/repository",
       "query": "authentication login user",
       "limit": 10
     }' | jq .
   ```

2. Record response time from `time` output

3. Repeat query 5 times to verify consistent performance:
   ```bash
   for i in {1..5}; do
     echo "Query $i:"
     time curl -s -X POST http://localhost:8000/query/semantic \
       -H "Content-Type: application/json" \
       -d '{
         "repository_path": "/path/to/indexed/repository",
         "query": "authentication login user",
         "limit": 10
       }' > /dev/null
   done
   ```

### Expected Results

- Response time: <10ms (typically <1ms)
- Results: Same as cold query (consistent)
- HTTP status: 200 OK
- No errors in response

### Acceptance Criteria

- [ ] Query completes successfully (HTTP 200)
- [ ] Response time is <10ms
- [ ] Results are identical to cold query
- [ ] All 5 repeated queries complete in <10ms
- [ ] No error messages in server logs

## Test Scenario 3: Cache Statistics Validation

### Objective

Verify cache statistics endpoint returns accurate hit/miss metrics.

### Setup

1. Continue from Scenario 2 (server still running with cached index)
2. Cache should have 1 miss (cold query) and 1+ hits (warm queries)

### Execution

1. Obtain authentication token (if not already obtained):
   ```bash
   # Login to get JWT token
   TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "your_password"}' | jq -r '.access_token')

   echo "Token: $TOKEN"
   ```

2. Query cache statistics endpoint (requires authentication):
   ```bash
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/cache/stats | jq .
   ```

3. Verify statistics structure:
   ```bash
   # Check hit count
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/cache/stats | jq '.hit_count'

   # Check miss count
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/cache/stats | jq '.miss_count'

   # Check hit ratio
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/cache/stats | jq '.hit_ratio'

   # Check cached repositories
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/cache/stats | jq '.cached_repositories'
   ```

4. Calculate expected hit ratio:
   - If you ran cold query once (1 miss) and warm queries 6 times (6 hits)
   - Expected hit ratio: 6 / (1 + 6) = 0.857 (85.7%)

### Expected Results

```json
{
  "cached_repositories": 1,
  "total_memory_mb": 100.0,
  "hit_count": 6,
  "miss_count": 1,
  "hit_ratio": 0.857,
  "eviction_count": 0,
  "per_repository_stats": {
    "/path/to/indexed/repository": {
      "access_count": 7,
      "last_accessed": "2025-11-30T12:34:56.789",
      "created_at": "2025-11-30T12:30:00.123",
      "ttl_remaining_seconds": 543.2
    }
  }
}
```

### Acceptance Criteria

- [ ] Endpoint requires authentication (401 without token, 200 with token)
- [ ] hit_count matches expected count (6 if following plan)
- [ ] miss_count equals 1 (from cold query)
- [ ] hit_ratio is approximately 0.857 (85.7%)
- [ ] cached_repositories is at least 1
- [ ] per_repository_stats contains tested repository path
- [ ] Repository access_count equals hit_count + miss_count (7 in this example)

## Test Scenario 4: Speedup Ratio Validation

### Objective

Calculate and validate actual speedup ratio meets acceptance criteria (>100x).

### Setup

1. Use timing measurements from Scenario 1 (cold) and Scenario 2 (warm)

### Execution

1. Calculate speedup ratio:
   ```bash
   # Manual calculation:
   # speedup = cold_time_ms / warm_time_ms

   # Example with recorded times:
   # Cold: 277ms
   # Warm: 0.15ms
   # Speedup: 277 / 0.15 = 1,846x
   ```

2. Document results:
   ```
   Cold query time:  _____ms
   Warm query time:  _____ms
   Speedup ratio:    _____x
   ```

### Expected Results

- Speedup ratio: >100x (targeting 200-1800x)
- Cold query: 200-400ms
- Warm query: <10ms

### Acceptance Criteria

- [ ] Speedup ratio is greater than 100x
- [ ] Cold query time is between 200-400ms
- [ ] Warm query time is less than 10ms
- [ ] Speedup meets or exceeds documented target

## Test Scenario 5: TTL-Based Eviction

### Objective

Verify cache entries are evicted after TTL expires (default: 10 minutes).

### Setup

1. Continue from previous scenarios with cached index
2. Default TTL: 600 seconds (10 minutes)

### Execution

1. Record current cache statistics:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq '.active_entries'
   ```

2. Wait for TTL expiration (or configure shorter TTL for testing):
   ```bash
   # Option A: Wait 10+ minutes
   sleep 660  # 11 minutes

   # Option B: Configure shorter TTL for testing
   # In server config or environment:
   # CIDX_HNSW_CACHE_TTL_SECONDS=60  # 1 minute
   ```

3. Check cache statistics after TTL expiration:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq .
   ```

4. Execute query to verify cache rebuild:
   ```bash
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/indexed/repository",
       "query": "authentication login user",
       "limit": 10
     }' | jq .
   ```

### Expected Results

- After TTL expiration: active_entries should be 0 or reduced
- Query after expiration: slower (cache miss, rebuild required)
- Cache statistics: miss_count increments

### Acceptance Criteria

- [ ] Cache entries are evicted after TTL expiration
- [ ] Query after eviction shows cache miss behavior (slower)
- [ ] Statistics correctly reflect new miss
- [ ] Cache can rebuild and continue functioning

## Test Scenario 6: Multi-Repository Isolation

### Objective

Verify cache properly isolates HNSW indexes by repository path.

### Setup

1. Have at least 2 indexed repositories available on server
2. Both repositories should have HNSW indexes

### Execution

1. Query first repository:
   ```bash
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/repository1",
       "query": "test query",
       "limit": 10
     }' | jq .
   ```

2. Query second repository:
   ```bash
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/repository2",
       "query": "test query",
       "limit": 10
     }' | jq .
   ```

3. Check cache statistics for both repositories:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq '.per_repository'
   ```

4. Repeat queries and verify independent hit tracking:
   ```bash
   # Repeat repository1 query (should be cache hit)
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/repository1",
       "query": "test query",
       "limit": 10
     }' | jq .

   # Repeat repository2 query (should be cache hit)
   time curl -X POST http://localhost:8000/query/semantic \
     -H "Content-Type: application/json" \
     -d '{
       "repository_path": "/path/to/repository2",
       "query": "test query",
       "limit": 10
     }' | jq .
   ```

5. Verify statistics:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq .
   ```

### Expected Results

- Each repository has independent cache entry
- Each repository has separate hit/miss tracking
- Both repositories show cache hit speedup on repeated queries
- active_entries shows 2 (one per repository)

### Acceptance Criteria

- [ ] per_repository contains both repository paths
- [ ] Each repository shows 1 miss, 1+ hits
- [ ] active_entries equals 2
- [ ] Both repositories benefit from caching independently
- [ ] No cross-repository cache contamination

## Test Scenario 7: Server Restart Cache Clearing

### Objective

Verify cache is properly cleared on server restart.

### Setup

1. Have queries cached from previous scenarios

### Execution

1. Record pre-restart cache statistics:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq . > /tmp/cache_before_restart.json
   ```

2. Restart server:
   ```bash
   echo "PASSWORD" | sudo -S systemctl restart cidx-server
   ```

3. Wait for server to stabilize:
   ```bash
   sleep 5
   systemctl status cidx-server --no-pager
   ```

4. Check post-restart cache statistics:
   ```bash
   curl -s http://localhost:8000/cache/stats | jq .
   ```

### Expected Results

- Cache statistics reset to zero
- active_entries: 0
- total_hits: 0
- total_misses: 0

### Acceptance Criteria

- [ ] All cache statistics are reset to zero
- [ ] No stale cache entries remain
- [ ] Server functions correctly after restart
- [ ] First query after restart shows cache miss behavior

## Summary of Evidence Collection

### Required Evidence for Each Scenario

1. Cold Query Performance
   - Screenshot/copy of curl command with timing output
   - Response body showing results
   - Server logs excerpt (if errors)

2. Warm Query Performance
   - Screenshot/copy of curl command with timing output
   - Timing comparison table (cold vs warm)
   - Multiple query timings to verify consistency

3. Cache Statistics
   - Full JSON output from /cache/stats endpoint
   - Verification of hit/miss counts
   - Per-repository breakdown

4. Speedup Ratio
   - Calculation showing cold_time / warm_time
   - Documented speedup ratio with evidence
   - Comparison against acceptance criteria (>100x)

5. TTL Eviction
   - Cache stats before TTL expiration
   - Cache stats after TTL expiration
   - Query timing showing cache rebuild

6. Multi-Repository Isolation
   - Cache stats showing multiple repositories
   - Independent hit/miss tracking evidence
   - Timing measurements for both repositories

7. Server Restart
   - Cache stats before restart
   - Cache stats after restart
   - Evidence of clean cache clearing

## Overall Acceptance Criteria

The manual testing execution is considered SUCCESSFUL when:

- [ ] All 7 test scenarios pass their individual acceptance criteria
- [ ] Cold query performance: 200-400ms
- [ ] Warm query performance: <10ms
- [ ] Speedup ratio: >100x (documented and verified)
- [ ] Cache statistics are accurate and consistent
- [ ] TTL-based eviction works correctly
- [ ] Multi-repository isolation is maintained
- [ ] Server restart properly clears cache
- [ ] No errors or warnings in server logs during testing
- [ ] All evidence is collected and documented

## Notes for Manual Test Executor

- Document all timing measurements precisely
- Include screenshots or command output copies
- Note any deviations from expected results
- Capture server logs for any failures
- Test with production-scale repositories when possible
- Verify cache configuration matches deployment environment
- Document actual TTL settings used during testing
