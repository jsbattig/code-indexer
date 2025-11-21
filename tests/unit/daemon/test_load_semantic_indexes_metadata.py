"""
Unit tests for _load_semantic_indexes storing collection metadata.

Tests verify that when daemon loads semantic indexes, it stores collection_name
and vector_dim in the cache entry for use during search execution.
"""

from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json
from code_indexer.daemon.service import CIDXDaemonService
from code_indexer.daemon.cache import CacheEntry


class TestLoadSemanticIndexesMetadata:
    """Test that _load_semantic_indexes stores metadata in cache entry."""

    def test_load_semantic_indexes_stores_collection_name_and_vector_dim(self):
        """_load_semantic_indexes stores collection_name and vector_dim in cache entry.

        This test verifies that when loading semantic indexes, the daemon stores
        the collection name and vector dimension for use during search execution,
        eliminating hardcoded values.
        """
        service = CIDXDaemonService()
        entry = CacheEntry(project_path=Path("/tmp/test_project"))

        # Mock filesystem structure
        index_dir = Path("/tmp/test_project/.code-indexer/index")
        collection_name = "voyage-code-3"
        index_dir / collection_name

        # Mock collection metadata
        metadata = {
            "vector_size": 1024,
            "hnsw_index": {"index_rebuild_uuid": "test-uuid"},
        }

        with (
            patch.object(Path, "exists", return_value=True),
            patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_vector_store_class,
            patch("builtins.open", mock_open(read_data=json.dumps(metadata))),
            patch("json.load", return_value=metadata),
            patch(
                "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
            ) as mock_hnsw_manager_class,
            patch(
                "code_indexer.storage.id_index_manager.IDIndexManager"
            ) as mock_id_manager_class,
        ):

            # Mock FilesystemVectorStore.list_collections()
            mock_vector_store = Mock()
            mock_vector_store.list_collections.return_value = [collection_name]
            mock_vector_store_class.return_value = mock_vector_store

            # Mock HNSW and ID index loading
            mock_hnsw_manager = Mock()
            mock_hnsw_manager.load_index.return_value = Mock()  # Mock HNSW index
            mock_hnsw_manager_class.return_value = mock_hnsw_manager

            mock_id_manager = Mock()
            mock_id_manager.load_index.return_value = {
                "point_1": Path("/tmp/test.json")
            }
            mock_id_manager_class.return_value = mock_id_manager

            # Execute _load_semantic_indexes
            service._load_semantic_indexes(entry)

            # Verify metadata stored in cache entry
            assert entry.collection_name == collection_name
            assert entry.vector_dim == 1024
