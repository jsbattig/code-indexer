"""Unit tests for TemporalIndexer using diff-based approach."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.config import ConfigManager
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer


class TestTemporalIndexerDiffBased:
    """Test suite for diff-based temporal indexer."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager."""
        mock = Mock(spec=ConfigManager)
        mock.get_config.return_value = Mock(
            embedding_provider="voyage-ai",
            voyage_ai=Mock(parallel_requests=4, model="voyage-code-3"),
        )
        return mock

    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        mock = Mock(spec=FilesystemVectorStore)
        mock.project_root = Path("/test/project")
        mock.base_path = Path("/test/project") / ".code-indexer" / "index"
        mock.collection_exists.return_value = True
        return mock

    @patch("pathlib.Path.mkdir")
    def test_temporal_indexer_uses_diff_scanner(
        self, mock_mkdir, mock_config_manager, mock_vector_store
    ):
        """Test that TemporalIndexer uses TemporalDiffScanner, not blob scanner."""
        # This test should fail initially because temporal_indexer still imports blob_scanner
        indexer = TemporalIndexer(mock_config_manager, mock_vector_store)

        # Should have diff_scanner attribute, not blob_scanner
        assert hasattr(indexer, "diff_scanner")
        assert not hasattr(indexer, "blob_scanner")
        assert not hasattr(indexer, "blob_reader")
        assert not hasattr(indexer, "blob_registry")
