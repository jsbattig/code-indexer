# Story 10: Matrix Multiplication Resident Service

**Story ID:** S10
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 5-7 days
**Implementation Order:** 10

## User Story

**As a** developer using filesystem backend for large repositories
**I want** projection matrix multiplications to be fast and memory-efficient
**So that** indexing and querying don't reload the projection matrix thousands of times

**Conversation Reference:** "shouldn't we create a matrix multiplication resident service, automatically managed by the first call to cidx that needs this, automatically restarted if not running, accessible using a pipe or http so the matrix is loaded once, per indexed repo, and available to run multiplications as needed?"

## Business Value

### Problems Solved
1. **Performance Bottleneck:** Current implementation loads 513 KB projection matrix on every `cidx index` call (3,500 loads for Django = 1.7 GB I/O waste)
2. **Memory Inefficiency:** Matrix loaded and discarded repeatedly instead of staying resident
3. **Indexing Speed:** Eliminating redundant I/O improves throughput by ~30-50%

### Performance Impact
- **Before:** 513 KB × 3,500 loads = 1.7 GB disk I/O per indexing session
- **After:** 513 KB × 1 load = one-time cost, reused for all operations
- **Speedup:** Estimated 30-50% faster indexing for large repositories

## Acceptance Criteria

### Functional Requirements

1. ✅ **Service Auto-Start:** First `cidx` operation requiring matrix multiplication automatically starts service if not running
2. ✅ **HTTP API:** Service exposes HTTP endpoint for matrix multiplication requests
3. ✅ **Matrix Loading:** Service loads projection matrices on-demand from YAML files
4. ✅ **Matrix Caching:** Loaded matrices stay in RAM with 60-minute TTL per matrix
5. ✅ **Auto-Shutdown:** Service shuts down after 60 minutes of complete inactivity (no requests)
6. ✅ **Matrix Identification:** Matrices identified by full absolute path to collection directory
7. ✅ **YAML Format:** Projection matrices stored in text-based YAML format (git-friendly)
8. ✅ **Fallback Mode:** If service fails to start or respond within 5s, fall back to in-process multiplication
9. ✅ **Visible Feedback:** Console shows "⚠️ Using in-process matrix multiplication (service unavailable)" when fallback occurs

### Technical Requirements

1. ✅ **Service Architecture:** Single global service per machine (not per-repo)
2. ✅ **Port Allocation:** Uses existing GlobalPortRegistry for dynamic port allocation with lock file
3. ✅ **Collision Detection:** If two services attempt to start simultaneously, port allocation determines winner (loser exits gracefully)
4. ✅ **Client Retry Logic:** Exponential backoff up to 5 seconds total when launching service
   - Retry delays: 100ms, 200ms, 400ms, 800ms, 1600ms, 1900ms (total: 5s)
   - Max retry count: 6 attempts
5. ✅ **Service Discovery:** Client checks for running service before attempting to start
6. ✅ **Health Endpoint:** Service provides `/health` endpoint for readiness checks
7. ✅ **Graceful Shutdown:** Service handles SIGTERM/SIGINT for clean shutdown
8. ✅ **PID Management:** Service writes PID file for detection and cleanup
9. ✅ **Response Timeout:** Matrix multiplication responses must return within 5s or client falls back

### Storage Requirements

1. ✅ **YAML Matrix Format:**
   ```yaml
   # projection_matrix.yaml
   shape: [1024, 64]
   dtype: float32
   data:
     - [0.123, -0.456, 0.789, ...]  # Row 1 (64 values)
     - [0.234, -0.567, 0.890, ...]  # Row 2 (64 values)
     # ... 1024 rows total
   created_at: "2025-10-24T12:00:00Z"
   collection: "voyage-code-3"
   ```

2. ✅ **Backward Compatibility:** Existing `.npy` files automatically converted to `.yaml` on first use
3. ✅ **Storage Overhead:** Accept 5-10x size increase (513 KB → ~3-5 MB) for git-friendly text format
4. ✅ **Lazy Conversion:** Convert `.npy` → `.yaml` only when needed (not all at once)

### API Requirements

1. ✅ **HTTP Endpoints:**
   - `POST /multiply` - Perform matrix multiplication
     - Request: `{"vector": [1024 floats], "collection_path": "/full/path/to/collection"}`
     - Response: `{"result": [64 floats], "cache_hit": true/false}`
   - `GET /health` - Service health check
     - Response: `{"status": "ready", "cached_matrices": 3, "uptime_seconds": 1234}`
   - `GET /stats` - Service statistics
     - Response: `{"cache_size": 3, "total_multiplications": 15234, "cache_hits": 98.5%}`
   - `POST /shutdown` - Graceful shutdown (for testing)

2. ✅ **Request Validation:** Validate vector dimensions match expected matrix input dimensions
3. ✅ **Error Responses:** Return 400/500 with descriptive error messages

### Service Management Requirements

1. ✅ **Auto-Start Logic:**
   ```python
   def get_reduced_vector(vector: np.ndarray, collection_path: Path) -> np.ndarray:
       # Try service first
       try:
           result = matrix_service_client.multiply(vector, collection_path, timeout=5)
           return result
       except ServiceNotRunning:
           # Start service and retry
           start_service()
           # Retry with exponential backoff (up to 5s total)
           result = matrix_service_client.multiply_with_retry(vector, collection_path)
           return result
       except (Timeout, ServiceError):
           # Fallback to in-process
           console.print("⚠️ Using in-process matrix multiplication (service unavailable)")
           return load_and_multiply_locally(vector, collection_path)
   ```

2. ✅ **Service Detection:** Check for running service via:
   - PID file exists at `~/.code-indexer-matrix-service/service.pid`
   - Process with PID is alive
   - Health endpoint responds

3. ✅ **Service Location:**
   ```
   ~/.code-indexer-matrix-service/
   ├── service.pid           # Process ID
   ├── service.log           # Service logs
   ├── port.txt              # Allocated port number
   ├── cache/                # Matrix cache directory
   │   ├── {sha256_path1}.yaml  # Cached matrix for collection 1
   │   └── {sha256_path2}.yaml  # Cached matrix for collection 2
   ```

4. ✅ **Matrix Cache Management:**
   - **Cache Key:** SHA256 hash of absolute collection path
   - **Cache Entry:** `{matrix: np.ndarray, last_access: datetime, collection_path: str}`
   - **TTL:** 60 minutes per matrix
   - **Eviction:** Background thread checks every 5 minutes, evicts expired matrices

### Client Integration Requirements

1. ✅ **Refactor FilesystemVectorStore.upsert_points():**
   - Remove `matrix_manager.load_matrix()` call (line 170)
   - Replace with `matrix_service_client.multiply()` call
   - Add fallback to in-process multiplication on failure

2. ✅ **Refactor VectorQuantizer.quantize_vector():**
   - Accept pre-computed 64-dim vector OR
   - Accept 1024-dim vector + call service for reduction

3. ✅ **Add MatrixServiceClient class:**
   ```python
   class MatrixServiceClient:
       def multiply(self, vector: np.ndarray, collection_path: Path, timeout: float = 5.0) -> np.ndarray:
           """Call service or fallback to local."""

       def multiply_with_retry(self, vector: np.ndarray, collection_path: Path) -> np.ndarray:
           """Retry with exponential backoff."""

       def is_service_running(self) -> bool:
           """Check if service is accessible."""

       def start_service(self) -> bool:
           """Attempt to start service."""
   ```

### Collision Detection Requirements

1. ✅ **Port Allocation as Tie-Breaker:**
   ```python
   # Service startup
   try:
       port = GlobalPortRegistry().allocate_port("matrix-service")
       # Success! This service wins
       start_http_server(port)
   except PortAllocationError:
       # Another service already running
       logger.info("Matrix service already running, exiting gracefully")
       sys.exit(0)
   ```

2. ✅ **Atomic Operations:** Port allocation uses file locking (existing GlobalPortRegistry handles this)

3. ✅ **Service Discovery:** Client reads allocated port from registry before attempting connection

### Performance Requirements

1. ✅ **Matrix Multiplication:** <100ms per operation (in-memory matrix multiplication)
2. ✅ **Service Startup:** <2s to be ready for first request
3. ✅ **HTTP Overhead:** <10ms round-trip for localhost HTTP call
4. ✅ **YAML Loading:** <1s to load and parse 5 MB YAML file
5. ✅ **Total Latency:** <200ms per multiplication (service) vs ~50ms (in-process fallback)

### Safety Requirements

1. ✅ **Crash Recovery:** If service crashes, client auto-restarts it on next call
2. ✅ **Orphan Process Prevention:** PID file cleanup on service shutdown
3. ✅ **Resource Limits:** Service monitors memory usage, warns if cache exceeds 500 MB
4. ✅ **Concurrent Requests:** Service handles multiple simultaneous requests (thread pool)
5. ✅ **Invalid Requests:** Service validates vector dimensions before multiplication

## Manual Testing Steps

```bash
# Test 1: Service auto-starts on first indexing
cd /tmp/test-repo
cidx init --vector-store filesystem
cidx index

# Expected:
# [Background] Matrix multiplication service starting on port 18765
# [Service ready in 1.2s]
# Indexing proceeds normally

# Verify service running
ps aux | grep matrix-service
cat ~/.code-indexer-matrix-service/service.pid
curl http://localhost:18765/health
# Expected: {"status": "ready", "cached_matrices": 1}

# Test 2: Service reuses loaded matrix
cidx index  # Second run
# Expected: Faster (no matrix loading), uses cached matrix

# Test 3: Service auto-shuts down after 60 min idle
# Wait 61 minutes
ps aux | grep matrix-service
# Expected: Service not running (auto-shutdown)

# Test 4: Collision detection (two services)
# Terminal 1:
python -m code_indexer.services.matrix_service &
# Terminal 2:
python -m code_indexer.services.matrix_service &
# Expected: Second service exits immediately (port already allocated)

# Test 5: Fallback to in-process
# Kill service
pkill -f matrix-service
# Remove PID file to simulate crash
rm ~/.code-indexer-matrix-service/service.pid
# Prevent service startup
chmod -x $(which python)  # Extreme test
cidx index

# Expected:
# [Attempt to start service: FAILED]
# ⚠️ Using in-process matrix multiplication (service unavailable)
# [Indexing proceeds with in-process multiplication]

# Test 6: YAML matrix format
cat .code-indexer/index/voyage-code-3/projection_matrix.yaml
# Expected: Text-based YAML format, human-readable

# Test 7: Service timeout handling
# Simulate slow service (debug mode with delays)
MATRIX_SERVICE_DEBUG_DELAY=10 cidx index

# Expected after 5s:
# ⚠️ Matrix service timeout (5s exceeded)
# ⚠️ Using in-process matrix multiplication
```

## Technical Implementation Details

### Service Architecture

```python
# src/code_indexer/services/matrix_multiplication_service.py

class MatrixMultiplicationService:
    """HTTP service for fast projection matrix multiplications."""

    def __init__(self, port: int):
        self.port = port
        self.matrix_cache: Dict[str, CachedMatrix] = {}
        self.cache_lock = threading.Lock()
        self.last_request_time = time.time()
        self.shutdown_timer = None

    def start(self):
        """Start HTTP service."""
        app = Flask(__name__)

        @app.route('/multiply', methods=['POST'])
        def multiply():
            data = request.json
            vector = np.array(data['vector'])
            collection_path = Path(data['collection_path'])

            # Get or load matrix
            matrix = self._get_or_load_matrix(collection_path)

            # Perform multiplication
            result = np.dot(vector, matrix)

            return jsonify({'result': result.tolist()})

        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'ready',
                'cached_matrices': len(self.matrix_cache),
                'uptime_seconds': time.time() - self.start_time
            })

        app.run(host='127.0.0.1', port=self.port, threaded=True)

    def _get_or_load_matrix(self, collection_path: Path) -> np.ndarray:
        """Get cached matrix or load from YAML."""
        cache_key = hashlib.sha256(str(collection_path.absolute()).encode()).hexdigest()

        with self.cache_lock:
            # Check cache
            if cache_key in self.matrix_cache:
                entry = self.matrix_cache[cache_key]

                # Check TTL (60 minutes)
                if time.time() - entry.last_access < 3600:
                    entry.last_access = time.time()
                    return entry.matrix
                else:
                    # Expired, remove from cache
                    del self.matrix_cache[cache_key]

            # Load from YAML file
            yaml_path = collection_path / 'projection_matrix.yaml'

            if not yaml_path.exists():
                # Convert from .npy if YAML doesn't exist
                npy_path = collection_path / 'projection_matrix.npy'
                if npy_path.exists():
                    matrix = self._convert_npy_to_yaml(npy_path, yaml_path)
                else:
                    raise FileNotFoundError(f"No projection matrix found at {collection_path}")
            else:
                # Load from YAML
                matrix = self._load_matrix_yaml(yaml_path)

            # Cache the loaded matrix
            self.matrix_cache[cache_key] = CachedMatrix(
                matrix=matrix,
                last_access=time.time(),
                collection_path=str(collection_path)
            )

            return matrix

    def _load_matrix_yaml(self, yaml_path: Path) -> np.ndarray:
        """Load projection matrix from YAML format."""
        import yaml

        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        shape = tuple(data['shape'])
        dtype = data.get('dtype', 'float32')
        matrix_data = data['data']

        # Convert nested list to numpy array
        matrix = np.array(matrix_data, dtype=dtype)

        # Verify shape
        if matrix.shape != shape:
            raise ValueError(f"Matrix shape mismatch: expected {shape}, got {matrix.shape}")

        return matrix

    def _convert_npy_to_yaml(self, npy_path: Path, yaml_path: Path) -> np.ndarray:
        """Convert existing .npy file to YAML format."""
        import yaml

        # Load binary matrix
        matrix = np.load(npy_path)

        # Convert to YAML-serializable format
        yaml_data = {
            'shape': list(matrix.shape),
            'dtype': str(matrix.dtype),
            'data': matrix.tolist(),
            'created_at': datetime.utcnow().isoformat(),
            'converted_from_npy': True
        }

        # Write YAML
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False)

        return matrix
```

### Client Integration

```python
# src/code_indexer/services/matrix_service_client.py

class MatrixServiceClient:
    """Client for matrix multiplication service with automatic fallback."""

    SERVICE_HOME = Path.home() / '.code-indexer-matrix-service'
    MAX_RETRIES = 6
    RETRY_DELAYS = [0.1, 0.2, 0.4, 0.8, 1.6, 1.9]  # Total: 5.0s

    def multiply(self, vector: np.ndarray, collection_path: Path, timeout: float = 5.0) -> np.ndarray:
        """Multiply vector by projection matrix via service or fallback.

        Args:
            vector: Input vector (e.g., 1024-dim from VoyageAI)
            collection_path: Absolute path to collection directory
            timeout: Max time to wait for service response

        Returns:
            Reduced vector (e.g., 64-dim for quantization)
        """
        try:
            # Check if service is running
            if not self._is_service_running():
                # Attempt to start service
                if not self._start_service_with_retry():
                    # Startup failed after retries
                    return self._fallback_multiply(vector, collection_path)

            # Call service
            port = self._get_service_port()
            response = requests.post(
                f'http://127.0.0.1:{port}/multiply',
                json={
                    'vector': vector.tolist(),
                    'collection_path': str(collection_path.absolute())
                },
                timeout=timeout
            )

            if response.status_code == 200:
                result = np.array(response.json()['result'])
                return result
            else:
                # Service error
                raise ServiceError(f"Service returned {response.status_code}")

        except (requests.Timeout, requests.ConnectionError, ServiceError) as e:
            # Service unavailable or timeout
            console.print(f"⚠️ Using in-process matrix multiplication (service unavailable: {e})")
            return self._fallback_multiply(vector, collection_path)

    def _start_service_with_retry(self) -> bool:
        """Attempt to start service with exponential backoff.

        Returns:
            True if service started and ready, False otherwise
        """
        # Start service process
        subprocess.Popen(
            [sys.executable, '-m', 'code_indexer.services.matrix_service'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent
        )

        # Wait for service to be ready (exponential backoff)
        for attempt, delay in enumerate(self.RETRY_DELAYS, 1):
            time.sleep(delay)

            if self._is_service_running():
                # Service is ready
                return True

            if attempt >= self.MAX_RETRIES:
                # Max retries exceeded
                return False

        return False

    def _is_service_running(self) -> bool:
        """Check if service is running and healthy."""
        try:
            # Check PID file
            pid_file = self.SERVICE_HOME / 'service.pid'
            if not pid_file.exists():
                return False

            pid = int(pid_file.read_text().strip())

            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 checks existence without killing
            except OSError:
                # Process doesn't exist
                pid_file.unlink()  # Clean up stale PID file
                return False

            # Check health endpoint
            port = self._get_service_port()
            response = requests.get(f'http://127.0.0.1:{port}/health', timeout=1.0)

            return response.status_code == 200

        except Exception:
            return False

    def _get_service_port(self) -> int:
        """Get service port from port file."""
        port_file = self.SERVICE_HOME / 'port.txt'
        if port_file.exists():
            return int(port_file.read_text().strip())

        # Fallback to GlobalPortRegistry
        from code_indexer.services.global_port_registry import GlobalPortRegistry
        registry = GlobalPortRegistry()
        return registry.get_port_for_service('matrix-service')

    def _fallback_multiply(self, vector: np.ndarray, collection_path: Path) -> np.ndarray:
        """Fallback to in-process matrix multiplication."""
        from code_indexer.storage.projection_matrix_manager import ProjectionMatrixManager

        manager = ProjectionMatrixManager()

        # Try YAML first, fallback to .npy
        yaml_path = collection_path / 'projection_matrix.yaml'
        npy_path = collection_path / 'projection_matrix.npy'

        if yaml_path.exists():
            matrix = manager.load_matrix_yaml(yaml_path)
        elif npy_path.exists():
            matrix = np.load(npy_path)
        else:
            raise FileNotFoundError(f"No projection matrix found at {collection_path}")

        # Perform multiplication
        return np.dot(vector, matrix)
```

### Service Implementation

```python
# src/code_indexer/services/matrix_service.py

class MatrixServiceDaemon:
    """Standalone HTTP service for matrix multiplications."""

    def __init__(self):
        self.service_home = Path.home() / '.code-indexer-matrix-service'
        self.service_home.mkdir(exist_ok=True)

        self.cache: Dict[str, CachedMatrix] = {}
        self.cache_lock = threading.Lock()
        self.last_request_time = time.time()
        self.start_time = time.time()

        # Allocate port using GlobalPortRegistry (collision detection)
        self.port = self._allocate_port()

        # Start inactivity monitor
        self.shutdown_timer = threading.Thread(target=self._monitor_inactivity, daemon=True)
        self.shutdown_timer.start()

    def _allocate_port(self) -> int:
        """Allocate port using GlobalPortRegistry (collision detection).

        Raises:
            PortAllocationError: If port already allocated (another service running)
        """
        from code_indexer.services.global_port_registry import GlobalPortRegistry

        try:
            registry = GlobalPortRegistry()
            port = registry.allocate_port_for_service('matrix-service')

            # Write port to file for client discovery
            (self.service_home / 'port.txt').write_text(str(port))

            return port
        except Exception as e:
            # Port allocation failed (another service running)
            logging.info("Matrix service already running (port allocated), exiting gracefully")
            sys.exit(0)  # Graceful exit (loser in collision detection)

    def _monitor_inactivity(self):
        """Background thread monitoring inactivity and shutting down after 60 min."""
        while True:
            time.sleep(300)  # Check every 5 minutes

            # Check overall inactivity
            idle_time = time.time() - self.last_request_time

            if idle_time > 3600:  # 60 minutes
                logging.info(f"Shutting down after {idle_time/60:.1f} minutes of inactivity")
                self._graceful_shutdown()
                break

            # Evict expired matrices (60 min TTL)
            self._evict_expired_matrices()

    def _evict_expired_matrices(self):
        """Remove matrices that haven't been accessed in 60 minutes."""
        now = time.time()

        with self.cache_lock:
            expired_keys = [
                key for key, entry in self.cache.items()
                if now - entry.last_access > 3600
            ]

            for key in expired_keys:
                del self.cache[key]
                logging.info(f"Evicted matrix {key} (TTL expired)")

    def run(self):
        """Start HTTP service."""
        # Write PID file
        (self.service_home / 'service.pid').write_text(str(os.getpid()))

        app = Flask(__name__)

        @app.route('/multiply', methods=['POST'])
        def multiply():
            try:
                data = request.json
                vector = np.array(data['vector'])
                collection_path = Path(data['collection_path'])

                # Update last request time
                self.last_request_time = time.time()

                # Get or load matrix
                matrix = self._get_or_load_matrix(collection_path)

                # Validate dimensions
                if vector.shape[0] != matrix.shape[0]:
                    return jsonify({
                        'error': f'Dimension mismatch: vector is {vector.shape[0]}, matrix expects {matrix.shape[0]}'
                    }), 400

                # Perform multiplication
                result = np.dot(vector, matrix)

                return jsonify({'result': result.tolist()})

            except Exception as e:
                logging.error(f"Matrix multiplication error: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'ready',
                'cached_matrices': len(self.cache),
                'uptime_seconds': time.time() - self.start_time
            })

        @app.route('/stats', methods=['GET'])
        def stats():
            with self.cache_lock:
                cache_info = [
                    {
                        'collection': entry.collection_path,
                        'age_minutes': (time.time() - entry.last_access) / 60
                    }
                    for entry in self.cache.values()
                ]

            return jsonify({
                'cache_size': len(self.cache),
                'cached_matrices': cache_info
            })

        app.run(host='127.0.0.1', port=self.port, threaded=True)

@dataclass
class CachedMatrix:
    """Cached projection matrix with TTL tracking."""
    matrix: np.ndarray
    last_access: float
    collection_path: str
```

## Dependencies

### Internal Dependencies
- Story 2: FilesystemVectorStore.upsert_points() to refactor
- Story 3: FilesystemVectorStore.search() to refactor
- Existing GlobalPortRegistry for port allocation
- Existing ProjectionMatrixManager for matrix operations

### External Dependencies
- Flask (lightweight HTTP server)
- PyYAML (text-based matrix format)
- numpy (matrix operations)
- requests (client HTTP calls)

## Success Metrics

1. ✅ Service starts automatically on first use
2. ✅ Matrix loaded once per collection (not per-file)
3. ✅ Indexing speed improves 30-50% for large repositories
4. ✅ Service auto-shuts down after 60 min idle
5. ✅ Fallback works when service unavailable
6. ✅ Zero user intervention required
7. ✅ Git-friendly YAML format
8. ✅ Collision detection prevents duplicate services

## Non-Goals

- Distributed matrix service (local only)
- GPU acceleration (CPU matrix multiplication sufficient)
- Matrix operations beyond multiplication (just dot product)
- Persistent cache across service restarts (load on-demand)

## Follow-Up Stories

- **Story 11 (Optional):** Matrix service monitoring dashboard
- **Story 12 (Optional):** Matrix compression for even smaller YAML files

## Implementation Notes

### YAML Format Trade-offs

**Pros:**
- Git-friendly (text-based, readable diffs)
- Human-inspectable for debugging
- Cross-platform (no binary format issues)

**Cons:**
- 5-10x larger than .npy (513 KB → ~3-5 MB)
- Slower parsing (~1s vs ~50ms)
- More memory during deserialization

**Mitigation:** Matrices stay resident in service RAM, load cost is one-time per 60 minutes.

### Service Management Strategy

**Auto-Start:**
- No user action required
- First `cidx index` or `cidx query` starts service automatically
- Retry logic handles race conditions

**Auto-Shutdown:**
- Service monitors its own inactivity
- Shuts down after 60 min with no requests
- No orphan processes

**Collision Detection:**
- GlobalPortRegistry provides atomic port allocation
- Second service attempting to start sees port taken, exits immediately
- Clean tie-breaker with no race conditions

### Backward Compatibility

**Existing .npy files:**
- Automatically converted to .yaml on first access
- Original .npy preserved (for safety)
- Conversion is one-time cost

**Fallback mode:**
- If service unavailable, works exactly like before
- No regression in functionality
- Slight performance improvement even with fallback (caching within CLI session)

## Risk Assessment

### Technical Risks

1. **Service Crashes:** Mitigated by auto-restart and fallback
2. **Port Conflicts:** Mitigated by GlobalPortRegistry
3. **Memory Leaks:** Mitigated by TTL eviction
4. **YAML Size:** Accepted trade-off for git-friendliness

### Operational Risks

1. **Service Discovery Failures:** Mitigated by fallback to in-process
2. **Network Timeouts:** Mitigated by 5s timeout + fallback
3. **Concurrent Modifications:** Mitigated by cache key using collection path hash

## Test Scenarios

### Unit Tests

```python
def test_service_auto_starts_on_first_multiply():
    """Service starts automatically when not running."""

def test_service_caches_matrix_with_ttl():
    """Matrix cached for 60 minutes."""

def test_collision_detection_exits_second_service():
    """Second service exits when port already allocated."""

def test_client_retry_logic_with_exponential_backoff():
    """Client retries service startup with delays."""

def test_fallback_when_service_unavailable():
    """Falls back to in-process when service fails."""

def test_yaml_matrix_format_loads_correctly():
    """YAML format deserializes to correct numpy array."""

def test_npy_to_yaml_conversion_automatic():
    """Existing .npy files auto-convert to .yaml."""
```

### Integration Tests

```python
def test_end_to_end_indexing_with_service():
    """Full indexing workflow uses service for all multiplications."""

def test_service_shutdown_after_60_min_idle():
    """Service shuts down after inactivity period."""

def test_multiple_collections_cached_simultaneously():
    """Service caches multiple projection matrices."""
```

### Performance Tests

```python
def test_indexing_performance_improvement():
    """Indexing with service is 30-50% faster than without."""
    # Index 1000 files with service
    # Index 1000 files with fallback
    # Assert service is significantly faster

def test_matrix_multiplication_latency():
    """Service multiplication completes in <200ms."""
```

## Definition of Done

1. ✅ Matrix multiplication service implemented and tested
2. ✅ HTTP API with /multiply, /health, /stats endpoints
3. ✅ Auto-start logic with retry and backoff
4. ✅ Auto-shutdown after 60 min inactivity
5. ✅ YAML matrix format implemented
6. ✅ Automatic .npy → .yaml conversion
7. ✅ Collision detection via port allocation
8. ✅ Client fallback to in-process multiplication
9. ✅ FilesystemVectorStore refactored to use service
10. ✅ All tests passing (unit + integration + performance)
11. ✅ 30-50% indexing performance improvement measured
12. ✅ Documentation updated with service architecture
