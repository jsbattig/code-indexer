# Story 2.1: RPyC Daemon Service with In-Memory Index Caching

## Story Overview

**Story Points:** 11 (4.5 days)
**Priority:** HIGH
**Dependencies:** Story 2.0 (PoC must pass GO criteria)
**Risk:** Medium

**As a** CIDX power user running hundreds of queries
**I want** a persistent daemon service that caches indexes in memory with integrated watch mode and cache-coherent storage operations
**So that** repeated queries complete in under 1 second, file changes are reflected instantly, and storage operations maintain cache coherence

## Technical Requirements

### Core Service Implementation

```python
# daemon_service.py
import rpyc
from rpyc.utils.server import ThreadedServer
from threading import RLock, Lock
from datetime import datetime, timedelta
from pathlib import Path
import sys
import json

class CIDXDaemonService(rpyc.Service):
    def __init__(self):
        # Single project cache (daemon is per-repository)
        self.cache_entry = None
        self.cache_lock = RLock()

        # Watch management
        self.watch_handler = None  # GitAwareWatchHandler instance
        self.watch_thread = None   # Background thread running watch

    class CacheEntry:
        def __init__(self, project_path):
            self.project_path = project_path
            # Semantic index cache
            self.hnsw_index = None
            self.id_mapping = None
            # FTS index cache
            self.tantivy_index = None
            self.tantivy_searcher = None
            self.fts_available = False
            # Shared metadata
            self.last_accessed = datetime.now()
            self.ttl_minutes = 10  # Default 10 minutes
            self.read_lock = RLock()  # For concurrent reads
            self.write_lock = Lock()  # For serialized writes
            self.access_count = 0

    def exposed_query(self, project_path, query, limit=10, **kwargs):
        """Execute semantic search with caching."""
        project_path = Path(project_path).resolve()

        # Get or create cache entry
        with self.cache_lock:
            if self.cache_entry is None:
                self.cache_entry = self.CacheEntry(project_path)

        # Concurrent read with RLock
        with self.cache_entry.read_lock:
            # Load indexes if not cached
            if self.cache_entry.hnsw_index is None:
                self._load_indexes(self.cache_entry)

            # Update access time
            self.cache_entry.last_accessed = datetime.now()
            self.cache_entry.access_count += 1

            # Perform search
            results = self._execute_search(
                self.cache_entry.hnsw_index,
                self.cache_entry.id_mapping,
                query,
                limit
            )

        return results

    def exposed_query_fts(self, project_path, query, **kwargs):
        """Execute FTS search with caching."""
        project_path = Path(project_path).resolve()

        # Get or create cache entry
        with self.cache_lock:
            if self.cache_entry is None:
                self.cache_entry = self.CacheEntry(project_path)

        # Concurrent read with RLock
        with self.cache_entry.read_lock:
            # Load Tantivy index if not cached
            if self.cache_entry.tantivy_searcher is None:
                self._load_tantivy_index(self.cache_entry)

            if not self.cache_entry.fts_available:
                return {"error": "FTS index not available for this project"}

            # Update access time (shared TTL)
            self.cache_entry.last_accessed = datetime.now()
            self.cache_entry.access_count += 1

            # Perform FTS search
            results = self._execute_fts_search(
                self.cache_entry.tantivy_searcher,
                query,
                **kwargs
            )

        return results

    def exposed_query_hybrid(self, project_path, query, **kwargs):
        """Execute parallel semantic + FTS search."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            semantic_future = executor.submit(
                self.exposed_query, project_path, query, **kwargs
            )
            fts_future = executor.submit(
                self.exposed_query_fts, project_path, query, **kwargs
            )
            semantic_results = semantic_future.result()
            fts_results = fts_future.result()

        return self._merge_hybrid_results(semantic_results, fts_results)

    def exposed_index(self, project_path, callback=None, **kwargs):
        """Perform indexing with serialized writes."""
        project_path = Path(project_path).resolve()

        # Get or create cache entry
        with self.cache_lock:
            if self.cache_entry is None:
                self.cache_entry = self.CacheEntry(project_path)

        # Serialized write with Lock
        with self.cache_entry.write_lock:
            # Perform indexing
            self._perform_indexing(project_path, callback, **kwargs)

            # Invalidate cache
            self.cache_entry.hnsw_index = None
            self.cache_entry.id_mapping = None
            self.cache_entry.tantivy_index = None
            self.cache_entry.tantivy_searcher = None
            self.cache_entry.last_accessed = datetime.now()

        return {"status": "completed", "project": str(project_path)}

    def exposed_get_status(self):
        """Return daemon and cache statistics."""
        with self.cache_lock:
            if self.cache_entry is None:
                return {"running": True, "cache_empty": True}

            return {
                "running": True,
                "project": str(self.cache_entry.project_path),
                "semantic_cached": self.cache_entry.hnsw_index is not None,
                "fts_available": self.cache_entry.fts_available,
                "fts_cached": self.cache_entry.tantivy_searcher is not None,
                "last_accessed": self.cache_entry.last_accessed.isoformat(),
                "access_count": self.cache_entry.access_count,
                "ttl_minutes": self.cache_entry.ttl_minutes
            }

    def exposed_clear_cache(self):
        """Clear cache for project."""
        with self.cache_lock:
            self.cache_entry = None
            return {"status": "cache cleared"}

    def exposed_watch_start(self, project_path, callback=None, **kwargs):
        """
        Start file watching inside daemon process.

        Why in daemon:
        - Watch updates indexes directly in memory (no disk writes)
        - Cache stays synchronized automatically
        - No cache invalidation required
        - Progress callbacks stream to client

        Args:
            project_path: Project root directory
            callback: RPyC callback for progress updates
            **kwargs: Watch configuration (reconcile, etc.)

        Returns:
            Status dict: {"status": "started", "project": str, "watching": True}
        """
        project_path = Path(project_path).resolve()

        with self.cache_lock:
            if self.watch_handler is not None:
                return {"status": "already_running", "project": str(project_path)}

            # Create watch handler
            from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler

            # Get or create indexer for watch
            if self.cache_entry is None:
                self.cache_entry = self.CacheEntry(project_path)

            self.watch_handler = GitAwareWatchHandler(
                project_path=project_path,
                indexer=self._get_or_create_indexer(project_path),
                progress_callback=callback,
                **kwargs
            )

            # Start watch in background thread
            self.watch_thread = threading.Thread(
                target=self.watch_handler.start,
                daemon=True
            )
            self.watch_thread.start()

            logger.info(f"Watch started for {project_path}")
            return {
                "status": "started",
                "project": str(project_path),
                "watching": True
            }

    def exposed_watch_stop(self, project_path):
        """
        Stop file watching inside daemon process.

        Args:
            project_path: Project root directory

        Returns:
            Status dict with final statistics
        """
        project_path = Path(project_path).resolve()

        with self.cache_lock:
            if self.watch_handler is None:
                return {"status": "not_running"}

            # Stop watch handler
            self.watch_handler.stop()

            if self.watch_thread:
                self.watch_thread.join(timeout=5)

            stats = {
                "status": "stopped",
                "project": str(project_path),
                "files_processed": getattr(self.watch_handler, 'files_processed', 0),
                "updates_applied": getattr(self.watch_handler, 'updates_applied', 0)
            }

            # Clean up
            self.watch_handler = None
            self.watch_thread = None

            logger.info(f"Watch stopped for {project_path}")
            return stats

    def exposed_watch_status(self):
        """
        Get current watch status.

        Returns:
            Status dict with watch state information
        """
        with self.cache_lock:
            if self.watch_handler is None:
                return {"watching": False}

            return {
                "watching": True,
                "project": str(self.watch_handler.project_path),
                "files_processed": getattr(self.watch_handler, 'files_processed', 0),
                "last_update": getattr(self.watch_handler, 'last_update', datetime.now()).isoformat()
            }

    def exposed_clean(self, project_path, **kwargs):
        """
        Clear vectors from collection.

        Cache Coherence: Invalidates daemon cache BEFORE clearing vectors
        to prevent cache pointing to deleted data.

        Args:
            project_path: Project root directory
            **kwargs: Arguments for clean operation

        Returns:
            Status dict with operation results

        Implementation:
            1. Acquire write lock (serialized operation)
            2. Clear cache (invalidate all cached indexes)
            3. Execute clean operation on disk storage
            4. Return status
        """
        project_path = Path(project_path).resolve()

        with self.cache_lock:
            # Invalidate cache first
            logger.info("Invalidating cache before clean operation")
            self.cache_entry = None

            # Execute clean operation
            from code_indexer.services.cleanup_service import CleanupService
            cleanup = CleanupService(project_path)
            result = cleanup.clean_vectors(**kwargs)

            return {
                "status": "success",
                "operation": "clean",
                "cache_invalidated": True,
                "result": result
            }

    def exposed_clean_data(self, project_path, **kwargs):
        """
        Clear project data without stopping containers.

        Cache Coherence: Invalidates daemon cache BEFORE clearing data
        to prevent cache pointing to deleted data.

        Args:
            project_path: Project root directory
            **kwargs: Arguments for clean-data operation

        Returns:
            Status dict with operation results

        Implementation:
            1. Acquire write lock (serialized operation)
            2. Clear cache (invalidate all cached indexes)
            3. Execute clean-data operation on disk storage
            4. Return status
        """
        project_path = Path(project_path).resolve()

        with self.cache_lock:
            # Invalidate cache first
            logger.info("Invalidating cache before clean-data operation")
            self.cache_entry = None

            # Execute clean-data operation
            from code_indexer.services.cleanup_service import CleanupService
            cleanup = CleanupService(project_path)
            result = cleanup.clean_data(**kwargs)

            return {
                "status": "success",
                "operation": "clean_data",
                "cache_invalidated": True,
                "result": result
            }

    def exposed_status(self, project_path):
        """
        Get comprehensive status including daemon and storage.

        Returns daemon cache status combined with storage status.

        Args:
            project_path: Project root directory

        Returns:
            Combined status dict:
            {
                "daemon": {
                    "running": True,
                    "cache_status": {...},
                    "watch_status": {...}
                },
                "storage": {
                    "index_size": ...,
                    "collection_count": ...,
                    ...
                }
            }

        Implementation:
            1. Get daemon status (from exposed_get_status)
            2. Get storage status (from local status command)
            3. Combine and return
        """
        project_path = Path(project_path).resolve()

        # Get daemon status
        daemon_status = self.exposed_get_status()

        # Get storage status
        from code_indexer.services.status_service import StatusService
        status_service = StatusService(project_path)
        storage_status = status_service.get_storage_status()

        return {
            "daemon": daemon_status,
            "storage": storage_status,
            "mode": "daemon"
        }

    def exposed_shutdown(self):
        """
        Gracefully shutdown daemon.

        Called by 'cidx stop' command.
        - Stops watch if running
        - Clears cache
        - Exits process after 0.5 second delay

        Returns:
            {"status": "shutting_down"}
        """
        logger.info("Graceful shutdown requested")

        # Stop watch if running
        if self.watch_handler:
            self.exposed_watch_stop(self.watch_handler.project_path)

        # Clear cache
        self.exposed_clear_cache()

        # Signal server to shutdown (delayed to allow response)
        import threading
        def delayed_shutdown():
            time.sleep(0.5)
            os._exit(0)

        threading.Thread(target=delayed_shutdown, daemon=True).start()

        return {"status": "shutting_down"}

    def _load_indexes(self, entry):
        """Load HNSW and ID mapping indexes."""
        # Implementation from filesystem_vector_store.py
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        vector_store = FilesystemVectorStore(entry.project_path)
        entry.hnsw_index = vector_store._load_hnsw_index()
        entry.id_mapping = vector_store._load_id_mapping()

    def _load_tantivy_index(self, entry):
        """Load Tantivy FTS index into cache."""
        tantivy_index_dir = entry.project_path / ".code-indexer" / "tantivy_index"

        if not tantivy_index_dir.exists():
            entry.fts_available = False
            return

        try:
            # Lazy import tantivy
            import tantivy
            entry.tantivy_index = tantivy.Index.open(str(tantivy_index_dir))
            entry.tantivy_searcher = entry.tantivy_index.searcher()
            entry.fts_available = True
        except (ImportError, Exception):
            entry.fts_available = False

def start_daemon(config_path: Path):
    """Start daemon with socket binding as lock."""
    socket_path = config_path.parent / "daemon.sock"

    try:
        # Socket binding is atomic lock mechanism
        server = ThreadedServer(
            CIDXDaemonService,
            socket_path=str(socket_path),
            protocol_config={
                'allow_public_attrs': True,
                'allow_pickle': False
            }
        )
        server.start()
    except OSError as e:
        if "Address already in use" in str(e):
            # Daemon already running - this is fine
            logger.info("Daemon already running")
            sys.exit(0)
        raise
```

### TTL-Based Cache Eviction

```python
# daemon_service.py (continued)
import threading

class CacheEvictionThread(threading.Thread):
    def __init__(self, daemon_service, check_interval=60):
        super().__init__(daemon=True)
        self.daemon_service = daemon_service
        self.check_interval = check_interval  # 60 seconds
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
        """Check cache entry and evict if expired."""
        now = datetime.now()

        with self.daemon_service.cache_lock:
            if self.daemon_service.cache_entry:
                entry = self.daemon_service.cache_entry
                ttl_delta = timedelta(minutes=entry.ttl_minutes)
                if now - entry.last_accessed > ttl_delta:
                    logger.info(f"Evicting cache (TTL expired)")
                    self.daemon_service.cache_entry = None

                    # Check if auto-shutdown enabled
                    config = self._load_config()
                    if config.get("daemon", {}).get("auto_shutdown_on_idle", True):
                        logger.info("Auto-shutdown on idle")
                        self.daemon_service.shutdown()

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
            "cache_active": self.daemon_service.cache_entry is not None
        }
```

## Acceptance Criteria

### Functional Requirements
- [ ] Daemon service starts and accepts RPyC connections on Unix socket
- [ ] Socket binding provides atomic lock (no PID files)
- [ ] Indexes cached in memory after first load (semantic + FTS)
- [ ] Cache hit returns results in <100ms
- [ ] TTL eviction works correctly (10 min default)
- [ ] Eviction check runs every 60 seconds
- [ ] Auto-shutdown on idle when configured
- [ ] Concurrent reads supported via RLock
- [ ] Writes serialized via Lock per project
- [ ] Status endpoint returns accurate statistics
- [ ] Clear cache endpoint works
- [ ] Multi-client concurrent connections supported
- [ ] `exposed_watch_start()` starts watch in background thread
- [ ] `exposed_watch_stop()` stops watch gracefully with statistics
- [ ] `exposed_watch_status()` reports current watch state
- [ ] `exposed_shutdown()` performs graceful daemon shutdown
- [ ] Watch updates indexes directly in memory cache
- [ ] Only one watch can run at a time per daemon
- [ ] Watch handler cleanup on stop
- [ ] Daemon shutdown stops watch automatically
- [ ] `exposed_clean()` invalidates cache before clearing vectors
- [ ] `exposed_clean_data()` invalidates cache before clearing data
- [ ] `exposed_status()` returns combined daemon + storage status
- [ ] Storage operations properly synchronized with write lock
- [ ] Cache coherence maintained after storage operations

### Performance Requirements
- [ ] Cache hit query time: <100ms (excluding embedding)
- [ ] FTS cache hit: <20ms (no embedding needed)
- [ ] Memory usage stable over 1000 queries
- [ ] Support 10+ concurrent read queries
- [ ] Index load happens once per TTL period

### Reliability Requirements
- [ ] Daemon handles client disconnections gracefully
- [ ] Cache survives query errors
- [ ] Memory cleaned up on eviction
- [ ] Proper error propagation to client
- [ ] Socket binding prevents duplicate daemons

### Critical E2E Test Requirements
- [ ] **MANDATORY**: `test_concurrent_watch_query_index_operations()` passes without race conditions
  - Thread 1: Watch mode making file changes
  - Thread 2: Concurrent queries (10+ queries) during file changes
  - Thread 3: Index operation while watch and queries active
  - All operations complete successfully without errors
  - No cache corruption, NoneType errors, or deadlocks
  - Cache coherence maintained throughout
  - This test validates the most complex real-world concurrent scenario

## Implementation Tasks

### Task 1: Core Service Structure (Day 1)
- [ ] Create daemon_service.py with RPyC service class
- [ ] Implement CacheEntry data structure
- [ ] Add basic query and index methods
- [ ] Setup logging infrastructure
- [ ] Implement socket binding mechanism

### Task 2: Caching Logic (Day 1)
- [ ] Implement index loading and caching
- [ ] Add cache lookup logic
- [ ] Implement TTL tracking (10 minutes)
- [ ] Add access time updates
- [ ] Support both semantic and FTS indexes

### Task 3: Concurrency Control (Day 2)
- [ ] Add RLock for concurrent reads
- [ ] Add Lock for serialized writes
- [ ] Test concurrent access patterns
- [ ] Verify no deadlocks
- [ ] Test multi-client scenarios

### Task 4: TTL Eviction (Day 2)
- [ ] Create background eviction thread
- [ ] Implement 60-second check interval
- [ ] Add safe eviction with locks
- [ ] Implement auto-shutdown logic
- [ ] Test eviction scenarios

### Task 5: Health & Monitoring (Day 3)
- [ ] Implement status endpoint
- [ ] Add health monitoring
- [ ] Create metrics collection
- [ ] Add diagnostic endpoints

### Task 6: Integration (Day 3)
- [ ] Integrate with filesystem_vector_store.py
- [ ] Wire up actual index loading
- [ ] Add FTS support with Tantivy
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
    assert service.cache_entry.access_count == 1

    # Second query - cache hit
    result2 = service.exposed_query("/project1", "test")
    assert service.cache_entry.access_count == 2

def test_concurrent_reads():
    """Test multiple concurrent read queries."""
    service = CIDXDaemonService()

    def read_query(i):
        return service.exposed_query("/project", f"query {i}")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_query, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    assert service.cache_entry.access_count == 10

def test_ttl_eviction():
    """Test TTL-based cache eviction."""
    service = CIDXDaemonService()

    # Add cache entry
    service.exposed_query("/project", "test")

    # Simulate TTL expiration (10 minutes)
    entry = service.cache_entry
    entry.last_accessed = datetime.now() - timedelta(minutes=11)

    # Run eviction
    eviction_thread = CacheEvictionThread(service)
    eviction_thread._check_and_evict()

    assert service.cache_entry is None

def test_socket_binding_lock():
    """Test socket binding prevents duplicate daemons."""
    socket_path = Path("/tmp/test-daemon.sock")

    # Start first daemon
    server1 = ThreadedServer(CIDXDaemonService, socket_path=str(socket_path))

    # Try to start second daemon - should fail
    with pytest.raises(OSError) as exc_info:
        server2 = ThreadedServer(CIDXDaemonService, socket_path=str(socket_path))

    assert "Address already in use" in str(exc_info.value)

def test_watch_start_stop():
    """Test watch lifecycle in daemon."""
    service = CIDXDaemonService()

    # Start watch
    result = service.exposed_watch_start("/project", callback=None)
    assert result["status"] == "started"

    # Verify running
    status = service.exposed_watch_status()
    assert status["watching"] is True

    # Stop watch
    stats = service.exposed_watch_stop("/project")
    assert stats["status"] == "stopped"

    # Verify stopped
    status = service.exposed_watch_status()
    assert status["watching"] is False

def test_only_one_watch_allowed():
    """Test that only one watch can run at a time."""
    service = CIDXDaemonService()

    # Start first watch
    result1 = service.exposed_watch_start("/project1")
    assert result1["status"] == "started"

    # Try to start second watch - should fail
    result2 = service.exposed_watch_start("/project2")
    assert result2["status"] == "already_running"

def test_shutdown_stops_watch():
    """Test graceful shutdown stops active watch."""
    service = CIDXDaemonService()

    # Start watch
    service.exposed_watch_start("/project")
    assert service.watch_handler is not None

    # Shutdown
    with patch("os._exit"):
        result = service.exposed_shutdown()
        assert result["status"] == "shutting_down"

    # Watch should be stopped
    assert service.watch_handler is None

def test_clean_invalidates_cache():
    """Test clean operation invalidates cache."""
    service = CIDXDaemonService()

    # Load cache
    service.exposed_query("/project", "test")
    assert service.cache_entry is not None

    # Clean operation
    with patch("code_indexer.services.cleanup_service.CleanupService"):
        result = service.exposed_clean("/project")

    # Cache should be invalidated
    assert service.cache_entry is None
    assert result["cache_invalidated"] is True

def test_clean_data_invalidates_cache():
    """Test clean-data operation invalidates cache."""
    service = CIDXDaemonService()

    # Load cache
    service.exposed_query("/project", "test")
    assert service.cache_entry is not None

    # Clean-data operation
    with patch("code_indexer.services.cleanup_service.CleanupService"):
        result = service.exposed_clean_data("/project")

    # Cache should be invalidated
    assert service.cache_entry is None
    assert result["cache_invalidated"] is True

def test_status_includes_daemon_info():
    """Test status includes daemon cache information."""
    service = CIDXDaemonService()

    with patch("code_indexer.services.status_service.StatusService"):
        status = service.exposed_status("/project")

    assert "daemon" in status
    assert "storage" in status
    assert status["mode"] == "daemon"
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

def test_fts_caching():
    """Test FTS index caching."""
    daemon = start_test_daemon()

    # First FTS query - loads Tantivy index
    start = time.perf_counter()
    result1 = query_fts_daemon("/project", "function")
    load_time = time.perf_counter() - start

    # Second FTS query - uses cached searcher
    start = time.perf_counter()
    result2 = query_fts_daemon("/project", "function")
    cache_time = time.perf_counter() - start

    assert cache_time < load_time * 0.05  # 95% faster

def test_hybrid_parallel_execution():
    """Test hybrid search runs in parallel."""
    daemon = start_test_daemon()

    start = time.perf_counter()
    result = query_hybrid_daemon("/project", "test")
    duration = time.perf_counter() - start

    # Should be close to max(semantic, fts), not sum
    assert duration < 1.5  # Not 2.5s
    assert result["semantic_count"] > 0
    assert result["fts_count"] > 0

def test_concurrent_watch_query_index_operations():
    """
    CRITICAL E2E TEST: Verify daemon handles concurrent operations without race conditions.

    This test reproduces the most complex real-world scenario:
    - Thread 1: Watch mode making file changes
    - Thread 2: Concurrent queries during file changes
    - Thread 3: Index operation requested while watch and queries active

    All three operations must work correctly without:
    - Cache corruption
    - NoneType errors
    - Deadlocks
    - Duplicate watch handlers
    - Lost file change events

    Test Scenario:
    1. Start daemon with empty cache
    2. Thread 1: Start watch mode
    3. Thread 1: Make file changes (create/modify/delete files)
    4. Thread 2: Run concurrent queries (10 queries during file changes)
    5. Thread 3: Request full re-index while watch and queries running
    6. Verify all operations complete successfully
    7. Verify cache coherence maintained
    8. Verify no race conditions occurred
    """
    service, project_path = daemon_service_with_project

    # Storage for results and errors
    watch_errors = []
    query_results = []
    query_errors = []
    index_result = None
    index_error = None
    results_lock = threading.Lock()

    # Thread 1: Watch mode with file changes
    def watch_and_modify_files():
        try:
            # Start watch
            watch_response = service.exposed_watch_start(
                project_path=str(project_path),
                callback=None,
                debounce_seconds=1.0,
            )
            assert watch_response["status"] == "success", "Watch should start"

            # Make file changes
            test_file = project_path / "test_file.py"
            for i in range(5):
                test_file.write_text(f"# Modified content {i}\n")
                time.sleep(0.2)  # Trigger watch events

        except Exception as e:
            with results_lock:
                watch_errors.append(e)

    # Thread 2: Concurrent queries
    def run_concurrent_queries():
        for i in range(10):
            try:
                result = service.exposed_query(
                    project_path=str(project_path),
                    query=f"test query {i}",
                    limit=5,
                )
                with results_lock:
                    query_results.append(result)
                time.sleep(0.1)
            except Exception as e:
                with results_lock:
                    query_errors.append(e)

    # Thread 3: Index operation
    def request_indexing():
        nonlocal index_result, index_error
        try:
            time.sleep(0.3)  # Let watch and queries start first
            result = service.exposed_index(
                project_path=str(project_path),
                callback=None,
            )
            index_result = result
        except Exception as e:
            index_error = e

    # Run all three operations concurrently
    thread1 = threading.Thread(target=watch_and_modify_files, daemon=True)
    thread2 = threading.Thread(target=run_concurrent_queries, daemon=True)
    thread3 = threading.Thread(target=request_indexing, daemon=True)

    thread1.start()
    thread2.start()
    thread3.start()

    # Wait for completion
    thread1.join(timeout=15)
    thread2.join(timeout=15)
    thread3.join(timeout=15)

    # CRITICAL ASSERTIONS: No race conditions should occur
    if watch_errors:
        pytest.fail(f"Watch errors detected: {watch_errors}")

    if query_errors:
        pytest.fail(f"Query errors detected ({len(query_errors)}/10 failed): {query_errors}")

    if index_error:
        pytest.fail(f"Index operation failed: {index_error}")

    # All operations should succeed
    assert len(query_results) == 10, f"Expected 10 successful queries, got {len(query_results)}"
    assert index_result is not None, "Index operation should complete"
    assert index_result["status"] in ["completed", "started"], "Index should complete or be running"

    # Verify cache coherence
    assert service.cache_entry is not None or index_result["status"] == "completed", \
        "Cache should exist or be invalidated by index operation"

    # Verify watch is still running (only stopped explicitly)
    watch_status = service.exposed_watch_status()
    assert watch_status["running"], "Watch should still be running after concurrent operations"

    # Cleanup
    service.exposed_watch_stop(str(project_path))
    if service.indexing_thread:
        service.indexing_thread.join(timeout=30)
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
- [ ] Let cache sit for >10 minutes, verify eviction
- [ ] Check daemon status endpoint
- [ ] Clear cache and verify re-load
- [ ] Kill daemon and verify cannot start duplicate
- [ ] Test auto-shutdown on idle

## Configuration Schema

```json
{
  "daemon": {
    "enabled": true,
    "ttl_minutes": 10,
    "auto_shutdown_on_idle": true,
    "eviction_check_interval_seconds": 60,
    "max_retries": 4,
    "retry_delays_ms": [100, 500, 1000, 2000]
  }
}
```

## Error Handling Scenarios

### Scenario 1: Index File Not Found
- Log error with project path
- Return empty cache entry
- Let query fail with proper error

### Scenario 2: Memory Pressure
- Rely on TTL eviction (10 minutes)
- Auto-shutdown on idle if configured
- No hard memory limits

### Scenario 3: Concurrent Write During Read
- RLock prevents write during reads
- Reads wait for write completion
- Cache invalidated after write

### Scenario 4: Client Disconnect During Query
- RPyC handles cleanup
- Cache remains valid
- No partial state corruption

### Scenario 5: Socket Already In Use
- Socket binding detects running daemon
- Exit cleanly (not an error)
- Client connects to existing daemon

## Definition of Done

- [ ] Daemon service implemented with all endpoints
- [ ] In-memory caching working with 10-min TTL eviction
- [ ] Socket binding prevents duplicate daemons
- [ ] FTS index caching implemented
- [ ] Concurrent read/write locks properly implemented
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] **CRITICAL**: `test_concurrent_watch_query_index_operations()` E2E test passing
  - Validates concurrent watch + queries + indexing without race conditions
  - This test MUST pass before story completion
- [ ] Performance targets met (<100ms cache hit)
- [ ] Health monitoring operational
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "One daemon per repository"
- "Socket binding as atomic lock (no PID files)"
- "Unix socket at .code-indexer/daemon.sock"
- "10-minute TTL default"
- "60-second eviction check interval"
- "Auto-shutdown on idle when configured"
- "Multi-client concurrent support"
- "FTS caching alongside semantic"