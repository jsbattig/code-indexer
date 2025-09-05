"""
Test suite for Feature 3: Individual File Tracking

Tests for file line formatting, status labels, and completion behavior
as specified in the Rich Progress Display epic.
"""

from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.utils.status_display import FreeScrollStreamDisplay
from code_indexer.utils.file_line_tracker import FileLineTracker
from rich.console import Console


class TestFileLineTrackerBasicFormatting:
    """Test file line formatting: ├─ filename (size, elapsed) status"""

    def test_file_line_format_structure(self):
        """Test that file lines follow exact format: ├─ filename (size, elapsed) status"""
        tracker = FileLineTracker()

        # Start processing a file
        file_path = Path("utils.py")
        file_size = 2150  # 2.1 KB

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, file_size)

        with patch("time.time", return_value=1005.0):  # 5 seconds elapsed
            line = tracker.update_file_status(file_path, "vectorizing")

        # Should match exact format: ├─ filename (size, elapsed) status
        expected = "├─ utils.py (2.1 KB, 5s) vectorizing..."
        assert line == expected

    def test_file_size_formatting_kb(self):
        """Test file size formatting in KB with one decimal place."""
        tracker = FileLineTracker()

        # Test various file sizes
        assert tracker.format_file_size(1024) == "1.0 KB"
        assert tracker.format_file_size(2150) == "2.1 KB"
        assert tracker.format_file_size(3456) == "3.4 KB"
        assert tracker.format_file_size(512) == "0.5 KB"
        assert tracker.format_file_size(10240) == "10.0 KB"

    def test_elapsed_time_formatting(self):
        """Test elapsed time formatting in seconds."""
        tracker = FileLineTracker()

        # Test various elapsed times (in seconds)
        assert tracker.format_elapsed_time(5.0) == "5s"
        assert tracker.format_elapsed_time(10.2) == "10s"
        assert tracker.format_elapsed_time(0.8) == "1s"  # Round up partial seconds
        assert tracker.format_elapsed_time(59.9) == "60s"

    def test_tree_prefix_consistency(self):
        """Test that all file lines use tree-style ├─ prefix."""
        tracker = FileLineTracker()

        files = [Path("main.py"), Path("config.py"), Path("utils/helper.py")]
        sizes = [1024, 2048, 3072]

        with patch("time.time", return_value=1000.0):
            for file_path, size in zip(files, sizes):
                tracker.start_file_processing(file_path, size)

        with patch("time.time", return_value=1003.0):
            lines = []
            for file_path in files:
                line = tracker.update_file_status(file_path, "vectorizing")
                lines.append(line)

        # All lines should start with tree prefix
        for line in lines:
            assert line.startswith("├─ ")
            assert " vectorizing..." in line


class TestFileLineTrackerStatusLabels:
    """Test processing state labels: 'vectorizing...' and 'complete'"""

    def test_vectorizing_status_label(self):
        """Test 'vectorizing...' label during processing."""
        tracker = FileLineTracker()
        file_path = Path("test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)

        with patch("time.time", return_value=1003.0):
            line = tracker.update_file_status(file_path, "vectorizing")

        assert line.endswith("vectorizing...")
        assert "vectorizing..." in line

    def test_complete_status_label(self):
        """Test 'complete' label when processing finishes."""
        tracker = FileLineTracker()
        file_path = Path("test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)

        with patch("time.time", return_value=1007.0):
            line = tracker.update_file_status(file_path, "complete")

        assert line.endswith("complete")
        assert "complete" in line

    def test_status_transition_vectorizing_to_complete(self):
        """Test status transition from vectorizing to complete."""
        tracker = FileLineTracker()
        file_path = Path("test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)

        with patch("time.time", return_value=1003.0):
            vectorizing_line = tracker.update_file_status(file_path, "vectorizing")
            assert "vectorizing..." in vectorizing_line

        with patch("time.time", return_value=1008.0):
            complete_line = tracker.update_file_status(file_path, "complete")
            assert "complete" in complete_line
            assert "vectorizing..." not in complete_line


class TestFileLineTrackerCompletionBehavior:
    """Test 3-second completion display before line removal"""

    def test_completion_display_duration(self):
        """Test that 'complete' status is shown for exactly 3 seconds."""
        tracker = FileLineTracker()
        file_path = Path("test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)

        with patch("time.time", return_value=1005.0):
            tracker.complete_file_processing(file_path)

        # Should be present in active lines initially
        active_lines = tracker.get_active_file_lines(current_time=1005.0)
        assert len(active_lines) == 1
        assert "complete" in active_lines[0]

        # Should still be present at 2.9 seconds
        active_lines = tracker.get_active_file_lines(current_time=1007.9)
        assert len(active_lines) == 1

        # Should be removed after exactly 3 seconds
        active_lines = tracker.get_active_file_lines(current_time=1008.1)
        assert len(active_lines) == 0

    def test_multiple_file_completion_timing(self):
        """Test completion timing with multiple files finishing at different times."""
        tracker = FileLineTracker()

        files = [Path("file1.py"), Path("file2.py"), Path("file3.py")]
        completion_times = [1005.0, 1007.0, 1010.0]

        # Start all files
        with patch("time.time", return_value=1000.0):
            for file_path in files:
                tracker.start_file_processing(file_path, 1024)

        # Complete files at different times
        for file_path, completion_time in zip(files, completion_times):
            with patch("time.time", return_value=completion_time):
                tracker.complete_file_processing(file_path)

        # At t=1008.0, file1 should be removed, file2 and file3 still visible
        active_lines = tracker.get_active_file_lines(current_time=1008.0)
        assert len(active_lines) == 2
        filenames = [line for line in active_lines]
        assert not any("file1.py" in line for line in filenames)
        assert any("file2.py" in line for line in filenames)
        assert any("file3.py" in line for line in filenames)

        # At t=1011.0, only file3 should remain
        active_lines = tracker.get_active_file_lines(current_time=1011.0)
        assert len(active_lines) == 1
        assert "file3.py" in active_lines[0]

        # At t=1014.0, all files should be removed
        active_lines = tracker.get_active_file_lines(current_time=1014.0)
        assert len(active_lines) == 0

    def test_completion_behavior_with_real_time_updates(self):
        """Test completion behavior with real-time elapsed time updates."""
        tracker = FileLineTracker()
        file_path = Path("real_time_test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 2048)

        # Update during processing (elapsed time should update)
        with patch("time.time", return_value=1003.5):
            line = tracker.update_file_status(file_path, "vectorizing")
            assert "4s" in line  # Should round 3.5s to 4s

        # Complete the file
        with patch("time.time", return_value=1007.2):
            tracker.complete_file_processing(file_path)

        # Check complete line format
        active_lines = tracker.get_active_file_lines(current_time=1007.2)
        assert len(active_lines) == 1
        complete_line = active_lines[0]
        assert "├─ real_time_test.py (2.0 KB, 7s) complete" == complete_line


class TestFileLineTrackerIntegration:
    """Test integration with existing progress display system"""

    def test_integration_with_free_scroll_stream_display(self):
        """Test integration with FreeScrollStreamDisplay."""
        console = Mock(spec=Console)
        display = FreeScrollStreamDisplay(console)
        tracker = FileLineTracker(console)

        # Test that file lines can be added to display content
        file_path = Path("integration_test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1536)

        with patch("time.time", return_value=1004.0):
            file_line = tracker.update_file_status(file_path, "vectorizing")

        # Should be able to pass file line to display
        assert file_line == "├─ integration_test.py (1.5 KB, 4s) vectorizing..."

        # Simulate adding to display content
        display.update_content(file_line + "\n")

    def test_multi_threaded_file_processing_simulation(self):
        """Test file tracking behavior simulating multi-threaded processing."""
        tracker = FileLineTracker()

        # Simulate 3 worker threads processing files concurrently
        thread_files = [
            [Path("thread1_file1.py"), Path("thread1_file2.py")],
            [Path("thread2_file1.py"), Path("thread2_file2.py")],
            [Path("thread3_file1.py"), Path("thread3_file2.py")],
        ]

        # Start all files at slightly different times
        start_times = [1000.0, 1000.2, 1000.5]
        for thread_id, files in enumerate(thread_files):
            with patch("time.time", return_value=start_times[thread_id]):
                for file_path in files:
                    tracker.start_file_processing(file_path, 1024 * (thread_id + 1))

        # All files should be active and show vectorizing status
        active_lines = tracker.get_active_file_lines(current_time=1002.0)
        assert len(active_lines) == 6

        # All should show vectorizing status
        for line in active_lines:
            assert "vectorizing..." in line
            assert line.startswith("├─ ")

        # Complete files from different threads at different times
        completion_times = [1005.0, 1006.0, 1007.0, 1008.0, 1009.0, 1010.0]
        all_files = [file_path for files in thread_files for file_path in files]

        for i, file_path in enumerate(all_files):
            with patch("time.time", return_value=completion_times[i]):
                tracker.complete_file_processing(file_path)

        # At t=1008.1:
        # - File completed at 1005.0: 3.1s elapsed, should be removed
        # - Files completed at 1006.0, 1007.0, 1008.0: <3s elapsed, still visible
        # - Files completed at 1009.0, 1010.0: haven't completed yet at t=1008.1
        active_lines = tracker.get_active_file_lines(current_time=1008.1)

        # Only files completed at 1009.0 and 1010.0 haven't reached completion time yet,
        # so they should still show as processing (not completed yet)
        # Files completed at 1006.0, 1007.0, 1008.0 should show as complete
        # File completed at 1005.0 should be removed
        # So we expect 5 files total: 2 still processing + 3 completed but not yet removed
        assert len(active_lines) == 5


class TestFileLineTrackerErrorCases:
    """Test error handling and edge cases"""

    def test_duplicate_file_processing_start(self):
        """Test handling of duplicate file processing starts."""
        tracker = FileLineTracker()
        file_path = Path("duplicate_test.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)
            # Starting same file again should not cause issues
            tracker.start_file_processing(file_path, 2048)  # Different size

        with patch("time.time", return_value=1003.0):
            line = tracker.update_file_status(file_path, "vectorizing")
            # Should use the most recent start (2048 bytes = 2.0 KB)
            assert "2.0 KB" in line

    def test_status_update_for_non_existent_file(self):
        """Test status update for file that wasn't started."""
        tracker = FileLineTracker()
        file_path = Path("non_existent.py")

        with patch("time.time", return_value=1003.0):
            # Should handle gracefully, perhaps by auto-starting
            line = tracker.update_file_status(file_path, "vectorizing")
            # Implementation should handle this case appropriately
            assert "non_existent.py" in line

    def test_zero_byte_file_handling(self):
        """Test handling of zero-byte files."""
        tracker = FileLineTracker()
        file_path = Path("empty.py")

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 0)

        with patch("time.time", return_value=1001.0):
            line = tracker.update_file_status(file_path, "vectorizing")

        assert "0.0 KB" in line
        assert "empty.py" in line

    def test_very_long_filename_handling(self):
        """Test handling of very long filenames."""
        tracker = FileLineTracker()
        long_filename = (
            "very_long_filename_that_might_cause_display_issues_in_terminal_output.py"
        )
        file_path = Path(long_filename)

        with patch("time.time", return_value=1000.0):
            tracker.start_file_processing(file_path, 1024)

        with patch("time.time", return_value=1003.0):
            line = tracker.update_file_status(file_path, "vectorizing")

        # Should contain the filename and proper formatting
        assert long_filename in line
        assert line.startswith("├─ ")
        assert "vectorizing..." in line
