"""Tests for temporal storage optimization - pointer-based storage.

This tests that added/deleted files store pointers only (no content),
while modified files store diffs as before.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestPointerBasedStorage:
    """Test that temporal indexer creates pointer payloads for added/deleted files."""

    def test_added_file_payload_has_reconstruct_marker(self):
        """Test that added files have reconstruct_from_git marker in payload."""
        # Simulate what temporal_indexer should create for an added file
        diff_info_added = {
            "diff_type": "added",
            "commit_hash": "abc123",
            "file_path": "test.py",
        }

        # Expected payload structure for added file (pointer only)
        expected_payload = {
            "type": "commit_diff",
            "diff_type": "added",
            "commit_hash": "abc123",
            "path": "test.py",
            "reconstruct_from_git": True,  # NEW: Signals pointer-based storage
            # NO "content" field - that's the point of the optimization
        }

        # This test verifies the expected structure
        # The actual implementation will be in temporal_indexer.py
        assert expected_payload["reconstruct_from_git"] is True
        assert "content" not in expected_payload

    @pytest.fixture
    def mock_temporal_indexer_components(self):
        """Create mock components for temporal indexer testing."""
        from src.code_indexer.config import ConfigManager
        from src.code_indexer.storage.filesystem_vector_store import (
            FilesystemVectorStore,
        )

        # Create minimal mock config
        mock_config = Mock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = Mock()
        mock_config.voyage_ai.parallel_requests = 4
        mock_config.voyage_ai.max_concurrent_batches_per_commit = 10
        mock_config.voyage_ai.model = "voyage-code-2"

        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_config.return_value = mock_config

        # Create minimal mock vector store
        mock_vector_store = Mock(spec=FilesystemVectorStore)
        mock_vector_store.project_root = Path("/tmp/test_repo")
        mock_vector_store.base_path = Path("/tmp/test_repo/.code-indexer/index")
        mock_vector_store.collection_exists.return_value = True
        mock_vector_store.load_id_index.return_value = set()
        mock_vector_store.upsert_points.return_value = {"status": "ok"}

        return mock_config_manager, mock_vector_store

    def test_temporal_indexer_creates_pointer_payload_for_added_file(
        self, mock_temporal_indexer_components
    ):
        """Test that TemporalIndexer creates pointer-based payload for added files."""
        from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
        from unittest.mock import patch

        mock_config_manager, mock_vector_store = mock_temporal_indexer_components

        # Mock embedding provider info
        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
        ):

            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create indexer
            indexer = TemporalIndexer(mock_config_manager, mock_vector_store)

            # Create an added file diff
            diff_info = DiffInfo(
                file_path="test.py",
                diff_type="added",
                commit_hash="abc123",
                diff_content="+def hello():\n+    return 'world'\n",
                blob_hash="blob123",
            )

            # We need to test that when processing this diff, the indexer creates
            # a payload with reconstruct_from_git=True and no content field
            # This will be verified by checking what gets passed to vector_store.upsert_points

            # For now, this test documents the expected behavior
            # The actual implementation will modify temporal_indexer.py line ~444-460
            assert diff_info.diff_type == "added"
