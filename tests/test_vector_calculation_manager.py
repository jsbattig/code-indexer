"""
Unit tests for VectorCalculationManager.

Tests parallel vector calculation functionality with mocked embedding providers.
"""

import time
import threading
from unittest.mock import Mock
import pytest

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    VectorResult,
    get_default_thread_count,
)
from code_indexer.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingResult,
    BatchEmbeddingResult,
)
from typing import List, Optional, Dict, Any


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing."""

    def __init__(
        self,
        provider_name: str = "test-provider",
        delay: float = 0.1,
        dimensions: int = 768,
    ):
        super().__init__()
        self.provider_name = provider_name
        self.delay = delay
        self.dimensions = dimensions
        self.call_count = 0
        self.call_lock = threading.Lock()

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_current_model(self) -> str:
        return "test-model"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "test-model", "dimensions": self.dimensions}

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Mock embedding generation with configurable delay."""
        with self.call_lock:
            self.call_count += 1

        if self.delay > 0:
            time.sleep(self.delay)

        # Generate a simple mock embedding based on text length
        return [float(len(text) % 100) / 100.0] * self.dimensions

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Mock batch embedding generation."""
        return [self.get_embedding(text, model) for text in texts]

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Mock embedding generation with metadata."""
        embedding = self.get_embedding(text, model)
        return EmbeddingResult(
            embedding=embedding,
            model=model or self.get_current_model(),
            tokens_used=len(text.split()),
            provider=self.provider_name,
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Mock batch embedding generation with metadata."""
        embeddings = self.get_embeddings_batch(texts, model)
        total_tokens = sum(len(text.split()) for text in texts)
        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model or self.get_current_model(),
            total_tokens_used=total_tokens,
            provider=self.provider_name,
        )

    def supports_batch_processing(self) -> bool:
        """Mock batch processing support."""
        return True

    def health_check(self) -> bool:
        return True


class TestVectorCalculationManager:
    """Test cases for VectorCalculationManager."""

    def test_default_thread_count_voyage_ai(self):
        """Test default thread count for VoyageAI provider."""
        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "voyage-ai"

        thread_count = get_default_thread_count(mock_provider)
        assert thread_count == 8

    def test_default_thread_count_ollama(self):
        """Test default thread count for Ollama provider."""
        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "ollama"

        thread_count = get_default_thread_count(mock_provider)
        assert thread_count == 1

    def test_default_thread_count_unknown(self):
        """Test default thread count for unknown provider."""
        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "unknown-provider"

        thread_count = get_default_thread_count(mock_provider)
        assert thread_count == 2

    def test_initialization(self):
        """Test VectorCalculationManager initialization."""
        provider = MockEmbeddingProvider()
        manager = VectorCalculationManager(provider, thread_count=4)

        assert manager.thread_count == 4
        assert manager.embedding_provider == provider
        assert not manager.is_running
        assert manager.executor is None

    def test_context_manager(self):
        """Test VectorCalculationManager as context manager."""
        provider = MockEmbeddingProvider()

        with VectorCalculationManager(provider, thread_count=2) as manager:
            assert manager.is_running
            assert manager.executor is not None

        # After exiting context, should be shut down
        assert not manager.is_running
        assert manager.executor is None

    def test_single_chunk_processing(self):
        """Test processing a single chunk."""
        provider = MockEmbeddingProvider(delay=0.01)
        test_text = "Hello, world!"
        metadata = {"file": "test.py", "chunk_index": 0}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_chunk(test_text, metadata)
            result = future.result(timeout=5.0)

            assert isinstance(result, VectorResult)
            assert result.error is None
            assert len(result.embedding) == provider.dimensions
            assert result.metadata == metadata
            assert result.processing_time > 0

    def test_parallel_chunk_processing(self):
        """Test processing multiple chunks in parallel."""
        provider = MockEmbeddingProvider(delay=0.1)
        chunks = [f"Chunk {i}" for i in range(10)]
        metadatas = [{"chunk_index": i} for i in range(10)]

        with VectorCalculationManager(provider, thread_count=4) as manager:
            start_time = time.time()

            # Submit all chunks
            futures = []
            for chunk, metadata in zip(chunks, metadatas):
                future = manager.submit_chunk(chunk, metadata)
                futures.append(future)

            # Wait for all results
            results = []
            for future in futures:
                result = future.result(timeout=10.0)
                results.append(result)

            end_time = time.time()

            # Verify all chunks processed successfully
            assert len(results) == 10
            for i, result in enumerate(results):
                assert result.error is None
                assert result.metadata["chunk_index"] == i
                assert len(result.embedding) == provider.dimensions

            # Verify parallel processing was faster than sequential
            # With 4 threads and 0.1s delay per chunk, should complete in ~0.3s
            # instead of 1.0s sequentially
            total_time = end_time - start_time
            assert total_time < 0.8  # Allow some overhead

            # Verify provider was called correct number of times
            assert provider.call_count == 10

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit some tasks
            futures = []
            for i in range(5):
                future = manager.submit_chunk(f"text {i}", {"index": i})
                futures.append(future)

            # Wait for completion
            for future in futures:
                future.result(timeout=5.0)

            # Check statistics
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 5
            assert stats.total_tasks_completed == 5
            assert stats.total_tasks_failed == 0
            assert stats.average_processing_time > 0
            assert stats.embeddings_per_second > 0
            assert stats.queue_size == 0

    def test_error_handling(self):
        """Test error handling in vector calculation."""
        provider = MockEmbeddingProvider()

        # Mock the provider to raise an exception
        def failing_get_embedding(
            text: str, model: Optional[str] = None
        ) -> List[float]:
            if "fail" in text:
                raise ValueError("Simulated embedding failure")
            return [1.0] * 768

        provider.get_embedding = failing_get_embedding  # type: ignore[method-assign]

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit a failing task
            future = manager.submit_chunk("fail this task", {"test": True})
            result = future.result(timeout=5.0)

            assert result.error is not None
            assert "Simulated embedding failure" in result.error
            assert result.embedding == []

            # Submit a successful task
            future = manager.submit_chunk("success", {"test": True})
            result = future.result(timeout=5.0)

            assert result.error is None
            assert len(result.embedding) == 768

            # Check that error statistics are tracked
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 2
            assert stats.total_tasks_completed == 2
            assert stats.total_tasks_failed == 1

    def test_thread_count_scaling(self):
        """Test performance scaling with different thread counts."""
        provider = MockEmbeddingProvider(delay=0.05)
        chunk_count = 8

        # Test with 1 thread
        with VectorCalculationManager(provider, thread_count=1) as manager:
            start_time = time.time()
            futures = []
            for i in range(chunk_count):
                future = manager.submit_chunk(f"chunk {i}", {"index": i})
                futures.append(future)

            for future in futures:
                future.result(timeout=10.0)

            single_thread_time = time.time() - start_time

        # Test with 4 threads
        provider.call_count = 0  # Reset counter
        with VectorCalculationManager(provider, thread_count=4) as manager:
            start_time = time.time()
            futures = []
            for i in range(chunk_count):
                future = manager.submit_chunk(f"chunk {i}", {"index": i})
                futures.append(future)

            for future in futures:
                future.result(timeout=10.0)

            multi_thread_time = time.time() - start_time

        # Multi-threaded should be significantly faster
        # Allow for some overhead, but expect at least 2x improvement
        speedup_ratio = single_thread_time / multi_thread_time
        assert speedup_ratio > 1.5, f"Expected speedup > 1.5x, got {speedup_ratio:.2f}x"

    def test_shutdown_with_pending_tasks(self):
        """Test shutdown behavior with pending tasks."""
        provider = MockEmbeddingProvider(delay=0.2)

        manager = VectorCalculationManager(provider, thread_count=1)
        manager.start()

        # Submit a task that will take time
        future = manager.submit_chunk("slow task", {"test": True})

        # Shutdown immediately without waiting
        manager.shutdown(wait=False)

        # The future should still complete or be cancelled
        try:
            result = future.result(timeout=1.0)
            # If it completes, it should be valid
            assert isinstance(result, VectorResult)
        except Exception:
            # If it's cancelled/times out, that's also acceptable
            pass

        assert not manager.is_running

    def test_wait_for_all_tasks(self):
        """Test waiting for all tasks to complete."""
        provider = MockEmbeddingProvider(delay=0.05)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit several tasks
            futures = []
            for i in range(6):
                future = manager.submit_chunk(f"task {i}", {"index": i})
                futures.append(future)

            # Wait for all tasks to complete
            success = manager.wait_for_all_tasks(timeout=5.0)
            assert success

            # All futures should be done
            for future in futures:
                assert future.done()

            stats = manager.get_stats()
            assert stats.queue_size == 0
            assert stats.total_tasks_completed == 6

    def test_queue_size_tracking(self):
        """Test that queue size is tracked correctly."""
        provider = MockEmbeddingProvider(delay=0.1)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit multiple tasks quickly
            futures = []
            for i in range(5):
                future = manager.submit_chunk(f"task {i}", {"index": i})
                futures.append(future)

            # Check that queue size increases
            stats = manager.get_stats()
            assert stats.queue_size > 0
            assert stats.total_tasks_submitted == 5

            # Wait for completion
            for future in futures:
                future.result(timeout=10.0)

            # Queue should be empty now
            final_stats = manager.get_stats()
            assert final_stats.queue_size == 0
            assert final_stats.total_tasks_completed == 5

    def test_task_id_uniqueness(self):
        """Test that task IDs are unique."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            futures = []
            for i in range(10):
                future = manager.submit_chunk(f"task {i}", {"index": i})
                futures.append(future)

            # Collect all task IDs
            task_ids = set()
            for future in futures:
                result = future.result(timeout=5.0)
                task_ids.add(result.task_id)

            # All task IDs should be unique
            assert len(task_ids) == 10

    def test_metadata_preservation(self):
        """Test that metadata is preserved through processing."""
        provider = MockEmbeddingProvider(delay=0.01)
        complex_metadata = {
            "file_path": "/path/to/file.py",
            "chunk_index": 42,
            "nested": {"key": "value", "list": [1, 2, 3]},
            "timestamp": "2024-01-01T00:00:00Z",
        }

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_chunk("test text", complex_metadata)
            result = future.result(timeout=5.0)

            assert result.error is None
            assert result.metadata == complex_metadata
            # Verify it's a copy, not the same object
            assert result.metadata is not complex_metadata


@pytest.fixture
def mock_voyage_provider():
    """Fixture providing a mock VoyageAI provider."""
    provider = MockEmbeddingProvider(
        provider_name="voyage-ai", delay=0.02, dimensions=1024
    )
    return provider


@pytest.fixture
def mock_ollama_provider():
    """Fixture providing a mock Ollama provider."""
    provider = MockEmbeddingProvider(provider_name="ollama", delay=0.1, dimensions=768)
    return provider


class TestProviderSpecificBehavior:
    """Test provider-specific behavior."""

    @pytest.mark.unit  # This is a unit test with mocks, not real API
    def test_voyage_ai_parallel_performance(self, mock_voyage_provider):
        """Test that VoyageAI benefits from parallelization."""
        chunk_count = 16

        with VectorCalculationManager(mock_voyage_provider, thread_count=8) as manager:
            start_time = time.time()
            futures = []
            for i in range(chunk_count):
                future = manager.submit_chunk(f"voyage chunk {i}", {"index": i})
                futures.append(future)

            results = []
            for future in futures:
                result = future.result(timeout=10.0)
                results.append(result)

            total_time = time.time() - start_time

            # Verify all processed successfully
            assert len(results) == chunk_count
            assert all(result.error is None for result in results)
            assert all(len(result.embedding) == 1024 for result in results)

            # Should be much faster than sequential processing
            # Expected: ~0.04s with 8 threads vs ~0.32s sequential
            assert total_time < 0.2

    def test_ollama_single_thread_default(self, mock_ollama_provider):
        """Test that Ollama defaults to single thread."""
        default_threads = get_default_thread_count(mock_ollama_provider)
        assert default_threads == 1

        with VectorCalculationManager(mock_ollama_provider, thread_count=1) as manager:
            futures = []
            for i in range(3):
                future = manager.submit_chunk(f"ollama chunk {i}", {"index": i})
                futures.append(future)

            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)

            # Verify all processed successfully
            assert len(results) == 3
            assert all(result.error is None for result in results)
            assert all(len(result.embedding) == 768 for result in results)

    @pytest.mark.unit  # This is a unit test with mocks, not real API
    def test_mixed_chunk_sizes(self, mock_voyage_provider):
        """Test processing chunks of different sizes."""
        chunks = [
            "short",
            "medium length text chunk",
            "very long text chunk that contains much more content and should take similar time to process",
            "",  # empty chunk
            "special chars: áéíóú 中文 🚀",
        ]

        with VectorCalculationManager(mock_voyage_provider, thread_count=4) as manager:
            futures = []
            for i, chunk in enumerate(chunks):
                future = manager.submit_chunk(chunk, {"index": i, "length": len(chunk)})
                futures.append(future)

            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)

            # All should process successfully
            assert len(results) == len(chunks)
            for i, result in enumerate(results):
                assert result.error is None
                assert result.metadata["index"] == i
                assert result.metadata["length"] == len(chunks[i])
                assert len(result.embedding) == 1024


if __name__ == "__main__":
    pytest.main([__file__])
