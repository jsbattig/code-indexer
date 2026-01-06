"""
Server-side cache module for CIDX server.

Story #526: Provides singleton HNSW index cache for server-wide performance optimization.
Story #XXX: Provides singleton FTS (Tantivy) index cache for FTS query performance.
"""

from code_indexer.server.middleware.correlation import get_correlation_id
from .hnsw_index_cache import (
    HNSWIndexCache,
    HNSWIndexCacheConfig,
    HNSWIndexCacheEntry,
    HNSWIndexCacheStats,
)
from .fts_index_cache import (
    FTSIndexCache,
    FTSIndexCacheConfig,
    FTSIndexCacheEntry,
    FTSIndexCacheStats,
)

# Server-wide singleton cache instances
# Initialized on first import, shared across all server components
_global_cache_instance = None
_global_fts_cache_instance = None


def get_global_cache() -> HNSWIndexCache:
    """
    Get or create the global HNSW index cache instance.

    This is a singleton pattern - one cache instance shared across
    all server components (SemanticQueryManager, FilesystemVectorStore, etc).

    The cache is initialized with configuration from:
    1. ~/.cidx-server/config.json (if exists)
    2. Environment variables (CIDX_INDEX_CACHE_TTL_MINUTES)
    3. Default values (10 minute TTL)

    Returns:
        Global HNSWIndexCache instance
    """
    global _global_cache_instance

    if _global_cache_instance is None:
        # Try to load configuration from server config file
        from pathlib import Path
        import logging

        logger = logging.getLogger(__name__)

        config_file = Path.home() / ".cidx-server" / "config.json"

        if config_file.exists():
            try:
                config = HNSWIndexCacheConfig.from_file(str(config_file))
                logger.info(
                    f"Loaded HNSW cache config from {config_file}: TTL={config.ttl_minutes}min",
                    extra={"correlation_id": get_correlation_id()},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load cache config from {config_file}: {e}. Using defaults.",
                    extra={"correlation_id": get_correlation_id()},
                )
                config = HNSWIndexCacheConfig.from_env()
        else:
            # Try environment variables, fall back to defaults
            config = HNSWIndexCacheConfig.from_env()
            logger.info(
                f"Initialized HNSW cache with env/default config: TTL={config.ttl_minutes}min",
                extra={"correlation_id": get_correlation_id()},
            )

        _global_cache_instance = HNSWIndexCache(config=config)

        # Start background cleanup thread
        _global_cache_instance.start_background_cleanup()

    return _global_cache_instance


def reset_global_cache() -> None:
    """
    Reset the global cache instance (for testing purposes).

    Stops background cleanup and clears the singleton.
    """
    global _global_cache_instance

    if _global_cache_instance is not None:
        _global_cache_instance.stop_background_cleanup()
        _global_cache_instance = None


def get_global_fts_cache() -> FTSIndexCache:
    """
    Get or create the global FTS (Tantivy) index cache instance.

    This is a singleton pattern - one cache instance shared across
    all server components for FTS search operations.

    The cache is initialized with configuration from:
    1. ~/.cidx-server/config.json (if exists)
    2. Environment variables (CIDX_FTS_CACHE_TTL_MINUTES)
    3. Default values (10 minute TTL, reload_on_access=True)

    Returns:
        Global FTSIndexCache instance
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
                    f"Loaded FTS cache config from {config_file}: "
                    f"TTL={config.ttl_minutes}min, reload_on_access={config.reload_on_access}",
                    extra={"correlation_id": get_correlation_id()},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load FTS cache config from {config_file}: {e}. Using defaults.",
                    extra={"correlation_id": get_correlation_id()},
                )
                config = FTSIndexCacheConfig.from_env()
        else:
            # Try environment variables, fall back to defaults
            config = FTSIndexCacheConfig.from_env()
            logger.info(
                f"Initialized FTS cache with env/default config: "
                f"TTL={config.ttl_minutes}min, reload_on_access={config.reload_on_access}",
                extra={"correlation_id": get_correlation_id()},
            )

        _global_fts_cache_instance = FTSIndexCache(config=config)

        # Start background cleanup thread
        _global_fts_cache_instance.start_background_cleanup()

    return _global_fts_cache_instance


def reset_global_fts_cache() -> None:
    """
    Reset the global FTS cache instance (for testing purposes).

    Stops background cleanup and clears the singleton.
    """
    global _global_fts_cache_instance

    if _global_fts_cache_instance is not None:
        _global_fts_cache_instance.stop_background_cleanup()
        _global_fts_cache_instance = None


__all__ = [
    # HNSW cache exports
    "HNSWIndexCache",
    "HNSWIndexCacheConfig",
    "HNSWIndexCacheEntry",
    "HNSWIndexCacheStats",
    "get_global_cache",
    "reset_global_cache",
    # FTS cache exports
    "FTSIndexCache",
    "FTSIndexCacheConfig",
    "FTSIndexCacheEntry",
    "FTSIndexCacheStats",
    "get_global_fts_cache",
    "reset_global_fts_cache",
]
