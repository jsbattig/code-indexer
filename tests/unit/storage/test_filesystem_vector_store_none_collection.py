"""Test FilesystemVectorStore handling of None collection_name.

This test reproduces the bug where upsert_points is called with collection_name=None,
causing TypeError: unsupported operand type(s) for /: 'PosixPath' and 'NoneType'.

Bug Context:
- FileChunkingManager calls upsert_points with metadata.get("collection_name")
- If "collection_name" key doesn't exist in metadata, it returns None
- FilesystemVectorStore does: self.base_path / collection_name
- When collection_name is None, this causes the TypeError

Fix: Handle None collection_name by using the first/only available collection.
"""

import pytest
import tempfile
from pathlib import Path
import numpy as np

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestFilesystemVectorStoreNoneCollection:
    """Test suite for None collection_name handling."""

    def test_upsert_points_with_none_collection_name_auto_resolves_single_collection(self):
        """After fix: calling upsert_points with collection_name=None auto-resolves when only one collection.

        Before fix: This raised TypeError: unsupported operand type(s) for /: 'PosixPath' and 'NoneType'
        After fix: Auto-resolves to the single available collection and succeeds.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "index"
            project_root = Path(tmpdir)

            # Initialize store
            store = FilesystemVectorStore(base_path=base_path, project_root=project_root)

            # Create a collection
            store.create_collection("test_collection", vector_size=384)

            # Prepare test point
            test_point = {
                'id': 'test_point_1',
                'vector': np.random.rand(384).tolist(),
                'payload': {
                    'path': 'test.py',
                    'content': 'test content',
                    'start_line': 1,
                    'end_line': 10,
                    'language': 'python'
                }
            }

            # FIX VERIFICATION: Call upsert_points with collection_name=None
            # This mimics what FileChunkingManager does: metadata.get("collection_name")
            # After fix: Should auto-resolve to "test_collection" and succeed
            result = store.upsert_points(
                collection_name=None,  # Was causing bug, now auto-resolves
                points=[test_point]
            )

            # Should succeed
            assert result['status'] == 'ok'
            assert result['count'] == 1

            # Verify point was actually stored
            assert store.count_points("test_collection") == 1

    def test_upsert_points_with_none_collection_auto_resolves_to_only_collection(self):
        """After fix: upsert_points with None collection_name should auto-resolve if only one collection exists.

        This is the DESIRED behavior after the fix.
        Currently this test will FAIL.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "index"
            project_root = Path(tmpdir)

            # Initialize store
            store = FilesystemVectorStore(base_path=base_path, project_root=project_root)

            # Create ONLY ONE collection
            store.create_collection("nomic-embed-text", vector_size=768)

            # Prepare test point
            test_point = {
                'id': 'test_point_1',
                'vector': np.random.rand(768).tolist(),
                'payload': {
                    'path': 'test.py',
                    'content': 'test content',
                    'start_line': 1,
                    'end_line': 10,
                    'language': 'python'
                }
            }

            # DESIRED FIX: When collection_name=None and only one collection exists,
            # auto-resolve to that collection
            result = store.upsert_points(
                collection_name=None,
                points=[test_point]
            )

            # Should succeed
            assert result['status'] == 'ok'
            assert result['count'] == 1

            # Verify point was actually stored
            assert store.count_points("nomic-embed-text") == 1

    def test_upsert_points_with_none_collection_raises_error_when_multiple_collections(self):
        """After fix: upsert_points with None collection_name should raise clear error if multiple collections exist.

        This test ensures we give a helpful error message when collection_name is None
        but there are multiple collections to choose from.

        Currently this test will FAIL with confusing TypeError.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "index"
            project_root = Path(tmpdir)

            # Initialize store
            store = FilesystemVectorStore(base_path=base_path, project_root=project_root)

            # Create MULTIPLE collections
            store.create_collection("collection_1", vector_size=384)
            store.create_collection("collection_2", vector_size=768)

            # Prepare test point
            test_point = {
                'id': 'test_point_1',
                'vector': np.random.rand(384).tolist(),
                'payload': {
                    'path': 'test.py',
                    'content': 'test content'
                }
            }

            # Should raise clear ValueError about ambiguous collection
            with pytest.raises(ValueError) as exc_info:
                store.upsert_points(
                    collection_name=None,
                    points=[test_point]
                )

            error_message = str(exc_info.value)
            assert "collection_name" in error_message.lower()
            assert "required" in error_message.lower() or "ambiguous" in error_message.lower()
