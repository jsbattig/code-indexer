# Operating Modes

Complete guide to CIDX's three operating modes: CLI Mode, Daemon Mode, and Server Mode.

## Table of Contents

- [Overview](#overview)
- [Mode Comparison](#mode-comparison)
- [CLI Mode](#cli-mode)
- [Daemon Mode](#daemon-mode)
- [Server Mode](#server-mode)
- [Switching Between Modes](#switching-between-modes)
- [Performance Characteristics](#performance-characteristics)
- [Troubleshooting](#troubleshooting)

## Overview

CIDX operates in three modes, each optimized for different use cases:

1. **CLI Mode** - Direct command execution, simple setup, individual developers
2. **Daemon Mode** - Background service with caching, faster queries, watch mode
3. **Server Mode** - Multi-user server, team collaboration, centralized indexing

All three modes use the same **container-free filesystem storage** - no Docker, no complex setup.

## Mode Comparison

| Feature | CLI Mode | Daemon Mode | Server Mode |
|---------|----------|-------------|-------------|
| **Setup Complexity** | Instant | Simple | Moderate |
| **Query Speed** | ~1s (disk I/O) | ~5ms (cached) | <1ms (cached) |
| **Watch Mode** | No | Yes | N/A |
| **Multi-User** | No | No | Yes |
| **Caching** | None | In-memory HNSW/FTS | Advanced HNSW caching |
| **Authentication** | N/A | N/A | OAuth 2.0 |
| **Best For** | Quick searches | Active development | Team collaboration |
| **Resource Usage** | Minimal | Low | Moderate |
| **Network** | None | Unix socket | HTTP/HTTPS |

**Recommendation**:
- **Start with CLI Mode** - Simple, works immediately
- **Upgrade to Daemon Mode** - If you run many queries and want watch mode
- **Deploy Server Mode** - For team-wide semantic search

## CLI Mode

**Direct command-line interface** for local development. No background processes, no setup complexity.

### How It Works

1. Commands execute directly (no daemon required)
2. Indexes stored in `.code-indexer/` per project
3. Each query loads indexes from disk
4. Filesystem-based vector storage (JSON files)

### Architecture

```
User → cidx query → Load indexes from disk → Search → Return results
                    ↓
              .code-indexer/index/
                └── collection/
                    ├── vectors/*.json
                    ├── index.hnsw
                    └── metadata.json
```

### Setup

```bash
# No setup required! Just install and use
cidx --version

# Navigate to project
cd /path/to/project

# Index code
cidx index

# Query
cidx query "search term"
```

### Storage Location

**Per-Project**: `.code-indexer/` in each indexed project

Contents:
- `index/` - Vector indexes and metadata
- `config.json` - Project configuration
- `scip/` - SCIP indexes (if generated)

### Commands

All `cidx` commands work in CLI mode:

```bash
# Indexing
cidx init                    # Create .code-indexer/
cidx index                   # Index codebase
cidx index --fts             # Add full-text search
cidx index --index-commits   # Add git history

# Querying
cidx query "search"          # Semantic search
cidx query "text" --fts      # Full-text search

# SCIP
cidx scip generate           # Generate SCIP indexes
cidx scip definition "Symbol"

# Data management
cidx clean-data              # Clear indexes
cidx uninstall               # Remove .code-indexer/
```

### Use Cases

**✓ Best For**:
- Individual developers
- Quick ad-hoc searches
- Simple projects
- Minimal setup required
- Learning CIDX

**✗ Not Ideal For**:
- Frequent repeated queries (slow disk I/O)
- Real-time file watching
- Team collaboration
- Performance-critical workflows

### Performance

| Operation | Time | Notes |
|-----------|------|-------|
| **First query** | ~1-2s | Load indexes from disk |
| **Subsequent queries** | ~1s | Reload from disk each time |
| **Indexing** | Varies | Depends on codebase size |

**Why Slower?**:
- No in-memory caching
- Indexes loaded from disk per query
- HNSW graph deserialization overhead

**Trade-off**: Simplicity vs speed. CLI mode prioritizes ease of use.

## Daemon Mode

**Background service** with in-memory caching for faster queries and real-time watch mode.

### How It Works

1. Daemon process runs in background
2. Indexes cached in memory
3. Queries sent via Unix socket (IPC)
4. Watch mode monitors file changes and auto-indexes

### Architecture

```
User → cidx query → Unix socket → Daemon process → Cached indexes → Return results
                                        ↓
                                  In-memory cache:
                                   - HNSW graph
                                   - FTS index
                                   - Metadata
```

### Setup

```bash
# 1. Enable daemon mode
cidx config --daemon

# 2. Start daemon (auto-starts on first query if not running)
cidx start

# 3. Verify daemon is running
cidx status

# 4. Use normally - queries go through daemon
cidx query "search term"
```

### Daemon Management

```bash
# Start daemon
cidx start

# Stop daemon
cidx stop

# Check status
cidx status

# Restart daemon
cidx stop && cidx start
```

### Watch Mode

Monitor files and auto-index changes in real-time:

```bash
# Start watch mode (daemon must be running)
cidx watch

# Watch with FTS indexing
cidx watch --fts

# Custom debounce delay (default: 2.0 seconds)
cidx watch --debounce 3.0

# Stop watch mode
cidx watch-stop
```

**How Watch Mode Works**:
1. Monitors file system for changes
2. Debounces changes (avoids indexing on every keystroke)
3. Automatically indexes modified files
4. Updates cached indexes in real-time

**Use Cases for Watch Mode**:
- Active development sessions
- Keep indexes synchronized with code changes
- Avoid manual re-indexing

### Storage Location

**Per-Project**: `.code-indexer/` (same as CLI mode)

**Additional Files**:
- `daemon.sock` - Unix socket for IPC
- `daemon.pid` - Process ID file

### Performance

| Operation | Time | Improvement vs CLI |
|-----------|------|--------------------|
| **First query** | ~1s | Same (cold cache) |
| **Cached queries** | ~5ms | 200x faster |
| **Watch indexing** | <20ms per file* | Real-time updates |

*Typical performance - actual times vary by file size and system load

**Why Faster?**:
- HNSW/FTS indexes cached in RAM
- No disk I/O for queries
- Unix socket communication (fast IPC)

### Use Cases

**✓ Best For**:
- Active development (frequent queries)
- Real-time file watching
- Performance-sensitive workflows
- Single developer, local machine

**✗ Not Ideal For**:
- Team collaboration (single user only)
- Remote access (Unix socket is local only)
- Minimal resource usage (daemon uses RAM)

### Switching from CLI to Daemon

```bash
# Currently using CLI mode
cidx query "search"  # ~1s per query

# Enable daemon mode
cidx config --daemon
cidx start

# Now using daemon mode
cidx query "search"  # ~5ms per query (cached)
```

### Switching from Daemon to CLI

```bash
# Disable daemon mode
cidx config --no-daemon

# Stop daemon
cidx stop

# Now using CLI mode
cidx query "search"  # Back to ~1s per query
```

## Server Mode

**Multi-user server** with advanced caching for team-wide semantic search.

### How It Works

1. CIDX server runs as HTTP/HTTPS service
2. Centralized golden repositories indexed server-side
3. Advanced HNSW cache (100-1800x speedup)
4. OAuth 2.0 authentication for secure access
5. REST API and MCP interface for clients

### Architecture

```
Users → HTTP/HTTPS → CIDX Server → HNSW Cache → Golden Repositories
                           ↓                            ↓
                      OAuth 2.0              ~/.cidx-server/data/
                                                └── golden-repos/
                                                    ├── project1/
                                                    ├── project2/
                                                    └── project3/
```

### Setup

See [Server Deployment Guide](server-deployment.md) for complete instructions.

**Quick Overview**:
```bash
# 1. Install on server
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46

# 2. Configure environment
export VOYAGE_API_KEY="your-key"
export CIDX_SERVER_PORT=8000

# 3. Add golden repositories
# (done via admin API after server starts)

# 4. Start server
cidx-server start
```

### Golden Repositories

Server mode uses **golden repositories** - centralized code repositories indexed once and shared across all users.

**Benefits**:
- Index code once, query many times
- Shared cache across team
- Consistent results for all users
- Centralized management

**Storage**: `~/.cidx-server/data/golden-repos/`

### Advanced HNSW Caching

Server mode includes sophisticated caching:

| Metric | Value | Description |
|--------|-------|-------------|
| **Cold query** | ~277ms | First query (disk load) |
| **Warm query** | <1ms | Cached query (100-1800x faster) |
| **Cache TTL** | 10 minutes | Default eviction time |
| **Hit ratio** | >95%* | Typical cache efficiency |

*Typical production performance - actual hit ratio varies by usage patterns

**How It Works**:
1. First query: Load index from disk (~277ms)
2. Cache HNSW graph in memory
3. Subsequent queries: Use cached graph (<1ms)
4. TTL expiration: Evict stale cache entries
5. Per-repository isolation: Independent caches

**Cache Configuration**:
```bash
# Set cache TTL (minutes)
export CIDX_INDEX_CACHE_TTL_MINUTES=10  # 10 minutes default

# Increase for longer cache lifetime
export CIDX_INDEX_CACHE_TTL_MINUTES=30  # 30 minutes

# Decrease for more frequent updates
export CIDX_INDEX_CACHE_TTL_MINUTES=5  # 5 minutes
```

**Monitor Cache Performance**:
```bash
# Query cache statistics
curl http://localhost:8000/cache/stats

# Response
{
  "total_hits": 1234,
  "total_misses": 56,
  "hit_ratio": 0.957,
  "active_entries": 12
}
```

### Authentication

Server mode uses **OAuth 2.0** for secure access:

**Roles**:
- **admin** - Full access (manage repos, users)
- **power_user** - Activate repos, query
- **normal_user** - Query only

**Authentication Flow**:
1. User requests access
2. OAuth 2.0 browser flow
3. Server issues tokens
4. Tokens used for API requests

### Client Access

**REST API**:
```bash
# Query via REST API
curl -X POST http://localhost:8000/api/v1/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query_text": "authentication", "limit": 10}'
```

**MCP Interface** (Claude Desktop):
- See [CIDX MCP Bridge](../README.md#cidx-mcp-bridge-for-claude-desktop)
- Connects Claude to CIDX server
- Semantic search in conversations

### Use Cases

**✓ Best For**:
- Team collaboration (10+ developers)
- Centralized code search
- Large codebases (100K+ files)
- Shared indexing infrastructure
- Remote access

**✗ Not Ideal For**:
- Individual developers (overhead)
- Offline work (requires network)
- Simple projects (CLI/Daemon sufficient)

### Performance

| Scenario | Performance | Notes |
|----------|-------------|-------|
| **First query (cold)** | ~277ms | OS page cache benefit |
| **Repeated queries (warm)** | <1ms | 100-1800x speedup |
| **Cache hit ratio** | >95% | Typical production |
| **Multi-user** | Shared cache | All users benefit |

## Switching Between Modes

### CLI → Daemon

```bash
# Enable daemon
cidx config --daemon

# Start daemon
cidx start

# Verify
cidx status
```

**Impact**: Faster queries, watch mode available, daemon process runs in background

### Daemon → CLI

```bash
# Disable daemon
cidx config --no-daemon

# Stop daemon
cidx stop

# Verify
cidx status
```

**Impact**: Slower queries, no watch mode, no background process

### Local (CLI/Daemon) → Server

**Migration**:
1. Install CIDX server
2. Add local repos as golden repositories
3. Configure client to use server API
4. Remove local `.code-indexer/` (optional)

**Benefits**: Team access, shared cache, centralized management

### Server → Local (CLI/Daemon)

**Migration**:
1. Clone repositories locally
2. Run `cidx index` on each repo
3. Use CLI or daemon mode

**Benefits**: Offline access, no network dependency

## Performance Characteristics

### Query Speed Comparison

| Mode | Cold Query | Warm Query | Notes |
|------|------------|------------|-------|
| **CLI** | ~1s | ~1s | No caching |
| **Daemon** | ~1s | ~5ms | In-memory cache |
| **Server** | ~277ms | <1ms | Advanced HNSW cache |

### Resource Usage

| Mode | RAM | CPU | Disk | Network |
|------|-----|-----|------|---------|
| **CLI** | Minimal | Low | Per-query I/O | None |
| **Daemon** | Moderate | Low | Minimal | Unix socket |
| **Server** | High | Moderate | Minimal | HTTP/HTTPS |

### Indexing Performance

| Mode | Indexing Location | Speed |
|------|-------------------|-------|
| **CLI** | Local | Standard |
| **Daemon** | Local | Standard |
| **Server** | Server-side | Standard (but indexed once) |

**Note**: Indexing speed is the same across all modes. Performance differences are in query execution.

## Troubleshooting

### Daemon Won't Start

**Check**:
```bash
# Verify daemon status
cidx status

# Check for stale PID file
ls -la .code-indexer/daemon.pid

# Remove stale PID if needed
rm .code-indexer/daemon.pid

# Restart
cidx start
```

### Daemon Queries Still Slow

**Possible Causes**:
1. Cache not warmed up (first query)
2. Daemon not actually running
3. Querying different repository

**Solutions**:
```bash
# Verify daemon is running
cidx status

# Warm cache with a query
cidx query "test" --limit 1

# Subsequent queries should be fast
cidx query "test" --limit 10  # Should be ~5ms
```

### Server Cache Not Working

**Check**:
```bash
# Query cache stats
curl http://localhost:8000/cache/stats

# Check TTL configuration
echo $CIDX_INDEX_CACHE_TTL_MINUTES

# Verify cache hits increasing
# (hit ratio should be >90% after warmup)
```

### Watch Mode Not Detecting Changes

**Solutions**:
```bash
# Stop and restart watch mode
cidx watch-stop
cidx watch

# Check debounce delay (increase if too sensitive)
cidx watch --debounce 3.0

# Verify daemon is running
cidx status
```

### Unix Socket Permission Denied

**Check**:
```bash
# Verify socket exists
ls -la .code-indexer/daemon.sock

# Check permissions
# Should be readable/writable by user

# Fix if needed
chmod 600 .code-indexer/daemon.sock
```

---

## Next Steps

- **Installation**: [Installation Guide](installation.md)
- **Query Guide**: [Query Guide](query-guide.md)
- **Server Deployment**: [Server Deployment Guide](server-deployment.md)
- **Main Documentation**: [README](../README.md)

---

## Related Documentation

- **Architecture**: [Architecture Guide](architecture.md)
- **SCIP**: [SCIP Code Intelligence](scip/README.md)
- **Configuration**: [Configuration Guide](configuration.md)
