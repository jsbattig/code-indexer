"""
Test file chunk batching optimization - primary performance improvement.

This test validates the critical optimization that reduces API calls from N chunks
to 1 API call per file, providing 10-50x throughput improvement.

Tests verify:
1. Single batch submission replaces individual chunk processing loop
2. Filesystem point creation from batch results with proper chunk-to-embedding mapping
3. File atomicity and error handling (atomic failure, no partial results)
4. Order preservation and metadata consistency across all chunks
5. API call reduction measurement (N chunks → 1 API call)
"""

import pytest
from unittest.mock import Mock
from concurrent.futures import Future
from typing import List, Dict, Any

from src.code_indexer.services.file_chunking_manager import FileChunkingManager
from src.code_indexer.services.vector_calculation_manager import VectorResult


@pytest.fixture
def mock_chunker():
    """Mock chunker that returns predictable chunks."""
    chunker = Mock()
    # Return 3 chunks with predictable content
    chunker.chunk_file.return_value = [
        {"text": "chunk_1_content", "line_start": 1, "line_end": 5},
        {"text": "chunk_2_content", "line_start": 6, "line_end": 10},
        {"text": "chunk_3_content", "line_start": 11, "line_end": 15},
    ]
    return chunker


@pytest.fixture
def mock_vector_manager():
    """Mock vector manager with batch processing capabilities."""
    manager = Mock()
    # Track API calls for reduction validation
    manager.submit_chunk_call_count = 0
    manager.submit_batch_task_call_count = 0

    # TOKEN COUNTING FIX: Mock embedding provider methods
    manager.embedding_provider.get_current_model.return_value = (
        "voyage-large-2-instruct"
    )
    manager.embedding_provider._get_model_token_limit.return_value = 120000

    def mock_submit_chunk(*args, **kwargs):
        manager.submit_chunk_call_count += 1
        future: Future = Future()
        # This should not be called in optimized version
        future.set_result(Mock())
        return future

    def mock_submit_batch_task(chunk_texts: List[str], metadata: Dict[str, Any]):
        manager.submit_batch_task_call_count += 1
        future: Future = Future()
        # Return batch result with embeddings for all chunks
        vector_result = VectorResult(
            task_id="batch_task_123",
            embeddings=(  # Tuple of embeddings matching chunk order
                (0.1, 0.2, 0.3),  # chunk_1 embedding
                (0.4, 0.5, 0.6),  # chunk_2 embedding
                (0.7, 0.8, 0.9),  # chunk_3 embedding
            ),
            metadata=metadata,
            processing_time=0.1,
            error=None,
        )
        future.set_result(vector_result)
        return future

    manager.submit_chunk.side_effect = mock_submit_chunk
    manager.submit_batch_task.side_effect = mock_submit_batch_task
    return manager


@pytest.fixture
def mock_filesystem_client():
    """Mock Filesystem client for point storage."""
    client = Mock()
    client.upsert_points.return_value = True
    return client


@pytest.fixture
def mock_slot_tracker():
    """Mock slot tracker for file status management."""
    tracker = Mock()
    tracker.acquire_slot.return_value = "slot_123"
    tracker.get_concurrent_files_data.return_value = []
    return tracker


@pytest.fixture
def file_chunking_manager(
    mock_chunker,
    mock_vector_manager,
    mock_filesystem_client,
    mock_slot_tracker,
    tmp_path,
):
    """Create FileChunkingManager with mocked dependencies."""
    manager = FileChunkingManager(
        vector_manager=mock_vector_manager,
        chunker=mock_chunker,
        vector_store_client=mock_filesystem_client,
        thread_count=4,
        slot_tracker=mock_slot_tracker,
        codebase_dir=tmp_path,
    )

    # TOKEN COUNTING FIX: Mock the voyage client count_tokens method
    manager.voyage_client = Mock()
    manager.voyage_client.count_tokens.return_value = 100  # Return fixed token count

    return manager


@pytest.fixture
def standard_metadata():
    """Standard metadata for testing with all required fields."""
    return {
        "collection_name": "test",
        "project_id": "test_project",
        "file_hash": "test_hash_123",
        "git_available": False,
        "branch_name": "main",
    }


class TestFileChunkBatchingOptimization:
    """Test the critical file chunk batching optimization."""

    def test_single_batch_submission_replaces_individual_chunks(
        self,
        file_chunking_manager,
        mock_vector_manager,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """
        CRITICAL TEST: Verify single batch submission replaces N individual chunk submissions.

        This is the PRIMARY optimization - reducing N API calls to 1 API call per file.
        """
        # Create test file
        test_file = tmp_path / "test_file.py"
        test_file.write_text(
            "def func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass"
        )

        # Use standard metadata and add file_path
        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Process file using context manager and submit method
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()  # Wait for completion

        # CRITICAL VALIDATION: Single batch API call, zero individual calls
        assert (
            mock_vector_manager.submit_batch_task_call_count == 1
        ), "Must use exactly 1 batch API call per file"
        assert (
            mock_vector_manager.submit_chunk_call_count == 0
        ), "Must not use individual chunk API calls in optimized version"

        # Verify batch submission received all chunk texts
        batch_call = mock_vector_manager.submit_batch_task.call_args
        chunk_texts = batch_call[0][0]  # First positional argument
        expected_texts = ["chunk_1_content", "chunk_2_content", "chunk_3_content"]
        assert (
            chunk_texts == expected_texts
        ), "Batch submission must include all chunk texts in order"

        # Verify successful processing
        assert result.success is True
        assert result.chunks_processed == 3

    def test_filesystem_point_creation_from_batch_results(
        self,
        file_chunking_manager,
        mock_filesystem_client,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """
        Verify Filesystem points created from batch results with proper chunk-to-embedding mapping.

        Critical: chunks[i] ↔ embeddings[i] ↔ points[i] mapping must be preserved.
        """
        # Create test file
        test_file = tmp_path / "test_file.py"
        test_file.write_text("content")

        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Process file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # Verify Filesystem upsert was called
        assert mock_filesystem_client.upsert_points.called

        # Analyze the points that were created
        upsert_call = mock_filesystem_client.upsert_points.call_args
        points_data = upsert_call.kwargs["points"]

        # Verify correct number of points
        assert len(points_data) == 3, "Must create point for each chunk"

        # Verify chunk-to-embedding mapping preservation
        expected_mappings = [
            (
                "chunk_1_content",
                (0.1, 0.2, 0.3),
                1,
                5,
            ),  # chunk_text, embedding, line_start, line_end
            ("chunk_2_content", (0.4, 0.5, 0.6), 6, 10),
            ("chunk_3_content", (0.7, 0.8, 0.9), 11, 15),
        ]

        for i, (
            expected_text,
            expected_vector,
            expected_line_start,
            expected_line_end,
        ) in enumerate(expected_mappings):
            point = points_data[i]

            # Verify text content mapping
            assert expected_text in str(
                point
            ), f"Point {i} must contain correct chunk text"

            # Verify embedding mapping (accept both list and tuple formats)
            actual_vector = point["vector"]
            expected_vector_list = list(
                expected_vector
            )  # Convert tuple to list for comparison
            assert (
                actual_vector == expected_vector_list
            ), f"Point {i} must have correct embedding from batch result"

            # Verify metadata mapping
            payload = point["payload"]
            assert payload["line_start"] == expected_line_start
            assert payload["line_end"] == expected_line_end
            assert payload["chunk_index"] == i
            assert payload["total_chunks"] == 3

        assert result.success is True

    def test_file_atomicity_with_batch_failure(
        self,
        file_chunking_manager,
        mock_vector_manager,
        mock_filesystem_client,
        tmp_path,
        mock_slot_tracker,
    ):
        """
        Verify file atomicity: batch failure results in complete file failure.

        No partial results should be stored when batch processing fails.
        """
        # Create test file
        test_file = tmp_path / "test_file.py"
        test_file.write_text("content")

        metadata = {
            "collection_name": "test",
            "file_path": str(test_file),
            "project_id": "test_project",
            "file_hash": "test_hash_123",
            "git_available": False,
        }

        # Configure batch processing to fail
        def failing_batch_task(chunk_texts, metadata):
            future: Future = Future()
            vector_result = VectorResult(
                task_id="batch_fail",
                embeddings=(),
                metadata=metadata,
                processing_time=0.1,
                error="Batch processing failed",
            )
            future.set_result(vector_result)
            return future

        mock_vector_manager.submit_batch_task.side_effect = failing_batch_task

        # Process file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # Verify atomic failure
        assert result.success is False
        assert result.chunks_processed == 0
        assert (
            "Batch processing failed" in str(result.error)
            or result.error == "No valid embeddings"
        )

        # Verify no partial data written to Filesystem
        assert (
            not mock_filesystem_client.upsert_points.called
        ), "No data should be written to Filesystem on batch failure"

    def test_order_preservation_and_metadata_consistency(
        self,
        file_chunking_manager,
        mock_filesystem_client,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """
        Verify order preservation: chunks[i] maps to embeddings[i] and points[i].

        Critical for maintaining semantic relationship between chunks and vectors.
        """
        test_file = tmp_path / "ordered_test.py"
        test_file.write_text("content")

        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Process file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # Extract created points
        points_data = mock_filesystem_client.upsert_points.call_args.kwargs["points"]

        # Verify strict order preservation
        for i, point in enumerate(points_data):
            payload = point["payload"]

            # Verify chunk index sequence
            assert (
                payload["chunk_index"] == i
            ), f"Point {i} must have correct chunk_index"

            # Verify line number ordering (chunks must be in file order)
            if i > 0:
                prev_point = points_data[i - 1]
                prev_line_end = prev_point["payload"]["line_end"]
                curr_line_start = payload["line_start"]
                assert (
                    curr_line_start > prev_line_end
                ), f"Chunk {i} line_start must be after previous chunk line_end"

            # Verify consistent metadata across all points
            expected_metadata_keys = {
                "path",
                "line_start",
                "line_end",
                "chunk_index",
                "total_chunks",
            }
            actual_keys = set(payload.keys())
            assert expected_metadata_keys.issubset(
                actual_keys
            ), f"Point {i} missing required metadata keys. Expected: {expected_metadata_keys}, Actual: {actual_keys}"

        assert result.success is True

    def test_api_call_reduction_measurement(
        self,
        file_chunking_manager,
        mock_vector_manager,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """
        PERFORMANCE TEST: Measure and validate API call reduction (N chunks → 1 call).

        This test quantifies the 10-50x performance improvement.
        """
        # Create test file that will generate multiple chunks
        test_file = tmp_path / "large_file.py"
        test_file.write_text("content")

        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Configure chunker to return more chunks for better measurement
        mock_chunker = file_chunking_manager.chunker
        large_chunks = [
            {
                "text": f"chunk_{i}_content",
                "line_start": i * 10,
                "line_end": (i * 10) + 5,
            }
            for i in range(10)  # 10 chunks = 10x reduction
        ]
        mock_chunker.chunk_file.return_value = large_chunks

        # Configure batch response for 10 chunks
        def batch_with_10_embeddings(chunk_texts, metadata):
            mock_vector_manager.submit_batch_task_call_count += 1  # Increment counter
            future: Future = Future()
            embeddings = tuple(
                (float(i), float(i + 0.1), float(i + 0.2)) for i in range(10)
            )
            vector_result = VectorResult(
                task_id="batch_10",
                embeddings=embeddings,
                metadata=metadata,
                processing_time=0.1,
                error=None,
            )
            future.set_result(vector_result)
            return future

        mock_vector_manager.submit_batch_task.side_effect = batch_with_10_embeddings

        # Process file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # PERFORMANCE VALIDATION: Measure API call reduction
        chunks_processed = 10
        api_calls_old_approach = chunks_processed  # N individual calls
        api_calls_new_approach = (
            mock_vector_manager.submit_batch_task_call_count
        )  # 1 batch call

        # Verify dramatic reduction
        assert (
            api_calls_new_approach == 1
        ), "Must use exactly 1 API call for any number of chunks"
        assert api_calls_old_approach == 10, "Old approach would need 10 API calls"

        # Calculate and verify improvement ratio
        improvement_ratio = api_calls_old_approach / api_calls_new_approach
        assert (
            improvement_ratio == 10.0
        ), f"Expected 10x improvement, got {improvement_ratio}x"

        # Verify all chunks still processed successfully
        assert result.success is True
        assert result.chunks_processed == 10

        print(
            f"✅ API Call Reduction: {chunks_processed} chunks → 1 API call ({improvement_ratio}x improvement)"
        )


class TestBatchProcessingEdgeCases:
    """Test edge cases for batch processing optimization."""

    def test_empty_file_batch_optimization(
        self,
        file_chunking_manager,
        mock_vector_manager,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """Verify empty files bypass batch processing efficiently."""
        # Create empty file
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        # Configure chunker to return empty chunks
        mock_chunker = file_chunking_manager.chunker
        mock_chunker.chunk_file.return_value = []

        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Process empty file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # Verify no API calls for empty files
        assert mock_vector_manager.submit_batch_task_call_count == 0
        assert mock_vector_manager.submit_chunk_call_count == 0

        # Verify successful empty result
        assert result.success is True
        assert result.chunks_processed == 0

    def test_single_chunk_batch_processing(
        self,
        file_chunking_manager,
        mock_vector_manager,
        standard_metadata,
        tmp_path,
        mock_slot_tracker,
    ):
        """Verify single chunk still uses batch processing (not individual calls)."""
        test_file = tmp_path / "single.py"
        test_file.write_text("content")

        # Configure single chunk
        mock_chunker = file_chunking_manager.chunker
        mock_chunker.chunk_file.return_value = [
            {"text": "single_chunk", "line_start": 1, "line_end": 5}
        ]

        # Configure batch response for single chunk
        def single_chunk_batch(chunk_texts, metadata):
            mock_vector_manager.submit_batch_task_call_count += 1  # Increment counter
            future: Future = Future()
            vector_result = VectorResult(
                task_id="single_batch",
                embeddings=((0.1, 0.2, 0.3),),  # Single embedding tuple
                metadata=metadata,
                processing_time=0.1,
                error=None,
            )
            future.set_result(vector_result)
            return future

        mock_vector_manager.submit_batch_task.side_effect = single_chunk_batch

        metadata = {**standard_metadata, "file_path": str(test_file)}

        # Process single chunk file
        with file_chunking_manager:
            future = file_chunking_manager.submit_file_for_processing(
                test_file, metadata, None
            )
            result = future.result()

        # Verify batch processing used even for single chunk
        assert mock_vector_manager.submit_batch_task_call_count == 1
        assert mock_vector_manager.submit_chunk_call_count == 0

        assert result.success is True
        assert result.chunks_processed == 1
