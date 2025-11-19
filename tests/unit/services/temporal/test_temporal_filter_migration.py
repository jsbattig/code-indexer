"""Integration tests for temporal filter migration to vector store.

Tests that temporal filters (time_range, diff_type, author) are correctly
applied via filter_conditions in the vector store, enabling early exit
optimization and reducing unnecessary JSON loads.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
    ALL_TIME_RANGE,
)
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for tests."""
    config = Mock()
    config.get.return_value = None
    return config


@pytest.fixture
def mock_embedding_provider():
    """Mock embedding provider."""
    provider = Mock()
    provider.get_embedding.return_value = [0.1] * 1024
    return provider


@pytest.fixture
def mock_vector_store():
    """Mock FilesystemVectorStore for testing."""
    store = MagicMock(spec=FilesystemVectorStore)
    store.collection_exists.return_value = True
    return store


@pytest.fixture
def temporal_service(
    mock_config_manager, mock_vector_store, mock_embedding_provider, tmp_path
):
    """Create TemporalSearchService with mocked dependencies."""
    service = TemporalSearchService(
        config_manager=mock_config_manager,
        project_root=tmp_path,
        vector_store_client=mock_vector_store,
        embedding_provider=mock_embedding_provider,
        collection_name="code-indexer-temporal",
    )
    return service


class TestTemporalFilterMigration:
    """Test temporal filters applied via filter_conditions."""

    def test_time_range_filter_in_filter_conditions(
        self, temporal_service, mock_vector_store, mock_embedding_provider
    ):
        """Test that time_range is converted to filter_conditions with range operator."""
        # Setup mock to return empty results (we're testing filter_conditions, not results)
        mock_vector_store.search.return_value = ([], {})

        # Execute query with time range
        time_range = ("2024-01-01", "2024-12-31")
        temporal_service.query_temporal(
            query="test query",
            time_range=time_range,
            limit=10,
        )

        # Verify vector_store.search was called
        assert mock_vector_store.search.called

        # Extract filter_conditions from the call
        call_kwargs = mock_vector_store.search.call_args.kwargs
        filter_conditions = call_kwargs.get("filter_conditions", {})

        # Verify time range filter is present with range operator
        assert "must" in filter_conditions
        time_filters = [
            f for f in filter_conditions["must"] if f.get("key") == "commit_timestamp"
        ]
        assert len(time_filters) == 1

        time_filter = time_filters[0]
        assert "range" in time_filter

        # Verify timestamp conversion
        start_ts = int(datetime.strptime("2024-01-01", "%Y-%m-%d").timestamp())
        end_ts = int(
            datetime.strptime("2024-12-31", "%Y-%m-%d")
            .replace(hour=23, minute=59, second=59)
            .timestamp()
        )

        assert time_filter["range"]["gte"] == start_ts
        assert time_filter["range"]["lte"] == end_ts

    def test_diff_type_filter_in_filter_conditions(
        self, temporal_service, mock_vector_store, mock_embedding_provider
    ):
        """Test that diff_types are converted to filter_conditions with any operator."""
        mock_vector_store.search.return_value = ([], {})

        # Execute query with diff_types
        temporal_service.query_temporal(
            query="test query",
            time_range=ALL_TIME_RANGE,
            diff_types=["added", "modified"],
            limit=10,
        )

        # Extract filter_conditions
        call_kwargs = mock_vector_store.search.call_args.kwargs
        filter_conditions = call_kwargs.get("filter_conditions", {})

        # Verify diff_type filter is present with any operator
        assert "must" in filter_conditions
        diff_filters = [
            f for f in filter_conditions["must"] if f.get("key") == "diff_type"
        ]
        assert len(diff_filters) == 1

        diff_filter = diff_filters[0]
        assert "match" in diff_filter
        assert "any" in diff_filter["match"]
        assert set(diff_filter["match"]["any"]) == {"added", "modified"}

    def test_author_filter_in_filter_conditions(
        self, temporal_service, mock_vector_store, mock_embedding_provider
    ):
        """Test that author is converted to filter_conditions with contains operator."""
        mock_vector_store.search.return_value = ([], {})

        # Execute query with author filter
        temporal_service.query_temporal(
            query="test query",
            time_range=ALL_TIME_RANGE,
            author="john.doe",
            limit=10,
        )

        # Extract filter_conditions
        call_kwargs = mock_vector_store.search.call_args.kwargs
        filter_conditions = call_kwargs.get("filter_conditions", {})

        # Verify author filter is present with contains operator
        assert "must" in filter_conditions
        author_filters = [
            f for f in filter_conditions["must"] if f.get("key") == "author_name"
        ]
        assert len(author_filters) == 1

        author_filter = author_filters[0]
        assert "match" in author_filter
        assert "contains" in author_filter["match"]
        assert author_filter["match"]["contains"] == "john.doe"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
