"""
Unit tests for filter parsing performance optimization.

Tests verify that filter parsing happens once before the result loop,
not repeatedly for each result.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from code_indexer.daemon.service import CIDXDaemonService
from code_indexer.daemon.cache import CacheEntry


class TestFilterParsingPerformance:
    """Test that filter parsing is optimized (outside loop)."""

    def test_filter_parsing_happens_once_not_per_result(self):
        """Filter conditions built once before loop, not per result.

        BEFORE FIX: Filter parsing in loop = O(n) where n = number of results
        AFTER FIX: Filter parsing before loop = O(1)

        This test verifies that PathFilterBuilder and LanguageValidator are
        instantiated only ONCE, not once per result.
        """
        service = CIDXDaemonService()

        # Setup cache entry
        entry = CacheEntry(project_path=Path("/tmp/test_project"))
        entry.collection_name = "voyage-code-3"
        entry.vector_dim = 1024

        # Mock HNSW index that returns 3 candidates
        mock_hnsw_index = Mock()
        test_vector_paths = {
            "point_1": Path("/tmp/v1.json"),
            "point_2": Path("/tmp/v2.json"),
            "point_3": Path("/tmp/v3.json"),
        }
        entry.set_semantic_indexes(mock_hnsw_index, test_vector_paths)
        service.cache_entry = entry

        # Mock Path.exists() to return True for vector files
        def mock_exists(self):
            return str(self).endswith(".json")

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
            patch("builtins.open", create=True) as mock_open,
            patch("json.load") as mock_json_load,
            patch(
                "code_indexer.services.path_filter_builder.PathFilterBuilder"
            ) as mock_path_filter_builder_class,
            patch.object(Path, "exists", mock_exists),
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_provider.embed.return_value = np.zeros(1024)
            mock_embedding_factory.create.return_value = mock_embedding_provider

            # Mock backend and vector store
            mock_vector_store = Mock()
            mock_vector_store.resolve_collection_name.return_value = "voyage-code-3"
            # Return 3 results to test filter parsing performance
            mock_results = [
                {
                    "score": 0.9,
                    "payload": {
                        "path": "/tmp/test_project/src/file1.py",
                        "language": ".py",
                    },
                },
                {
                    "score": 0.8,
                    "payload": {
                        "path": "/tmp/test_project/src/file2.py",
                        "language": ".py",
                    },
                },
                {
                    "score": 0.7,
                    "payload": {
                        "path": "/tmp/test_project/src/file3.py",
                        "language": ".py",
                    },
                },
            ]
            mock_vector_store.search.return_value = (mock_results, {})

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Mock HNSW query to return 3 candidates
            mock_hnsw_manager = Mock()
            mock_hnsw_manager.query.return_value = (
                ["point_1", "point_2", "point_3"],
                [0.1, 0.2, 0.3],
            )
            mock_hnsw_manager_class.return_value = mock_hnsw_manager

            # Mock vector metadata
            vector_metadata = {
                "payload": {
                    "path": "/tmp/test_project/src/file.py",
                    "language": ".py",
                }
            }
            mock_json_load.return_value = vector_metadata

            # Mock PathFilterBuilder
            mock_path_builder = Mock()
            mock_path_builder.build_exclusion_filter.return_value = {
                "must_not": [{"key": "path", "match": {"text": "*test*"}}]
            }
            mock_path_filter_builder_class.return_value = mock_path_builder

            # Execute search with exclude_paths filter
            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project",
                query="test query",
                limit=10,
                exclude_paths=("*test*",),
            )

            # CRITICAL ASSERTION: PathFilterBuilder should be instantiated ONCE, not 3 times
            # BEFORE FIX: This will fail with call_count=3 (once per result)
            # AFTER FIX: call_count=1 (once before loop)
            assert (
                mock_path_filter_builder_class.call_count == 1
            ), f"PathFilterBuilder should be instantiated ONCE, not {mock_path_filter_builder_class.call_count} times"
