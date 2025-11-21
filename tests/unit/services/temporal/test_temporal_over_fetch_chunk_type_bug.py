"""
Test for over-fetch multiplier bug with chunk_type filtering.

BUG: temporal_search_service.py line 380 doesn't include chunk_type in has_post_filters check,
causing searches with --chunk-type to use exact limit instead of over-fetch multiplier.

SYMPTOM: When searching with --chunk-type commit_message --limit 20:
- Commit messages are ~2.7% of all vectors (382 / 14,084)
- Uses exact limit (20) without over-fetch
- Gets top 20 vectors from HNSW
- Filters by chunk_type="commit_message"
- Statistically: 20 × 2.7% = 0.5 results survive
- User sees 0-3 results instead of 20

EXPECTED: Should use over-fetch multiplier when chunk_type filter is present.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
    ALL_TIME_RANGE,
)


def test_chunk_type_filter_triggers_over_fetch_multiplier():
    """
    Test that chunk_type parameter is included in has_post_filters check.

    BUG: Line 380 in temporal_search_service.py:
        has_post_filters = bool(diff_types or author or not is_all_time)

    MISSING: chunk_type parameter

    SHOULD BE:
        has_post_filters = bool(diff_types or author or chunk_type or not is_all_time)

    This test directly verifies the search_limit calculation logic by inspecting
    the limit passed to vector_store.search() when chunk_type is provided.
    """
    # Create mock components
    mock_project_root = Path("/fake/repo")
    mock_config_manager = MagicMock()
    mock_vector_store = MagicMock()
    mock_embedding_provider = MagicMock()

    # Mock isinstance check to return True for FilesystemVectorStore
    with patch(
        "code_indexer.services.temporal.temporal_search_service.isinstance",
        return_value=True,
    ):
        # Create search service
        search_service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=mock_project_root,
            vector_store_client=mock_vector_store,
            embedding_provider=mock_embedding_provider,
        )

        # Mock the vector store search to capture the limit parameter
        # Return empty results to avoid processing logic
        mock_vector_store.search.return_value = ([], None)

        # Mock embedding generation
        mock_embedding_provider.embed_query.return_value = [0.1] * 1024

        # Execute search with chunk_type filter (the bug condition)
        try:
            search_service.query_temporal(
                query="test query",
                time_range=ALL_TIME_RANGE,  # ("1970-01-01", "2100-12-31")
                chunk_type="commit_message",  # POST-FILTER: Should trigger over-fetch
                limit=20,
                diff_types=None,
                author=None,
            )
        except Exception:
            # Ignore any post-processing errors - we only care about the vector_store.search call
            pass

        # ASSERTION: Verify vector_store.search was called
        assert mock_vector_store.search.called, "vector_store.search was not called"

        # Extract the limit parameter from the search call
        call_args = mock_vector_store.search.call_args
        actual_limit = call_args.kwargs.get("limit") or call_args.kwargs.get("top_k")

        # BUG DETECTION: With chunk_type filter, should use over-fetch multiplier
        # With limit=20 and chunk_type="commit_message", expected search_limit ≈ 740 (20 × 37)
        # BUG: Currently uses exact limit (20) because line 380 doesn't include chunk_type
        assert actual_limit > 20, (
            f"BUG DETECTED: chunk_type filter didn't trigger over-fetch multiplier.\n"
            f"  Requested limit: 20\n"
            f"  Actual search limit: {actual_limit}\n"
            f"  Expected: >20 (likely ~740 for multiplier ~37)\n"
            f"\n"
            f"ROOT CAUSE: Line 380 in temporal_search_service.py is missing chunk_type:\n"
            f"  Current:  has_post_filters = bool(diff_types or author or not is_all_time)\n"
            f"  Should be: has_post_filters = bool(diff_types or author or chunk_type or not is_all_time)\n"
            f"\n"
            f"IMPACT: Users get 0-3 results instead of 20 when filtering by chunk_type."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
