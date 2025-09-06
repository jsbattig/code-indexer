"""Test to validate that 12-thread file display limit fix works correctly.

This test validates the fix for the hardcoded 8-line limit issue where:
- User configures 12 threads → Shows "12 threads" ✅
- File display shows only 8 lines → Should show 12 lines ✅

The fix involved:
1. Adding max_lines parameter to MultiThreadedProgressManager constructor
2. Passing parallel_vector_worker_thread_count from CLI to progress manager
3. Ensuring ConcurrentFileDisplay respects the max_lines setting
"""

from pathlib import Path
from unittest import TestCase

from rich.console import Console

from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


class TestFileDisplayLimitFix(TestCase):
    """Validation tests for the 12-thread file display fix."""

    def test_progress_manager_accepts_custom_max_lines(self):
        """Test MultiThreadedProgressManager accepts and uses custom max_lines parameter."""

        console = Console()

        # Before fix: MultiThreadedProgressManager hardcoded to 8 lines
        # After fix: Accepts max_lines parameter
        progress_manager = MultiThreadedProgressManager(console, max_lines=12)

        # Verify the fix propagated correctly
        self.assertEqual(progress_manager.concurrent_display.max_lines, 12)

    def test_concurrent_file_display_respects_12_thread_limit(self):
        """Test ConcurrentFileDisplay can handle 12 concurrent files when configured."""

        console = Console()
        progress_manager = MultiThreadedProgressManager(console, max_lines=12)
        display = progress_manager.concurrent_display

        # Simulate 12 threads working on files simultaneously
        test_files = [Path(f"/test/file{i}.py") for i in range(1, 13)]

        # Add all 12 files to display
        for i, file_path in enumerate(test_files):
            display.add_file_line(
                thread_id=i + 1,
                file_path=file_path,
                file_size=1024,
                estimated_seconds=2,
            )

        # Before fix: Only 8 lines would be displayed (oldest removed)
        # After fix: All 12 lines are displayed
        self.assertEqual(
            len(display.active_lines),
            12,
            "ConcurrentFileDisplay should show all 12 files when max_lines=12",
        )

    def test_file_tracker_initialized_with_correct_thread_count(self):
        """Test HighThroughputProcessor file tracker uses actual thread count."""

        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize required attributes
        import threading

        processor.cancelled = False
        processor.file_tracker = None
        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Initialize with 12 threads (simulating CLI parameter)
        processor._ensure_file_tracker_initialized(thread_count=12)

        # Verify file tracker was initialized with correct thread count
        self.assertEqual(processor.file_tracker.max_concurrent_files, 12)

    def test_end_to_end_12_thread_workflow_produces_12_display_lines(self):
        """Integration test: 12 threads configured → 12 display lines shown."""

        # Create progress manager with 12 threads (simulating CLI fix)
        console = Console()
        progress_manager = MultiThreadedProgressManager(console, max_lines=12)

        # Create processor with 12 threads
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)
        import threading

        processor.cancelled = False
        processor.file_tracker = None
        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()
        processor._ensure_file_tracker_initialized(thread_count=12)

        # Simulate 12 concurrent files being processed
        test_files = [Path(f"/test/file{i}.py") for i in range(1, 13)]

        for i, file_path in enumerate(test_files):
            # Start file processing in tracker
            processor.file_tracker.start_file_processing(
                thread_id=i + 1, file_path=file_path, file_size=1024
            )

            # Add to display (simulating progress callback flow)
            progress_manager.concurrent_display.add_file_line(
                thread_id=i + 1,
                file_path=file_path,
                file_size=1024,
                estimated_seconds=2,
            )

        # Verify both components show all 12 files
        concurrent_files = processor.file_tracker.get_concurrent_files_data()
        display_lines = len(progress_manager.concurrent_display.active_lines)

        self.assertEqual(
            len(concurrent_files),
            12,
            "File tracker should track all 12 concurrent files",
        )
        self.assertEqual(
            display_lines, 12, "Progress display should show all 12 concurrent files"
        )

    def test_original_bug_scenario_now_fixed(self):
        """Test that the original bug scenario (8 lines despite 12 threads) is now fixed."""

        # Original bug: MultiThreadedProgressManager hardcoded to 8 max_lines
        # Even when user configured 12 threads, only 8 file lines were displayed

        # Now with fix: max_lines parameter propagated from thread count
        console = Console()

        # Simulate CLI passing thread count to progress manager
        thread_count = 12  # This would come from parallel_vector_worker_thread_count
        progress_manager = MultiThreadedProgressManager(console, max_lines=thread_count)

        # Test that we can display 12 files (not limited to 8)
        test_files = [Path(f"/test/file{i}.py") for i in range(1, 13)]

        for i, file_path in enumerate(test_files):
            progress_manager.concurrent_display.add_file_line(
                thread_id=i + 1,
                file_path=file_path,
                file_size=1024,
                estimated_seconds=1,
            )

        # The fix: Now we get 12 lines, not 8
        displayed_files = len(progress_manager.concurrent_display.active_lines)

        # Before fix: displayed_files would be 8 (hardcoded limit)
        # After fix: displayed_files should be 12 (respects thread count)
        self.assertEqual(
            displayed_files,
            12,
            "File display should show 12 lines when 12 threads configured (bug fixed)",
        )
