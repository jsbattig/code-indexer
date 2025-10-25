"""Integration tests for Matrix Multiplication Service with FilesystemVectorStore.

Story 9: Matrix Multiplication Resident Service
Tests AC: Service integration with indexing pipeline
"""

import numpy as np
import pytest
import tempfile
from pathlib import Path
import shutil

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.matrix_service_client import MatrixServiceClient


class TestMatrixServiceIntegration:
    """Test matrix multiplication service integration with indexing pipeline."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.base_path = self.temp_dir / ".code-indexer" / "index"
        self.project_root = self.temp_dir

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_filesystem_vector_store_uses_matrix_service(self):
        """Test FilesystemVectorStore uses MatrixServiceClient for matrix multiplication."""
        # Create vector store with matrix service enabled
        store = FilesystemVectorStore(
            base_path=self.base_path,
            project_root=self.project_root,
            use_matrix_service=True
        )

        # Verify matrix client is initialized
        assert store.matrix_client is not None
        assert isinstance(store.matrix_client, MatrixServiceClient)
        assert store.use_matrix_service is True

    def test_filesystem_vector_store_without_matrix_service(self):
        """Test FilesystemVectorStore works without matrix service."""
        # Create vector store with matrix service disabled
        store = FilesystemVectorStore(
            base_path=self.base_path,
            project_root=self.project_root,
            use_matrix_service=False
        )

        # Verify matrix client is not initialized
        assert store.matrix_client is None
        assert store.use_matrix_service is False

    def test_upsert_points_with_matrix_service_fallback(self):
        """Test upsert_points uses matrix service with in-process fallback."""
        # Create vector store with matrix service enabled
        store = FilesystemVectorStore(
            base_path=self.base_path,
            project_root=self.project_root,
            use_matrix_service=True
        )

        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        store.create_collection(collection_name, vector_size)

        # Create test points
        points = [
            {
                'id': f"test_{i}",
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {
                    'path': f'test_file_{i}.py',
                    'start_line': 1,
                    'end_line': 10,
                    'content': f'Test content {i}'
                }
            }
            for i in range(5)
        ]

        # Upsert points (should use matrix service with fallback)
        result = store.upsert_points(collection_name, points)

        # Verify upsert succeeded
        assert result['status'] == 'ok'
        assert result['count'] == 5

        # Verify points were stored
        assert store.count_points(collection_name) == 5

    def test_upsert_points_without_matrix_service(self):
        """Test upsert_points works with direct matrix multiplication."""
        # Create vector store with matrix service disabled
        store = FilesystemVectorStore(
            base_path=self.base_path,
            project_root=self.project_root,
            use_matrix_service=False
        )

        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        store.create_collection(collection_name, vector_size)

        # Create test points
        points = [
            {
                'id': f"test_{i}",
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {
                    'path': f'test_file_{i}.py',
                    'start_line': 1,
                    'end_line': 10,
                    'content': f'Test content {i}'
                }
            }
            for i in range(5)
        ]

        # Upsert points (should use direct multiplication)
        result = store.upsert_points(collection_name, points)

        # Verify upsert succeeded
        assert result['status'] == 'ok'
        assert result['count'] == 5

        # Verify points were stored
        assert store.count_points(collection_name) == 5

    def test_matrix_service_and_direct_produce_same_results(self):
        """Test matrix service and direct multiplication produce identical results."""
        # Create two vector stores: one with service, one without
        store_with_service = FilesystemVectorStore(
            base_path=self.base_path / "with_service",
            project_root=self.project_root,
            use_matrix_service=True
        )

        store_without_service = FilesystemVectorStore(
            base_path=self.base_path / "without_service",
            project_root=self.project_root,
            use_matrix_service=False
        )

        # Create collections with same parameters
        collection_name = "test_collection"
        vector_size = 1536

        store_with_service.create_collection(collection_name, vector_size)
        store_without_service.create_collection(collection_name, vector_size)

        # Copy projection matrix to ensure same matrix is used
        matrix_file_src = self.base_path / "with_service" / collection_name / "projection_matrix.yaml"
        matrix_file_dst = self.base_path / "without_service" / collection_name / "projection_matrix.yaml"
        shutil.copy(matrix_file_src, matrix_file_dst)

        # Create same test point
        test_vector = np.random.randn(vector_size)
        point = {
            'id': "test_1",
            'vector': test_vector.tolist(),
            'payload': {
                'path': 'test_file.py',
                'start_line': 1,
                'end_line': 10,
                'content': 'Test content'
            }
        }

        # Upsert to both stores
        store_with_service.upsert_points(collection_name, [point])
        store_without_service.upsert_points(collection_name, [point])

        # Retrieve points from both stores
        point_with_service = store_with_service.get_point("test_1", collection_name)
        point_without_service = store_without_service.get_point("test_1", collection_name)

        # Verify both points exist
        assert point_with_service is not None
        assert point_without_service is not None

        # Verify vectors are identical (or very close due to floating point)
        np.testing.assert_array_almost_equal(
            np.array(point_with_service['vector']),
            np.array(point_without_service['vector']),
            decimal=6
        )

    def test_upsert_points_progress_callback_with_matrix_service(self):
        """Test progress callback works with matrix service integration."""
        store = FilesystemVectorStore(
            base_path=self.base_path,
            project_root=self.project_root,
            use_matrix_service=True
        )

        # Create collection
        collection_name = "test_collection"
        vector_size = 1536
        store.create_collection(collection_name, vector_size)

        # Track progress callbacks
        progress_calls = []

        def progress_callback(current, total, file_path, info):
            progress_calls.append({
                'current': current,
                'total': total,
                'file_path': str(file_path),
                'info': info
            })

        # Create test points
        points = [
            {
                'id': f"test_{i}",
                'vector': np.random.randn(vector_size).tolist(),
                'payload': {
                    'path': f'test_file_{i}.py',
                    'start_line': 1,
                    'end_line': 10,
                    'content': f'Test content {i}'
                }
            }
            for i in range(3)
        ]

        # Upsert with progress callback
        result = store.upsert_points(collection_name, points, progress_callback=progress_callback)

        # Verify callbacks were made
        assert len(progress_calls) == 3
        assert progress_calls[0]['current'] == 1
        assert progress_calls[1]['current'] == 2
        assert progress_calls[2]['current'] == 3
        assert all(call['total'] == 3 for call in progress_calls)
