"""Test that temporal indexer uses parallel processing in index_commits."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer


class TestTemporalIndexerUsesParallel(unittest.TestCase):
    """Test that index_commits uses the parallel processing method."""

    def test_index_commits_calls_parallel_processing(self):
        """Test that index_commits method calls _process_commits_parallel."""
        # Setup
        test_dir = Path("/tmp/test-repo")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 8
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info, \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.create") as mock_create, \
             patch("src.code_indexer.services.vector_calculation_manager.VectorCalculationManager") as mock_vector_manager_class:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "model_info": {"dimension": 1536}
            }

            # Mock embedding provider
            mock_embedding_provider = Mock()
            mock_create.return_value = mock_embedding_provider

            # Mock vector manager
            mock_vector_manager = MagicMock()
            # Mock cancellation event (no cancellation)
            mock_cancellation_event = MagicMock()
            mock_cancellation_event.is_set.return_value = False
            mock_vector_manager.cancellation_event = mock_cancellation_event
            mock_vector_manager.__enter__ = Mock(return_value=mock_vector_manager)
            mock_vector_manager.__exit__ = Mock(return_value=None)
            mock_vector_manager_class.return_value = mock_vector_manager

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Mock the parallel processing method
            # Returns: (commits_processed, files_processed, vectors_created)
            indexer._process_commits_parallel = Mock(return_value=(10, 15, 20))

            # Mock commit history
            with patch.object(indexer, '_get_commit_history') as mock_history:
                mock_history.return_value = [
                    Mock(hash="commit1", timestamp=1000, message="Test commit 1"),
                    Mock(hash="commit2", timestamp=2000, message="Test commit 2")
                ]

                # Call index_commits
                result = indexer.index_commits(all_branches=False)

                # Verify _process_commits_parallel was called
                indexer._process_commits_parallel.assert_called_once()

                # Verify it was called with the right arguments
                call_args = indexer._process_commits_parallel.call_args
                self.assertEqual(len(call_args[0][0]), 2)  # 2 commits
                self.assertEqual(call_args[0][1], mock_embedding_provider)  # embedding provider
                self.assertIsNotNone(call_args[0][2])  # vector manager passed


if __name__ == "__main__":
    unittest.main()