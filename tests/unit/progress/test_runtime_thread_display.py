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
            # slot_tracker will be lazily initialized
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

            # Initialize slot tracker with correct thread count
            processor._ensure_slot_tracker_initialized(vector_thread_count)

            # Simulate 12 files being processed using slot_tracker API
            from src.code_indexer.services.clean_slot_tracker import (
                FileData,
                FileStatus,
            )

            file_paths = [Path(f"/test/file{i}.py") for i in range(1, 13)]
            for i, file_path in enumerate(file_paths):
                file_data = FileData(
                    filename=str(file_path), file_size=1024, status=FileStatus.STARTING
                )
                _ = processor.slot_tracker.acquire_slot(file_data)

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
            # slot_tracker will be lazily initialized
            processor._thread_counter = 0
            processor._file_to_thread_map = {}
            processor._file_to_thread_lock = threading.Lock()

            # Test various thread counts
            test_cases = [4, 8, 12, 16, 24]

            for actual_threads in test_cases:
                # Reset and initialize with actual thread count
                # Explicitly reset slot_tracker to allow re-initialization
                processor.slot_tracker = None  # type: ignore[assignment]
                processor._ensure_slot_tracker_initialized(actual_threads)

                # Register that many files using slot_tracker API
                from src.code_indexer.services.clean_slot_tracker import (
                    FileData,
                    FileStatus,
                )

                for i in range(actual_threads):
                    file_data = FileData(
                        filename=str(Path(f"/test/file{i}.py")),
                        file_size=1024,
                        status=FileStatus.STARTING,
                    )
                    _ = processor.slot_tracker.acquire_slot(file_data)

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
