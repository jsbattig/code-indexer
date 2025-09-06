"""Runtime test to verify thread display behavior with actual execution."""

import pytest
from pathlib import Path
from unittest.mock import patch
import threading
import time

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


@pytest.mark.unit
class TestRuntimeThreadDisplay:
    """Test runtime behavior of thread display with different configurations."""

    def test_progress_callback_receives_correct_concurrent_files(self):
        """Test that progress callback receives correct number of concurrent files."""
        with patch.object(HighThroughputProcessor, "__init__", return_value=None):
            processor = HighThroughputProcessor()

            # Initialize all required attributes
            processor.file_tracker = None
            processor._thread_counter = 0
            processor._file_to_thread_map = {}
            processor._file_to_thread_lock = threading.Lock()
            processor.cancelled = False
            processor._file_rate_lock = threading.Lock()
            processor._file_rate_start_time = time.time()
            processor._file_rate_count = 0
            processor._source_bytes_lock = threading.Lock()
            processor._cumulative_source_bytes = 0
            processor._source_bytes_history = []

            # Test with 12 threads
            vector_thread_count = 12

            # Initialize file tracker with correct thread count
            processor._ensure_file_tracker_initialized(vector_thread_count)

            # Simulate 12 files being processed
            file_paths = [Path(f"/test/file{i}.py") for i in range(1, 13)]
            for i, file_path in enumerate(file_paths):
                processor.file_tracker.start_file_processing(
                    thread_id=i, file_path=file_path, file_size=1024
                )

            # Call _get_concurrent_threads_snapshot (even with hardcoded max_threads=8)
            concurrent_files = processor._get_concurrent_threads_snapshot(max_threads=8)

            # Verify it returns all 12 files despite the hardcoded 8 parameter
            # This proves the parameter is ignored and actual thread count is used
            assert len(concurrent_files) == 12, (
                f"Expected 12 concurrent files from tracker initialized with {vector_thread_count} threads, "
                f"got {len(concurrent_files)}. The max_threads parameter should be ignored."
            )

    def test_hardcoded_parameter_is_ignored(self):
        """Test that the hardcoded max_threads=8 parameter is completely ignored."""
        with patch.object(HighThroughputProcessor, "__init__", return_value=None):
            processor = HighThroughputProcessor()

            # Initialize attributes
            processor.file_tracker = None
            processor._thread_counter = 0
            processor._file_to_thread_map = {}
            processor._file_to_thread_lock = threading.Lock()

            # Test various thread counts
            test_cases = [4, 8, 12, 16, 24]

            for actual_threads in test_cases:
                # Reset and initialize with actual thread count
                processor.file_tracker = None
                processor._ensure_file_tracker_initialized(actual_threads)

                # Register that many files
                for i in range(actual_threads):
                    processor.file_tracker.start_file_processing(
                        thread_id=i, file_path=Path(f"/test/file{i}.py"), file_size=1024
                    )

                # Call with different hardcoded values - all should be ignored
                for bogus_param in [1, 8, 100]:
                    result = processor._get_concurrent_threads_snapshot(
                        max_threads=bogus_param
                    )

                    assert len(result) == actual_threads, (
                        f"With {actual_threads} threads initialized, got {len(result)} files "
                        f"when calling with max_threads={bogus_param}. "
                        f"The parameter should be completely ignored."
                    )
