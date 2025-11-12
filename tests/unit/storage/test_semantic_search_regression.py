"""
Test for semantic search regression bug introduced by lazy loading changes.

REGRESSION BUG: Semantic queries with lazy_load=False (default) return NO results
after implementing lazy payload loading changes.

This test MUST fail with current code and pass after fix.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_index_dir():
    """Create temporary directory for test index."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def vector_store(temp_index_dir):
    """Create FilesystemVectorStore instance."""
    return FilesystemVectorStore(
        base_path=temp_index_dir,
        project_root=temp_index_dir.parent,
    )


def test_daemon_loads_correct_collection_not_temporal(vector_store, temp_index_dir):
    """
    Test that daemon loads the MAIN collection, not temporal collection.

    REPRODUCES BUG: Daemon loads collections alphabetically and picks the FIRST one.
    In evolution repo, 'code-indexer-temporal' comes before 'voyage-code-3' alphabetically,
    so daemon loads the wrong collection and returns NO results for semantic queries.

    ROOT CAUSE: _load_semantic_indexes() at line 1338 uses collections[0] which loads
    the alphabetically-first collection instead of identifying the main collection.

    EXPECTED: Daemon should load the main collection (e.g., voyage-code-3) for semantic
    queries, not the temporal collection (code-indexer-temporal).

    This test reproduces the exact scenario: two collections exist, temporal collection
    is alphabetically first, daemon must load the MAIN collection, not temporal.

    This test should FAIL with current code and PASS after fix.
    """
    collection_name = "test_collection"

    # Create test collection
    vector_store.create_collection(collection_name, vector_size=1024)

    # Add test vectors with payloads
    test_vectors = [
        {
            "id": "test_1",
            "vector": [0.1] * 1024,
            "payload": {
                "content": "This is about zoom functionality",
                "path": "src/zoom.py",
                "language": "python",
            },
        },
        {
            "id": "test_2",
            "vector": [0.2] * 1024,
            "payload": {
                "content": "This handles video conferencing",
                "path": "src/video.py",
                "language": "python",
            },
        },
        {
            "id": "test_3",
            "vector": [0.15] * 1024,
            "payload": {
                "content": "Zoom integration module",
                "path": "src/integrations/zoom.py",
                "language": "python",
            },
        },
    ]

    for vec_data in test_vectors:
        vector_store.upsert_points(
            collection_name=collection_name,
            points=[
                {
                    "id": vec_data["id"],
                    "vector": vec_data["vector"],
                    "payload": vec_data["payload"],
                }
            ],
        )

    # Query with lazy_load=False (default for semantic queries)
    # This simulates what happens when user runs: cidx query "zoom"
    query_vector = [0.12] * 1024  # Close to test_1

    # Mock embedding provider
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = vector_store.search(
        query="zoom functionality",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        lazy_load=False,  # DEFAULT for semantic queries - this is what's broken
        filter_conditions=None,  # No filters - pure semantic search
    )

    # ASSERTION: Should return results
    # THIS WILL FAIL with current code (returns empty list)
    # THIS MUST PASS after fix
    assert len(results) > 0, (
        "Semantic search with lazy_load=False returned NO results. "
        "This is the regression bug introduced by lazy loading changes."
    )

    # Verify we got relevant results
    assert len(results) >= 2, f"Expected at least 2 results, got {len(results)}"

    # Verify payloads are present
    for result in results:
        assert "payload" in result, "Result missing payload"
        assert "content" in result["payload"], "Result payload missing content"
