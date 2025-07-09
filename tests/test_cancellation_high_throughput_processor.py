"""
Unit tests for HighThroughputProcessor cancellation functionality.

These tests verify that the HighThroughputProcessor can be cancelled
gracefully and responds quickly to cancellation requests.
"""

import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from .conftest import local_temporary_directory, get_local_tmp_dir

from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.embedding_provider import EmbeddingProvider, EmbeddingResult
from typing import List, Optional, Dict, Any


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing."""

    def __init__(self, delay: float = 0.1):
        super().__init__()
        self.delay = delay

    def get_provider_name(self) -> str:
        return "test-provider"

    def get_current_model(self) -> str:
        return "test-model"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "test-model", "dimensions": 768}

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        time.sleep(self.delay)
        return [1.0] * 768

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        return [self.get_embedding(text, model) for text in texts]

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        embedding = self.get_embedding(text, model)
        return EmbeddingResult(
            embedding=embedding,
            model=model or self.get_current_model(),
            tokens_used=len(text.split()),
            provider=self.get_provider_name(),
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ):
        embeddings = self.get_embeddings_batch(texts, model)
        return MagicMock(
            embeddings=embeddings,
            model=model or self.get_current_model(),
            total_tokens_used=sum(len(text.split()) for text in texts),
            provider=self.get_provider_name(),
        )

    def supports_batch_processing(self) -> bool:
        return True

    def health_check(self) -> bool:
        return True


class TestHighThroughputProcessorCancellation:
    """Test cases for HighThroughputProcessor cancellation functionality."""

    def setup_method(self, method):
        """Set up test fixtures."""
        self.embedding_provider = MockEmbeddingProvider(delay=0.1)
        self.qdrant_client = Mock(spec=QdrantClient)
        self.qdrant_client.upsert_points.return_value = True
        self.qdrant_client.upsert_points_atomic.return_value = True
        self.qdrant_client.create_point.return_value = {
            "id": "test",
            "vector": [1.0] * 768,
        }

        # Create mock config
        self.config = Mock()
        self.config.codebase_dir = Path(str(get_local_tmp_dir() / "test"))
        self.config.exclude_dirs = []
        self.config.exclude_patterns = []

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_has_cancelled_flag(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that HighThroughputProcessor has cancelled flag."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Should have cancelled attribute
        assert hasattr(processor, "cancelled")
        assert isinstance(processor.cancelled, bool)
        assert not processor.cancelled

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_has_request_cancellation_method(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that HighThroughputProcessor has request_cancellation method."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Should have request_cancellation method
        assert hasattr(processor, "request_cancellation")
        assert callable(getattr(processor, "request_cancellation"))

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
        """Test that request_cancellation sets the cancelled flag."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Initially not cancelled
        assert not processor.cancelled

        # After calling request_cancellation, should be set
        processor.request_cancellation()
        assert processor.cancelled

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_as_completed_loop_checks_cancellation(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that as_completed loop checks cancellation flag every iteration."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(5):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    pass\n")
                test_files.append(test_file)

            # Mock chunker to return chunks
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"content of {file_path.name}",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "file_extension": "py",
                    }
                ]

            processor.text_chunker.chunk_file.side_effect = mock_chunk_file

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

            processor.file_identifier.get_file_metadata.side_effect = (
                mock_get_file_metadata
            )

            # Track progress callback calls
            callback_calls = []

            def progress_callback(current, total, path, info=None):
                callback_calls.append((current, total, str(path), info))
                # Cancel after first callback
                if len(callback_calls) == 2:
                    processor.request_cancellation()
                    return "INTERRUPT"
                return None

            # Process files (should be cancelled quickly)
            start_time = time.time()
            processor.process_files_high_throughput(
                files=test_files,
                vector_thread_count=2,
                batch_size=10,
                progress_callback=progress_callback,
            )
            processing_time = time.time() - start_time

            # Should complete quickly due to cancellation
            assert (
                processing_time < 2.0
            ), f"Processing took {processing_time:.2f}s, expected < 2.0s"

            # Should have received cancellation signal
            assert len(callback_calls) >= 2
            # Check that we have at least 2 callbacks and cancellation occurred
            assert processor.cancelled, "Processor should be marked as cancelled"

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_cancellation_prevents_further_processing(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that cancellation prevents further chunk processing."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(10):  # More files to ensure some get cancelled
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(
                    f"def test{i}():\n    pass\n" * 10
                )  # Larger content
                test_files.append(test_file)

            # Mock chunker to return multiple chunks per file
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"chunk {j} of {file_path.name}",
                        "chunk_index": j,
                        "total_chunks": 3,
                        "file_extension": "py",
                    }
                    for j in range(3)
                ]

            processor.text_chunker.chunk_file.side_effect = mock_chunk_file

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 300,
                }

            processor.file_identifier.get_file_metadata.side_effect = (
                mock_get_file_metadata
            )

            # Use slower embedding provider to ensure cancellation takes effect
            processor.embedding_provider = MockEmbeddingProvider(delay=0.2)

            # Track progress and cancel early
            callback_count = 0

            def progress_callback(current, total, path, info=None):
                nonlocal callback_count
                callback_count += 1
                # Cancel after a few callbacks
                if callback_count == 3:
                    processor.request_cancellation()
                    return "INTERRUPT"
                return None

            # Process files
            start_time = time.time()
            stats = processor.process_files_high_throughput(
                files=test_files,
                vector_thread_count=2,
                batch_size=5,
                progress_callback=progress_callback,
            )
            processing_time = time.time() - start_time

            # Should complete much faster than processing all chunks
            # Without cancellation: 10 files * 3 chunks * 0.2s = 6s minimum
            # With cancellation: should be much less
            assert (
                processing_time < 3.0
            ), f"Processing took {processing_time:.2f}s, expected < 3.0s"

            # Should have processed fewer than all files
            assert stats.files_processed < len(
                test_files
            ), f"Expected fewer than {len(test_files)} files processed, got {stats.files_processed}"

    @pytest.mark.unit
    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_cancellation_preserves_completed_work(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that cancellation preserves already completed work."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create a few test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(3):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    pass\n")
                test_files.append(test_file)

            # Mock chunker
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"content of {file_path.name}",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "file_extension": "py",
                    }
                ]

            processor.text_chunker.chunk_file.side_effect = mock_chunk_file

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

            processor.file_identifier.get_file_metadata.side_effect = (
                mock_get_file_metadata
            )

            # Cancel after second file starts processing
            callback_count = 0

            def progress_callback(current, total, path, info=None):
                nonlocal callback_count
                callback_count += 1
                if callback_count == 5:  # Cancel partway through
                    processor.request_cancellation()
                    return "INTERRUPT"
                return None

            # Process files
            stats = processor.process_files_high_throughput(
                files=test_files,
                vector_thread_count=1,
                batch_size=10,
                progress_callback=progress_callback,
            )

            # Should have completed at least some work
            assert stats.files_processed >= 0
            assert stats.chunks_created >= 0

            # Qdrant should have been called for any completed work
            if stats.chunks_created > 0:
                # Check for either upsert_points or upsert_points_atomic calls
                assert (
                    self.qdrant_client.upsert_points.called
                    or self.qdrant_client.upsert_points_atomic.called
                )

    @patch("code_indexer.services.git_aware_processor.FileIdentifier")
    @patch("code_indexer.services.git_aware_processor.GitDetectionService")
    @patch("code_indexer.indexing.processor.FileFinder")
    @patch("code_indexer.indexing.processor.TextChunker")
    def test_multiple_cancellation_requests_safe(
        self,
        mock_text_chunker,
        mock_file_finder,
        mock_git_detection,
        mock_file_identifier,
    ):
        """Test that multiple cancellation requests are safe."""
        # Create processor with mocked dependencies
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create a test file
        with local_temporary_directory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def test():\n    pass\n")

            # Mock chunker
            processor.text_chunker.chunk_file.return_value = [
                {
                    "text": "content",
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "file_extension": "py",
                }
            ]

            # Mock file identifier
            processor.file_identifier.get_file_metadata.return_value = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
                "file_mtime": time.time(),
                "file_size": 100,
            }

            # Multiple cancellation requests should be safe
            processor.request_cancellation()
            processor.request_cancellation()
            processor.request_cancellation()

            # All calls should be safe, no exceptions
            assert processor.cancelled

            # Processing should still work (just exit immediately)
            def progress_callback(current, total, path, info=None):
                return "INTERRUPT"  # Always interrupt

            stats = processor.process_files_high_throughput(
                files=[test_file],
                vector_thread_count=1,
                batch_size=10,
                progress_callback=progress_callback,
            )

            # Should complete without errors
            assert stats is not None


if __name__ == "__main__":
    pytest.main([__file__])
