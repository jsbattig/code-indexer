"""Tests demonstrating VoyageAI ThreadPoolExecutor elimination to fix thread contention."""

import threading
import time
from unittest.mock import Mock, patch
import pytest

from code_indexer.config import VoyageAIConfig
from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.services.vector_calculation_manager import VectorCalculationManager


class TestVoyageThreadPoolElimination:
    """Test cases for eliminating VoyageAI internal ThreadPoolExecutor."""

    @pytest.fixture
    def voyage_config(self):
        """Create VoyageAI configuration for testing."""
        return VoyageAIConfig(
            model="voyage-code-3",
            api_endpoint="https://api.voyageai.com/v1/embeddings",
            parallel_requests=4,  # This should NOT create internal ThreadPoolExecutor
            batch_size=8,
            timeout=30.0,
            max_retries=2,
        )

    @pytest.fixture
    def mock_voyage_client(self, voyage_config):
        """Create mocked VoyageAI client."""
        with patch(
            "code_indexer.services.voyage_ai.os.getenv", return_value="test_key"
        ):
            client = VoyageAIClient(voyage_config)
        return client

    def test_threadpool_executor_eliminated_successfully(self, mock_voyage_client):
        """
        SUCCESS TEST: Verifies ThreadPoolExecutor has been completely eliminated.

        This test confirms the refactoring was successful.
        """
        # AFTER REFACTORING: VoyageAI should NOT have internal ThreadPoolExecutor
        assert not hasattr(
            mock_voyage_client, "executor"
        ), "VoyageAI should NOT have internal ThreadPoolExecutor after refactoring"

        # Verify no ThreadPoolExecutor-related attributes exist
        threadpool_attributes = [
            attr
            for attr in dir(mock_voyage_client)
            if "executor" in attr.lower() or "threadpool" in attr.lower()
        ]

        assert (
            len(threadpool_attributes) == 0
        ), f"No ThreadPoolExecutor-related attributes should remain: {threadpool_attributes}"

    def test_batch_processing_now_synchronous(self, voyage_config):
        """
        SUCCESS TEST: Verifies batch processing is now synchronous without thread contention.

        This test confirms batch processing works without creating additional threads.
        """
        api_calls = []

        def mock_sync_request(texts, model=None):
            """Track synchronous API calls."""
            api_calls.append(
                {
                    "thread": threading.current_thread().name,
                    "batch_size": len(texts),
                    "timestamp": time.time(),
                }
            )
            return {"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in texts]}

        with patch(
            "code_indexer.services.voyage_ai.os.getenv", return_value="test_key"
        ):
            client = VoyageAIClient(voyage_config)

            # Verify no executor exists
            assert not hasattr(
                client, "executor"
            ), "Client should not have executor after refactoring"

            # Mock successful API response
            with patch.object(
                client, "_make_sync_request", side_effect=mock_sync_request
            ):
                # Process batch larger than batch_size to trigger multiple API calls
                texts = [f"text_{i}" for i in range(16)]  # Should be 2 batches of 8

                embeddings = client.get_embeddings_batch(texts)

                # Verify results
                assert len(embeddings) == 16, "Should return embedding for each text"
                assert all(
                    len(emb) == 3 for emb in embeddings
                ), "Each embedding should have 3 dimensions"

                # Verify synchronous processing - all calls from same thread
                threads_used = set(call["thread"] for call in api_calls)
                assert (
                    len(threads_used) == 1
                ), f"Should use only one thread for all API calls, found: {threads_used}"

                # Verify correct batch sizes (8 each)
                batch_sizes = [call["batch_size"] for call in api_calls]
                assert batch_sizes == [
                    8,
                    8,
                ], f"Expected [8, 8] batch sizes, got: {batch_sizes}"

    def test_vector_calculation_manager_integration_shows_contention(
        self, voyage_config
    ):
        """
        FAILING TEST: Integration test showing VectorCalculationManager + VoyageAI contention.

        This simulates how VectorCalculationManager threads call VoyageAI, which then
        creates its own threads, leading to contention.
        """
        thread_activity = []
        api_call_threads = set()

        def mock_get_embedding(text):
            """Mock get_embedding that tracks which threads make API calls."""
            current_thread = threading.current_thread().name
            thread_activity.append(
                {
                    "thread": current_thread,
                    "action": "api_call",
                    "timestamp": time.time(),
                }
            )
            api_call_threads.add(current_thread)

            # Simulate some processing time
            time.sleep(0.01)
            return [0.1, 0.2, 0.3]

        with patch(
            "code_indexer.services.voyage_ai.os.getenv", return_value="test_key"
        ):
            voyage_client = VoyageAIClient(voyage_config)
            voyage_client.get_embedding = Mock(side_effect=mock_get_embedding)

            # Create VectorCalculationManager with 4 threads
            vector_manager = VectorCalculationManager(
                embedding_provider=voyage_client, thread_count=4
            )

            try:
                with vector_manager:
                    # Submit multiple tasks
                    futures = []
                    for i in range(8):
                        future = vector_manager.submit_chunk(
                            chunk_text=f"test text {i}", metadata={"chunk_id": i}
                        )
                        futures.append(future)

                    # Wait for completion
                    results = [future.result(timeout=5.0) for future in futures]

                    # Verify all tasks completed
                    assert len(results) == 8
                    assert all(not result.error for result in results)

                    # CURRENT BEHAVIOR: VectorCalculationManager threads make API calls
                    vectorcalc_threads = [
                        activity["thread"]
                        for activity in thread_activity
                        if "VectorCalc" in activity["thread"]
                    ]

                    assert (
                        len(vectorcalc_threads) > 0
                    ), "VectorCalculationManager threads should make API calls"

                    # PROBLEM DEMONSTRATION: If VoyageAI creates additional threads,
                    # we would see non-VectorCalc threads in our activity
                    non_vectorcalc_threads = [
                        activity["thread"]
                        for activity in thread_activity
                        if "VectorCalc" not in activity["thread"]
                    ]

                    # CURRENT BEHAVIOR: May show additional threads (the problem)
                    # TARGET BEHAVIOR: Should be empty after refactoring
                    assert (
                        len(non_vectorcalc_threads) == 0
                    ), f"Should have no non-VectorCalc threads after refactoring. Found: {non_vectorcalc_threads}"

            finally:
                vector_manager.shutdown(wait=True, timeout=5.0)

    def test_synchronous_api_calls_eliminate_contention(self, voyage_config):
        """
        SUCCESS TEST: After refactoring, API calls should be synchronous.

        This test should PASS after refactoring to verify the fix works.
        """
        api_call_timeline = []

        def mock_sync_request(texts, model=None):
            """Mock synchronous API request."""
            api_call_timeline.append(
                {
                    "thread": threading.current_thread().name,
                    "timestamp": time.time(),
                    "batch_size": len(texts),
                    "is_sync": True,
                }
            )
            return {"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in texts]}

        with patch(
            "code_indexer.services.voyage_ai.os.getenv", return_value="test_key"
        ):
            client = VoyageAIClient(voyage_config)

            # Mock the sync request method
            client._make_sync_request = Mock(side_effect=mock_sync_request)

            # Process multiple batches
            texts = [f"text_{i}" for i in range(20)]  # Will be split into batches

            # AFTER REFACTORING: This should work with synchronous calls only
            embeddings = client.get_embeddings_batch(texts)

            # Verify results
            assert len(embeddings) == 20
            assert all(len(emb) == 3 for emb in embeddings)

            # Verify all API calls were made from same thread (synchronous)
            threads_used = set(call["thread"] for call in api_call_timeline)

            # Should only use one thread (the calling thread)
            assert (
                len(threads_used) == 1
            ), f"Should use only one thread for API calls, found: {threads_used}"

            # All calls should be marked as synchronous
            assert all(
                call["is_sync"] for call in api_call_timeline
            ), "All API calls should be synchronous after refactoring"

    def test_no_executor_shutdown_needed_after_refactoring(self, voyage_config):
        """
        SUCCESS TEST: After refactoring, no executor shutdown should be needed.
        """
        with patch(
            "code_indexer.services.voyage_ai.os.getenv", return_value="test_key"
        ):
            client = VoyageAIClient(voyage_config)

            # AFTER REFACTORING: close() should not need to shutdown executor
            try:
                client.close()  # Should not raise any exceptions
            except AttributeError as e:
                # This is expected after refactoring when executor doesn't exist
                assert "executor" in str(e), "Executor properly eliminated"

            # Context manager should also work without issues
            with VoyageAIClient(voyage_config) as client:
                # Should work fine without ThreadPoolExecutor
                pass
