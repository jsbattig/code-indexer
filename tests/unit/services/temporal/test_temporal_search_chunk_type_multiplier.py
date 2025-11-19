"""Unit tests for chunk_type-specific over-fetch multipliers in temporal search.

These tests verify that temporal search applies appropriate over-fetch multipliers
based on chunk_type to compensate for post-filtering of minority types.

Root Cause: Chunk_type filtering happens AFTER HNSW search (post-filter).
When filtering for commit_message (2.7% of vectors), standard 3x multiplier
yields insufficient results.

Solution: Apply chunk_type-specific multipliers:
- commit_message: 40x (compensates for 2.7% distribution)
- commit_diff: 1.5x (97.3% of vectors, minimal over-fetch)
"""

from unittest.mock import Mock
from code_indexer.services.temporal.temporal_search_service import TemporalSearchService


class TestChunkTypeMultipliers:
    """Test chunk_type-specific over-fetch multiplier calculation."""

    def test_commit_message_uses_40x_multiplier(self):
        """Verify commit_message chunk_type uses 40x multiplier for over-fetch.

        Given: Query with chunk_type=commit_message and limit=20
        When: Calculating search_limit (prefetch_limit)
        Then: search_limit should be 20 * 40 = 800

        Rationale: Commit messages are 2.7% of vectors (382 / 14,084).
        With 800 candidates, expect ~21.6 commit messages after filtering.
        """
        # Setup
        service = TemporalSearchService(
            config_manager=Mock(),
            project_root="/fake/path",
            vector_store_client=Mock(),
            embedding_provider=Mock(),
        )

        # Mock vector_store_client.search to capture prefetch_limit and stop execution
        captured_prefetch_limit = None

        class PrefetchCaptured(Exception):
            """Exception to stop test execution after capturing prefetch_limit."""

            pass

        def mock_search(*args, **kwargs):
            nonlocal captured_prefetch_limit
            captured_prefetch_limit = kwargs.get("prefetch_limit")
            # Raise exception to stop execution (we only need to verify prefetch_limit)
            raise PrefetchCaptured()

        # Make isinstance check pass for FilesystemVectorStore
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        service.vector_store_client = Mock(spec=FilesystemVectorStore)
        service.vector_store_client.search = mock_search

        # Execute (will raise PrefetchCaptured after capturing prefetch_limit)
        try:
            service.query_temporal(
                query="fix",
                limit=20,
                chunk_type="commit_message",
                time_range=("1970-01-01", "2100-12-31"),  # ALL_TIME_RANGE
            )
        except PrefetchCaptured:
            pass  # Expected - we only need prefetch_limit

        # Verify: prefetch_limit should be 20 * 40 = 800
        assert captured_prefetch_limit == 800, (
            f"Expected prefetch_limit=800 (20 * 40x multiplier) for commit_message, "
            f"got {captured_prefetch_limit}"
        )
