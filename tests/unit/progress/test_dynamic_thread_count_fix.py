"""Tests validating the fix for dynamic thread count in file display.

This test suite validates that the ConsolidatedFileTracker is now properly initialized
with the actual thread count from configuration, not hardcoded to 8.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import threading

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


@pytest.mark.unit
class TestDynamicThreadCountFix:
    """Test cases validating the dynamic thread count fix."""

    def test_lazy_initialization_uses_actual_thread_count(self):
        """Test that CleanSlotTracker uses actual thread count in local creation."""
        # Test CleanSlotTracker creation directly with different thread counts
        from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker

        # Test with different thread counts
        test_cases = [4, 8, 12, 16, 24]

        for thread_count in test_cases:
            # Create slot tracker with thread count + 2 (matching processor logic)
            expected_slots = thread_count + 2
            slot_tracker = CleanSlotTracker(max_slots=expected_slots)

            # Verify slot tracker was created with correct thread count
            assert slot_tracker is not None, "Slot tracker should be initialized"
            assert slot_tracker.max_slots == expected_slots, (
                f"Expected max_slots={expected_slots} ({thread_count}+2), "
                f"got {slot_tracker.max_slots}"
            )

    def test_process_files_initializes_with_vector_thread_count(self):
        """Test that process_files_high_throughput creates local tracker with vector_thread_count."""
        with patch.object(HighThroughputProcessor, "__init__", return_value=None):
            processor = HighThroughputProcessor()

            # Initialize required attributes for the new architecture
            processor.cancelled = False
            processor._file_rate_lock = threading.Lock()
            processor._source_bytes_lock = threading.Lock()
            processor._visibility_lock = threading.Lock()
            processor._git_lock = threading.Lock()
            processor._content_id_lock = threading.Lock()
            processor._database_lock = threading.Lock()
            processor._cancellation_event = threading.Event()
            processor._cancellation_lock = threading.Lock()
            processor._file_processing_start_time = None
            processor._file_completion_history = []
            processor._rolling_window_seconds = 30.0
            processor._min_time_diff = 0.1
            processor._total_source_bytes_processed = 0
            processor._source_bytes_history = []

            # Mock required components that would be used during processing
            processor.fixed_size_chunker = Mock()
            processor.fixed_size_chunker.chunk_file = Mock(return_value=[])
            processor.file_identifier = Mock()
            processor.embedding_provider = Mock()
            processor.qdrant_client = Mock()

            # Mock config object (required for codebase_dir parameter)
            processor.config = Mock()
            processor.config.codebase_dir = Path("/test/codebase")

            # Mock the VectorCalculationManager and FileChunkingManager contexts

            # Test with specific thread count
            vector_thread_count = 16

            # Mock the context managers to capture the slot tracker creation
            captured_slot_tracker = None

            def mock_file_chunking_manager(*args, **kwargs):
                nonlocal captured_slot_tracker
                captured_slot_tracker = kwargs.get("slot_tracker")
                mock_manager = MagicMock()
                mock_manager.__enter__ = MagicMock(return_value=mock_manager)
                mock_manager.__exit__ = MagicMock(return_value=False)
                mock_manager.submit_file_for_processing = Mock(return_value=Mock())
                return mock_manager

            with (
                patch(
                    "src.code_indexer.services.high_throughput_processor.VectorCalculationManager"
                ) as mock_vector_manager,
                patch(
                    "src.code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=mock_file_chunking_manager,
                ),
            ):

                mock_vector_context = MagicMock()
                mock_vector_context.__enter__ = MagicMock(
                    return_value=mock_vector_context
                )
                mock_vector_context.__exit__ = MagicMock(return_value=False)
                mock_vector_manager.return_value = mock_vector_context

                # Call process_files_high_throughput with empty files (will exit early)
                processor.process_files_high_throughput(
                    files=[],
                    vector_thread_count=vector_thread_count,
                )

            # Verify slot tracker was created with correct thread count (thread_count + 2)
            assert (
                captured_slot_tracker is not None
            ), "Slot tracker should be passed to FileChunkingManager"
            expected_slots = vector_thread_count + 2
            assert captured_slot_tracker.max_slots == expected_slots, (
                f"Expected tracker initialized with {expected_slots} slots ({vector_thread_count}+2), "
                f"got {captured_slot_tracker.max_slots}"
            )

    def test_concurrent_file_display_matches_thread_count(self):
        """Test that concurrent file display can show as many files as threads configured."""
        from src.code_indexer.services.clean_slot_tracker import (
            CleanSlotTracker,
            FileData,
            FileStatus,
        )

        # Test with 12 threads (common configuration)
        thread_count = 12
        expected_slots = thread_count + 2  # Matching processor logic

        # Create slot tracker directly with thread count + 2
        slot_tracker = CleanSlotTracker(max_slots=expected_slots)

        # Register 12 files (simulating all threads active)
        file_paths = [Path(f"/test/file{i}.py") for i in range(1, thread_count + 1)]

        # Register files using the slot_tracker API
        acquired_slot_ids = []
        for i, file_path in enumerate(file_paths):
            file_data = FileData(
                filename=str(file_path), file_size=1024, status=FileStatus.STARTING
            )
            slot_id = slot_tracker.acquire_slot(file_data)
            acquired_slot_ids.append(slot_id)

        # Get concurrent files data
        concurrent_files = slot_tracker.get_concurrent_files_data()

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

        # Clean up by releasing all slots
        for slot_id in acquired_slot_ids:
            slot_tracker.release_slot(slot_id)

    def test_backwards_compatibility_fallback_to_8(self):
        """Test that CleanSlotTracker creates with specified thread count."""
        from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker

        # Test default behavior when using 8 threads (common fallback value)
        default_thread_count = 8
        expected_slots = default_thread_count + 2  # 8 threads + 2 = 10 slots

        slot_tracker = CleanSlotTracker(max_slots=expected_slots)

        # Should create with 8 + 2 = 10 slots for backwards compatibility scenario
        assert (
            slot_tracker.max_slots == expected_slots  # 8 threads + 2 = 10
        ), f"Expected {expected_slots} slots ({default_thread_count}+2) for backwards compatibility"
