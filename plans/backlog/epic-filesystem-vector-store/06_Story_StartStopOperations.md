# Story 6: Seamless Start and Stop Operations

**Story ID:** S06
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 2-3 days
**Implementation Order:** 7

## User Story

**As a** developer using filesystem backend
**I want to** start and stop operations to work consistently
**So that** commands behave predictably regardless of backend type

**Conversation Reference:** "I don't want to run ANY containers, zero" - Start/stop operations must be no-ops for filesystem backend, maintaining consistent CLI interface.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx start` succeeds immediately for filesystem backend (no-op)
2. ✅ `cidx stop` succeeds immediately for filesystem backend (no-op)
3. ✅ Start/stop maintain same CLI interface for both backends
4. ✅ No container checks or health monitoring for filesystem
5. ✅ Backend abstraction layer handles differences transparently
6. ✅ Clear user feedback showing filesystem requires no services

### Technical Requirements
1. ✅ FilesystemBackend.start() returns success immediately
2. ✅ FilesystemBackend.stop() returns success immediately
3. ✅ Backend status reflects "always running" state
4. ✅ No port allocation or network checks
5. ✅ Consistent return values with Qdrant backend
6. ✅ Commands continue to work with Qdrant backend unchanged

### User Experience
1. Clear messaging that filesystem backend has no services
2. No confusing "starting..." messages for filesystem
3. Instant command completion
4. Helpful context about backend differences

## Manual Testing Steps

```bash
# Test 1: Start filesystem backend
cd /path/to/indexed-repo
cidx init --vector-store filesystem
cidx start

# Expected output:
# ✅ Filesystem backend ready (no services to start)
# 📁 Vectors stored in .code-indexer/vectors/
# 💡 Filesystem backend requires no containers

# Verify instant completion (no delay)
time cidx start
# Expected: real 0m0.050s (instant)

# Test 2: Stop filesystem backend
cidx stop

# Expected output:
# ✅ Filesystem backend stopped (no services to stop)
# 💡 Vector data remains in .code-indexer/vectors/

# Test 3: Start/stop with Qdrant (backward compatibility)
cd /path/to/qdrant-repo
cidx init --vector-store qdrant
cidx start

# Expected: Traditional container startup
# ⏳ Starting Qdrant container...
# ⏳ Starting data-cleaner container...
# ✅ Containers started successfully

cidx stop
# Expected: Container shutdown
# ⏳ Stopping containers...
# ✅ Containers stopped

# Test 4: Status after start (filesystem)
cd /path/to/filesystem-repo
cidx start
cidx status

# Expected output:
# 📁 Filesystem Backend
#   Status: Ready ✅
#   Path: .code-indexer/vectors/
#   No services running (none required)

# Test 5: Query without explicit start (auto-start)
cd /path/to/filesystem-repo
# Don't run cidx start
cidx query "test query"

# Expected: Query works immediately (no auto-start delay)
# 🔍 Searching for: "test query"
# 📊 Found 5 results...

# Test 6: Index without explicit start
cd /path/to/filesystem-repo
cidx index

# Expected: Indexing works immediately
# ℹ️ Using filesystem vector store
# ⏳ Indexing files: [===>  ] 25/100 (25%)...

# Test 7: Multiple start calls (idempotent)
cidx start
cidx start
cidx start

# Expected: Each call succeeds immediately
# ✅ Filesystem backend ready (no services to start)
# ✅ Filesystem backend ready (no services to start)
# ✅ Filesystem backend ready (no services to start)
```

## Technical Implementation Details

### FilesystemBackend Start/Stop Implementation

```python
class FilesystemBackend(VectorStoreBackend):
    """Filesystem-based vector storage backend."""

    def __init__(self, config: Config):
        self.config = config
        self.base_path = Path(config.codebase_dir) / ".code-indexer" / "vectors"

    def initialize(self, config: Dict) -> bool:
        """Create directory structure (from Story 1)."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        return True

    def start(self) -> bool:
        """No-op for filesystem backend.

        Filesystem backend has no services to start.
        Always returns True (success).
        """
        # Verify base path exists (from initialization)
        if not self.base_path.exists():
            # Attempt to create if missing
            try:
                self.base_path.mkdir(parents=True, exist_ok=True)
            except Exception:
                return False

        return True  # Always "started" and ready

    def stop(self) -> bool:
        """No-op for filesystem backend.

        Filesystem backend has no services to stop.
        Always returns True (success).
        """
        return True  # Always "stopped" successfully

    def get_status(self) -> Dict[str, Any]:
        """Get filesystem backend status."""
        return {
            "type": "filesystem",
            "status": "ready",  # Always ready
            "path": str(self.base_path),
            "exists": self.base_path.exists(),
            "writable": os.access(self.base_path, os.W_OK) if self.base_path.exists() else False,
            "requires_services": False,  # Key difference from Qdrant
            "collections": self._list_collections(),
            "total_vectors": self._count_all_vectors()
        }

    def health_check(self) -> bool:
        """Check filesystem accessibility.

        For filesystem backend, "healthy" means:
        - Base path exists
        - Base path is writable
        """
        return self.base_path.exists() and os.access(self.base_path, os.W_OK)

    def get_service_info(self) -> Dict[str, Any]:
        """Get filesystem service information."""
        return {
            "type": "filesystem",
            "path": str(self.base_path),
            "no_containers": True,
            "no_ports": True,
            "status": "always_ready"
        }

    def cleanup(self, remove_data: bool = False) -> bool:
        """Clean up filesystem storage."""
        if remove_data and self.base_path.exists():
            shutil.rmtree(self.base_path)
        return True
```

### QdrantContainerBackend (Unchanged - Backward Compatibility)

```python
class QdrantContainerBackend(VectorStoreBackend):
    """Container-based Qdrant backend (existing behavior)."""

    def __init__(self, docker_manager: DockerManager, config: Config):
        self.docker_manager = docker_manager
        self.config = config

    def start(self) -> bool:
        """Start Qdrant and data-cleaner containers."""
        return self.docker_manager.start_containers()

    def stop(self) -> bool:
        """Stop containers."""
        return self.docker_manager.stop_containers()

    def get_status(self) -> Dict[str, Any]:
        """Get container status."""
        return {
            "type": "container",
            "status": "running" if self._are_containers_running() else "stopped",
            "requires_services": True,
            "qdrant_running": self.docker_manager.is_qdrant_running(),
            "data_cleaner_running": self.docker_manager.is_data_cleaner_running(),
            "ports": {
                "qdrant": self.config.qdrant.port,
                "data_cleaner": self.config.data_cleaner_port
            }
        }

## Unit Test Coverage Requirements

**Test Strategy:** Test both backends with real operations (NO mocking for filesystem, container mocking acceptable for Qdrant)

**Test File:** `tests/unit/backends/test_backend_start_stop.py`

**Required Tests:**

```python
class TestBackendStartStopOperations:
    """Test start/stop operations for both backends."""

    def test_filesystem_start_returns_immediately(self, tmp_path):
        """GIVEN filesystem backend
        WHEN start() is called
        THEN returns True in <10ms"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        start_time = time.perf_counter()
        result = backend.start()
        duration = time.perf_counter() - start_time

        assert result is True
        assert duration < 0.01  # <10ms (essentially instant)

    def test_filesystem_stop_returns_immediately(self, tmp_path):
        """GIVEN filesystem backend
        WHEN stop() is called
        THEN returns True in <10ms"""
        backend = FilesystemBackend(config)

        start_time = time.perf_counter()
        result = backend.stop()
        duration = time.perf_counter() - start_time

        assert result is True
        assert duration < 0.01  # <10ms

    def test_filesystem_query_works_after_stop(self, tmp_path):
        """GIVEN filesystem backend
        WHEN stop() is called and then query is executed
        THEN query still works (nothing actually stopped)"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        store = backend.get_vector_store_client()
        store.create_collection('test_coll', 1536)

        # Index some data
        points = [
            {'id': 'vec_1', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': 'file.py'}}
        ]
        store.upsert_points('test_coll', points)

        # Stop backend
        backend.stop()

        # Query should still work
        results = store.search('test_coll', np.random.randn(1536), limit=1)
        assert len(results) == 1

    def test_get_status_shows_always_ready(self, tmp_path):
        """GIVEN filesystem backend
        WHEN get_status() is called (before or after start/stop)
        THEN status always shows 'ready'"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        # Before start
        status_before = backend.get_status()
        assert status_before['type'] == 'filesystem'
        assert status_before['requires_services'] is False

        # After start
        backend.start()
        status_after_start = backend.get_status()
        assert status_after_start == status_before  # No change

        # After stop
        backend.stop()
        status_after_stop = backend.get_status()
        assert status_after_stop == status_before  # Still no change

    def test_qdrant_backend_start_stop_delegate_to_docker(self):
        """GIVEN Qdrant backend
        WHEN start/stop called
        THEN delegates to DockerManager"""
        # Mock DockerManager for this test
        mock_docker = Mock()
        mock_docker.start_containers.return_value = True
        mock_docker.stop_containers.return_value = True

        backend = QdrantContainerBackend(mock_docker, config)

        # Start
        result_start = backend.start()
        assert result_start is True
        mock_docker.start_containers.assert_called_once()

        # Stop
        result_stop = backend.stop()
        assert result_stop is True
        mock_docker.stop_containers.assert_called_once()
```

**Coverage Requirements:**
- ✅ Filesystem start/stop timing (<10ms)
- ✅ No-op verification (status unchanged)
- ✅ Query functionality after stop
- ✅ Qdrant backend delegation to DockerManager
- ✅ Status reporting accuracy

**Test Data:**
- Real filesystem operations for FilesystemBackend
- Mock DockerManager for QdrantContainerBackend
- Small dataset for query verification

**Performance Assertions:**
- start(): <10ms for filesystem
- stop(): <10ms for filesystem
- get_status(): <50ms for both backends
```

### CLI Start Command

```python
@click.command()
def start_command():
    """Start backend services (no-op for filesystem)."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    backend_type = backend.get_status()["type"]

    if backend_type == "filesystem":
        # Filesystem backend - instant success
        result = backend.start()

        if result:
            console.print("✅ Filesystem backend ready (no services to start)", style="green")
            console.print(f"📁 Vectors stored in {backend.get_status()['path']}")
            console.print("💡 Filesystem backend requires no containers", style="dim")
        else:
            console.print("❌ Failed to verify filesystem backend", style="red")
            console.print("💡 Check that .code-indexer/vectors/ is accessible")
            raise Exit(1)

    else:
        # Qdrant backend - existing behavior
        console.print("⏳ Starting containers...")

        with console.status("Starting Qdrant and data-cleaner..."):
            result = backend.start()

        if result:
            console.print("✅ Containers started successfully", style="green")

            # Show status
            status = backend.get_status()
            console.print(f"   Qdrant: {'Running ✅' if status['qdrant_running'] else 'Stopped ❌'}")
            console.print(f"   Port: {status['ports']['qdrant']}")
        else:
            console.print("❌ Failed to start containers", style="red")
            raise Exit(1)
```

### CLI Stop Command

```python
@click.command()
def stop_command():
    """Stop backend services (no-op for filesystem)."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    backend_type = backend.get_status()["type"]

    if backend_type == "filesystem":
        # Filesystem backend - instant success
        result = backend.stop()

        if result:
            console.print("✅ Filesystem backend stopped (no services to stop)", style="green")
            console.print("💡 Vector data remains in .code-indexer/vectors/", style="dim")
        else:
            # Unlikely to fail, but handle gracefully
            console.print("⚠️  Filesystem backend stop returned error (non-critical)", style="yellow")

    else:
        # Qdrant backend - existing behavior
        console.print("⏳ Stopping containers...")

        with console.status("Stopping Qdrant and data-cleaner..."):
            result = backend.stop()

        if result:
            console.print("✅ Containers stopped", style="green")
        else:
            console.print("❌ Failed to stop containers", style="red")
            raise Exit(1)
```

### Auto-Start Logic (Transparent)

```python
def ensure_backend_started(backend: VectorStoreBackend) -> bool:
    """Ensure backend is ready for operations.

    For Qdrant: Check if containers running, start if needed
    For Filesystem: Always ready (no-op check)
    """
    if not backend.health_check():
        # Backend not healthy, attempt to start
        return backend.start()

    return True  # Already healthy


# Used in index and query commands
def index_command():
    """Index command with auto-start."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    # Ensure backend ready (instant for filesystem, may start containers for Qdrant)
    if not ensure_backend_started(backend):
        console.print("❌ Backend not ready", style="red")
        raise Exit(1)

    # Proceed with indexing
    vector_store = backend.get_vector_store_client()
    # ... indexing logic


def query_command(query_text: str):
    """Query command with auto-start."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    # Ensure backend ready
    if not ensure_backend_started(backend):
        console.print("❌ Backend not ready", style="red")
        raise Exit(1)

    # Proceed with query
    vector_store = backend.get_vector_store_client()
    # ... query logic
```

## Dependencies

### Internal Dependencies
- Story 1: Backend abstraction layer (VectorStoreBackend interface)
- Existing DockerManager for Qdrant backend

### External Dependencies
- None (filesystem operations only)

## Success Metrics

1. ✅ Start/stop commands complete instantly for filesystem backend (<50ms)
2. ✅ No container-related errors for filesystem backend
3. ✅ Qdrant backend start/stop behavior unchanged
4. ✅ User messaging clearly indicates backend differences
5. ✅ Auto-start logic works transparently for both backends

## Non-Goals

- Service lifecycle management for filesystem (none needed)
- Health monitoring dashboards
- Graceful degradation (filesystem always works or fails cleanly)
- Background service management

## Follow-Up Stories

- **Story 8**: Switch Between Qdrant and Filesystem Backends (uses start/stop during switching)

## Implementation Notes

### Critical Design Philosophy

**Filesystem backend has no services** - this is fundamental to the architecture. Start/stop are no-ops that:
1. Always succeed immediately
2. Provide clear user messaging
3. Maintain CLI interface consistency
4. Enable transparent backend switching

### Idempotency

Both start and stop must be **idempotent**:
- Calling `start` multiple times is safe (no side effects)
- Calling `stop` multiple times is safe (no errors)
- Calling `start` → `stop` → `start` works correctly

### Auto-Start Transparency

**Key insight:** With filesystem backend, auto-start logic becomes instant verification rather than container startup. This provides seamless user experience where:
- `cidx query` "just works" without explicit start
- No confusing startup messages
- No startup delays

### User Messaging Strategy

Messaging should be **informative not alarming**:
- ✅ "Filesystem backend ready (no services to start)" - clear, positive
- ❌ "Warning: No services to start" - sounds like error
- ✅ "No containers needed ✅" - highlight benefit
- ❌ "Containers disabled" - sounds like missing feature

### Performance Comparison

| Backend | Start Time | Stop Time | Health Check Time |
|---------|------------|-----------|-------------------|
| Filesystem | <50ms | <10ms | <10ms (path check) |
| Qdrant | 2-5s | 1-2s | 100-500ms (HTTP call) |

Filesystem backend provides **40-100x faster** start/stop operations.

### Error Handling Edge Cases

**Filesystem backend failure scenarios:**
- Directory not writable: Return False from health_check(), suggest permissions fix
- Directory missing: Attempt to create in start(), fail gracefully if impossible
- Corrupted data: Detected in health validation (Story 4), not in start/stop

**Never throw exceptions** from start/stop - return False and let CLI handle messaging.
