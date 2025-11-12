"""
Test for chunk-type filtering bug (Story #476).

ISSUE: --chunk-type commit_message returns 0 results when it should return commit messages.

This test reproduces the bug by directly calling the filter method with realistic data.
"""

from unittest.mock import MagicMock

from src.code_indexer.services.temporal.temporal_search_service import TemporalSearchService


def test_chunk_type_filter_with_realistic_data():
    """
    Test that _filter_by_time_range correctly filters by chunk_type.

    This test uses realistic data structures matching what FilesystemVectorStore returns.

    BUG REPRODUCTION:
    - User reports that --chunk-type commit_message returns 0 results
    - Without the filter, returns 20 mixed results
    - This suggests the filter is incorrectly filtering out commit_message chunks
    """
    # Create mock config manager
    mock_config_manager = MagicMock()
    mock_config = MagicMock()
    from pathlib import Path
    mock_config.codebase_dir = Path("/tmp/test")
    mock_config_manager.get_config.return_value = mock_config

    # Create TemporalSearchService
    service = TemporalSearchService(
        config_manager=mock_config_manager,
        project_root=Path("/tmp/test"),
        vector_store_client=None,  # Not needed for this test
        embedding_provider=None,  # Not needed for this test
    )

    # Create realistic search results matching FilesystemVectorStore output
    # This is what the vector store returns: list of dicts with id, score, payload, chunk_text
    semantic_results = [
        {
            "id": "test:commit:abc123:0",
            "score": 0.9,
            "payload": {
                "type": "commit_message",  # This should match the filter
                "commit_hash": "abc123",
                "commit_timestamp": 1704153600,  # 2024-01-02 00:00:00 UTC
                "commit_date": "2024-01-02",
                "author_name": "Test User",
                "author_email": "test@example.com",
                "chunk_index": 0,
            },
            "chunk_text": "Add exception logging infrastructure",
        },
        {
            "id": "test:diff:def456:file.py:0",
            "score": 0.85,
            "payload": {
                "type": "commit_diff",  # This should NOT match the filter
                "diff_type": "modified",
                "commit_hash": "def456",
                "commit_timestamp": 1704240000,  # 2024-01-03 00:00:00 UTC
                "commit_date": "2024-01-03",
                "author_name": "Test User",
                "author_email": "test@example.com",
                "path": "file.py",
                "chunk_index": 0,
            },
            "chunk_text": "def authenticate():",
        },
    ]

    # Call _filter_by_time_range with chunk_type filter
    filtered_results, _ = service._filter_by_time_range(
        semantic_results=semantic_results,
        start_date="2024-01-01",
        end_date="2024-12-31",
        chunk_type="commit_message",  # Filter to commit_message only
    )

    # ASSERTION: Should return exactly 1 result (the commit_message)
    # Bug would cause this to return 0 results
    assert len(filtered_results) == 1, (
        f"Expected 1 commit_message result but got {len(filtered_results)} results. "
        f"Bug: chunk_type filter not working correctly."
    )

    # VERIFICATION: The result should be the commit_message
    assert filtered_results[0].metadata["type"] == "commit_message", (
        f"Expected type='commit_message' but got type='{filtered_results[0].metadata['type']}'"
    )
    assert "exception logging" in filtered_results[0].content.lower(), (
        f"Expected commit message content but got: {filtered_results[0].content}"
    )
