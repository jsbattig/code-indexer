"""Integration tests for VectorIndexManager integration with FilesystemVectorStore.

Tests index creation during upsert and index-based search optimization.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.storage.vector_index_manager import VectorIndexManager


class TestFilesystemVectorStoreIndexIntegration:
    """Integration tests for binary index with FilesystemVectorStore."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def vector_store(self, temp_storage):
        """Create FilesystemVectorStore instance."""
        return FilesystemVectorStore(
            base_path=temp_storage / "index",
            project_root=temp_storage
        )

    @pytest.fixture
    def index_manager(self):
        """Create VectorIndexManager instance."""
        return VectorIndexManager()

    def test_upsert_creates_index_file(self, vector_store, temp_storage):
        """Test that upsert_points creates binary index file."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert some points
        points = [
            {
                'id': f'point_{i}',
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'file_{i}.py', 'content': f'content {i}'}
            }
            for i in range(10)
        ]

        vector_store.upsert_points(collection_name, points)

        # Check that index file was created
        collection_path = temp_storage / "index" / collection_name
        index_file = collection_path / "vector_index.bin"

        # This should pass after integration
        assert index_file.exists(), "Binary index file should be created during upsert"

        # Verify index file size (40 bytes per entry * 10 entries)
        assert index_file.stat().st_size == 400, "Index file should contain 10 entries (40 bytes each)"

    def test_index_contains_correct_entries(self, vector_store, index_manager, temp_storage):
        """Test that index contains correct vector IDs and hashes."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert points with known vectors
        point_ids = ['point_1', 'point_2', 'point_3']
        points = [
            {
                'id': pid,
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'{pid}.py'}
            }
            for pid in point_ids
        ]

        vector_store.upsert_points(collection_name, points)

        # Load index
        collection_path = temp_storage / "index" / collection_name
        index, id_mapping = index_manager.load_index(collection_path)

        # This should pass after integration
        assert index.shape[0] == 3, "Index should contain 3 entries"
        assert len(id_mapping) == 3, "ID mapping should contain 3 entries"

        # Verify all point IDs are in the mapping (now preserved from JSON files)
        mapped_ids = set(id_mapping.values())
        for pid in point_ids:
            assert pid in mapped_ids, f"Point ID {pid} should be in index mapping"

    def test_search_uses_index_when_available(self, vector_store, temp_storage):
        """Test that search method uses binary index for candidate selection."""
        # Create collection with sufficient vectors
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert many points to make index beneficial
        num_vectors = 100
        points = [
            {
                'id': f'point_{i}',
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'file_{i}.py', 'content': f'content {i}'}
            }
            for i in range(num_vectors)
        ]

        vector_store.upsert_points(collection_name, points)

        # Perform search
        query_vector = np.random.randn(vector_size).tolist()
        results = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )

        # This should pass after integration
        # Verify results are returned (search works with index)
        assert len(results) > 0, "Search should return results using index"
        assert len(results) <= 10, "Search should respect limit parameter"

        # Verify index file exists (was used during search)
        collection_path = temp_storage / "index" / collection_name
        index_file = collection_path / "vector_index.bin"
        assert index_file.exists(), "Index file should exist and be used for search"

    def test_search_falls_back_without_index(self, vector_store, temp_storage):
        """Test that search works even if index file is missing (graceful fallback)."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert points
        points = [
            {
                'id': f'point_{i}',
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'file_{i}.py', 'content': f'content {i}'}
            }
            for i in range(20)
        ]

        vector_store.upsert_points(collection_name, points)

        # Delete index file to force fallback
        collection_path = temp_storage / "index" / collection_name
        index_file = collection_path / "vector_index.bin"
        if index_file.exists():
            index_file.unlink()

        # Search should still work via fallback
        query_vector = np.random.randn(vector_size).tolist()
        results = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=5
        )

        # This should pass after integration
        assert len(results) > 0, "Search should work via fallback when index missing"
        assert len(results) <= 5, "Search fallback should respect limit"

    def test_index_rebuild_recreates_entries(self, vector_store, index_manager, temp_storage):
        """Test that rebuild_from_vectors correctly recreates index."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert points
        num_points = 15
        points = [
            {
                'id': f'point_{i}',
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'file_{i}.py'}
            }
            for i in range(num_points)
        ]

        vector_store.upsert_points(collection_name, points)

        # Get original index state
        collection_path = temp_storage / "index" / collection_name
        index_orig, id_mapping_orig = index_manager.load_index(collection_path)

        # Delete index file
        index_file = collection_path / "vector_index.bin"
        index_file.unlink()

        # Rebuild index
        index_manager.rebuild_from_vectors(collection_path)

        # Load rebuilt index
        index_rebuilt, id_mapping_rebuilt = index_manager.load_index(collection_path)

        # This should pass after integration
        assert index_rebuilt.shape == index_orig.shape, "Rebuilt index should have same shape"
        assert len(id_mapping_rebuilt) == len(id_mapping_orig), "Rebuilt mapping should have same size"

        # Verify all IDs are present
        assert set(id_mapping_rebuilt.values()) == set(id_mapping_orig.values()), \
            "Rebuilt index should contain same vector IDs"

    def test_concurrent_upserts_maintain_index_integrity(self, vector_store, index_manager, temp_storage):
        """Test that concurrent upserts maintain index file integrity."""
        import threading

        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Define worker function for concurrent upserts
        def upsert_batch(start_idx, count):
            points = [
                {
                    'id': f'point_{start_idx + i}',
                    'vector': np.random.randn(vector_size).tolist(),
                    'payload': {'path': f'file_{start_idx + i}.py'}
                }
                for i in range(count)
            ]
            vector_store.upsert_points(collection_name, points)

        # Run concurrent upserts
        threads = []
        for i in range(5):
            thread = threading.Thread(target=upsert_batch, args=(i * 10, 10))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify index integrity
        collection_path = temp_storage / "index" / collection_name
        index, id_mapping = index_manager.load_index(collection_path)

        # This should pass after integration
        assert index.shape[0] == 50, "Index should contain 50 entries from concurrent upserts"
        assert len(id_mapping) == 50, "ID mapping should contain 50 unique entries"

    def test_index_based_search_returns_same_results_as_full_scan(self, vector_store, temp_storage):
        """Test that index-based search returns same results as full scan."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Upsert points
        num_points = 50
        points = [
            {
                'id': f'point_{i}',
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {'path': f'file_{i}.py', 'content': f'content {i}'}
            }
            for i in range(num_points)
        ]

        vector_store.upsert_points(collection_name, points)

        # Perform search WITH index
        query_vector = np.random.randn(vector_size).tolist()
        results_with_index = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )

        # Delete index and perform search WITHOUT index (full scan)
        collection_path = temp_storage / "index" / collection_name
        index_file = collection_path / "vector_index.bin"
        index_file.unlink()

        results_without_index = vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            limit=10
        )

        # This should pass after integration
        # Results should be identical (same IDs and scores)
        assert len(results_with_index) == len(results_without_index), \
            "Index-based and full scan should return same number of results"

        # Extract IDs and scores for comparison
        ids_with_index = {r['id']: r['score'] for r in results_with_index}
        ids_without_index = {r['id']: r['score'] for r in results_without_index}

        assert set(ids_with_index.keys()) == set(ids_without_index.keys()), \
            "Index-based and full scan should return same result IDs"

        # Scores should be approximately equal
        for result_id in ids_with_index:
            assert abs(ids_with_index[result_id] - ids_without_index[result_id]) < 1e-6, \
                f"Scores should match for {result_id}"

    def test_collection_metadata_contains_index_tracking(self, vector_store, temp_storage):
        """Test that collection metadata includes index tracking fields."""
        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        vector_store.create_collection(collection_name, vector_size)

        # Load metadata
        collection_path = temp_storage / "index" / collection_name
        metadata_path = collection_path / "collection_meta.json"

        with open(metadata_path) as f:
            metadata = json.load(f)

        # This should pass after integration
        assert 'index_version' in metadata, "Metadata should contain index_version"
        assert 'index_format' in metadata, "Metadata should contain index_format"
        assert 'index_record_size' in metadata, "Metadata should contain index_record_size"

        assert metadata['index_version'] == 1, "Index version should be 1"
        assert metadata['index_format'] == 'binary_v1', "Index format should be binary_v1"
        assert metadata['index_record_size'] == 40, "Index record size should be 40 bytes"
