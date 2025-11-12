"""CIDX Daemon Service Module.

Provides RPyC-based daemon service for in-memory index caching, watch mode integration,
and cache-coherent storage operations.

Key Components:
- CIDXDaemonService: Main RPyC service with exposed methods
- CacheEntry: In-memory cache for HNSW and Tantivy indexes
- TTLEvictionThread: Background thread for cache eviction
- DaemonServer: Server startup with socket binding as atomic lock
"""

__all__ = [
    "CIDXDaemonService",
    "CacheEntry",
    "TTLEvictionThread",
    "start_daemon",
]
