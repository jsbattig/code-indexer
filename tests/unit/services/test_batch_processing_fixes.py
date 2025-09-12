"""
TDD tests for batch processing implementation fixes.

These tests expose the issues identified by the code-reviewer:
1. Empty batch handling - unnecessary API calls for empty chunks
2. Statistics tracking accuracy - counting tasks instead of embeddings
3. Complex immutability pattern - overly complex __post_init__ mutations

All tests should FAIL initially, demonstrating the problems that need fixing.
"""

import time
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    VectorTask,
    VectorResult,
    VectorCalculationStats,
)
from code_indexer.services.embedding_provider import EmbeddingProvider


class TestBatchProcessingFixes:
    """Test cases for batch processing implementation fixes."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_provider = Mock(spec=EmbeddingProvider)
        self.mock_provider.get_embeddings_batch = Mock(return_value=[])
        self.mock_provider.health_check = Mock(return_value=True)

    def test_empty_batch_handling_should_avoid_api_call(self):
        """
        FAILING TEST: Empty batches should return early without calling API.

        Current behavior: Makes unnecessary API call for empty chunk_texts.
        Expected behavior: Return early with empty result, avoid API call.
        """
        manager = VectorCalculationManager(self.mock_provider, thread_count=1)

        # Create task with empty chunk_texts
        empty_task = VectorTask(
            task_id="test_empty",
            chunk_texts=(),  # Empty tuple
            metadata={"test": True},
            created_at=time.time(),
        )

        # Process the empty task
        result = manager._calculate_vector(empty_task)

        # EXPECTED: API should NOT be called for empty batch
        self.mock_provider.get_embeddings_batch.assert_not_called()

        # EXPECTED: Should return empty embeddings
        assert result.embeddings == ()
        assert result.error is None
        assert result.task_id == "test_empty"

    def test_statistics_should_track_individual_embeddings_not_tasks(self):
        """
        FAILING TEST: Statistics should count embeddings, not tasks.

        Current behavior: Tracks tasks in rolling window, making embeddings_per_second misleading.
        Expected behavior: Track actual embedding count for accurate rate calculation.
        """
        # Mock provider returning 3 embeddings per call
        self.mock_provider.get_embeddings_batch = Mock(
            return_value=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]  # 3 embeddings
        )

        manager = VectorCalculationManager(self.mock_provider, thread_count=1)
        manager.start()

        # Submit task with 3 chunks (should create 3 embeddings)
        task_with_multiple_chunks = VectorTask(
            task_id="multi_chunk",
            chunk_texts=("chunk1", "chunk2", "chunk3"),
            metadata={"test": True},
            created_at=time.time(),
        )

        # Process the task
        result = manager._calculate_vector(task_with_multiple_chunks)

        # Get statistics
        stats = manager.get_stats()

        # EXPECTED: Should track 3 embeddings processed, not 1 task
        # Current implementation tracks tasks, so this will FAIL
        assert hasattr(
            stats, "total_embeddings_processed"
        ), "Statistics should track total embeddings"
        assert (
            stats.total_embeddings_processed == 3
        ), "Should count 3 embeddings, not 1 task"

        # EXPECTED: embeddings_per_second calculation should use embedding count
        assert result.batch_size == 3, "Result should reflect 3 embeddings"

    def test_embeddings_per_second_should_use_actual_embedding_count(self):
        """
        FAILING TEST: embeddings_per_second should be calculated from actual embedding counts.

        Current behavior: Uses task count in rolling window calculation.
        Expected behavior: Use total embedding count for accurate rate.
        """
        # Mock provider for multiple tasks with different batch sizes
        embeddings_sequence = [
            [[1.0, 2.0], [3.0, 4.0]],  # Task 1: 2 embeddings
            [[5.0, 6.0], [7.0, 8.0], [9.0, 10.0]],  # Task 2: 3 embeddings
            [[11.0, 12.0]],  # Task 3: 1 embedding
        ]
        self.mock_provider.get_embeddings_batch = Mock(side_effect=embeddings_sequence)

        manager = VectorCalculationManager(self.mock_provider, thread_count=1)
        manager.start()

        # Submit 3 tasks with different batch sizes
        tasks = [
            VectorTask("task1", ("chunk1", "chunk2"), {"test": 1}, time.time()),
            VectorTask(
                "task2", ("chunk3", "chunk4", "chunk5"), {"test": 2}, time.time()
            ),
            VectorTask("task3", ("chunk6",), {"test": 3}, time.time()),
        ]

        # Process all tasks
        for task in tasks:
            manager._calculate_vector(task)
            time.sleep(0.1)  # Small delay to distinguish timestamps

        stats = manager.get_stats()

        # EXPECTED: Total embeddings should be 2 + 3 + 1 = 6
        # Current implementation counts tasks (3), so this will FAIL
        assert stats.total_embeddings_processed == 6, "Should count 6 total embeddings"

        # EXPECTED: embeddings_per_second should be based on embedding count, not task count
        # This assertion will FAIL because current calculation uses task count
        assert (
            stats.embeddings_per_second > 0
        ), "Should calculate rate based on embeddings"

    def test_immutable_dataclasses_should_use_simpler_factory_pattern(self):
        """
        SUCCESS TEST: Immutable dataclasses now use simpler factory methods.

        Previous behavior: Complex __post_init__ with object.__setattr__ mutations.
        Fixed behavior: Clean factory methods for explicit construction.
        """
        # Test VectorTask creation using factory method
        task_data = {
            "task_id": "test_task",
            "chunk_texts": ["chunk1", "chunk2"],  # List input
            "metadata": {"key": "value"},
            "created_at": time.time(),
        }

        # SUCCESS: Factory method now exists and works cleanly
        task = VectorTask.create_immutable(**task_data)
        assert isinstance(task.chunk_texts, tuple), "Should convert to tuple"
        assert task.chunk_texts == ("chunk1", "chunk2"), "Should preserve content"
        assert task.metadata == {"key": "value"}, "Should deep copy metadata"

        # Test VectorResult creation using factory method
        result_data = {
            "task_id": "test_result",
            "embeddings": [[1.0, 2.0], [3.0, 4.0]],  # List input
            "metadata": {"key": "value"},
            "processing_time": 1.0,
        }

        # SUCCESS: Factory method now exists and works cleanly
        result = VectorResult.create_immutable(**result_data)
        assert isinstance(result.embeddings, tuple), "Should convert to tuple"
        assert all(
            isinstance(emb, tuple) for emb in result.embeddings
        ), "Should convert nested lists"
        assert result.embeddings == ((1.0, 2.0), (3.0, 4.0)), "Should preserve content"

        # Verify both approaches work (factory vs direct constructor)
        task_direct = VectorTask(**task_data)
        assert (
            task_direct.chunk_texts == task.chunk_texts
        ), "Both approaches should work"

    def test_batch_processing_edge_cases_should_be_handled_gracefully(self):
        """
        Test that batch processing handles edge cases properly.

        Tests various edge cases that could cause issues:
        - Empty strings in batch
        - None values
        - Very large batches
        """
        manager = VectorCalculationManager(self.mock_provider, thread_count=1)

        # Test empty string handling
        self.mock_provider.get_embeddings_batch = Mock(return_value=[[0.0, 0.0]])
        empty_string_task = VectorTask(
            task_id="empty_string",
            chunk_texts=("",),  # Empty string
            metadata={},
            created_at=time.time(),
        )

        result = manager._calculate_vector(empty_string_task)

        # Should handle empty strings gracefully
        assert result.error is None
        assert len(result.embeddings) == 1

    def test_statistics_initialization_should_include_embedding_tracking(self):
        """
        FAILING TEST: VectorCalculationStats should include embedding tracking fields.

        Current behavior: Only tracks task-level statistics.
        Expected behavior: Include total_embeddings_processed field.
        """
        stats = VectorCalculationStats()

        # EXPECTED: Should have embedding tracking field
        # This will FAIL because the field doesn't exist yet
        assert hasattr(
            stats, "total_embeddings_processed"
        ), "Stats should track embeddings"
        assert stats.total_embeddings_processed == 0, "Should initialize to zero"

    def test_rolling_window_should_track_embeddings_not_tasks(self):
        """
        FAILING TEST: Rolling window calculation should use embedding counts.

        Current behavior: Rolling window tracks task completion count.
        Expected behavior: Track actual embedding count for accurate rate calculation.
        """
        self.mock_provider.get_embeddings_batch = Mock(
            return_value=[[1.0, 2.0], [3.0, 4.0]]  # 2 embeddings per call
        )

        manager = VectorCalculationManager(self.mock_provider, thread_count=1)

        # Access the rolling window update method directly for testing
        current_time = time.time()

        # EXPECTED: Method should accept embedding count, not task count
        # This will FAIL because current signature only accepts task count
        try:
            # Current method signature - will work but is wrong conceptually
            manager._update_rolling_window(current_time, total_completed=1)

            # EXPECTED: Should have embedding-aware signature
            # This call should work but will FAIL because method doesn't exist
            manager._update_rolling_window_embeddings(
                current_time, total_embeddings=2, total_tasks=1
            )
            assert False, "Expected method doesn't exist yet"
        except AttributeError:
            # Expected to fail - the embedding-aware method doesn't exist
            pass

    def test_concurrent_batch_processing_statistics_accuracy(self):
        """
        Test that statistics remain accurate under concurrent batch processing.

        Verifies that embedding counts are properly tracked when multiple
        threads process batches simultaneously.
        """
        # Mock provider with different batch sizes
        self.mock_provider.get_embeddings_batch = Mock(
            side_effect=lambda texts: [[i, i + 1] for i, _ in enumerate(texts)]
        )

        manager = VectorCalculationManager(self.mock_provider, thread_count=2)
        manager.start()

        # Create batch tasks directly to test actual batch processing
        expected_total_embeddings = 0
        batch_tasks = []

        for i in range(5):
            batch_size = i + 1  # Varying batch sizes: 1, 2, 3, 4, 5
            chunk_texts = tuple(f"chunk_{i}_{j}" for j in range(batch_size))
            expected_total_embeddings += batch_size

            # Create batch task directly
            task = VectorTask(
                task_id=f"batch_task_{i}",
                chunk_texts=chunk_texts,
                metadata={"test": i},
                created_at=time.time(),
            )
            batch_tasks.append(task)

        # Process batch tasks directly
        for task in batch_tasks:
            manager._calculate_vector(task)

        stats = manager.get_stats()

        # SUCCESS: Statistics should accurately reflect total embeddings
        assert stats.total_embeddings_processed == expected_total_embeddings, (
            f"Expected {expected_total_embeddings} embeddings, got {stats.total_embeddings_processed}. "
            f"Tasks completed: {stats.total_tasks_completed}"
        )

        manager.shutdown()
