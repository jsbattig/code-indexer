"""
Test case to reproduce P0 regression where regular indexing fails when temporal collection exists.

REGRESSION BUG:
- After Story 1 created "code-indexer-temporal" collection, regular indexing fails
- Error: "collection_name is required when multiple collections exist"
- Root cause: Regular indexing doesn't specify collection_name parameter
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock
import pytest
import json

from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.config import ConfigManager


class TestRegularIndexingWithTemporalCollection:
    """Test that regular indexing works when temporal collection exists."""

    def test_regular_indexing_works_when_temporal_collection_exists(self):
        """
        REGRESSION TEST: Regular indexing should work even when temporal collection exists.

        This test reproduces the P0 bug where regular indexing fails with:
        "collection_name is required when multiple collections exist.
        Available collections: code-indexer-temporal, voyage-code-3"
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

            # SIMULATE STORY 1: Create temporal collection (this is what causes the bug)
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

            # SIMULATE OLD COLLECTION: Create voyage-code-3 collection (might exist from before)
            old_collection_dir = index_dir / "voyage-code-3"
            old_collection_dir.mkdir(parents=True)

            old_meta = {
                "collection_name": "voyage-code-3",
                "vector_count": 100,
                "embedding_provider": "voyage",
                "embedding_model": "voyage-code-3",
                "embedding_dimensions": 1536,
            }

            with open(old_collection_dir / "collection_meta.json", "w") as f:
                json.dump(old_meta, f)

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

            # Test the actual code path - using FileChunkingManager inside HighThroughputProcessor
            # Set up mocks for the actual flow
            ConfigManager.create_with_backtrack(test_repo)
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=test_repo
            )

            # Create a simple test chunk
            test_chunk = {
                "text": "def hello():\n    print('Hello, World!')\n",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
                "line_start": 1,
                "line_end": 2,
            }

            # Create metadata without collection_name (this is the bug)
            metadata = {
                "project_id": "test_project",
                "file_hash": "abc123",
                "git_available": False,
                "file_mtime": 1234567890,
                "file_size": 100,
            }

            # Create a mock embedding
            embedding = [0.1] * 1536

            # Create a mock filesystem point
            from src.code_indexer.services.file_chunking_manager import (
                FileChunkingManager,
            )

            # Mock dependencies
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

            # Create the Filesystem point as the manager would
            filesystem_point = file_chunking_mgr._create_filesystem_point(
                test_chunk, embedding, metadata, test_file
            )

            # THIS IS THE BUG: When upsert_points is called without collection_name
            # it will fail because multiple collections exist
            with pytest.raises(ValueError) as exc_info:
                vector_store.upsert_points(
                    points=[filesystem_point],
                    collection_name=metadata.get(
                        "collection_name"
                    ),  # This returns None - the bug!
                )

            # Verify the exact error message we expect
            assert "collection_name is required when multiple collections exist" in str(
                exc_info.value
            )
            assert "code-indexer-temporal" in str(exc_info.value)
            assert "voyage-code-3" in str(exc_info.value)
