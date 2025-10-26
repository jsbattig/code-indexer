"""Unit tests for HNSWIndexManager."""

import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import Mock, patch

import numpy as np
import pytest

from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestHNSWIndexManagerInit:
    """Test HNSWIndexManager initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        manager = HNSWIndexManager()
        assert manager.vector_dim == 1536
        assert manager.space == 'cosine'

    def test_init_with_custom_dims(self):
        """Test initialization with custom vector dimensions."""
        manager = HNSWIndexManager(vector_dim=768, space='l2')
        assert manager.vector_dim == 768
        assert manager.space == 'l2'

    def test_init_with_invalid_space(self):
        """Test initialization with invalid distance metric."""
        with pytest.raises(ValueError, match="Invalid space metric"):
            HNSWIndexManager(space='invalid')


class TestHNSWIndexManagerBuildIndex:
    """Test index building functionality."""

    def test_build_index_creates_file(self, tmp_path: Path):
        """Test that build_index creates hnsw_index.bin file."""
        manager = HNSWIndexManager(vector_dim=128)

        # Create test data
        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        # Build index
        manager.build_index(tmp_path, vectors, ids)

        # Verify file exists
        index_file = tmp_path / HNSWIndexManager.INDEX_FILENAME
        assert index_file.exists()
        assert index_file.stat().st_size > 0

    def test_build_index_with_progress_callback(self, tmp_path: Path):
        """Test that progress callback is called during index building."""
        manager = HNSWIndexManager(vector_dim=64)

        vectors = np.random.randn(50, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(50)]

        # Mock progress callback
        progress_callback = Mock()

        manager.build_index(tmp_path, vectors, ids, progress_callback=progress_callback)

        # Verify callback was called
        assert progress_callback.called
        # Should be called with (current, total) at least once
        progress_callback.assert_called()

    def test_build_index_with_custom_hnsw_params(self, tmp_path: Path):
        """Test building index with custom HNSW parameters."""
        manager = HNSWIndexManager(vector_dim=128)

        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        # Build with custom parameters
        manager.build_index(tmp_path, vectors, ids, M=32, ef_construction=400)

        # Verify file was created
        index_file = tmp_path / HNSWIndexManager.INDEX_FILENAME
        assert index_file.exists()

    def test_build_index_validates_vector_dimensions(self, tmp_path: Path):
        """Test that build_index validates vector dimensions match expected."""
        manager = HNSWIndexManager(vector_dim=128)

        # Wrong dimensions
        vectors = np.random.randn(100, 256).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        with pytest.raises(ValueError, match="Vector dimension"):
            manager.build_index(tmp_path, vectors, ids)

    def test_build_index_validates_ids_length(self, tmp_path: Path):
        """Test that build_index validates IDs list matches vectors length."""
        manager = HNSWIndexManager(vector_dim=128)

        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(50)]  # Wrong length

        with pytest.raises(ValueError, match="IDs length.*vectors"):
            manager.build_index(tmp_path, vectors, ids)

    def test_build_index_updates_metadata(self, tmp_path: Path):
        """Test that build_index updates collection metadata."""
        manager = HNSWIndexManager(vector_dim=128)

        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]

        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        # Check metadata file
        meta_file = tmp_path / 'collection_meta.json'
        assert meta_file.exists()

        with open(meta_file) as f:
            metadata = json.load(f)

        assert 'hnsw_index' in metadata
        hnsw_meta = metadata['hnsw_index']
        assert hnsw_meta['vector_count'] == 100
        assert hnsw_meta['vector_dim'] == 128
        assert hnsw_meta['M'] == 16
        assert hnsw_meta['ef_construction'] == 200
        assert hnsw_meta['space'] == 'cosine'
        assert 'last_rebuild' in hnsw_meta
        assert 'file_size_bytes' in hnsw_meta


class TestHNSWIndexManagerLoadIndex:
    """Test index loading functionality."""

    def test_load_index_returns_none_if_not_exists(self, tmp_path: Path):
        """Test that load_index returns None if index file doesn't exist."""
        manager = HNSWIndexManager()
        index = manager.load_index(tmp_path)
        assert index is None

    def test_load_index_returns_valid_index(self, tmp_path: Path):
        """Test that load_index returns a valid hnswlib.Index object."""
        manager = HNSWIndexManager(vector_dim=128)

        # Build an index first
        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]
        manager.build_index(tmp_path, vectors, ids)

        # Load it
        index = manager.load_index(tmp_path, max_elements=1000)

        assert index is not None
        # Should be able to query it
        query_vec = np.random.randn(128).astype(np.float32)
        labels, distances = index.knn_query(query_vec, k=5)
        assert len(labels[0]) == 5

    def test_load_index_with_insufficient_max_elements(self, tmp_path: Path):
        """Test load_index with max_elements smaller than actual index size."""
        manager = HNSWIndexManager(vector_dim=64)

        # Build index with 100 vectors
        vectors = np.random.randn(100, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]
        manager.build_index(tmp_path, vectors, ids)

        # Try to load with max_elements=50 (should still work, hnswlib allows resizing)
        index = manager.load_index(tmp_path, max_elements=50)
        assert index is not None


class TestHNSWIndexManagerQuery:
    """Test query functionality."""

    def test_query_returns_nearest_neighbors(self, tmp_path: Path):
        """Test that query returns k nearest neighbors."""
        manager = HNSWIndexManager(vector_dim=128)

        # Build index
        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]
        manager.build_index(tmp_path, vectors, ids)

        # Load and query
        index = manager.load_index(tmp_path, max_elements=1000)
        query_vec = np.random.randn(128).astype(np.float32)

        result_ids, distances = manager.query(index, query_vec, tmp_path, k=10)

        assert len(result_ids) == 10
        assert len(distances) == 10
        assert all(isinstance(id_val, str) for id_val in result_ids)
        assert all(isinstance(dist, float) for dist in distances)

    def test_query_with_custom_ef(self, tmp_path: Path):
        """Test query with custom ef parameter."""
        manager = HNSWIndexManager(vector_dim=64)

        vectors = np.random.randn(50, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(50)]
        manager.build_index(tmp_path, vectors, ids)

        index = manager.load_index(tmp_path, max_elements=100)
        query_vec = np.random.randn(64).astype(np.float32)

        # Query with higher ef for better accuracy
        result_ids, distances = manager.query(index, query_vec, tmp_path, k=5, ef=100)

        assert len(result_ids) == 5
        assert len(distances) == 5

    def test_query_validates_vector_dimension(self, tmp_path: Path):
        """Test that query validates query vector dimension."""
        manager = HNSWIndexManager(vector_dim=128)

        vectors = np.random.randn(50, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(50)]
        manager.build_index(tmp_path, vectors, ids)

        index = manager.load_index(tmp_path, max_elements=100)

        # Wrong dimension query
        wrong_query = np.random.randn(64).astype(np.float32)

        with pytest.raises(ValueError, match="dimension"):
            manager.query(index, wrong_query, tmp_path, k=5)

    def test_query_limits_k_to_available_vectors(self, tmp_path: Path):
        """Test that query handles k larger than available vectors."""
        manager = HNSWIndexManager(vector_dim=64)

        # Only 10 vectors
        vectors = np.random.randn(10, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(10)]
        manager.build_index(tmp_path, vectors, ids)

        index = manager.load_index(tmp_path, max_elements=100)
        query_vec = np.random.randn(64).astype(np.float32)

        # Request 20 neighbors but only 10 available
        result_ids, distances = manager.query(index, query_vec, tmp_path, k=20)

        # Should return only 10
        assert len(result_ids) == 10
        assert len(distances) == 10


class TestHNSWIndexManagerIndexExists:
    """Test index existence checking."""

    def test_index_exists_returns_false_when_not_exists(self, tmp_path: Path):
        """Test that index_exists returns False when index doesn't exist."""
        manager = HNSWIndexManager()
        assert not manager.index_exists(tmp_path)

    def test_index_exists_returns_true_when_exists(self, tmp_path: Path):
        """Test that index_exists returns True when index exists."""
        manager = HNSWIndexManager(vector_dim=64)

        vectors = np.random.randn(50, 64).astype(np.float32)
        ids = [f"vec_{i}" for i in range(50)]
        manager.build_index(tmp_path, vectors, ids)

        assert manager.index_exists(tmp_path)


class TestHNSWIndexManagerGetIndexStats:
    """Test index statistics retrieval."""

    def test_get_index_stats_returns_metadata(self, tmp_path: Path):
        """Test that get_index_stats returns comprehensive metadata."""
        manager = HNSWIndexManager(vector_dim=128)

        vectors = np.random.randn(100, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(100)]
        manager.build_index(tmp_path, vectors, ids, M=16, ef_construction=200)

        stats = manager.get_index_stats(tmp_path)

        assert stats is not None
        assert stats['vector_count'] == 100
        assert stats['vector_dim'] == 128
        assert stats['M'] == 16
        assert stats['ef_construction'] == 200
        assert stats['space'] == 'cosine'
        assert 'last_rebuild' in stats
        assert stats['file_size_bytes'] > 0

    def test_get_index_stats_returns_none_when_no_index(self, tmp_path: Path):
        """Test that get_index_stats returns None when index doesn't exist."""
        manager = HNSWIndexManager()
        stats = manager.get_index_stats(tmp_path)
        assert stats is None


class TestHNSWIndexManagerRebuildFromVectors:
    """Test index rebuilding from vector files."""

    def test_rebuild_from_vectors_recreates_index(self, tmp_path: Path):
        """Test that rebuild_from_vectors scans JSON files and rebuilds index."""
        manager = HNSWIndexManager(vector_dim=128)

        # Create mock vector JSON files
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(50):
            vector_file = vectors_dir / f"vector_{i}.json"
            vector_data = {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist()
            }
            with open(vector_file, 'w') as f:
                json.dump(vector_data, f)

        # Create metadata file (required for rebuild)
        meta_file = tmp_path / 'collection_meta.json'
        metadata = {
            "vector_dim": 128
        }
        with open(meta_file, 'w') as f:
            json.dump(metadata, f)

        # Rebuild
        vector_count = manager.rebuild_from_vectors(tmp_path)

        assert vector_count == 50
        assert manager.index_exists(tmp_path)

    def test_rebuild_from_vectors_with_progress_callback(self, tmp_path: Path):
        """Test that rebuild calls progress callback."""
        manager = HNSWIndexManager(vector_dim=64)

        # Create mock vector files
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(20):
            vector_file = vectors_dir / f"vector_{i}.json"
            vector_data = {
                "id": f"vec_{i}",
                "vector": np.random.randn(64).tolist()
            }
            with open(vector_file, 'w') as f:
                json.dump(vector_data, f)

        # Metadata
        meta_file = tmp_path / 'collection_meta.json'
        with open(meta_file, 'w') as f:
            json.dump({"vector_dim": 64}, f)

        # Rebuild with progress callback
        progress_callback = Mock()
        manager.rebuild_from_vectors(tmp_path, progress_callback=progress_callback)

        assert progress_callback.called

    def test_rebuild_from_vectors_handles_missing_metadata(self, tmp_path: Path):
        """Test rebuild fails gracefully when metadata is missing."""
        manager = HNSWIndexManager(vector_dim=128)

        with pytest.raises(FileNotFoundError, match="metadata"):
            manager.rebuild_from_vectors(tmp_path)

    def test_rebuild_from_vectors_skips_malformed_files(self, tmp_path: Path):
        """Test that rebuild skips malformed JSON files."""
        manager = HNSWIndexManager(vector_dim=64)

        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        # Create valid files
        for i in range(10):
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, 'w') as f:
                json.dump({"id": f"vec_{i}", "vector": np.random.randn(64).tolist()}, f)

        # Create malformed file
        bad_file = vectors_dir / "vector_bad.json"
        with open(bad_file, 'w') as f:
            f.write("{ invalid json")

        # Metadata
        meta_file = tmp_path / 'collection_meta.json'
        with open(meta_file, 'w') as f:
            json.dump({"vector_dim": 64}, f)

        # Should succeed, skipping bad file
        vector_count = manager.rebuild_from_vectors(tmp_path)
        assert vector_count == 10


class TestHNSWIndexManagerGracefulDegradation:
    """Test graceful degradation when hnswlib is not installed."""

    @patch('code_indexer.storage.hnsw_index_manager.HNSWLIB_AVAILABLE', False)
    def test_init_fails_gracefully_without_hnswlib(self):
        """Test that initialization provides clear error when hnswlib not installed."""
        with pytest.raises(ImportError, match="hnswlib.*not installed"):
            HNSWIndexManager()

    @patch('code_indexer.storage.hnsw_index_manager.HNSWLIB_AVAILABLE', False)
    def test_build_index_fails_gracefully_without_hnswlib(self, tmp_path: Path):
        """Test that build_index fails gracefully without hnswlib."""
        # This test verifies the error message is clear
        # In practice, __init__ would fail first, but we test the pattern
        with pytest.raises(ImportError):
            manager = HNSWIndexManager()
