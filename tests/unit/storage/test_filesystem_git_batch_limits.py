"""Unit tests for FilesystemVectorStore git batching limits.

Test Strategy: Reproduce and fix the "Argument list too long" error (Errno 7)
that occurs when passing 1000+ file paths to git ls-tree command.
"""

import numpy as np
import pytest
import subprocess
from unittest.mock import patch, MagicMock


class TestGitBatchLimits:
    """Test git command batching to avoid Errno 7."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        # Generate enough for 1500 files
        return np.random.randn(1500, 1536)

    @pytest.fixture
    def mock_git_repo(self, tmp_path, monkeypatch):
        """Mock git repository detection and commands."""

        # Mock _get_repo_root to return tmp_path
        def mock_get_repo_root():
            return tmp_path

        # Track git ls-tree calls to verify batching
        git_calls = []

        original_run = subprocess.run

        def mock_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "git" and "ls-tree" in cmd:
                git_calls.append(cmd)
                # Calculate number of file paths in this call
                file_paths = [
                    arg
                    for arg in cmd
                    if not arg.startswith("-")
                    and arg != "git"
                    and arg != "ls-tree"
                    and arg != "HEAD"
                ]

                # Simulate Errno 7 if too many files (> 100 in our test)
                if len(file_paths) > 100:
                    raise OSError(7, "Argument list too long", "git")

                # Mock successful response
                result = MagicMock()
                result.returncode = 0
                result.stdout = "\n".join(
                    [
                        f"100644 blob abc123{i}\t{path}"
                        for i, path in enumerate(file_paths)
                    ]
                )
                return result

            # Pass through other commands
            return original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        return {
            "repo_root": tmp_path,
            "git_calls": git_calls,
            "mock_get_repo_root": mock_get_repo_root,
        }

    def test_git_ls_tree_with_many_files_would_fail_without_batching(
        self, tmp_path, test_vectors, mock_git_repo
    ):
        """GIVEN 1000+ file paths to index
        WHEN _get_blob_hashes_batch() is called
        THEN operation succeeds because batching prevents Errno 7

        This test verifies the fix by showing that with batching, large numbers
        of files can be processed without hitting "Argument list too long" error.
        The mock enforces a 100-file limit to simulate the system limit.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Patch _get_repo_root to return our mock repo
        with patch.object(
            FilesystemVectorStore,
            "_get_repo_root",
            return_value=mock_git_repo["repo_root"],
        ):
            store = FilesystemVectorStore(base_path=tmp_path)
            store.create_collection("test_coll", vector_size=1536)

            # Create 1500 points (would exceed argument list limit without batching)
            points = [
                {
                    "id": f"test_{i:04d}",
                    "vector": test_vectors[i].tolist(),
                    "payload": {
                        "path": f"src/file_{i:04d}.py",
                        "line_start": 10,
                        "line_end": 20,
                        "language": "python",
                        "type": "content",
                    },
                }
                for i in range(1500)
            ]

            # With batching fix, this should succeed
            result = store.upsert_points("test_coll", points)

            assert result["status"] == "ok"

            # Verify git ls-tree was called in batches
            git_calls = mock_git_repo["git_calls"]
            assert len(git_calls) > 1, "Should batch git ls-tree calls"

    def test_git_ls_tree_batching_prevents_errno_7(
        self, tmp_path, test_vectors, mock_git_repo
    ):
        """GIVEN 1000+ file paths to index
        WHEN _get_blob_hashes_batch() batches git ls-tree calls (100 files per batch)
        THEN operation succeeds without OSError

        This test verifies the fix works.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Patch _get_repo_root to return our mock repo
        with patch.object(
            FilesystemVectorStore,
            "_get_repo_root",
            return_value=mock_git_repo["repo_root"],
        ):
            store = FilesystemVectorStore(base_path=tmp_path)
            store.create_collection("test_coll", vector_size=1536)

            # Create 1500 points
            points = [
                {
                    "id": f"test_{i:04d}",
                    "vector": test_vectors[i].tolist(),
                    "payload": {
                        "path": f"src/file_{i:04d}.py",
                        "line_start": 10,
                        "line_end": 20,
                        "language": "python",
                        "type": "content",
                    },
                }
                for i in range(1500)
            ]

            # With batching fix, this should succeed
            result = store.upsert_points("test_coll", points)

            assert result["status"] == "ok"

            # Verify git ls-tree was called multiple times (batched)
            git_calls = mock_git_repo["git_calls"]
            assert len(git_calls) > 1, "Should batch git ls-tree calls"

            # Verify each call has <= 100 files
            for call in git_calls:
                file_count = len(
                    [
                        arg
                        for arg in call
                        if not arg.startswith("-")
                        and arg != "git"
                        and arg != "ls-tree"
                        and arg != "HEAD"
                    ]
                )
                assert (
                    file_count <= 100
                ), f"Batch should have <= 100 files, got {file_count}"

    def test_temporal_collection_skips_blob_hash_lookup(
        self, tmp_path, test_vectors, mock_git_repo
    ):
        """GIVEN temporal collection with many files
        WHEN upsert_points() is called with collection_name="code-indexer-temporal"
        THEN blob hash lookup is skipped entirely (no git ls-tree calls)

        This test verifies FIX 1: Skip blob hash lookup for temporal collection.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Patch _get_repo_root to return our mock repo
        with patch.object(
            FilesystemVectorStore,
            "_get_repo_root",
            return_value=mock_git_repo["repo_root"],
        ):
            store = FilesystemVectorStore(base_path=tmp_path)
            store.create_collection("code-indexer-temporal", vector_size=1536)

            # Create 1500 points for temporal collection
            points = [
                {
                    "id": f"test_{i:04d}",
                    "vector": test_vectors[i].tolist(),
                    "payload": {
                        "path": f"src/file_{i:04d}.py",
                        "line_start": 10,
                        "line_end": 20,
                        "language": "python",
                        "type": "content",
                    },
                }
                for i in range(1500)
            ]

            # This should succeed without any git ls-tree calls
            result = store.upsert_points("code-indexer-temporal", points)

            assert result["status"] == "ok"

            # Verify NO git ls-tree calls were made
            git_calls = mock_git_repo["git_calls"]
            assert (
                len(git_calls) == 0
            ), "Temporal collection should skip git ls-tree entirely"

    def test_semantic_collection_still_uses_git_awareness(
        self, tmp_path, test_vectors, mock_git_repo
    ):
        """GIVEN semantic collection with files
        WHEN upsert_points() is called
        THEN git ls-tree is called (with batching) to maintain git-awareness

        This test ensures semantic indexing still gets blob hashes for git-awareness.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Patch _get_repo_root to return our mock repo
        with patch.object(
            FilesystemVectorStore,
            "_get_repo_root",
            return_value=mock_git_repo["repo_root"],
        ):
            store = FilesystemVectorStore(base_path=tmp_path)
            store.create_collection("code-indexer", vector_size=1536)

            # Create 50 points for semantic collection
            points = [
                {
                    "id": f"test_{i:04d}",
                    "vector": test_vectors[i].tolist(),
                    "payload": {
                        "path": f"src/file_{i:04d}.py",
                        "line_start": 10,
                        "line_end": 20,
                        "language": "python",
                        "type": "content",
                    },
                }
                for i in range(50)
            ]

            # This should succeed with git ls-tree calls
            result = store.upsert_points("code-indexer", points)

            assert result["status"] == "ok"

            # Verify git ls-tree WAS called for semantic collection
            git_calls = mock_git_repo["git_calls"]
            assert (
                len(git_calls) > 0
            ), "Semantic collection should use git ls-tree for git-awareness"
