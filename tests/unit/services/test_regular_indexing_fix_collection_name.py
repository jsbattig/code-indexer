"""
Test to verify the fix for regular indexing with temporal collection.

This test verifies that the collection_name is correctly passed through
when regular indexing happens and multiple collections exist.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock
import json

from src.code_indexer.services.file_chunking_manager import FileChunkingManager
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.config import ConfigManager


class TestRegularIndexingFixCollectionName:
    """Test that the collection_name fix works correctly."""

    def test_collection_name_is_added_to_metadata(self):
        """
        Test that collection_name is added to metadata when submitting files.

        This verifies the fix that adds collection_name to file metadata
        so that FilesystemVectorStore.upsert_points() works when multiple
        collections exist.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_repo = Path(tmpdir) / "test_repo"
            test_repo.mkdir(parents=True)

            # Create test files
            src_dir = test_repo / "src"
            src_dir.mkdir()

            test_file = src_dir / "test.py"
            test_file.write_text("def hello():\n    print('Hello, World!')\n")

            # Create .code-indexer directory structure
            index_dir = test_repo / ".code-indexer/index"
            index_dir.mkdir(parents=True)

            # Create temporal collection (simulating Story 1)
            temporal_collection_dir = index_dir / "code-indexer-temporal"
            temporal_collection_dir.mkdir(parents=True)

            temporal_meta = {
                "collection_name": "code-indexer-temporal",
                "vector_count": 26,
                "embedding_provider": "voyage",
                "embedding_model": "voyage-code-3",
                "embedding_dimensions": 1536,
            }

            with open(temporal_collection_dir / "collection_meta.json", "w") as f:
                json.dump(temporal_meta, f)

            # Create default collection
            default_collection_dir = index_dir / "voyage-code-3"
            default_collection_dir.mkdir(parents=True)

            default_meta = {
                "collection_name": "voyage-code-3",
                "vector_count": 0,
                "embedding_provider": "voyage",
                "embedding_model": "voyage-code-3",
                "embedding_dimensions": 1536,
            }

            with open(default_collection_dir / "collection_meta.json", "w") as f:
                json.dump(default_meta, f)

            # Create projection matrix for the default collection
            import numpy as np

            projection_matrix = np.random.randn(1536, 64).astype(np.float32)
            np.save(default_collection_dir / "projection_matrix.npy", projection_matrix)

            # Setup config
            config_path = test_repo / ".code-indexer/config.json"
            config_path.parent.mkdir(exist_ok=True)
            config_data = {
                "project_id": "test_project",
                "embedding_provider": "voyage",
                "embedding_model": "voyage-code-3",
                "voyage": {"api_key": "test_key", "batch_size": 128},
            }
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            # Test the fix with collection_name in metadata
            ConfigManager.create_with_backtrack(test_repo)
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=test_repo
            )

            # Create test chunk
            test_chunk = {
                "text": "def hello():\n    print('Hello, World!')\n",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
                "line_start": 1,
                "line_end": 2,
            }

            # Create metadata WITH collection_name (the fix)
            metadata = {
                "project_id": "test_project",
                "file_hash": "abc123",
                "git_available": False,
                "file_mtime": 1234567890,
                "file_size": 100,
                "collection_name": "voyage-code-3",  # THE FIX: collection_name is now included
            }

            # Create a mock embedding
            embedding = [0.1] * 1536

            # Create FileChunkingManager
            mock_vector_manager = Mock()
            mock_chunker = Mock()
            mock_slot_tracker = Mock()

            file_chunking_mgr = FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                vector_store_client=vector_store,
                thread_count=4,
                slot_tracker=mock_slot_tracker,
                codebase_dir=test_repo,
            )

            # Create the Filesystem point
            filesystem_point = file_chunking_mgr._create_filesystem_point(
                test_chunk, embedding, metadata, test_file
            )

            # WITH THE FIX: upsert_points should work now
            result = vector_store.upsert_points(
                points=[filesystem_point],
                collection_name=metadata.get(
                    "collection_name"
                ),  # This now returns "voyage-code-3"
            )

            # Check that it succeeded (returns dict with status)
            assert result is not None
            assert isinstance(result, dict)
            assert result.get("status") == "ok"
            assert result.get("count") == 1

            # Verify the point was actually written
            collection_path = default_collection_dir

            # Check that at least one vector file was created
            vector_files = list(collection_path.glob("**/*.json"))
            # Filter out collection_meta.json
            vector_files = [f for f in vector_files if f.name != "collection_meta.json"]

            assert len(vector_files) > 0, "Vector file should be created"
