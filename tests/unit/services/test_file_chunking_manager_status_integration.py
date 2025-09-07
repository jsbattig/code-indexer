"""
Test FileChunkingManager integration with ConsolidatedFileTracker for status reporting.

This test module validates the surgical restoration of status reporting system:
1. FileTracker integration with FileChunkingManager
2. File status progression throughout lifecycle
3. Proper cancellation handling without error spam
"""

import threading
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.file_chunking_manager import FileChunkingManager
from code_indexer.services.consolidated_file_tracker import (
    ConsolidatedFileTracker,
    FileStatus,
)


class TestFileChunkingManagerStatusIntegration:
    """Test FileChunkingManager integration with status tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_vector_manager = Mock()
        self.mock_vector_manager.cancellation_event = threading.Event()
        self.mock_chunker = Mock()
        self.mock_qdrant_client = Mock()

        # Create real file tracker for integration testing
        self.file_tracker = ConsolidatedFileTracker(max_concurrent_files=4)

        # Create temporary test file
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        )
        self.temp_file.write("test content")
        self.temp_file.close()
        self.test_file = Path(self.temp_file.name)

        # Test metadata
        self.test_metadata = {
            "project_id": "test_project",
            "file_hash": "abc123",
            "git_available": False,
            "file_mtime": 1234567890.0,
            "file_size": 1000,
        }

    def teardown_method(self):
        """Clean up test fixtures."""
        # Remove temporary file
        if self.test_file.exists():
            os.unlink(self.test_file)

    def test_file_chunking_manager_accepts_file_tracker_parameter(self):
        """Test that FileChunkingManager constructor accepts file_tracker parameter."""
        # Test should now PASS since the parameter has been implemented

        # Constructor should accept file_tracker parameter
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,  # This parameter should be accepted
        )

        # Verify file_tracker was assigned
        assert manager.file_tracker is self.file_tracker

        # Verify thread management fields are initialized
        assert hasattr(manager, "_thread_counter")
        assert hasattr(manager, "_thread_lock")
        assert manager._thread_counter == 0

    def test_file_status_progression_lifecycle(self):
        """Test file status progression through complete lifecycle."""
        # This test should FAIL initially since status updates are not implemented

        # Mock successful processing
        self.mock_chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]

        # Mock successful vector processing
        mock_future = Mock()
        mock_vector_result = Mock()
        mock_vector_result.error = None
        mock_vector_result.embedding = [0.1, 0.2, 0.3]
        mock_future.result.return_value = mock_vector_result

        self.mock_vector_manager.submit_chunk.return_value = mock_future
        self.mock_qdrant_client.upsert_points_atomic.return_value = True

        # Create FileChunkingManager (this will fail until constructor is updated)
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,  # Should be accepted after implementation
        )

        # Track status changes
        status_updates = []
        original_update = self.file_tracker.update_file_status

        def track_status_updates(thread_id, status):
            status_updates.append((thread_id, status))
            original_update(thread_id, status)

        self.file_tracker.update_file_status = track_status_updates

        # Process file and track status progression
        with manager:
            future = manager.submit_file_for_processing(
                self.test_file, self.test_metadata, None
            )
            result = future.result(timeout=5.0)

        # Verify successful processing
        assert result.success is True

        # FAILING ASSERTION: Status progression should be tracked
        # Expected: STARTING -> PROCESSING -> COMPLETING -> COMPLETE
        expected_statuses = [
            FileStatus.STARTING,
            FileStatus.PROCESSING,
            FileStatus.COMPLETING,
            FileStatus.COMPLETE,
        ]

        actual_statuses = [status for _, status in status_updates]
        assert actual_statuses == expected_statuses, (
            f"Expected status progression {expected_statuses}, "
            f"but got {actual_statuses}"
        )

    def test_cancellation_handling_cleanup(self):
        """Test proper cancellation handling with file tracker cleanup."""
        # This test should FAIL initially since cancellation handling is not implemented

        # Mock cancellation scenario
        self.mock_vector_manager.cancellation_event.set()  # Signal cancellation

        self.mock_chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]

        # Create FileChunkingManager with file tracker
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,
        )

        # Process file during cancellation
        with manager:
            future = manager.submit_file_for_processing(
                self.test_file, self.test_metadata, None
            )
            result = future.result(timeout=5.0)

        # FAILING ASSERTION: Should handle cancellation gracefully
        assert result.success is False
        assert "cancelled" in result.error.lower()

        # FAILING ASSERTION: File tracker should be cleaned up after delay
        # ConsolidatedFileTracker has a 3-second cleanup delay for completed files
        time.sleep(3.1)  # Wait for automatic cleanup
        active_count = self.file_tracker.get_active_file_count()
        assert (
            active_count == 0
        ), f"Expected 0 active files after cancellation, got {active_count}"

    def test_thread_pool_shutdown_error_handling(self):
        """Test handling of 'Thread pool not started' error without spam."""
        # This test should FAIL initially since error handling is not implemented

        # Mock RuntimeError during chunk submission
        self.mock_chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]

        # Mock thread pool shutdown error
        self.mock_vector_manager.submit_chunk.side_effect = RuntimeError(
            "Thread pool not started"
        )

        # Create FileChunkingManager with file tracker
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,
        )

        # Process file with thread pool shutdown
        with manager:
            future = manager.submit_file_for_processing(
                self.test_file, self.test_metadata, None
            )
            result = future.result(timeout=5.0)

        # FAILING ASSERTION: Should handle shutdown gracefully
        assert result.success is False
        assert "cancelled" in result.error.lower()

        # FAILING ASSERTION: Should clean up file tracker after delay
        time.sleep(3.1)  # Wait for automatic cleanup
        active_count = self.file_tracker.get_active_file_count()
        assert (
            active_count == 0
        ), f"Expected 0 active files after shutdown, got {active_count}"

    def test_thread_id_assignment_and_tracking(self):
        """Test thread ID assignment and file tracking integration."""
        # This test should FAIL initially since thread ID management is not implemented

        # Mock successful processing for multiple files
        self.mock_chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]

        mock_future = Mock()
        mock_vector_result = Mock()
        mock_vector_result.error = None
        mock_vector_result.embedding = [0.1, 0.2, 0.3]
        mock_future.result.return_value = mock_vector_result

        self.mock_vector_manager.submit_chunk.return_value = mock_future
        self.mock_qdrant_client.upsert_points_atomic.return_value = True

        # Create FileChunkingManager with file tracker
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,
        )

        # Track file tracker calls
        start_calls = []
        complete_calls = []

        original_start = self.file_tracker.start_file_processing
        original_complete = self.file_tracker.complete_file_processing

        def track_start_calls(thread_id, file_path, file_size=None):
            start_calls.append((thread_id, file_path))
            original_start(thread_id, file_path, file_size)

        def track_complete_calls(thread_id):
            complete_calls.append(thread_id)
            original_complete(thread_id)

        self.file_tracker.start_file_processing = track_start_calls
        self.file_tracker.complete_file_processing = track_complete_calls

        # Create additional temporary files for multiple file test
        temp_files = []
        for i in range(2):
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_test_{i}.py", delete=False
            )
            temp_file.write(f"test content {i}")
            temp_file.close()
            temp_files.append(Path(temp_file.name))

        test_files = temp_files

        with manager:
            futures = []
            for file_path in test_files:
                future = manager.submit_file_for_processing(
                    file_path, self.test_metadata, None
                )
                futures.append(future)

            # Wait for all files to complete
            results = [future.result(timeout=5.0) for future in futures]

        # Verify all files processed successfully
        assert all(result.success for result in results)

        # FAILING ASSERTION: Each file should get unique thread ID
        thread_ids = [thread_id for thread_id, _ in start_calls]
        assert len(set(thread_ids)) == len(
            test_files
        ), "Each file should get unique thread ID"

        # FAILING ASSERTION: Start and complete calls should match
        assert len(start_calls) == len(test_files)
        assert len(complete_calls) == len(test_files)
        assert set(thread_ids) == set(complete_calls)

        # Clean up additional temp files
        for temp_file in temp_files:
            if temp_file.exists():
                os.unlink(temp_file)

    @patch("code_indexer.services.file_chunking_manager.logger")
    def test_error_handling_with_file_tracker_cleanup(self, mock_logger):
        """Test error handling ensures file tracker cleanup."""
        # This test should FAIL initially since error cleanup is not implemented

        # Mock chunking failure
        self.mock_chunker.chunk_file.side_effect = Exception("Chunking failed")

        # Create FileChunkingManager with file tracker
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=self.file_tracker,
        )

        # Process file with error
        with manager:
            future = manager.submit_file_for_processing(
                self.test_file, self.test_metadata, None
            )
            result = future.result(timeout=5.0)

        # Verify error handling
        assert result.success is False
        assert "chunking failed" in result.error.lower()

        # FAILING ASSERTION: File tracker should be cleaned up even on error after delay
        time.sleep(3.1)  # Wait for automatic cleanup
        active_count = self.file_tracker.get_active_file_count()
        assert (
            active_count == 0
        ), f"Expected 0 active files after error, got {active_count}"

    def test_file_tracker_none_handling(self):
        """Test FileChunkingManager works when file_tracker is None."""
        # This test should FAIL initially since the optional parameter handling is not implemented

        # Mock successful processing
        self.mock_chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]

        mock_future = Mock()
        mock_vector_result = Mock()
        mock_vector_result.error = None
        mock_vector_result.embedding = [0.1, 0.2, 0.3]
        mock_future.result.return_value = mock_vector_result

        self.mock_vector_manager.submit_chunk.return_value = mock_future
        self.mock_qdrant_client.upsert_points_atomic.return_value = True

        # Create FileChunkingManager WITHOUT file_tracker
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
            file_tracker=None,  # Should be handled gracefully
        )

        # Process file without file tracker
        with manager:
            future = manager.submit_file_for_processing(
                self.test_file, self.test_metadata, None
            )
            result = future.result(timeout=5.0)

        # FAILING ASSERTION: Should work without file tracker
        assert result.success is True
        assert result.chunks_processed == 1
