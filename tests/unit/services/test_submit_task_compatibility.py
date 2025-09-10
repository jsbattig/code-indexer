"""
Tests for submit_task() compatibility layer in VectorCalculationManager.

Tests that submit_task() wraps single chunks for batch processing while preserving
identical behavior to the original implementation.
"""

import time
import threading
import pytest
from concurrent.futures import Future

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    VectorResult,
)
from typing import List, Optional, Dict, Any


class MockEmbeddingProvider:
    """Mock embedding provider for testing submit_task compatibility."""

    def __init__(
        self,
        provider_name: str = "test-provider",
        delay: float = 0.01,
        dimensions: int = 768,
        fail_on_batch: bool = False,
    ):
        self.provider_name = provider_name
        self.delay = delay
        self.dimensions = dimensions
        self.fail_on_batch = fail_on_batch
        self.call_count = 0
        self.batch_call_count = 0
        self.call_lock = threading.Lock()
        self.batch_calls_log: List[List[str]] = []

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_current_model(self) -> str:
        return "test-model"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "test-model", "dimensions": self.dimensions}

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Mock embedding generation - should NOT be called by submit_task()."""
        with self.call_lock:
            self.call_count += 1
        if self.delay > 0:
            time.sleep(self.delay)
        return [float(len(text) % 100) / 100.0] * self.dimensions

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Mock batch embedding generation - should be called by submit_task()."""
        with self.call_lock:
            self.batch_call_count += 1
            self.batch_calls_log.append(list(texts))

        if self.fail_on_batch:
            raise ValueError("Mock batch processing failure")

        if self.delay > 0:
            time.sleep(self.delay)

        # Generate embeddings for all texts in batch
        embeddings = []
        for text in texts:
            embeddings.append([float(len(text) % 100) / 100.0] * self.dimensions)
        return embeddings

    def supports_batch_processing(self) -> bool:
        return True

    def health_check(self) -> bool:
        return True


class TestSubmitTaskCompatibility:
    """Test cases for submit_task() compatibility layer."""

    def test_submit_task_method_exists(self):
        """Test that submit_task() method exists and has correct signature."""
        provider = MockEmbeddingProvider()
        manager = VectorCalculationManager(provider, thread_count=1)

        # Should have submit_task method
        assert hasattr(manager, "submit_task")

        # Should be callable
        assert callable(getattr(manager, "submit_task"))

    def test_submit_task_preserves_identical_behavior(self):
        """Test that submit_task() preserves identical behavior using batch processing internally."""
        provider = MockEmbeddingProvider(delay=0.01)
        test_text = "Hello, world!"
        metadata = {"file": "test.py", "chunk_index": 0}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task(test_text, metadata)
            result = future.result(timeout=5.0)

            # Verify behavior identical to submit_chunk
            assert isinstance(result, VectorResult)
            assert result.error is None
            assert len(result.embedding) == provider.dimensions
            assert isinstance(result.embedding, list)  # Must be List[float], not tuple
            assert result.metadata == metadata
            assert result.processing_time > 0

            # Verify internally uses batch processing
            assert provider.batch_call_count == 1
            assert provider.call_count == 0  # Should NOT use single embedding API
            assert len(provider.batch_calls_log) == 1
            assert provider.batch_calls_log[0] == [test_text]

    def test_submit_task_future_interface_preservation(self):
        """Test that Future interface and behavior are preserved."""
        provider = MockEmbeddingProvider(delay=0.05)
        test_text = "Test future interface"
        metadata = {"test": "future"}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task(test_text, metadata)

            # Future should be returned immediately
            assert isinstance(future, Future)
            assert not future.done()  # Should not be done immediately

            # Future.result() should work
            result = future.result(timeout=5.0)
            assert future.done()
            assert isinstance(result, VectorResult)
            assert result.error is None

            # Future should support cancellation (though may not succeed)
            new_future = manager.submit_task("cancellation test", {"test": True})
            cancel_result = (
                new_future.cancel()
            )  # May return True or False depending on timing
            assert isinstance(cancel_result, bool)

    def test_submit_task_error_handling_preservation(self):
        """Test that error handling produces same error types and messages as before."""
        provider = MockEmbeddingProvider(fail_on_batch=True)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task("fail this task", {"test": True})
            result = future.result(timeout=5.0)

            # Should handle errors identically
            assert result.error is not None
            assert "Mock batch processing failure" in result.error
            assert result.embedding == []
            assert isinstance(result.embedding, list)

    def test_submit_task_statistics_preservation(self):
        """Test that statistics tracking accounts for single-task submissions correctly."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Submit multiple tasks
            futures = []
            for i in range(3):
                future = manager.submit_task(f"task {i}", {"index": i})
                futures.append(future)

            # Wait for completion
            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)

            # Check statistics
            stats = manager.get_stats()
            assert (
                stats.total_tasks_submitted == 3
            )  # Each submit_task() counts as 1 task
            assert stats.total_tasks_completed == 3
            assert stats.total_tasks_failed == 0
            assert (
                stats.total_embeddings_processed == 3
            )  # Each task generates 1 embedding

    def test_submit_task_thread_pool_integration_unchanged(self):
        """Test that thread pool integration and resource management are unchanged."""
        provider = MockEmbeddingProvider(delay=0.02)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit multiple tasks concurrently
            futures = []
            for i in range(6):
                future = manager.submit_task(f"concurrent task {i}", {"index": i})
                futures.append(future)

            # All futures should be separate objects
            assert len(set(id(f) for f in futures)) == 6

            # Each should resolve independently
            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)
                assert result.error is None

            # Thread pool should handle concurrency properly
            stats = manager.get_stats()
            assert stats.total_tasks_submitted == 6
            assert stats.total_tasks_completed == 6

    def test_submit_task_cancellation_behavior(self):
        """Test that cancellation behavior works identically for single tasks."""
        provider = MockEmbeddingProvider(delay=0.05)

        manager = VectorCalculationManager(provider, thread_count=1)
        manager.start()

        try:
            # Request cancellation
            manager.request_cancellation()

            # Submit task after cancellation
            future = manager.submit_task("cancelled task", {"test": True})
            result = future.result(timeout=5.0)

            # Should handle cancellation identically
            assert result.error is not None
            assert "Cancelled" in result.error
            assert result.embedding == []
        finally:
            manager.shutdown()

    def test_submit_task_metadata_immutability(self):
        """Test that submit_task() creates immutable copies of metadata."""
        provider = MockEmbeddingProvider(delay=0.01)
        original_metadata = {"mutable": ["list", "data"], "dict": {"key": "value"}}

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task("test text", original_metadata)
            result = future.result(timeout=5.0)

            # Modify original metadata
            original_metadata["new_key"] = "new_value"
            original_metadata["mutable"].append("new_item")
            original_metadata["dict"]["new_dict_key"] = "new_dict_value"

            # Result metadata should not be affected
            assert "new_key" not in result.metadata
            assert "new_item" not in result.metadata["mutable"]
            assert "new_dict_key" not in result.metadata["dict"]

    def test_submit_task_single_embedding_extraction(self):
        """Test that single embedding is extracted correctly from batch response."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task("test embedding extraction", {"test": True})
            result = future.result(timeout=5.0)

            # Should extract single embedding from batch result
            assert result.error is None
            assert isinstance(result.embedding, list)
            assert len(result.embedding) == provider.dimensions

            # Verify it's the single embedding, not array of arrays
            assert all(isinstance(x, float) for x in result.embedding)

            # Verify batch API was called with single chunk
            assert provider.batch_call_count == 1
            assert provider.batch_calls_log[0] == ["test embedding extraction"]

    def test_submit_task_performance_maintained(self):
        """Test that performance is maintained or improved for single task submissions."""
        provider = MockEmbeddingProvider(delay=0.02)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Measure submit_task performance
            start_time = time.time()
            futures = []
            for i in range(4):
                future = manager.submit_task(f"perf test {i}", {"index": i})
                futures.append(future)

            results = []
            for future in futures:
                result = future.result(timeout=5.0)
                results.append(result)

            total_time = time.time() - start_time

            # Should complete efficiently with parallel processing
            assert len(results) == 4
            assert all(r.error is None for r in results)
            # With 2 threads and 0.02s delay, should complete faster than 2 * 0.02 * 2 = 0.08s
            assert total_time < 0.1

    def test_submit_task_task_id_uniqueness(self):
        """Test that task IDs remain unique across submit_task() calls."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            futures = []
            for i in range(5):
                future = manager.submit_task(f"unique id test {i}", {"index": i})
                futures.append(future)

            # Collect all task IDs
            task_ids = set()
            for future in futures:
                result = future.result(timeout=5.0)
                task_ids.add(result.task_id)

            # All task IDs should be unique
            assert len(task_ids) == 5

    def test_submit_task_empty_text_handling(self):
        """Test that submit_task() handles empty text correctly."""
        provider = MockEmbeddingProvider(delay=0.01)

        with VectorCalculationManager(provider, thread_count=1) as manager:
            future = manager.submit_task("", {"empty_text": True})
            result = future.result(timeout=5.0)

            # Should handle empty text without error
            assert result.error is None
            assert isinstance(result.embedding, list)
            assert len(result.embedding) == provider.dimensions

            # Should still use batch API
            assert provider.batch_call_count == 1
            assert provider.batch_calls_log[0] == [""]


if __name__ == "__main__":
    pytest.main([__file__])
