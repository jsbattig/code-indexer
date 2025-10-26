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
                   │ RPyC (TCP/Unix Socket)
                   ▼
┌─────────────────────────────────────────────┐
│           CIDX Daemon Service               │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │    In-Memory Index Cache            │   │
│  │  ┌──────────────────────────────┐   │   │
│  │  │ Project A: HNSW + ID Map     │   │   │
│  │  │ (TTL: 60 min, last: 2m ago)  │   │   │
│  │  ├──────────────────────────────┤   │   │
│  │  │ Project B: HNSW + ID Map     │   │   │
│  │  │ (TTL: 60 min, last: 5m ago)  │   │   │
│  │  └──────────────────────────────┘   │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │    Concurrency Manager              │   │
│  │  - RLock per project (reads)        │   │
│  │  - Lock per project (writes)        │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Key Components

**1. RPyC Daemon Service**
- Persistent Python process with pre-loaded imports
- Listens on Unix socket (local) or TCP (remote)
- Handles multiple concurrent connections
- Automatic restart on failure

**2. In-Memory Index Cache**
- Per-project HNSW index and ID mapping storage
- TTL-based eviction (default 60 minutes, configurable)
- Background thread monitors and evicts expired entries
- No hard memory limits (trust OS management)

**3. Client Delegation**
- Lightweight CLI detects daemon configuration
- Establishes RPyC connection (~50ms)
- Delegates query to daemon
- Loads Rich imports async during RPC call

**4. Concurrency Control**
- Per-project RLock for concurrent reads
- Per-project Lock for serialized writes
- Thread-safe cache operations
- Connection pooling for multiple clients

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
- Default 60-minute TTL per project
- Configurable via `daemon_ttl_minutes` in config.json
- Background monitoring thread
- No memory caps

**Rationale:** Simple, predictable, avoids premature eviction

### Decision: Daemon Lifecycle (Option B Selected)
**Approach:** Automatic daemon startup
- First query auto-starts daemon if configured
- No manual daemon commands needed
- PID file tracking
- Health monitoring

**Rationale:** Frictionless user experience

### Decision: Error Handling (Option A Selected)
**Approach:** Silent fallback with console reporting
- Always complete operation
- Never fail due to daemon issues
- Clear console messages
- Troubleshooting tips provided

**Rationale:** Reliability over performance

## Non-Functional Requirements

### Performance Requirements
- Daemon startup: <50ms client connection time
- Cache hit: <5ms index retrieval
- Cache miss: Normal load time + <10ms overhead
- RPC overhead: <100ms per call
- Concurrent queries: Support 10+ simultaneous reads

### Reliability Requirements
- Automatic daemon restart on crash
- Graceful fallback to standalone mode
- No data corruption on daemon failure
- Clean shutdown on system signals
- PID file management for process tracking

### Scalability Requirements
- Support 100+ projects in cache
- Handle 1000+ queries/minute
- Efficient memory usage with TTL eviction
- Connection pooling for multiple clients

## Implementation Approach

### Phase 1: Core Daemon Infrastructure
1. RPyC service skeleton
2. Basic cache implementation
3. Configuration management
4. PID file handling

### Phase 2: Client Integration
1. Daemon detection logic
2. RPyC client implementation
3. Fallback mechanism
4. Async import warming

### Phase 3: Advanced Features
1. Progress callback streaming
2. TTL-based eviction
3. Health monitoring
4. Auto-restart logic

## Testing Strategy

### Unit Tests
- Cache operations (get/set/evict)
- TTL expiration logic
- Concurrency control (locks)
- Configuration parsing

### Integration Tests
- Client-daemon communication
- Fallback scenarios
- Progress streaming
- Multi-project caching

### Performance Tests
- Baseline vs daemon comparison
- Cache hit/miss scenarios
- Concurrent query handling
- Memory growth over time

### Reliability Tests
- Daemon crash recovery
- Network interruption handling
- Clean shutdown behavior
- PID file management

## Success Metrics

**Quantitative:**
- [ ] Startup time: 1.86s → ≤50ms
- [ ] Index load elimination: 376ms → 0ms (cached)
- [ ] Total query time: 3.09s → ≤1.0s (with cache hit)
- [ ] Concurrent support: ≥10 simultaneous queries
- [ ] Memory stability: <500MB growth over 1000 queries

**Qualitative:**
- [ ] Transparent daemon operation
- [ ] No manual daemon management
- [ ] Clear fallback messaging
- [ ] Zero breaking changes

## Risk Analysis

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| RPyC instability | High | Low | Comprehensive PoC validation |
| Memory growth | High | Medium | TTL eviction + monitoring |
| Daemon crashes | High | Low | Auto-restart + fallback |
| Complex debugging | Medium | Medium | Extensive logging |
| Platform issues | Low | Low | Unix/TCP socket options |

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
  "daemon": {
    "enabled": true,
    "ttl_minutes": 60,
    "socket_type": "unix",
    "socket_path": "/tmp/cidx-daemon.sock",
    "tcp_port": 9876,
    "auto_start": true
  }
}
```

### RPyC Service Interface
```python
class CIDXDaemonService(rpyc.Service):
    def exposed_query(self, project_path, query, limit, **kwargs):
        """Execute semantic search query."""

    def exposed_index(self, project_path, callback=None, **kwargs):
        """Perform indexing with optional progress callback."""

    def exposed_get_status(self):
        """Return daemon status and cache statistics."""

    def exposed_clear_cache(self, project_path=None):
        """Clear cache for project or all projects."""
```

### Cache Structure
```python
{
    "/path/to/project1": {
        "hnsw_index": <loaded_index>,
        "id_mapping": <loaded_mapping>,
        "last_accessed": datetime.now(),
        "ttl_minutes": 60,
        "lock": RLock()  # For reads
        "write_lock": Lock()  # For indexing
    }
}
```

## References

**Conversation Context:**
- "Persistent RPyC daemon with in-memory index caching"
- "Client delegation with async import warming"
- "Progress streaming via RPyC callbacks"
- "Per-project concurrency control"
- "Option A selected: Daemon optional with auto-fallback"
- "Option B selected: Automatic daemon startup on first query"
- "TTL-based eviction (default 60 minutes, configurable)"