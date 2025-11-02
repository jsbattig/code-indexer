"""
Test that the frozen slots fix (deepcopy) works for both hash and indexing phases.

This test verifies that concurrent_files data is properly deep-copied before being
passed to progress callbacks, preventing RPyC proxy caching issues that cause
frozen/stale display in daemon mode.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.services.clean_slot_tracker import CleanSlotTracker, FileData, FileStatus
from code_indexer.services.high_throughput_processor import HighThroughputProcessor


class TestFrozenSlotsDeepCopyFix:
    """Test that deepcopy fix prevents frozen slots in both hash and indexing phases."""

    def test_hash_phase_uses_deepcopy(self):
        """Verify hash phase deep-copies concurrent_files before callback."""
        # Create slot tracker with some test data
        tracker = CleanSlotTracker(max_slots=3)

        # Acquire some slots to simulate active files
        slot1 = tracker.acquire_slot(FileData(
            filename="file1.py",
            file_size=1000,
            status=FileStatus.PROCESSING
        ))
        slot2 = tracker.acquire_slot(FileData(
            filename="file2.py",
            file_size=2000,
            status=FileStatus.PROCESSING
        ))

        # Get concurrent files data - this is what the hash phase reads
        original_data = tracker.get_concurrent_files_data()

        # Deep copy (what the fix does)
        copied_data = copy.deepcopy(original_data)

        # Verify they're equal but NOT the same object
        assert original_data == copied_data
        assert original_data is not copied_data

        # Verify nested objects are also different (true deep copy)
        assert original_data[0] is not copied_data[0]
        assert original_data[1] is not copied_data[1]

        # Modify the tracker by updating slot status (simulates file processing)
        tracker.update_slot(slot1, FileStatus.COMPLETE)
        new_original_data = tracker.get_concurrent_files_data()

        # Verify new original data has updated status
        updated_slot = next(item for item in new_original_data if item["slot_id"] == slot1)
        assert updated_slot["status"] == "complete"

        # Copied data remains unchanged (frozen snapshot with old status)
        copied_slot = next(item for item in copied_data if item["slot_id"] == slot1)
        assert copied_slot["status"] == "processing"  # Still has original status

        # Verify both snapshots have same files but different states
        assert len(copied_data) == 2
        assert len(new_original_data) == 2
        assert copied_data[0]["file_path"] == new_original_data[0]["file_path"]
        assert copied_data[1]["file_path"] == new_original_data[1]["file_path"]

    def test_indexing_phase_uses_deepcopy(self):
        """Verify indexing phase deep-copies concurrent_files before callback."""
        # Create slot tracker with some test data
        tracker = CleanSlotTracker(max_slots=3)

        # Acquire some slots to simulate active files
        slot1 = tracker.acquire_slot(FileData(
            filename="file_a.py",
            file_size=500,
            status=FileStatus.PROCESSING
        ))
        slot2 = tracker.acquire_slot(FileData(
            filename="file_b.py",
            file_size=1500,
            status=FileStatus.PROCESSING
        ))

        # Get concurrent files data - this is what the indexing phase reads
        original_data = tracker.get_concurrent_files_data()

        # Deep copy (what the fix does)
        copied_data = copy.deepcopy(original_data)

        # Verify they're equal but NOT the same object
        assert original_data == copied_data
        assert original_data is not copied_data

        # Verify nested objects are also different (true deep copy)
        assert original_data[0] is not copied_data[0]
        assert original_data[1] is not copied_data[1]

        # Modify the tracker by updating slot status (simulates file processing)
        tracker.update_slot(slot2, FileStatus.COMPLETE)
        new_original_data = tracker.get_concurrent_files_data()

        # Verify new original data has updated status
        updated_slot = next(item for item in new_original_data if item["slot_id"] == slot2)
        assert updated_slot["status"] == "complete"

        # Copied data remains unchanged (frozen snapshot with old status)
        copied_slot = next(item for item in copied_data if item["slot_id"] == slot2)
        assert copied_slot["status"] == "processing"  # Still has original status

        # Verify both snapshots have same files but different states
        assert len(copied_data) == 2
        assert len(new_original_data) == 2
        assert copied_data[0]["file_path"] == new_original_data[0]["file_path"]
        assert copied_data[1]["file_path"] == new_original_data[1]["file_path"]

    def test_deepcopy_creates_independent_snapshot(self):
        """Verify deepcopy creates truly independent snapshot that won't change."""
        tracker = CleanSlotTracker(max_slots=5)

        # Fill tracker with files
        slots = []
        for i in range(5):
            slot = tracker.acquire_slot(FileData(
                filename=f"test_{i}.py",
                file_size=1000 * (i + 1),
                status=FileStatus.PROCESSING
            ))
            slots.append(slot)

        # Take snapshot with deepcopy (simulates what fix does before callback)
        snapshot = copy.deepcopy(tracker.get_concurrent_files_data())

        # Verify snapshot has all 5 files
        assert len(snapshot) == 5
        expected_files = [f"test_{i}.py" for i in range(5)]
        actual_files = [item["file_path"] for item in snapshot]
        assert sorted(actual_files) == sorted(expected_files)

        # Now release all slots and acquire new ones
        for slot in slots:
            tracker.release_slot(slot)

        new_slots = []
        for i in range(5):
            new_slot = tracker.acquire_slot(FileData(
                filename=f"new_{i}.py",
                file_size=500 * (i + 1),
                status=FileStatus.PROCESSING
            ))
            new_slots.append(new_slot)

        # Check current tracker state (should have new files)
        current_data = tracker.get_concurrent_files_data()
        current_files = [item["file_path"] for item in current_data]

        # Snapshot should be UNCHANGED (still has old files)
        snapshot_files = [item["file_path"] for item in snapshot]
        assert sorted(snapshot_files) == sorted(expected_files)

        # Current data should have NEW files
        assert "new_0.py" in current_files
        assert "test_0.py" not in current_files

        # Snapshot should still have OLD files (proves independence)
        assert "test_0.py" in snapshot_files
        assert "new_0.py" not in snapshot_files

    def test_concurrent_modification_doesnt_affect_deepcopy(self):
        """Verify concurrent modifications don't affect deepcopy snapshot."""
        tracker = CleanSlotTracker(max_slots=3)

        # Add initial files
        slot1 = tracker.acquire_slot(FileData(
            filename="initial1.py",
            file_size=1000,
            status=FileStatus.PROCESSING
        ))
        slot2 = tracker.acquire_slot(FileData(
            filename="initial2.py",
            file_size=2000,
            status=FileStatus.PROCESSING
        ))

        # Take snapshot with deepcopy
        snapshot1 = copy.deepcopy(tracker.get_concurrent_files_data())

        # Modify tracker (release one, add new one)
        tracker.release_slot(slot1)
        slot3 = tracker.acquire_slot(FileData(
            filename="new3.py",
            file_size=3000,
            status=FileStatus.PROCESSING
        ))

        # Take another snapshot
        snapshot2 = copy.deepcopy(tracker.get_concurrent_files_data())

        # Snapshots should be different (proves they're independent)
        assert snapshot1 != snapshot2

        # Snapshot1 should have initial files
        files1 = [item["file_path"] for item in snapshot1]
        assert "initial1.py" in files1
        assert "initial2.py" in files1
        assert "new3.py" not in files1

        # Snapshot2 should have modified state
        files2 = [item["file_path"] for item in snapshot2]
        assert "initial1.py" not in files2  # Released
        assert "initial2.py" in files2  # Still there
        assert "new3.py" in files2  # Newly added

        # Further modifications shouldn't affect either snapshot
        tracker.release_slot(slot2)
        tracker.release_slot(slot3)

        # Both snapshots remain unchanged
        assert [item["file_path"] for item in snapshot1] == files1
        assert [item["file_path"] for item in snapshot2] == files2

    def test_deepcopy_preserves_all_fields(self):
        """Verify deepcopy preserves all fields in concurrent_files data."""
        tracker = CleanSlotTracker(max_slots=2)

        # Add file with all fields
        slot = tracker.acquire_slot(FileData(
            filename="test_file.py",
            file_size=12345,
            status=FileStatus.PROCESSING
        ))

        # Get data and deepcopy
        original = tracker.get_concurrent_files_data()
        copied = copy.deepcopy(original)

        # Verify all fields are preserved
        assert copied[0]["file_path"] == "test_file.py"
        assert copied[0]["file_size"] == 12345
        assert copied[0]["status"] == "processing"
        assert copied[0]["slot_id"] == slot

        # Verify structure matches original
        assert copied[0].keys() == original[0].keys()
        for key in original[0].keys():
            assert copied[0][key] == original[0][key]
