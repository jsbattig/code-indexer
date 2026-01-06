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
- reload_on_access option for fresh data (AC8)

Performance improvement: Eliminates reload() overhead on every search.
Expected speedup: 5-50x for repeated FTS queries.
"""

from code_indexer.server.middleware.correlation import get_correlation_id
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FTSIndexCacheConfig:
    """
    Configuration for FTS index cache (AC6: Configuration Externalization).

    Supports configuration from:
    - Constructor arguments (programmatic)
    - Environment variables (CIDX_FTS_CACHE_TTL_MINUTES)
    - Config file (~/.cidx-server/config.json)
    """

    ttl_minutes: float = 10.0
    cleanup_interval_seconds: int = 60
    max_cache_size_mb: Optional[int] = None  # No limit by default
    reload_on_access: bool = True  # Call reload() on cache hit for fresh data

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
        """
        Create config from environment variables.

        Supported environment variables:
        - CIDX_FTS_CACHE_TTL_MINUTES: TTL in minutes (default: 10)
        - CIDX_FTS_CACHE_CLEANUP_INTERVAL: Cleanup interval in seconds (default: 60)
        - CIDX_FTS_CACHE_MAX_SIZE_MB: Maximum cache size in MB (default: None)
        - CIDX_FTS_CACHE_RELOAD_ON_ACCESS: Whether to reload on cache hit (default: true)

        Returns:
            FTSIndexCacheConfig instance
        """
        ttl_minutes = float(os.environ.get("CIDX_FTS_CACHE_TTL_MINUTES", "10"))
        cleanup_interval = int(os.environ.get("CIDX_FTS_CACHE_CLEANUP_INTERVAL", "60"))
        max_size_mb_str = os.environ.get("CIDX_FTS_CACHE_MAX_SIZE_MB")
        max_size_mb = int(max_size_mb_str) if max_size_mb_str else None
        reload_on_access = (
            os.environ.get("CIDX_FTS_CACHE_RELOAD_ON_ACCESS", "true").lower() == "true"
        )

        return cls(
            ttl_minutes=ttl_minutes,
            cleanup_interval_seconds=cleanup_interval,
            max_cache_size_mb=max_size_mb,
            reload_on_access=reload_on_access,
        )

    @classmethod
    def from_file(cls, config_file_path: str) -> "FTSIndexCacheConfig":
        """
        Create config from JSON configuration file.

        Expected format in config.json:
        {
            "fts_cache_ttl_minutes": 15,
            "fts_cache_cleanup_interval_seconds": 90,
            "fts_cache_max_size_mb": 1024,
            "fts_cache_reload_on_access": true
        }

        Args:
            config_file_path: Path to config.json

        Returns:
            FTSIndexCacheConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is invalid JSON
        """
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
    """
    Cache entry for a single repository's FTS index (AC4: Per-Repository Isolation).

    Tracks:
    - Tantivy index object (tantivy.Index)
    - Schema for the index
    - Access timestamp for TTL refresh (AC3)
    - Access count for statistics (AC7)
    """

    tantivy_index: Any  # tantivy.Index instance
    schema: Any  # tantivy.Schema instance
    index_dir: str
    ttl_minutes: float

    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0

    def record_access(self) -> None:
        """
        Record access to this cache entry (AC3: Access-based TTL refresh).

        Refreshes TTL by updating last_accessed timestamp.
        """
        self.last_accessed = datetime.now()
        self.access_count += 1

    def is_expired(self) -> bool:
        """
        Check if cache entry has exceeded TTL (AC2: TTL-based eviction).

        TTL is calculated from last_accessed time (not created_at),
        implementing access-based TTL refresh (AC3).

        Returns:
            True if expired, False otherwise
        """
        ttl_delta = timedelta(minutes=self.ttl_minutes)
        expiration_time = self.last_accessed + ttl_delta
        return datetime.now() > expiration_time

    def ttl_remaining_seconds(self) -> float:
        """
        Calculate remaining TTL in seconds (AC7: Statistics).

        Returns:
            Remaining TTL in seconds (negative if expired)
        """
        ttl_delta = timedelta(minutes=self.ttl_minutes)
        expiration_time = self.last_accessed + ttl_delta
        remaining = (expiration_time - datetime.now()).total_seconds()
        return remaining


@dataclass
class FTSIndexCacheStats:
    """
    Cache statistics for monitoring (AC7: Cache Statistics).

    Provides visibility into:
    - Cache size and memory usage
    - Hit/miss ratio
    - Reload count (FTS-specific)
    - Per-repository statistics
    """

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
    """
    Thread-safe in-memory cache for FTS (Tantivy) indexes (AC5: Thread-Safe Operations).

    Provides:
    - AC1: Server-side index caching for performance
    - AC2: TTL-based eviction
    - AC3: Access-based TTL refresh
    - AC4: Per-repository cache isolation
    - AC5: Thread-safe operations with proper locking
    - AC6: Configuration externalization
    - AC7: Cache statistics and monitoring
    - AC8: reload_on_access option for fresh data

    Performance improvement: Eliminates reload() + searcher() overhead.
    Expected speedup: 5-50x for repeated FTS queries.
    """

    # Estimated memory size per FTS index entry (in MB)
    ESTIMATED_INDEX_SIZE_MB = 10

    def __init__(self, config: Optional[FTSIndexCacheConfig] = None):
        """
        Initialize FTS index cache.

        Args:
            config: Cache configuration (defaults to standard config if None)
        """
        self.config = config or FTSIndexCacheConfig()

        # Per-repository cache (AC4)
        self._cache: Dict[str, FTSIndexCacheEntry] = {}

        # Thread-safe locking (AC5)
        # Use RLock to allow same thread to acquire lock multiple times
        self._cache_lock = RLock()

        # Statistics tracking (AC7)
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0
        self._reload_count = 0

        # Background cleanup thread (AC2)
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()

        logger.info(
            f"FTS Index Cache initialized with TTL={self.config.ttl_minutes} minutes, "
            f"reload_on_access={self.config.reload_on_access}"
        , extra={"correlation_id": get_correlation_id()})

    def get_or_load(
        self,
        index_dir: str,
        loader: Callable[[], Tuple[Any, Any]],
    ) -> Tuple[Any, Any]:
        """
        Get cached FTS index or load if not cached (AC1: Cache Implementation).

        Implements:
        - AC1: Cache hit returns cached index
        - AC1: Cache miss loads index and caches it
        - AC3: Access refreshes TTL
        - AC5: Thread-safe operations with deduplication
        - AC8: Optional reload() on cache hit

        Args:
            index_dir: FTS index directory path (cache key)
            loader: Function to load index if not cached
                    Returns (tantivy_index, schema)

        Returns:
            Tuple of (tantivy_index, schema)
        """
        # Normalize path for consistent cache keys
        index_dir = str(Path(index_dir).resolve())

        with self._cache_lock:
            # Check if cached
            if index_dir in self._cache:
                entry = self._cache[index_dir]

                # Check if expired (AC2)
                if entry.is_expired():
                    # Evict expired entry
                    logger.debug(f"FTS cache entry expired for {index_dir}, reloading", extra={"correlation_id": get_correlation_id()})
                    del self._cache[index_dir]
                    self._eviction_count += 1
                    # Fall through to load
                else:
                    # Cache hit - refresh TTL (AC3)
                    entry.record_access()
                    self._hit_count += 1

                    # Optionally reload to pick up index changes (AC8)
                    if self.config.reload_on_access:
                        try:
                            entry.tantivy_index.reload()
                            self._reload_count += 1
                        except Exception as e:
                            logger.warning(f"FTS index reload failed: {e}", extra={"correlation_id": get_correlation_id()})

                    logger.debug(
                        f"FTS Cache HIT for {index_dir} (access_count={entry.access_count})"
                    , extra={"correlation_id": get_correlation_id()})
                    return entry.tantivy_index, entry.schema

            # Cache miss - load index (AC1)
            self._miss_count += 1
            logger.debug(f"FTS Cache MISS for {index_dir}, loading index", extra={"correlation_id": get_correlation_id()})

            # Load index (hold lock to prevent duplicate loads)
            tantivy_index, schema = loader()

            # Create cache entry with initial access recorded
            entry = FTSIndexCacheEntry(
                tantivy_index=tantivy_index,
                schema=schema,
                index_dir=index_dir,
                ttl_minutes=self.config.ttl_minutes,
            )

            # Record the initial load as an access
            entry.record_access()

            # Store in cache
            self._cache[index_dir] = entry

            # Enforce size limit (AC3A: Cache size limits)
            # NOTE: Called within _cache_lock, so _enforce_size_limit must not re-acquire lock
            self._enforce_size_limit()

            logger.info(f"Cached FTS index for {index_dir}", extra={"correlation_id": get_correlation_id()})

            return tantivy_index, schema

    def invalidate(self, index_dir: str) -> None:
        """
        Invalidate cache entry for specific repository.

        Args:
            index_dir: Index directory path to invalidate
        """
        index_dir = str(Path(index_dir).resolve())

        with self._cache_lock:
            if index_dir in self._cache:
                del self._cache[index_dir]
                self._eviction_count += 1
                logger.info(f"Invalidated FTS cache for {index_dir}", extra={"correlation_id": get_correlation_id()})

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._cache_lock:
            evicted = len(self._cache)
            self._cache.clear()
            self._eviction_count += evicted
            logger.info(f"Cleared FTS cache ({evicted} entries)", extra={"correlation_id": get_correlation_id()})

    def _enforce_size_limit(self) -> None:
        """
        Enforce cache size limit by evicting LRU entries (AC3A: Cache size limits).

        IMPORTANT: Must be called while holding _cache_lock (does not acquire lock itself).
        Called after adding new entries to ensure cache stays within max_cache_size_mb.
        Evicts oldest (least recently accessed) entries first.
        """
        # Skip if no size limit configured
        if self.config.max_cache_size_mb is None:
            return

        # Calculate current cache size using estimated size per index
        current_size_mb = len(self._cache) * self.ESTIMATED_INDEX_SIZE_MB

        # Evict LRU entries until under limit
        while current_size_mb > self.config.max_cache_size_mb and self._cache:
            # Find least recently accessed entry
            lru_index_dir = min(
                self._cache.keys(),
                key=lambda path: self._cache[path].last_accessed,
            )

            # Evict LRU entry
            del self._cache[lru_index_dir]
            self._eviction_count += 1
            logger.debug(
                f"Evicted LRU FTS cache entry to enforce size limit: {lru_index_dir}"
            , extra={"correlation_id": get_correlation_id()})

            # Recalculate size
            current_size_mb = len(self._cache) * self.ESTIMATED_INDEX_SIZE_MB

        if current_size_mb <= self.config.max_cache_size_mb and self._cache:
            logger.debug(
                f"FTS cache size: {current_size_mb}MB / {self.config.max_cache_size_mb}MB"
            , extra={"correlation_id": get_correlation_id()})

    def _cleanup_expired_entries(self) -> None:
        """
        Clean up expired cache entries (AC2: TTL-based eviction).

        Called by background cleanup thread and manual cleanup.
        """
        with self._cache_lock:
            expired_dirs = [
                index_dir
                for index_dir, entry in self._cache.items()
                if entry.is_expired()
            ]

            for index_dir in expired_dirs:
                del self._cache[index_dir]
                self._eviction_count += 1
                logger.debug(f"Evicted expired FTS cache entry: {index_dir}", extra={"correlation_id": get_correlation_id()})

            if expired_dirs:
                logger.info(f"Evicted {len(expired_dirs)} expired FTS cache entries", extra={"correlation_id": get_correlation_id()})

    def start_background_cleanup(self) -> None:
        """
        Start background cleanup thread (AC2: Automatic eviction).

        Thread periodically checks for expired entries and evicts them.
        """
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("FTS background cleanup thread already running", extra={"correlation_id": get_correlation_id()})
            return

        self._cleanup_stop_event.clear()

        def cleanup_loop():
            """Background cleanup loop."""
            while not self._cleanup_stop_event.is_set():
                try:
                    self._cleanup_expired_entries()
                except Exception as e:
                    logger.error(f"Error in FTS background cleanup: {e}", extra={"correlation_id": get_correlation_id()})

                # Wait for cleanup interval or stop event
                self._cleanup_stop_event.wait(
                    timeout=self.config.cleanup_interval_seconds
                )

        self._cleanup_thread = threading.Thread(
            target=cleanup_loop, name="FTSIndexCacheCleanup", daemon=True
        )
        self._cleanup_thread.start()
        logger.info("Started FTS background cache cleanup thread", extra={"correlation_id": get_correlation_id()})

    def stop_background_cleanup(self) -> None:
        """Stop background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=5)
            logger.info("Stopped FTS background cache cleanup thread", extra={"correlation_id": get_correlation_id()})

    def get_stats(self) -> FTSIndexCacheStats:
        """
        Get cache statistics (AC7: Monitoring).

        Returns:
            FTSIndexCacheStats with current cache metrics
        """
        with self._cache_lock:
            # Calculate total memory usage using estimated size per index
            total_memory_mb = len(self._cache) * self.ESTIMATED_INDEX_SIZE_MB

            # Per-repository stats
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
