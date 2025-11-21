"""Unit tests for chunk_type filtering in temporal search (Story #476 AC3/AC4)."""

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


@pytest.fixture
def mock_config_manager():
    """Create mock config manager."""
    manager = MagicMock()
    config = MagicMock()
    config.codebase_dir = Path("/tmp/test")
    manager.get_config.return_value = config
    return manager


@pytest.fixture
def temporal_search_service(mock_config_manager):
    """Create TemporalSearchService instance."""
    return TemporalSearchService(
        config_manager=mock_config_manager,
        project_root=Path("/tmp/test"),
        vector_store_client=MagicMock(),
        embedding_provider=MagicMock(),
    )


class TestChunkTypeFiltering:
    """Test AC3/AC4: chunk_type parameter filters search results."""

    def test_query_temporal_accepts_chunk_type_parameter(self, temporal_search_service):
        """Test that query_temporal accepts chunk_type parameter and applies filter.

        This test verifies AC3/AC4: chunk_type filtering is supported.
        """
        # Arrange
        mock_vector_store = temporal_search_service.vector_store_client
        mock_embedding_provider = temporal_search_service.embedding_provider

        # Mock vector store to return mixed chunk types
        # Use FilesystemClient-style mocking (returns list directly, not tuple)
        mock_vector_store.collection_exists.return_value = True
        mock_vector_store.__class__.__name__ = "FilesystemClient"
        mock_vector_store.search.return_value = [
            MagicMock(
                id="test:commit:abc123:0",
                score=0.9,
                payload={
                    "type": "commit_message",
                    "commit_hash": "abc123",
                    "commit_timestamp": 1704153600,  # 2024-01-02 00:00:00 UTC (in range)
                    "commit_date": "2024-01-02",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                    "commit_message": "Fix bug",
                    "path": "[commit:abc123]",
                },
                chunk_text="Fix authentication bug",
            ),
            MagicMock(
                id="test:diff:def456:file.py:0",
                score=0.85,
                payload={
                    "type": "commit_diff",
                    "commit_hash": "def456",
                    "commit_timestamp": 1704240000,  # 2024-01-03 00:00:00 UTC (in range)
                    "commit_date": "2024-01-03",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                    "path": "file.py",
                    "diff_type": "modified",
                },
                chunk_text="def authenticate():",
            ),
        ]

        mock_embedding_provider.get_embedding.return_value = [0.1] * 1024

        # Act: Query with chunk_type filter for commit_message
        results = temporal_search_service.query_temporal(
            query="authentication",
            time_range=("2024-01-01", "2024-12-31"),
            limit=10,
            chunk_type="commit_message",  # AC3: Filter to commit messages only
        )

        # Assert: Should only return commit_message chunks
        assert len(results.results) == 1
        assert results.results[0].metadata["type"] == "commit_message"
        assert "Fix authentication bug" in results.results[0].content

    def test_query_without_chunk_type_returns_mixed_results(
        self, temporal_search_service
    ):
        """Test that query_temporal without chunk_type returns both chunk types.

        This test verifies AC2: Without chunk_type filter, results include both
        commit_message and commit_diff chunks.
        """
        # Arrange
        mock_vector_store = temporal_search_service.vector_store_client
        mock_embedding_provider = temporal_search_service.embedding_provider

        # Mock vector store to return mixed chunk types
        mock_vector_store.collection_exists.return_value = True
        mock_vector_store.__class__.__name__ = "FilesystemClient"
        mock_vector_store.search.return_value = [
            MagicMock(
                id="test:commit:abc123:0",
                score=0.9,
                payload={
                    "type": "commit_message",
                    "commit_hash": "abc123",
                    "commit_timestamp": 1704153600,  # 2024-01-02 00:00:00 UTC (in range)
                    "commit_date": "2024-01-02",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                    "commit_message": "Fix bug",
                    "path": "[commit:abc123]",
                },
                chunk_text="Fix authentication bug",
            ),
            MagicMock(
                id="test:diff:def456:file.py:0",
                score=0.85,
                payload={
                    "type": "commit_diff",
                    "commit_hash": "def456",
                    "commit_timestamp": 1704240000,  # 2024-01-03 00:00:00 UTC (in range)
                    "commit_date": "2024-01-03",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                    "path": "file.py",
                    "diff_type": "modified",
                },
                chunk_text="def authenticate():",
            ),
        ]

        mock_embedding_provider.get_embedding.return_value = [0.1] * 1024

        # Act: Query WITHOUT chunk_type filter
        results = temporal_search_service.query_temporal(
            query="authentication",
            time_range=("2024-01-01", "2024-12-31"),
            limit=10,
            # AC2: No chunk_type specified - should return all types
        )

        # Assert: Should return both commit_message and commit_diff chunks
        assert len(results.results) == 2
        result_types = {r.metadata["type"] for r in results.results}
        assert "commit_message" in result_types
        assert "commit_diff" in result_types

    def test_chunk_type_combines_with_other_filters(self, temporal_search_service):
        """Test that chunk_type filter combines correctly with author and time_range.

        This test verifies AC6: chunk_type filter works alongside other temporal filters
        (author, time_range, diff_type).
        """
        # Arrange
        mock_vector_store = temporal_search_service.vector_store_client
        mock_embedding_provider = temporal_search_service.embedding_provider

        # Mock vector store to return results from multiple authors
        mock_vector_store.collection_exists.return_value = True
        mock_vector_store.__class__.__name__ = "FilesystemClient"
        mock_vector_store.search.return_value = [
            MagicMock(
                id="test:commit:abc123:0",
                score=0.9,
                payload={
                    "type": "commit_message",
                    "commit_hash": "abc123",
                    "commit_timestamp": 1704153600,  # 2024-01-02 00:00:00 UTC (in range)
                    "commit_date": "2024-01-02",
                    "author_name": "Alice Smith",
                    "author_email": "alice@example.com",
                    "commit_message": "Fix bug",
                    "path": "[commit:abc123]",
                },
                chunk_text="Fix authentication bug",
            ),
            MagicMock(
                id="test:commit:def456:1",
                score=0.88,
                payload={
                    "type": "commit_message",
                    "commit_hash": "def456",
                    "commit_timestamp": 1704240000,  # 2024-01-03 00:00:00 UTC (in range)
                    "commit_date": "2024-01-03",
                    "author_name": "Bob Jones",
                    "author_email": "bob@example.com",
                    "commit_message": "Update auth",
                    "path": "[commit:def456]",
                },
                chunk_text="Update authentication method",
            ),
            MagicMock(
                id="test:diff:ghi789:file.py:0",
                score=0.85,
                payload={
                    "type": "commit_diff",
                    "commit_hash": "ghi789",
                    "commit_timestamp": 1704326400,  # 2024-01-04 00:00:00 UTC (in range)
                    "commit_date": "2024-01-04",
                    "author_name": "Alice Smith",
                    "author_email": "alice@example.com",
                    "path": "file.py",
                    "diff_type": "modified",
                },
                chunk_text="def authenticate():",
            ),
        ]

        mock_embedding_provider.get_embedding.return_value = [0.1] * 1024

        # Act: Query with combined filters (chunk_type + author)
        results = temporal_search_service.query_temporal(
            query="authentication",
            time_range=("2024-01-01", "2024-12-31"),
            limit=10,
            chunk_type="commit_message",  # AC6: Filter to commit messages
            author="Alice",  # AC6: Filter to Alice's commits
        )

        # Assert: Should only return commit_message chunks from Alice
        assert len(results.results) == 1
        assert results.results[0].metadata["type"] == "commit_message"
        assert "Alice" in results.results[0].metadata["author_name"]
        assert "Fix authentication bug" in results.results[0].content
