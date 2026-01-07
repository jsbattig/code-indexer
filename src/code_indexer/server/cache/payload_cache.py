"""Payload Cache for semantic search result truncation.

Story #679: S1 - Semantic Search with Payload Control (Foundation)

Provides SQLite-based caching for large content with TTL-based eviction.
"""

import asyncio
import logging
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from code_indexer.server.utils.config_manager import CacheConfig

logger = logging.getLogger(__name__)


class CacheNotFoundError(Exception):
    """Raised when a cache handle is not found or expired."""

    pass


@dataclass
class CacheRetrievalResult:
    """Result of retrieving cached content with pagination info."""

    content: str
    page: int
    total_pages: int
    has_more: bool


@dataclass
class PayloadCacheConfig:
    """Configuration for payload cache (AC1).

    Attributes:
        preview_size_chars: Number of characters to include in preview (default 2000)
        max_fetch_size_chars: Maximum chars per page when fetching (default 5000)
        cache_ttl_seconds: Time-to-live for cache entries in seconds (default 900)
        cleanup_interval_seconds: Interval between cleanup runs in seconds (default 60)
    """

    preview_size_chars: int = 2000
    max_fetch_size_chars: int = 5000
    cache_ttl_seconds: int = 900
    cleanup_interval_seconds: int = 60

    @classmethod
    def from_env(cls) -> "PayloadCacheConfig":
        """Create config from environment variables with fallback to defaults.

        Environment variables:
            CIDX_PREVIEW_SIZE_CHARS: Override preview_size_chars
            CIDX_MAX_FETCH_SIZE_CHARS: Override max_fetch_size_chars
            CIDX_CACHE_TTL_SECONDS: Override cache_ttl_seconds
            CIDX_CLEANUP_INTERVAL_SECONDS: Override cleanup_interval_seconds

        Returns:
            PayloadCacheConfig with values from env or defaults
        """
        config = cls()

        # Preview size override
        if preview_env := os.environ.get("CIDX_PREVIEW_SIZE_CHARS"):
            try:
                config.preview_size_chars = int(preview_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_PREVIEW_SIZE_CHARS '{preview_env}', using default"
                )

        # Max fetch size override
        if fetch_env := os.environ.get("CIDX_MAX_FETCH_SIZE_CHARS"):
            try:
                config.max_fetch_size_chars = int(fetch_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_MAX_FETCH_SIZE_CHARS '{fetch_env}', using default"
                )

        # Cache TTL override
        if ttl_env := os.environ.get("CIDX_CACHE_TTL_SECONDS"):
            try:
                config.cache_ttl_seconds = int(ttl_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_CACHE_TTL_SECONDS '{ttl_env}', using default"
                )

        # Cleanup interval override
        if cleanup_env := os.environ.get("CIDX_CLEANUP_INTERVAL_SECONDS"):
            try:
                config.cleanup_interval_seconds = int(cleanup_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_CLEANUP_INTERVAL_SECONDS '{cleanup_env}', using default"
                )

        return config

    @classmethod
    def from_server_config(
        cls, cache_config: Optional["CacheConfig"]
    ) -> "PayloadCacheConfig":
        """Create config from server CacheConfig with environment variable overrides.

        Priority: Environment variables > Server config > Defaults

        Args:
            cache_config: CacheConfig from server configuration (can be None)

        Environment variables (override server config):
            CIDX_PREVIEW_SIZE_CHARS: Override preview_size_chars
            CIDX_MAX_FETCH_SIZE_CHARS: Override max_fetch_size_chars
            CIDX_CACHE_TTL_SECONDS: Override cache_ttl_seconds
            CIDX_CLEANUP_INTERVAL_SECONDS: Override cleanup_interval_seconds

        Returns:
            PayloadCacheConfig with values from server config or defaults,
            with environment variable overrides applied
        """
        # Start with server config values or defaults
        if cache_config is not None:
            config = cls(
                preview_size_chars=cache_config.payload_preview_size_chars,
                max_fetch_size_chars=cache_config.payload_max_fetch_size_chars,
                cache_ttl_seconds=cache_config.payload_cache_ttl_seconds,
                cleanup_interval_seconds=cache_config.payload_cleanup_interval_seconds,
            )
        else:
            config = cls()  # Use class defaults

        # Apply environment variable overrides (same logic as from_env)
        if preview_env := os.environ.get("CIDX_PREVIEW_SIZE_CHARS"):
            try:
                config.preview_size_chars = int(preview_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_PREVIEW_SIZE_CHARS '{preview_env}', "
                    "using server config value"
                )

        if fetch_env := os.environ.get("CIDX_MAX_FETCH_SIZE_CHARS"):
            try:
                config.max_fetch_size_chars = int(fetch_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_MAX_FETCH_SIZE_CHARS '{fetch_env}', "
                    "using server config value"
                )

        if ttl_env := os.environ.get("CIDX_CACHE_TTL_SECONDS"):
            try:
                config.cache_ttl_seconds = int(ttl_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_CACHE_TTL_SECONDS '{ttl_env}', "
                    "using server config value"
                )

        if cleanup_env := os.environ.get("CIDX_CLEANUP_INTERVAL_SECONDS"):
            try:
                config.cleanup_interval_seconds = int(cleanup_env)
            except ValueError:
                logger.warning(
                    f"Invalid CIDX_CLEANUP_INTERVAL_SECONDS '{cleanup_env}', "
                    "using server config value"
                )

        return config


class PayloadCache:
    """SQLite-based cache for storing large content with pagination support (AC2).

    Uses WAL mode for concurrent read/write access and stores content
    with UUID4 handles for later retrieval.
    """

    def __init__(self, db_path: Path, config: PayloadCacheConfig):
        """Initialize PayloadCache.

        Args:
            db_path: Path to SQLite database file
            config: Cache configuration
        """
        self.db_path = db_path
        self.config = config
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()

    async def initialize(self) -> None:
        """Initialize database with WAL mode and create schema."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(str(self.db_path)) as db:
            # Enable WAL mode for concurrent access
            await db.execute("PRAGMA journal_mode=WAL")

            # Create table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS payload_cache (
                    handle TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    total_size INTEGER NOT NULL
                )
                """
            )

            # Create index for TTL cleanup
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_payload_cache_created_at
                ON payload_cache(created_at)
                """
            )

            await db.commit()

    async def close(self) -> None:
        """Close the cache and cleanup resources."""
        self.stop_background_cleanup()

    def start_background_cleanup(self) -> None:
        """Start background cleanup thread as daemon."""
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return  # Already running

        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="PayloadCacheCleanup",
        )
        self._cleanup_thread.start()

    def stop_background_cleanup(self) -> None:
        """Stop background cleanup thread."""
        self._stop_cleanup.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=2.0)

    def _cleanup_loop(self) -> None:
        """Background cleanup loop running in separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while not self._stop_cleanup.wait(self.config.cleanup_interval_seconds):
                try:
                    loop.run_until_complete(self.cleanup_expired())
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
        finally:
            loop.close()

    async def store(self, content: str) -> str:
        """Store content and return a UUID4 handle.

        Args:
            content: Content to cache

        Returns:
            UUID4 handle for retrieving the content
        """
        handle = str(uuid.uuid4())
        created_at = time.time()
        total_size = len(content)

        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO payload_cache (handle, content, created_at, total_size)
                VALUES (?, ?, ?, ?)
                """,
                (handle, content, created_at, total_size),
            )
            await db.commit()

        return handle

    async def retrieve(self, handle: str, page: int = 0) -> CacheRetrievalResult:
        """Retrieve cached content by handle with pagination.

        Args:
            handle: UUID4 handle from store()
            page: Page number (0-indexed)

        Returns:
            CacheRetrievalResult with content and pagination info

        Raises:
            CacheNotFoundError: If handle not found or page out of range
        """
        if page < 0:
            raise CacheNotFoundError(f"Invalid page number: {page}")

        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                "SELECT content, total_size FROM payload_cache WHERE handle = ?",
                (handle,),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            raise CacheNotFoundError(f"Cache handle not found: {handle}")

        content = row[0]
        total_size = row[1]
        page_size = self.config.max_fetch_size_chars

        # Calculate pagination
        total_pages = max(1, math.ceil(total_size / page_size))

        if page >= total_pages:
            raise CacheNotFoundError(
                f"Page {page} out of range for handle {handle} (total: {total_pages})"
            )

        # Extract page content
        start = page * page_size
        end = start + page_size
        page_content = content[start:end]

        has_more = page < total_pages - 1

        return CacheRetrievalResult(
            content=page_content,
            page=page,
            total_pages=total_pages,
            has_more=has_more,
        )

    async def truncate_result(self, content: str) -> dict:
        """Truncate content for semantic search response (AC3).

        For content larger than preview_size_chars:
            Returns preview, cache_handle, has_more=True, total_size

        For content <= preview_size_chars:
            Returns full content, cache_handle=None, has_more=False

        Args:
            content: Full content to potentially truncate

        Returns:
            Dict with appropriate keys based on content size
        """
        preview_size = self.config.preview_size_chars

        if len(content) > preview_size:
            # Large content: store full content and return preview
            cache_handle = await self.store(content)
            return {
                "preview": content[:preview_size],
                "cache_handle": cache_handle,
                "has_more": True,
                "total_size": len(content),
            }
        else:
            # Small content: return full content without caching
            return {
                "content": content,
                "cache_handle": None,
                "has_more": False,
            }

    async def cleanup_expired(self) -> int:
        """Delete cache entries older than cache_ttl_seconds.

        Returns:
            Number of entries deleted
        """
        cutoff_time = time.time() - self.config.cache_ttl_seconds

        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM payload_cache WHERE created_at < ?",
                (cutoff_time,),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            await db.execute(
                "DELETE FROM payload_cache WHERE created_at < ?",
                (cutoff_time,),
            )
            await db.commit()

        return count
