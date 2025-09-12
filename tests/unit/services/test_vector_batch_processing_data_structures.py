"""
Unit tests for VectorTask and VectorResult batch processing data structure modifications.

Tests the enhanced data structures that support batch processing operations
while maintaining thread safety and order preservation.
"""

import pytest
import time
import threading
from typing import List

from code_indexer.services.vector_calculation_manager import (
    VectorTask,
    VectorResult,
)


class TestVectorTaskBatchProcessing:
    """Test VectorTask batch processing support."""

    def test_vector_task_supports_chunk_texts_array(self):
        """Test that VectorTask supports chunk_texts array field."""
        chunk_texts = ["text1", "text2", "text3"]
        metadata = {"file_path": "test.py", "batch_size": 3}
        task_id = "batch_task_001"
        created_at = time.time()

        # This should work with new batch structure
        task = VectorTask(
            task_id=task_id,
            chunk_texts=chunk_texts,  # New batch field
            metadata=metadata,
            created_at=created_at,
        )

        assert task.task_id == task_id
        assert task.chunk_texts == tuple(chunk_texts)  # Now returns immutable tuple
        assert len(task.chunk_texts) == 3
        assert task.metadata == metadata
        assert task.created_at == created_at

    def test_vector_task_batch_size_tracking(self):
        """Test that VectorTask tracks batch_size in metadata."""
        chunk_texts = ["chunk1", "chunk2", "chunk3", "chunk4"]
        metadata = {"file_path": "test.py", "original_index": 0}

        task = VectorTask(
            task_id="batch_task_002",
            chunk_texts=chunk_texts,
            metadata=metadata,
            created_at=time.time(),
        )

        # Should automatically track batch size
        assert task.batch_size == 4
        assert task.batch_size == len(chunk_texts)

    def test_vector_task_maintains_single_chunk_compatibility(self):
        """Test that VectorTask maintains compatibility with single chunks."""
        # Should still support single chunk via chunk_texts with one element
        single_chunk_texts = ["single chunk text"]
        metadata = {"file_path": "test.py", "chunk_index": 0}

        task = VectorTask(
            task_id="single_task_001",
            chunk_texts=single_chunk_texts,
            metadata=metadata,
            created_at=time.time(),
        )

        assert task.batch_size == 1
        assert len(task.chunk_texts) == 1
        assert task.chunk_texts[0] == "single chunk text"

    def test_vector_task_empty_batch_handling(self):
        """Test VectorTask handling of empty batch."""
        empty_chunk_texts: List[str] = []
        metadata = {"file_path": "test.py"}

        task = VectorTask(
            task_id="empty_task_001",
            chunk_texts=empty_chunk_texts,
            metadata=metadata,
            created_at=time.time(),
        )

        assert task.batch_size == 0
        assert len(task.chunk_texts) == 0

    def test_vector_task_metadata_preservation(self):
        """Test that all existing metadata fields are preserved."""
        chunk_texts = ["text1", "text2"]
        complex_metadata = {
            "file_path": "/path/to/file.py",
            "original_chunk_index": 42,
            "nested": {"key": "value", "list": [1, 2, 3]},
            "timestamp": "2024-01-01T00:00:00Z",
            "processing_context": "batch_operation",
        }

        task = VectorTask(
            task_id="metadata_task_001",
            chunk_texts=chunk_texts,
            metadata=complex_metadata,
            created_at=time.time(),
        )

        assert task.metadata == complex_metadata
        assert task.metadata["file_path"] == "/path/to/file.py"
        assert task.metadata["nested"]["key"] == "value"
        assert task.batch_size == 2


class TestVectorResultBatchProcessing:
    """Test VectorResult batch processing support."""

    def test_vector_result_supports_embeddings_array(self):
        """Test that VectorResult supports embeddings array field."""
        embeddings = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]
        metadata = {"file_path": "test.py", "batch_size": 3}
        task_id = "batch_result_001"
        processing_time = 0.5

        # This should work with new batch structure
        result = VectorResult(
            task_id=task_id,
            embeddings=embeddings,  # New batch field
            metadata=metadata,
            processing_time=processing_time,
        )

        assert result.task_id == task_id
        assert result.embeddings == tuple(
            tuple(emb) for emb in embeddings
        )  # Now returns nested immutable tuples
        assert len(result.embeddings) == 3
        assert len(result.embeddings[0]) == 3
        assert result.metadata == metadata
        assert result.processing_time == processing_time
        assert result.error is None

    def test_vector_result_batch_size_tracking(self):
        """Test that VectorResult tracks batch_size."""
        embeddings = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
        metadata = {"file_path": "test.py"}

        result = VectorResult(
            task_id="batch_result_002",
            embeddings=embeddings,
            metadata=metadata,
            processing_time=0.3,
        )

        # Should automatically track batch size
        assert result.batch_size == 4
        assert result.batch_size == len(embeddings)

    def test_vector_result_maintains_single_embedding_compatibility(self):
        """Test that VectorResult maintains compatibility with single embeddings."""
        # Should support single embedding via embeddings array with one element
        single_embeddings = [[0.1, 0.2, 0.3, 0.4, 0.5]]
        metadata = {"file_path": "test.py", "chunk_index": 0}

        result = VectorResult(
            task_id="single_result_001",
            embeddings=single_embeddings,
            metadata=metadata,
            processing_time=0.1,
        )

        assert result.batch_size == 1
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 5

    def test_vector_result_empty_embeddings_handling(self):
        """Test VectorResult handling of empty embeddings."""
        empty_embeddings: List[List[float]] = []
        metadata = {"file_path": "test.py"}

        result = VectorResult(
            task_id="empty_result_001",
            embeddings=empty_embeddings,
            metadata=metadata,
            processing_time=0.05,
        )

        assert result.batch_size == 0
        assert len(result.embeddings) == 0

    def test_vector_result_error_handling_with_batch(self):
        """Test VectorResult error handling in batch context."""
        embeddings: List[List[float]] = []  # Empty on error
        metadata = {"file_path": "test.py", "batch_size": 3}
        error_message = "Batch processing failed: Connection timeout"

        result = VectorResult(
            task_id="error_result_001",
            embeddings=embeddings,
            metadata=metadata,
            processing_time=2.0,
            error=error_message,
        )

        assert result.error == error_message
        assert result.batch_size == 0  # Empty on error
        assert len(result.embeddings) == 0

    def test_vector_result_metadata_preservation(self):
        """Test that all existing metadata fields are preserved."""
        embeddings = [[0.1, 0.2], [0.3, 0.4]]
        complex_metadata = {
            "file_path": "/path/to/file.py",
            "original_chunk_indices": [42, 43],
            "nested": {"key": "value", "list": [1, 2, 3]},
            "timestamp": "2024-01-01T00:00:00Z",
            "processing_context": "batch_operation",
        }

        result = VectorResult(
            task_id="metadata_result_001",
            embeddings=embeddings,
            metadata=complex_metadata,
            processing_time=0.2,
        )

        assert result.metadata == complex_metadata
        assert result.metadata["file_path"] == "/path/to/file.py"
        assert result.metadata["nested"]["key"] == "value"
        assert result.batch_size == 2


class TestBatchDataStructureOrderPreservation:
    """Test order preservation guarantees for batch processing."""

    def test_vector_task_chunk_order_preservation(self):
        """Test that VectorTask preserves order of chunk_texts."""
        ordered_chunks = [
            "First chunk in sequence",
            "Second chunk in sequence",
            "Third chunk in sequence",
            "Fourth chunk in sequence",
            "Fifth chunk in sequence",
        ]

        task = VectorTask(
            task_id="order_task_001",
            chunk_texts=ordered_chunks,
            metadata={"file_path": "test.py"},
            created_at=time.time(),
        )

        # Order should be preserved exactly
        for i, chunk in enumerate(task.chunk_texts):
            assert chunk == ordered_chunks[i]
            assert "chunk in sequence" in chunk

    def test_vector_result_embedding_order_preservation(self):
        """Test that VectorResult preserves order of embeddings."""
        # Create ordered embeddings with distinct patterns
        ordered_embeddings = [
            [float(i), float(i + 1), float(i + 2)] for i in range(0, 15, 3)
        ]

        result = VectorResult(
            task_id="order_result_001",
            embeddings=ordered_embeddings,
            metadata={"file_path": "test.py"},
            processing_time=0.3,
        )

        # Order should be preserved exactly
        for i, embedding in enumerate(result.embeddings):
            expected_embedding = [float(i * 3), float(i * 3 + 1), float(i * 3 + 2)]
            assert (
                list(embedding) == expected_embedding
            )  # Convert tuple to list for comparison

    def test_batch_processing_chunk_to_embedding_correspondence(self):
        """Test that chunk order corresponds to embedding order."""
        chunk_texts = [f"Chunk {i} content" for i in range(5)]
        embeddings = [[float(i), float(i * 2)] for i in range(5)]

        task = VectorTask(
            task_id="correspondence_task_001",
            chunk_texts=chunk_texts,
            metadata={"file_path": "test.py"},
            created_at=time.time(),
        )

        result = VectorResult(
            task_id="correspondence_task_001",
            embeddings=embeddings,
            metadata={"file_path": "test.py"},
            processing_time=0.4,
        )

        # Verify correspondence by index
        assert len(task.chunk_texts) == len(result.embeddings)
        for i in range(len(chunk_texts)):
            assert f"Chunk {i} content" == task.chunk_texts[i]
            assert [float(i), float(i * 2)] == list(
                result.embeddings[i]
            )  # Convert tuple to list for comparison


class TestBatchDataStructureThreadSafety:
    """Test thread safety of batch processing data structures."""

    def test_vector_task_concurrent_access_safety(self):
        """Test that VectorTask data is safe for concurrent access."""
        chunk_texts = [f"Thread safe chunk {i}" for i in range(10)]
        metadata = {"file_path": "test.py", "thread_test": True}

        task = VectorTask(
            task_id="thread_task_001",
            chunk_texts=chunk_texts,
            metadata=metadata,
            created_at=time.time(),
        )

        # Simulate concurrent access from multiple threads
        access_results = []
        access_lock = threading.Lock()

        def concurrent_access():
            # Read data from multiple threads
            local_chunks = list(task.chunk_texts)  # Create copy
            local_metadata = dict(task.metadata)  # Create copy
            local_batch_size = task.batch_size

            with access_lock:
                access_results.append(
                    {
                        "chunks_count": len(local_chunks),
                        "metadata_keys": set(local_metadata.keys()),
                        "batch_size": local_batch_size,
                    }
                )

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=concurrent_access)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all threads got consistent data
        assert len(access_results) == 5
        for result in access_results:
            assert result["chunks_count"] == 10
            assert "file_path" in result["metadata_keys"]
            assert result["batch_size"] == 10

    def test_vector_result_concurrent_access_safety(self):
        """Test that VectorResult data is safe for concurrent access."""
        embeddings = [[float(i), float(i + 0.5)] for i in range(8)]
        metadata = {"file_path": "test.py", "thread_test": True}

        result = VectorResult(
            task_id="thread_result_001",
            embeddings=embeddings,
            metadata=metadata,
            processing_time=0.5,
        )

        # Simulate concurrent access from multiple threads
        access_results = []
        access_lock = threading.Lock()

        def concurrent_access():
            # Read data from multiple threads
            local_embeddings = [list(emb) for emb in result.embeddings]  # Deep copy
            local_metadata = dict(result.metadata)  # Create copy
            local_batch_size = result.batch_size
            local_error = result.error

            with access_lock:
                access_results.append(
                    {
                        "embeddings_count": len(local_embeddings),
                        "embedding_dimensions": (
                            len(local_embeddings[0]) if local_embeddings else 0
                        ),
                        "metadata_keys": set(local_metadata.keys()),
                        "batch_size": local_batch_size,
                        "has_error": local_error is not None,
                    }
                )

        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=concurrent_access)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all threads got consistent data
        assert len(access_results) == 3
        for result in access_results:
            assert result["embeddings_count"] == 8
            assert result["embedding_dimensions"] == 2
            assert "file_path" in result["metadata_keys"]
            assert result["batch_size"] == 8
            assert result["has_error"] is False


if __name__ == "__main__":
    pytest.main([__file__])
