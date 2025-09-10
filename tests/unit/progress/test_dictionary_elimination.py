"""
TDD tests for complete elimination of dictionary-based display system.

REQUIREMENTS:
1. ConcurrentFileDisplay class must NOT exist
2. No dictionary operations in display code
3. Display must read CleanSlotTracker array directly
4. Single data structure only - the status_array
"""

from pathlib import Path


def test_concurrent_file_display_class_does_not_exist():
    """FAILING TEST: Verify ConcurrentFileDisplay class is completely deleted."""
    from src.code_indexer.progress import multi_threaded_display

    # This should fail initially - class should not exist after elimination
    assert not hasattr(
        multi_threaded_display, "ConcurrentFileDisplay"
    ), "ConcurrentFileDisplay class must be completely deleted"


def test_file_processing_line_dataclass_does_not_exist():
    """FAILING TEST: Verify FileProcessingLine dataclass is completely deleted."""
    from src.code_indexer.progress import multi_threaded_display

    # This should fail initially - dataclass should not exist after elimination
    assert not hasattr(
        multi_threaded_display, "FileProcessingLine"
    ), "FileProcessingLine dataclass must be completely deleted"


def test_no_dictionary_operations_in_multi_threaded_display():
    """FAILING TEST: Verify no dictionary operations exist in display module."""
    # Read the source file and check for dictionary patterns
    display_file = Path("src/code_indexer/progress/multi_threaded_display.py")
    content = display_file.read_text()

    # Should fail initially - these dictionary patterns should not exist
    forbidden_patterns = [
        "active_lines: Dict",
        "active_lines[",
        ".add_file_line(",
        ".update_file_line(",
        ".remove_file_line(",
        "del self.active_lines",
        "in self.active_lines",
    ]

    found_patterns = []
    for pattern in forbidden_patterns:
        if pattern in content:
            found_patterns.append(pattern)

    assert (
        not found_patterns
    ), f"Dictionary patterns found in display code: {found_patterns}"


def test_multi_threaded_progress_manager_uses_direct_array_access():
    """FAILING TEST: Verify MultiThreadedProgressManager uses direct array access."""
    from src.code_indexer.progress.multi_threaded_display import (
        MultiThreadedProgressManager,
    )
    from rich.console import Console

    # This should fail initially - manager should read from tracker array directly
    console = Console()
    manager = MultiThreadedProgressManager(console)

    # Manager should not have concurrent_display attribute after elimination
    assert not hasattr(
        manager, "concurrent_display"
    ), "MultiThreadedProgressManager must not have concurrent_display attribute"


def test_display_reads_slot_tracker_array_directly():
    """FAILING TEST: Display should read CleanSlotTracker status_array directly."""
    from src.code_indexer.services.clean_slot_tracker import (
        CleanSlotTracker,
        FileData,
        FileStatus,
    )
    from src.code_indexer.progress.multi_threaded_display import (
        MultiThreadedProgressManager,
    )
    from rich.console import Console

    # This should fail initially - display should scan tracker array directly
    tracker = CleanSlotTracker(max_slots=14)  # threadcount+2
    console = Console()
    manager = MultiThreadedProgressManager(console)

    # Add test data to tracker array
    file_data = FileData(filename="test.py", file_size=1024, status=FileStatus.CHUNKING)
    tracker.acquire_slot(file_data)

    # Manager should read tracker array directly to get display lines
    # This method should exist after elimination
    display_lines = manager.get_display_lines_from_tracker(tracker)

    assert len(display_lines) == 1, "Display should read directly from tracker array"
    assert (
        "test.py" in display_lines[0]
    ), "Display line should contain filename from tracker array"


def test_single_data_structure_architecture():
    """FAILING TEST: Only CleanSlotTracker.status_array should exist for tracking AND display."""
    from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker
    from src.code_indexer.progress.multi_threaded_display import (
        MultiThreadedProgressManager,
    )
    from rich.console import Console

    # This should fail initially - only status_array should be used
    tracker = CleanSlotTracker(max_slots=14)
    console = Console()
    manager = MultiThreadedProgressManager(console)

    # Manager should have reference to tracker, not separate display data
    # This should be the architecture after elimination
    manager.slot_tracker = tracker

    # Verify only one data structure exists
    assert hasattr(tracker, "status_array"), "CleanSlotTracker must have status_array"
    assert hasattr(
        manager, "slot_tracker"
    ), "Manager should reference slot_tracker directly"


def test_threadcount_plus_two_array_scanning():
    """FAILING TEST: Display should scan array[0] to array[threadcount+1]."""
    from src.code_indexer.services.clean_slot_tracker import (
        CleanSlotTracker,
        FileData,
        FileStatus,
    )
    from src.code_indexer.progress.multi_threaded_display import (
        MultiThreadedProgressManager,
    )
    from rich.console import Console

    # This should fail initially - simple array scanning should work
    threadcount = 12
    max_slots = threadcount + 2  # 14 slots total

    tracker = CleanSlotTracker(max_slots=max_slots)
    console = Console()
    manager = MultiThreadedProgressManager(console)

    # Fill some slots
    for i in range(3):
        file_data = FileData(
            filename=f"file_{i}.py",
            file_size=1024 * (i + 1),
            status=FileStatus.CHUNKING,
        )
        tracker.acquire_slot(file_data)

    # Manager should scan array directly: for slot_id in range(14)
    display_lines = manager.get_array_display_lines(tracker, max_slots)

    assert (
        len(display_lines) == 3
    ), "Display should find 3 active files by scanning array"

    # Should use simple slot scanning logic
    assert all(
        "file_" in line for line in display_lines
    ), "All display lines should contain file data from array"


def test_no_insert_remove_operations():
    """FAILING TEST: No insert/remove operations should exist in display code."""
    # Read the source file and verify no complex operations
    display_file = Path("src/code_indexer/progress/multi_threaded_display.py")
    content = display_file.read_text()

    # Should fail initially - these operations should be eliminated
    forbidden_operations = [
        "insert(",
        "remove(",
        "add_file_line",
        "update_file_line",
        "remove_file_line",
        "del ",
    ]

    found_operations = []
    for op in forbidden_operations:
        if op in content:
            found_operations.append(op)

    assert (
        not found_operations
    ), f"Complex operations found in display code: {found_operations}"


def test_stale_data_problem_eliminated():
    """FAILING TEST: Stale display data should be impossible with single array."""
    from src.code_indexer.services.clean_slot_tracker import (
        CleanSlotTracker,
        FileData,
        FileStatus,
    )
    from src.code_indexer.progress.multi_threaded_display import (
        MultiThreadedProgressManager,
    )
    from rich.console import Console

    # This should fail initially - stale data should be eliminated
    tracker = CleanSlotTracker(max_slots=14)
    console = Console()
    manager = MultiThreadedProgressManager(console)

    # Add and update file data
    file_data = FileData(filename="test.py", file_size=1024, status=FileStatus.STARTING)
    acquired_slot_id = tracker.acquire_slot(file_data)

    # Update status in tracker
    tracker.update_slot(acquired_slot_id, FileStatus.COMPLETE)

    # Display should immediately reflect the update (no stale data)
    display_lines = manager.get_current_display_lines(tracker)

    assert any(
        "complete" in line.lower() for line in display_lines
    ), "Display should immediately show updated status from tracker array"

    # No separate display data means no stale data possible
    assert not hasattr(
        manager, "active_lines"
    ), "No separate display data structure should exist"
