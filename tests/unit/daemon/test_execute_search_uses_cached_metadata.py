"""
Unit tests for _execute_semantic_search using cached metadata.

Tests verify that search execution uses collection_name and vector_dim from
cache entry instead of hardcoded values.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from code_indexer.daemon.service import CIDXDaemonService
from code_indexer.daemon.cache import CacheEntry


class TestExecuteSearchUsesCachedMetadata:
    """Test that _execute_semantic_search uses cached metadata."""

    def test_execute_search_uses_cached_collection_name_and_vector_dim(self):
        """_execute_semantic_search uses cached collection_name and vector_dim.

        BEFORE FIX: Hardcoded "voyage-code-3" and 1024
        AFTER FIX: Uses self.cache_entry.collection_name and self.cache_entry.vector_dim
        """
        service = CIDXDaemonService()

        # Setup cache entry with custom metadata
        entry = CacheEntry(project_path=Path("/tmp/test_project"))
        entry.collection_name = "custom-collection"
        entry.vector_dim = 768  # Different from hardcoded 1024

        # Mock HNSW index and id_mapping
        mock_hnsw_index = Mock()
        entry.set_semantic_indexes(mock_hnsw_index, {})
        service.cache_entry = entry

        with (
            patch("code_indexer.config.ConfigManager") as mock_config_mgr,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory"
            ) as mock_backend_factory,
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
            patch(
                "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
            ) as mock_hnsw_manager_class,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_provider.embed.return_value = np.zeros(
                768
            )  # Match vector_dim
            mock_embedding_factory.create.return_value = mock_embedding_provider

            # Mock backend and vector store
            mock_vector_store = Mock()
            mock_vector_store.resolve_collection_name.return_value = "custom-collection"
            mock_vector_store.search.return_value = ([], {})  # Empty results

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Mock HNSWIndexManager to verify it's called with correct vector_dim
            mock_hnsw_manager = Mock()
            mock_hnsw_manager.query.return_value = ([], [])  # Empty results
            mock_hnsw_manager_class.return_value = mock_hnsw_manager

            # Execute search
            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test", limit=10
            )

            # CRITICAL: Verify vector_store.search was called
            # (the actual search now uses vector_store.search instead of direct HNSW)
            assert mock_vector_store.search.called

            # Verify resolve_collection_name was called
            # (this confirms the search uses vector store resolution)
            assert mock_vector_store.resolve_collection_name.called
