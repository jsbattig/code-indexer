"""
Unit tests for VectorCalculationManager.

Tests parallel vector calculation functionality with mocked embedding providers.
"""

import time
import threading
from unittest.mock import Mock
import pytest
from concurrent.futures import Future

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    VectorResult,
    VectorTask,
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
        fail_on_batch: bool = False,
        batch_delay_multiplier: float = 1.0,
    ):
        super().__init__()
        self.provider_name = provider_name
        self.delay = delay
        self.dimensions = dimensions
        self.fail_on_batch = fail_on_batch
        self.batch_delay_multiplier = batch_delay_multiplier
        self.call_count = 0
        self.batch_call_count = 0
        self.call_lock = threading.Lock()
        self.batch_calls_log: List[List[str]] = []  # Track actual batch calls

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_current_model(self) -> str:
        return "voyage-3"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "voyage-3", "dimensions": self.dimensions}

    def _get_model_token_limit(self) -> int:
        """Get token limit for current model."""
        return 120000

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
        """Mock batch embedding generation with tracking."""
        with self.call_lock:
            self.batch_call_count += 1
            # Log the actual batch call for verification
            self.batch_calls_log.append(list(texts))

        if self.fail_on_batch:
            raise ValueError("Mock batch processing failure")

        if self.delay > 0:
            time.sleep(self.delay * self.batch_delay_multiplier)

        # Generate embeddings for all texts in batch
        embeddings = []
        for text in texts:
            # Generate a simple mock embedding based on text length
            embeddings.append([float(len(text) % 100) / 100.0] * self.dimensions)

        return embeddings

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

    def _submit_batch_task(
        self,
        manager: VectorCalculationManager,
        chunk_texts: List[str],
        metadata: Dict[str, Any],
    ) -> "Future[VectorResult]":
        """Helper method to submit a batch task directly to test batch processing."""
        # Create a VectorTask with multiple chunks
        task = VectorTask(
            task_id=f"batch_task_{time.time()}",
            chunk_texts=tuple(chunk_texts),
            metadata=metadata,
            created_at=time.time(),
        )

        # Submit directly to the thread pool
        if not manager.executor:
            raise RuntimeError("Thread pool not started")
        future = manager.executor.submit(manager._calculate_vector, task)

        # Update stats for submitted batch task
        with manager.stats_lock:
            manager.stats.total_tasks_submitted += 1

        return future  # type: ignore[no-any-return]

    def test_config_json_thread_count_simplified(self):
        """Test that thread count now comes from config.json only."""
        # With radical simplification, thread count is always from config.json
        # No more complex resolution hierarchy - just use config.voyage_ai.parallel_requests
        mock_config = Mock()
        mock_config.voyage_ai = Mock()
        mock_config.voyage_ai.parallel_requests = 12

        assert (
            mock_config.voyage_ai.parallel_requests == 12
        ), "Config.json setting should be used directly"

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
            future: Future[Any] = manager.submit_chunk(test_text, metadata)
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
                future: Future[Any] = manager.submit_chunk(chunk, metadata)
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

            # Verify provider batch API was called correct number of times (now uses batch processing for single chunks)
            assert provider.batch_call_count == 10  # 10 batch calls with 1 chunk each
            assert provider.call_count == 0  # No single embedding calls should be made

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit some tasks
            futures = []
            for i in range(5):
                future: Future[Any] = manager.submit_chunk(f"text {i}", {"index": i})
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

        # Mock the provider to raise an exception on batch calls (now uses batch processing)
        def failing_get_embeddings_batch(
            texts: List[str], model: Optional[str] = None
        ) -> List[List[float]]:
            for text in texts:
                if "fail" in text:
                    raise ValueError("Simulated embedding failure")
            return [[1.0] * 768 for _ in texts]

        provider.get_embeddings_batch = failing_get_embeddings_batch  # type: ignore[method-assign]

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit a failing task
            fail_future: Future[Any] = manager.submit_chunk(
                "fail this task", {"test": True}
            )
            result = fail_future.result(timeout=5.0)

            assert result.error is not None
            assert "Simulated embedding failure" in result.error
            assert result.embedding == []

            # Submit a successful task
            success_future: Future[Any] = manager.submit_chunk(
                "success", {"test": True}
            )
            result = success_future.result(timeout=5.0)

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
                single_future = manager.submit_chunk(f"chunk {i}", {"index": i})
                futures.append(single_future)

            for future in futures:
                future.result(timeout=10.0)

            single_thread_time = time.time() - start_time

        # Test with 4 threads
        provider.call_count = 0  # Reset counter
        with VectorCalculationManager(provider, thread_count=4) as manager:
            start_time = time.time()
            futures = []
            for i in range(chunk_count):
                multi_future = manager.submit_chunk(f"chunk {i}", {"index": i})
                futures.append(multi_future)

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
        future: Future[Any] = manager.submit_chunk("slow task", {"test": True})

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
                future: Future[Any] = manager.submit_chunk(f"task {i}", {"index": i})
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
                future: Future[Any] = manager.submit_chunk(f"task {i}", {"index": i})
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
                future: Future[Any] = manager.submit_chunk(f"task {i}", {"index": i})
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
            future: Future[Any] = manager.submit_chunk("test text", complex_metadata)
            result = future.result(timeout=5.0)

            assert result.error is None
            assert result.metadata == complex_metadata
            # Verify it's a copy, not the same object
            assert result.metadata is not complex_metadata

    # ========== BATCH PROCESSING TESTS ==========

    def test_batch_processing_multiple_chunks(self):
        """Test batch processing with multiple chunks via get_embeddings_batch()."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts = ["First chunk", "Second chunk", "Third chunk"]
        metadata = {"batch_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit batch task
            future = self._submit_batch_task(manager, chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify batch processing occurred
            assert result.error is None
            assert result.batch_size == 3
            assert len(result.embeddings) == 3
            assert result.metadata == metadata

            # Verify batch API was called exactly once
            assert provider.batch_call_count == 1
            assert provider.call_count == 0  # Single embedding API should not be called

            # Verify the batch call received correct texts
            assert len(provider.batch_calls_log) == 1
            assert provider.batch_calls_log[0] == chunk_texts

            # Verify each embedding has correct dimensions
            for embedding in result.embeddings:
                assert len(embedding) == provider.dimensions

    def test_batch_processing_single_chunk_compatibility(self):
        """Test that batch processing works with single chunk (backward compatibility)."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts = ["Single chunk text"]
        metadata = {"single_chunk": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit single-chunk batch task
            future = self._submit_batch_task(manager, chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify processing succeeded
            assert result.error is None
            assert result.batch_size == 1
            assert len(result.embeddings) == 1
            assert result.metadata == metadata

            # Verify batch API was used even for single chunk
            assert provider.batch_call_count == 1
            assert provider.call_count == 0

            # Verify backward compatibility properties
            assert result.embedding == list(result.embeddings[0])

    def test_batch_processing_error_handling(self):
        """Test error handling for batch operations with retry patterns."""
        provider = MockEmbeddingProvider(delay=0.01, fail_on_batch=True)
        chunk_texts = ["Chunk 1", "Chunk 2", "Chunk 3"]
        metadata = {"error_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit batch task that will fail
            future = self._submit_batch_task(manager, chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify error handling
            assert result.error is not None
            assert "Mock batch processing failure" in result.error
            assert result.batch_size == 0  # Empty on error
            assert len(result.embeddings) == 0

            # Verify batch API was called
            assert provider.batch_call_count == 1

            # Verify stats tracking for failed batch
            stats = manager.get_stats()
            assert stats.total_tasks_failed == 1

    def test_batch_processing_statistics_tracking(self):
        """Test statistics tracking accurately reflects batch operations."""
        provider = MockEmbeddingProvider(delay=0.02)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit multiple batch tasks with different sizes
            futures = []
            batch_configs = [
                (["A", "B", "C"], {"batch": 1}),
                (["D", "E"], {"batch": 2}),
                (["F"], {"batch": 3}),
                (["G", "H", "I", "J"], {"batch": 4}),
            ]

            for chunk_texts, metadata in batch_configs:
                future = self._submit_batch_task(manager, chunk_texts, metadata)
                futures.append(future)

            # Wait for all batches to complete
            results = []
            for future in futures:
                result = future.result(timeout=10.0)
                results.append(result)

            # Verify all batches processed successfully
            assert len(results) == 4
            for result in results:
                assert result.error is None

            # Verify batch API calls
            assert provider.batch_call_count == 4  # 4 batch API calls
            assert provider.call_count == 0  # No single embedding calls

            # Verify statistics accuracy
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 4  # 4 batch tasks submitted
            assert stats.total_tasks_completed == 4  # 4 batch tasks completed
            assert stats.total_tasks_failed == 0
            assert stats.embeddings_per_second > 0

            # Verify individual results match batch sizes
            assert results[0].batch_size == 3  # First batch: 3 chunks
            assert results[1].batch_size == 2  # Second batch: 2 chunks
            assert results[2].batch_size == 1  # Third batch: 1 chunk
            assert results[3].batch_size == 4  # Fourth batch: 4 chunks

    def test_batch_processing_cancellation_handling(self):
        """Test cancellation handling for batch operations."""
        provider = MockEmbeddingProvider(
            delay=0.05
        )  # Shorter delay for more reliable cancellation
        chunk_texts = ["Chunk 1", "Chunk 2", "Chunk 3"]
        metadata = {"cancellation_test": True}

        manager = VectorCalculationManager(provider, thread_count=1)
        manager.start()

        try:
            # Request cancellation before submitting task
            manager.request_cancellation()

            # Submit batch task after cancellation is requested
            future = self._submit_batch_task(manager, chunk_texts, metadata)

            # Wait for result
            result = future.result(timeout=5.0)

            # Verify cancellation was handled
            assert result.error is not None
            assert "Cancelled" in result.error
            assert result.batch_size == 0
            assert len(result.embeddings) == 0
        finally:
            manager.shutdown()

    def test_batch_processing_empty_chunks(self):
        """Test batch processing with empty chunk list."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts: List[str] = []  # Empty chunk list
        metadata = {"empty_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit batch task with empty chunks
            future = self._submit_batch_task(manager, chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Should complete successfully with empty results
            assert result.error is None
            assert result.batch_size == 0
            assert len(result.embeddings) == 0

            # CRITICAL FIX: Empty batches should NOT call the API (optimization)
            # Old behavior: Made unnecessary API call with empty list
            # New behavior: Return early without API call for better performance
            assert provider.batch_call_count == 0, "Empty batches should not call API"
            assert len(provider.batch_calls_log) == 0, "No API calls should be logged"

    def test_batch_processing_performance_improvement(self):
        """Test that batch processing provides performance improvements."""
        # Configure provider with batch efficiency
        provider = MockEmbeddingProvider(
            delay=0.05,  # Base delay per chunk
            batch_delay_multiplier=0.3,  # Batch processing is much more efficient
        )

        chunk_count = 10
        chunks_per_batch = 5

        with VectorCalculationManager(provider, thread_count=2) as manager:
            start_time = time.time()

            # Submit two batch tasks
            futures = []
            for batch_idx in range(2):
                batch_chunks = [
                    f"Batch {batch_idx} chunk {i}" for i in range(chunks_per_batch)
                ]
                future = self._submit_batch_task(
                    manager, batch_chunks, {"batch": batch_idx}
                )
                futures.append(future)

            # Wait for completion
            results = []
            for future in futures:
                result = future.result(timeout=10.0)
                results.append(result)

            total_time = time.time() - start_time

            # Verify all processed successfully
            assert len(results) == 2
            for result in results:
                assert result.error is None
                assert result.batch_size == chunks_per_batch

            # Verify performance improvement
            # With batch processing: 2 API calls * (0.05 * 0.3) = ~0.03s
            # Without batch: would be 10 API calls * 0.05 = 0.5s
            assert total_time < 0.2  # Should be much faster than individual processing

            # Verify batch API usage
            assert (
                provider.batch_call_count == 2
            )  # Only 2 batch calls for 10 embeddings
            assert provider.call_count == 0  # No individual calls

    def test_batch_processing_large_batch_handling(self):
        """Test batch processing with large batches."""
        provider = MockEmbeddingProvider(delay=0.01)
        # Create a larger batch to test system handling
        chunk_texts = [f"Large batch chunk {i:03d}" for i in range(50)]
        metadata = {"large_batch": True, "chunk_count": 50}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit large batch task
            future = self._submit_batch_task(manager, chunk_texts, metadata)
            result = future.result(timeout=10.0)

            # Verify large batch processing
            assert result.error is None
            assert result.batch_size == 50
            assert len(result.embeddings) == 50

            # Verify batch API was called once for entire batch
            assert provider.batch_call_count == 1
            assert len(provider.batch_calls_log[0]) == 50

            # Verify all embeddings are correct
            for i, embedding in enumerate(result.embeddings):
                assert len(embedding) == provider.dimensions

    # ========== NEW submit_batch_task() API TESTS ==========

    def test_submit_batch_task_basic_functionality(self):
        """Test submit_batch_task() method basic functionality."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts = ["First chunk", "Second chunk", "Third chunk"]
        metadata = {"batch_api_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Use new public API method
            future = manager.submit_batch_task(chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify batch processing occurred
            assert result.error is None
            assert result.batch_size == 3
            assert len(result.embeddings) == 3
            assert result.metadata == metadata
            assert result.processing_time > 0

            # Verify task ID is generated correctly
            assert result.task_id.startswith("task_")

            # Verify batch API was called exactly once
            assert provider.batch_call_count == 1
            assert provider.call_count == 0

    def test_submit_batch_task_empty_chunks(self):
        """Test submit_batch_task() with empty chunk list."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts: List[str] = []
        metadata = {"empty_batch_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_batch_task(chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Should complete successfully with empty results
            assert result.error is None
            assert result.batch_size == 0
            assert len(result.embeddings) == 0
            assert result.metadata == metadata

            # Empty batches should not call API
            assert provider.batch_call_count == 0

    def test_submit_batch_task_single_chunk(self):
        """Test submit_batch_task() with single chunk."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts = ["Single chunk text"]
        metadata = {"single_chunk_batch": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_batch_task(chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify processing succeeded
            assert result.error is None
            assert result.batch_size == 1
            assert len(result.embeddings) == 1
            assert result.metadata == metadata

            # Verify batch API was used
            assert provider.batch_call_count == 1
            assert provider.call_count == 0

            # Verify backward compatibility properties
            assert result.embedding == list(result.embeddings[0])

    def test_submit_batch_task_manager_not_started(self):
        """Test submit_batch_task() when manager is not started."""
        provider = MockEmbeddingProvider(delay=0.01)
        manager = VectorCalculationManager(provider, thread_count=1)
        # Manager not started yet
        assert not manager.is_running

        chunk_texts = ["Test chunk"]
        metadata = {"auto_start_test": True}

        # Should auto-start the manager
        future = manager.submit_batch_task(chunk_texts, metadata)
        result = future.result(timeout=5.0)

        # Verify it worked and manager was started
        assert manager.is_running
        assert result.error is None
        assert result.batch_size == 1

        manager.shutdown()

    def test_submit_batch_task_cancelled_manager(self):
        """Test submit_batch_task() when manager is cancelled."""
        provider = MockEmbeddingProvider(delay=0.01)
        manager = VectorCalculationManager(provider, thread_count=1)
        manager.start()
        manager.request_cancellation()

        chunk_texts = ["Test chunk"]
        metadata = {"cancelled_test": True}

        # Should return cancelled result immediately
        future = manager.submit_batch_task(chunk_texts, metadata)
        result = future.result(timeout=5.0)

        assert result.error == "Cancelled"
        assert result.batch_size == 0
        assert len(result.embeddings) == 0
        assert result.task_id == "cancelled"

        manager.shutdown()

    def test_submit_batch_task_error_handling(self):
        """Test submit_batch_task() error handling."""
        provider = MockEmbeddingProvider(delay=0.01, fail_on_batch=True)
        chunk_texts = ["Chunk 1", "Chunk 2"]
        metadata = {"error_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_batch_task(chunk_texts, metadata)
            result = future.result(timeout=5.0)

            # Verify error handling
            assert result.error is not None
            assert "Mock batch processing failure" in result.error
            assert result.batch_size == 0
            assert len(result.embeddings) == 0

    def test_submit_batch_task_statistics_tracking(self):
        """Test that submit_batch_task() updates statistics correctly."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit multiple batch tasks
            futures = []
            batch_configs = [
                (["A", "B"], {"batch": 1}),
                (["C", "D", "E"], {"batch": 2}),
                (["F"], {"batch": 3}),
            ]

            for chunk_texts, metadata in batch_configs:
                future = manager.submit_batch_task(chunk_texts, metadata)
                futures.append(future)

            # Wait for completion
            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)

            # Verify statistics
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 3  # 3 batch tasks
            assert stats.total_tasks_completed == 3
            assert stats.total_tasks_failed == 0
            assert stats.total_embeddings_processed == 6  # 2 + 3 + 1 embeddings

    def test_submit_batch_task_metadata_immutability(self):
        """Test that submit_batch_task() creates immutable copies of metadata."""
        provider = MockEmbeddingProvider(delay=0.01)
        chunk_texts = ["Test chunk"]
        original_metadata: Dict[str, Any] = {
            "mutable": ["list", "data"],
            "dict": {"key": "value"},
        }

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_batch_task(chunk_texts, original_metadata)
            result = future.result(timeout=5.0)

            # Modify original metadata
            original_metadata["new_key"] = "new_value"
            original_metadata["mutable"].append("new_item")
            original_metadata["dict"]["new_dict_key"] = "new_dict_value"

            # Result metadata should not be affected
            assert "new_key" not in result.metadata
            assert "new_item" not in result.metadata["mutable"]
            assert "new_dict_key" not in result.metadata["dict"]

    def test_submit_batch_task_chunk_texts_immutability(self):
        """Test that submit_batch_task() creates immutable copies of chunk_texts."""
        provider = MockEmbeddingProvider(delay=0.01)
        original_chunks = ["Original chunk 1", "Original chunk 2"]
        metadata = {"immutability_test": True}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_batch_task(original_chunks, metadata)

            # Modify original chunks list
            original_chunks.append("New chunk added after submit")
            original_chunks[0] = "Modified first chunk"

            result = future.result(timeout=5.0)

            # Verify the task was processed with original data
            assert result.error is None
            assert result.batch_size == 2  # Not affected by append

            # Check that provider received original data
            assert len(provider.batch_calls_log) == 1
            assert provider.batch_calls_log[0] == [
                "Original chunk 1",
                "Original chunk 2",
            ]

    def test_submit_batch_task_invalid_inputs(self):
        """Test submit_batch_task() with invalid inputs."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Test with None chunk_texts - should raise TypeError
            with pytest.raises(TypeError):
                manager.submit_batch_task(None, {"test": True})

            # Test with None metadata - should raise TypeError when deep copying
            with pytest.raises(TypeError):
                manager.submit_batch_task(["test"], None)

    def test_submit_batch_task_thread_safety(self):
        """Test submit_batch_task() thread safety with concurrent submissions."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=4) as manager:
            import threading
            import queue

            results_queue: queue.Queue = queue.Queue()

            def submit_batch(thread_id):
                chunk_texts = [f"Thread {thread_id} chunk {i}" for i in range(3)]
                metadata = {"thread_id": thread_id}
                future = manager.submit_batch_task(chunk_texts, metadata)
                result = future.result(timeout=10.0)
                results_queue.put(result)

            # Submit from multiple threads simultaneously
            threads = []
            for i in range(5):
                thread = threading.Thread(target=submit_batch, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join()

            # Collect all results
            results = []
            while not results_queue.empty():
                results.append(results_queue.get())

            # Verify all submissions succeeded
            assert len(results) == 5
            for result in results:
                assert result.error is None
                assert result.batch_size == 3

            # Verify statistics
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 5
            assert stats.total_tasks_completed == 5
            assert stats.total_embeddings_processed == 15


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
                future: Future[Any] = manager.submit_chunk(
                    f"voyage chunk {i}", {"index": i}
                )
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

    def test_ollama_single_thread_from_config(self, mock_ollama_provider):
        """Test that Ollama uses config.json setting."""
        # With radical simplification, Ollama also uses config.voyage_ai.parallel_requests
        # No more provider-specific defaults - everything from config.json
        mock_config = Mock()
        mock_config.voyage_ai = Mock()
        mock_config.voyage_ai.parallel_requests = 1  # Config setting for Ollama

        assert mock_config.voyage_ai.parallel_requests == 1

        with VectorCalculationManager(mock_ollama_provider, thread_count=1) as manager:
            futures = []
            for i in range(3):
                future: Future[Any] = manager.submit_chunk(
                    f"ollama chunk {i}", {"index": i}
                )
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
                future: Future[Any] = manager.submit_chunk(
                    chunk, {"index": i, "length": len(chunk)}
                )
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
