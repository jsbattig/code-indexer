"""
HNSW Index Cache for Server-Side Performance Optimization.

Story #526: Server-Side HNSW Index Caching for 1800x Query Performance

Provides in-memory caching of hnswlib.Index objects with:
- TTL-based eviction (AC2)
- Access-based TTL refresh (AC3)
- Per-repository cache isolation (AC4)
- Thread-safe operations (AC5)
- Configuration externalization (AC6)
- Cache statistics and monitoring (AC7)

Performance improvement: ~277ms → <1ms for repeated queries (1800x faster).
"""

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
class HNSWIndexCacheConfig:
    """
    Configuration for HNSW index cache (AC6: Configuration Externalization).

    Supports configuration from:
    - Constructor arguments (programmatic)
    - Environment variables (CIDX_INDEX_CACHE_TTL_MINUTES)
    - Config file (~/.cidx-server/config.json)
    """

    ttl_minutes: float = 10.0
    cleanup_interval_seconds: int = 60
    max_cache_size_mb: Optional[int] = None  # No limit by default

    def __post_init__(self):
        """Validate configuration values."""
        if self.ttl_minutes <= 0:
            raise ValueError(f"TTL must be positive, got {self.ttl_minutes}")

        if self.cleanup_interval_seconds <= 0:
            raise ValueError(
                f"Cleanup interval must be positive, got {self.cleanup_interval_seconds}"
            )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "HNSWIndexCacheConfig":
        """
        Create config from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            HNSWIndexCacheConfig instance
        """
        return cls(
            ttl_minutes=config_dict.get("ttl_minutes", 10.0),
            cleanup_interval_seconds=config_dict.get("cleanup_interval_seconds", 60),
            max_cache_size_mb=config_dict.get("max_cache_size_mb"),
        )

    @classmethod
    def from_env(cls) -> "HNSWIndexCacheConfig":
        """
        Create config from environment variables.

        Supported environment variables:
        - CIDX_INDEX_CACHE_TTL_MINUTES: TTL in minutes (default: 10)
        - CIDX_INDEX_CACHE_CLEANUP_INTERVAL: Cleanup interval in seconds (default: 60)
        - CIDX_INDEX_CACHE_MAX_SIZE_MB: Maximum cache size in MB (default: None)

        Returns:
            HNSWIndexCacheConfig instance
        """
        ttl_minutes = float(os.environ.get("CIDX_INDEX_CACHE_TTL_MINUTES", "10"))
        cleanup_interval = int(
            os.environ.get("CIDX_INDEX_CACHE_CLEANUP_INTERVAL", "60")
        )
        max_size_mb_str = os.environ.get("CIDX_INDEX_CACHE_MAX_SIZE_MB")
        max_size_mb = int(max_size_mb_str) if max_size_mb_str else None

        return cls(
            ttl_minutes=ttl_minutes,
            cleanup_interval_seconds=cleanup_interval,
            max_cache_size_mb=max_size_mb,
        )

    @classmethod
    def from_file(cls, config_file_path: str) -> "HNSWIndexCacheConfig":
        """
        Create config from JSON configuration file.

        Expected format in config.json:
        {
            "index_cache_ttl_minutes": 15,
            "index_cache_cleanup_interval_seconds": 90,
            "index_cache_max_size_mb": 1024
        }

        Args:
            config_file_path: Path to config.json

        Returns:
            HNSWIndexCacheConfig instance

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
            ttl_minutes=config_data.get("index_cache_ttl_minutes", 10.0),
            cleanup_interval_seconds=config_data.get(
                "index_cache_cleanup_interval_seconds", 60
            ),
            max_cache_size_mb=config_data.get("index_cache_max_size_mb"),
        )


@dataclass
class HNSWIndexCacheEntry:
    """
    Cache entry for a single repository's HNSW index (AC4: Per-Repository Isolation).

    Tracks:
    - HNSW index object (hnswlib.Index)
    - ID mapping (label -> vector ID)
    - Access timestamp for TTL refresh (AC3)
    - Access count for statistics (AC7)
    """

    hnsw_index: Any  # hnswlib.Index instance
    id_mapping: Dict[int, str]  # label -> vector ID
    repo_path: str
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
class HNSWIndexCacheStats:
    """
    Cache statistics for monitoring (AC7: Cache Statistics).

    Provides visibility into:
    - Cache size and memory usage
    - Hit/miss ratio
    - Per-repository statistics
    """

    cached_repositories: int
    total_memory_mb: float
    hit_count: int
    miss_count: int
    eviction_count: int
    per_repository_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class HNSWIndexCache:
    """
    Thread-safe in-memory cache for HNSW indexes (AC5: Thread-Safe Operations).

    Provides:
    - AC1: Server-side index caching for performance
    - AC2: TTL-based eviction
    - AC3: Access-based TTL refresh
    - AC4: Per-repository cache isolation
    - AC5: Thread-safe operations with proper locking
    - AC6: Configuration externalization
    - AC7: Cache statistics and monitoring

    Performance improvement: ~277ms → <1ms for repeated queries (1800x faster).
    """

    def __init__(self, config: Optional[HNSWIndexCacheConfig] = None):
        """
        Initialize HNSW index cache.

        Args:
            config: Cache configuration (defaults to standard config if None)
        """
        self.config = config or HNSWIndexCacheConfig()

        # Per-repository cache (AC4)
        self._cache: Dict[str, HNSWIndexCacheEntry] = {}

        # Thread-safe locking (AC5)
        # Use RLock to allow same thread to acquire lock multiple times
        self._cache_lock = RLock()

        # Statistics tracking (AC7)
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0

        # Background cleanup thread (AC2)
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()

        logger.info(
            f"HNSW Index Cache initialized with TTL={self.config.ttl_minutes} minutes"
        )

    def get_or_load(
        self,
        repo_path: str,
        loader: Callable[[], Tuple[Any, Dict[int, str]]],
    ) -> Tuple[Any, Dict[int, str]]:
        """
        Get cached HNSW index or load if not cached (AC1: Cache Implementation).

        Implements:
        - AC1: Cache hit returns cached index
        - AC1: Cache miss loads index and caches it
        - AC3: Access refreshes TTL
        - AC5: Thread-safe operations with deduplication

        Args:
            repo_path: Repository path (cache key)
            loader: Function to load index if not cached
                    Returns (hnsw_index, id_mapping)

        Returns:
            Tuple of (hnsw_index, id_mapping)
        """
        # Normalize repo path for consistent cache keys
        repo_path = str(Path(repo_path).resolve())

        with self._cache_lock:
            # Check if cached
            if repo_path in self._cache:
                entry = self._cache[repo_path]

                # Check if expired (AC2)
                if entry.is_expired():
                    # Evict expired entry
                    logger.debug(f"Cache entry expired for {repo_path}, reloading")
                    del self._cache[repo_path]
                    self._eviction_count += 1
                    # Fall through to load
                else:
                    # Cache hit - refresh TTL (AC3)
                    entry.record_access()
                    self._hit_count += 1
                    logger.debug(
                        f"Cache HIT for {repo_path} (access_count={entry.access_count})"
                    )
                    return entry.hnsw_index, entry.id_mapping

            # Cache miss - load index (AC1)
            self._miss_count += 1
            logger.debug(f"Cache MISS for {repo_path}, loading index")

            # Load index outside lock to avoid blocking other queries
            # But we need to hold lock to prevent duplicate loads
            # Solution: Hold lock during load (simpler, correct)
            hnsw_index, id_mapping = loader()

            # Create cache entry with initial access recorded
            entry = HNSWIndexCacheEntry(
                hnsw_index=hnsw_index,
                id_mapping=id_mapping,
                repo_path=repo_path,
                ttl_minutes=self.config.ttl_minutes,
            )

            # Record the initial load as an access
            entry.record_access()

            # Store in cache
            self._cache[repo_path] = entry

            logger.info(f"Cached HNSW index for {repo_path}")

            return hnsw_index, id_mapping

    def invalidate(self, repo_path: str) -> None:
        """
        Invalidate cache entry for specific repository.

        Args:
            repo_path: Repository path to invalidate
        """
        repo_path = str(Path(repo_path).resolve())

        with self._cache_lock:
            if repo_path in self._cache:
                del self._cache[repo_path]
                self._eviction_count += 1
                logger.info(f"Invalidated cache for {repo_path}")

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._cache_lock:
            evicted = len(self._cache)
            self._cache.clear()
            self._eviction_count += evicted
            logger.info(f"Cleared cache ({evicted} entries)")

    def _cleanup_expired_entries(self) -> None:
        """
        Clean up expired cache entries (AC2: TTL-based eviction).

        Called by background cleanup thread and manual cleanup.
        """
        with self._cache_lock:
            expired_repos = [
                repo_path
                for repo_path, entry in self._cache.items()
                if entry.is_expired()
            ]

            for repo_path in expired_repos:
                del self._cache[repo_path]
                self._eviction_count += 1
                logger.debug(f"Evicted expired cache entry: {repo_path}")

            if expired_repos:
                logger.info(f"Evicted {len(expired_repos)} expired cache entries")

    def start_background_cleanup(self) -> None:
        """
        Start background cleanup thread (AC2: Automatic eviction).

        Thread periodically checks for expired entries and evicts them.
        """
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("Background cleanup thread already running")
            return

        self._cleanup_stop_event.clear()

        def cleanup_loop():
            """Background cleanup loop."""
            while not self._cleanup_stop_event.is_set():
                try:
                    self._cleanup_expired_entries()
                except Exception as e:
                    logger.error(f"Error in background cleanup: {e}")

                # Wait for cleanup interval or stop event
                self._cleanup_stop_event.wait(
                    timeout=self.config.cleanup_interval_seconds
                )

        self._cleanup_thread = threading.Thread(
            target=cleanup_loop, name="HNSWIndexCacheCleanup", daemon=True
        )
        self._cleanup_thread.start()
        logger.info("Started background cache cleanup thread")

    def stop_background_cleanup(self) -> None:
        """Stop background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=5)
            logger.info("Stopped background cache cleanup thread")

    def get_stats(self) -> HNSWIndexCacheStats:
        """
        Get cache statistics (AC7: Monitoring).

        Returns:
            HNSWIndexCacheStats with current cache metrics
        """
        with self._cache_lock:
            # Calculate total memory usage (rough estimate)
            # Each HNSW index size is difficult to estimate without access to internal structures
            # For now, use cached repository count as proxy
            total_memory_mb = len(self._cache) * 100  # Rough estimate: 100MB per index

            # Per-repository stats
            per_repo_stats = {}
            for repo_path, entry in self._cache.items():
                per_repo_stats[repo_path] = {
                    "access_count": entry.access_count,
                    "last_accessed": entry.last_accessed.isoformat(),
                    "created_at": entry.created_at.isoformat(),
                    "ttl_remaining_seconds": entry.ttl_remaining_seconds(),
                }

            return HNSWIndexCacheStats(
                cached_repositories=len(self._cache),
                total_memory_mb=total_memory_mb,
                hit_count=self._hit_count,
                miss_count=self._miss_count,
                eviction_count=self._eviction_count,
                per_repository_stats=per_repo_stats,
            )
