"""Test parallel processing architecture for temporal indexer.

This test verifies the queue-based parallel processing with ThreadPoolExecutor
as required by Story 1 acceptance criteria.
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer


class TestTemporalIndexerParallelProcessing(unittest.TestCase):
    """Test parallel processing architecture for temporal indexer."""

    def test_parallel_processing_method_exists(self):
        """Test that the parallel processing method exists and is called."""
        # Setup
        test_dir = Path("/tmp/test-repo")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 8
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"  # Required for initialization
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "model_info": {"dimension": 1536}
            }

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # The indexer should have a method for parallel processing
            self.assertTrue(
                hasattr(indexer, '_process_commits_parallel'),
                "TemporalIndexer should have _process_commits_parallel method"
            )


    def test_parallel_processing_uses_queue(self):
        """Test that the parallel processing method uses Queue."""
        from queue import Queue, Empty

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
        vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info, \
             patch("src.code_indexer.services.temporal.temporal_indexer.Queue") as mock_queue_class:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "model_info": {"dimension": 1536}
            }

            # Create a mock queue instance that simulates empty after 10 items
            mock_queue = Mock(spec=Queue)
            mock_queue.put = Mock()

            # Make get_nowait raise Empty after being called 10 times
            commits_to_return = [Mock(hash=f"commit{i}") for i in range(10)]
            mock_queue.get_nowait = Mock(side_effect=commits_to_return + [Empty()])
            mock_queue.task_done = Mock()

            mock_queue_class.return_value = mock_queue

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Mock the diff scanner to avoid subprocess calls
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Call the method with test data
            commits = [Mock(hash=f"commit{i}") for i in range(10)]
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=Mock()
            )

            # Verify Queue was created
            mock_queue_class.assert_called_once()

            # Verify commits were added to queue
            self.assertEqual(mock_queue.put.call_count, 10)

    def test_parallel_processing_uses_threadpool(self):
        """Test that the parallel processing method uses ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor

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
        vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner") as mock_diff_scanner, \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info, \
             patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "model_info": {"dimension": 1536}
            }

            # Mock diff scanner
            mock_diff_scanner.return_value.get_diffs_for_commit.return_value = []

            # Create a mock executor
            mock_executor = Mock(spec=ThreadPoolExecutor)
            mock_executor.__enter__ = Mock(return_value=mock_executor)
            mock_executor.__exit__ = Mock(return_value=None)
            mock_executor_class.return_value = mock_executor

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Mock the diff scanner to avoid subprocess calls
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Call the method with test data
            commits = [Mock(hash=f"commit{i}") for i in range(10)]
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=Mock()
            )

            # Verify ThreadPoolExecutor was created
            mock_executor_class.assert_called_once()

    def test_parallel_processing_worker_function(self):
        """Test that the parallel processing uses worker functions."""

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
        vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner") as mock_diff_scanner_class, \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "model_info": {"dimension": 1536}
            }

            # Mock diff scanner to return test diffs
            mock_diff_scanner = Mock()
            mock_diff_scanner.get_diffs_for_commit.return_value = [
                Mock(
                    file_path="test.py",
                    diff_content="test diff",
                    diff_type="modified"
                )
            ]

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Replace the diff_scanner with our mock
            indexer.diff_scanner = mock_diff_scanner

            # Create test commits
            commits = [
                Mock(hash=f"commit{i}", timestamp=1000+i, message=f"Message {i}")
                for i in range(3)
            ]

            # Call the method
            result = indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=Mock()
            )

            # Verify diff scanner was called for each commit
            self.assertEqual(mock_diff_scanner.get_diffs_for_commit.call_count, 3)


if __name__ == "__main__":
    unittest.main()