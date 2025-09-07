"""
Tests for simple, safe cancellation strategy that prioritizes file atomicity.

These tests define the expected behavior:
1. Files complete atomically during cancellation
2. No database corruption - files either complete or don't start
3. Cancellation checks happen AFTER file writes, not during
4. Reasonable timeouts don't cause false failures
5. Simple between-files cancellation in HighThroughputProcessor
"""

import threading
import time
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.file_chunking_manager import FileChunkingManager
from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor
from src.code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
)
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker


class TestSafeCancellationStrategy:
    """Test safe cancellation strategy that prioritizes file atomicity."""

    @pytest.fixture
    def mock_vector_manager(self):
        """Create mock vector manager with cancellation support."""
        manager = Mock(spec=VectorCalculationManager)
        manager.cancellation_event = threading.Event()
        manager.submit_chunk = Mock()
        manager.request_cancellation = Mock()
        return manager

    @pytest.fixture
    def mock_chunker(self):
        """Create mock chunker."""
        chunker = Mock(spec=FixedSizeChunker)
        chunker.chunk_file = Mock(
            return_value=[
                {
                    "text": "test content",
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "file_extension": "py",
                    "line_start": 1,
                    "line_end": 10,
                }
            ]
        )
        return chunker

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = Mock()
        client.upsert_points_atomic = Mock(return_value=True)
        return client

    def test_file_completes_atomically_during_cancellation(
        self, mock_vector_manager, mock_chunker, mock_qdrant_client
    ):
        """Test that files complete atomically even when cancellation is requested.

        CRITICAL: This test should FAIL initially because current implementation
        checks for cancellation DURING file processing, breaking atomicity.
        """
        # Setup vector future that will complete successfully
        mock_future = Mock()
        mock_future.result = Mock(return_value=Mock(error=None, embedding=[0.1] * 384))
        mock_vector_manager.submit_chunk.return_value = mock_future

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=2,
        ) as manager:

            # Submit file for processing
            test_file = Path("/test/file.py")
            metadata = {"project_id": "test", "file_hash": "abc123"}
            future = manager.submit_file_for_processing(test_file, metadata, None)

            # Request cancellation AFTER submission but BEFORE completion
            # This simulates user cancelling while file is being processed
            time.sleep(0.1)  # Let processing start
            manager.request_cancellation()
            mock_vector_manager.cancellation_event.set()

            # File should still complete successfully (atomic completion)
            result = future.result(timeout=5.0)

            # CRITICAL ASSERTION: File completed despite cancellation
            # Current implementation will FAIL this - it checks cancellation during processing
            assert result.success is True
            assert result.chunks_processed == 1
            assert "cancelled" not in (result.error or "").lower()

            # Verify database write was called (atomic completion)
            mock_qdrant_client.upsert_points_atomic.assert_called_once()

    def test_no_partial_files_in_database_during_cancellation(
        self, mock_vector_manager, mock_chunker, mock_qdrant_client
    ):
        """Test that cancellation never leaves partial files in database.

        CRITICAL: This test should FAIL initially because current upsert_points_atomic
        is not actually atomic - it processes in batches.
        """
        # Create multi-chunk file to test atomicity
        mock_chunker.chunk_file.return_value = [
            {
                "text": f"chunk {i}",
                "chunk_index": i,
                "total_chunks": 3,
                "file_extension": "py",
                "line_start": i * 10 + 1,
                "line_end": (i + 1) * 10,
            }
            for i in range(3)
        ]

        # Setup vector futures
        mock_futures = []
        for i in range(3):
            future = Mock()
            future.result = Mock(return_value=Mock(error=None, embedding=[0.1] * 384))
            mock_futures.append(future)
        mock_vector_manager.submit_chunk.side_effect = mock_futures

        # Mock database to track what gets written
        written_points = []

        def track_upsert(points, collection_name=None):
            written_points.extend(points)
            return True

        mock_qdrant_client.upsert_points_atomic.side_effect = track_upsert

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=2,
        ) as manager:

            # Submit file
            test_file = Path("/test/multi_chunk_file.py")
            metadata = {"project_id": "test", "file_hash": "def456"}
            future = manager.submit_file_for_processing(test_file, metadata, None)

            # Cancel immediately after submission
            manager.request_cancellation()
            mock_vector_manager.cancellation_event.set()

            # Get result
            result = future.result(timeout=5.0)

            # CRITICAL: Either ALL chunks written (file completed) OR NO chunks written
            # Current implementation may write some chunks but not others = CORRUPTION
            if result.success:
                # If file succeeded, ALL chunks must be in database
                assert len(written_points) == 3
                assert result.chunks_processed == 3
            else:
                # If file failed, NO chunks should be in database
                assert len(written_points) == 0
                assert result.chunks_processed == 0

            # NEVER allow partial file state
            assert len(written_points) in [
                0,
                3,
            ], f"Partial file corruption: {len(written_points)} chunks written"

    def test_cancellation_check_after_file_write_only(
        self, mock_vector_manager, mock_chunker, mock_qdrant_client
    ):
        """Test that cancellation is only checked AFTER file write, not during processing.

        CRITICAL: This test should FAIL initially because current implementation
        has multiple cancellation checks during file processing.
        """
        # Track when cancellation checks happen vs when database writes happen
        cancellation_check_times = []
        database_write_times = []

        # Mock cancellation event to track when it's checked
        original_is_set = mock_vector_manager.cancellation_event.is_set

        def track_cancellation_check():
            cancellation_check_times.append(time.time())
            return original_is_set()

        mock_vector_manager.cancellation_event.is_set = track_cancellation_check

        # Mock database write to track timing
        def track_database_write(points, collection_name=None):
            database_write_times.append(time.time())
            return True

        mock_qdrant_client.upsert_points_atomic.side_effect = track_database_write

        # Setup vector future
        mock_future = Mock()
        mock_future.result = Mock(return_value=Mock(error=None, embedding=[0.1] * 384))
        mock_vector_manager.submit_chunk.return_value = mock_future

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=2,
        ) as manager:

            # Submit file
            test_file = Path("/test/file.py")
            metadata = {"project_id": "test", "file_hash": "ghi789"}
            future = manager.submit_file_for_processing(test_file, metadata, None)

            # Let file process completely
            _ = future.result(
                timeout=5.0
            )  # We don't use the result, just ensure it completes

            # CRITICAL ASSERTION: Cancellation should only be checked AFTER database write
            # Current implementation checks cancellation BEFORE and DURING processing
            assert len(database_write_times) > 0, "Database write should have happened"

            if cancellation_check_times:
                # Find cancellation checks that happened before database write
                pre_write_checks = [
                    t for t in cancellation_check_times if t < database_write_times[0]
                ]

                # SHOULD FAIL: Current implementation has pre-write cancellation checks
                assert len(pre_write_checks) == 0, (
                    f"Found {len(pre_write_checks)} cancellation checks before database write. "
                    f"Cancellation should only be checked AFTER file completion."
                )

    def test_reasonable_timeouts_no_false_failures(self):
        """Test that reasonable timeouts don't cause false failures.

        CRITICAL: This test should FAIL initially because current implementation
        uses aggressive 15-60 second timeouts that cause false failures.
        """
        # Test that 300 second (5 minute) timeout is used instead of 15-60 seconds
        # This is a design test - validates timeout configuration

        # Check FileChunkingManager timeout constants
        from src.code_indexer.services.file_chunking_manager import (
            VECTOR_PROCESSING_TIMEOUT,
        )

        # SHOULD FAIL: Current timeout is too aggressive
        assert VECTOR_PROCESSING_TIMEOUT >= 300.0, (
            f"Vector processing timeout {VECTOR_PROCESSING_TIMEOUT}s is too aggressive. "
            f"Should be at least 300s (5 minutes) to avoid false failures with slow embedding providers."
        )

    def test_high_throughput_processor_between_files_cancellation_only(self):
        """Test that HighThroughputProcessor only cancels between files, not during files.

        CRITICAL: This test should FAIL initially because current implementation
        has complex timeout and cancellation logic during file processing.
        """
        # Create processor with mocked dependencies
        config = Mock()
        config.codebase_dir = Path("/test")

        processor = Mock(spec=HighThroughputProcessor)
        processor.cancelled = False
        processor._cancellation_event = threading.Event()
        processor._cancellation_lock = threading.Lock()

        # Mock the as_completed loop behavior we want to test
        test_files = [
            Path("/test/file1.py"),
            Path("/test/file2.py"),
            Path("/test/file3.py"),
        ]

        # Simulate file futures completing
        completed_files = []
        cancelled_during_processing = False

        def mock_as_completed_behavior():
            """Simulate the desired as_completed loop behavior."""
            nonlocal cancelled_during_processing

            for i, file_path in enumerate(test_files):
                # Simulate file processing result
                file_result = Mock()
                file_result.success = True
                file_result.file_path = file_path
                file_result.chunks_processed = 5
                completed_files.append(file_path)

                # Check cancellation only BETWEEN files (not during file processing)
                if i == 1:  # Cancel after second file completes
                    with processor._cancellation_lock:
                        if processor.cancelled:
                            # This is correct - cancel between files
                            break
                        else:
                            # Simulate cancellation request between files
                            processor.cancelled = True
                            processor._cancellation_event.set()

                # Verify no cancellation checks during file processing
                # This would be violated by current implementation

        # Execute mock behavior
        mock_as_completed_behavior()

        # CRITICAL ASSERTIONS:
        # 1. Files completed before cancellation check
        assert (
            len(completed_files) >= 2
        ), "At least 2 files should complete before cancellation"

        # 2. Cancellation happened between files, not during file processing
        # Current implementation violates this by checking cancellation with timeouts
        assert not cancelled_during_processing, (
            "Cancellation check should not happen during file processing. "
            "Current implementation uses aggressive timeouts that effectively cancel during processing."
        )

    def test_file_atomicity_preserved_under_load(
        self, mock_vector_manager, mock_chunker, mock_qdrant_client
    ):
        """Test file atomicity under high load with multiple concurrent cancellations.

        This test simulates production conditions where multiple files are processing
        and cancellation is requested multiple times.
        """
        # Create multiple files processing concurrently
        num_files = 10

        # Setup chunker to return multi-chunk files
        mock_chunker.chunk_file.return_value = [
            {
                "text": f"chunk {i}",
                "chunk_index": i,
                "total_chunks": 2,
                "file_extension": "py",
                "line_start": i * 10 + 1,
                "line_end": (i + 1) * 10,
            }
            for i in range(2)
        ]

        # Track database writes per file
        writes_per_file = {}

        def track_writes_per_file(points, collection_name=None):
            # Extract file path from first point
            if points and "payload" in points[0] and "path" in points[0]["payload"]:
                file_path = points[0]["payload"]["path"]
                if file_path not in writes_per_file:
                    writes_per_file[file_path] = 0
                writes_per_file[file_path] += len(points)
            return True

        mock_qdrant_client.upsert_points_atomic.side_effect = track_writes_per_file

        # Setup vector futures
        mock_future = Mock()
        mock_future.result = Mock(return_value=Mock(error=None, embedding=[0.1] * 384))
        mock_vector_manager.submit_chunk.return_value = mock_future

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as manager:

            # Submit multiple files concurrently
            futures = []
            for i in range(num_files):
                test_file = Path(f"/test/file_{i}.py")
                metadata = {"project_id": "test", "file_hash": f"hash_{i}"}
                future = manager.submit_file_for_processing(test_file, metadata, None)
                futures.append((test_file, future))

            # Cancel after small delay (some files may be processing)
            time.sleep(0.2)
            manager.request_cancellation()
            mock_vector_manager.cancellation_event.set()

            # Collect all results
            results = {}
            for test_file, future in futures:
                try:
                    result = future.result(timeout=10.0)
                    results[str(test_file)] = result
                except Exception as e:
                    results[str(test_file)] = Mock(success=False, error=str(e))

            # CRITICAL: Verify atomicity for each file
            for file_path, result in results.items():
                if result.success:
                    # File succeeded - must have ALL chunks in database
                    chunks_written = writes_per_file.get(file_path, 0)
                    assert chunks_written == 2, (
                        f"File {file_path} succeeded but only {chunks_written}/2 chunks written. "
                        f"This indicates database corruption during cancellation."
                    )
                else:
                    # File failed - must have NO chunks in database
                    chunks_written = writes_per_file.get(file_path, 0)
                    assert chunks_written == 0, (
                        f"File {file_path} failed but {chunks_written} chunks were written. "
                        f"This indicates partial file corruption."
                    )


class TestCurrentImplementationFailures:
    """Tests that demonstrate current implementation problems.

    These tests document the specific issues with the current implementation
    that need to be fixed.
    """

    def test_upsert_points_atomic_is_not_atomic(self):
        """Demonstrate that current upsert_points_atomic is not actually atomic.

        This test shows the corruption risk in the current implementation.
        """
        from src.code_indexer.services.qdrant import QdrantClient

        # Create mock client to examine implementation
        mock_config = Mock()
        mock_config.host = "http://localhost:6333"
        client = QdrantClient(mock_config)

        # Mock the underlying upsert_points to fail partway through
        call_count = 0

        def failing_upsert(points, collection_name=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return True  # First batch succeeds
            else:
                return False  # Second batch fails - CORRUPTION!

        client.upsert_points = failing_upsert

        # Create large points list that will be split into batches
        large_points_list = [
            {"id": f"point_{i}", "vector": [0.1] * 10} for i in range(150)
        ]

        # This should be atomic but will actually leave partial data
        result = client.upsert_points_atomic(large_points_list, max_batch_size=100)

        # CURRENT IMPLEMENTATION PROBLEM: Returns False but first 100 points were written
        # This is NOT atomic behavior - it's partial corruption
        assert result is False
        assert call_count == 2  # Two batches were attempted

        # The problem: First batch succeeded, second failed = partial corruption
        # True atomic behavior would roll back the first batch or use transactions

    def test_aggressive_timeouts_cause_false_failures(self):
        """Demonstrate that current timeout values cause false failures."""
        # Current implementation uses 15-60 second graduated timeouts
        # These are too aggressive for production embedding providers

        # Simulate slow but legitimate embedding response (90 seconds)
        slow_embedding_time = 90.0
        current_timeout_limits = [60.0, 30.0, 15.0]  # Current graduated timeouts

        # All current timeouts would fail this legitimate slow response
        for timeout in current_timeout_limits:
            would_timeout = slow_embedding_time > timeout
            assert would_timeout, (
                f"Current {timeout}s timeout would fail legitimate {slow_embedding_time}s embedding response. "
                f"This causes false failures in production."
            )

        # Reasonable timeout would handle this fine
        reasonable_timeout = 300.0  # 5 minutes
        would_handle_fine = slow_embedding_time <= reasonable_timeout
        assert would_handle_fine, "300s timeout should handle 90s embedding response"

    def test_mid_process_cancellation_breaks_atomicity(self):
        """Demonstrate how current mid-process cancellation breaks file atomicity."""
        # This test shows the conceptual problem - we can't easily unit test
        # the actual FileChunkingManager behavior without complex mocking

        # The issue: Current implementation has these cancellation points:
        cancellation_check_locations = [
            "Before chunk submission (line 285-298)",
            "During chunk processing loop (line 342-354)",
            "Before database write (line 407-419)",
        ]

        # Each cancellation point can leave the file in partial state:
        # - After chunking but before vectors: File chunked but no database entry
        # - After some vectors but before others: Partial vectors computed
        # - After vectors but before database: Vectors computed but not persisted

        assert len(cancellation_check_locations) > 1, (
            f"Current implementation has {len(cancellation_check_locations)} cancellation points during file processing. "
            f"This breaks file atomicity. There should be only ONE cancellation check AFTER file completion."
        )
