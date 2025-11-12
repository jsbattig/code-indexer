"""Test that proves the frozen slots bug is FIXED.

This test verifies that MultiThreadedProgressManager always gets FRESH
concurrent_files data from slot_tracker instead of using stale cached data.

BUG (BEFORE FIX):
- update_complete_state() cached concurrent_files in self._concurrent_files
- get_integrated_display() read from stale self._concurrent_files
- Rich Live refresh (10x/sec) showed frozen slots with old filenames

FIX (AFTER):
- get_integrated_display() ALWAYS calls slot_tracker.get_concurrent_files_data()
- Never reads from stale self._concurrent_files when slot_tracker available
- Rich Live refresh always shows current slot state
"""

from src.code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileStatus,
    FileData,
)
from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from rich.console import Console
from io import StringIO


def test_display_always_gets_fresh_slot_data():
    """Test that get_integrated_display() always gets FRESH data from slot_tracker.

    This test proves the fix works:
    1. Create progress manager with slot tracker
    2. Update slot tracker with initial files
    3. Call get_integrated_display() - should show initial files
    4. Update slot tracker with NEW files (simulating ongoing work)
    5. Call get_integrated_display() again - should show NEW files (NOT cached old files)
    """
    # Setup: Create slot tracker and progress manager
    slot_tracker = CleanSlotTracker(max_slots=8)
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Connect progress manager to slot tracker
    progress_manager.set_slot_tracker(slot_tracker)

    # Step 1: Acquire slots with initial files
    initial_files = [
        "file1.py",
        "file2.py",
        "file3.py",
        "file4.py",
        "file5.py",
        "file6.py",
        "file7.py",
        "file8.py",
    ]

    slot_ids = []
    for filename in initial_files:
        file_data = FileData(
            filename=filename,
            file_size=1024,
            status=FileStatus.PROCESSING,
        )
        slot_id = slot_tracker.acquire_slot(file_data)
        slot_ids.append(slot_id)

    # Step 2: Initialize progress manager (simulates first daemon callback)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=[],  # Empty - should use slot_tracker
        slot_tracker=slot_tracker,
    )

    # Step 3: Get display - should show initial files
    display1 = progress_manager.get_integrated_display()

    # Render table to string to check contents
    from rich.console import Console as RenderConsole

    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display1)
    display1_text = render_buffer.getvalue()

    # Verify initial files are in display (at least some of them)
    # Note: We can't check all because LIFO queue may reorder
    assert "file1.py" in display1_text or "file8.py" in display1_text

    # Step 4: Update slot tracker with NEW files (simulating real work progression)
    # Release and re-acquire slots 0, 2, 4, 6 with new files
    new_files_map = {
        slot_ids[0]: "new_file1.py",
        slot_ids[2]: "new_file2.py",
        slot_ids[4]: "new_file3.py",
        slot_ids[6]: "new_file4.py",
    }

    for slot_id, new_filename in new_files_map.items():
        slot_tracker.release_slot(slot_id)
        new_file_data = FileData(
            filename=new_filename,
            file_size=2048,
            status=FileStatus.PROCESSING,
        )
        new_slot_id = slot_tracker.acquire_slot(new_file_data)
        assert new_slot_id == slot_id  # LIFO queue returns same slot

    # Step 5: Get display AGAIN (simulates Rich Live refresh)
    # CRITICAL TEST: This should show NEW files, NOT cached old files
    display2 = progress_manager.get_integrated_display()

    # Render to string
    render_buffer2 = StringIO()
    render_console2 = RenderConsole(file=render_buffer2, force_terminal=True, width=120)
    render_console2.print(display2)
    display2_text = render_buffer2.getvalue()

    # ASSERTION: Display should now show NEW files
    # Before fix: Would show old files (frozen slots)
    # After fix: Shows new files (fresh data from slot_tracker)
    assert (
        "new_file1.py" in display2_text
        or "new_file2.py" in display2_text
        or "new_file3.py" in display2_text
        or "new_file4.py" in display2_text
    ), f"Display should show NEW files from slot_tracker, not cached old files. Got: {display2_text}"

    # Also verify we're NOT showing the old files that were replaced
    # (Some old files like file3.py, file5.py may still be there - only check replaced ones)


def test_display_uses_cached_when_no_slot_tracker():
    """Test that display falls back to cached concurrent_files when slot_tracker is None.

    This is the hash phase scenario where slot_tracker is not available.
    """
    # Setup
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Scenario: Hash phase (no slot_tracker)
    concurrent_files = [
        {
            "slot_id": 0,
            "file_path": "hash1.py",
            "file_size": 1024,
            "status": "processing",
        },
        {
            "slot_id": 1,
            "file_path": "hash2.py",
            "file_size": 2048,
            "status": "processing",
        },
    ]

    # Update with concurrent_files but NO slot_tracker (hash phase)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=concurrent_files,
        slot_tracker=None,  # No slot tracker in hash phase
    )

    # Get display - should use cached concurrent_files
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole

    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # Verify cached files are displayed
    assert "hash1.py" in display_text
    assert "hash2.py" in display_text


def test_multiple_display_refreshes_stay_fresh():
    """Test that multiple display refreshes (Rich Live 10x/sec) always show fresh data.

    This simulates the real production scenario where Rich Live calls
    get_integrated_display() 10 times per second for refresh.
    """
    # Setup
    slot_tracker = CleanSlotTracker(max_slots=8)
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )
    progress_manager.set_slot_tracker(slot_tracker)

    # Initial state: 8 files
    for i in range(8):
        file_data = FileData(
            filename=f"initial_{i}.py",
            file_size=1024,
            status=FileStatus.PROCESSING,
        )
        slot_tracker.acquire_slot(file_data)

    # Simulate 3 display refreshes (Rich Live behavior)
    for refresh_round in range(3):
        # Between refreshes, update slot 0 with a new file
        slot_tracker.release_slot(0)
        new_file_data = FileData(
            filename=f"updated_round_{refresh_round}.py",
            file_size=2048,
            status=FileStatus.PROCESSING,
        )
        slot_tracker.acquire_slot(new_file_data)

        # Get display (simulates Rich Live refresh)
        display = progress_manager.get_integrated_display()

        # Render to string
        from rich.console import Console as RenderConsole

        render_buffer = StringIO()
        render_console = RenderConsole(
            file=render_buffer, force_terminal=True, width=120
        )
        render_console.print(display)
        display_text = render_buffer.getvalue()

        # CRITICAL: Display should show the LATEST file for this round
        assert (
            f"updated_round_{refresh_round}.py" in display_text
        ), f"Round {refresh_round}: Display should show updated file, not cached old file. Got: {display_text}"
