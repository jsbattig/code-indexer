"""
Unit tests specifically for backward compatibility properties of VectorTask and VectorResult.

Tests the compatibility properties that allow existing code to continue working
with the new batch processing data structures.
"""

import pytest
from code_indexer.services.vector_calculation_manager import (
    VectorTask,
    VectorResult,
)


class TestVectorTaskBackwardCompatibility:
    """Test VectorTask backward compatibility properties."""

    def test_chunk_text_property_single_chunk(self):
        """Test chunk_text property works with single chunk."""
        task = VectorTask(
            task_id="single_001",
            chunk_texts=["single chunk content"],
            metadata={"file": "test.py"},
            created_at=1234567890.0,
        )

        # Should be able to access via chunk_text property
        assert task.chunk_text == "single chunk content"
        assert task.chunk_text == task.chunk_texts[0]

    def test_chunk_text_property_empty_chunks(self):
        """Test chunk_text property returns empty string for empty chunks."""
        task = VectorTask(
            task_id="empty_001",
            chunk_texts=[],
            metadata={"file": "test.py"},
            created_at=1234567890.0,
        )

        # Should return empty string for empty chunks
        assert task.chunk_text == ""

    def test_chunk_text_property_multiple_chunks_raises(self):
        """Test chunk_text property raises ValueError for multiple chunks."""
        task = VectorTask(
            task_id="batch_001",
            chunk_texts=["chunk1", "chunk2", "chunk3"],
            metadata={"file": "test.py"},
            created_at=1234567890.0,
        )

        # Should raise ValueError when accessing chunk_text with multiple chunks
        with pytest.raises(ValueError) as exc_info:
            _ = task.chunk_text

        assert "Cannot access chunk_text on batch with 3 chunks" in str(exc_info.value)
        assert "Use chunk_texts instead" in str(exc_info.value)


class TestVectorResultBackwardCompatibility:
    """Test VectorResult backward compatibility properties."""

    def test_embedding_property_single_embedding(self):
        """Test embedding property works with single embedding."""
        result = VectorResult(
            task_id="single_001",
            embeddings=[[0.1, 0.2, 0.3, 0.4]],
            metadata={"file": "test.py"},
            processing_time=0.5,
        )

        # Should be able to access via embedding property
        assert result.embedding == [0.1, 0.2, 0.3, 0.4]
        assert result.embedding == list(
            result.embeddings[0]
        )  # Convert tuple to list for comparison

    def test_embedding_property_empty_embeddings(self):
        """Test embedding property returns empty list for empty embeddings."""
        result = VectorResult(
            task_id="empty_001",
            embeddings=[],
            metadata={"file": "test.py"},
            processing_time=0.1,
        )

        # Should return empty list for empty embeddings
        assert result.embedding == []

    def test_embedding_property_multiple_embeddings_raises(self):
        """Test embedding property raises ValueError for multiple embeddings."""
        result = VectorResult(
            task_id="batch_001",
            embeddings=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            metadata={"file": "test.py"},
            processing_time=1.0,
        )

        # Should raise ValueError when accessing embedding with multiple embeddings
        with pytest.raises(ValueError) as exc_info:
            _ = result.embedding

        assert "Cannot access embedding on batch with 3 embeddings" in str(
            exc_info.value
        )
        assert "Use embeddings instead" in str(exc_info.value)


class TestBackwardCompatibilityIntegration:
    """Test backward compatibility in realistic usage scenarios."""

    def test_legacy_code_single_chunk_workflow(self):
        """Test that legacy code expecting single chunks still works."""
        # Legacy code pattern - single chunk submission
        task = VectorTask(
            task_id="legacy_001",
            chunk_texts=["This is legacy single chunk text"],
            metadata={"legacy": True},
            created_at=1234567890.0,
        )

        # Legacy code accessing via chunk_text property
        legacy_text = task.chunk_text  # Should work
        assert legacy_text == "This is legacy single chunk text"

        # Create result with single embedding
        result = VectorResult(
            task_id="legacy_001",
            embeddings=[[1.0, 2.0, 3.0]],
            metadata={"legacy": True},
            processing_time=0.2,
        )

        # Legacy code accessing via embedding property
        legacy_embedding = result.embedding  # Should work
        assert legacy_embedding == [1.0, 2.0, 3.0]

    def test_mixed_usage_patterns(self):
        """Test mixing old and new access patterns."""
        # Single chunk task - both patterns should work
        single_task = VectorTask(
            task_id="mixed_001",
            chunk_texts=["single"],
            metadata={},
            created_at=1234567890.0,
        )

        assert single_task.chunk_text == "single"  # Old pattern
        assert single_task.chunk_texts[0] == "single"  # New pattern
        assert single_task.batch_size == 1  # New pattern

        # Batch task - only new pattern should work
        batch_task = VectorTask(
            task_id="mixed_002",
            chunk_texts=["first", "second"],
            metadata={},
            created_at=1234567890.0,
        )

        assert batch_task.chunk_texts == (
            "first",
            "second",
        )  # New pattern (now immutable tuple)
        assert batch_task.batch_size == 2  # New pattern

        # Old pattern should fail with clear error
        with pytest.raises(ValueError) as exc_info:
            _ = batch_task.chunk_text
        assert "Use chunk_texts instead" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
