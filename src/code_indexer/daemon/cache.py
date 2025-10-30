"""Cache entry and TTL eviction logic for daemon service.

Provides in-memory caching of HNSW and Tantivy indexes with TTL-based eviction,
access tracking, and thread-safe concurrency control.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheEntry:
    """In-memory cache entry for semantic and FTS indexes.

    Attributes:
        project_path: Path to the project root
        hnsw_index: HNSW index for semantic search (None if not loaded)
        id_mapping: Mapping from point IDs to file paths (None if not loaded)
        tantivy_index: Tantivy FTS index (None if not loaded)
        tantivy_searcher: Tantivy searcher instance (None if not loaded)
        fts_available: Whether FTS indexes are available
        last_accessed: Timestamp of last access
        ttl_minutes: Time-to-live in minutes before eviction
        access_count: Number of times this entry has been accessed
        read_lock: RLock for concurrent reads
        write_lock: Lock for serialized writes
    """

    def __init__(self, project_path: Path, ttl_minutes: int = 10):
        """Initialize cache entry.

        Args:
            project_path: Path to the project root
            ttl_minutes: Time-to-live in minutes (default: 10)
        """
        # Project metadata
        self.project_path = project_path

        # Semantic indexes
        self.hnsw_index: Optional[Any] = None
        self.id_mapping: Optional[Dict[str, Any]] = None

        # FTS indexes
        self.tantivy_index: Optional[Any] = None
        self.tantivy_searcher: Optional[Any] = None
        self.fts_available: bool = False

        # Access tracking
        self.last_accessed: datetime = datetime.now()
        self.ttl_minutes: int = ttl_minutes
        self.access_count: int = 0

        # Concurrency control
        self.read_lock: threading.RLock = threading.RLock()  # Concurrent reads
        self.write_lock: threading.Lock = threading.Lock()  # Serialized writes

    def update_access(self) -> None:
        """Update last accessed timestamp and increment access count.

        Thread-safe method to track cache entry usage.
        """
        self.last_accessed = datetime.now()
        self.access_count += 1

    def is_expired(self) -> bool:
        """Check if cache entry has exceeded its TTL.

        Returns:
            True if entry is expired, False otherwise
        """
        ttl_delta = timedelta(minutes=self.ttl_minutes)
        return datetime.now() - self.last_accessed >= ttl_delta

    def set_semantic_indexes(self, hnsw_index: Any, id_mapping: Dict[str, Any]) -> None:
        """Set semantic search indexes.

        Args:
            hnsw_index: HNSW index for vector search
            id_mapping: Mapping from point IDs to file paths
        """
        self.hnsw_index = hnsw_index
        self.id_mapping = id_mapping

    def set_fts_indexes(self, tantivy_index: Any, tantivy_searcher: Any) -> None:
        """Set FTS indexes.

        Args:
            tantivy_index: Tantivy index instance
            tantivy_searcher: Tantivy searcher instance
        """
        self.tantivy_index = tantivy_index
        self.tantivy_searcher = tantivy_searcher
        self.fts_available = True

    def invalidate(self) -> None:
        """Invalidate cache entry by clearing all indexes.

        Preserves access tracking metadata (access_count, last_accessed).
        Used when storage operations modify underlying data.
        """
        self.hnsw_index = None
        self.id_mapping = None
        self.tantivy_index = None
        self.tantivy_searcher = None
        self.fts_available = False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache entry statistics.

        Returns:
            Dict with cache entry metadata and status
        """
        return {
            "project_path": str(self.project_path),
            "access_count": self.access_count,
            "ttl_minutes": self.ttl_minutes,
            "last_accessed": self.last_accessed.isoformat(),
            "semantic_loaded": self.hnsw_index is not None,
            "fts_loaded": self.fts_available,
            "expired": self.is_expired(),
        }


class TTLEvictionThread(threading.Thread):
    """Background thread for TTL-based cache eviction.

    Runs every check_interval seconds to check for expired cache entries.
    Supports auto-shutdown on idle when configured.

    Attributes:
        daemon_service: Reference to the CIDXDaemonService
        check_interval: Seconds between eviction checks (default: 60)
        running: Flag to control thread execution
    """

    def __init__(self, daemon_service: Any, check_interval: int = 60):
        """Initialize TTL eviction thread.

        Args:
            daemon_service: Reference to CIDXDaemonService
            check_interval: Seconds between eviction checks (default: 60)
        """
        super().__init__(daemon=True)
        self.daemon_service = daemon_service
        self.check_interval = check_interval
        self.running = True

    def run(self) -> None:
        """Run eviction loop.

        Checks for expired cache every check_interval seconds.
        Exits when running flag is set to False.
        """
        while self.running:
            time.sleep(self.check_interval)
            self._check_and_evict()

    def stop(self) -> None:
        """Stop the eviction thread gracefully."""
        self.running = False

    def _check_and_evict(self) -> None:
        """Check for expired cache and evict if necessary.

        Acquires cache lock before checking expiration.
        Triggers auto-shutdown if configured and cache is evicted.
        """
        with self.daemon_service.cache_lock:
            if self.daemon_service.cache_entry is None:
                return

            if self.daemon_service.cache_entry.is_expired():
                logger.info("Cache expired, evicting")
                self.daemon_service.cache_entry = None

                # Check for auto-shutdown
                if self._should_shutdown():
                    logger.info("Auto-shutdown on idle")
                    os._exit(0)

    def _should_shutdown(self) -> bool:
        """Check if daemon should auto-shutdown on idle.

        Returns:
            True if auto-shutdown should be triggered, False otherwise
        """
        # Check if auto-shutdown is enabled
        if not hasattr(self.daemon_service, "config"):
            return False

        if not hasattr(self.daemon_service.config, "auto_shutdown_on_idle"):
            return False

        if not self.daemon_service.config.auto_shutdown_on_idle:
            return False

        # Check if cache is empty (idle state)
        if self.daemon_service.cache_entry is not None:
            return False

        return True
