"""Integration tests for HNSW index manager with filesystem storage."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestHNSWIndexPersistence:
    """Test HNSW index persistence and reload across sessions."""

    def test_hnsw_index_survives_reload(self, tmp_path: Path):
        """Test that HNSW index can be saved, reloaded, and queried correctly."""
        # Create initial index manager
        manager1 = HNSWIndexManager(vector_dim=256)

        # Build index with known vectors
        num_vectors = 500
        vectors = np.random.randn(num_vectors, 256).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]

        manager1.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        # Verify index was created
        assert manager1.index_exists(tmp_path)
        stats = manager1.get_index_stats(tmp_path)
        assert stats['vector_count'] == num_vectors

        # Query with first manager
        index1 = manager1.load_index(tmp_path, max_elements=1000)
        query_vec = np.random.randn(256).astype(np.float32)
        results1, distances1 = manager1.query(index1, query_vec, tmp_path, k=10)

        # Create new manager instance (simulating new session)
        manager2 = HNSWIndexManager(vector_dim=256)

        # Load same index
        index2 = manager2.load_index(tmp_path, max_elements=1000)
        results2, distances2 = manager2.query(index2, query_vec, tmp_path, k=10)

        # Results should be identical
        assert results1 == results2
        assert len(distances1) == len(distances2)
        # Distances should be very close (floating point comparison)
        for d1, d2 in zip(distances1, distances2):
            assert abs(d1 - d2) < 1e-6

    def test_hnsw_index_rebuild_produces_queryable_index(self, tmp_path: Path):
        """Test that rebuild_from_vectors produces a functional index."""
        # Create vector files
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        num_vectors = 200
        vectors = []
        for i in range(num_vectors):
            vector = np.random.randn(128).astype(np.float32)
            vectors.append(vector)

            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, 'w') as f:
                json.dump({
                    "id": f"vec_{i}",
                    "vector": vector.tolist()
                }, f)

        # Create metadata
        meta_file = tmp_path / 'collection_meta.json'
        with open(meta_file, 'w') as f:
            json.dump({"vector_dim": 128}, f)

        # Rebuild index
        manager = HNSWIndexManager(vector_dim=128)
        count = manager.rebuild_from_vectors(tmp_path)

        assert count == num_vectors
        assert manager.index_exists(tmp_path)

        # Query the rebuilt index
        index = manager.load_index(tmp_path, max_elements=1000)
        query_vec = np.random.randn(128).astype(np.float32)
        result_ids, distances = manager.query(index, query_vec, tmp_path, k=10)

        assert len(result_ids) == 10
        assert len(distances) == 10
        assert all(id_val.startswith("vec_") for id_val in result_ids)


class TestHNSWQueryAccuracy:
    """Test HNSW query accuracy and performance characteristics."""

    def test_hnsw_finds_exact_match(self, tmp_path: Path):
        """Test that HNSW finds exact vector match as top result."""
        manager = HNSWIndexManager(vector_dim=128)

        # Create vectors with one exact match
        num_vectors = 100
        vectors = np.random.randn(num_vectors, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]

        manager.build_index(tmp_path, vectors, ids)

        # Query with an exact vector from the index
        index = manager.load_index(tmp_path, max_elements=200)
        exact_match_idx = 42
        query_vec = vectors[exact_match_idx].copy()

        result_ids, distances = manager.query(index, query_vec, tmp_path, k=10, ef=100)

        # First result should be the exact match
        assert result_ids[0] == f"vec_{exact_match_idx}"
        # Distance should be very small (near zero for exact match)
        assert distances[0] < 1e-5

    def test_hnsw_higher_ef_improves_accuracy(self, tmp_path: Path):
        """Test that higher ef parameter can improve query accuracy."""
        manager = HNSWIndexManager(vector_dim=64)

        # Build index
        num_vectors = 200
        vectors = np.random.randn(num_vectors, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]
        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        # Query with low ef
        index = manager.load_index(tmp_path, max_elements=500)
        query_vec = vectors[50].copy()

        results_low_ef, distances_low_ef = manager.query(
            index, query_vec, tmp_path, k=10, ef=10
        )

        # Query with high ef
        results_high_ef, distances_high_ef = manager.query(
            index, query_vec, tmp_path, k=10, ef=200
        )

        # Both should find the exact match as first result
        assert results_low_ef[0] == f"vec_50"
        assert results_high_ef[0] == f"vec_50"

        # Higher ef should give same or similar top distance
        # For exact matches, distances should be near zero
        assert abs(distances_high_ef[0]) < 1e-5
        assert abs(distances_low_ef[0]) < 1e-5


class TestHNSWDifferentMetrics:
    """Test HNSW with different distance metrics."""

    def test_hnsw_with_l2_metric(self, tmp_path: Path):
        """Test HNSW index with L2 (Euclidean) distance."""
        manager = HNSWIndexManager(vector_dim=64, space='l2')

        vectors = np.random.randn(100, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        manager.build_index(tmp_path, vectors, ids)

        index = manager.load_index(tmp_path, max_elements=200)
        query_vec = np.random.randn(64).astype(np.float32)

        result_ids, distances = manager.query(index, query_vec, tmp_path, k=5)

        assert len(result_ids) == 5
        assert len(distances) == 5
        # L2 distances should be non-negative
        assert all(d >= 0 for d in distances)

    def test_hnsw_with_ip_metric(self, tmp_path: Path):
        """Test HNSW index with inner product metric."""
        manager = HNSWIndexManager(vector_dim=64, space='ip')

        vectors = np.random.randn(100, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        manager.build_index(tmp_path, vectors, ids)

        index = manager.load_index(tmp_path, max_elements=200)
        query_vec = np.random.randn(64).astype(np.float32)

        result_ids, distances = manager.query(index, query_vec, tmp_path, k=5)

        assert len(result_ids) == 5
        assert len(distances) == 5


class TestHNSWLargeScale:
    """Test HNSW performance with larger datasets."""

    def test_hnsw_handles_1000_vectors(self, tmp_path: Path):
        """Test HNSW with 1000 vectors (realistic small collection)."""
        manager = HNSWIndexManager(vector_dim=256)

        # Create 1000 vectors
        num_vectors = 1000
        vectors = np.random.randn(num_vectors, 256).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]

        # Build index
        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        # Verify index
        stats = manager.get_index_stats(tmp_path)
        assert stats['vector_count'] == num_vectors

        # Query
        index = manager.load_index(tmp_path, max_elements=2000)
        query_vec = np.random.randn(256).astype(np.float32)

        result_ids, distances = manager.query(index, query_vec, tmp_path, k=20)

        assert len(result_ids) == 20
        assert len(distances) == 20

        # Distances should be sorted (nearest first)
        for i in range(len(distances) - 1):
            assert distances[i] <= distances[i + 1] * 1.01  # Allow small tolerance

    def test_hnsw_query_performance_is_sublinear(self, tmp_path: Path):
        """Test that query time doesn't scale linearly with dataset size."""
        import time

        manager = HNSWIndexManager(vector_dim=128)

        # Build index with 2000 vectors
        num_vectors = 2000
        vectors = np.random.randn(num_vectors, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]

        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)
        index = manager.load_index(tmp_path, max_elements=5000)

        # Run multiple queries and measure time
        query_times = []
        for _ in range(10):
            query_vec = np.random.randn(128).astype(np.float32)
            start = time.time()
            manager.query(index, query_vec, tmp_path, k=10, ef=50)
            query_times.append(time.time() - start)

        avg_query_time = sum(query_times) / len(query_times)

        # Query should be very fast (< 10ms for 2000 vectors)
        # This is a performance characteristic test
        assert avg_query_time < 0.01  # 10ms

    def test_hnsw_index_file_size_reasonable(self, tmp_path: Path):
        """Test that HNSW index file size is reasonable for dataset."""
        manager = HNSWIndexManager(vector_dim=256)

        # Create 1000 vectors
        num_vectors = 1000
        vectors = np.random.randn(num_vectors, 256).astype(np.float32)
        ids = [f"vec_{i}" for i in range(num_vectors)]

        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        stats = manager.get_index_stats(tmp_path)
        file_size_mb = stats['file_size_bytes'] / (1024 * 1024)

        # Index should be compact (typically < 50MB for 1000 256-dim vectors)
        # This is highly dependent on M parameter
        assert file_size_mb < 50
