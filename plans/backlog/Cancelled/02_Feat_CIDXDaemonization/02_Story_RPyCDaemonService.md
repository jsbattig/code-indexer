# Story 2.1: RPyC Daemon Service with In-Memory Index Caching

## Story Overview

**Story Points:** 8 (3 days)
**Priority:** HIGH
**Dependencies:** Story 2.0 (PoC must pass GO criteria)
**Risk:** Medium

**As a** CIDX power user running hundreds of queries
**I want** a persistent daemon service that caches indexes in memory
**So that** repeated queries to the same project complete in under 1 second

## Technical Requirements

### Core Service Implementation

```python
# daemon_service.py
import rpyc
from rpyc.utils.server import ThreadedServer
from threading import RLock, Lock
from datetime import datetime, timedelta
from pathlib import Path
import pickle
import json

class CIDXDaemonService(rpyc.Service):
    def __init__(self):
        self.cache = {}  # {project_path: CacheEntry}
        self.cache_lock = RLock()  # Global cache access

    class CacheEntry:
        def __init__(self, project_path):
            self.project_path = project_path
            self.hnsw_index = None
            self.id_mapping = None
            self.last_accessed = datetime.now()
            self.ttl_minutes = 60  # Default, configurable
            self.read_lock = RLock()  # For concurrent reads
            self.write_lock = Lock()  # For serialized writes
            self.access_count = 0

    def exposed_query(self, project_path, query, limit=10, **kwargs):
        """Execute semantic search with caching."""
        project_path = Path(project_path).resolve()

        # Get or create cache entry
        with self.cache_lock:
            if str(project_path) not in self.cache:
                self.cache[str(project_path)] = self.CacheEntry(project_path)
            entry = self.cache[str(project_path)]

        # Concurrent read with RLock
        with entry.read_lock:
            # Load indexes if not cached
            if entry.hnsw_index is None:
                self._load_indexes(entry)

            # Update access time
            entry.last_accessed = datetime.now()
            entry.access_count += 1

            # Perform search
            results = self._execute_search(
                entry.hnsw_index,
                entry.id_mapping,
                query,
                limit
            )

        return results

    def exposed_index(self, project_path, callback=None, **kwargs):
        """Perform indexing with serialized writes."""
        project_path = Path(project_path).resolve()

        # Get or create cache entry
        with self.cache_lock:
            if str(project_path) not in self.cache:
                self.cache[str(project_path)] = self.CacheEntry(project_path)
            entry = self.cache[str(project_path)]

        # Serialized write with Lock
        with entry.write_lock:
            # Perform indexing
            self._perform_indexing(project_path, callback, **kwargs)

            # Invalidate cache
            entry.hnsw_index = None
            entry.id_mapping = None
            entry.last_accessed = datetime.now()

        return {"status": "completed", "project": str(project_path)}

    def exposed_get_status(self):
        """Return daemon and cache statistics."""
        with self.cache_lock:
            status = {
                "running": True,
                "cache_entries": len(self.cache),
                "projects": []
            }

            for path, entry in self.cache.items():
                status["projects"].append({
                    "path": path,
                    "cached": entry.hnsw_index is not None,
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count,
                    "ttl_minutes": entry.ttl_minutes
                })

        return status

    def exposed_clear_cache(self, project_path=None):
        """Clear cache for specific project or all."""
        with self.cache_lock:
            if project_path:
                project_path = str(Path(project_path).resolve())
                if project_path in self.cache:
                    del self.cache[project_path]
                    return {"cleared": project_path}
            else:
                count = len(self.cache)
                self.cache.clear()
                return {"cleared_all": count}

    def _load_indexes(self, entry):
        """Load HNSW and ID mapping indexes."""
        # Implementation from filesystem_vector_store.py
        vector_store = FilesystemVectorStore(entry.project_path)

        # Load HNSW index
        entry.hnsw_index = vector_store._load_hnsw_index()

        # Load ID mapping
        entry.id_mapping = vector_store._load_id_mapping()
```

### TTL-Based Cache Eviction

```python
# daemon_service.py (continued)
import threading

class CacheEvictionThread(threading.Thread):
    def __init__(self, daemon_service, check_interval=60):
        super().__init__(daemon=True)
        self.daemon_service = daemon_service
        self.check_interval = check_interval
        self.running = True

    def run(self):
        """Background thread for TTL-based eviction."""
        while self.running:
            try:
                self._check_and_evict()
                threading.Event().wait(self.check_interval)
            except Exception as e:
                logger.error(f"Eviction thread error: {e}")

    def _check_and_evict(self):
        """Check cache entries and evict expired ones."""
        now = datetime.now()
        to_evict = []

        with self.daemon_service.cache_lock:
            for path, entry in self.daemon_service.cache.items():
                ttl_delta = timedelta(minutes=entry.ttl_minutes)
                if now - entry.last_accessed > ttl_delta:
                    to_evict.append(path)

            # Evict expired entries
            for path in to_evict:
                logger.info(f"Evicting cache for {path} (TTL expired)")
                del self.daemon_service.cache[path]

    def stop(self):
        self.running = False
```

### Health Monitoring

```python
# health_monitor.py
class HealthMonitor:
    def __init__(self, daemon_service):
        self.daemon_service = daemon_service
        self.start_time = datetime.now()
        self.query_count = 0
        self.error_count = 0

    def record_query(self, duration):
        """Track query metrics."""
        self.query_count += 1

    def record_error(self, error):
        """Track errors."""
        self.error_count += 1
        logger.error(f"Query error: {error}")

    def get_health(self):
        """Return health metrics."""
        uptime = datetime.now() - self.start_time
        return {
            "status": "healthy" if self.error_count < 10 else "degraded",
            "uptime_seconds": uptime.total_seconds(),
            "queries_processed": self.query_count,
            "errors": self.error_count,
            "error_rate": self.error_count / max(1, self.query_count),
            "cache_size": len(self.daemon_service.cache)
        }
```

## Acceptance Criteria

### Functional Requirements
- [ ] Daemon service starts and accepts RPyC connections
- [ ] Indexes cached in memory after first load
- [ ] Cache hit returns results in <100ms
- [ ] TTL eviction works correctly (60 min default)
- [ ] Concurrent reads supported via RLock
- [ ] Writes serialized via Lock per project
- [ ] Status endpoint returns accurate statistics
- [ ] Clear cache endpoint works for single/all projects

### Performance Requirements
- [ ] Cache hit query time: <100ms (excluding embedding)
- [ ] Memory usage stable over 1000 queries
- [ ] Support 10+ concurrent read queries
- [ ] Index load happens once per TTL period

### Reliability Requirements
- [ ] Daemon handles client disconnections gracefully
- [ ] Cache survives query errors
- [ ] Memory cleaned up on eviction
- [ ] Proper error propagation to client

## Implementation Tasks

### Task 1: Core Service Structure (Day 1)
- [ ] Create daemon_service.py with RPyC service class
- [ ] Implement CacheEntry data structure
- [ ] Add basic query and index methods
- [ ] Setup logging infrastructure

### Task 2: Caching Logic (Day 1)
- [ ] Implement index loading and caching
- [ ] Add cache lookup logic
- [ ] Implement TTL tracking
- [ ] Add access time updates

### Task 3: Concurrency Control (Day 2)
- [ ] Add RLock for concurrent reads
- [ ] Add Lock for serialized writes
- [ ] Test concurrent access patterns
- [ ] Verify no deadlocks

### Task 4: TTL Eviction (Day 2)
- [ ] Create background eviction thread
- [ ] Implement TTL checking logic
- [ ] Add safe eviction with locks
- [ ] Test eviction scenarios

### Task 5: Health & Monitoring (Day 3)
- [ ] Implement status endpoint
- [ ] Add health monitoring
- [ ] Create metrics collection
- [ ] Add diagnostic endpoints

### Task 6: Integration (Day 3)
- [ ] Integrate with filesystem_vector_store.py
- [ ] Wire up actual index loading
- [ ] Test with real data
- [ ] Performance validation

## Testing Strategy

### Unit Tests

```python
def test_cache_basic_operations():
    """Test cache get/set/evict."""
    service = CIDXDaemonService()

    # First query - cache miss
    result1 = service.exposed_query("/project1", "test")
    assert service.cache["/project1"].access_count == 1

    # Second query - cache hit
    result2 = service.exposed_query("/project1", "test")
    assert service.cache["/project1"].access_count == 2

def test_concurrent_reads():
    """Test multiple concurrent read queries."""
    service = CIDXDaemonService()

    def read_query(i):
        return service.exposed_query("/project", f"query {i}")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_query, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    assert service.cache["/project"].access_count == 10

def test_ttl_eviction():
    """Test TTL-based cache eviction."""
    service = CIDXDaemonService()

    # Add cache entry
    service.exposed_query("/project", "test")

    # Simulate TTL expiration
    entry = service.cache["/project"]
    entry.last_accessed = datetime.now() - timedelta(minutes=61)

    # Run eviction
    eviction_thread = CacheEvictionThread(service)
    eviction_thread._check_and_evict()

    assert "/project" not in service.cache
```

### Integration Tests

```python
def test_real_index_caching():
    """Test with actual index files."""
    # Start daemon
    daemon = start_test_daemon()

    # First query - loads from disk
    start = time.perf_counter()
    result1 = query_daemon("/real/project", "authentication")
    load_time = time.perf_counter() - start

    # Second query - uses cache
    start = time.perf_counter()
    result2 = query_daemon("/real/project", "authentication")
    cache_time = time.perf_counter() - start

    assert cache_time < load_time * 0.1  # 90% faster
```

### Performance Tests

```python
def test_cache_performance():
    """Measure cache hit performance."""
    service = CIDXDaemonService()

    # Warm cache
    service.exposed_query("/project", "warmup")

    # Measure cache hits
    times = []
    for i in range(100):
        start = time.perf_counter()
        service.exposed_query("/project", f"query {i}")
        times.append(time.perf_counter() - start)

    avg_time = sum(times) / len(times)
    assert avg_time < 0.1  # <100ms average
```

## Manual Testing Checklist

- [ ] Start daemon service manually
- [ ] Query same project multiple times
- [ ] Verify second query is faster (cache hit)
- [ ] Run concurrent queries from multiple terminals
- [ ] Let cache sit for >60 minutes, verify eviction
- [ ] Query multiple different projects
- [ ] Check daemon status endpoint
- [ ] Clear cache and verify re-load
- [ ] Kill daemon and verify restart

## Configuration Schema

```json
{
  "daemon": {
    "cache": {
      "ttl_minutes": 60,
      "eviction_check_interval": 60,
      "max_entries": null
    },
    "concurrency": {
      "max_connections": 100,
      "thread_pool_size": 20
    },
    "health": {
      "enable_monitoring": true,
      "metrics_interval": 60
    }
  }
}
```

## Error Handling Scenarios

### Scenario 1: Index File Not Found
- Log error with project path
- Return empty cache entry
- Let query fail with proper error

### Scenario 2: Memory Pressure
- Monitor system memory
- Trigger aggressive eviction if needed
- Log memory warnings

### Scenario 3: Concurrent Write During Read
- RLock prevents write during reads
- Reads wait for write completion
- Cache invalidated after write

### Scenario 4: Client Disconnect During Query
- RPyC handles cleanup
- Cache remains valid
- No partial state corruption

## Definition of Done

- [ ] Daemon service implemented with all endpoints
- [ ] In-memory caching working with TTL eviction
- [ ] Concurrent read/write locks properly implemented
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Performance targets met (<100ms cache hit)
- [ ] Health monitoring operational
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "Persistent service caching HNSW/ID indexes per project path"
- "Concurrent reads (RLock), serialized writes (Lock) per project"
- "Health monitoring and structured data returns"
- "TTL-based eviction (default 60 minutes, configurable)"
- "Background thread monitors idle time, evicts expired cached indexes"