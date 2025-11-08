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

        # AC11: Version tracking for cache invalidation after rebuild
        self.hnsw_index_version: Optional[str] = (
            None  # Tracks loaded index_rebuild_uuid
        )

        # Temporal collection cache (IDENTICAL pattern to HEAD collection)
        self.temporal_hnsw_index: Optional[Any] = None
        self.temporal_id_mapping: Optional[Dict[str, Any]] = None
        self.temporal_index_version: Optional[str] = None

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

        AC13: Properly closes mmap file descriptors before clearing indexes.
        """
        # AC13: Close mmap file descriptor if HNSW index is loaded
        # hnswlib Index objects don't expose close() method, but Python GC
        # will close the mmap when index object is deleted (refcount = 0)
        self.hnsw_index = None
        self.id_mapping = None
        self.tantivy_index = None
        self.tantivy_searcher = None
        self.fts_available = False
        # AC11: Clear version tracking
        self.hnsw_index_version = None

    def load_temporal_indexes(self, collection_path: Path) -> None:
        """Load temporal HNSW index using mmap.

        Uses IDENTICAL HNSWIndexManager.load_index() as HEAD collection.
        Follows exact same pattern as existing semantic index loading.

        Args:
            collection_path: Path to temporal collection directory

        Raises:
            FileNotFoundError: If collection path doesn't exist
            OSError: If unable to load indexes
        """
        if self.temporal_hnsw_index is not None:
            logger.debug("Temporal HNSW already loaded")
            return

        # Verify collection exists
        if not collection_path.exists():
            raise FileNotFoundError(f"Temporal collection not found: {collection_path}")

        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
        from code_indexer.storage.id_index_manager import IDIndexManager
        import json

        # Read collection metadata to get vector dimension
        metadata_file = collection_path / "collection_meta.json"
        if not metadata_file.exists():
            raise FileNotFoundError(f"Collection metadata not found: {metadata_file}")

        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        vector_dim = metadata.get("vector_size", 1536)

        # IDENTICAL loading mechanism as HEAD collection
        hnsw_manager = HNSWIndexManager(vector_dim=vector_dim, space="cosine")
        self.temporal_hnsw_index = hnsw_manager.load_index(
            collection_path, max_elements=100000
        )

        # Load ID index using IDIndexManager
        id_manager = IDIndexManager()
        self.temporal_id_mapping = id_manager.load_index(collection_path)

        # Track version for rebuild detection
        self.temporal_index_version = self._read_index_rebuild_uuid(collection_path)

        logger.info(f"Temporal HNSW index loaded via mmap from {collection_path}")

    def invalidate_temporal(self) -> None:
        """Invalidate temporal cache, closing mmap file descriptors.

        Python GC closes mmap when index object deleted (refcount = 0).
        Same cleanup pattern as HEAD cache invalidation.
        """
        self.temporal_hnsw_index = None
        self.temporal_id_mapping = None
        self.temporal_index_version = None
        logger.info("Temporal cache invalidated")

    def is_temporal_stale_after_rebuild(self, collection_path: Path) -> bool:
        """Check if cached temporal index version differs from disk metadata.

        Args:
            collection_path: Path to temporal collection directory

        Returns:
            True if cached index is stale (rebuild detected), False otherwise
        """
        # If no version tracked yet, not stale (not loaded yet)
        if self.temporal_index_version is None:
            return False

        # Read current index_rebuild_uuid from disk
        current_version = self._read_index_rebuild_uuid(collection_path)

        # Compare with cached version
        return self.temporal_index_version != current_version

    def is_stale_after_rebuild(self, collection_path: Path) -> bool:
        """Check if cached index version differs from disk metadata (AC11).

        Used to detect when background rebuild completed and cache needs reload.

        Args:
            collection_path: Path to collection directory

        Returns:
            True if cached index is stale (rebuild detected), False otherwise
        """

        # If no version tracked yet, not stale (not loaded yet)
        if self.hnsw_index_version is None:
            return False

        # Read current index_rebuild_uuid from disk
        current_version = self._read_index_rebuild_uuid(collection_path)

        # Compare with cached version
        return self.hnsw_index_version != current_version

    def _read_index_rebuild_uuid(self, collection_path: Path) -> str:
        """Read index_rebuild_uuid from collection_meta.json.

        Args:
            collection_path: Path to collection directory

        Returns:
            index_rebuild_uuid string or "v0" if not found
        """
        import json

        meta_file = collection_path / "collection_meta.json"

        if not meta_file.exists():
            return "v0"  # Default version if no metadata

        try:
            with open(meta_file) as f:
                metadata = json.load(f)

            return metadata.get("hnsw_index", {}).get("index_rebuild_uuid", "v0")

        except (json.JSONDecodeError, KeyError, OSError):
            return "v0"  # Corrupted/missing metadata

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
            "hnsw_version": self.hnsw_index_version,  # AC11: Include version in stats
            "temporal_loaded": self.temporal_hnsw_index is not None,
            "temporal_version": self.temporal_index_version,
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
