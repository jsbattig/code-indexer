"""SCIP index loader with LRU caching."""

from functools import lru_cache
from pathlib import Path

from ..protobuf import Index


class SCIPLoader:
    """Loads SCIP indexes from .scip files with LRU caching."""

    def __init__(self, cache_size: int = 128):
        """
        Initialize SCIP loader.

        Args:
            cache_size: Maximum number of indexes to cache in memory
        """
        self.cache_size = cache_size
        # Create cached load function
        self._cached_load = lru_cache(maxsize=cache_size)(self._load_from_disk)

    def load(self, scip_file: Path) -> Index:
        """
        Load a SCIP index from file.

        Args:
            scip_file: Path to .scip file

        Returns:
            Parsed Index protobuf object

        Raises:
            FileNotFoundError: If scip_file doesn't exist
            ValueError: If file is not a valid SCIP index
        """
        if not scip_file.exists():
            raise FileNotFoundError(f"SCIP file not found: {scip_file}")

        # Use cached load (cache key is the file path as string)
        return self._cached_load(str(scip_file.resolve()))

    def _load_from_disk(self, scip_file_str: str) -> Index:
        """
        Internal method to load SCIP index from disk.

        Args:
            scip_file_str: String path to .scip file

        Returns:
            Parsed Index protobuf object
        """
        scip_file = Path(scip_file_str)

        with open(scip_file, "rb") as f:
            data = f.read()

        index = Index()
        index.ParseFromString(data)

        return index

    def clear_cache(self) -> None:
        """Clear the LRU cache of loaded indexes."""
        self._cached_load.cache_clear()

    def cache_info(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache hits, misses, size, and maxsize
        """
        info = self._cached_load.cache_info()
        return {
            "hits": info.hits,
            "misses": info.misses,
            "size": info.currsize,
            "maxsize": info.maxsize,
        }
