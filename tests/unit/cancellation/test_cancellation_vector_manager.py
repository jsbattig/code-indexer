"""
Unit tests for VectorCalculationManager cancellation functionality.

These tests verify that the VectorCalculationManager can be cancelled
gracefully and responds quickly to cancellation requests.
"""

import time
import threading
import pytest

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
)
from code_indexer.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingResult,
    BatchEmbeddingResult,
)
from typing import List, Optional, Dict, Any


class SlowMockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider with configurable delays for testing cancellation."""

    def __init__(self, delay: float = 0.5):
        super().__init__()
        self.delay = delay
        self.call_count = 0
        self.call_lock = threading.Lock()

    def get_provider_name(self) -> str:
        return "slow-test-provider"

    def get_current_model(self) -> str:
        return "slow-test-model"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "slow-test-model", "dimensions": 768}

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Mock embedding generation with configurable delay."""
        with self.call_lock:
            self.call_count += 1

        # Simulate slow embedding calculation
        time.sleep(self.delay)
        return [1.0] * 768

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
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
            provider=self.get_provider_name(),
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
            provider=self.get_provider_name(),
        )

    def supports_batch_processing(self) -> bool:
        return True

    def health_check(self) -> bool:
        return True


class TestVectorCalculationManagerCancellation:
    """Test cases for VectorCalculationManager cancellation functionality."""

    def test_has_cancellation_event(self):
        """Test that VectorCalculationManager has cancellation event."""
        provider = SlowMockEmbeddingProvider()
        manager = VectorCalculationManager(provider, thread_count=2)

        # Should have cancellation_event attribute
        assert hasattr(manager, "cancellation_event")
        assert isinstance(manager.cancellation_event, threading.Event)
        assert not manager.cancellation_event.is_set()

    def test_has_request_cancellation_method(self):
        """Test that VectorCalculationManager has request_cancellation method."""
        provider = SlowMockEmbeddingProvider()
        manager = VectorCalculationManager(provider, thread_count=2)

        # Should have request_cancellation method
        assert hasattr(manager, "request_cancellation")
        assert callable(getattr(manager, "request_cancellation"))

    def test_request_cancellation_sets_event(self):
        """Test that request_cancellation sets the cancellation event."""
        provider = SlowMockEmbeddingProvider()
        manager = VectorCalculationManager(provider, thread_count=2)

        # Initially not set
        assert not manager.cancellation_event.is_set()

        # After calling request_cancellation, should be set
        manager.request_cancellation()
        assert manager.cancellation_event.is_set()

    def test_worker_checks_cancellation_flag(self):
        """Test that worker threads check cancellation flag before processing."""
        provider = SlowMockEmbeddingProvider(
            delay=0.5
        )  # Longer delay to ensure cancellation happens first

        with VectorCalculationManager(provider, thread_count=1) as manager:
            # Request cancellation first
            manager.request_cancellation()

            # Submit a task after cancellation is requested
            future = manager.submit_chunk("test text", {"test": True})

            # Get result (should be cancelled)
            result = future.result(timeout=5.0)

            # Should have error indicating cancellation
            assert result.error is not None
            assert (
                "cancelled" in result.error.lower()
                or "canceled" in result.error.lower()
            )

    def test_cancellation_response_time(self):
        """Test that cancellation responds within reasonable time."""
        provider = SlowMockEmbeddingProvider(delay=2.0)  # Very slow tasks

        with VectorCalculationManager(provider, thread_count=4) as manager:
            # Submit many slow tasks
            futures = []
            for i in range(20):
                future = manager.submit_chunk(f"slow task {i}", {"index": i})
                futures.append(future)

            # Wait a bit for tasks to start
            time.sleep(0.1)

            # Request cancellation and measure response time
            start_cancel = time.time()
            manager.request_cancellation()

            # Wait for all futures to complete (they should complete quickly due to cancellation)
            completed_count = 0
            for future in futures:
                try:
                    future.result(timeout=3.0)
                    completed_count += 1
                except Exception:
                    # Timeout is acceptable for cancelled tasks
                    pass

            cancel_response_time = time.time() - start_cancel

            # Should respond to cancellation within 3 seconds
            # (much faster than the 40+ seconds it would take without cancellation)
            assert (
                cancel_response_time < 3.0
            ), f"Cancellation took {cancel_response_time:.2f}s, expected < 3.0s"

    def test_no_new_tasks_after_cancellation(self):
        """Test that no new tasks are processed after cancellation."""
        provider = SlowMockEmbeddingProvider(delay=0.1)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit first batch of tasks
            futures_batch1 = []
            for i in range(3):
                future = manager.submit_chunk(
                    f"batch1 task {i}", {"batch": 1, "index": i}
                )
                futures_batch1.append(future)

            # Request cancellation
            manager.request_cancellation()

            # Submit second batch of tasks (should be rejected or cancelled)
            futures_batch2 = []
            for i in range(3):
                future = manager.submit_chunk(
                    f"batch2 task {i}", {"batch": 2, "index": i}
                )
                futures_batch2.append(future)

            # Check results
            batch2_successful = 0
            for future in futures_batch2:
                try:
                    result = future.result(timeout=2.0)
                    if result.error is None:
                        batch2_successful += 1
                except Exception:
                    # Timeout/cancellation is expected
                    pass

            # Most or all batch2 tasks should be cancelled
            assert (
                batch2_successful <= 1
            ), f"Expected most batch2 tasks cancelled, but {batch2_successful} succeeded"

    @pytest.mark.unit
    def test_cancellation_preserves_completed_results(self):
        """Test that cancellation doesn't affect already completed results."""
        provider = SlowMockEmbeddingProvider(delay=0.05)  # Fast tasks

        with VectorCalculationManager(provider, thread_count=4) as manager:
            # Submit and let some tasks complete
            futures = []
            for i in range(5):
                future = manager.submit_chunk(f"fast task {i}", {"index": i})
                futures.append(future)

            # Wait for first few to complete
            time.sleep(0.2)

            # Request cancellation
            manager.request_cancellation()

            # Check results - early tasks should have completed successfully
            completed_successfully = 0
            for future in futures:
                try:
                    result = future.result(timeout=1.0)
                    if result.error is None:
                        completed_successfully += 1
                except Exception:
                    pass

            # At least some tasks should have completed successfully before cancellation
            assert (
                completed_successfully >= 2
            ), f"Expected some tasks to complete before cancellation, got {completed_successfully}"

    def test_cancellation_cleans_up_resources(self):
        """Test that cancellation properly cleans up resources."""
        provider = SlowMockEmbeddingProvider(delay=0.2)

        manager = VectorCalculationManager(provider, thread_count=4)
        manager.start()

        # Submit tasks
        futures = []
        for i in range(10):
            future = manager.submit_chunk(f"cleanup test {i}", {"index": i})
            futures.append(future)

        # Request cancellation
        manager.request_cancellation()

        # Shutdown should complete quickly
        start_shutdown = time.time()
        manager.shutdown(wait=True, timeout=5.0)
        shutdown_time = time.time() - start_shutdown

        # Shutdown should be fast even with pending tasks
        assert (
            shutdown_time < 3.0
        ), f"Shutdown took {shutdown_time:.2f}s, expected < 3.0s"
        assert not manager.is_running

    def test_multiple_cancellation_requests_safe(self):
        """Test that multiple cancellation requests are safe."""
        provider = SlowMockEmbeddingProvider(delay=0.1)

        with VectorCalculationManager(provider, thread_count=2) as manager:
            # Submit tasks
            futures = []
            for i in range(5):
                future = manager.submit_chunk(f"multi cancel test {i}", {"index": i})
                futures.append(future)

            # Request cancellation multiple times (should be safe)
            manager.request_cancellation()
            manager.request_cancellation()
            manager.request_cancellation()

            # All calls should be safe, no exceptions
            assert manager.cancellation_event.is_set()


if __name__ == "__main__":
    pytest.main([__file__])
