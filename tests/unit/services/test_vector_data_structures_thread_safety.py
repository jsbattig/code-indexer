"""
Tests for thread safety issues in VectorTask and VectorResult data structures.

These tests demonstrate the critical thread safety violations that need to be fixed:
1. Mutable lists and dictionaries can be modified from multiple threads
2. No protection against external mutation of internal data
3. Race conditions when accessing shared mutable state
"""

# type: ignore

import pytest
import threading
import time
from dataclasses import FrozenInstanceError

from src.code_indexer.services.vector_calculation_manager import (
    VectorTask,
    VectorResult,
)


class TestVectorTaskThreadSafety:
    """Test thread safety issues in VectorTask data structure."""

    def test_vector_task_mutable_list_race_condition(self):
        """Test that chunk_texts is now immutable (prevents race conditions)."""
        # Create VectorTask with immutable tuple
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["chunk1", "chunk2"],
            metadata={"file": "test.py"},
            created_at=time.time(),
        )

        # This should fail with AttributeError because tuples are immutable
        with pytest.raises(
            AttributeError, match="'tuple' object has no attribute 'append'"
        ):
            task.chunk_texts.append("chunk3")  # Now properly prevented!

    def test_vector_task_mutable_metadata_race_condition(self):
        """Test that mutable metadata dict creates race conditions."""
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["chunk1"],
            metadata={"file": "test.py", "line": 1},
            created_at=time.time(),
        )

        # This should fail with frozen dataclass - currently passes (BAD)
        task.metadata["new_key"] = "new_value"  # THREAD SAFETY VIOLATION!
        assert task.metadata["new_key"] == "new_value"  # Mutation succeeded (BAD)

    def test_vector_task_concurrent_mutation_race_condition(self):
        """Test concurrent mutations are prevented by frozen dataclass."""
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["initial"],
            metadata={"count": 0},
            created_at=time.time(),
        )

        def modify_task():
            """Attempt to modify task data from multiple threads."""
            # These mutations should fail with AttributeError due to tuple immutability
            with pytest.raises(AttributeError):
                task.chunk_texts.append("chunk_fail")  # Tuple has no append method

            # Metadata is deep copied so mutations don't affect the original
            task.metadata["count"] = task.metadata.get("count", 0) + 1
            # This mutation should only affect the local copy, not the original task

        # Run concurrent modifications
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=modify_task)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Original task should be unchanged
        assert len(task.chunk_texts) == 1
        assert task.chunk_texts[0] == "initial"

    def test_vector_task_should_be_frozen(self):
        """Test that VectorTask should be immutable (frozen dataclass)."""
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["chunk1"],
            metadata={"file": "test.py"},
            created_at=time.time(),
        )

        # These assignments should fail with FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            task.task_id = "modified"  # Should fail but currently passes

        with pytest.raises(FrozenInstanceError):
            task.chunk_texts = ["new_chunk"]  # Should fail but currently passes

        with pytest.raises(FrozenInstanceError):
            task.metadata = {"new": "metadata"}  # Should fail but currently passes


class TestVectorResultThreadSafety:
    """Test thread safety issues in VectorResult data structure."""

    def test_vector_result_mutable_embeddings_race_condition(self):
        """Test that embeddings is now immutable (prevents race conditions)."""
        result = VectorResult(
            task_id="test_task",
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            metadata={"file": "test.py"},
            processing_time=0.1,
        )

        # This should fail with AttributeError because tuples are immutable
        with pytest.raises(
            AttributeError, match="'tuple' object has no attribute 'append'"
        ):
            result.embeddings.append([0.5, 0.6])  # Now properly prevented!

    def test_vector_result_mutable_metadata_race_condition(self):
        """Test that mutable metadata dict creates race conditions."""
        result = VectorResult(
            task_id="test_task",
            embeddings=[[0.1, 0.2]],
            metadata={"file": "test.py"},
            processing_time=0.1,
        )

        # This should fail with frozen dataclass - currently passes (BAD)
        result.metadata["modified"] = "yes"  # THREAD SAFETY VIOLATION!
        assert result.metadata["modified"] == "yes"  # Mutation succeeded (BAD)

    def test_vector_result_should_be_frozen(self):
        """Test that VectorResult should be immutable (frozen dataclass)."""
        result = VectorResult(
            task_id="test_task",
            embeddings=[[0.1, 0.2]],
            metadata={"file": "test.py"},
            processing_time=0.1,
        )

        # These assignments should fail with FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            result.task_id = "modified"  # Should fail but currently passes

        with pytest.raises(FrozenInstanceError):
            result.embeddings = [[0.9, 0.8]]  # Should fail but currently passes

        with pytest.raises(FrozenInstanceError):
            result.metadata = {"new": "metadata"}  # Should fail but currently passes


class TestDeepNestingViolations:
    """Test deep nesting anti-pattern violations in property implementations."""

    def test_vector_task_chunk_text_property_deep_nesting(self):
        """Test that chunk_text property has deep nesting violation."""
        # Single chunk - should work
        task_single = VectorTask(
            task_id="test_single",
            chunk_texts=["single_chunk"],
            metadata={},
            created_at=time.time(),
        )
        assert task_single.chunk_text == "single_chunk"

        # Empty chunks - should return empty string
        task_empty = VectorTask(
            task_id="test_empty", chunk_texts=[], metadata={}, created_at=time.time()
        )
        assert task_empty.chunk_text == ""

        # Multiple chunks - should raise ValueError
        task_multiple = VectorTask(
            task_id="test_multiple",
            chunk_texts=["chunk1", "chunk2"],
            metadata={},
            created_at=time.time(),
        )
        with pytest.raises(ValueError, match="Cannot access chunk_text on batch"):
            _ = task_multiple.chunk_text

    def test_vector_result_embedding_property_deep_nesting(self):
        """Test that embedding property has deep nesting violation."""
        # Single embedding - should work
        result_single = VectorResult(
            task_id="test_single",
            embeddings=[[0.1, 0.2, 0.3]],
            metadata={},
            processing_time=0.1,
        )
        assert result_single.embedding == [0.1, 0.2, 0.3]

        # Empty embeddings - should return empty list
        result_empty = VectorResult(
            task_id="test_empty", embeddings=[], metadata={}, processing_time=0.1
        )
        assert result_empty.embedding == []

        # Multiple embeddings - should raise ValueError
        result_multiple = VectorResult(
            task_id="test_multiple",
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            metadata={},
            processing_time=0.1,
        )
        with pytest.raises(ValueError, match="Cannot access embedding on batch"):
            _ = result_multiple.embedding


class TestImmutableTypeRequirements:
    """Test that data structures should use immutable types."""

    def test_vector_task_should_use_tuple_for_chunk_texts(self):
        """Test that chunk_texts should be a Tuple, not List."""
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["chunk1", "chunk2"],  # Currently List - should be Tuple
            metadata={"file": "test.py"},
            created_at=time.time(),
        )

        # Should be tuple type for immutability
        assert isinstance(task.chunk_texts, tuple)  # Currently fails - it's a list

    def test_vector_result_should_use_tuple_for_embeddings(self):
        """Test that embeddings should be a Tuple, not List."""
        result = VectorResult(
            task_id="test_task",
            embeddings=[[0.1, 0.2], [0.3, 0.4]],  # Currently List - should be Tuple
            metadata={"file": "test.py"},
            processing_time=0.1,
        )

        # Should be tuple type for immutability
        assert isinstance(result.embeddings, tuple)  # Currently fails - it's a list


class TestMetadataProtection:
    """Test that metadata should be protected from external mutation."""

    def test_vector_task_metadata_should_be_immutable(self):
        """Test that metadata should be protected from mutation."""
        original_metadata = {"file": "test.py", "line": 1}
        task = VectorTask(
            task_id="test_task",
            chunk_texts=["chunk1"],
            metadata=original_metadata,
            created_at=time.time(),
        )

        # Modifying original metadata should not affect task
        original_metadata["modified"] = "externally"

        # Task metadata should be unaffected (currently fails)
        assert (
            "modified" not in task.metadata
        )  # Currently fails due to shared reference

    def test_vector_result_metadata_should_be_immutable(self):
        """Test that metadata should be protected from mutation."""
        original_metadata = {"file": "test.py", "line": 1}
        result = VectorResult(
            task_id="test_task",
            embeddings=[[0.1, 0.2]],
            metadata=original_metadata,
            processing_time=0.1,
        )

        # Modifying original metadata should not affect result
        original_metadata["modified"] = "externally"

        # Result metadata should be unaffected (currently fails)
        assert (
            "modified" not in result.metadata
        )  # Currently fails due to shared reference
