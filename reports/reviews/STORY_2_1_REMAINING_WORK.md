# Story 2.1 - Remaining Implementation Work

## CONTEXT

Story 2.1 implements RPyC Daemon Service with In-Memory Index Caching. The cache infrastructure (CacheEntry, TTLEvictionThread) is **COMPLETE with 40/40 tests passing**.

## COMPLETED (✅)

- `/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/cache.py` - CacheEntry + TTLEvictionThread (207 lines)
- `/home/jsbattig/Dev/code-indexer/tests/unit/daemon/test_cache_entry.py` - 24 passing tests
- `/home/jsbattig/Dev/code-indexer/tests/unit/daemon/test_ttl_eviction.py` - 16 passing tests

## REMAINING WORK

### 1. CIDXDaemonService (service.py)

**File**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/service.py`

**Requirements**:
- Inherit from `rpyc.Service`
- Initialize with cache_entry=None, cache_lock=Lock(), eviction_thread
- Implement all 14 exposed methods (see story spec)

**Critical Methods**:

```python
class CIDXDaemonService(rpyc.Service):
    def __init__(self):
        super().__init__()
        self.cache_entry: Optional[CacheEntry] = None
        self.cache_lock: threading.Lock = threading.Lock()
        self.config = Mock(auto_shutdown_on_idle=False)  # TODO: Load real config
        self.watch_handler: Optional[Any] = None
        self.watch_thread: Optional[threading.Thread] = None

        # Start TTL eviction thread
        self.eviction_thread = TTLEvictionThread(self, check_interval=60)
        self.eviction_thread.start()

    def exposed_query(self, project_path, query, limit=10, **kwargs):
        """Semantic search with caching."""
        # 1. Ensure cache loaded (call _ensure_cache_loaded)
        # 2. Update access with cache_entry.update_access()
        # 3. Execute search using cached HNSW index
        # 4. Return results

    def exposed_query_fts(self, project_path, query, **kwargs):
        """FTS search with caching."""
        # 1. Ensure cache loaded
        # 2. Update access
        # 3. Execute FTS search using cached Tantivy index
        # 4. Return results

    def exposed_query_hybrid(self, project_path, query, **kwargs):
        """Parallel semantic + FTS search."""
        # 1. Execute both exposed_query and exposed_query_fts in parallel
        # 2. Merge results
        # 3. Return combined results

    def exposed_index(self, project_path, callback=None, **kwargs):
        """Index with cache invalidation."""
        # 1. Invalidate cache BEFORE indexing
        # 2. Call FileChunkingManager.index_repository()
        # 3. Return status

    def exposed_watch_start(self, project_path, callback=None, **kwargs):
        """Start watch in daemon."""
        # 1. Check if watch already running
        # 2. Create GitAwareWatchHandler
        # 3. Start in background thread
        # 4. Return status

    def exposed_watch_stop(self, project_path):
        """Stop watch gracefully."""
        # 1. Stop watch handler
        # 2. Join watch thread
        # 3. Clear watch_handler/watch_thread
        # 4. Return statistics

    def exposed_clean(self, project_path, **kwargs):
        """Clear vectors with cache invalidation."""
        # 1. Invalidate cache FIRST
        # 2. Call FilesystemVectorStore.clear_vectors()
        # 3. Return status

    def exposed_status(self, project_path):
        """Combined daemon + storage status."""
        # 1. Get daemon cache stats
        # 2. Get storage stats from FilesystemVectorStore
        # 3. Combine and return

    def _ensure_cache_loaded(self, project_path):
        """Load indexes into cache if not already loaded."""
        with self.cache_lock:
            if self.cache_entry is None or self.cache_entry.project_path != project_path:
                # Create new cache entry
                self.cache_entry = CacheEntry(Path(project_path))

                # Load semantic indexes (REAL loading, not mocked)
                self._load_semantic_indexes(self.cache_entry)

                # Load FTS indexes (REAL loading, not mocked)
                self._load_fts_indexes(self.cache_entry)

    def _load_semantic_indexes(self, entry: CacheEntry):
        """Load REAL HNSW index from FilesystemVectorStore."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        vector_store = FilesystemVectorStore(
            index_dir=entry.project_path / ".code-indexer" / "index",
            collection_name="default"
        )

        # Load HNSW index (REAL, not mocked)
        entry.hnsw_index = vector_store._load_hnsw_index()

        # Load ID mapping (REAL, not mocked)
        entry.id_mapping = vector_store._load_id_mapping()

    def _load_fts_indexes(self, entry: CacheEntry):
        """Load REAL Tantivy index."""
        tantivy_dir = entry.project_path / ".code-indexer" / "tantivy_index"
        if not tantivy_dir.exists():
            entry.fts_available = False
            return

        try:
            import tantivy
            entry.tantivy_index = tantivy.Index.open(str(tantivy_dir))
            entry.tantivy_searcher = entry.tantivy_index.searcher()
            entry.fts_available = True
        except ImportError:
            entry.fts_available = False
```

**Tests**: `/home/jsbattig/Dev/code-indexer/tests/unit/daemon/test_daemon_service.py`
- Test each exposed method
- Test cache loading (with real FilesystemVectorStore)
- Test cache invalidation on storage operations
- Test concurrent access

### 2. Daemon Server (server.py)

**File**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/server.py`

**Requirements**:
- Socket binding as atomic lock (from PoC)
- Clean stale socket before binding
- ThreadedServer with Unix socket
- Signal handling for graceful shutdown

```python
def start_daemon(config_path: Path):
    """Start daemon with socket binding as atomic lock."""
    socket_path = config_path.parent / "daemon.sock"

    # Clean stale socket if exists
    if socket_path.exists():
        # Try to connect - if fails, it's stale
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path))
            sock.close()
            logger.error(f"Daemon already running on {socket_path}")
            sys.exit(1)
        except (ConnectionRefusedError, FileNotFoundError):
            socket_path.unlink()
            sock.close()

    # Create server
    try:
        server = ThreadedServer(
            CIDXDaemonService,
            socket_path=str(socket_path),
            protocol_config={
                "allow_public_attrs": True,
                "allow_pickle": True,
            },
        )

        logger.info(f"CIDX daemon started on {socket_path}")
        server.start()  # Blocks

    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"Daemon already running on {socket_path}")
            sys.exit(1)
        raise
    finally:
        if socket_path.exists():
            socket_path.unlink()
```

**Tests**: `/home/jsbattig/Dev/code-indexer/tests/integration/daemon/test_daemon_lifecycle.py`
- Test daemon starts successfully
- Test socket binding prevents second daemon
- Test daemon cleanup on exit
- Test client connection/disconnection

### 3. Entry Point (__main__.py)

**File**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/__main__.py`

```python
"""Entry point for daemon service.

Usage: python -m code_indexer.daemon [config_path]
"""

import sys
from pathlib import Path
from .server import start_daemon

if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / ".code-indexer" / "config.json"
    start_daemon(config_path)
```

### 4. Watch Mode Integration (watch_integration.py)

**File**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/watch_integration.py`

**Requirements**:
- Create GitAwareWatchHandler inside daemon
- Direct cache updates (not via RPC)
- Thread safety with cache_lock

```python
class WatchCacheUpdater:
    """Updates daemon cache directly from watch events."""

    def __init__(self, daemon_service, cache_entry):
        self.daemon_service = daemon_service
        self.cache_entry = cache_entry

    def on_file_updated(self, file_path, vector_id):
        """Update cache when file changes."""
        with self.daemon_service.cache_lock:
            # Update HNSW index in-place
            # Update ID mapping
            pass
```

**Tests**: `/home/jsbattig/Dev/code-indexer/tests/unit/daemon/test_watch_integration.py`
- Test watch starts in daemon
- Test watch updates cache directly
- Test only one watch per daemon
- Test watch cleanup on stop

### 5. Integration Tests

**Files**:
- `/home/jsbattig/Dev/code-indexer/tests/integration/daemon/test_query_caching.py` - Query caching with real indexes
- `/home/jsbattig/Dev/code-indexer/tests/integration/daemon/test_storage_coherence.py` - Storage operations maintain cache coherence

**Requirements**:
- Use REAL FilesystemVectorStore (not mocked)
- Create actual .code-indexer/index directory
- Test with real HNSW indexes
- Test with real Tantivy indexes
- Verify cache hit performance (<100ms)
- Verify cache invalidation works

## SUCCESS CRITERIA

- All 24 acceptance criteria satisfied
- All tests pass (unit + integration)
- >90% test coverage for daemon module
- Real index loading works (not simulated)
- Cache coherence maintained across storage operations
- Watch mode runs inside daemon
- Concurrent queries work without race conditions

## ARCHITECTURAL NOTES

1. **NO external subprocess calls** - All operations use internal APIs
2. **Real index loading** - Must load actual HNSW and Tantivy indexes
3. **Cache coherence** - Storage operations MUST invalidate cache before modifying data
4. **Thread safety** - RLock for reads, Lock for writes per CacheEntry
5. **Socket as lock** - No PID files, socket binding provides atomic exclusion
6. **Auto-shutdown** - Configurable auto-shutdown on idle after cache eviction

## REFERENCE IMPLEMENTATION

See `/home/jsbattig/Dev/code-indexer/poc/daemon_service.py` for validated PoC architecture (socket binding, RPyC setup, basic caching).

## IMPLEMENTATION APPROACH

Use strict TDD:
1. Write failing test for each exposed method
2. Implement minimal code to pass test
3. Refactor for quality
4. Run fast-automation.sh frequently
5. Verify coverage >90%
