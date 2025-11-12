"""
Unit tests for CacheEntry metadata storage (collection_name, vector_dim).

Tests verify that CacheEntry stores collection metadata needed for semantic search
without hardcoding these values in the search execution code.
"""

from pathlib import Path
from code_indexer.daemon.cache import CacheEntry


class TestCacheEntryMetadata:
    """Test metadata storage in CacheEntry."""

    def test_cache_entry_stores_collection_name(self):
        """CacheEntry stores collection_name for loaded semantic indexes.

        This eliminates hardcoded collection names in search execution.
        BEFORE FIX: collection_name not stored, forcing hardcoded "voyage-code-3"
        AFTER FIX: collection_name stored during index loading, used during search
        """
        entry = CacheEntry(project_path=Path("/tmp/test"))

        # Initially None
        assert entry.collection_name is None

        # Can be set
        entry.collection_name = "voyage-code-3"
        assert entry.collection_name == "voyage-code-3"

    def test_cache_entry_stores_vector_dim(self):
        """CacheEntry stores vector_dim for loaded semantic indexes.

        This eliminates hardcoded vector dimensions in search execution.
        BEFORE FIX: vector_dim not stored, forcing hardcoded 1024
        AFTER FIX: vector_dim stored during index loading, used during search
        """
        entry = CacheEntry(project_path=Path("/tmp/test"))

        # Default is 1536 (VoyageAI voyage-3)
        assert entry.vector_dim == 1536

        # Can be set to actual dimension
        entry.vector_dim = 1024
        assert entry.vector_dim == 1024

    def test_cache_entry_invalidate_clears_metadata(self):
        """CacheEntry.invalidate() clears collection metadata.

        When cache is invalidated, metadata should also be cleared.
        """
        entry = CacheEntry(project_path=Path("/tmp/test"))

        # Set metadata
        entry.collection_name = "voyage-code-3"
        entry.vector_dim = 1024

        # Set mock indexes
        entry.hnsw_index = "mock_index"
        entry.id_mapping = {"point_1": Path("/tmp/test.json")}

        # Invalidate
        entry.invalidate()

        # Metadata should be cleared
        assert entry.collection_name is None
        assert entry.vector_dim == 1536  # Reset to default
        assert entry.hnsw_index is None
        assert entry.id_mapping is None
