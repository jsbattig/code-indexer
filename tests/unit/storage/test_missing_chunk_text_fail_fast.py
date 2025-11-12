"""Test fail-fast behavior for missing chunk_text in commit messages.

MESSI Rule #2 (Anti-Fallback): When chunk_text is missing for payload types
that require it (like commit_message), the system should fail fast with a
clear error message instead of silently falling back to empty string.
"""

import pytest
import numpy as np
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


def test_missing_chunk_text_for_commit_message_raises_runtime_error(tmp_path):
    """Test that missing chunk_text for commit_message triggers RuntimeError.

    MESSI Rule #2 (Anti-Fallback): No silent fallbacks that mask bugs.
    If chunk_text is None for a commit_message, it indicates an indexing bug
    and should fail fast with a clear error message.
    """
    # Arrange
    store = FilesystemVectorStore(tmp_path / "index", project_root=tmp_path)
    store.create_collection("test_collection", vector_size=64)

    vector = np.random.rand(64)
    payload = {
        "type": "commit_message",
        "commit_hash": "abc123",
        "author": "test",
        "path": "test.py",
    }
    point_id = "test_point_1"

    # Act & Assert: chunk_text=None should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        store._prepare_vector_data_batch(
            point_id=point_id,
            vector=vector,
            payload=payload,
            chunk_text=None,  # Missing chunk_text for commit_message
            repo_root=tmp_path,
            blob_hashes={},
            uncommitted_files=set(),
        )

    # Verify error message is clear and actionable
    error_msg = str(exc_info.value)
    assert "Missing chunk_text" in error_msg
    assert "commit_message" in error_msg
    assert "indexing bug" in error_msg.lower()
    assert point_id in error_msg
