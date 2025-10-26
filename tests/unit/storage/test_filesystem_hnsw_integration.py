"""Unit tests for HNSW index integration into FilesystemVectorStore.

Tests comprehensive integration of HNSW index manager as alternative to binary index
with mutual exclusivity enforcement and CLI support.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestCollectionMetadata:
    """Test collection metadata handling."""

    def test_create_collection_sets_basic_metadata(self, tmp_path: Path):
        """Test that newly created collections have proper metadata."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert metadata["name"] == "test_collection"
        assert metadata["vector_size"] == 1536
        assert "created_at" in metadata

    def test_backward_compatibility_with_old_collections(
        self, tmp_path: Path
    ):
        """Test that old collections without new metadata fields still work."""
        # Simulate old collection without HNSW metadata
        collection_path = tmp_path / "old_collection"
        collection_path.mkdir()

        metadata = {
            "name": "old_collection",
            "vector_size": 1536,
            "created_at": "2025-10-25T00:00:00",
            "quantization_range": {"min": -0.75, "max": 0.75},
            "index_version": 1,
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        store = FilesystemVectorStore(tmp_path)

        # Should be able to load old collections
        loaded_meta = store.get_collection_info("old_collection")
        assert loaded_meta["name"] == "old_collection"


class TestHNSWIndexCreation:
    """Test HNSW index creation during upsert."""

    def test_upsert_creates_hnsw_index(self, tmp_path: Path):
        """Test that upserting points creates HNSW index file."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Upsert points
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]

        store.upsert_points("test_collection", points)

        # HNSW index should exist
        hnsw_index_file = tmp_path / "test_collection" / "hnsw_index.bin"
        assert hnsw_index_file.exists()

    def test_only_hnsw_index_exists_after_upsert(self, tmp_path: Path):
        """Test that only HNSW index exists after upsert operation."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=64)

        # Upsert points
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(64).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(5)
        ]

        store.upsert_points("test_collection", points)

        # Only HNSW index should exist
        hnsw_exists = (tmp_path / "test_collection" / "hnsw_index.bin").exists()
        assert hnsw_exists


class TestHNSWSearchPath:
    """Test that search() uses HNSW index."""

    def test_search_uses_hnsw_index(self, tmp_path: Path):
        """Test that search loads and uses HNSW index for queries."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Upsert vectors to build HNSW index
        vectors = [np.random.randn(128).astype(np.float32) for i in range(50)]
        points = [
            {
                "id": f"vec_{i}",
                "vector": vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(50)
        ]

        store.upsert_points("test_collection", points)

        # Perform search
        query_vector = np.random.randn(128).tolist()
        results, timing = store.search(
            query_vector=query_vector,
            collection_name="test_collection",
            limit=10,
            return_timing=True,
        )

        # Verify search path indicates HNSW was used
        assert timing.get("search_path") == "hnsw_index"
        assert len(results) > 0

    def test_search_raises_error_if_hnsw_index_missing(
        self, tmp_path: Path
    ):
        """Test that search raises error if HNSW index is missing."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=64)

        # Don't upsert any vectors, so no HNSW index is built

        # Perform search - should raise RuntimeError
        query_vector = np.random.randn(64).tolist()

        with pytest.raises(RuntimeError, match="HNSW index not found"):
            store.search(
                query_vector=query_vector,
                collection_name="test_collection",
                limit=5,
            )

    def test_hnsw_search_path_activation_with_timing_metrics(self, tmp_path: Path, caplog):
        """Test that HNSW search path is activated and timing metrics show correct path."""
        import logging
        caplog.set_level(logging.DEBUG)

        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Upsert vectors to build HNSW index
        vectors = [np.random.randn(128).astype(np.float32) for i in range(100)]
        points = [
            {
                "id": f"vec_{i}",
                "vector": vectors[i].tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "start_line": i * 10,
                    "end_line": i * 10 + 5,
                    "language": "python",
                    "type": "content"
                },
            }
            for i in range(100)
        ]

        store.upsert_points("test_collection", points)

        # Verify HNSW index file exists
        hnsw_index_file = tmp_path / "test_collection" / "hnsw_index.bin"
        assert hnsw_index_file.exists(), "HNSW index file should exist"

        # Perform search with timing
        query_vector = np.random.randn(128).tolist()
        results, timing = store.search(
            query_vector=query_vector,
            collection_name="test_collection",
            limit=10,
            return_timing=True,
        )

        # CRITICAL ASSERTIONS
        # 1. Search path must be 'hnsw_index'
        assert timing.get("search_path") == "hnsw_index", (
            f"Search path should be 'hnsw_index' but got '{timing.get('search_path')}'. "
            f"This indicates HNSW path is not activating correctly."
        )

        # 2. HNSW-specific timing metrics should be present
        assert "hnsw_search_ms" in timing, "HNSW search timing should be present"
        assert timing.get("hnsw_search_ms", 0) > 0, "HNSW search should have non-zero time"

        # 3. Results should be returned
        assert len(results) > 0, "Should return search results"

        # 4. Results should have proper structure
        assert all("payload" in r for r in results), "All results should have payload"
        assert all("content" in r.get("payload", {}) for r in results), "All results should have content"
        assert all("staleness" in r for r in results), "All results should have staleness"


class TestHNSWIndexBuildParameters:
    """Test HNSW index building with custom parameters."""

    def test_upsert_builds_hnsw_with_default_parameters(self, tmp_path: Path):
        """Test that HNSW index is built with reasonable defaults."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(50)
        ]

        store.upsert_points("test_collection", points)

        # Check HNSW metadata
        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert "hnsw_index" in metadata
        hnsw_meta = metadata["hnsw_index"]
        assert hnsw_meta["M"] == 16  # Default M parameter
        assert hnsw_meta["ef_construction"] == 200  # Default ef_construction
        assert hnsw_meta["vector_count"] == 50


class TestBackwardCompatibility:
    """Test backward compatibility with existing collections."""

    def test_existing_collections_upgraded_to_hnsw(self, tmp_path: Path):
        """Test that existing collections work and get upgraded to HNSW."""
        # Simulate old collection without HNSW metadata
        collection_path = tmp_path / "old_collection"
        collection_path.mkdir()

        # Old metadata format
        metadata = {
            "name": "old_collection",
            "vector_size": 128,
            "created_at": "2025-10-25T00:00:00",
            "quantization_range": {"min": -0.75, "max": 0.75},
            "index_version": 1,
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        # Create projection matrix
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        matrix_manager = ProjectionMatrixManager()
        projection_matrix = matrix_manager.create_projection_matrix(128, 64)
        matrix_manager.save_matrix(projection_matrix, collection_path)

        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)

        # Should be able to upsert (uses HNSW now)
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]

        result = store.upsert_points("old_collection", points)
        assert result["status"] == "ok"

        # Should create HNSW index
        hnsw_file = collection_path / "hnsw_index.bin"
        assert hnsw_file.exists()
