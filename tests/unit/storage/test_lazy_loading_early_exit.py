"""Unit tests for lazy loading with early exit optimization.

Tests that the vector store can load payloads on-demand and exit early
when enough results are found, reducing JSON I/O operations.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_store(tmp_path):
    """Create temporary filesystem vector store."""
    store = FilesystemVectorStore(base_path=tmp_path / "vectors", project_root=tmp_path)
    return store


@pytest.fixture
def large_temporal_store(temp_store):
    """Create store with large temporal dataset to test early exit."""
    collection_name = "test_temporal_large"
    temp_store.create_collection(collection_name, vector_size=4)

    # Create 50 test vectors, but only first 10 match our filter
    points = []
    for i in range(50):
        is_match = i < 10  # First 10 match time range
        points.append(
            {
                "id": f"commit{i}_file",
                "vector": [1.0 - (i * 0.01), i * 0.01, 0.0, 0.0],
                "payload": {
                    "path": f"src/file{i}.py",
                    "language": "python",
                    "commit_hash": f"hash{i}",
                    "commit_timestamp": (
                        1609459200 + (i * 86400) if is_match else 1640995200 + i
                    ),  # Match vs no-match
                    "author_name": "John Doe" if is_match else "Jane Smith",
                    "diff_type": "modified",
                },
            }
        )

    temp_store.begin_indexing(collection_name)
    temp_store.upsert_points(collection_name, points)
    temp_store.end_indexing(collection_name)
    return temp_store, collection_name


def test_lazy_loading_early_exit_reduces_json_loads(large_temporal_store):
    """Test that lazy loading with early exit loads fewer JSONs than eager loading.

    This test verifies the core optimization: with restrictive filters and early exit,
    we should load significantly fewer JSON files than the prefetch limit.
    """
    store, collection_name = large_temporal_store

    # Filter that matches only first 10 results (narrow time range)
    filter_conditions = {
        "must": [
            {
                "key": "commit_timestamp",
                "range": {
                    "gte": 1609459200,  # Start of matching range
                    "lte": 1609459200 + (9 * 86400),  # End of matching range (10 days)
                },
            }
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    # Track how many JSON files are opened
    original_open = open
    json_loads_count = 0

    def counting_open(*args, **kwargs):
        nonlocal json_loads_count
        if len(args) > 0 and isinstance(args[0], (str, Path)):
            path_str = str(args[0])
            if path_str.endswith(".json") and "collection_meta.json" not in path_str:
                json_loads_count += 1
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=counting_open):
        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=10,
            filter_conditions=filter_conditions,
            lazy_load=True,  # Enable lazy loading
            prefetch_limit=50,  # Prefetch more candidates than we need
        )

    # Should return exactly 10 results (our limit)
    assert len(results) == 10

    # Key assertion: With lazy loading and early exit, we should load ~10-15 JSONs
    # instead of all 50. Allow some overhead for HNSW ordering, but should be << 50.
    assert json_loads_count < 25, (
        f"Lazy loading should load ~10-15 JSONs but loaded {json_loads_count}. "
        f"Early exit optimization may not be working."
    )
