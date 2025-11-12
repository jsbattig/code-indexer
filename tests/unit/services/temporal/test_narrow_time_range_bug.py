"""
Proof-of-concept test demonstrating the narrow time range bug.

This test SHOULD FAIL with current implementation, proving the bug exists.
After fixing the filter detection logic, this test should PASS.
"""

import unittest
from unittest.mock import MagicMock
from pathlib import Path

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestNarrowTimeRangeBug(unittest.TestCase):
    """Demonstrate bug: narrow time range without filters uses wrong limit."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_manager = MagicMock()
        self.project_root = Path("/tmp/test_project")
        self.vector_store = MagicMock()
        self.embedding_provider = MagicMock()
        self.collection_name = "code-indexer-temporal"

        self.vector_store.collection_exists.return_value = True

        self.service = TemporalSearchService(
            config_manager=self.config_manager,
            project_root=self.project_root,
            vector_store_client=self.vector_store,
            embedding_provider=self.embedding_provider,
            collection_name=self.collection_name,
        )

    def test_narrow_time_range_no_filters_SHOULD_use_multiplier(self):
        """
        BUG DEMONSTRATION: Narrow time range without diff/author filters.

        SCENARIO:
        - Time range: 2024-01-01..2024-01-31 (1 month, aggressive filtering)
        - No diff_types filter
        - No author filter
        - Limit: 10

        CURRENT BEHAVIOR (BUGGY):
        - has_filters = bool(None or None) = False
        - search_limit = 10 (exact limit, NO multiplier)
        - Time filtering rejects 90% of results
        - User only gets 1-2 results instead of 10

        EXPECTED BEHAVIOR (CORRECT):
        - Detect narrow time range (not "all")
        - has_post_filters = True (time filtering is post-filtering)
        - search_limit = 150 (15x multiplier for limit=10)
        - Time filtering rejects 90% of 150 = ~15 results
        - User gets 10+ results as requested

        THIS TEST SHOULD FAIL until bug is fixed.
        """
        # Arrange
        query = "authentication"
        limit = 10
        time_range = ("2024-01-01", "2024-01-31")  # NARROW range (1 month)
        diff_types = None  # NO filter
        author = None  # NO filter

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
        call_args = self.vector_store.search.call_args

        # BUG: Current implementation uses limit=10 (no multiplier)
        # FIX: Should use limit=150 (15x multiplier for narrow time range)
        actual_limit = call_args.kwargs["limit"]

        # This assertion WILL FAIL with current buggy implementation
        self.assertEqual(
            actual_limit,
            150,
            f"BUG DETECTED: Narrow time range should use multiplier (15x=150), "
            f"but got {actual_limit}. Time filtering is post-filtering and "
            f"requires over-fetch headroom even without diff/author filters.",
        )


if __name__ == "__main__":
    unittest.main()
