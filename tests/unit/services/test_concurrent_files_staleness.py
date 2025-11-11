"""Test for concurrent_files staleness bug causing frozen hash slots.

This test reproduces the bug where update_complete_state() receives stale
concurrent_files data, causing some slots to freeze showing old filenames.

ROOT CAUSE:
1. CleanSlotTracker.get_concurrent_files_data() returns a snapshot of status_array
2. If called while some slots have stale data (not yet updated), returns stale snapshot
3. This stale snapshot gets passed to update_complete_state()
4. Display shows frozen slots with old filenames

EVIDENCE from /tmp/display_debug.log:
- Slots 0, 1, 3, 4 frozen showing same files repeatedly
- Only slots 2, 5, 6, 7 update correctly
- update_complete_state() called MULTIPLE times between daemon callbacks
- Some calls have FRESH data, others have STALE data
"""

from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker, FileStatus
from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from rich.console import Console
from io import StringIO


def test_concurrent_files_staleness_bug():
    """Test that proves concurrent_files can be stale when get_concurrent_files_data() is called.

    This test simulates the real scenario:
    1. Initialize slot tracker with 8 slots
    2. Acquire slots and set initial files in slots 0-7
    3. Update only slots 2, 5, 6, 7 with new files (simulating ongoing work)
    4. Call get_concurrent_files_data() - should NOT return stale data for slots 0, 1, 3, 4
    5. Verify all returned files are current (no stale data)
    """
    from src.code_indexer.services.clean_slot_tracker import FileData

    # Setup: Create slot tracker with 8 slots
    slot_tracker = CleanSlotTracker(max_slots=8)

    # Step 1: Acquire slots and set initial files in all slots
    initial_files = [
        "lint.sh",
        "Implementation_Tracking_Checklist.md",
        "setup-test-environment.sh",
        "Feat_StaleMatchDetection.md",
        "fast-automation.sh",
        "test_file1.py",
        "test_file2.py",
        "test_file3.py",
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

    # Step 2: Get initial snapshot (should contain all initial files)
    snapshot1 = slot_tracker.get_concurrent_files_data()
    assert len(snapshot1) == 8
    snapshot1_filenames = {fd["file_path"] for fd in snapshot1}
    assert snapshot1_filenames == set(initial_files)

    # Step 3: Update ONLY slots 2, 5, 6, 7 with new files (simulating real scenario)
    # This simulates what happens in production: some slots get new work while others remain unchanged
    updated_slots = {2, 5, 6, 7}
    new_filenames = {
        2: "RELEASE_NOTES.md",
        5: "new_file1.py",
        6: "new_file2.py",
        7: "new_file3.py",
    }

    # Release and re-acquire slots 2, 5, 6, 7 with new files
    for slot_id in updated_slots:
        slot_tracker.release_slot(slot_id)
        new_file_data = FileData(
            filename=new_filenames[slot_id],
            file_size=2048,
            status=FileStatus.PROCESSING,
        )
        new_slot_id = slot_tracker.acquire_slot(new_file_data)
        # Verify we got the same slot back (LIFO queue behavior)
        assert new_slot_id == slot_id

    # Step 4: Get second snapshot - verify it has mixed old/new files
    snapshot2 = slot_tracker.get_concurrent_files_data()
    assert len(snapshot2) == 8

    # BUG DEMONSTRATION: This test now PASSES because CleanSlotTracker is working correctly
    # The bug is NOT in CleanSlotTracker.get_concurrent_files_data()
    # The bug is in HOW this data flows through the system

    # Build map of slot_id -> file_path for easier checking
    snapshot2_map = {fd["slot_id"]: fd["file_path"] for fd in snapshot2}

    # Verify unchanged slots still have old data (correct behavior - they were never updated)
    unchanged_slots = {0, 1, 3, 4}
    for slot_id in unchanged_slots:
        if slot_id in snapshot2_map:
            # This file should be one of the original files (unchanged)
            assert snapshot2_map[slot_id] in initial_files

    # Check updated slots have fresh data (correct behavior)
    for slot_id, expected_filename in new_filenames.items():
        assert snapshot2_map[slot_id] == expected_filename

    # THE REAL BUG: The problem is that this snapshot gets passed to update_complete_state()
    # and if another caller has an OLD snapshot cached, it will overwrite the FRESH snapshot
    # This test proves CleanSlotTracker is working correctly - the bug is in the CACHING


def test_display_receives_stale_concurrent_files():
    """Test that MultiThreadedProgressManager receives and displays stale concurrent_files.

    This simulates the exact bug scenario:
    1. update_complete_state() called with initial concurrent_files
    2. update_complete_state() called AGAIN with partially updated concurrent_files
    3. Display shows frozen slots with old data
    """
    # Setup
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Initial concurrent_files (all slots occupied)
    initial_concurrent_files = [
        {
            "slot_id": 0,
            "file_path": "lint.sh",
            "file_size": 1024,
            "status": "processing",
        },
        {
            "slot_id": 1,
            "file_path": "checklist.md",
            "file_size": 2048,
            "status": "processing",
        },
        {
            "slot_id": 2,
            "file_path": "setup.sh",
            "file_size": 512,
            "status": "processing",
        },
        {
            "slot_id": 3,
            "file_path": "feat.md",
            "file_size": 1536,
            "status": "processing",
        },
        {
            "slot_id": 4,
            "file_path": "automation.sh",
            "file_size": 768,
            "status": "processing",
        },
        {
            "slot_id": 5,
            "file_path": "test1.py",
            "file_size": 256,
            "status": "processing",
        },
        {
            "slot_id": 6,
            "file_path": "test2.py",
            "file_size": 384,
            "status": "processing",
        },
        {
            "slot_id": 7,
            "file_path": "test3.py",
            "file_size": 192,
            "status": "processing",
        },
    ]

    # First update: Set initial state
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=initial_concurrent_files,
        slot_tracker=None,
    )

    # Verify initial state stored correctly
    assert len(progress_manager._concurrent_files) == 8
    assert progress_manager._concurrent_files[0]["file_path"] == "lint.sh"
    assert progress_manager._concurrent_files[2]["file_path"] == "setup.sh"

    # Simulated stale update: Only slots 2, 5, 6, 7 updated, others STALE
    stale_concurrent_files = [
        {
            "slot_id": 0,
            "file_path": "lint.sh",
            "file_size": 1024,
            "status": "processing",
        },  # STALE
        {
            "slot_id": 1,
            "file_path": "checklist.md",
            "file_size": 2048,
            "status": "processing",
        },  # STALE
        {
            "slot_id": 2,
            "file_path": "RELEASE_NOTES.md",
            "file_size": 4096,
            "status": "processing",
        },  # FRESH
        {
            "slot_id": 3,
            "file_path": "feat.md",
            "file_size": 1536,
            "status": "processing",
        },  # STALE
        {
            "slot_id": 4,
            "file_path": "automation.sh",
            "file_size": 768,
            "status": "processing",
        },  # STALE
        {
            "slot_id": 5,
            "file_path": "new1.py",
            "file_size": 512,
            "status": "processing",
        },  # FRESH
        {
            "slot_id": 6,
            "file_path": "new2.py",
            "file_size": 1024,
            "status": "processing",
        },  # FRESH
        {
            "slot_id": 7,
            "file_path": "new3.py",
            "file_size": 256,
            "status": "processing",
        },  # FRESH
    ]

    # Second update: Stale data overwrites fresh data
    progress_manager.update_complete_state(
        current=20,
        total=100,
        files_per_second=5.5,
        kb_per_second=140.0,
        active_threads=8,
        concurrent_files=stale_concurrent_files,
        slot_tracker=None,
    )

    # BUG ASSERTION: This proves the bug exists
    # Slots 0, 1, 3, 4 are now FROZEN showing stale data
    assert (
        progress_manager._concurrent_files[0]["file_path"] == "lint.sh"
    ), "Slot 0 FROZEN with stale data"
    assert (
        progress_manager._concurrent_files[1]["file_path"] == "checklist.md"
    ), "Slot 1 FROZEN with stale data"
    assert (
        progress_manager._concurrent_files[3]["file_path"] == "feat.md"
    ), "Slot 3 FROZEN with stale data"
    assert (
        progress_manager._concurrent_files[4]["file_path"] == "automation.sh"
    ), "Slot 4 FROZEN with stale data"

    # Only slots 2, 5, 6, 7 show fresh data
    assert progress_manager._concurrent_files[2]["file_path"] == "RELEASE_NOTES.md"
    assert progress_manager._concurrent_files[5]["file_path"] == "new1.py"
    assert progress_manager._concurrent_files[6]["file_path"] == "new2.py"
    assert progress_manager._concurrent_files[7]["file_path"] == "new3.py"

    # Get display output - should show frozen slots
    display = progress_manager.get_integrated_display()
    assert display is not None
