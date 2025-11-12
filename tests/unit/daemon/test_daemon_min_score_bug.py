"""
Unit tests for daemon min_score parameter extraction bug.

CRITICAL BUG: Daemon extracts score_threshold from kwargs, but public API uses min_score.
When users call with min_score=0.8, daemon extracts score_threshold → gets None → minimum score filter silently ignored!

These tests verify daemon correctly extracts min_score (not score_threshold) from kwargs.
"""

from unittest.mock import Mock, patch
from code_indexer.daemon.service import CIDXDaemonService


class TestDaemonMinScoreParameterExtraction:
    """Test daemon extracts min_score parameter correctly."""

    def test_daemon_extracts_min_score_from_kwargs(self):
        """Daemon should extract min_score (not score_threshold) from kwargs.

        CRITICAL BUG REPRODUCTION:
        - User calls: cidx query "test" --min-score 0.8
        - CLI passes: min_score=0.8 in kwargs
        - Daemon extracts: score_threshold = kwargs.get("score_threshold") → None
        - Vector store receives: score_threshold=None → NO FILTERING!

        This test should FAIL before fix (score_threshold=None).
        After fix, score_threshold should be 0.8.
        """
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

            # Execute semantic search with min_score (as CLI provides)
            kwargs = {
                "min_score": 0.8,  # Correct parameter name from public API
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test query", limit=10, **kwargs
            )

            # Verify vector_store.search was called with score_threshold=0.8
            assert mock_vector_store.search.called
            call_kwargs = mock_vector_store.search.call_args[1]

            # CRITICAL ASSERTION: Should have score_threshold=0.8
            # BEFORE FIX: This will FAIL because score_threshold is None
            assert (
                "score_threshold" in call_kwargs
            ), "vector_store.search should receive score_threshold parameter"
            assert (
                call_kwargs["score_threshold"] == 0.8
            ), f"score_threshold should be 0.8 (from min_score), got {call_kwargs['score_threshold']}"

    def test_daemon_filters_results_by_min_score(self):
        """Daemon should filter results below min_score threshold.

        Verifies that when min_score=0.9 is provided, vector_store.search
        receives score_threshold=0.9 for filtering.
        """
        service = CIDXDaemonService()

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
            # Simulate vector store returning results with scores
            mock_vector_store.search.return_value = (
                [
                    {"path": "file1.py", "score": 0.95},
                    {"path": "file2.py", "score": 0.92},
                ],
                {},
            )

            mock_backend = Mock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_backend_factory.create.return_value = mock_backend

            # Execute with min_score=0.9
            kwargs = {
                "min_score": 0.9,
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test query", limit=10, **kwargs
            )

            # Verify score_threshold=0.9 was passed to search
            call_kwargs = mock_vector_store.search.call_args[1]
            assert (
                call_kwargs["score_threshold"] == 0.9
            ), f"Vector store should receive score_threshold=0.9, got {call_kwargs.get('score_threshold')}"

    def test_daemon_min_score_none_returns_all_results(self):
        """Daemon should return all results when min_score=None.

        When no min_score is provided, score_threshold should be None,
        allowing vector store to return all results without filtering.
        """
        service = CIDXDaemonService()

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

            # Execute without min_score
            kwargs = {}  # No min_score provided

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test query", limit=10, **kwargs
            )

            # Verify score_threshold=None was passed to search
            call_kwargs = mock_vector_store.search.call_args[1]
            assert (
                call_kwargs["score_threshold"] is None
            ), f"Vector store should receive score_threshold=None when min_score not provided, got {call_kwargs.get('score_threshold')}"

    def test_daemon_min_score_zero_passes_zero(self):
        """Daemon should pass min_score=0.0 correctly (edge case).

        Edge case: min_score=0.0 should be preserved (not treated as None/False).
        """
        service = CIDXDaemonService()

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

            # Execute with min_score=0.0 (edge case)
            kwargs = {
                "min_score": 0.0,
            }

            results, timing = service._execute_semantic_search(
                project_path="/tmp/test_project", query="test query", limit=10, **kwargs
            )

            # Verify score_threshold=0.0 was passed (not None)
            call_kwargs = mock_vector_store.search.call_args[1]
            assert (
                call_kwargs["score_threshold"] == 0.0
            ), f"Vector store should receive score_threshold=0.0, got {call_kwargs.get('score_threshold')}"
