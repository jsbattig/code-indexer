# Feature: CIDX Daemonization

## Feature Overview

**Objective:** Eliminate Python startup overhead and repeated index loading by implementing a persistent RPyC daemon service with in-memory index caching.

**Business Value:**
- Reduce startup overhead from 1.86s to 50ms (97% reduction)
- Eliminate repeated index loading (376ms saved per query via caching)
- Enable concurrent read queries with proper synchronization
- Maintain full backward compatibility with automatic fallback

**Priority:** HIGH - MVP

## Problem Statement

### Current Architecture Issues

**Per-Query Overhead (Current):**
```
Every cidx query command:
├── Python interpreter startup: 400ms
├── Import Rich/argparse/modules: 460ms
├── Application initialization: 1000ms
├── Load HNSW index from disk: 180ms
├── Load ID mapping from disk: 196ms
├── Generate embedding: 792ms
└── Perform search: 62ms
Total: 3090ms per query
```

**Scale Impact:**
- 100 queries = 5.15 minutes (309 seconds)
- 1000 queries = 51.5 minutes
- "Dozens of jobs doing queries" (per conversation)

### Root Causes
1. **Cold Start:** Every query starts fresh Python process
2. **No Caching:** Indexes loaded from disk repeatedly
3. **Import Tax:** Rich/argparse loaded per query
4. **No Concurrency:** Sequential processing only

## Solution Architecture

### Daemon Service Design

```
┌─────────────────────────────────────────────┐
│              CIDX CLI Client                │
│         (Lightweight, 50ms startup)         │
└──────────────────┬──────────────────────────┘
                   │ RPyC (Unix Socket Only)
                   ▼
┌─────────────────────────────────────────────┐
│    CIDX Daemon Service (Per-Repository)     │
│      Socket: .code-indexer/daemon.sock      │
│                                             │
│  ┌─────────────────────────────────────────┐   │
│  │    In-Memory Index Cache            │   │
│  │  ┌──────────────────────────────┐   │   │
│  │  │ HNSW + ID Map + FTS Indexes  │   │   │
│  │  │ (TTL: 10 min, last: 2m ago)  │   │   │
│  │  └──────────────────────────────┘   │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────────┐   │
│  │    Concurrency Manager              │   │
│  │  - RLock per project (reads)        │   │
│  │  - Lock per project (writes)        │   │
│  │  - Multi-client support             │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Key Components

**1. RPyC Daemon Service**
- **One daemon per repository** (identified by config location after backtrack)
- Persistent Python process with pre-loaded imports
- Listens on Unix socket at `.code-indexer/daemon.sock`
- Handles multiple concurrent connections from different clients
- Automatic restart on failure with crash recovery (2 attempts before fallback)

**2. In-Memory Index Cache**
- Single project cache (daemon is per-repository)
- HNSW index, ID mapping, and FTS Tantivy indexes
- TTL-based eviction (default 10 minutes, configurable)
- Background thread monitors and evicts expired entries every 60 seconds
- Optional auto-shutdown when idle and cache expired
- No hard memory limits (trust OS management)

**3. Client Delegation**
- Lightweight CLI detects daemon configuration
- Establishes RPyC connection (~50ms)
- Delegates query to daemon
- Loads Rich imports async during RPC call
- **Crash recovery:** 2 restart attempts before fallback to standalone

**4. Concurrency Control**
- RLock for concurrent reads (multiple clients can query simultaneously)
- Lock for serialized writes (indexing operations)
- Thread-safe cache operations
- Connection pooling for multiple clients

**5. Socket Management**
- **Socket binding as atomic lock** (no PID files needed)
- Socket path: `.code-indexer/daemon.sock` (next to config.json)
- Automatic cleanup of stale sockets
- Unix domain sockets only (no TCP/IP support)

## User Stories

### Story 2.0: RPyC Performance PoC [BLOCKING]
Validate daemon architecture before full implementation.

### Story 2.1: RPyC Daemon Service with In-Memory Index Caching
Build core daemon service with caching infrastructure.

### Story 2.2: Repository Daemon Configuration
Enable per-repository daemon configuration and management.

### Story 2.3: Client Delegation with Async Import Warming
Implement lightweight client with intelligent delegation.

### Story 2.4: Progress Callbacks via RPyC for Indexing
Enable progress streaming from daemon to client terminal.

## Architecture Decisions

### Decision: Backward Compatibility (Option A Selected)
**Approach:** Optional daemon with automatic fallback
- Daemon configured per repository via `cidx init --daemon`
- Auto-detect daemon mode from config
- Silent fallback if daemon unreachable
- Console messages explain fallback

**Rationale:** Zero friction adoption, graceful degradation

### Decision: Memory Management (TTL-based Selected)
**Approach:** TTL eviction without hard limits
- Default 10-minute TTL per project
- Configurable via `ttl_minutes` in config.json
- Background monitoring thread (60-second intervals)
- Auto-shutdown on idle when enabled
- No memory caps

**Rationale:** Simple, predictable, avoids premature eviction

### Decision: Daemon Lifecycle (Option B Selected)
**Approach:** Automatic daemon startup
- First query auto-starts daemon if configured
- No manual daemon commands needed
- Socket binding for process tracking (no PID files)
- Health monitoring
- Crash recovery with 2 restart attempts

**Rationale:** Frictionless user experience

### Decision: Error Handling (Option A Selected)
**Approach:** Silent fallback with console reporting
- Always complete operation
- Never fail due to daemon issues
- Clear console messages
- Troubleshooting tips provided
- 2 restart attempts before fallback

**Rationale:** Reliability over performance

### Decision: Socket Architecture (Unix Only)
**Approach:** Unix domain sockets only
- Socket at `.code-indexer/daemon.sock` (per-repository)
- Socket binding as atomic lock mechanism
- No TCP/IP support (simplified architecture)
- Automatic cleanup of stale sockets

**Rationale:** Simplicity, security, atomic operations

### Decision: Retry Strategy (Exponential Backoff)
**Approach:** Progressive retry delays
- 4 retry attempts: [100, 500, 1000, 2000]ms
- Exponential backoff reduces connection storms
- Graceful degradation after retries exhausted

**Rationale:** Balance between quick recovery and system load

## Non-Functional Requirements

### Performance Requirements
- Daemon startup: <50ms client connection time
- Cache hit: <5ms index retrieval
- Cache miss: Normal load time + <10ms overhead
- RPC overhead: <100ms per call
- Concurrent queries: Support 10+ simultaneous reads
- FTS queries: <100ms with warm cache (95% improvement)

### Reliability Requirements
- Automatic daemon restart on crash (2 attempts)
- Graceful fallback to standalone mode
- No data corruption on daemon failure
- Clean shutdown on system signals
- Socket binding for atomic process management
- Multi-client concurrent access support

### Scalability Requirements
- One daemon per repository (not system-wide)
- Handle 1000+ queries/minute per daemon
- Efficient memory usage with 10-minute TTL eviction
- Connection pooling for multiple clients
- Auto-shutdown on idle to free resources

## Implementation Approach

### Phase 1: Core Daemon Infrastructure
1. RPyC service skeleton
2. Basic cache implementation (semantic + FTS)
3. Configuration management
4. Socket binding mechanism

### Phase 2: Client Integration
1. Daemon detection logic
2. RPyC client implementation with retry backoff
3. Fallback mechanism with crash recovery
4. Async import warming

### Phase 3: Advanced Features
1. Progress callback streaming
2. TTL-based eviction with 60-second checks
3. Health monitoring
4. Auto-restart logic with 2 attempts
5. Auto-shutdown on idle

## Testing Strategy

### Unit Tests
- Cache operations (get/set/evict)
- TTL expiration logic (10-minute default)
- Concurrency control (locks)
- Configuration parsing
- Socket binding race conditions

### Integration Tests
- Client-daemon communication
- Fallback scenarios
- Progress streaming
- Multi-client concurrent access
- Crash recovery (2 attempts)

### Performance Tests
- Baseline vs daemon comparison
- Cache hit/miss scenarios
- Concurrent query handling
- Memory growth over time
- FTS query performance (95% improvement target)

### Reliability Tests
- Daemon crash recovery (2 attempts)
- Network interruption handling
- Clean shutdown behavior
- Socket binding conflicts
- Multi-client race conditions

## Success Metrics

**Quantitative:**
- [ ] Startup time: 1.86s → ≤50ms
- [ ] Index load elimination: 376ms → 0ms (cached)
- [ ] Total query time: 3.09s → ≤1.0s (with cache hit)
- [ ] FTS query time: 2.24s → ≤100ms (with cache hit, 95% improvement)
- [ ] Concurrent support: ≥10 simultaneous queries
- [ ] Memory stability: <500MB growth over 1000 queries
- [ ] TTL accuracy: Cache evicted within 60s of expiry

**Qualitative:**
- [ ] Transparent daemon operation
- [ ] No manual daemon management
- [ ] Clear fallback messaging
- [ ] Zero breaking changes
- [ ] Multi-client support working

## Risk Analysis

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| RPyC instability | High | Low | Comprehensive PoC validation |
| Memory growth | High | Medium | 10-min TTL + auto-shutdown |
| Daemon crashes | High | Low | 2 auto-restarts + fallback |
| Complex debugging | Medium | Medium | Extensive logging |
| Socket conflicts | Low | Low | Per-project sockets |
| Race conditions | Medium | Low | Socket binding as lock |

## Documentation Requirements

- [ ] Daemon architecture overview
- [ ] Configuration guide (`cidx init --daemon`)
- [ ] Troubleshooting guide
- [ ] Performance tuning guide
- [ ] Migration guide for existing users

## Technical Specifications

### Configuration Schema
```json
{
  "version": "2.0.0",
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

### RPyC Service Interface
```python
class CIDXDaemonService(rpyc.Service):
    def exposed_query(self, project_path, query, limit, **kwargs):
        """Execute semantic search query."""

    def exposed_query_fts(self, project_path, query, **kwargs):
        """Execute FTS query with caching."""

    def exposed_query_hybrid(self, project_path, query, **kwargs):
        """Execute parallel semantic + FTS search."""

    def exposed_index(self, project_path, callback=None, **kwargs):
        """Perform indexing with optional progress callback."""

    def exposed_get_status(self):
        """Return daemon status and cache statistics."""

    def exposed_clear_cache(self, project_path=None):
        """Clear cache for project."""
```

### Cache Structure
```python
{
    # Single project cache (daemon is per-repository)
    "hnsw_index": <loaded_index>,
    "id_mapping": <loaded_mapping>,
    "tantivy_index": <loaded_fts_index>,
    "tantivy_searcher": <cached_searcher>,
    "fts_available": True,
    "last_accessed": datetime.now(),
    "ttl_minutes": 10,
    "lock": RLock(),  # For reads
    "write_lock": Lock()  # For indexing
}
```

### Socket Management
```python
def get_socket_path() -> Path:
    """Determine socket path from config location."""
    config_path = ConfigManager.find_config_upward(Path.cwd())
    return config_path.parent / "daemon.sock"

def bind_socket_as_lock():
    """Use socket binding as atomic lock."""
    try:
        server.bind(socket_path)  # Atomic operation
    except OSError as e:
        if "Address already in use" in str(e):
            # Daemon already running
            sys.exit(0)
```

## References

**Conversation Context:**
- "One daemon per indexed repository"
- "Socket at .code-indexer/daemon.sock"
- "Socket binding as atomic lock (no PID files)"
- "Unix sockets only (no TCP/IP)"
- "TTL default 10 minutes"
- "Auto-shutdown on idle when enabled"
- "Retry with exponential backoff [100, 500, 1000, 2000]ms"
- "2 restart attempts before fallback"
- "Multi-client concurrent access support"
- "FTS integration for 95% query improvement"