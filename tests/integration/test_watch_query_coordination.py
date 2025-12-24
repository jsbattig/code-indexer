"""Integration tests for watch mode → query coordination via HNSW staleness.

This test suite verifies the end-to-end workflow:
1. Normal indexing builds HNSW index
2. Watch mode marks HNSW as stale (skips rebuild)
3. Query detects staleness and rebuilds before searching
"""

import subprocess
import time
from unittest.mock import Mock

import numpy as np
import pytest


@pytest.fixture
def git_repo_with_files(tmp_path):
    """Create a git repo with some test files."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Create test files
    (tmp_path / "file1.py").write_text("def foo(): pass\n")
    (tmp_path / "file2.py").write_text("def bar(): pass\n")
    (tmp_path / "file3.py").write_text("def baz(): pass\n")

    # Commit files
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    return tmp_path


class TestWatchQueryCoordination:
    """Test watch mode and query coordination via HNSW staleness."""

    def test_watch_marks_stale_query_rebuilds(self, git_repo_with_files):
        """GIVEN normal indexing followed by watch mode update
        WHEN query is executed
        THEN query automatically rebuilds stale HNSW index

        This tests the complete workflow:
        1. Initial indexing (skip_hnsw_rebuild=False) → fresh HNSW
        2. Watch mode update (skip_hnsw_rebuild=True) → stale HNSW
        3. Query detects staleness and rebuilds → fresh HNSW + correct results
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager

        repo_path = git_repo_with_files
        store = FilesystemVectorStore(base_path=repo_path, project_root=repo_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # === STEP 1: Initial indexing (normal mode) ===
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file{i}.py", "content": f"content {i}"},
            }
            for i in range(1, 4)
        ]

        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, points)
        store.end_indexing(collection_name, skip_hnsw_rebuild=False)

        # Verify HNSW is fresh after initial indexing
        collection_path = repo_path / collection_name
        hnsw_manager = HNSWIndexManager(vector_dim=1536, space="cosine")
        assert not hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be fresh after normal indexing"

        # === STEP 2: Watch mode update (simulate file change) ===
        new_points = [
            {
                "id": "vec_new_1",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "file_new.py", "content": "new content"},
            }
        ]

        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, new_points)
        store.end_indexing(collection_name, skip_hnsw_rebuild=True)  # Watch mode!

        # Verify HNSW is now stale
        assert hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be stale after watch mode"

        # === STEP 3: Query triggers auto-rebuild ===
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results = store.search(
            query="test query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=5,
        )

        # Verify search succeeded
        assert len(results) > 0, "Search should return results"

        # Verify HNSW is now fresh (rebuilt during search)
        assert not hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be fresh after query rebuild"

        # Verify all vectors are searchable (including watch mode addition)
        assert (
            store.count_points(collection_name) == 4
        ), "Should have 4 vectors (3 initial + 1 watch)"

    def test_multiple_watch_changes_single_rebuild(self, git_repo_with_files):
        """GIVEN multiple watch mode updates
        WHEN first query executes
        THEN rebuilds once, second query uses fresh HNSW

        This verifies that:
        1. Multiple watch updates keep HNSW stale (no rebuilds)
        2. First query rebuilds once
        3. Second query uses fresh HNSW (no rebuild)
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager

        repo_path = git_repo_with_files
        store = FilesystemVectorStore(base_path=repo_path, project_root=repo_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial indexing
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file{i}.py"},
            }
            for i in range(1, 4)
        ]

        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, points)
        store.end_indexing(collection_name, skip_hnsw_rebuild=False)

        collection_path = repo_path / collection_name
        hnsw_manager = HNSWIndexManager(vector_dim=1536, space="cosine")

        # === Simulate 5 watch mode updates ===
        for i in range(5):
            new_point = [
                {
                    "id": f"vec_watch_{i}",
                    "vector": np.random.randn(1536).tolist(),
                    "payload": {"path": f"watch_file_{i}.py"},
                }
            ]
            store.begin_indexing(collection_name)
            store.upsert_points(collection_name, new_point)
            store.end_indexing(collection_name, skip_hnsw_rebuild=True)

        # Verify HNSW is stale after all watch updates
        assert hnsw_manager.is_stale(collection_path), "HNSW should be stale"

        # === First query: should trigger rebuild ===
        hnsw_file = collection_path / "hnsw_index.bin"
        mtime_before_first_query = hnsw_file.stat().st_mtime

        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = np.random.randn(
            1536
        ).tolist()

        results1 = store.search(
            query="first query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=5,
        )

        assert len(results1) > 0, "First search should return results"
        assert not hnsw_manager.is_stale(
            collection_path
        ), "HNSW should be fresh after first query"

        # Verify HNSW was rebuilt (file modified)
        mtime_after_first_query = hnsw_file.stat().st_mtime
        assert (
            mtime_after_first_query > mtime_before_first_query
        ), "HNSW should be rebuilt on first query"

        # === Second query: should NOT trigger rebuild ===
        # Small delay to ensure mtime would change if file was modified
        time.sleep(0.01)

        results2 = store.search(
            query="second query",
            embedding_provider=mock_embedding_provider,
            collection_name=collection_name,
            limit=5,
        )

        assert len(results2) > 0, "Second search should return results"
        assert not hnsw_manager.is_stale(collection_path), "HNSW should still be fresh"

        # Verify HNSW was NOT rebuilt (file not modified)
        mtime_after_second_query = hnsw_file.stat().st_mtime
        assert (
            mtime_after_second_query == mtime_after_first_query
        ), "HNSW should not be rebuilt on second query"

        # Verify all vectors present
        assert (
            store.count_points(collection_name) == 8
        ), "Should have 8 vectors (3 initial + 5 watch)"

    def test_watch_mode_performance_benefit(self, git_repo_with_files):
        """GIVEN watch mode processing
        WHEN processing file updates
        THEN completes faster than normal mode (no HNSW rebuild)

        This is a performance validation test to ensure watch mode
        actually provides the expected speed benefit.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        repo_path = git_repo_with_files
        store = FilesystemVectorStore(base_path=repo_path, project_root=repo_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial indexing with 100 vectors
        points = [
            {
                "id": f"vec_{i}",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": f"file{i}.py"},
            }
            for i in range(100)
        ]

        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, points)
        store.end_indexing(collection_name, skip_hnsw_rebuild=False)

        # === Test watch mode update speed ===
        new_point = [
            {
                "id": "vec_watch",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "watch_file.py"},
            }
        ]

        start_watch = time.time()
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, new_point)
        store.end_indexing(collection_name, skip_hnsw_rebuild=True)
        watch_duration = time.time() - start_watch

        # === Test normal mode update speed (for comparison) ===
        new_point2 = [
            {
                "id": "vec_normal",
                "vector": np.random.randn(1536).tolist(),
                "payload": {"path": "normal_file.py"},
            }
        ]

        start_normal = time.time()
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, new_point2)
        store.end_indexing(collection_name, skip_hnsw_rebuild=False)
        normal_duration = time.time() - start_normal

        # Watch mode should be significantly faster (at least 2x)
        # With 100 vectors, HNSW rebuild takes significant time
        assert (
            watch_duration < normal_duration / 2
        ), f"Watch mode ({watch_duration:.3f}s) should be faster than normal mode ({normal_duration:.3f}s)"

        # Watch mode should complete in <2 seconds (requirement)
        assert (
            watch_duration < 2.0
        ), f"Watch mode should complete in <2s, took {watch_duration:.3f}s"
