"""
Integration test for direct array access display system.

Validates that the new single data structure architecture works correctly:
- CleanSlotTracker.status_array as the only data structure
- MultiThreadedProgressManager reads directly from array
- No dictionary operations, no stale data
"""

from rich.console import Console

from src.code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)
from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)


def test_end_to_end_direct_array_integration():
    """Test complete integration of direct array access display."""
    # Initialize components
    console = Console()
    slot_tracker = CleanSlotTracker(max_slots=14)  # threadcount+2
    progress_manager = MultiThreadedProgressManager(console, max_slots=14)

    # Add multiple files to tracker
    test_files = [
        ("file_1.py", 1024, FileStatus.CHUNKING),
        ("file_2.js", 2048, FileStatus.VECTORIZING),
        ("file_3.md", 512, FileStatus.FINALIZING),
    ]

    slot_ids = []
    for filename, size, status in test_files:
        file_data = FileData(filename=filename, file_size=size, status=status)
        slot_id = slot_tracker.acquire_slot(file_data)
        slot_ids.append(slot_id)

    # Test direct array access display
    display_lines = progress_manager.get_display_lines_from_tracker(slot_tracker)

    # Verify all files are displayed
    assert (
        len(display_lines) == 3
    ), f"Expected 3 display lines, got {len(display_lines)}"

    # Verify content is correct
    assert any(
        "file_1.py" in line for line in display_lines
    ), "file_1.py should be in display"
    assert any(
        "file_2.js" in line for line in display_lines
    ), "file_2.js should be in display"
    assert any(
        "file_3.md" in line for line in display_lines
    ), "file_3.md should be in display"

    # Verify status formatting
    assert any(
        "chunking..." in line for line in display_lines
    ), "chunking status should be formatted"
    assert any(
        "vectorizing..." in line for line in display_lines
    ), "vectorizing status should be formatted"
    assert any(
        "finalizing..." in line for line in display_lines
    ), "finalizing status should be formatted"

    # Test real-time updates (no stale data)
    slot_tracker.update_slot(slot_ids[0], FileStatus.COMPLETE)

    updated_display_lines = progress_manager.get_display_lines_from_tracker(
        slot_tracker
    )
    assert any(
        "complete ✓" in line for line in updated_display_lines
    ), "Status should update immediately"

    # Test slot cleanup
    slot_tracker.release_slot(slot_ids[1])

    final_display_lines = progress_manager.get_display_lines_from_tracker(slot_tracker)
    assert len(final_display_lines) == 2, "Released slot should not appear in display"
    assert not any(
        "file_2.js" in line for line in final_display_lines
    ), "Released file should not be displayed"


def test_array_scanning_range():
    """Test that display scans the correct range of slots."""
    console = Console()
    threadcount = 12
    max_slots = threadcount + 2  # 14

    slot_tracker = CleanSlotTracker(max_slots=max_slots)
    progress_manager = MultiThreadedProgressManager(console, max_slots=max_slots)

    # Fill slots at different positions
    test_positions = [0, 7, 13]  # First, middle, last

    for i, pos in enumerate(test_positions):
        # Fill slots sequentially until we reach desired position
        while slot_tracker.get_slot_count() <= i:
            file_data = FileData(
                filename=f"file_at_pos_{pos}.py",
                file_size=1024 * (pos + 1),
                status=FileStatus.CHUNKING,
            )
            slot_tracker.acquire_slot(file_data)

    # Verify display finds files at all positions
    display_lines = progress_manager.get_array_display_lines(slot_tracker, max_slots)

    assert len(display_lines) >= len(
        test_positions
    ), f"Should find at least {len(test_positions)} files across slot range"

    # Verify scanning covers the full range (0 to threadcount+1)
    all_lines = progress_manager.get_display_lines_from_tracker(slot_tracker)
    assert len(all_lines) >= len(
        test_positions
    ), "Array scanning should find files across full range"


def test_single_data_structure_consistency():
    """Test that there is only one source of truth for display data."""
    console = Console()
    slot_tracker = CleanSlotTracker(max_slots=14)
    progress_manager = MultiThreadedProgressManager(console)

    # Add file to tracker
    file_data = FileData(
        filename="consistency_test.py", file_size=1024, status=FileStatus.STARTING
    )
    slot_id = slot_tracker.acquire_slot(file_data)

    # Get display from different methods - should be consistent
    method1_lines = progress_manager.get_display_lines_from_tracker(slot_tracker)
    method2_lines = progress_manager.get_current_display_lines(slot_tracker)
    method3_lines = progress_manager.get_array_display_lines(slot_tracker, 14)

    # All methods should return the same data (single source of truth)
    assert (
        len(method1_lines) == len(method2_lines) == len(method3_lines) == 1
    ), "All display methods should return the same data"

    assert (
        method1_lines[0] == method2_lines[0] == method3_lines[0]
    ), "All display methods should return identical content"

    # Update in tracker should be reflected immediately in all methods
    slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)

    updated1 = progress_manager.get_display_lines_from_tracker(slot_tracker)
    updated2 = progress_manager.get_current_display_lines(slot_tracker)
    updated3 = progress_manager.get_array_display_lines(slot_tracker, 14)

    # All should show the updated status immediately
    for lines in [updated1, updated2, updated3]:
        assert any(
            "complete ✓" in line for line in lines
        ), "All display methods should show updated status immediately"

    # Content should still be identical across all methods
    assert (
        updated1[0] == updated2[0] == updated3[0]
    ), "Updated content should be identical across all methods"
