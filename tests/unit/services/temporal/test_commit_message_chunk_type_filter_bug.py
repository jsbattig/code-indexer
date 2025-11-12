"""Test for Story #476 bug: commit message chunks not returned when filtering by --chunk-type.

SYMPTOM:
- 382 commit message chunks indexed correctly with type="commit_message"
- chunk_text populated with actual commit messages
- Queries return 0 results when filtering by --chunk-type commit_message
- User reports only getting 0-3 results for obvious queries

ROOT CAUSE HYPOTHESIS:
The temporal search service appears to be filtering out commit message chunks
somewhere between the vector store search and the final results.
"""

from pathlib import Path
from unittest.mock import Mock
from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


def test_chunk_type_filter_logic_in_filter_by_time_range():
    """Test the specific filtering logic in _filter_by_time_range method.

    This test directly calls the filtering method to isolate the bug.
    Reproduces the exact scenario where commit message chunks are filtered out.
    """
    # Setup
    config_manager = Mock()
    project_root = Path("/fake/project")
    vector_store_client = Mock()
    embedding_provider = Mock()

    service = TemporalSearchService(
        config_manager=config_manager,
        project_root=project_root,
        vector_store_client=vector_store_client,
        embedding_provider=embedding_provider,
        collection_name="code-indexer-temporal",
    )

    # Create semantic results (what vector store returns)
    # This matches the exact structure from actual vector files on disk
    # Using timestamp 1704088800 = 2024-01-01 (within our test range)
    semantic_results = [
        {
            "score": 0.85,
            "payload": {
                "type": "commit_message",  # THIS IS THE KEY FIELD
                "commit_hash": "abc123",
                "commit_timestamp": 1704088800,  # 2024-01-01
                "commit_date": "2024-01-01",
                "author_name": "Test Author",
                "path": "dummy",
            },
            "chunk_text": "Fix temporal query bug",  # Content at root level
        },
    ]

    # Call _filter_by_time_range with chunk_type filter
    # Using ALL_TIME_RANGE to match user's --time-range-all flag
    filtered_results, _ = service._filter_by_time_range(
        semantic_results=semantic_results,
        start_date="1970-01-01",  # ALL_TIME_RANGE
        end_date="2100-12-31",    # ALL_TIME_RANGE
        chunk_type="commit_message",  # Filter for commit messages
    )

    # ASSERTION: Should NOT filter out the commit message
    assert len(filtered_results) == 1, (
        f"Expected 1 result after chunk_type filtering, but got {len(filtered_results)}. "
        f"The chunk_type filter is incorrectly filtering out commit messages."
    )

    assert filtered_results[0].content == "Fix temporal query bug"
