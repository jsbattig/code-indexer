"""Test that temporal search service enables lazy loading optimization.

This test verifies that temporal queries actually USE the lazy loading feature
that was implemented in the vector store. Without this, the optimization is
dead code and provides zero performance benefit.
"""

from pathlib import Path
from unittest.mock import Mock
from code_indexer.services.temporal.temporal_search_service import TemporalSearchService
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalSearchLazyLoadingEnabled:
    """Test that temporal search enables lazy loading in vector store calls."""

    def test_temporal_search_enables_lazy_load_parameter(self):
        """Test that temporal search passes lazy_load=True to vector store.

        This is critical for the lazy loading optimization to actually work.
        Without this parameter being passed, all temporal queries still load
        ALL payloads upfront, defeating the entire optimization.
        """
        # Setup
        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.search = Mock(return_value=([], {}))

        embedding_provider = Mock()
        embedding_provider.get_embedding = Mock(return_value=[0.1] * 1024)

        config_manager = Mock()
        project_root = Path("/tmp/test")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
            vector_store_client=vector_store,
            embedding_provider=embedding_provider,
            collection_name="code-indexer-temporal"
        )

        # Execute temporal query with filters
        service.query_temporal(
            query="test query",
            time_range=("2024-01-01", "2024-12-31"),
            limit=10,
            diff_types=["added"],
            author=None,
            min_score=None,
        )

        # CRITICAL ASSERTION: Verify vector_store.search was called with lazy_load=True
        vector_store.search.assert_called_once()
        call_kwargs = vector_store.search.call_args.kwargs

        assert "lazy_load" in call_kwargs, (
            "Vector store search must be called with lazy_load parameter. "
            "Without this, lazy loading optimization is never activated!"
        )

        assert call_kwargs["lazy_load"] is True, (
            f"Expected lazy_load=True for temporal queries, got {call_kwargs['lazy_load']}. "
            "Temporal queries should enable lazy loading for performance optimization."
        )
