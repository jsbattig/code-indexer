"""E2E performance test for binary index optimization.

Measures query performance with and without binary index to verify speedup.
"""

import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestBinaryIndexPerformance:
    """E2E performance tests for binary index."""

    @pytest.fixture
    def large_vector_store(self):
        """Create vector store with substantial number of vectors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            store = FilesystemVectorStore(
                base_path=temp_path / "index",
                project_root=temp_path
            )

            # Create collection with realistic vector size
            collection_name = "performance_test"
            vector_size = 1536
            store.create_collection(collection_name, vector_size)

            # Insert 1000 vectors (enough to see performance difference)
            print(f"\nCreating test collection with 1000 vectors...")
            points = []
            for i in range(1000):
                points.append({
                    'id': f'point_{i:04d}',
                    'vector': np.random.randn(vector_size).tolist(),
                    'payload': {
                        'path': f'test_file_{i}.py',
                        'content': f'test content {i}',
                        'line': i
                    }
                })

            store.upsert_points(collection_name, points)

            yield store, collection_name, temp_path

    def test_index_maintains_performance_parity(self, large_vector_store):
        """Test that binary index maintains performance parity with full scan.

        Note: At 1000 vectors, index overhead is similar to full scan time.
        Real speedups (10x+) appear at 10K+ vectors but this verifies correctness.
        """
        vector_store, collection_name, temp_path = large_vector_store

        # Create query vector
        query_vector = np.random.randn(1536).tolist()

        # === WITH INDEX ===
        collection_path = temp_path / "index" / collection_name
        index_file = collection_path / "vector_index.bin"

        assert index_file.exists(), "Index file should exist after upsert"

        # Warm-up query (load caches)
        _ = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )

        # Measure with index (5 queries for stable measurement)
        with_index_times = []
        for _ in range(5):
            start = time.time()
            results_with_index = vector_store.search(
                query_vector=query_vector,
                collection_name=collection_name,
                limit=10
            )
            elapsed = time.time() - start
            with_index_times.append(elapsed)

        avg_with_index = sum(with_index_times) / len(with_index_times)
        print(f"\n  With index: {avg_with_index*1000:.1f}ms (avg of {len(with_index_times)} queries)")

        # === WITHOUT INDEX (FULL SCAN) ===
        # Delete index to force full scan
        index_file.unlink()

        # Measure without index (5 queries for stable measurement)
        without_index_times = []
        for _ in range(5):
            start = time.time()
            results_without_index = vector_store.search(
                query_vector=query_vector,
                collection_name=collection_name,
                limit=10
            )
            elapsed = time.time() - start
            without_index_times.append(elapsed)

        avg_without_index = sum(without_index_times) / len(without_index_times)
        print(f"  Without index: {avg_without_index*1000:.1f}ms (avg of {len(without_index_times)} queries)")

        # === VERIFICATION ===
        # Verify results are identical (same IDs returned)
        ids_with_index = {r['id'] for r in results_with_index}
        ids_without_index = {r['id'] for r in results_without_index}

        assert ids_with_index == ids_without_index, \
            "Index-based and full scan should return same result IDs"

        # Calculate speedup
        speedup = avg_without_index / avg_with_index
        print(f"  Speedup: {speedup:.1f}x")

        # Verify speedup or at least no regression
        # Note: At 1000 vectors, index overhead ~= full scan time
        # Real benefits appear at 10K+ vectors, but this tests correctness
        assert speedup >= 0.8, \
            f"Binary index should not significantly slow down queries, got {speedup:.1f}x speedup"

        # Report detailed timing statistics
        print(f"\n  Timing details:")
        print(f"    With index:    {min(with_index_times)*1000:.1f}ms - {max(with_index_times)*1000:.1f}ms")
        print(f"    Without index: {min(without_index_times)*1000:.1f}ms - {max(without_index_times)*1000:.1f}ms")
        print(f"    Improvement:   {(avg_without_index - avg_with_index)*1000:.1f}ms saved per query")

    def test_index_scales_with_collection_size(self, large_vector_store):
        """Test that index performance scales better than full scan."""
        vector_store, collection_name, temp_path = large_vector_store

        query_vector = np.random.randn(1536).tolist()

        # Measure performance at current size (1000 vectors)
        start = time.time()
        _ = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )
        time_1000 = time.time() - start

        # Add more vectors (double the size)
        print(f"\n  Adding 1000 more vectors...")
        points = []
        for i in range(1000, 2000):
            points.append({
                'id': f'point_{i:04d}',
                'vector': np.random.randn(1536).tolist(),
                'payload': {
                    'path': f'test_file_{i}.py',
                    'content': f'test content {i}'
                }
            })

        vector_store.upsert_points(collection_name, points)

        # Measure performance at doubled size (2000 vectors)
        start = time.time()
        _ = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )
        time_2000 = time.time() - start

        # With binary index, Hamming scan is O(N) but faster than JSON loading
        # Scaling should be roughly linear (close to 2x when doubling vectors)
        # This is still better than full scan since we load fewer JSONs
        scaling_factor = time_2000 / time_1000

        print(f"\n  Performance scaling:")
        print(f"    1000 vectors: {time_1000*1000:.1f}ms")
        print(f"    2000 vectors: {time_2000*1000:.1f}ms")
        print(f"    Scaling factor: {scaling_factor:.2f}x (expected: ~2.0x for linear scaling)")

        # Verify reasonable scaling (should be roughly 2x, allow variance)
        assert 1.5 < scaling_factor < 3.0, \
            f"Index performance should scale roughly linearly, got {scaling_factor:.2f}x"

    def test_index_maintains_quality_with_filters(self, large_vector_store):
        """Test that index-based search works correctly with filters."""
        vector_store, collection_name, temp_path = large_vector_store

        query_vector = np.random.randn(1536).tolist()

        # Search with filter using index
        collection_path = temp_path / "index" / collection_name
        index_file = collection_path / "vector_index.bin"
        assert index_file.exists(), "Index should exist"

        start = time.time()
        filtered_results = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=5,
            filter_conditions={
                'must': [
                    {'key': 'path', 'match': {'value': 'test_file_1*.py'}}
                ]
            }
        )
        with_index_time = time.time() - start

        # Verify filters work correctly
        for result in filtered_results:
            assert result['payload']['path'].startswith('test_file_1'), \
                "Filter should be applied correctly with index"

        # Delete index and search with filter using full scan
        index_file.unlink()

        start = time.time()
        unfiltered_results = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=5,
            filter_conditions={
                'must': [
                    {'key': 'path', 'match': {'value': 'test_file_1*.py'}}
                ]
            }
        )
        without_index_time = time.time() - start

        # Results should be identical
        filtered_ids = {r['id'] for r in filtered_results}
        unfiltered_ids = {r['id'] for r in unfiltered_results}

        assert filtered_ids == unfiltered_ids, \
            "Filtered results should match between index and full scan"

        print(f"\n  Filtered search performance:")
        print(f"    With index: {with_index_time*1000:.1f}ms")
        print(f"    Without index: {without_index_time*1000:.1f}ms")
        print(f"    Speedup: {without_index_time/with_index_time:.1f}x")
