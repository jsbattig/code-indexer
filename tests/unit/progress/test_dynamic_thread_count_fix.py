"""Tests validating the fix for dynamic thread count in file display.

This test suite validates that the ConsolidatedFileTracker is now properly initialized
with the actual thread count from configuration, not hardcoded to 8.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import threading

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


@pytest.mark.unit
class TestDynamicThreadCountFix:
    """Test cases validating the dynamic thread count fix."""

    def test_lazy_initialization_uses_actual_thread_count(self):
        """Test that ConsolidatedFileTracker uses actual thread count via lazy initialization."""
        # Create a mock processor to test lazy initialization
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize required attributes
        processor.file_tracker = None  # Start with None for lazy init
        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Test with different thread counts
        test_cases = [4, 8, 12, 16, 24]

        for thread_count in test_cases:
            # Reset file tracker for each test
            processor.file_tracker = None

            # Call the lazy initialization method with specific thread count
            processor._ensure_file_tracker_initialized(thread_count)

            # Verify file tracker was created with correct thread count
            assert (
                processor.file_tracker is not None
            ), "File tracker should be initialized"
            assert processor.file_tracker.max_concurrent_files == thread_count, (
                f"Expected max_concurrent_files={thread_count}, "
                f"got {processor.file_tracker.max_concurrent_files}"
            )

    def test_process_files_initializes_with_vector_thread_count(self):
        """Test that process_files_high_throughput initializes tracker with vector_thread_count."""
        with patch.object(HighThroughputProcessor, "__init__", return_value=None):
            processor = HighThroughputProcessor()

            # Initialize required attributes
            processor.file_tracker = None
            processor._thread_counter = 0
            processor._file_to_thread_map = {}
            processor._file_to_thread_lock = threading.Lock()
            processor.cancelled = False
            processor._file_rate_lock = threading.Lock()
            processor._source_bytes_lock = threading.Lock()

            # Mock other required components
            processor.fixed_size_chunker = Mock()
            processor.fixed_size_chunker.chunk_file = Mock(return_value=[])
            processor.file_identifier = Mock()
            processor.embedding_provider = Mock()
            processor.qdrant_client = Mock()

            # Call process_files_high_throughput with specific thread count
            vector_thread_count = 16

            try:
                processor.process_files_high_throughput(
                    files=[],
                    vector_thread_count=vector_thread_count,
                    progress_callback=None,
                )
            except Exception:
                # We expect it to fail on empty files, but initialization should happen
                pass

            # Verify tracker was initialized with correct thread count
            assert (
                processor.file_tracker is not None
            ), "File tracker should be initialized"
            assert processor.file_tracker.max_concurrent_files == vector_thread_count, (
                f"Expected tracker initialized with {vector_thread_count} threads, "
                f"got {processor.file_tracker.max_concurrent_files}"
            )

    def test_concurrent_file_display_matches_thread_count(self):
        """Test that concurrent file display can show as many files as threads configured."""
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize attributes
        processor.file_tracker = None
        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Test with 12 threads (common configuration)
        thread_count = 12
        processor._ensure_file_tracker_initialized(thread_count)

        # Register 12 files (simulating all threads active)
        file_paths = [Path(f"/test/file{i}.py") for i in range(1, thread_count + 1)]

        for i, file_path in enumerate(file_paths):
            processor.file_tracker.start_file_processing(
                thread_id=i, file_path=file_path, file_size=1024
            )

        # Get concurrent files data
        concurrent_files = processor.file_tracker.get_concurrent_files_data()

        # Verify all files are displayed (not limited to 8)
        assert len(concurrent_files) == thread_count, (
            f"Expected {thread_count} concurrent files to match configured threads, "
            f"got {len(concurrent_files)}"
        )

        # Verify all files are present
        displayed_paths = {cf["file_path"] for cf in concurrent_files}
        expected_paths = {str(fp) for fp in file_paths}

        assert displayed_paths == expected_paths, (
            f"Missing files from display. Expected: {expected_paths}, "
            f"Got: {displayed_paths}"
        )

    def test_backwards_compatibility_fallback_to_8(self):
        """Test that uninitialized tracker falls back to 8 threads for backwards compatibility."""
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize attributes
        processor.file_tracker = None
        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Call ensure_file_tracker_initialized without thread count (fallback case)
        processor._ensure_file_tracker_initialized()

        # Should fall back to 8 for backwards compatibility
        assert (
            processor.file_tracker.max_concurrent_files == 8
        ), "Expected fallback to 8 threads for backwards compatibility"
