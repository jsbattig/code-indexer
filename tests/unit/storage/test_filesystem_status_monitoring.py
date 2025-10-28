"""Unit tests for FilesystemVectorStore status and health monitoring (Story 4).

Tests health/validation methods for monitoring filesystem index status.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_store(tmp_path: Path) -> FilesystemVectorStore:
    """Create temporary filesystem vector store."""
    store = FilesystemVectorStore(base_path=tmp_path / "index", project_root=tmp_path)
    return store


@pytest.fixture
def populated_store(temp_store: FilesystemVectorStore) -> FilesystemVectorStore:
    """Create store with test data."""
    collection_name = "test_collection"
    vector_size = 128

    # Create collection
    temp_store.create_collection(collection_name, vector_size)

    # Add test vectors with various files
    test_files = [
        "src/main.py",
        "src/utils.py",
        "tests/test_main.py",
        "README.md",
        "docs/guide.md",
    ]

    points = []
    for idx, file_path in enumerate(test_files):
        vector = np.random.rand(vector_size).tolist()
        payload = {
            "path": file_path,
            "start_line": idx * 10,
            "end_line": idx * 10 + 10,
            "language": "python" if file_path.endswith(".py") else "markdown",
            "content": f"Test content for {file_path}",
        }
        points.append({"id": f"chunk_{idx}", "vector": vector, "payload": payload})

    # Upsert all points
    temp_store.upsert_points(collection_name, points)

    return temp_store


class TestGetAllIndexedFiles:
    """Test get_all_indexed_files() method."""

    def test_empty_collection_returns_empty_list(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that empty collection returns empty list."""
        collection_name = "empty_collection"
        temp_store.create_collection(collection_name, 128)

        result = temp_store.get_all_indexed_files(collection_name)

        assert result == []

    def test_returns_all_unique_file_paths(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that all unique file paths are returned."""
        collection_name = "test_collection"

        result = populated_store.get_all_indexed_files(collection_name)

        expected_files = [
            "src/main.py",
            "src/utils.py",
            "tests/test_main.py",
            "README.md",
            "docs/guide.md",
        ]

        assert sorted(result) == sorted(expected_files)

    def test_multiple_chunks_same_file_deduplicates(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that multiple chunks from same file appear once."""
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, 128)

        # Add multiple chunks from same file
        points = []
        for chunk_idx in range(5):
            vector = np.random.rand(128).tolist()
            payload = {
                "path": "src/main.py",
                "start_line": chunk_idx * 10,
                "end_line": chunk_idx * 10 + 10,
                "language": "python",
                "content": f"Chunk {chunk_idx}",
            }
            points.append(
                {"id": f"chunk_{chunk_idx}", "vector": vector, "payload": payload}
            )

        temp_store.upsert_points(collection_name, points)

        result = temp_store.get_all_indexed_files(collection_name)

        assert result == ["src/main.py"]

    def test_nonexistent_collection_returns_empty_list(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that nonexistent collection returns empty list."""
        result = temp_store.get_all_indexed_files("nonexistent")

        assert result == []


class TestGetFileIndexTimestamps:
    """Test get_file_index_timestamps() method."""

    def test_empty_collection_returns_empty_dict(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that empty collection returns empty dict."""
        collection_name = "empty_collection"
        temp_store.create_collection(collection_name, 128)

        result = temp_store.get_file_index_timestamps(collection_name)

        assert result == {}

    def test_returns_timestamps_for_all_files(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that timestamps are returned for all files."""
        collection_name = "test_collection"

        result = populated_store.get_file_index_timestamps(collection_name)

        expected_files = [
            "src/main.py",
            "src/utils.py",
            "tests/test_main.py",
            "README.md",
            "docs/guide.md",
        ]

        # All files should have timestamps
        assert sorted(result.keys()) == sorted(expected_files)

        # All timestamps should be datetime objects
        for file_path, timestamp in result.items():
            assert isinstance(timestamp, datetime)

    def test_multiple_chunks_same_file_returns_latest_timestamp(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that multiple chunks from same file return latest timestamp."""
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, 128)

        # Add multiple chunks with different timestamps
        import time

        points = []
        for chunk_idx in range(3):
            vector = np.random.rand(128).tolist()
            payload = {
                "path": "src/main.py",
                "start_line": chunk_idx * 10,
                "end_line": chunk_idx * 10 + 10,
                "language": "python",
                "content": f"Chunk {chunk_idx}",
            }
            points.append(
                {"id": f"chunk_{chunk_idx}", "vector": vector, "payload": payload}
            )
            time.sleep(0.01)  # Small delay to ensure different timestamps

        temp_store.upsert_points(collection_name, points)

        result = temp_store.get_file_index_timestamps(collection_name)

        # Should have exactly one entry for the file
        assert len(result) == 1
        assert "src/main.py" in result
        assert isinstance(result["src/main.py"], datetime)

    def test_nonexistent_collection_returns_empty_dict(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that nonexistent collection returns empty dict."""
        result = temp_store.get_file_index_timestamps("nonexistent")

        assert result == {}


class TestSampleVectors:
    """Test sample_vectors() method."""

    def test_empty_collection_returns_empty_list(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that empty collection returns empty list."""
        collection_name = "empty_collection"
        temp_store.create_collection(collection_name, 128)

        result = temp_store.sample_vectors(collection_name, sample_size=5)

        assert result == []

    def test_returns_requested_sample_size(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that requested sample size is returned."""
        collection_name = "test_collection"

        result = populated_store.sample_vectors(collection_name, sample_size=3)

        assert len(result) == 3

    def test_sample_size_larger_than_collection_returns_all(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that sample size larger than collection returns all vectors."""
        collection_name = "test_collection"

        result = populated_store.sample_vectors(collection_name, sample_size=100)

        # Store has 5 vectors
        assert len(result) == 5

    def test_sample_contains_full_vector_data(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that sample contains complete vector data."""
        collection_name = "test_collection"

        result = populated_store.sample_vectors(collection_name, sample_size=2)

        for vector_data in result:
            # Verify structure
            assert "id" in vector_data
            assert "vector" in vector_data
            assert "file_path" in vector_data
            assert "metadata" in vector_data

            # Verify vector is list of floats
            assert isinstance(vector_data["vector"], list)
            assert len(vector_data["vector"]) == 128
            assert all(isinstance(x, (int, float)) for x in vector_data["vector"])

    def test_default_sample_size_is_five(self, populated_store: FilesystemVectorStore):
        """Test that default sample size is 5."""
        collection_name = "test_collection"

        result = populated_store.sample_vectors(collection_name)

        # Store has 5 vectors, so all should be returned
        assert len(result) == 5

    def test_nonexistent_collection_returns_empty_list(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that nonexistent collection returns empty list."""
        result = temp_store.sample_vectors("nonexistent", sample_size=5)

        assert result == []


class TestValidateEmbeddingDimensions:
    """Test validate_embedding_dimensions() method."""

    def test_empty_collection_returns_true(self, temp_store: FilesystemVectorStore):
        """Test that empty collection returns True (vacuously valid)."""
        collection_name = "empty_collection"
        temp_store.create_collection(collection_name, 128)

        result = temp_store.validate_embedding_dimensions(
            collection_name, expected_dims=128
        )

        assert result is True

    def test_all_vectors_match_dimensions_returns_true(
        self, populated_store: FilesystemVectorStore
    ):
        """Test that matching dimensions returns True."""
        collection_name = "test_collection"

        result = populated_store.validate_embedding_dimensions(
            collection_name, expected_dims=128
        )

        assert result is True

    def test_mismatched_dimensions_returns_false(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that mismatched dimensions returns False."""
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, 128)

        # Add vectors with correct dimensions first
        points = []
        for idx in range(3):
            vector = np.random.rand(128).tolist()
            payload = {
                "path": f"file_{idx}.py",
                "start_line": 0,
                "end_line": 10,
                "language": "python",
                "content": "test",
            }
            points.append({"id": f"chunk_{idx}", "vector": vector, "payload": payload})

        temp_store.upsert_points(collection_name, points)

        # Manually corrupt the stored vectors to have wrong dimensions
        collection_path = temp_store.base_path / collection_name
        for json_file in collection_path.rglob("*.json"):
            if "collection_meta" not in json_file.name:
                with open(json_file) as f:
                    data = json.load(f)
                # Truncate vector to wrong size
                data["vector"] = data["vector"][:64]
                with open(json_file, "w") as f:
                    json.dump(data, f)

        result = temp_store.validate_embedding_dimensions(
            collection_name, expected_dims=128
        )

        assert result is False

    def test_mixed_dimensions_returns_false(self, temp_store: FilesystemVectorStore):
        """Test that mixed dimensions returns False."""
        collection_name = "test_collection"
        temp_store.create_collection(collection_name, 128)

        # Add vectors with correct dimensions first
        points = []
        for idx in range(5):
            vector = np.random.rand(128).tolist()
            payload = {
                "path": f"file_{idx}.py",
                "start_line": 0,
                "end_line": 10,
                "language": "python",
                "content": "test",
            }
            points.append({"id": f"chunk_{idx}", "vector": vector, "payload": payload})

        temp_store.upsert_points(collection_name, points)

        # Manually corrupt some vectors to have wrong dimensions
        collection_path = temp_store.base_path / collection_name
        file_idx = 0
        for json_file in collection_path.rglob("*.json"):
            if "collection_meta" not in json_file.name:
                with open(json_file) as f:
                    data = json.load(f)
                # Corrupt every other file
                if file_idx % 2 == 1:
                    data["vector"] = data["vector"][:64]
                    with open(json_file, "w") as f:
                        json.dump(data, f)
                file_idx += 1

        result = temp_store.validate_embedding_dimensions(
            collection_name, expected_dims=128
        )

        assert result is False

    def test_nonexistent_collection_returns_true(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that nonexistent collection returns True (vacuously valid)."""
        result = temp_store.validate_embedding_dimensions(
            "nonexistent", expected_dims=128
        )

        assert result is True


class TestHealthCheck:
    """Test health_check() method (existing functionality)."""

    def test_accessible_filesystem_returns_true(
        self, temp_store: FilesystemVectorStore
    ):
        """Test that accessible filesystem returns True."""
        result = temp_store.health_check()

        assert result is True

    def test_nonexistent_path_returns_false(self, tmp_path: Path):
        """Test that nonexistent path returns False."""
        store = FilesystemVectorStore(
            base_path=tmp_path / "nonexistent" / "deeply" / "nested",
            project_root=tmp_path,
        )

        # Remove the path if it was created
        if store.base_path.exists():
            import shutil

            shutil.rmtree(store.base_path)

        result = store.health_check()

        assert result is False
