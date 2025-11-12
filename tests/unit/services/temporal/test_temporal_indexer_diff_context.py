"""Unit tests for TemporalIndexer diff_context_lines integration (Story #443 - AC1, AC2).

Tests that TemporalIndexer passes diff_context_lines from config to TemporalDiffScanner.
"""

from unittest.mock import Mock


from src.code_indexer.config import Config, ConfigManager, TemporalConfig
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalIndexerDiffContext:
    """Test TemporalIndexer integration with diff_context_lines config."""

    def test_temporal_indexer_passes_diff_context_to_scanner(self, tmp_path):
        """AC1, AC2: TemporalIndexer reads config and passes diff_context_lines to scanner."""
        # Create config with custom diff_context_lines
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config = Config(codebase_dir=tmp_path)
        config.temporal = TemporalConfig(diff_context_lines=15)
        config_manager.save(config)

        # Create mock vector store
        mock_vector_store = Mock(spec=FilesystemVectorStore)
        mock_vector_store.project_root = tmp_path
        mock_vector_store.base_path = tmp_path / ".code-indexer" / "index"
        mock_vector_store.collection_exists = Mock(return_value=True)

        # Create TemporalIndexer
        indexer = TemporalIndexer(config_manager, mock_vector_store)

        # Verify diff_scanner was created with correct diff_context_lines
        assert hasattr(indexer, "diff_scanner")
        assert hasattr(indexer.diff_scanner, "diff_context_lines")
        assert indexer.diff_scanner.diff_context_lines == 15
