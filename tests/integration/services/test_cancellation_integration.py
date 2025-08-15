"""
Integration test for cancellation functionality that actually creates instances.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from ...conftest import get_local_tmp_dir
from code_indexer.services.high_throughput_processor import HighThroughputProcessor


class TestCancellationIntegration:
    """Integration test cases for cancellation functionality."""

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_cancellation_flag_in_instance(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that an instance of HighThroughputProcessor has cancelled flag."""
        # Create mock config
        config = Mock()
        config.codebase_dir = Path(str(get_local_tmp_dir() / "test"))

        # Create mock providers
        embedding_provider = Mock()
        qdrant_client = Mock()

        # Create processor instance
        processor = HighThroughputProcessor(
            config=config,
            embedding_provider=embedding_provider,
            qdrant_client=qdrant_client,
        )

        # Should have cancelled attribute set to False initially
        assert hasattr(processor, "cancelled")
        assert not processor.cancelled

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_request_cancellation_sets_flag(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that request_cancellation sets the cancelled flag to True."""
        # Create mock config
        config = Mock()
        config.codebase_dir = Path(str(get_local_tmp_dir() / "test"))

        # Create mock providers
        embedding_provider = Mock()
        qdrant_client = Mock()

        # Create processor instance
        processor = HighThroughputProcessor(
            config=config,
            embedding_provider=embedding_provider,
            qdrant_client=qdrant_client,
        )

        # Initially not cancelled
        assert not processor.cancelled

        # After calling request_cancellation, should be True
        processor.request_cancellation()
        assert processor.cancelled


if __name__ == "__main__":
    pytest.main([__file__])
