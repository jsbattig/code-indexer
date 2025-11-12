"""
Test for time-range-all limit optimization.

When using --time-range-all with no additional filters (no --diff-type, no --author),
the system should use exact limit instead of wasteful 5x-20x multiplier.

This optimization improves query performance when users want to query entire temporal
history without filtering by diff type or author.
"""

import unittest
from unittest.mock import MagicMock
from pathlib import Path

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestTemporalTimeRangeAllLimitOptimization(unittest.TestCase):
    """Test limit handling for --time-range-all queries with and without filters."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_manager = MagicMock()
        self.project_root = Path("/tmp/test_project")
        self.vector_store = MagicMock()
        self.embedding_provider = MagicMock()
        self.collection_name = "code-indexer-temporal"

        # Set up vector store mock
        self.vector_store.collection_exists.return_value = True

        # Create service
        self.service = TemporalSearchService(
            config_manager=self.config_manager,
            project_root=self.project_root,
            vector_store_client=self.vector_store,
            embedding_provider=self.embedding_provider,
            collection_name=self.collection_name,
        )

    def test_time_range_all_no_filters_uses_exact_limit(self):
        """
        TEST 1: --time-range-all --limit 10 with NO filters → should fetch exactly 10.

        EXPECTED BEHAVIOR:
        - No diff_types filter
        - No author filter
        - Should use exact limit (10) without multiplier
        - Vector store search called with limit=10
        """
        # Arrange
        query = "authentication"
        limit = 10
        time_range = ("1970-01-01", "2100-12-31")  # Represents "all"
        diff_types = None  # NO filter
        author = None  # NO filter

        # Mock vector store to track search calls
        from src.code_indexer.storage.filesystem_vector_store import (
            FilesystemVectorStore,
        )

        self.vector_store.__class__ = FilesystemVectorStore
        self.vector_store.search.return_value = ([], {})  # Empty results

        # Act
        self.service.query_temporal(
            query=query,
            time_range=time_range,
            diff_types=diff_types,
            author=author,
            limit=limit,
        )

        # Assert
        self.vector_store.search.assert_called_once()
        call_args = self.vector_store.search.call_args

        # CRITICAL: Should use exact limit (10), NOT multiplied (150)
        self.assertEqual(
            call_args.kwargs["limit"],
            10,
            "With no filters, should use exact limit (10), not multiplied limit",
        )

    def test_time_range_all_with_diff_type_filter_uses_multiplier(self):
        """
        TEST 2: --time-range-all --limit 10 --diff-type added → should fetch 150.

        EXPECTED BEHAVIOR:
        - Has diff_types filter
        - Should use multiplier (15x for limit 10)
        - Vector store search called with limit=150
        """
        # Arrange
        query = "authentication"
        limit = 10
        time_range = ("1970-01-01", "2100-12-31")  # Represents "all"
        diff_types = ["added"]  # HAS filter
        author = None

        # Mock vector store
        from src.code_indexer.storage.filesystem_vector_store import (
            FilesystemVectorStore,
        )

        self.vector_store.__class__ = FilesystemVectorStore
        self.vector_store.search.return_value = ([], {})

        # Act
        self.service.query_temporal(
            query=query,
            time_range=time_range,
            diff_types=diff_types,
            author=author,
            limit=limit,
        )

        # Assert
        self.vector_store.search.assert_called_once()
        call_args = self.vector_store.search.call_args

        # Should use multiplier (15x for limit 10)
        self.assertEqual(
            call_args.kwargs["limit"],
            150,
            "With diff_type filter, should use multiplier (15x = 150)",
        )

    def test_time_range_all_with_author_filter_uses_multiplier(self):
        """
        TEST 3: --time-range-all --limit 10 --author john → should fetch 150.

        EXPECTED BEHAVIOR:
        - Has author filter
        - Should use multiplier (15x for limit 10)
        - Vector store search called with limit=150
        """
        # Arrange
        query = "authentication"
        limit = 10
        time_range = ("1970-01-01", "2100-12-31")  # Represents "all"
        diff_types = None
        author = "john"  # HAS filter

        # Mock vector store
        from src.code_indexer.storage.filesystem_vector_store import (
            FilesystemVectorStore,
        )

        self.vector_store.__class__ = FilesystemVectorStore
        self.vector_store.search.return_value = ([], {})

        # Act
        self.service.query_temporal(
            query=query,
            time_range=time_range,
            diff_types=diff_types,
            author=author,
            limit=limit,
        )

        # Assert
        self.vector_store.search.assert_called_once()
        call_args = self.vector_store.search.call_args

        # Should use multiplier (15x for limit 10)
        self.assertEqual(
            call_args.kwargs["limit"],
            150,
            "With author filter, should use multiplier (15x = 150)",
        )


if __name__ == "__main__":
    unittest.main()
