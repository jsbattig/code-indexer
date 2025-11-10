"""
E2E test exposing critical data loss bug where storage layer ignores chunk_text from point structure.

Bug: FilesystemVectorStore.upsert_points() extracts only id, vector, and payload from point structure,
but never extracts chunk_text, causing content loss when chunk_text is at root level (not in payload).
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_storage():
    """Create temporary filesystem vector store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FilesystemVectorStore(base_path=Path(tmpdir))
        yield store


def test_chunk_text_preserved_from_point_root(temp_storage):
    """
    Test that chunk_text at point root level is preserved during upsert.

    This test exposes the bug where chunk_text is ignored during upsert_points processing.

    CRITICAL: Points may have chunk_text at root level (optimization path) rather than in payload.
    Storage layer MUST extract and persist chunk_text from point root.
    """
    collection = "test_collection"

    # Create collection
    temp_storage.create_collection(collection_name=collection, vector_size=64)

    # Create point with chunk_text at ROOT level (not in payload)
    # This is the optimization path used by temporal indexer
    original_chunk_text = "def authenticate(user, password):\n    return True"

    point = {
        "id": "test_point_1",
        "vector": np.random.rand(64).tolist(),
        "payload": {
            "file_path": "src/auth.py",
            "type": "code_chunk",
            # NOTE: NO content field in payload - chunk_text is at root
        },
        "chunk_text": original_chunk_text,  # At ROOT level
    }

    # Upsert point
    temp_storage.upsert_points(
        collection_name=collection,
        points=[point],
    )

    # Retrieve vector from disk
    retrieved = temp_storage.get_point(
        point_id="test_point_1",
        collection_name=collection,
    )

    assert retrieved is not None, "Should retrieve the point"

    # CRITICAL ASSERTIONS: chunk_text must be preserved
    assert "chunk_text" in retrieved, "chunk_text field must exist in retrieved vector"
    assert retrieved["chunk_text"] == original_chunk_text, (
        f"chunk_text must match original. "
        f"Expected: {original_chunk_text!r}, "
        f"Got: {retrieved.get('chunk_text', 'MISSING')!r}"
    )

    # Verify payload does NOT have content field (optimization path)
    assert "content" not in retrieved.get("payload", {}), (
        "content should NOT be in payload when chunk_text is at root level"
    )
