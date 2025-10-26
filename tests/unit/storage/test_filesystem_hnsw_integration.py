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


class TestCollectionMetadataIndexType:
    """Test index_type tracking in collection metadata."""

    def test_create_collection_defaults_to_binary_index_type(self, tmp_path: Path):
        """Test that newly created collections default to binary index type."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert "index_type" in metadata
        assert metadata["index_type"] == "binary"

    def test_create_collection_includes_index_format_binary_v1(self, tmp_path: Path):
        """Test that binary index format is set correctly in metadata."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert metadata["index_format"] == "binary_v1"

    def test_backward_compatibility_missing_index_type_defaults_to_binary(
        self, tmp_path: Path
    ):
        """Test that collections without index_type default to binary."""
        # Simulate old collection without index_type field
        collection_path = tmp_path / "old_collection"
        collection_path.mkdir()

        metadata = {
            "name": "old_collection",
            "vector_size": 1536,
            "created_at": "2025-10-25T00:00:00",
            "quantization_range": {"min": -0.75, "max": 0.75},
            "index_version": 1,
            "index_format": "binary_v1",
        }

        meta_file = collection_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        store = FilesystemVectorStore(tmp_path)

        # When loading metadata, should default to binary
        loaded_meta = store.get_collection_info("old_collection")
        # The implementation should handle missing index_type gracefully
        assert loaded_meta.get("index_type", "binary") == "binary"


class TestSetIndexType:
    """Test set_index_type() method for switching between index types."""

    def test_set_index_type_updates_metadata_to_hnsw(self, tmp_path: Path):
        """Test switching from binary to HNSW updates metadata."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert metadata["index_type"] == "hnsw"
        assert metadata["index_format"] == "hnsw_v1"

    def test_set_index_type_updates_metadata_to_binary(self, tmp_path: Path):
        """Test switching from HNSW to binary updates metadata."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        # First switch to HNSW
        store.set_index_type("test_collection", "hnsw")

        # Then switch back to binary
        store.set_index_type("test_collection", "binary")

        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)

        assert metadata["index_type"] == "binary"
        assert metadata["index_format"] == "binary_v1"

    def test_set_index_type_removes_binary_index_when_switching_to_hnsw(
        self, tmp_path: Path
    ):
        """Test that switching to HNSW removes binary index file."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        # Create dummy binary index file
        binary_index_file = tmp_path / "test_collection" / "vector_index.bin"
        binary_index_file.write_bytes(b"binary_index_data")

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

        # Binary index should be removed
        assert not binary_index_file.exists()

    def test_set_index_type_removes_hnsw_index_when_switching_to_binary(
        self, tmp_path: Path
    ):
        """Test that switching to binary removes HNSW index file."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        # Switch to HNSW first
        store.set_index_type("test_collection", "hnsw")

        # Create dummy HNSW index file
        hnsw_index_file = tmp_path / "test_collection" / "hnsw_index.bin"
        hnsw_index_file.write_bytes(b"hnsw_index_data")

        # Switch back to binary
        store.set_index_type("test_collection", "binary")

        # HNSW index should be removed
        assert not hnsw_index_file.exists()

    def test_set_index_type_validates_index_type_value(self, tmp_path: Path):
        """Test that set_index_type validates index type parameter."""
        store = FilesystemVectorStore(tmp_path)
        store.create_collection("test_collection", vector_size=1536)

        with pytest.raises(ValueError, match="Invalid index_type"):
            store.set_index_type("test_collection", "invalid")

    def test_set_index_type_fails_for_nonexistent_collection(self, tmp_path: Path):
        """Test that set_index_type fails gracefully for missing collection."""
        store = FilesystemVectorStore(tmp_path)

        with pytest.raises(ValueError, match="does not exist"):
            store.set_index_type("nonexistent", "hnsw")


class TestMutualExclusivityInUpsert:
    """Test mutual exclusivity enforcement in upsert_points()."""

    def test_upsert_with_binary_index_removes_hnsw_index(self, tmp_path: Path):
        """Test that upserting with binary index type removes HNSW index file."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Switch to HNSW and create dummy index
        store.set_index_type("test_collection", "hnsw")
        hnsw_index_file = tmp_path / "test_collection" / "hnsw_index.bin"
        hnsw_index_file.write_bytes(b"hnsw_data")

        # Switch back to binary
        store.set_index_type("test_collection", "binary")

        # Upsert points (should enforce mutual exclusivity)
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]

        store.upsert_points("test_collection", points)

        # HNSW index should not exist
        assert not hnsw_index_file.exists()

        # Binary index should exist
        binary_index_file = tmp_path / "test_collection" / "vector_index.bin"
        assert binary_index_file.exists()

    def test_upsert_with_hnsw_index_removes_binary_index(self, tmp_path: Path):
        """Test that upserting with HNSW index type removes binary index file."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Create dummy binary index first
        binary_index_file = tmp_path / "test_collection" / "vector_index.bin"
        binary_index_file.write_bytes(b"binary_data")

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

        # Upsert points (should build HNSW index and remove binary)
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(128).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]

        store.upsert_points("test_collection", points)

        # Binary index should not exist
        assert not binary_index_file.exists()

        # HNSW index should exist
        hnsw_index_file = tmp_path / "test_collection" / "hnsw_index.bin"
        assert hnsw_index_file.exists()

    def test_only_one_index_exists_after_upsert(self, tmp_path: Path):
        """Test that only one index type exists after upsert operation."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=64)

        # Upsert with binary (default)
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(64).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(5)
        ]

        store.upsert_points("test_collection", points)

        binary_exists = (
            tmp_path / "test_collection" / "vector_index.bin"
        ).exists()
        hnsw_exists = (tmp_path / "test_collection" / "hnsw_index.bin").exists()

        # Only one should exist
        assert binary_exists != hnsw_exists
        assert binary_exists  # Should be binary since that's default


class TestHNSWSearchPath:
    """Test that search() uses HNSW index when index_type is hnsw."""

    def test_search_uses_hnsw_index_when_index_type_is_hnsw(self, tmp_path: Path):
        """Test that search loads and uses HNSW index for queries."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

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

    def test_search_uses_binary_index_when_index_type_is_binary(
        self, tmp_path: Path
    ):
        """Test that search uses binary index when index_type is binary."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Keep default binary index type
        # Upsert vectors
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

        # Verify search path indicates binary index was used
        assert timing.get("search_path") == "binary_index"
        assert len(results) > 0

    def test_search_falls_back_to_full_scan_if_hnsw_index_missing(
        self, tmp_path: Path
    ):
        """Test that search falls back to full scan if HNSW index is missing."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=64)

        # Set to HNSW but don't build index
        store.set_index_type("test_collection", "hnsw")

        # Upsert vectors WITHOUT building index (simulate missing index)
        # We'll need to bypass normal upsert to avoid auto-building
        # For this test, we'll manually insert vectors

        vectors = [np.random.randn(64).astype(np.float32) for i in range(10)]
        collection_path = tmp_path / "test_collection"

        # Manually create vector files without building index
        from code_indexer.storage.vector_quantizer import VectorQuantizer
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)
        matrix_manager = ProjectionMatrixManager()

        # Create projection matrix
        projection_matrix = matrix_manager.create_projection_matrix(64, 64)
        matrix_manager.save_matrix(projection_matrix, collection_path)

        min_val, max_val = -0.75, 0.75

        for i in range(10):
            vector = vectors[i]
            reduced = vector @ projection_matrix
            quantized_bits = quantizer._quantize_to_2bit(reduced, min_val, max_val)
            hex_path = quantizer._bits_to_hex(quantized_bits)
            segments = quantizer._split_hex_path(hex_path)

            dir_path = collection_path
            for segment in segments[:-1]:
                dir_path = dir_path / segment
            dir_path.mkdir(parents=True, exist_ok=True)

            vector_file = dir_path / f"vector_vec_{i}.json"
            vector_data = {
                "id": f"vec_{i}",
                "vector": vector.tolist(),
                "payload": {"path": f"file_{i}.py"},
            }

            with open(vector_file, "w") as f:
                json.dump(vector_data, f)

        # Perform search - should fall back to full scan
        query_vector = np.random.randn(64).tolist()
        results, timing = store.search(
            query_vector=query_vector,
            collection_name="test_collection",
            limit=5,
            return_timing=True,
        )

        # Should fall back to full scan or quantized lookup
        assert timing.get("search_path") in ["full_scan", "quantized_lookup"]
        assert len(results) > 0

    def test_hnsw_search_path_activation_with_timing_metrics(self, tmp_path: Path, caplog):
        """Test that HNSW search path is activated and timing metrics show correct path.

        This is a regression test for the issue where HNSW index exists and loads
        successfully, but queries fall back to binary index due to silent exception
        handling in the HNSW search path.
        """
        import logging
        caplog.set_level(logging.DEBUG)

        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

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

        # Verify collection metadata shows HNSW
        meta_file = tmp_path / "test_collection" / "collection_meta.json"
        with open(meta_file) as f:
            metadata = json.load(f)
        assert metadata["index_type"] == "hnsw", "Metadata should show HNSW index type"

        # Perform search with timing
        query_vector = np.random.randn(128).tolist()
        results, timing = store.search(
            query_vector=query_vector,
            collection_name="test_collection",
            limit=10,
            return_timing=True,
        )

        # CRITICAL ASSERTIONS: These should pass but currently fail in production
        # 1. Search path must be 'hnsw_index', not 'binary_index'
        assert timing.get("search_path") == "hnsw_index", (
            f"Search path should be 'hnsw_index' but got '{timing.get('search_path')}'. "
            f"This indicates HNSW path is not activating correctly."
        )

        # 2. HNSW-specific timing metrics should be present
        assert "hnsw_search_ms" in timing, "HNSW search timing should be present"
        assert timing.get("hnsw_search_ms", 0) > 0, "HNSW search should have non-zero time"

        # 3. Binary index timing should be zero (not used)
        assert timing.get("hamming_search_ms", 0) == 0, "Hamming search should not be used with HNSW"

        # 4. Results should be returned
        assert len(results) > 0, "Should return search results"

        # 5. Results should have proper structure
        assert all("payload" in r for r in results), "All results should have payload"
        assert all("content" in r.get("payload", {}) for r in results), "All results should have content"
        assert all("staleness" in r for r in results), "All results should have staleness"


class TestIndexTypeSwitch:
    """Integration tests for switching between index types."""

    def test_switch_from_binary_to_hnsw_and_back(self, tmp_path: Path):
        """Test full workflow of switching index types."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Start with binary (default)
        vectors = [np.random.randn(128).astype(np.float32) for i in range(30)]
        points = [
            {
                "id": f"vec_{i}",
                "vector": vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(30)
        ]

        store.upsert_points("test_collection", points)

        # Verify binary index exists
        binary_file = tmp_path / "test_collection" / "vector_index.bin"
        assert binary_file.exists()

        # Switch to HNSW
        store.set_index_type("test_collection", "hnsw")

        # Rebuild with HNSW
        store.upsert_points("test_collection", points)

        # Verify HNSW index exists, binary removed
        hnsw_file = tmp_path / "test_collection" / "hnsw_index.bin"
        assert hnsw_file.exists()
        assert not binary_file.exists()

        # Switch back to binary
        store.set_index_type("test_collection", "binary")
        store.upsert_points("test_collection", points)

        # Verify binary index restored, HNSW removed
        assert binary_file.exists()
        assert not hnsw_file.exists()

    def test_search_results_consistent_across_index_types(self, tmp_path: Path):
        """Test that search results are consistent between binary and HNSW."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)

        # Create deterministic vectors for reproducibility
        np.random.seed(42)
        vectors = [np.random.randn(128).astype(np.float32) for i in range(50)]
        points = [
            {
                "id": f"vec_{i}",
                "vector": vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(50)
        ]

        # Test with binary index
        store.upsert_points("test_collection", points)

        query_vector = np.random.randn(128).tolist()
        binary_results = store.search(
            query_vector=query_vector, collection_name="test_collection", limit=10
        )

        binary_ids = {r["id"] for r in binary_results}

        # Switch to HNSW and test
        store.set_index_type("test_collection", "hnsw")
        store.upsert_points("test_collection", points)

        hnsw_results = store.search(
            query_vector=query_vector, collection_name="test_collection", limit=10
        )

        hnsw_ids = {r["id"] for r in hnsw_results}

        # Results should have significant overlap (HNSW is approximate)
        # At least 70% overlap expected
        overlap = len(binary_ids & hnsw_ids)
        assert overlap >= 7, f"Only {overlap}/10 results matched between index types"


class TestHNSWIndexBuildParameters:
    """Test HNSW index building with custom parameters."""

    def test_upsert_builds_hnsw_with_default_parameters(self, tmp_path: Path):
        """Test that HNSW index is built with reasonable defaults."""
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        store.create_collection("test_collection", vector_size=128)
        store.set_index_type("test_collection", "hnsw")

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

    def test_existing_binary_collections_continue_working(self, tmp_path: Path):
        """Test that existing collections without index_type work correctly."""
        # Simulate old collection
        collection_path = tmp_path / "old_collection"
        collection_path.mkdir()

        # Old metadata format (no index_type)
        metadata = {
            "name": "old_collection",
            "vector_size": 128,
            "created_at": "2025-10-25T00:00:00",
            "quantization_range": {"min": -0.75, "max": 0.75},
            "index_version": 1,
            "index_format": "binary_v1",
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

        # Should be able to upsert (defaults to binary)
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

        # Should create binary index
        binary_file = collection_path / "vector_index.bin"
        assert binary_file.exists()
