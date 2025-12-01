# FTS (Tantivy) Index Cache Architecture Plan

## Executive Summary

This document presents a comprehensive architectural plan for implementing FTS (Tantivy) index caching in the CIDX server, following the established patterns from Story #526's HNSW cache implementation. The goal is to eliminate the `self._index.reload()` overhead currently incurred on every FTS search operation.

### Current Performance Problem

In `TantivyIndexManager.search()` (line 476), the Tantivy index is reloaded on EVERY search:

```python
# Line 476-477 in tantivy_index_manager.py
self._index.reload()
searcher = self._index.searcher()
```

While Tantivy uses mmap-based architecture (which is inherently more efficient than hnswlib's RAM loading), the `reload()` call still involves:
1. Filesystem stat() operations to check for index changes
2. Internal metadata parsing and validation
3. Potential segment file reopening
4. Searcher object instantiation

### Expected Performance Improvement

Based on the HNSW cache results (1821x speedup from 277ms to 0.15ms), we expect more modest but significant improvements for FTS:
- **Estimated baseline**: 5-50ms per reload() + searcher() call
- **Estimated cached**: <1ms (reuse existing searcher)
- **Expected speedup**: 5-50x improvement

The improvement is lower than HNSW because:
1. Tantivy uses mmap (OS-level caching already helps)
2. HNSW loads entire index into RAM (no mmap)
3. However, eliminating reload() and searcher creation still provides measurable gains

---

## Architecture Analysis

### HNSW Cache Pattern (Reference Implementation)

**File: `/src/code_indexer/server/cache/hnsw_index_cache.py`**
- `HNSWIndexCacheConfig`: Configuration with TTL, cleanup interval, max size
- `HNSWIndexCacheEntry`: Cached entry with hnsw_index, id_mapping, access tracking
- `HNSWIndexCache`: Thread-safe cache with get_or_load(), invalidate(), clear()

**File: `/src/code_indexer/server/cache/__init__.py`**
- `get_global_cache()`: Singleton pattern for server-wide cache instance
- `reset_global_cache()`: Testing utility

**File: `/src/code_indexer/server/app.py`** (lines 1452-1461)
```python
# Story #526: Initialize server-side HNSW cache at bootstrap
from .cache import get_global_cache
_server_hnsw_cache = get_global_cache()
```

**Key Pattern Characteristics**:
1. Module-level singleton initialization at server bootstrap
2. Cache passed down through BackendFactory -> FilesystemBackend -> FilesystemVectorStore
3. `get_or_load(cache_key, loader_function)` pattern for lazy loading
4. TTL-based eviction with access-based refresh
5. Per-repository cache isolation using repo_path as cache key
6. Thread-safe operations with RLock
7. Background cleanup thread for expired entries

### Current FTS Integration Points

**FTS is instantiated in multiple locations**:

1. **`/src/code_indexer/server/app.py`** (lines 4217-4221)
   ```python
   tantivy_manager = TantivyIndexManager(
       repo_path / ".code-indexer" / "tantivy_index"
   )
   tantivy_manager.initialize_index(create_new=False)
   ```
   - New TantivyIndexManager created per FTS search request
   - No caching - full initialization each time

2. **CLI mode**: Various places create TantivyIndexManager for local searches

### What Tantivy Objects Need Caching?

**Analysis of `TantivyIndexManager`**:

```python
class TantivyIndexManager:
    def __init__(self, index_dir: Path):
        self._index = None          # tantivy.Index - THE CACHEABLE OBJECT
        self._schema = None         # Schema - lightweight, reusable
        self._writer = None         # IndexWriter - FOR WRITE OPERATIONS ONLY
        self._heap_size = 1_000_000_000
        self._lock = threading.Lock()
```

**Objects to cache**:
1. `tantivy.Index` - Primary cacheable object (mmap handle to index files)
2. `tantivy.Searcher` - Obtained from `self._index.searcher()` - short-lived, can be recreated

**Objects NOT to cache**:
1. `IndexWriter` - Only needed for indexing operations, not searches
2. `Schema` - Lightweight, can be recreated quickly

### Tantivy vs hnswlib Architecture Differences

| Aspect | hnswlib | Tantivy |
|--------|---------|---------|
| Memory Model | Full RAM loading | mmap-based |
| Load Time | 277ms (100K vectors) | ~5-50ms (mmap overhead) |
| Index Handle | `hnswlib.Index` | `tantivy.Index` |
| Search Object | Built-in | `tantivy.Searcher` |
| Thread Safety | Not thread-safe | Thread-safe (Rust Arc<Mutex>) |
| Reload | N/A (reload whole file) | `index.reload()` + `searcher()` |

**Key Implication**: Tantivy's mmap architecture means the OS already provides some caching. However, eliminating `reload()` and `searcher()` creation still provides measurable benefits.

---

## Technical Design

### Cache Structure Decision

**Option A: Extend existing HNSW cache** (NOT RECOMMENDED)
- Pros: Reuse existing code
- Cons: Mixes different index types, complicates cache keys, different object lifecycles

**Option B: Create FTS-specific cache** (RECOMMENDED)
- Pros: Clean separation, optimized for Tantivy semantics, independent configuration
- Cons: Some code duplication (mitigated by similar patterns)

**Decision**: Create separate `fts_index_cache.py` following same patterns as `hnsw_index_cache.py`.

### What to Cache

**Cache Entry Contents**:
```python
@dataclass
class FTSIndexCacheEntry:
    tantivy_index: Any          # tantivy.Index (mmap handle)
    schema: Any                 # tantivy.Schema (reusable)
    index_dir: str              # Path to index directory
    ttl_minutes: float
    created_at: datetime
    last_accessed: datetime
    access_count: int
```

**NOT caching IndexWriter**:
- Writers are heavyweight (1GB heap allocation)
- Writers are for indexing, not searching
- Would require complex lifecycle management
- Server mode doesn't do indexing (read-only queries)

**NOT caching Searcher**:
- Searchers should be recreated after `reload()` to see new data
- Very lightweight to create from existing Index
- May become stale if index is modified

### Cache Key Strategy

**Cache Key**: `str(index_dir.resolve())`

This matches HNSW cache pattern and ensures:
1. Unique per repository/collection
2. Normalized path for consistency
3. Works across different server request contexts

### Cache Invalidation Strategy

**Invalidation Triggers**:
1. **TTL expiration**: Same as HNSW (10 minutes default)
2. **Manual invalidation**: When index is rebuilt
3. **Startup**: Fresh cache on server restart

**Index Staleness Detection**:
Unlike HNSW (which tracks `index_rebuild_uuid`), Tantivy uses mmap and can detect index changes via `reload()`. However, to maximize performance, we:
1. Cache the Index object between requests
2. Call `reload()` only when returning cached index (not on every search within same request)
3. Allow configurable "reload on access" behavior

### Configuration

**Environment Variables** (following HNSW pattern):
```
CIDX_FTS_CACHE_TTL_MINUTES=10
CIDX_FTS_CACHE_CLEANUP_INTERVAL=60
CIDX_FTS_CACHE_MAX_SIZE_MB=<none>
```

**Config File** (`~/.cidx-server/config.json`):
```json
{
  "fts_cache_ttl_minutes": 10,
  "fts_cache_cleanup_interval_seconds": 60,
  "fts_cache_max_size_mb": null
}
```

---

## Code Changes Required

### File 1: `/src/code_indexer/server/cache/fts_index_cache.py` (NEW FILE)

**Purpose**: FTS-specific cache implementation following HNSW patterns.

```python
"""
FTS Index Cache for Server-Side Performance Optimization.

Story #XXX: Server-Side FTS (Tantivy) Index Caching for Query Performance

Provides in-memory caching of tantivy.Index objects with:
- TTL-based eviction (AC2)
- Access-based TTL refresh (AC3)
- Per-repository cache isolation (AC4)
- Thread-safe operations (AC5)
- Configuration externalization (AC6)
- Cache statistics and monitoring (AC7)
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FTSIndexCacheConfig:
    """Configuration for FTS index cache."""

    ttl_minutes: float = 10.0
    cleanup_interval_seconds: int = 60
    max_cache_size_mb: Optional[int] = None
    reload_on_access: bool = True  # Call reload() when returning cached index

    def __post_init__(self):
        """Validate configuration values."""
        if self.ttl_minutes <= 0:
            raise ValueError(f"TTL must be positive, got {self.ttl_minutes}")
        if self.cleanup_interval_seconds <= 0:
            raise ValueError(
                f"Cleanup interval must be positive, got {self.cleanup_interval_seconds}"
            )

    @classmethod
    def from_env(cls) -> "FTSIndexCacheConfig":
        """Create config from environment variables."""
        ttl_minutes = float(os.environ.get("CIDX_FTS_CACHE_TTL_MINUTES", "10"))
        cleanup_interval = int(
            os.environ.get("CIDX_FTS_CACHE_CLEANUP_INTERVAL", "60")
        )
        max_size_mb_str = os.environ.get("CIDX_FTS_CACHE_MAX_SIZE_MB")
        max_size_mb = int(max_size_mb_str) if max_size_mb_str else None
        reload_on_access = os.environ.get(
            "CIDX_FTS_CACHE_RELOAD_ON_ACCESS", "true"
        ).lower() == "true"

        return cls(
            ttl_minutes=ttl_minutes,
            cleanup_interval_seconds=cleanup_interval,
            max_cache_size_mb=max_size_mb,
            reload_on_access=reload_on_access,
        )

    @classmethod
    def from_file(cls, config_file_path: str) -> "FTSIndexCacheConfig":
        """Create config from JSON configuration file."""
        config_path = Path(config_file_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file_path}")

        with open(config_path) as f:
            config_data = json.load(f)

        return cls(
            ttl_minutes=config_data.get("fts_cache_ttl_minutes", 10.0),
            cleanup_interval_seconds=config_data.get(
                "fts_cache_cleanup_interval_seconds", 60
            ),
            max_cache_size_mb=config_data.get("fts_cache_max_size_mb"),
            reload_on_access=config_data.get("fts_cache_reload_on_access", True),
        )


@dataclass
class FTSIndexCacheEntry:
    """Cache entry for a single repository's FTS index."""

    tantivy_index: Any  # tantivy.Index instance
    schema: Any         # tantivy.Schema instance
    index_dir: str
    ttl_minutes: float

    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0

    def record_access(self) -> None:
        """Record access and refresh TTL."""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def is_expired(self) -> bool:
        """Check if cache entry has exceeded TTL."""
        ttl_delta = timedelta(minutes=self.ttl_minutes)
        expiration_time = self.last_accessed + ttl_delta
        return datetime.now() > expiration_time

    def ttl_remaining_seconds(self) -> float:
        """Calculate remaining TTL in seconds."""
        ttl_delta = timedelta(minutes=self.ttl_minutes)
        expiration_time = self.last_accessed + ttl_delta
        remaining = (expiration_time - datetime.now()).total_seconds()
        return remaining


@dataclass
class FTSIndexCacheStats:
    """Cache statistics for monitoring."""

    cached_repositories: int
    total_memory_mb: float
    hit_count: int
    miss_count: int
    eviction_count: int
    reload_count: int  # FTS-specific: tracks reload() calls
    per_repository_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class FTSIndexCache:
    """Thread-safe in-memory cache for FTS indexes."""

    def __init__(self, config: Optional[FTSIndexCacheConfig] = None):
        """Initialize FTS index cache."""
        self.config = config or FTSIndexCacheConfig()

        self._cache: Dict[str, FTSIndexCacheEntry] = {}
        self._cache_lock = RLock()

        # Statistics tracking
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0
        self._reload_count = 0

        # Background cleanup thread
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()

        logger.info(
            f"FTS Index Cache initialized with TTL={self.config.ttl_minutes} minutes"
        )

    def get_or_load(
        self,
        index_dir: str,
        loader: Callable[[], Tuple[Any, Any]],
    ) -> Tuple[Any, Any]:
        """
        Get cached FTS index or load if not cached.

        Args:
            index_dir: FTS index directory path (cache key)
            loader: Function to load index if not cached
                    Returns (tantivy_index, schema)

        Returns:
            Tuple of (tantivy_index, schema)
        """
        index_dir = str(Path(index_dir).resolve())

        with self._cache_lock:
            if index_dir in self._cache:
                entry = self._cache[index_dir]

                if entry.is_expired():
                    logger.debug(f"FTS cache entry expired for {index_dir}, reloading")
                    del self._cache[index_dir]
                    self._eviction_count += 1
                else:
                    # Cache hit
                    entry.record_access()
                    self._hit_count += 1

                    # Optionally reload to pick up index changes
                    if self.config.reload_on_access:
                        try:
                            entry.tantivy_index.reload()
                            self._reload_count += 1
                        except Exception as e:
                            logger.warning(f"FTS index reload failed: {e}")

                    logger.debug(
                        f"FTS Cache HIT for {index_dir} (access_count={entry.access_count})"
                    )
                    return entry.tantivy_index, entry.schema

            # Cache miss - load index
            self._miss_count += 1
            logger.debug(f"FTS Cache MISS for {index_dir}, loading index")

            tantivy_index, schema = loader()

            entry = FTSIndexCacheEntry(
                tantivy_index=tantivy_index,
                schema=schema,
                index_dir=index_dir,
                ttl_minutes=self.config.ttl_minutes,
            )
            entry.record_access()

            self._cache[index_dir] = entry
            logger.info(f"Cached FTS index for {index_dir}")

            return tantivy_index, schema

    def invalidate(self, index_dir: str) -> None:
        """Invalidate cache entry for specific repository."""
        index_dir = str(Path(index_dir).resolve())

        with self._cache_lock:
            if index_dir in self._cache:
                del self._cache[index_dir]
                self._eviction_count += 1
                logger.info(f"Invalidated FTS cache for {index_dir}")

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._cache_lock:
            evicted = len(self._cache)
            self._cache.clear()
            self._eviction_count += evicted
            logger.info(f"Cleared FTS cache ({evicted} entries)")

    def _cleanup_expired_entries(self) -> None:
        """Clean up expired cache entries."""
        with self._cache_lock:
            expired_dirs = [
                index_dir
                for index_dir, entry in self._cache.items()
                if entry.is_expired()
            ]

            for index_dir in expired_dirs:
                del self._cache[index_dir]
                self._eviction_count += 1
                logger.debug(f"Evicted expired FTS cache entry: {index_dir}")

            if expired_dirs:
                logger.info(f"Evicted {len(expired_dirs)} expired FTS cache entries")

    def start_background_cleanup(self) -> None:
        """Start background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("FTS background cleanup thread already running")
            return

        self._cleanup_stop_event.clear()

        def cleanup_loop():
            while not self._cleanup_stop_event.is_set():
                try:
                    self._cleanup_expired_entries()
                except Exception as e:
                    logger.error(f"Error in FTS background cleanup: {e}")

                self._cleanup_stop_event.wait(
                    timeout=self.config.cleanup_interval_seconds
                )

        self._cleanup_thread = threading.Thread(
            target=cleanup_loop, name="FTSIndexCacheCleanup", daemon=True
        )
        self._cleanup_thread.start()
        logger.info("Started FTS background cache cleanup thread")

    def stop_background_cleanup(self) -> None:
        """Stop background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=5)
            logger.info("Stopped FTS background cache cleanup thread")

    def get_stats(self) -> FTSIndexCacheStats:
        """Get cache statistics."""
        with self._cache_lock:
            # Rough memory estimate (mmap doesn't consume RAM directly)
            total_memory_mb = len(self._cache) * 10  # Placeholder

            per_repo_stats = {}
            for index_dir, entry in self._cache.items():
                per_repo_stats[index_dir] = {
                    "access_count": entry.access_count,
                    "last_accessed": entry.last_accessed.isoformat(),
                    "created_at": entry.created_at.isoformat(),
                    "ttl_remaining_seconds": entry.ttl_remaining_seconds(),
                }

            return FTSIndexCacheStats(
                cached_repositories=len(self._cache),
                total_memory_mb=total_memory_mb,
                hit_count=self._hit_count,
                miss_count=self._miss_count,
                eviction_count=self._eviction_count,
                reload_count=self._reload_count,
                per_repository_stats=per_repo_stats,
            )
```

### File 2: `/src/code_indexer/server/cache/__init__.py` (MODIFY)

**Changes**: Add FTS cache exports and singleton pattern.

```python
# Add after existing HNSW exports:

from .fts_index_cache import (
    FTSIndexCache,
    FTSIndexCacheConfig,
    FTSIndexCacheEntry,
    FTSIndexCacheStats,
)

# FTS server-wide singleton cache instance
_global_fts_cache_instance = None


def get_global_fts_cache() -> FTSIndexCache:
    """
    Get or create the global FTS index cache instance.

    This is a singleton pattern - one cache instance shared across
    all server components.
    """
    global _global_fts_cache_instance

    if _global_fts_cache_instance is None:
        from pathlib import Path
        import logging

        logger = logging.getLogger(__name__)
        config_file = Path.home() / ".cidx-server" / "config.json"

        if config_file.exists():
            try:
                config = FTSIndexCacheConfig.from_file(str(config_file))
                logger.info(
                    f"Loaded FTS cache config from {config_file}: TTL={config.ttl_minutes}min"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load FTS cache config from {config_file}: {e}. Using defaults."
                )
                config = FTSIndexCacheConfig.from_env()
        else:
            config = FTSIndexCacheConfig.from_env()
            logger.info(
                f"Initialized FTS cache with env/default config: TTL={config.ttl_minutes}min"
            )

        _global_fts_cache_instance = FTSIndexCache(config=config)
        _global_fts_cache_instance.start_background_cleanup()

    return _global_fts_cache_instance


def reset_global_fts_cache() -> None:
    """Reset the global FTS cache instance (for testing purposes)."""
    global _global_fts_cache_instance

    if _global_fts_cache_instance is not None:
        _global_fts_cache_instance.stop_background_cleanup()
        _global_fts_cache_instance = None


# Update __all__
__all__ = [
    # HNSW cache exports (existing)
    "HNSWIndexCache",
    "HNSWIndexCacheConfig",
    "HNSWIndexCacheEntry",
    "HNSWIndexCacheStats",
    "get_global_cache",
    "reset_global_cache",
    # FTS cache exports (new)
    "FTSIndexCache",
    "FTSIndexCacheConfig",
    "FTSIndexCacheEntry",
    "FTSIndexCacheStats",
    "get_global_fts_cache",
    "reset_global_fts_cache",
]
```

### File 3: `/src/code_indexer/server/app.py` (MODIFY)

**Changes**: Add FTS cache initialization at bootstrap.

**Location**: After line 1461 (after HNSW cache initialization)

```python
# Add module-level variable (after line 1126):
_server_fts_cache: Optional[Any] = None

# Add in configure_app() function (after HNSW cache init around line 1461):
# Story #XXX: Initialize server-side FTS cache at bootstrap
from .cache import get_global_fts_cache

_server_fts_cache = get_global_fts_cache()
logger.info(
    f"FTS index cache initialized (TTL: {_server_fts_cache.config.ttl_minutes}min)"
)
```

**Location**: Modify FTS search code (lines 4217-4221)

**Current code**:
```python
tantivy_manager = TantivyIndexManager(
    repo_path / ".code-indexer" / "tantivy_index"
)
tantivy_manager.initialize_index(create_new=False)
```

**New code**:
```python
# Story #XXX: Use cached FTS index for performance
from ..services.tantivy_index_manager import TantivyIndexManager

fts_index_dir = repo_path / ".code-indexer" / "tantivy_index"

def fts_loader():
    """Loader function for FTS cache miss."""
    manager = TantivyIndexManager(fts_index_dir)
    manager.initialize_index(create_new=False)
    return manager._index, manager._schema

# Get or load from cache
tantivy_index, schema = _server_fts_cache.get_or_load(
    str(fts_index_dir), fts_loader
)

# Create a lightweight TantivyIndexManager wrapper with cached index
tantivy_manager = TantivyIndexManager(fts_index_dir)
tantivy_manager._index = tantivy_index
tantivy_manager._schema = schema
# Note: No writer needed for search operations
```

### File 4: `/src/code_indexer/services/tantivy_index_manager.py` (MODIFY)

**Changes**: Add method to allow external cache to inject index/schema.

**Add new method** (after `close()` method around line 1137):

```python
def set_cached_index(self, index: Any, schema: Any) -> None:
    """
    Set index and schema from external cache.

    Used by server-side caching to inject pre-loaded index
    without re-initializing from disk.

    Args:
        index: tantivy.Index instance from cache
        schema: tantivy.Schema instance from cache

    Note: Writer is NOT set - this is for read-only search operations only.
    """
    self._index = index
    self._schema = schema
    logger.debug(f"Set cached FTS index for {self.index_dir}")

def get_index_for_caching(self) -> Tuple[Any, Any]:
    """
    Get index and schema for external caching.

    Returns:
        Tuple of (tantivy_index, schema) for caching

    Raises:
        RuntimeError: If index is not initialized
    """
    if self._index is None:
        raise RuntimeError("Index not initialized. Call initialize_index() first.")

    return self._index, self._schema
```

### File 5: Add Cache Statistics Endpoint (OPTIONAL)

**Location**: `/src/code_indexer/server/app.py`

Add endpoint to monitor FTS cache alongside HNSW cache:

```python
@app.get(
    "/api/cache/fts/stats",
    response_model=Dict[str, Any],
    summary="Get FTS cache statistics",
    tags=["monitoring"],
)
async def get_fts_cache_stats(
    current_user: User = Depends(get_current_user),
):
    """Get FTS index cache statistics."""
    try:
        from .cache import get_global_fts_cache

        cache = get_global_fts_cache()
        stats = cache.get_stats()

        return {
            "cached_repositories": stats.cached_repositories,
            "total_memory_mb": stats.total_memory_mb,
            "hit_count": stats.hit_count,
            "miss_count": stats.miss_count,
            "eviction_count": stats.eviction_count,
            "reload_count": stats.reload_count,
            "hit_ratio": stats.hit_ratio,
            "per_repository_stats": stats.per_repository_stats,
        }
    except Exception as e:
        logger.error(f"Failed to get FTS cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get FTS cache stats: {str(e)}",
        )
```

---

## ASCII Architecture Diagram

```
+------------------+     +------------------+     +------------------+
|   REST/MCP API   |     |   REST/MCP API   |     |   REST/MCP API   |
|   (search req)   |     |   (search req)   |     |   (search req)   |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         v                        v                        v
+------------------------------------------------------------------------+
|                         app.py (Server)                                |
|                                                                        |
|  +---------------------------+    +---------------------------+        |
|  | _server_hnsw_cache        |    | _server_fts_cache          |        |
|  | (module-level singleton)  |    | (module-level singleton)   |        |
|  +---------------------------+    +---------------------------+        |
|                                                                        |
+------------------------------------------------------------------------+
         |                                      |
         | get_or_load(repo_path, loader)       | get_or_load(index_dir, loader)
         v                                      v
+---------------------------+          +---------------------------+
|    HNSWIndexCache         |          |    FTSIndexCache          |
|                           |          |                           |
| +-----------------------+ |          | +-----------------------+ |
| | Cache Entries         | |          | | Cache Entries         | |
| | /repo1 -> HNSWEntry   | |          | | /repo1/fts -> FTSEntry| |
| | /repo2 -> HNSWEntry   | |          | | /repo2/fts -> FTSEntry| |
| +-----------------------+ |          | +-----------------------+ |
|                           |          |                           |
| - RLock (thread safety)   |          | - RLock (thread safety)   |
| - TTL eviction            |          | - TTL eviction            |
| - Background cleanup      |          | - Background cleanup      |
| - Statistics tracking     |          | - Statistics tracking     |
+---------------------------+          +---------------------------+
         |                                      |
         | Cache HIT: return cached index       | Cache HIT: return cached index + reload()
         | Cache MISS: call loader()            | Cache MISS: call loader()
         v                                      v
+---------------------------+          +---------------------------+
| FilesystemVectorStore     |          | TantivyIndexManager       |
| (uses cached hnsw_index)  |          | (uses cached tantivy_idx) |
+---------------------------+          +---------------------------+
         |                                      |
         v                                      v
+---------------------------+          +---------------------------+
| .code-indexer/index/      |          | .code-indexer/tantivy_idx/|
| - hnsw.bin (mmap)         |          | - meta.json (mmap)        |
| - id_index.json           |          | - *.segment (mmap)        |
+---------------------------+          +---------------------------+
```

---

## Risks and Considerations

### 1. Tantivy vs hnswlib Architectural Differences

**Risk**: Tantivy uses mmap, which means OS already provides caching. Benefits may be lower than expected.

**Mitigation**:
- Add performance telemetry to measure actual improvement
- The `reload()` + `searcher()` creation overhead is still eliminated
- Expected 5-50x improvement (not 1800x like HNSW)

### 2. Index Staleness After Rebuild

**Risk**: Cached index may not reflect newly indexed documents.

**Mitigation**:
- `reload_on_access` config option (default: true) calls `index.reload()` on cache hit
- This ensures fresh searcher sees latest committed segments
- TTL eviction ensures maximum staleness window

### 3. Memory Usage

**Risk**: Holding multiple tantivy.Index handles may consume file descriptors.

**Mitigation**:
- Tantivy uses mmap (no RAM duplication)
- TTL-based eviction prevents unbounded growth
- Monitor file descriptor usage in production

### 4. Thread Safety

**Risk**: Multiple threads accessing same cached index.

**Mitigation**:
- `tantivy.Index` and `tantivy.Searcher` are thread-safe (Rust Arc<Mutex>)
- `FTSIndexCache` uses RLock for cache operations
- TantivyIndexManager has its own `threading.Lock` for writer operations

### 5. Backwards Compatibility

**Risk**: Changes may break existing FTS functionality.

**Mitigation**:
- Cache is opt-in (only used in server mode via `_server_fts_cache`)
- CLI mode unaffected (no cache passed)
- Existing TantivyIndexManager API unchanged
- New `set_cached_index()` method is additive

---

## Testing Strategy

### Unit Tests

**File: `/tests/server/test_fts_index_cache.py`** (NEW)

Following patterns from `test_hnsw_index_cache.py`:

1. **Configuration tests**:
   - `test_default_config_values()`
   - `test_config_from_dict()`
   - `test_config_validation_negative_ttl()`
   - `test_config_from_env_variable()`
   - `test_config_from_file()`

2. **Cache entry tests**:
   - `test_cache_entry_creation()`
   - `test_cache_entry_access_updates_timestamp()`
   - `test_cache_entry_is_expired_false_when_fresh()`
   - `test_cache_entry_is_expired_true_when_stale()`
   - `test_cache_entry_access_extends_ttl()`

3. **Cache behavior tests**:
   - `test_cache_initialization()`
   - `test_cache_get_or_load_new_index()`
   - `test_cache_get_or_load_cached_index()`
   - `test_cache_per_repository_isolation()`
   - `test_cache_eviction_after_ttl()`
   - `test_cache_access_refreshes_ttl_prevents_eviction()`
   - `test_cache_thread_safety_concurrent_loads()`
   - `test_cache_thread_safety_concurrent_access()`
   - `test_cache_stats_empty_cache()`
   - `test_cache_stats_with_entries()`
   - `test_cache_background_cleanup_evicts_expired()`
   - `test_cache_reload_on_access_behavior()`

### Integration Tests

**File: `/tests/server/test_fts_cache_integration_e2e.py`** (NEW)

1. **End-to-end FTS cache flow**:
   - `test_fts_cache_integration_with_real_index()`
   - `test_fts_cache_stats_endpoint()`
   - `test_fts_cache_survives_multiple_requests()`

### Performance Tests

**File: `/tests/e2e/server/test_fts_cache_performance.py`** (NEW)

1. **Baseline measurement**:
   - `test_fts_reload_overhead_without_cache()`
   - Measure time for `initialize_index()` + `reload()` + `searcher()`

2. **Cached performance**:
   - `test_fts_cached_search_performance()`
   - Measure time with cache hit (should be <1ms)

3. **Speedup calculation**:
   - `test_fts_cache_speedup_ratio()`
   - Calculate and log actual speedup achieved

---

## Implementation Sequence (TDD Workflow)

### Step 1: Create FTS Cache Config and Entry (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/server/cache/fts_index_cache.py` (NEW)
- `/tests/server/test_fts_index_cache.py` (NEW)

**Tests to write first**:
1. `test_default_config_values()`
2. `test_config_validation_negative_ttl()`
3. `test_cache_entry_creation()`
4. `test_cache_entry_is_expired_false_when_fresh()`
5. `test_cache_entry_is_expired_true_when_stale()`

**Implementation**:
- Create `FTSIndexCacheConfig` dataclass
- Create `FTSIndexCacheEntry` dataclass with TTL logic

### Step 2: Create FTS Cache Core Logic (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/server/cache/fts_index_cache.py`
- `/tests/server/test_fts_index_cache.py`

**Tests to write first**:
1. `test_cache_initialization()`
2. `test_cache_get_or_load_new_index()`
3. `test_cache_get_or_load_cached_index()`
4. `test_cache_per_repository_isolation()`
5. `test_cache_eviction_after_ttl()`

**Implementation**:
- Create `FTSIndexCache` class with `get_or_load()`, `invalidate()`, `clear()`
- Add RLock for thread safety
- Add statistics tracking

### Step 3: Add Background Cleanup and Statistics (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/server/cache/fts_index_cache.py`
- `/tests/server/test_fts_index_cache.py`

**Tests to write first**:
1. `test_cache_background_cleanup_starts()`
2. `test_cache_background_cleanup_evicts_expired()`
3. `test_cache_stats_empty_cache()`
4. `test_cache_stats_with_entries()`

**Implementation**:
- Add background cleanup thread
- Add `FTSIndexCacheStats` dataclass
- Add `get_stats()` method

### Step 4: Add Thread Safety Tests (RED-GREEN-REFACTOR)

**Files affected**:
- `/tests/server/test_fts_index_cache.py`

**Tests to write first**:
1. `test_cache_thread_safety_concurrent_loads()`
2. `test_cache_thread_safety_concurrent_access()`

**Implementation**:
- Verify existing RLock implementation
- Fix any race conditions found

### Step 5: Add Global Cache Singleton (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/server/cache/__init__.py`
- `/tests/server/test_fts_index_cache.py`

**Tests to write first**:
1. `test_get_global_fts_cache_returns_singleton()`
2. `test_reset_global_fts_cache()`

**Implementation**:
- Add `get_global_fts_cache()` function
- Add `reset_global_fts_cache()` for testing
- Update `__all__` exports

### Step 6: Integrate with Server App (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/server/app.py`
- `/tests/server/test_fts_cache_integration_e2e.py` (NEW)

**Tests to write first**:
1. `test_server_initializes_fts_cache()`
2. `test_fts_search_uses_cache()`
3. `test_fts_cache_stats_endpoint()`

**Implementation**:
- Add `_server_fts_cache` module variable
- Initialize in `configure_app()`
- Modify FTS search code to use cache
- Add stats endpoint

### Step 7: Add TantivyIndexManager Cache Support (RED-GREEN-REFACTOR)

**Files affected**:
- `/src/code_indexer/services/tantivy_index_manager.py`
- `/tests/services/test_tantivy_index_manager.py`

**Tests to write first**:
1. `test_set_cached_index()`
2. `test_get_index_for_caching()`

**Implementation**:
- Add `set_cached_index()` method
- Add `get_index_for_caching()` method

### Step 8: Performance Validation (RED-GREEN-REFACTOR)

**Files affected**:
- `/tests/e2e/server/test_fts_cache_performance.py` (NEW)

**Tests to write first**:
1. `test_fts_reload_overhead_without_cache()`
2. `test_fts_cached_search_performance()`
3. `test_fts_cache_speedup_ratio()`

**Implementation**:
- Measure baseline performance
- Measure cached performance
- Validate speedup meets expectations (5-50x)

### Step 9: Documentation and Cleanup

**Files affected**:
- Update CLAUDE.md with FTS cache documentation
- Update README if needed
- Clean up any TODO comments

---

## Summary

This architectural plan provides a comprehensive blueprint for implementing FTS (Tantivy) index caching in the CIDX server. The design:

1. **Follows established patterns** from Story #526's HNSW cache implementation
2. **Maintains separation of concerns** with dedicated FTS cache module
3. **Provides thread-safe, TTL-based caching** with access-based refresh
4. **Accounts for Tantivy's mmap architecture** with `reload_on_access` option
5. **Includes comprehensive testing strategy** following TDD methodology
6. **Provides step-by-step implementation sequence** for incremental delivery

Expected outcome: 5-50x performance improvement for repeated FTS queries in server mode, with no impact on CLI mode or backwards compatibility.
