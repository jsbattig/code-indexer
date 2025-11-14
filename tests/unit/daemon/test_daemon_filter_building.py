"""
Unit tests for daemon filter building from raw kwargs.

Tests verify that daemon mode builds filter_conditions correctly from raw
parameters (languages, exclude_languages, path_filter, exclude_paths) instead
of expecting pre-built filter_conditions in kwargs.
"""

from unittest.mock import Mock, patch
from code_indexer.daemon.service import CIDXDaemonService


class TestDaemonFilterBuilding:
    """Test filter building in daemon mode semantic search."""

    def test_daemon_builds_exclude_path_filter_from_raw_params(self):
        """Daemon builds path exclusion filter from raw exclude_paths parameter.

        This test reproduces the critical bug where daemon mode ignores all filters.
        BEFORE FIX: filter_conditions will be None, exclude_paths ignored.
        AFTER FIX: filter_conditions built with must_not array containing path filters.
        """
        service = CIDXDaemonService()

        # Setup cache entry with mock HNSW index and id_mapping
        from code_indexer.daemon.cache import CacheEntry
        from pathlib import Path
        import numpy as np

        cache_entry = CacheEntry(project_path=Path("/tmp/test_project"))

        # Mock HNSW index that returns one candidate
        mock_hnsw_index = Mock()

        # Mock id_mapping with test data
        test_vector_path = Path("/tmp/test_vector.json")
        mock_id_mapping = {"point_1": test_vector_path}

        # Set semantic indexes in cache entry
        cache_entry.set_semantic_indexes(mock_hnsw_index, mock_id_mapping)
        service.cache_entry = cache_entry

        # Mock dependencies - patch where they're imported (inside method)
        with (
            patch("code_indexer.config.ConfigManager") as mock_config_mgr,
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
            patch(
                "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
            ) as mock_hnsw_manager_class,
            patch("builtins.open", create=True) as mock_open,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_provider.embed.return_value = np.zeros(1024)
            mock_embedding_factory.create.return_value = mock_embedding_provider

            # Mock HNSWIndexManager.query() to return one candidate
            mock_hnsw_manager = Mock()
            mock_hnsw_manager.query.return_value = (["point_1"], [0.1])
            mock_hnsw_manager_class.return_value = mock_hnsw_manager

            # Mock file reading for vector metadata
            import json

            vector_metadata = {
                "payload": {
                    "path": "/tmp/test_project/src/test_file.py",
                    "language": ".py",
                }
            }
            mock_file = Mock()
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_file.read.return_value = json.dumps(vector_metadata)
            mock_open.return_value = mock_file

            # Mock json.load to return vector data
            with patch("json.load", return_value=vector_metadata):
                # Execute semantic search with exclude_paths filter
                kwargs = {
                    "exclude_paths": ("*test*",),
                    "min_score": 0.5,
                }

                results, timing = service._execute_semantic_search(
                    project_path="/tmp/test_project",
                    query="test query",
                    limit=10,
                    **kwargs,
                )

            # CRITICAL ASSERTION: Result should be filtered out by exclude_paths
            # File path contains "test", so it should be excluded
            assert (
                len(results) == 0
            ), "Results should be filtered out by exclude_paths pattern"

    def test_daemon_builds_language_filter_from_raw_params(self):
        """Daemon builds language inclusion filter from raw languages parameter."""
        service = CIDXDaemonService()

        # Mock dependencies
        with (
            patch("code_indexer.config.ConfigManager") as mock_config_mgr,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory"
            ) as mock_backend_factory,
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_factory.create.return_value = mock_embedding_provider

            mock_vector_store = Mock()
            mock_vector_store.resolve_collection_name.return_value = "test_collection"
            mock_vector_store.search.return_value = ([], {})

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Execute semantic search with language filter
            kwargs = {
                "languages": ("python",),
                "min_score": 0.5,
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test query", limit=10, **kwargs
            )

            # Verify vector_store.search was called with filter_conditions
            assert mock_vector_store.search.called
            call_kwargs = mock_vector_store.search.call_args[1]

            # Should have filter_conditions built from languages
            assert "filter_conditions" in call_kwargs
            filter_conditions = call_kwargs["filter_conditions"]
            assert filter_conditions is not None

            # Should have must array with language filter
            assert "must" in filter_conditions
            assert len(filter_conditions["must"]) > 0

            # Language filter has "should" wrapper with multiple extensions
            language_filter = filter_conditions["must"][0]
            assert "should" in language_filter
            assert len(language_filter["should"]) > 0

            # Each should condition references language
            for condition in language_filter["should"]:
                assert "key" in condition
                assert condition["key"] == "language"

    def test_daemon_extract_exclude_paths_from_kwargs(self):
        """Verify daemon correctly extracts exclude_paths from kwargs (RPyC serialization test)."""
        service = CIDXDaemonService()

        # Mock dependencies
        with (
            patch("code_indexer.config.ConfigManager") as mock_config_mgr,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory"
            ) as mock_backend_factory,
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_factory.create.return_value = mock_embedding_provider

            mock_vector_store = Mock()
            mock_vector_store.resolve_collection_name.return_value = "test_collection"
            mock_vector_store.search.return_value = ([], {})

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Test with tuple (as Click provides)
            kwargs_tuple = {
                "exclude_paths": ("*test*", "*build*"),
                "min_score": 0.5,
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project",
                query="test query",
                limit=10,
                **kwargs_tuple,
            )

            # Verify extraction worked
            assert mock_vector_store.search.called
            call_kwargs = mock_vector_store.search.call_args[1]
            assert "filter_conditions" in call_kwargs
            filter_conditions = call_kwargs["filter_conditions"]
            assert filter_conditions is not None
            assert "must_not" in filter_conditions

            # Test with list (potential RPyC serialization)
            mock_vector_store.reset_mock()
            kwargs_list = {
                "exclude_paths": ["*test*", "*build*"],
                "min_score": 0.5,
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project",
                query="test query",
                limit=10,
                **kwargs_list,
            )

            # Should also work with list
            assert mock_vector_store.search.called
            call_kwargs = mock_vector_store.search.call_args[1]
            assert "filter_conditions" in call_kwargs
            filter_conditions = call_kwargs["filter_conditions"]
            assert filter_conditions is not None
            assert "must_not" in filter_conditions

    def test_daemon_logs_received_kwargs_for_debugging(self):
        """Debug test: Verify what kwargs are actually received by daemon."""
        service = CIDXDaemonService()

        # Mock dependencies
        with (
            patch("code_indexer.config.ConfigManager") as mock_config_mgr,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory"
            ) as mock_backend_factory,
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config_mgr.create_with_backtrack.return_value.get_config.return_value = (
                mock_config
            )

            mock_embedding_provider = Mock()
            mock_embedding_factory.create.return_value = mock_embedding_provider

            mock_vector_store = Mock()
            mock_vector_store.resolve_collection_name.return_value = "test_collection"
            mock_vector_store.search.return_value = ([], {})

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Test with kwargs as would come from CLI
            test_kwargs = {
                "exclude_paths": ("*test*",),
                "languages": ("python",),
                "min_score": 0.5,
            }

            print("\n=== Input kwargs ===")
            print(f"exclude_paths: {test_kwargs.get('exclude_paths')}")
            print(f"languages: {test_kwargs.get('languages')}")

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project",
                query="test query",
                limit=10,
                **test_kwargs,
            )

            # Check what was passed to search
            call_kwargs = mock_vector_store.search.call_args[1]
            filter_conditions = call_kwargs.get("filter_conditions")

            print("\n=== Filter conditions passed to search ===")
            print(f"filter_conditions: {filter_conditions}")

            # Verify
            assert filter_conditions is not None, "filter_conditions should not be None"
            assert isinstance(
                filter_conditions, dict
            ), "filter_conditions should be dict"

            # Should have both must (language) and must_not (exclude_paths)
            assert (
                "must" in filter_conditions
            ), f"Should have must array, got: {filter_conditions}"
            assert (
                "must_not" in filter_conditions
            ), f"Should have must_not array, got: {filter_conditions}"
