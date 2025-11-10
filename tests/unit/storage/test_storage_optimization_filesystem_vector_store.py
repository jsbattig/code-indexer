"""Tests for temporal storage optimization in filesystem_vector_store.

Tests that added/deleted temporal diffs don't store content, only pointers.
"""

import pytest
import numpy as np
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalStorageOptimization:
    """Test that filesystem_vector_store handles temporal pointer storage correctly."""

    @pytest.fixture
    def vector_store(self, tmp_path):
        """Create a temporary filesystem vector store."""
        base_path = tmp_path / "index"
        project_root = tmp_path / "project"
        project_root.mkdir()
        return FilesystemVectorStore(base_path, project_root)

    def test_added_file_payload_does_not_store_chunk_text(self, vector_store):
        """Test that added temporal diffs don't store chunk_text field."""
        # Create payload for an added file with reconstruct_from_git marker
        payload = {
            "type": "commit_diff",
            "diff_type": "added",
            "commit_hash": "abc123",
            "path": "test.py",
            "reconstruct_from_git": True,
            "content": "+def hello():\n+    return 'world'\n",  # Content for embedding only
        }

        # Prepare vector data
        vector_data = vector_store._prepare_vector_data_batch(
            point_id="test:diff:abc123:test.py:0",
            vector=np.array([0.1, 0.2, 0.3]),
            payload=payload,
            chunk_text=None,
            repo_root=None,
            blob_hashes={},
            uncommitted_files=set(),
        )

        # Verify: NO chunk_text field (pointer-based storage)
        assert (
            "chunk_text" not in vector_data
        ), "Added files should NOT store chunk_text"

        # Verify: content removed from payload (not stored twice)
        assert (
            "content" not in vector_data["payload"]
        ), "Content should be removed from payload"

        # Verify: reconstruct_from_git marker preserved
        assert vector_data["payload"]["reconstruct_from_git"] is True