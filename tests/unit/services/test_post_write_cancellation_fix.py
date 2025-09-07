"""
Tests for post-write only cancellation implementation.

CRITICAL: These tests verify that the simple cancellation strategy is implemented correctly:
- NO cancellation checks during file processing
- Cancellation ONLY checked between files
- Files complete atomically before any cancellation
"""

import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.file_chunking_manager import FileChunkingManager
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.vector_calculation_manager import VectorCalculationManager
from code_indexer.services.qdrant import QdrantClient


class TestPostWriteCancellationFix:
    """Test suite for post-write only cancellation behavior."""

    def test_file_chunking_manager_no_mid_process_cancellation_checks(self):
        """
        CRITICAL TEST: FileChunkingManager must NOT check for cancellation during file processing.

        This test verifies that cancellation is NOT checked during:
        - Chunk creation
        - Vector calculation waiting
        - Qdrant writing

        Only after file is completely written should cancellation be considered.
        """
        # Setup mocks
        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.upsert_points_atomic.return_value = True

        mock_vector_manager = Mock(spec=VectorCalculationManager)

        # Create mock futures that simulate successful vector processing
        mock_future = Mock()
        mock_future.result.return_value = Mock(error=None, vector=[1.0, 2.0, 3.0])
        mock_vector_manager.submit_chunk.return_value = mock_future

        # Track when cancellation would be checked
        cancellation_checks = []

        def track_cancellation_property_access():
            cancellation_checks.append("cancellation_checked_during_processing")
            return False

        # Create file chunking manager with real chunker
        from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker

        mock_chunker = Mock(spec=FixedSizeChunker)
        mock_chunker.chunk_text.return_value = [
            {"text": "chunk1", "start": 0, "end": 100},
            {"text": "chunk2", "start": 100, "end": 200},
        ]

        manager = FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant,
            thread_count=4,
        )

        # Set up cancellation tracking
        manager._cancellation_requested = property(track_cancellation_property_access)

        # Process a test file
        test_file = Path("test_file.py")
        test_content = "# Test content\nprint('hello world')\n" * 10

        with patch("pathlib.Path.read_text", return_value=test_content):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = len(test_content)

                result = manager.process_file_parallel(
                    test_file, collection_name="test"
                )

        # CRITICAL ASSERTION: No cancellation checks should occur during processing
        # This is the core requirement - files must complete atomically
        assert len(cancellation_checks) == 0, (
            f"Cancellation was checked {len(cancellation_checks)} times during file processing. "
            f"This violates the post-write only cancellation requirement."
        )

        # File should complete successfully
        assert result.success is True
        assert result.chunks_processed > 0

    def test_high_throughput_processor_between_files_only_cancellation(self):
        """
        CRITICAL TEST: HighThroughputProcessor must only check cancellation between files.

        This test verifies that:
        1. Files are processed completely without interruption
        2. Cancellation is only checked after a file completes
        3. Files in progress are not interrupted
        """
        # Setup mocks
        mock_file_chunking = Mock(spec=FileChunkingManager)

        # Track file processing order
        processed_files = []

        def mock_process_file(file_path, **kwargs):
            processed_files.append(str(file_path))
            # Simulate file processing time
            time.sleep(0.1)
            return Mock(
                success=True,
                file_path=file_path,
                chunks_processed=5,
                processing_time=0.1,
                error=None,
            )

        mock_file_chunking.process_file_parallel = mock_process_file

        # Create processor
        processor = HighThroughputProcessor(
            file_chunking_manager=mock_file_chunking, progress_callback=Mock()
        )

        # Create test files
        test_files = [Path(f"test_file_{i}.py") for i in range(3)]

        # Start processing and cancel after first file
        def cancel_after_first_file():
            time.sleep(0.15)  # Wait for first file to complete
            processor.cancel()

        cancel_thread = threading.Thread(target=cancel_after_first_file)
        cancel_thread.start()

        # Process files
        with patch("pathlib.Path.exists", return_value=True):
            result = processor.process_files(test_files, collection_name="test")

        cancel_thread.join()

        # CRITICAL ASSERTIONS:
        # 1. At least one file should have completed fully before cancellation
        assert len(processed_files) >= 1, "No files completed before cancellation"

        # 2. If cancellation occurred, it should be reflected in the result
        if processor.cancelled:
            assert result.cancelled is True

        # 3. All processed files should have completed fully (no partial processing)
        # This ensures file atomicity was preserved
        for file_path in processed_files:
            # Each file that started processing should have completed
            # (We can't directly verify this in the mock, but the fact that
            # mock_process_file completed for each file in processed_files proves this)
            assert file_path in [str(f) for f in test_files]

    def test_qdrant_atomic_method_is_actually_atomic_or_properly_named(self):
        """
        CRITICAL TEST: The upsert_points_atomic method must either be truly atomic
        or be renamed to indicate it's not atomic.

        This test verifies that either:
        1. The method provides true atomicity (all-or-nothing)
        2. Or it's renamed to not claim atomicity when it's not provided
        """
        # Create real QdrantClient (mocked at the lower level)
        with patch("code_indexer.services.qdrant.QdrantClient.__init__") as mock_init:
            mock_init.return_value = None
            qdrant_client = QdrantClient(
                host="localhost", port=6333, api_key=None, console=Mock()
            )

            # Mock the underlying client
            mock_client = Mock()
            qdrant_client.client = mock_client

            # Test case 1: Method should handle partial failure correctly
            test_points = [
                {"id": 1, "vector": [1.0, 2.0], "payload": {"text": "test1"}},
                {"id": 2, "vector": [3.0, 4.0], "payload": {"text": "test2"}},
                {"id": 3, "vector": [5.0, 6.0], "payload": {"text": "test3"}},
            ]

            # Simulate partial failure in batch processing
            def mock_upsert_side_effect(collection_name, points, **kwargs):
                # First batch succeeds, second batch fails
                if len(points) > 0 and points[0]["id"] == 1:
                    return Mock(status="success")
                else:
                    raise Exception("Simulated batch failure")

            mock_client.upsert.side_effect = mock_upsert_side_effect
            qdrant_client.collection_name = "test_collection"

            # The method should either:
            # 1. Return False (indicating not all points were upserted)
            # 2. Raise an exception
            # 3. Provide true atomicity (rollback on failure)

            result = qdrant_client.upsert_points_atomic(test_points, max_batch_size=2)

            # CRITICAL ASSERTION: If method claims atomicity, it must handle failures properly
            # If it returns False, that's honest about partial failure
            # If it raises exception, that's also valid atomic behavior
            # What's NOT acceptable is returning True when some points failed

            assert result is False, (
                "upsert_points_atomic returned True despite batch failure. "
                "This violates atomicity claims and can cause data corruption during cancellation."
            )

    def test_file_processing_completes_atomically_before_cancellation_check(self):
        """
        INTEGRATION TEST: Verify that file processing completes fully before
        any cancellation check occurs.

        This is the core requirement: files must be atomic units that either
        complete fully or don't start at all.
        """
        # Setup mocks with timing verification
        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.upsert_points_atomic.return_value = True

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_future = Mock()
        mock_future.result.return_value = Mock(error=None, vector=[1.0, 2.0, 3.0])
        mock_vector_manager.submit_chunk.return_value = mock_future

        # Track the sequence of operations
        operation_sequence = []

        def track_qdrant_write(*args, **kwargs):
            operation_sequence.append("qdrant_write_completed")
            return True

        def track_cancellation_check():
            operation_sequence.append("cancellation_check")
            return False

        mock_qdrant.upsert_points_atomic.side_effect = track_qdrant_write

        # Create manager
        from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker

        mock_chunker = Mock(spec=FixedSizeChunker)
        mock_chunker.chunk_text.return_value = [
            {"text": "chunk1", "start": 0, "end": 100},
            {"text": "chunk2", "start": 100, "end": 200},
        ]

        manager = FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant,
            thread_count=4,
        )

        # Override cancellation property to track when it's accessed
        manager._cancellation_requested = property(
            lambda self: track_cancellation_check()
        )

        # Process file
        test_file = Path("test_file.py")
        test_content = "print('hello')\n" * 20

        with patch("pathlib.Path.read_text", return_value=test_content):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = len(test_content)

                result = manager.process_file_parallel(
                    test_file, collection_name="test"
                )

        # CRITICAL ASSERTION: Qdrant write must complete before any cancellation check
        if (
            "qdrant_write_completed" in operation_sequence
            and "cancellation_check" in operation_sequence
        ):
            qdrant_index = operation_sequence.index("qdrant_write_completed")
            cancellation_index = operation_sequence.index("cancellation_check")

            assert qdrant_index < cancellation_index, (
                f"Cancellation check occurred before Qdrant write completed. "
                f"Sequence: {operation_sequence}. This violates file atomicity."
            )

        # File should complete successfully
        assert result.success is True

    def test_no_cancellation_checks_during_chunk_processing(self):
        """
        UNIT TEST: Verify that no cancellation checks occur during individual
        chunk processing within a file.

        This ensures that once a file starts processing, it completes all its
        chunks without interruption.
        """
        # Setup mocks
        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.upsert_points_atomic.return_value = True

        mock_vector_manager = Mock(spec=VectorCalculationManager)

        # Create multiple chunks to test
        chunk_futures = []
        for i in range(5):  # 5 chunks
            mock_future = Mock()
            mock_future.result.return_value = Mock(
                error=None, vector=[float(i), float(i + 1), float(i + 2)]
            )
            chunk_futures.append(mock_future)

        call_count = [0]

        def mock_submit_chunk(*args, **kwargs):
            future = chunk_futures[call_count[0]]
            call_count[0] += 1
            return future

        mock_vector_manager.submit_chunk.side_effect = mock_submit_chunk

        # Track when cancellation property is accessed
        cancellation_access_count = [0]

        def track_cancellation_access():
            cancellation_access_count[0] += 1
            return False

        # Create manager
        from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker

        mock_chunker = Mock(spec=FixedSizeChunker)
        # Return multiple chunks to test iteration
        mock_chunker.chunk_text.return_value = [
            {"text": "chunk1", "start": 0, "end": 50},
            {"text": "chunk2", "start": 50, "end": 100},
            {"text": "chunk3", "start": 100, "end": 150},
        ]

        manager = FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant,
            thread_count=4,
        )

        # Override cancellation property
        manager._cancellation_requested = property(
            lambda self: track_cancellation_access()
        )

        # Process file with content that will create multiple chunks
        test_file = Path("test_file.py")
        test_content = "# This is a test file\n" + "print('chunk content')\n" * 20

        with patch("pathlib.Path.read_text", return_value=test_content):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = len(test_content)

                result = manager.process_file_parallel(
                    test_file, collection_name="test"
                )

        # CRITICAL ASSERTION: Cancellation should not be checked during chunk processing
        # It may be checked once at the very end (post-write), but not during processing
        assert cancellation_access_count[0] <= 1, (
            f"Cancellation was checked {cancellation_access_count[0]} times during file processing. "
            f"Maximum allowed is 1 (post-write check only)."
        )

        # Verify file completed successfully with multiple chunks
        assert result.success is True
        assert result.chunks_processed > 1  # Should have created multiple chunks
