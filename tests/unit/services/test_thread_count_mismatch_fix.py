"""
Tests for Thread Count Mismatch Fix.

This module tests the surgical fix for the thread count mismatch between
FileChunkingManager (thread_count + 2 workers) and ConsolidatedFileTracker
(thread_count max files). The mismatch causes 2 workers to process files
invisibly without display tracking.

ROOT CAUSE:
- FileChunkingManager: 14 workers (12 threads + 2)
- ConsolidatedFileTracker: 12 max files (threads only)
- Result: 2 workers process files without being displayed

SURGICAL FIX:
- Change max_concurrent_files=thread_count to max_concurrent_files=thread_count + 2
- This ensures ConsolidatedFileTracker can track all FileChunkingManager workers
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

from code_indexer.services.high_throughput_processor import HighThroughputProcessor


class TestThreadCountMismatchFix:
    """Test suite for thread count mismatch fix."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for the test
        self.temp_dir = Path(tempfile.mkdtemp(prefix="thread_count_test_"))

        # Create mock dependencies for HighThroughputProcessor
        config = Mock()
        config.codebase_dir = self.temp_dir
        config.exclude_dirs = []
        config.exclude_files = []
        config.file_extensions = [".py"]
        config.exclude_patterns = []
        config.include_patterns = ["*"]
        config.max_file_size_mb = 10

        embedding_provider = Mock()
        qdrant_client = Mock()

        self.processor = HighThroughputProcessor(
            config=config,
            embedding_provider=embedding_provider,
            qdrant_client=qdrant_client,
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_consolidated_file_tracker_handles_all_workers_failing_case(self):
        """FAILING TEST: ConsolidatedFileTracker should handle thread_count + 2 files.

        This test will FAIL until the fix is implemented because:
        - FileChunkingManager creates thread_count + 2 workers
        - ConsolidatedFileTracker only handles thread_count files
        - 2 workers will be invisible in display tracking

        Expected behavior after fix:
        - ConsolidatedFileTracker max_concurrent_files = thread_count + 2
        - All FileChunkingManager workers can register and be tracked
        - No invisible workers processing files
        """
        thread_count = 12

        # Initialize the file tracker with thread_count (current broken behavior)
        self.processor._ensure_file_tracker_initialized(thread_count=thread_count)

        # Simulate FileChunkingManager workers registering files (thread_count + 2 = 14)
        file_paths = [Path(f"/test/file{i}.py") for i in range(thread_count + 2)]

        # Register all workers (14 total) - simulating FileChunkingManager behavior
        registered_threads = []
        for i, file_path in enumerate(file_paths):
            # This simulates what FileChunkingManager workers do
            thread_id = self.processor._register_thread_file(file_path, "processing")
            registered_threads.append(thread_id)

        # ASSERTION THAT WILL FAIL: All 14 workers should be tracked
        # Currently fails because ConsolidatedFileTracker max_concurrent_files=12
        concurrent_files = self.processor.file_tracker.get_concurrent_files_data()

        # This assertion will FAIL - we expect 14 but only get 12 due to the bug
        assert len(concurrent_files) == thread_count + 2, (
            f"Expected {thread_count + 2} tracked files (matching FileChunkingManager workers), "
            f"but got {len(concurrent_files)}. This indicates invisible workers are processing files."
        )

        # Verify all workers can be found in display
        tracked_thread_ids = {file_data["thread_id"] for file_data in concurrent_files}
        expected_thread_ids = set(registered_threads)

        missing_threads = expected_thread_ids - tracked_thread_ids
        assert len(missing_threads) == 0, (
            f"Missing {len(missing_threads)} workers from display tracking: {missing_threads}. "
            f"These workers are processing files invisibly."
        )

    def test_all_file_chunking_manager_workers_visible_in_display(self):
        """FAILING TEST: All FileChunkingManager workers should be visible in display.

        This test simulates the real scenario where FileChunkingManager creates
        thread_count + 2 workers, but only thread_count workers are visible
        in the display because ConsolidatedFileTracker has insufficient capacity.

        This test will FAIL until max_concurrent_files is increased to thread_count + 2.
        """
        thread_count = 12
        expected_workers = thread_count + 2  # 14 total workers

        # Initialize tracker with current broken configuration
        self.processor._initialize_file_tracker(thread_count=thread_count)

        # Simulate FileChunkingManager creating workers
        worker_files = []
        for i in range(expected_workers):
            file_path = Path(f"/test/worker_file_{i}.py")
            worker_files.append(file_path)

        # Register all workers as they would be in real FileChunkingManager
        registered_workers = []
        for i, file_path in enumerate(worker_files):
            # Each worker registers its file for processing
            thread_id = self.processor._register_thread_file(file_path, "starting...")
            registered_workers.append(
                {"thread_id": thread_id, "file_path": file_path, "worker_index": i}
            )

        # Get display data - this is what the user sees
        display_lines = self.processor.file_tracker.get_formatted_display_lines()
        concurrent_data = self.processor.file_tracker.get_concurrent_files_data()

        # FAILING ASSERTION: All workers should be visible in display
        assert len(display_lines) == expected_workers, (
            f"Expected {expected_workers} display lines (one per FileChunkingManager worker), "
            f"but got {len(display_lines)}. Missing workers are processing files invisibly."
        )

        assert len(concurrent_data) == expected_workers, (
            f"Expected {expected_workers} tracked files, but got {len(concurrent_data)}. "
            f"The thread count mismatch causes {expected_workers - len(concurrent_data)} "
            f"workers to be invisible."
        )

        # Verify each worker can be found in the tracking system
        tracked_paths = {file_data["file_path"] for file_data in concurrent_data}
        expected_paths = {str(worker["file_path"]) for worker in registered_workers}

        missing_paths = expected_paths - tracked_paths
        assert len(missing_paths) == 0, (
            f"Missing {len(missing_paths)} worker files from tracking: "
            f"{list(missing_paths)[:3]}{'...' if len(missing_paths) > 3 else ''}"
        )

    def test_thread_count_plus_two_configuration_integration(self):
        """FAILING TEST: Verify the fix integrates correctly with existing systems.

        This test ensures that when the fix is applied (max_concurrent_files=thread_count + 2),
        the system works correctly with the broader ecosystem.

        This test will FAIL until the surgical fix is implemented in high_throughput_processor.py.
        """
        thread_count = 12

        # Test with the configuration that should match FileChunkingManager
        # This simulates the fix: max_concurrent_files = thread_count + 2
        from code_indexer.services.consolidated_file_tracker import (
            ConsolidatedFileTracker,
        )

        # Create tracker with the FIXED configuration (what we want after the fix)
        fixed_tracker = ConsolidatedFileTracker(max_concurrent_files=thread_count + 2)

        # But processor still uses the broken configuration
        self.processor._ensure_file_tracker_initialized(thread_count=thread_count)

        # Test the fixed tracker directly (this should work)
        test_files = [Path(f"/test/fixed_test_{i}.py") for i in range(thread_count + 2)]
        for i, file_path in enumerate(test_files):
            fixed_tracker.start_file_processing(i, file_path, 1024)

        fixed_data = fixed_tracker.get_concurrent_files_data()
        assert (
            len(fixed_data) == thread_count + 2
        ), f"Fixed tracker should handle {thread_count + 2} files, got {len(fixed_data)}"

        # But the processor's tracker should still be broken (until fix is applied)
        processor_files = [
            Path(f"/test/processor_test_{i}.py") for i in range(thread_count + 2)
        ]
        for file_path in processor_files:
            self.processor._register_thread_file(file_path, "processing")

        processor_data = self.processor.file_tracker.get_concurrent_files_data()

        # This assertion will FAIL because processor still uses thread_count (12) instead of thread_count + 2 (14)
        assert len(processor_data) == thread_count + 2, (
            f"Processor tracker should handle {thread_count + 2} files after fix, "
            f"but got {len(processor_data)}. The fix needs to be applied to "
            f"high_throughput_processor.py line 131: max_concurrent_files=thread_count + 2"
        )

    def test_no_invisible_workers_after_fix(self):
        """FAILING TEST: After fix, no FileChunkingManager workers should be invisible.

        This test simulates the exact scenario where the bug occurs:
        - FileChunkingManager creates 14 workers (thread_count=12 + 2)
        - ConsolidatedFileTracker only tracks 12 files (thread_count)
        - 2 workers process files without being displayed to user

        This test will FAIL until the surgical fix is implemented.
        """
        thread_count = 12

        # Initialize with current broken configuration
        self.processor._ensure_file_tracker_initialized(thread_count=thread_count)

        # Simulate FileChunkingManager worker behavior
        chunking_manager_workers = thread_count + 2  # 14 workers total
        worker_results = []

        for worker_id in range(chunking_manager_workers):
            file_path = Path(f"/test/chunk_worker_{worker_id}.py")

            # Each worker tries to register its file for display tracking
            thread_id = self.processor._register_thread_file(file_path, "starting...")

            # Worker updates its status (simulating real processing)
            if self.processor.file_tracker:
                from code_indexer.services.consolidated_file_tracker import FileStatus

                self.processor.file_tracker.update_file_status(
                    thread_id, FileStatus.PROCESSING
                )

            worker_results.append(
                {
                    "worker_id": worker_id,
                    "thread_id": thread_id,
                    "file_path": str(file_path),
                    "registered": thread_id is not None,
                }
            )

        # Check how many workers are actually tracked vs invisible
        concurrent_files = self.processor.file_tracker.get_concurrent_files_data()
        tracked_workers = len(concurrent_files)
        invisible_workers = chunking_manager_workers - tracked_workers

        # FAILING ASSERTION: No workers should be invisible
        assert invisible_workers == 0, (
            f"Found {invisible_workers} invisible workers! "
            f"FileChunkingManager created {chunking_manager_workers} workers, "
            f"but only {tracked_workers} are visible in ConsolidatedFileTracker. "
            f"Fix needed: change max_concurrent_files from {thread_count} to {thread_count + 2}"
        )

        # Verify user can see all workers in display
        display_lines = self.processor.file_tracker.get_formatted_display_lines()
        assert len(display_lines) == chunking_manager_workers, (
            f"User should see {chunking_manager_workers} file processing lines, "
            f"but only sees {len(display_lines)}. The invisible workers are processing "
            f"files without user feedback."
        )

        # Verify status tracking works for all workers
        processing_count = sum(
            1 for f in concurrent_files if f["status"] == "processing"
        )
        assert processing_count == chunking_manager_workers, (
            f"All {chunking_manager_workers} workers should show 'processing' status, "
            f"but only {processing_count} are tracked."
        )
