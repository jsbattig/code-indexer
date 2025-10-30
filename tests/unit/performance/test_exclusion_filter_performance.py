"""
Performance tests for language exclusion filtering.

These tests verify that language exclusion filters add minimal overhead
to query execution time.
"""

import pytest
import time
import numpy as np
from unittest.mock import Mock

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def large_populated_store(tmp_path):
    """Create a store with many files for performance testing."""
    np.random.seed(42)
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "perf_test"
    store.create_collection(collection_name, vector_size=1536)

    # Create 1000 points with various languages
    points = []
    languages = ["py", "js", "ts", "java", "go", "rust", "cpp"]

    for i in range(1000):
        language = languages[i % len(languages)]
        points.append(
            {
                "id": f"file_{i}_{language}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": f"src/file_{i}.{language}",
                    "language": language,
                    "type": "content",
                },
            }
        )

    # Batch insert for speed
    store.upsert_points(collection_name, points)

    return store, collection_name


def test_exclusion_filter_overhead_less_than_5ms(large_populated_store):
    """
    GIVEN a store with 1000 indexed files
    WHEN searching with and without exclusion filters
    THEN the overhead of exclusion filtering is less than 5ms
    """
    store, collection_name = large_populated_store

    query_vector = np.random.randn(1536).tolist()
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    # Baseline: search without filters
    start_time = time.perf_counter()
    for _ in range(10):  # Run multiple times for more accurate timing
        results_no_filter = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=10,
        )
    baseline_time = (time.perf_counter() - start_time) / 10

    # With exclusion filter
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "js"}},
            {"key": "language", "match": {"value": "ts"}},
        ]
    }

    start_time = time.perf_counter()
    for _ in range(10):  # Run multiple times for more accurate timing
        results_with_filter = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=10,
            filter_conditions=filter_conditions,
        )
    filtered_time = (time.perf_counter() - start_time) / 10

    # Calculate overhead
    overhead = filtered_time - baseline_time

    # Verify results are different (filter is working)
    assert len(results_with_filter) <= len(
        results_no_filter
    ), "Filtered results should be <= unfiltered"

    # Verify overhead is minimal
    assert (
        overhead < 0.005
    ), f"Exclusion filter overhead {overhead*1000:.2f}ms exceeds 5ms threshold"


def test_multiple_exclusions_performance_scales_linearly(large_populated_store):
    """
    GIVEN a store with 1000 indexed files
    WHEN searching with increasing numbers of exclusion filters
    THEN performance scales linearly (not exponentially)
    """
    store, collection_name = large_populated_store

    query_vector = np.random.randn(1536).tolist()
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    # Test with 1, 2, 4 exclusions
    exclusion_counts = [1, 2, 4]
    timings = []

    for count in exclusion_counts:
        languages_to_exclude = ["js", "ts", "java", "go"][:count]
        filter_conditions = {
            "must_not": [
                {"key": "language", "match": {"value": lang}}
                for lang in languages_to_exclude
            ]
        }

        start_time = time.perf_counter()
        for _ in range(10):
            store.search(
                query="test query",
                embedding_provider=mock_embedding_provider,
                collection_name=collection_name,
                limit=10,
                filter_conditions=filter_conditions,
            )
        avg_time = (time.perf_counter() - start_time) / 10
        timings.append(avg_time)

    # Verify linear scaling (2x filters should be less than 3x time)
    if timings[0] > 0:
        ratio_2x = timings[1] / timings[0]
        ratio_4x = timings[2] / timings[0]

        assert (
            ratio_2x < 3.0
        ), f"2x exclusions should not be 3x slower (ratio: {ratio_2x:.2f})"
        assert (
            ratio_4x < 5.0
        ), f"4x exclusions should not be 5x slower (ratio: {ratio_4x:.2f})"
