"""Test for Story #476: chunk_type parameter missing from filter_conditions.

ROOT CAUSE:
The query_temporal() method accepts chunk_type parameter but never adds it
to filter_conditions that are passed to the vector store search. This means:
1. Vector store searches across ALL chunk types (commit_message AND commit_diff)
2. Post-filter at line 635-639 tries to filter by chunk_type
3. But if commit_message chunks aren't semantically similar enough to the query,
   they never make it into the search results to be post-filtered

FIX:
Add chunk_type to filter_conditions before calling vector_store.search()
so the vector store only searches within the requested chunk type.
"""

from pathlib import Path
from unittest.mock import Mock
from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
    ALL_TIME_RANGE,
)


def test_chunk_type_added_to_filter_conditions():
    """Test that chunk_type parameter is added to filter_conditions for vector store.

    This is the root cause test. The bug is that chunk_type is accepted as a
    parameter but never added to filter_conditions, so the vector store searches
    across ALL chunk types instead of filtering at the vector store level.
    """
    # Setup
    config_manager = Mock()
    project_root = Path("/fake/project")

    # Mock vector store client to capture filter_conditions
    # Return a single mock result to avoid RuntimeError from empty results
    # Note: For non-FilesystemVectorStore mocks, search() returns list directly (not tuple)
    mock_result = {
        "id": "test:commit:abc:0",
        "score": 0.85,
        "payload": {
            "type": "commit_message",
            "commit_hash": "abc",
            "path": "dummy",
            "commit_timestamp": 1704088800,
        },
        "chunk_text": "test content",
    }
    vector_store_client = Mock()
    vector_store_client.collection_exists.return_value = True
    vector_store_client.search.return_value = [mock_result]  # List, not tuple

    embedding_provider = Mock()
    embedding_provider.get_embedding.return_value = [0.1] * 1024

    service = TemporalSearchService(
        config_manager=config_manager,
        project_root=project_root,
        vector_store_client=vector_store_client,
        embedding_provider=embedding_provider,
        collection_name="code-indexer-temporal",
    )

    # Execute query with chunk_type filter
    service.query_temporal(
        query="temporal",
        time_range=ALL_TIME_RANGE,
        chunk_type="commit_message",  # This should be added to filter_conditions
        limit=10,
    )

    # Verify vector_store.search was called
    assert (
        vector_store_client.search.called
    ), "Vector store search should have been called"

    # Get the filter_conditions that were passed to the vector store
    call_args = vector_store_client.search.call_args
    filter_conditions = (
        call_args[1].get("filter_conditions", {}) if call_args[1] else {}
    )

    # ASSERTION: filter_conditions should contain chunk_type filter
    # This will FAIL with current implementation
    must_conditions = filter_conditions.get("must", [])

    # Look for a condition that filters by type field
    type_filter_found = any(
        condition.get("key") == "type"
        and condition.get("match", {}).get("value") == "commit_message"
        for condition in must_conditions
    )

    assert type_filter_found, (
        f"Expected chunk_type filter in filter_conditions, but got: {filter_conditions}\n"
        f"The chunk_type='commit_message' parameter should be converted to:\n"
        f"  {{'key': 'type', 'match': {{'value': 'commit_message'}}}}\n"
        f"and added to filter_conditions['must'] before calling vector_store.search()"
    )
