"""Tests for slot visual feedback fix - completed files remain visible."""

import pytest
from pathlib import Path

from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)


def test_completed_files_remain_visible():
    """Test that completed files remain visible in slot display after completion."""
    tracker = CleanSlotTracker(max_slots=3)

    # Acquire slots for 3 files
    file1 = FileData(filename="file1.py", file_size=1000, status=FileStatus.STARTING)
    file2 = FileData(filename="file2.py", file_size=2000, status=FileStatus.STARTING)
    file3 = FileData(filename="file3.py", file_size=3000, status=FileStatus.STARTING)

    slot1 = tracker.acquire_slot(file1)
    slot2 = tracker.acquire_slot(file2)
    _slot3 = tracker.acquire_slot(file3)  # Use _ prefix for unused variable

    # All 3 files should be visible
    display_files = tracker.get_display_files()
    assert len(display_files) == 3

    # Complete file1 and file2
    tracker.update_slot(slot1, FileStatus.COMPLETE)
    tracker.update_slot(slot2, FileStatus.COMPLETE)

    # Both completed files should still be visible
    display_files = tracker.get_display_files()
    assert len(display_files) == 3

    # Check that completed files show correct status
    completed_files = [f for f in display_files if f.status == FileStatus.COMPLETE]
    assert len(completed_files) == 2


def test_release_slot_keep_visible_functionality():
    """Test that release_slot_keep_visible allows slot reuse while maintaining display."""
    tracker = CleanSlotTracker(max_slots=2)

    # Acquire both slots
    file1 = FileData(filename="file1.py", file_size=1000, status=FileStatus.STARTING)
    file2 = FileData(filename="file2.py", file_size=2000, status=FileStatus.STARTING)

    slot1 = tracker.acquire_slot(file1)
    _slot2 = tracker.acquire_slot(file2)  # Use _ prefix for unused variable

    # Complete file1 and release its slot while keeping visible
    tracker.update_slot(slot1, FileStatus.COMPLETE)
    tracker.release_slot_keep_visible(slot1)

    # File1 should still be visible as completed
    display_files = tracker.get_display_files()
    assert len(display_files) == 2
    completed_files = [f for f in display_files if f.status == FileStatus.COMPLETE]
    assert len(completed_files) == 1

    # But slot1 should be available for reuse
    available_count = tracker.get_available_slot_count()
    assert available_count == 1

    # Should be able to acquire a new file (reusing slot1)
    file3 = FileData(filename="file3.py", file_size=3000, status=FileStatus.STARTING)
    slot3 = tracker.acquire_slot(file3)  # Should reuse slot1
    assert slot3 == slot1  # Confirms slot reuse

    # Now we should see file3 in slot1 position, file2 still in slot2
    display_files = tracker.get_display_files()
    assert len(display_files) == 2

    # file1 is no longer visible (replaced by file3), file2 still visible
    file_paths = [f.filename for f in display_files]
    assert "file3.py" in file_paths
    assert "file2.py" in file_paths


def test_visual_feedback_with_continuous_processing():
    """Test visual feedback during continuous file processing."""
    tracker = CleanSlotTracker(max_slots=2)

    files_to_process = [
        Path("file1.py"),
        Path("file2.py"),
        Path("file3.py"),
        Path("file4.py"),
        Path("file5.py"),
    ]

    # Process first 2 files (fill all slots)
    file1_data = FileData(
        filename=files_to_process[0].name, file_size=1000, status=FileStatus.STARTING
    )
    file2_data = FileData(
        filename=files_to_process[1].name, file_size=2000, status=FileStatus.STARTING
    )

    slot1 = tracker.acquire_slot(file1_data)
    slot2 = tracker.acquire_slot(file2_data)

    # Both should be visible
    assert len(tracker.get_display_files()) == 2

    # Complete file1 and release for reuse (keep visible)
    tracker.update_slot(slot1, FileStatus.COMPLETE)
    tracker.release_slot_keep_visible(slot1)

    # File1 should still be visible as completed
    display_files = tracker.get_display_files()
    assert len(display_files) == 2
    completed_count = len([f for f in display_files if f.status == FileStatus.COMPLETE])
    assert completed_count == 1

    # Should be able to start file3 (reusing slot1)
    file3_data = FileData(
        filename=files_to_process[2].name, file_size=3000, status=FileStatus.STARTING
    )
    slot3 = tracker.acquire_slot(file3_data)
    assert slot3 == slot1  # Reused slot1

    # Now file3 should be in slot1 position (file1 replaced), file2 still processing
    display_files = tracker.get_display_files()
    file_names = [f.filename for f in display_files]
    assert "file3.py" in file_names
    assert "file2.py" in file_names
    assert "file1.py" not in file_names  # Replaced by file3

    # Continue with file2 completion
    tracker.update_slot(slot2, FileStatus.COMPLETE)
    tracker.release_slot_keep_visible(slot2)

    # Now we have: file3 (processing in slot1) + file2 (completed in slot2)
    display_files = tracker.get_display_files()
    completed_count = len([f for f in display_files if f.status == FileStatus.COMPLETE])
    assert completed_count == 1  # Only file2 is completed (file1 was replaced by file3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
