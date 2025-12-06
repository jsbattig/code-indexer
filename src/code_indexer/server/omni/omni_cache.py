"""
Cache management for omni-search results.

Provides TTL-based caching with cursor pagination.
"""

import uuid
import threading
from typing import Any, Dict, List, Optional
from cachetools import TTLCache


class OmniCache:
    """TTL-based cache with cursor pagination for omni-search results."""

    def __init__(
        self,
        ttl_seconds: int,
        max_entries: int,
        max_memory_mb: Optional[int] = None,
    ):
        """
        Initialize omni cache.

        Args:
            ttl_seconds: Time-to-live for cached entries in seconds
            max_entries: Maximum number of cached result sets
            max_memory_mb: Optional memory limit in megabytes (informational)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.max_memory_mb = max_memory_mb
        self.cache = TTLCache(maxsize=max_entries, ttl=ttl_seconds)
        self.lock = threading.RLock()

    def store_results(
        self,
        results: List[Dict],
        query_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store results in cache and return cursor.

        Args:
            results: List of search results
            query_params: Optional query parameters for reference

        Returns:
            Cursor string for retrieving results
        """
        cursor = str(uuid.uuid4())

        cache_entry = {
            "results": results,
            "query_params": query_params or {},
            "total_results": len(results),
        }

        with self.lock:
            self.cache[cursor] = cache_entry

        return cursor

    def get_results(
        self,
        cursor: str,
        offset: int = 0,
        limit: int = 10,
    ) -> Optional[List[Dict]]:
        """
        Retrieve results by cursor with offset/limit pagination.

        Args:
            cursor: Cursor string from store_results
            offset: Starting index for pagination
            limit: Maximum number of results to return

        Returns:
            List of results for the page, or None if cursor invalid/expired
        """
        with self.lock:
            cache_entry = self.cache.get(cursor)

        if cache_entry is None:
            return None

        results = cache_entry["results"]

        if offset >= len(results):
            return []

        end_idx = offset + limit
        return results[offset:end_idx]

    def get_metadata(self, cursor: str) -> Optional[Dict]:
        """
        Retrieve metadata for cached results.

        Args:
            cursor: Cursor string from store_results

        Returns:
            Metadata dict with total_results and query_params, or None
        """
        with self.lock:
            cache_entry = self.cache.get(cursor)

        if cache_entry is None:
            return None

        return {
            "total_results": cache_entry["total_results"],
            "query_params": cache_entry["query_params"],
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        with self.lock:
            total_entries = len(self.cache)

        return {
            "total_entries": total_entries,
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
        }
