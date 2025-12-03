"""Unit tests for FilesystemVectorStore.

Test Strategy: Use real filesystem operations with deterministic test data (NO mocking of file I/O).
Following Story 2 requirements for FilesystemClient-compatible interface.
"""

import json
import numpy as np
import pytest
from unittest.mock import Mock
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor


class TestFilesystemVectorStoreCore:
    """Test core FilesystemVectorStore operations."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        return {
            "small": np.random.randn(10, 1536),
            "medium": np.random.randn(100, 1536),
            "large": np.random.randn(1000, 1536),
        }

    def test_create_collection_generates_projection_matrix(self, tmp_path):
        """GIVEN collection name and vector size
        WHEN create_collection() is called
        THEN projection matrix and metadata files created

        AC1: create_collection() creates directory with projection matrix
        AC2: Projection matrix generated once per collection (deterministic)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)

        result = store.create_collection("test_coll", vector_size=1536)

        assert result is True, "create_collection should return True"

        # Verify collection directory exists
        coll_path = tmp_path / "test_coll"
        assert coll_path.exists(), "Collection directory should exist"

        # Verify projection matrix file exists
        matrix_file = coll_path / "projection_matrix.npy"
        assert matrix_file.exists(), "Projection matrix file should exist"

        # Verify collection metadata file exists
        meta_file = coll_path / "collection_meta.json"
        assert meta_file.exists(), "Collection metadata file should exist"

        # Verify metadata content
        with open(meta_file) as f:
            metadata = json.load(f)

        assert metadata["name"] == "test_coll"
        assert metadata["vector_size"] == 1536
        assert "created_at" in metadata

    def test_upsert_points_stores_json_at_quantized_paths(self, tmp_path, test_vectors):
        """GIVEN vectors to store
        WHEN upsert_points() is called
        THEN JSON files created at quantized paths with correct structure

        AC1: upsert_points() stores vectors as JSON files
        AC2: Path-as-vector quantization creates directory hierarchy
        AC4: Smart chunk storage (will test git-aware separately)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": test_vectors["small"][0].tolist(),
                "payload": {
                    "path": "src/test.py",
                    "line_start": 10,
                    "line_end": 20,
                    "language": "python",
                    "type": "content",
                },
            }
        ]

        result = store.upsert_points("test_coll", points)

        assert result["status"] == "ok", "upsert should succeed"

        # Verify JSON files exist on filesystem
        json_files = list((tmp_path / "test_coll").rglob("*.json"))
        vector_files = [f for f in json_files if "collection_meta" not in f.name]

        assert len(vector_files) >= 1, "At least one vector file should exist"

        # Verify JSON structure (payload nested as of batch implementation)
        with open(vector_files[0]) as f:
            data = json.load(f)

        assert data["id"] == "test_001"
        assert data["payload"]["path"] == "src/test.py"
        assert data["payload"]["line_start"] == 10
        assert data["payload"]["line_end"] == 20
        assert len(data["vector"]) == 1536, "Full vector should be stored"
        assert "metadata" in data

    def test_upsert_creates_directory_hierarchy(self, tmp_path, test_vectors):
        """GIVEN vector to quantize
        WHEN upserting
        THEN creates nested directory structure with depth factor 4

        AC2: Directory structure uses depth factor 4
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors["small"][i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(5)
        ]

        store.upsert_points("test_coll", points)

        # Check that nested directories were created (depth factor 4 = 4 levels + remainder)
        coll_path = tmp_path / "test_coll"

        # Find all vector JSON files
        vector_files = [
            f for f in coll_path.rglob("*.json") if "collection_meta" not in f.name
        ]
        assert len(vector_files) == 5, "Should have 5 vector files"

        # Verify directory nesting depth
        for vf in vector_files:
            # Path should be: base / collection / seg1 / seg2 / seg3 / seg4 / vector_*.json
            rel_path = vf.relative_to(coll_path)
            parts = rel_path.parts
            # Should have at least 2 levels of nesting (depth factor 4 means 4 segments of 2 chars each)
            assert len(parts) >= 2, f"Should have nested structure, got {parts}"

    def test_collection_exists(self, tmp_path):
        """GIVEN created collection
        WHEN collection_exists() is called
        THEN returns True for existing, False for non-existing

        AC6: Collection management (exists check)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)

        # Non-existent collection
        assert store.collection_exists("nonexistent") is False

        # Create collection
        store.create_collection("test_coll", vector_size=1536)

        # Now it exists
        assert store.collection_exists("test_coll") is True

    def test_list_collections(self, tmp_path):
        """GIVEN multiple collections
        WHEN list_collections() is called
        THEN returns all collection names

        AC6: Collection management (list collections)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)

        # Initially empty
        collections = store.list_collections()
        assert len(collections) == 0

        # Create some collections
        store.create_collection("coll1", vector_size=1536)
        store.create_collection("coll2", vector_size=768)
        store.create_collection("coll3", vector_size=1536)

        collections = store.list_collections()
        assert len(collections) == 3
        assert "coll1" in collections
        assert "coll2" in collections
        assert "coll3" in collections

    def test_count_points(self, tmp_path, test_vectors):
        """GIVEN vectors stored in collection
        WHEN count_points() is called
        THEN returns correct count

        AC: ID indexing for fast lookups
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Initially zero
        assert store.count_points("test_coll") == 0

        # Add 10 points
        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors["small"][i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]

        store.upsert_points("test_coll", points)

        # Should have 10
        assert store.count_points("test_coll") == 10

    def test_delete_points_removes_files(self, tmp_path, test_vectors):
        """GIVEN vectors stored in filesystem
        WHEN delete_points() is called
        THEN JSON files are actually removed from filesystem

        AC: delete_points() removes vector files
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store 10 vectors
        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors["small"][i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.upsert_points("test_coll", points)

        initial_count = store.count_points("test_coll")
        assert initial_count == 10

        # Delete specific points
        result = store.delete_points("test_coll", ["vec_1", "vec_2", "vec_3"])

        assert result["status"] == "ok"
        assert result["deleted"] == 3

        # Verify count decreased
        assert store.count_points("test_coll") == 7

    def test_concurrent_writes_thread_safety(self, tmp_path):
        """GIVEN concurrent upsert operations
        WHEN multiple threads write simultaneously
        THEN all vectors stored without corruption

        AC4: Concurrent vector writes with thread safety

        NOTE (Story #540 Fix): Each point must have a UNIQUE file path to avoid
        duplicate cleanup logic removing old versions. Updated to use unique paths.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        def write_batch(start_idx):
            points = [
                {
                    "id": f"vec_{start_idx}_{i}",
                    "vector": np.random.randn(1536).tolist(),
                    # Use unique file path per point to avoid duplicate cleanup
                    "payload": {"path": f"file_{start_idx}_{i}.py"},
                }
                for i in range(10)
            ]
            return store.upsert_points("test_coll", points)

        # Write 100 vectors across 10 threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_batch, i * 10) for i in range(10)]
            results = [f.result() for f in futures]

        # All writes succeed
        assert all(r["status"] == "ok" for r in results)
        assert store.count_points("test_coll") == 100

        # No corrupted JSON files
        coll_path = tmp_path / "test_coll"
        for json_file in coll_path.rglob("*.json"):
            if "collection_meta" in json_file.name:
                continue
            with open(json_file) as f:
                data = json.load(f)  # Should not raise JSONDecodeError
            assert "vector" in data
            assert len(data["vector"]) == 1536

    def test_batch_upsert_performance(self, tmp_path, test_vectors):
        """GIVEN 1000 vectors to store
        WHEN upsert_points() is called in batches
        THEN completes in <5s

        AC: Performance requirement for batch operations
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors["large"][i].tolist(),
                "payload": {"path": f"file_{i}.py", "line_start": i},
            }
            for i in range(1000)
        ]

        start = time.time()
        result = store.upsert_points("test_coll", points)
        duration = time.time() - start

        assert result["status"] == "ok"
        assert duration < 5.0, f"Batch upsert too slow: {duration:.2f}s"
        assert store.count_points("test_coll") == 1000

        # Verify files actually exist on filesystem
        coll_path = tmp_path / "test_coll"
        json_count = sum(
            1 for _ in coll_path.rglob("*.json") if "collection_meta" not in _.name
        )
        assert json_count == 1000


class TestChunkContentStorageAndRetrieval:
    """Test git-aware chunk storage and retrieval."""

    def test_non_git_repo_stores_chunk_text(self, tmp_path):
        """GIVEN a non-git directory
        WHEN indexing chunks
        THEN chunk_text stored in JSON (no git fallback)

        AC4: Non-git repos store chunk_text
        AC8: Automatic storage mode detection (non-git)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # No git init - plain directory
        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 0,
                    "line_end": 2,
                    "content": "def foo():\n    return 42\n",
                },
            }
        ]

        store.upsert_points("test_coll", points)

        # Verify JSON DOES contain chunk text (no git fallback)
        coll_path = tmp_path / "test_coll"
        json_files = [
            f for f in coll_path.rglob("*.json") if "collection_meta" not in f.name
        ]
        with open(json_files[0]) as f:
            data = json.load(f)

        assert "chunk_text" in data, "Chunk text should be stored for non-git"
        assert data["chunk_text"] == "def foo():\n    return 42\n"
        assert "git_blob_hash" not in data, "No git metadata for non-git repos"

    def test_clean_git_state_stores_blob_hash_not_content(self, tmp_path):
        """GIVEN clean git repo
        WHEN indexing
        THEN git_blob_hash stored (no chunk_text) for space efficiency

        AC4: Clean git repos store only git_blob_hash
        AC8: Batch git operations (<500ms for 100 files)
        """
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        content = "def foo(): return 42\n"
        test_file.write_text(content)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        # No modifications - clean state
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 0,
                    "line_end": 1,
                    "content": content,
                },
            }
        ]

        store.upsert_points("test_coll", points)

        # Verify git_blob_hash stored (no chunk_text)
        coll_path = tmp_path / "test_coll"
        json_files = [
            f for f in coll_path.rglob("*.json") if "collection_meta" not in f.name
        ]
        with open(json_files[0]) as f:
            data = json.load(f)

        assert "git_blob_hash" in data, "Git blob hash should be stored"
        assert (
            "chunk_text" not in data
        ), "Chunk text should NOT be stored (space efficient)"
        assert data.get("indexed_with_uncommitted_changes", False) is False

    def test_dirty_git_state_stores_chunk_text(self, tmp_path):
        """GIVEN git repo with uncommitted changes
        WHEN indexing
        THEN chunk_text stored (not git_blob_hash) to ensure correctness

        AC4: Dirty git repos store chunk_text
        AC8: No git state requirements (dirty allowed)
        """
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True
        )

        # Modify without committing (dirty state)
        dirty_content = "def foo(): return 99\n"
        test_file.write_text(dirty_content)

        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 0,
                    "line_end": 1,
                    "content": dirty_content,
                },
            }
        ]

        store.upsert_points("test_coll", points)

        # Verify chunk_text stored (not git_blob_hash)
        coll_path = tmp_path / "test_coll"
        json_files = [
            f for f in coll_path.rglob("*.json") if "collection_meta" not in f.name
        ]
        with open(json_files[0]) as f:
            data = json.load(f)

        assert "chunk_text" in data, "Chunk text should be stored for dirty git"
        assert data["chunk_text"] == dirty_content
        assert "git_blob_hash" not in data, "Git blob hash not stored for dirty state"
        assert data.get("indexed_with_uncommitted_changes") is True


class TestSearchMethods:
    """Test search(), scroll_points(), get_point() methods."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        return np.random.randn(20, 1536)

    def test_get_point_returns_vector_data(self, tmp_path, test_vectors):
        """GIVEN vector stored with specific ID
        WHEN get_point() is called with that ID
        THEN returns point data with vector and payload

        AC: get_point() method for ID lookups
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store a vector
        points = [
            {
                "id": "lookup_test",
                "vector": test_vectors[0].tolist(),
                "payload": {
                    "path": "src/test.py",
                    "language": "python",
                    "type": "content",
                },
            }
        ]
        store.upsert_points("test_coll", points)

        # Retrieve by ID
        result = store.get_point("lookup_test", "test_coll")

        assert result is not None, "get_point should return data"
        assert result["id"] == "lookup_test"
        assert "vector" in result
        assert len(result["vector"]) == 1536
        assert result["payload"]["path"] == "src/test.py"

    def test_get_point_returns_none_for_missing_id(self, tmp_path):
        """GIVEN collection with no vectors
        WHEN get_point() is called with non-existent ID
        THEN returns None

        AC: get_point() returns None for missing IDs
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        result = store.get_point("nonexistent", "test_coll")
        assert result is None

    def test_scroll_points_returns_all_points(self, tmp_path, test_vectors):
        """GIVEN 10 vectors stored
        WHEN scroll_points() is called with limit=100
        THEN returns all 10 points

        AC: scroll_points() enumerates all vectors
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store 10 vectors
        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.upsert_points("test_coll", points)

        # Scroll all points
        results, next_offset = store.scroll_points(
            collection_name="test_coll",
            limit=100,
            with_payload=True,
            with_vectors=False,
        )

        assert len(results) == 10, "Should return all 10 points"
        assert next_offset is None, "No more pages"

        # Verify payload structure
        assert all("id" in p for p in results)
        assert all("payload" in p for p in results)

    def test_scroll_points_pagination(self, tmp_path, test_vectors):
        """GIVEN 20 vectors stored
        WHEN scroll_points() is called with limit=10 twice
        THEN returns first 10, then next 10 with offset

        AC: scroll_points() supports pagination
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store 20 vectors
        points = [
            {
                "id": f"vec_{i:03d}",  # Zero-padded for consistent sorting
                "vector": test_vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(20)
        ]
        store.upsert_points("test_coll", points)

        # First page
        page1, offset1 = store.scroll_points(
            collection_name="test_coll", limit=10, with_payload=True, with_vectors=False
        )

        assert len(page1) == 10
        assert offset1 is not None, "Should have next page"

        # Second page
        page2, offset2 = store.scroll_points(
            collection_name="test_coll",
            limit=10,
            with_payload=True,
            with_vectors=False,
            offset=offset1,
        )

        assert len(page2) == 10
        assert offset2 is None, "No more pages"

        # Verify no duplicate IDs
        ids_page1 = {p["id"] for p in page1}
        ids_page2 = {p["id"] for p in page2}
        assert len(ids_page1.intersection(ids_page2)) == 0, "No duplicates across pages"

    def test_scroll_points_with_vectors(self, tmp_path, test_vectors):
        """GIVEN vectors stored
        WHEN scroll_points(with_vectors=True)
        THEN includes vector data in results

        AC: scroll_points() supports with_vectors parameter
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": test_vectors[0].tolist(),
                "payload": {"path": "test.py"},
            }
        ]
        store.upsert_points("test_coll", points)

        # Scroll with vectors
        results, _ = store.scroll_points(
            collection_name="test_coll", limit=10, with_payload=True, with_vectors=True
        )

        assert len(results) == 1
        assert "vector" in results[0], "Should include vector"
        assert len(results[0]["vector"]) == 1536

    def test_search_returns_similar_vectors(self, tmp_path, test_vectors):
        """GIVEN vectors stored in collection
        WHEN search() is called with query vector
        THEN returns top N results sorted by similarity score

        AC: search() performs similarity search
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store 10 vectors
        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py", "language": "python"},
            }
            for i in range(10)
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search with first vector (should match itself)
        query_vector = test_vectors[0].tolist()
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = query_vector

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=5,
        )

        assert len(results) <= 5, "Should respect limit"
        assert len(results) > 0, "Should find matches"

        # Results should have similarity scores
        assert all("score" in r for r in results), "Should include scores"
        assert all("id" in r for r in results)
        assert all("payload" in r for r in results)

        # Scores should be descending
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Scores should be descending"

        # Best match should be the query vector itself
        assert results[0]["id"] == "vec_0", "Best match should be query vector"
        assert results[0]["score"] > 0.99, "Self-similarity should be ~1.0"

    def test_search_with_score_threshold(self, tmp_path, test_vectors):
        """GIVEN vectors stored
        WHEN search() is called with score_threshold
        THEN only returns results above threshold

        AC: search() supports score_threshold filtering
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": f"vec_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search with high threshold
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = test_vectors[0].tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=10,
            score_threshold=0.95,
        )

        # Should only return very similar vectors
        assert all(r["score"] >= 0.95 for r in results), "All scores above threshold"

    def test_search_with_filter_conditions(self, tmp_path, test_vectors):
        """GIVEN vectors with different metadata
        WHEN search() with filter_conditions
        THEN only returns matching vectors

        AC: search() supports filter_conditions
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store vectors with different languages
        points = [
            {
                "id": "python_0",
                "vector": test_vectors[0].tolist(),
                "payload": {"path": "test.py", "language": "python"},
            },
            {
                "id": "python_1",
                "vector": test_vectors[1].tolist(),
                "payload": {"path": "main.py", "language": "python"},
            },
            {
                "id": "javascript_0",
                "vector": test_vectors[2].tolist(),
                "payload": {"path": "app.js", "language": "javascript"},
            },
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search with language filter
        filter_conditions = {"language": "python"}
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = test_vectors[0].tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=10,
            filter_conditions=filter_conditions,
        )

        # Should only return Python files
        assert all(r["payload"]["language"] == "python" for r in results)
        assert len(results) == 2


class TestBatchGitOperations:
    """Test batch git operations for performance."""

    def test_batch_git_blob_hashes_performance(self, tmp_path):
        """GIVEN 100 files in git repo
        WHEN _get_blob_hashes_batch() is called
        THEN completes in <500ms

        AC: Batch git operations <500ms for 100 files
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        # Create 100 files
        file_paths = []
        for i in range(100):
            test_file = tmp_path / f"file_{i}.py"
            test_file.write_text(f"# File {i}\n")
            file_paths.append(f"file_{i}.py")

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        store = FilesystemVectorStore(base_path=tmp_path)

        # Measure batch operation time
        start = time.time()
        blob_hashes = store._get_blob_hashes_batch(file_paths, tmp_path)
        duration = time.time() - start

        assert duration < 0.5, f"Batch git operation too slow: {duration:.3f}s"
        assert len(blob_hashes) == 100, "Should get all blob hashes"
        assert all(isinstance(h, str) for h in blob_hashes.values())

    def test_batch_uncommitted_check_performance(self, tmp_path):
        """GIVEN 100 files with some modified
        WHEN _check_uncommitted_batch() is called
        THEN completes in <500ms

        AC: Batch git status check <500ms for 100 files
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo with 100 files
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        file_paths = []
        for i in range(100):
            test_file = tmp_path / f"file_{i}.py"
            test_file.write_text(f"# File {i}\n")
            file_paths.append(f"file_{i}.py")

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True
        )

        # Modify 10 files
        for i in range(10):
            (tmp_path / f"file_{i}.py").write_text(f"# Modified {i}\n")

        store = FilesystemVectorStore(base_path=tmp_path)

        # Measure batch operation time
        start = time.time()
        uncommitted = store._check_uncommitted_batch(file_paths, tmp_path)
        duration = time.time() - start

        assert duration < 0.5, f"Batch git status too slow: {duration:.3f}s"
        assert len(uncommitted) == 10, "Should detect 10 modified files"


class TestProgressReporting:
    """Test progress_callback functionality."""

    def test_progress_callback_invoked_for_each_point(self, tmp_path):
        """GIVEN progress_callback parameter
        WHEN upsert_points() is called
        THEN callback invoked for each point

        AC: progress_callback called for each file
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Track callback invocations
        callbacks = []

        def progress_callback(current, total, file_path, info):
            callbacks.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                }
            )

        # Store 5 points with progress tracking
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(5)
        ]

        store.begin_indexing("test_coll")
        store.upsert_points(
            collection_name="test_coll",
            points=points,
            progress_callback=progress_callback,
        )
        store.end_indexing("test_coll", progress_callback=progress_callback)

        # Verify callback was called: 5 for points + callbacks from end_indexing
        assert (
            len(callbacks) >= 5
        ), "Callback should be called for each point plus HNSW index building"

        # Verify first 5 callbacks are for individual points
        assert callbacks[0]["current"] == 1
        assert callbacks[0]["total"] == 5
        assert callbacks[4]["current"] == 5
        assert callbacks[4]["total"] == 5

        # Verify HNSW index building callbacks exist
        # NOTE (Story #540 Fix): Progress callback format changed in HNSW manager
        # Messages now use emojis and different wording
        hnsw_messages = [cb["info"] for cb in callbacks[5:]]
        assert "🔧 Rebuilding HNSW index..." in hnsw_messages or "🔧 Building HNSW index..." in hnsw_messages
        assert any("HNSW index built" in msg or "index complete" in msg for msg in hnsw_messages)


class TestFilesystemClientCompatibility:
    """Test FilesystemClient-compatible interface methods."""

    def test_ensure_provider_aware_collection_creates_collection(self, tmp_path):
        """GIVEN embedding provider with model info
        WHEN ensure_provider_aware_collection() is called
        THEN collection created with provider-aware name

        AC: ensure_provider_aware_collection() creates collection
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Mock embedding provider
        class MockEmbeddingProvider:
            def get_current_model(self):
                return "voyage-code-2"

            def get_model_info(self):
                return {"dimensions": 1536}

        # Mock config
        class MockConfig:
            pass

        store = FilesystemVectorStore(base_path=tmp_path)
        provider = MockEmbeddingProvider()
        config = MockConfig()

        # Should create collection
        collection_name = store.ensure_provider_aware_collection(
            config, provider, quiet=True
        )

        assert collection_name == "voyage-code-2"
        assert store.collection_exists(collection_name)

    def test_ensure_provider_aware_collection_uses_existing(self, tmp_path):
        """GIVEN existing collection
        WHEN ensure_provider_aware_collection() is called
        THEN returns existing collection name

        AC: ensure_provider_aware_collection() handles existing collections
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        class MockEmbeddingProvider:
            def get_current_model(self):
                return "test-model"

            def get_model_info(self):
                return {"dimensions": 768}

        class MockConfig:
            pass

        store = FilesystemVectorStore(base_path=tmp_path)
        provider = MockEmbeddingProvider()
        config = MockConfig()

        # Pre-create collection
        store.create_collection("test-model", vector_size=768)

        # Should use existing
        collection_name = store.ensure_provider_aware_collection(
            config, provider, quiet=True
        )

        assert collection_name == "test-model"

    def test_clear_collection_removes_all_vectors(self, tmp_path):
        """GIVEN collection with 10 vectors
        WHEN clear_collection() is called
        THEN all vectors removed but collection structure remains

        AC: clear_collection() deletes all vectors
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store 10 vectors
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.upsert_points("test_coll", points)

        assert store.count_points("test_coll") == 10

        # Clear collection
        result = store.clear_collection("test_coll")

        assert result is True
        assert store.count_points("test_coll") == 0
        assert store.collection_exists("test_coll"), "Collection should still exist"

        # Verify metadata and projection matrix still exist
        coll_path = tmp_path / "test_coll"
        assert (coll_path / "collection_meta.json").exists()
        assert (coll_path / "projection_matrix.npy").exists()

    def test_create_point_returns_point_dict(self, tmp_path):
        """GIVEN vector and payload
        WHEN create_point() is called
        THEN returns properly formatted point dictionary

        AC: create_point() creates point objects for batch operations
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)

        vector = np.random.randn(1536).tolist()
        payload = {"path": "test.py", "language": "python"}

        point = store.create_point(vector=vector, payload=payload, point_id="test_001")

        assert point["id"] == "test_001"
        assert point["vector"] == vector
        assert point["payload"] == payload

    def test_delete_by_filter_removes_matching_vectors(self, tmp_path):
        """GIVEN vectors with different languages
        WHEN delete_by_filter() is called
        THEN only matching vectors removed

        AC: delete_by_filter() deletes vectors matching filter
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store vectors with different languages
        points = [
            {
                "id": "py_1",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "test1.py", "language": "python"},
            },
            {
                "id": "py_2",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "test2.py", "language": "python"},
            },
            {
                "id": "js_1",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "app.js", "language": "javascript"},
            },
        ]
        store.upsert_points("test_coll", points)

        assert store.count_points("test_coll") == 3

        # Delete Python files
        result = store.delete_by_filter(
            collection_name="test_coll", filter_conditions={"language": "python"}
        )

        assert result is True
        assert store.count_points("test_coll") == 1

        # Verify JavaScript file remains
        remaining = store.get_point("js_1", "test_coll")
        assert remaining is not None
        assert remaining["payload"]["language"] == "javascript"

    def test_get_collection_info_returns_metadata(self, tmp_path):
        """GIVEN collection with metadata
        WHEN get_collection_info() is called
        THEN returns collection metadata

        AC: get_collection_info() returns collection information
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        info = store.get_collection_info("test_coll")

        assert info is not None
        assert info["name"] == "test_coll"
        assert info["vector_size"] == 1536
        assert "created_at" in info

    def test_health_check_returns_true_for_accessible_filesystem(self, tmp_path):
        """GIVEN writable filesystem
        WHEN health_check() is called
        THEN returns True

        AC: health_check() verifies filesystem accessibility
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)

        assert store.health_check() is True

    def test_batch_update_points_updates_payloads(self, tmp_path):
        """GIVEN multiple points to update
        WHEN _batch_update_points() is called
        THEN all payloads updated

        AC: _batch_update_points() updates multiple points
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Store initial points
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file_{i}.py", "branch": "main"},
            }
            for i in range(5)
        ]
        store.upsert_points("test_coll", points)

        # Update payloads
        updates = [
            {"id": f"vec_{i}", "payload": {"path": f"file_{i}.py", "branch": "feature"}}
            for i in range(5)
        ]

        result = store._batch_update_points(updates, "test_coll")

        assert result is True

        # Verify updates
        for i in range(5):
            point = store.get_point(f"vec_{i}", "test_coll")
            assert point["payload"]["branch"] == "feature"

    def test_resolve_collection_name_returns_model_based_name(self, tmp_path):
        """GIVEN embedding provider with model name
        WHEN resolve_collection_name() is called
        THEN returns filesystem-safe model name

        AC: resolve_collection_name() generates collection name from model
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        class MockEmbeddingProvider:
            def get_current_model(self):
                return "voyage/code-2"

        class MockConfig:
            pass

        store = FilesystemVectorStore(base_path=tmp_path)
        provider = MockEmbeddingProvider()
        config = MockConfig()

        collection_name = store.resolve_collection_name(config, provider)

        # Should replace slashes with underscores for filesystem safety
        assert "/" not in collection_name
        assert collection_name == "voyage_code-2"

    def test_ensure_payload_indexes_is_noop(self, tmp_path):
        """GIVEN filesystem backend
        WHEN ensure_payload_indexes() is called
        THEN returns without error (no-op)

        AC: ensure_payload_indexes() is no-op for filesystem
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Should not raise error
        store.ensure_payload_indexes("test_coll", context="test")

    def test_rebuild_payload_indexes_is_noop(self, tmp_path):
        """GIVEN filesystem backend
        WHEN rebuild_payload_indexes() is called
        THEN returns True (no-op)

        AC: rebuild_payload_indexes() is no-op for filesystem
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        result = store.rebuild_payload_indexes("test_coll")
        assert result is True


class TestHNSWStalenessCoordination:
    """Test HNSW staleness coordination between watch mode and query."""

    def test_search_rebuilds_stale_hnsw_index(self, tmp_path):
        """GIVEN stale HNSW index (marked by watch mode)
        WHEN search() is called
        THEN HNSW index is automatically rebuilt before searching

        AC: search() detects staleness and triggers rebuild
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Initial indexing with normal HNSW build
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll", skip_hnsw_rebuild=False)

        # Verify HNSW is fresh
        collection_path = tmp_path / "test_coll"
        hnsw_manager = HNSWIndexManager(vector_dim=1536, space="cosine")
        assert not hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be fresh after build"

        # Simulate watch mode: add more vectors and skip rebuild
        new_points = [
            {
                "id": f"vec_new_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"new_file_{i}.py"},
            }
            for i in range(5)
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", new_points)
        store.end_indexing("test_coll", skip_hnsw_rebuild=True)  # Watch mode

        # Verify HNSW is now stale
        assert hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be stale after watch mode"

        # Perform search - should auto-rebuild
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=5,
        )

        # Verify search succeeded
        assert len(results) > 0, "Search should return results"

        # Verify HNSW is now fresh (rebuilt during search)
        assert not hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be fresh after search rebuild"

    def test_search_uses_fresh_hnsw_without_rebuild(self, tmp_path):
        """GIVEN fresh HNSW index
        WHEN search() is called
        THEN uses existing HNSW without rebuild

        AC: search() skips rebuild when HNSW is fresh
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager

        store = FilesystemVectorStore(base_path=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        # Index with normal HNSW build
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file_{i}.py"},
            }
            for i in range(10)
        ]
        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll", skip_hnsw_rebuild=False)

        # Verify HNSW is fresh
        collection_path = tmp_path / "test_coll"
        hnsw_manager = HNSWIndexManager(vector_dim=1536, space="cosine")
        assert not hnsw_manager.is_stale(collection_path), "HNSW should be fresh"

        # Get HNSW file modification time
        hnsw_file = collection_path / "hnsw_index.bin"
        mtime_before = hnsw_file.stat().st_mtime

        # Perform search (should use existing HNSW)
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=5,
        )

        # Verify search succeeded
        assert len(results) > 0, "Search should return results"

        # Verify HNSW was NOT rebuilt (file not modified)
        mtime_after = hnsw_file.stat().st_mtime
        assert mtime_before == mtime_after, "HNSW should not be rebuilt when fresh"

        # Verify still fresh
        assert not hnsw_manager.is_stale(collection_path), "HNSW should still be fresh"


class TestStory3ContentRetrievalAndStaleness:
    """Test Story 3: Chunk content retrieval and staleness detection."""

    def test_search_returns_content_for_non_git_repo(self, tmp_path):
        """GIVEN non-git repo with chunk_text in JSON
        WHEN search() is called
        THEN results include content from chunk_text and no staleness

        AC: Non-git repos return chunk_text with is_stale=False
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # No git init - plain directory
        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        content = "def hello():\n    return 'world'\n"
        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 0,
                    "line_end": 2,
                    "content": content,
                },
            }
        ]

        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=1,
        )

        assert len(results) == 1
        assert "content" in results[0]["payload"]
        assert results[0]["payload"]["content"] == content
        assert "staleness" in results[0]
        assert results[0]["staleness"]["is_stale"] is False
        assert results[0]["staleness"]["staleness_indicator"] is None

    def test_search_returns_content_from_current_file_if_unchanged(self, tmp_path):
        """GIVEN git repo with clean file
        WHEN search() is called
        THEN content retrieved from current file with no staleness

        AC: Clean git files return current content with is_stale=False
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        content = "def foo():\n    return 42\n"
        test_file.write_text(content)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 1,
                    "line_end": 2,
                    "content": content,
                },
            }
        ]

        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search (file unchanged)
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=1,
        )

        assert len(results) == 1
        assert results[0]["payload"]["content"] == content
        assert results[0]["staleness"]["is_stale"] is False
        assert results[0]["staleness"]["hash_mismatch"] is False

    def test_search_detects_modified_file_via_hash(self, tmp_path):
        """GIVEN indexed file later modified
        WHEN search() is called
        THEN staleness detected via hash mismatch, content from git blob

        AC: Modified files detected via hash, content retrieved from git blob
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        original_content = "def foo():\n    return 42\n"
        test_file.write_text(original_content)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 1,
                    "line_end": 2,
                    "content": original_content,
                },
            }
        ]

        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Modify file AFTER indexing
        modified_content = "def foo():\n    return 99\n"
        test_file.write_text(modified_content)

        # Search - should detect staleness
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=1,
        )

        assert len(results) == 1
        # Content should be from git blob (original), not modified file
        assert results[0]["payload"]["content"] == original_content
        assert results[0]["staleness"]["is_stale"] is True
        assert results[0]["staleness"]["staleness_indicator"] == "⚠️ Modified"
        assert (
            results[0]["staleness"]["staleness_reason"]
            == "file_modified_after_indexing"
        )
        assert results[0]["staleness"]["hash_mismatch"] is True

    def test_search_detects_deleted_file(self, tmp_path):
        """GIVEN indexed file later deleted
        WHEN search() is called
        THEN staleness indicates deletion, content from git blob

        AC: Deleted files detected, content retrieved from git blob
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        content = "def bar(): pass\n"
        test_file.write_text(content)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": "test_001",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": "test.py",
                    "line_start": 1,
                    "line_end": 1,
                    "content": content,
                },
            }
        ]

        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Delete file AFTER indexing
        test_file.unlink()

        # Search - should detect deletion
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=1,
        )

        assert len(results) == 1
        # Content should be from git blob
        assert results[0]["payload"]["content"] == content
        assert results[0]["staleness"]["is_stale"] is True
        assert results[0]["staleness"]["staleness_indicator"] == "🗑️ Deleted"
        assert results[0]["staleness"]["staleness_reason"] == "file_deleted"

    def test_compute_file_hash_matches_git_blob_hash(self, tmp_path):
        """GIVEN file committed to git
        WHEN _compute_file_hash() is called
        THEN hash matches git's blob hash

        AC: Hash computation compatible with git
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        test_file.write_text("test content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        # Get git's blob hash
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "test.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        git_hash = result.stdout.split()[2]

        # Compute our hash
        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        our_hash = store._compute_file_hash(test_file)

        assert our_hash == git_hash

    def test_retrieve_from_git_blob_extracts_chunk(self, tmp_path):
        """GIVEN git blob hash
        WHEN _retrieve_from_git_blob() is called
        THEN correct chunk content extracted

        AC: Git blob retrieval works correctly
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo with multi-line file
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        test_file = tmp_path / "test.py"
        lines = ["line 0\n", "line 1\n", "line 2\n", "line 3\n", "line 4\n"]
        test_file.write_text("".join(lines))
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test"], cwd=tmp_path, capture_output=True
        )

        # Get blob hash
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "test.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        blob_hash = result.stdout.split()[2]

        # Retrieve chunk (1-based lines 2-3, which are "line 1" and "line 2")
        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        chunk = store._retrieve_from_git_blob(blob_hash, start_line=2, end_line=3)

        assert chunk == "line 1\nline 2\n"

    def test_search_with_multiple_results_all_have_content(self, tmp_path):
        """GIVEN multiple indexed chunks
        WHEN search() returns multiple results
        THEN all results include content and staleness

        AC: Content retrieval works for multiple results
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Non-git for simplicity
        store = FilesystemVectorStore(base_path=tmp_path, project_root=tmp_path)
        store.create_collection("test_coll", vector_size=1536)

        points = [
            {
                "id": f"test_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {
                    "path": f"file_{i}.py",
                    "line_start": 0,
                    "line_end": 2,
                    "content": f"content {i}",
                },
            }
            for i in range(5)
        ]

        store.begin_indexing("test_coll")
        store.upsert_points("test_coll", points)
        store.end_indexing("test_coll")

        # Search for all
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name="test_coll",
            limit=5,
        )

        assert len(results) == 5
        for i, result in enumerate(results):
            assert "content" in result["payload"]
            assert "staleness" in result
            # All should be non-stale (non-git repo)
            assert result["staleness"]["is_stale"] is False
