"""
Test for high-throughput parallel indexing engine.

This test demonstrates the throughput difference between:
1. Current approach: Sequential file processing with parallel chunks per file
2. New approach: Queue-based parallel processing with continuous worker utilization
"""

import time
from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import pytest

from ...conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from ...shared.mock_providers import MockEmbeddingProvider


class TestParallelThroughputEngine:
    """Test cases for high-throughput parallel indexing."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory with test files
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files with multiple chunks each
        self.test_files = []
        for i in range(10):  # 10 files
            file_path = self.temp_path / f"test_file_{i}.py"
            # Create content that will generate 3-4 chunks per file
            content = f"""
def function_{i}_1():
    '''First function in file {i}'''
    return "This is a longer function with enough content to create a meaningful chunk"

def function_{i}_2():
    '''Second function in file {i}'''
    return "Another function with substantial content for chunking purposes"

def function_{i}_3():
    '''Third function in file {i}'''
    return "Yet another function to ensure we have multiple chunks per file"

class TestClass_{i}:
    '''Test class with methods'''
    
    def method_1(self):
        return "Method implementation with enough content"
    
    def method_2(self):
        return "Another method implementation"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Create mock config with all required attributes
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.include_extensions = [".py"]

        # Mock nested attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 768

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200  # Small chunks for testing
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_chunk_size = 8192  # Max chunk size

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200  # Small chunks for testing
        self.config.chunking.overlap_size = 50
        self.config.chunking.max_chunk_size = 8192  # Max chunk size

        # Mock Qdrant client
        self.mock_qdrant = Mock()
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.upsert_points_batched.return_value = True

    def test_throughput_comparison_demonstrates_improvement(self):
        """Test that queue-based approach is significantly faster than sequential."""

        # Mock the VoyageAI client to avoid tokenizer loading
        mock_voyage = Mock()
        mock_client = Mock()
        mock_client.count_tokens.return_value = 100  # Return reasonable token count
        mock_voyage.Client.return_value = mock_client
        with patch("code_indexer.services.file_chunking_manager.voyageai", mock_voyage):
            # Setup providers with realistic delays
            slow_provider = MockEmbeddingProvider(delay=0.1)  # 100ms per embedding
            fast_provider = MockEmbeddingProvider(delay=0.01)  # 10ms per embedding

            # Test with slow provider first (more dramatic difference)
            sequential_time = self._measure_sequential_approach(slow_provider)
            parallel_time = self._measure_parallel_approach(
                slow_provider, thread_count=4
            )

            # Parallel should be significantly faster
            print(f"Sequential time: {sequential_time:.3f}s")
            print(f"Parallel time: {parallel_time:.3f}s")

            # Handle edge case where sequential fails completely
            if sequential_time < 0.01:  # Less than 10ms means it failed
                # Skip this test since sequential approach isn't working
                import pytest

                pytest.skip("Sequential approach failed to process files properly")

            speedup = sequential_time / parallel_time
            assert speedup > 2.0, f"Expected >2x speedup, got {speedup:.2f}x"

            # Test with fast provider (should still show improvement)
            sequential_time_fast = self._measure_sequential_approach(fast_provider)
            parallel_time_fast = self._measure_parallel_approach(
                fast_provider, thread_count=4
            )

            speedup_fast = sequential_time_fast / parallel_time_fast
            assert (
                speedup_fast > 1.5
            ), f"Expected >1.5x speedup with fast provider, got {speedup_fast:.2f}x"

    def test_worker_thread_utilization(self):
        """Test that worker threads are continuously utilized."""
        # Mock the VoyageAI client to avoid tokenizer loading
        mock_voyage = Mock()
        mock_client = Mock()
        mock_client.count_tokens.return_value = 100  # Return reasonable token count
        mock_voyage.Client.return_value = mock_client
        with patch("code_indexer.services.file_chunking_manager.voyageai", mock_voyage):
            provider = MockEmbeddingProvider(delay=0.05)

            processor = HighThroughputProcessor(
                config=self.config,
                embedding_provider=provider,
                qdrant_client=self.mock_qdrant,
            )

            start_time = time.time()

            # Start processing
            stats = processor.process_files_high_throughput(
                self.test_files,
                vector_thread_count=4,
                batch_size=10,
            )

            end_time = time.time()
            total_time = end_time - start_time

            # Verify stats
            assert stats.chunks_created > 0
            assert stats.files_processed == len(self.test_files)

            # With 4 threads and 0.05s delay, we should process much faster than sequential
            # Sequential would take: chunks_created * 0.05 seconds
            # Parallel should take roughly: chunks_created * 0.05 / 4 seconds
            expected_sequential_time = stats.chunks_created * 0.05
            expected_speedup = expected_sequential_time / total_time

            assert (
                expected_speedup > 2.0
            ), f"Poor thread utilization, speedup: {expected_speedup:.2f}x"

    def test_high_throughput_processing_success(self):
        """Test that high-throughput processing completes successfully."""
        # Mock the VoyageAI client to avoid tokenizer loading
        mock_voyage = Mock()
        mock_client = Mock()
        mock_client.count_tokens.return_value = 100  # Return reasonable token count
        mock_voyage.Client.return_value = mock_client
        with patch("code_indexer.services.file_chunking_manager.voyageai", mock_voyage):
            provider = MockEmbeddingProvider(delay=0.02)

            processor = HighThroughputProcessor(
                config=self.config,
                embedding_provider=provider,
                qdrant_client=self.mock_qdrant,
            )

            # Process files
            stats = processor.process_files_high_throughput(
                self.test_files,
                vector_thread_count=3,
                batch_size=5,
            )

            # Verify all files were processed successfully
            assert stats.files_processed == len(self.test_files)
            assert stats.chunks_created > 0
            assert stats.failed_files == 0

            # Verify Qdrant was called with batches (either standard or atomic upsert)
            assert (
                self.mock_qdrant.upsert_points.called
                or self.mock_qdrant.upsert_points_batched.called
            )

            # Check that embeddings were generated for all chunks
            total_embeddings = provider.call_count
            assert total_embeddings == stats.chunks_created

    def _measure_sequential_approach(self, provider) -> float:
        """Measure time for sequential file processing (current approach)."""
        # Simulate sequential processing with realistic timing
        # Each file gets chunked and then each chunk gets embedded sequentially

        start_time = time.time()

        # Process files sequentially
        for file_path in self.test_files:
            # Simulate chunking (3-4 chunks per file based on our test data)
            chunks_per_file = 3

            for chunk_idx in range(chunks_per_file):
                # Get embedding for each chunk sequentially
                chunk_text = f"Chunk {chunk_idx} of {file_path.name}"
                provider.get_embedding(chunk_text)

        return time.time() - start_time

    def _measure_parallel_approach(self, provider, thread_count: int) -> float:
        """Measure time for parallel queue-based processing (new approach)."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=provider,
            qdrant_client=self.mock_qdrant,
        )

        start_time = time.time()
        processor.process_files_high_throughput(
            self.test_files,
            vector_thread_count=thread_count,
            batch_size=10,
        )
        return time.time() - start_time

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
