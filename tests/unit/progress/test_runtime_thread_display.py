"""Runtime test to verify thread display behavior with actual execution."""

import pytest
from pathlib import Path


@pytest.mark.unit
class TestRuntimeThreadDisplay:
    """Test runtime behavior of thread display with different configurations."""

    def test_progress_callback_receives_correct_concurrent_files(self):
        """Test that CleanSlotTracker can handle correct number of concurrent files."""
        from src.code_indexer.services.clean_slot_tracker import (
            CleanSlotTracker,
            FileData,
            FileStatus,
        )

        # Test with 12 threads
        vector_thread_count = 12
        expected_slots = vector_thread_count + 2  # Matching processor logic

        # Create slot tracker directly with thread count + 2
        slot_tracker = CleanSlotTracker(max_slots=expected_slots)

        # Simulate 12 files being processed using slot_tracker API
        file_paths = [Path(f"/test/file{i}.py") for i in range(1, 13)]
        acquired_slots = []
        for i, file_path in enumerate(file_paths):
            file_data = FileData(
                filename=str(file_path), file_size=1024, status=FileStatus.STARTING
            )
            slot_id = slot_tracker.acquire_slot(file_data)
            acquired_slots.append(slot_id)

        # Get concurrent files data
        concurrent_files = slot_tracker.get_concurrent_files_data()

        # Verify it returns all 12 files
        assert len(concurrent_files) == vector_thread_count, (
            f"Expected {vector_thread_count} concurrent files from tracker initialized with {expected_slots} slots, "
            f"got {len(concurrent_files)}."
        )

        # Clean up by releasing all slots
        for slot_id in acquired_slots:
            slot_tracker.release_slot(slot_id)

    def test_clean_slot_tracker_uses_configured_slots(self):
        """Test that CleanSlotTracker uses the configured slot count correctly."""
        from src.code_indexer.services.clean_slot_tracker import (
            CleanSlotTracker,
            FileData,
            FileStatus,
        )

        # Test various thread counts
        test_cases = [4, 8, 12, 16, 24]

        for actual_threads in test_cases:
            expected_slots = actual_threads + 2  # Matching processor logic

            # Create slot tracker with actual thread count + 2
            slot_tracker = CleanSlotTracker(max_slots=expected_slots)

            # Register that many files using slot_tracker API
            acquired_slots = []
            for i in range(actual_threads):
                file_data = FileData(
                    filename=str(Path(f"/test/file{i}.py")),
                    file_size=1024,
                    status=FileStatus.STARTING,
                )
                slot_id = slot_tracker.acquire_slot(file_data)
                acquired_slots.append(slot_id)

            # Get concurrent files data
            result = slot_tracker.get_concurrent_files_data()

            assert len(result) == actual_threads, (
                f"With {expected_slots} slots configured, got {len(result)} files. "
                f"Should handle {actual_threads} concurrent files."
            )

            # Clean up by releasing all slots
            for slot_id in acquired_slots:
                slot_tracker.release_slot(slot_id)
