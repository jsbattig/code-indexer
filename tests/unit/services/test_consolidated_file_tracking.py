"""
Tests for consolidated file tracking system.

Tests the unified file tracking system that consolidates FileLineTracker,
ConcurrentFileDisplay, and HighThroughputProcessor._active_threads into
a single, thread-safe solution.
"""

import time
import threading
from pathlib import Path
from unittest.mock import patch

from code_indexer.services.consolidated_file_tracker import (
    ConsolidatedFileTracker,
    FileStatus,
)


class TestConsolidatedFileTracker:
    """Test suite for ConsolidatedFileTracker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = ConsolidatedFileTracker(max_concurrent_files=8)
        self.test_file1 = Path("/test/file1.py")
        self.test_file2 = Path("/test/file2.py")
        self.test_file3 = Path("/test/file3.py")

    def test_start_file_processing_basic(self):
        """Test basic file processing start."""
        thread_id = 1
        file_size = 1024

        self.tracker.start_file_processing(thread_id, self.test_file1, file_size)

        # Should have one active file
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 1

        file_data = active_files[0]
        assert file_data["thread_id"] == thread_id
        assert file_data["file_path"] == str(self.test_file1)
        assert file_data["file_size"] == file_size
        assert file_data["status"] == FileStatus.STARTING.value

    def test_concurrent_file_limit_enforcement(self):
        """Test that max_concurrent_files limit is enforced."""
        # Start 10 files but tracker only supports 8
        for i in range(10):
            self.tracker.start_file_processing(i, Path(f"/test/file{i}.py"), 1024)

        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 8  # Limited to max_concurrent_files

        # Should have files 2-9 (oldest 0-1 removed to make room)
        thread_ids = [f["thread_id"] for f in active_files]
        assert thread_ids == list(range(2, 10))

    def test_thread_safety_concurrent_access(self):
        """Test thread safety with concurrent access."""
        results = []
        errors = []

        def worker_thread(thread_id):
            try:
                self.tracker.start_file_processing(
                    thread_id, Path(f"/test/file{thread_id}.py"), 1024 * thread_id
                )
                time.sleep(0.01)  # Small delay
                self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)
                results.append(thread_id)
            except Exception as e:
                errors.append(e)

        # Start 20 concurrent threads
        threads = []
        for i in range(20):
            t = threading.Thread(target=worker_thread, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0
        assert len(results) == 20

        # Should respect max concurrent limit
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 8

    def test_file_status_updates(self):
        """Test file status updates."""
        thread_id = 1
        self.tracker.start_file_processing(thread_id, self.test_file1, 1024)

        # Update to processing
        self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)
        active_files = self.tracker.get_concurrent_files_data()
        assert active_files[0]["status"] == FileStatus.PROCESSING.value

        # Update to completing
        self.tracker.update_file_status(thread_id, FileStatus.COMPLETING)
        active_files = self.tracker.get_concurrent_files_data()
        assert active_files[0]["status"] == FileStatus.COMPLETING.value

    def test_file_completion_with_cleanup_delay(self):
        """Test file completion with proper cleanup delay."""
        thread_id = 1
        self.tracker.start_file_processing(thread_id, self.test_file1, 1024)
        self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)

        # Complete the file
        self.tracker.complete_file_processing(thread_id)

        # Should still be visible immediately after completion
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 1
        assert active_files[0]["status"] == FileStatus.COMPLETE.value

        # PERFORMANCE FIX: Cleanup now happens in background thread
        # Wait for actual cleanup to occur (3 second delay + thread interval)
        time.sleep(4.0)
        
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 0

    def test_no_race_condition_in_cleanup(self):
        """Test that cleanup doesn't have race conditions."""
        # Start multiple files and complete them rapidly
        for i in range(5):
            self.tracker.start_file_processing(i, Path(f"/test/file{i}.py"), 1024)
            self.tracker.update_file_status(i, FileStatus.PROCESSING)

        # Complete all files rapidly
        for i in range(5):
            self.tracker.complete_file_processing(i)

        # All should be marked complete
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 5
        for file_data in active_files:
            assert file_data["status"] == FileStatus.COMPLETE.value

        # After cleanup delay, all should be removed
        with patch("time.time", return_value=time.time() + 4.0):
            active_files = self.tracker.get_concurrent_files_data()
            assert len(active_files) == 0

    def test_file_line_display_format(self):
        """Test formatted file line display."""
        thread_id = 1
        file_size = 2048  # 2 KB

        self.tracker.start_file_processing(thread_id, self.test_file1, file_size)
        self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)

        display_lines = self.tracker.get_formatted_display_lines()
        assert len(display_lines) == 1

        line = display_lines[0]
        assert "├─ file1.py" in line
        assert "(2.0 KB" in line
        assert "vectorizing..." in line

    def test_no_file_io_in_critical_sections(self):
        """Test that no file I/O operations happen in critical sections."""
        # This test ensures the lock contention issue is fixed
        # We'll mock file_path.stat() to take time and verify no blocking

        def slow_stat():
            time.sleep(0.1)  # Simulate slow file I/O
            return type("MockStat", (), {"st_size": 1024})()

        with patch.object(Path, "stat", side_effect=slow_stat):
            # File I/O should happen outside critical sections
            # so this should not block other operations

            start_time = time.time()

            # Start file processing (should do I/O outside lock)
            thread1 = threading.Thread(
                target=self.tracker.start_file_processing,
                args=(1, self.test_file1, None),  # None triggers stat() call
            )

            # Start another operation immediately
            thread2 = threading.Thread(
                target=self.tracker.start_file_processing,
                args=(2, self.test_file2, 2048),  # Pre-calculated size, no I/O
            )

            thread1.start()
            thread2.start()

            thread1.join()
            thread2.join()

            elapsed = time.time() - start_time

            # Thread2 should not be blocked by thread1's slow I/O
            # Total time should be close to single I/O time, not double
            assert elapsed < 0.15  # Allow some overhead

            # Both files should be tracked
            active_files = self.tracker.get_concurrent_files_data()
            assert len(active_files) == 2

    def test_integration_with_high_throughput_processor(self):
        """Test integration with HighThroughputProcessor interface."""
        # Test that the consolidated tracker provides the same interface
        # that HighThroughputProcessor expects

        # Start processing multiple files like HighThroughputProcessor would
        file_paths = [Path(f"/test/file{i}.py") for i in range(5)]

        for i, file_path in enumerate(file_paths):
            self.tracker.start_file_processing(i, file_path, 1024 * (i + 1))
            self.tracker.update_file_status(i, FileStatus.PROCESSING)

        # Get concurrent files data like progress callback expects
        concurrent_files = self.tracker.get_concurrent_files_data()

        # Should have expected structure for progress callback
        assert len(concurrent_files) == 5
        for i, file_data in enumerate(concurrent_files):
            assert file_data["thread_id"] == i
            assert file_data["file_path"] == str(file_paths[i])
            assert file_data["file_size"] == 1024 * (i + 1)
            assert file_data["status"] == FileStatus.PROCESSING.value
            assert "estimated_seconds" in file_data

    def test_replace_multiple_tracking_systems(self):
        """Test that consolidated tracker replaces all three tracking systems."""
        # This test verifies the consolidation actually works

        # Simulate the three different use cases:

        # 1. FileLineTracker use case - individual file tracking
        self.tracker.start_file_processing(1, self.test_file1, 1024)
        display_lines = self.tracker.get_formatted_display_lines()
        assert len(display_lines) == 1
        assert "├─" in display_lines[0]

        # 2. ConcurrentFileDisplay use case - multi-threaded display
        for i in range(8):
            self.tracker.start_file_processing(
                i + 2, Path(f"/test/file{i + 2}.py"), 1024
            )

        concurrent_data = self.tracker.get_concurrent_files_data()
        assert len(concurrent_data) == 8  # Respects max concurrent limit

        # 3. HighThroughputProcessor use case - progress callback data
        # After starting 9 files (1 + 8 more), max limit keeps only 8
        # Thread IDs should be 2-9 (oldest removed)
        expected_thread_ids = list(range(2, 10))
        actual_thread_ids = [file_data["thread_id"] for file_data in concurrent_data]
        assert actual_thread_ids == expected_thread_ids

        for file_data in concurrent_data:
            assert "estimated_seconds" in file_data
            assert file_data["status"] in [
                FileStatus.STARTING.value,
                FileStatus.PROCESSING.value,
            ]

    def test_cleanup_completed_files_automatically(self):
        """Test that completed files are automatically cleaned up."""
        # Start and complete files
        for i in range(3):
            self.tracker.start_file_processing(i, Path(f"/test/file{i}.py"), 1024)
            self.tracker.complete_file_processing(i)

        # Should have 3 completed files
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 3

        # Simulate time passing beyond cleanup delay
        future_time = time.time() + 4.0
        with patch("time.time", return_value=future_time):
            # Trigger cleanup by getting data
            active_files = self.tracker.get_concurrent_files_data()
            assert len(active_files) == 0  # All cleaned up

    def test_error_handling_missing_thread_id(self):
        """Test error handling for operations on non-existent thread ID."""
        # Try to update non-existent thread
        self.tracker.update_file_status(999, FileStatus.PROCESSING)  # Should not crash

        # Try to complete non-existent thread
        self.tracker.complete_file_processing(999)  # Should not crash

        # Should have no active files
        active_files = self.tracker.get_concurrent_files_data()
        assert len(active_files) == 0
