"""
Unit tests for CleanSlotTracker.
Tests the clean slot-based file tracking system.
"""

import threading
import time

from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileStatus,
    FileData,
)


class TestFileStatus:
    """Test FileStatus enum."""

    def test_file_status_enum_values(self):
        """Test all expected FileStatus enum values exist."""
        assert FileStatus.STARTING.value == "starting"
        assert FileStatus.CHUNKING.value == "chunking"
        assert FileStatus.VECTORIZING.value == "vectorizing"
        assert FileStatus.FINALIZING.value == "finalizing"
        assert FileStatus.COMPLETE.value == "complete"


class TestFileData:
    """Test FileData dataclass."""

    def test_file_data_creation(self):
        """Test FileData dataclass creation."""
        data = FileData(
            filename="test.py",
            file_size=1024,
            status=FileStatus.STARTING,
            start_time=123456.789,
            last_updated=123456.789,
        )

        assert data.filename == "test.py"
        assert data.file_size == 1024
        assert data.status == FileStatus.STARTING
        assert data.start_time == 123456.789
        assert data.last_updated == 123456.789


class TestCleanSlotTracker:
    """Test CleanSlotTracker class."""

    def test_initialization(self):
        """Test tracker initialization with correct slot allocation."""
        max_slots = 5
        tracker = CleanSlotTracker(max_slots)

        assert tracker.max_slots == max_slots
        assert len(tracker.status_array) == max_slots
        assert all(slot is None for slot in tracker.status_array)
        assert tracker.available_slots.qsize() == max_slots

    def test_acquire_slot_success(self):
        """Test successful slot acquisition."""
        tracker = CleanSlotTracker(3)

        file_data = FileData(
            filename="test.py",
            file_size=1024,
            status=FileStatus.STARTING,
        )
        slot_id = tracker.acquire_slot(file_data)

        # Should get slot 0, 1, or 2
        assert slot_id in [0, 1, 2]
        assert tracker.available_slots.qsize() == 2  # One less available

        # Check status array
        stored_data = tracker.status_array[slot_id]
        assert stored_data is not None
        assert stored_data.filename == "test.py"
        assert stored_data.status == FileStatus.STARTING
        assert stored_data.file_size == 1024
        assert stored_data.start_time > 0
        assert stored_data.last_updated > 0

    def test_acquire_multiple_slots(self):
        """Test acquiring multiple slots sequentially."""
        tracker = CleanSlotTracker(3)

        file1_data = FileData(
            filename="file1.py", file_size=100, status=FileStatus.STARTING
        )
        file2_data = FileData(
            filename="file2.py", file_size=200, status=FileStatus.STARTING
        )
        file3_data = FileData(
            filename="file3.py", file_size=300, status=FileStatus.STARTING
        )

        slot1 = tracker.acquire_slot(file1_data)
        slot2 = tracker.acquire_slot(file2_data)
        slot3 = tracker.acquire_slot(file3_data)

        # All slots should be different
        slots = {slot1, slot2, slot3}
        assert len(slots) == 3
        assert slots == {0, 1, 2}

        # All slots should be occupied
        assert tracker.available_slots.qsize() == 0

        # Check all status array entries
        for slot_id in [slot1, slot2, slot3]:
            assert tracker.status_array[slot_id] is not None

    def test_acquire_slot_blocking_behavior(self):
        """Test that slot acquisition blocks when all slots are taken."""
        tracker = CleanSlotTracker(2)  # Only 2 slots

        # Fill both slots
        file1_data = FileData(
            filename="file1.py", file_size=100, status=FileStatus.STARTING
        )
        file2_data = FileData(
            filename="file2.py", file_size=200, status=FileStatus.STARTING
        )

        tracker.acquire_slot(file1_data)
        tracker.acquire_slot(file2_data)

        assert tracker.available_slots.qsize() == 0

        # Test that acquisition would block by using a timeout
        # We test this indirectly by verifying queue is empty
        result = tracker.available_slots.empty()
        assert result

        # Release a slot and verify it becomes available
        tracker.release_slot(0)  # Release by slot_id
        assert tracker.available_slots.qsize() == 1

    def test_update_slot_success(self):
        """Test successful slot status update."""
        tracker = CleanSlotTracker(3)

        # Acquire slot first
        file_data = FileData(
            filename="test.py", file_size=1024, status=FileStatus.STARTING
        )
        slot_id = tracker.acquire_slot(file_data)
        original_time = tracker.status_array[slot_id].last_updated

        # Small delay to ensure different timestamps
        time.sleep(0.01)

        # Update status
        tracker.update_slot(slot_id, FileStatus.CHUNKING)

        # Verify update
        updated_data = tracker.status_array[slot_id]
        assert updated_data.status == FileStatus.CHUNKING
        assert updated_data.last_updated > original_time

    def test_update_slot_nonexistent_slot(self):
        """Test updating status for empty slot does nothing."""
        tracker = CleanSlotTracker(3)

        # Should not crash
        tracker.update_slot(0, FileStatus.CHUNKING)

        # Tracker should remain unchanged - slot 0 should still be None
        assert tracker.status_array[0] is None

    def test_release_slot_success(self):
        """Test successful slot release."""
        tracker = CleanSlotTracker(3)

        # Acquire slot
        file_data = FileData(
            filename="test.py", file_size=1024, status=FileStatus.STARTING
        )
        slot_id = tracker.acquire_slot(file_data)
        assert tracker.available_slots.qsize() == 2

        # Release slot
        tracker.release_slot(slot_id)

        # Verify slot is released
        assert tracker.available_slots.qsize() == 3
        assert tracker.status_array[slot_id] is None

    def test_release_slot_already_empty(self):
        """Test releasing already empty slot does nothing harmful."""
        tracker = CleanSlotTracker(3)

        initial_available = tracker.available_slots.qsize()

        # Release already empty slot
        tracker.release_slot(0)

        # Available count should increase (slot gets returned to pool)
        assert tracker.available_slots.qsize() == initial_available + 1
        assert tracker.status_array[0] is None

    def test_get_display_files_empty(self):
        """Test getting display files when no files are active."""
        tracker = CleanSlotTracker(3)

        active_files = tracker.get_display_files()

        assert active_files == []

    def test_get_display_files_with_active_files(self):
        """Test getting display files with active files."""
        tracker = CleanSlotTracker(3)

        # Acquire multiple slots
        file1_data = FileData(
            filename="file1.py", file_size=100, status=FileStatus.STARTING
        )
        file2_data = FileData(
            filename="file2.py", file_size=200, status=FileStatus.STARTING
        )

        tracker.acquire_slot(file1_data)
        tracker.acquire_slot(file2_data)

        active_files = tracker.get_display_files()

        assert len(active_files) == 2
        filenames = {f.filename for f in active_files}
        assert filenames == {"file1.py", "file2.py"}

        # All should be in STARTING status
        statuses = {f.status for f in active_files}
        assert statuses == {FileStatus.STARTING}

    def test_thread_safety_concurrent_acquisition(self):
        """Test thread safety during concurrent slot acquisition."""
        tracker = CleanSlotTracker(10)  # Enough slots for test
        acquired_slots = []
        errors = []

        def acquire_slot_worker(filename: str, thread_num: int):
            try:
                file_data = FileData(
                    filename=f"{filename}.py",
                    file_size=1024,
                    status=FileStatus.STARTING,
                )
                slot_id = tracker.acquire_slot(file_data)
                acquired_slots.append((filename, slot_id))
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=acquire_slot_worker, args=(f"file{i}", i))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0
        assert len(acquired_slots) == 5

        # All slots should be unique
        slot_ids = [slot_id for _, slot_id in acquired_slots]
        assert len(set(slot_ids)) == 5

    def test_thread_safety_concurrent_updates(self):
        """Test thread safety during concurrent status updates."""
        tracker = CleanSlotTracker(3)

        # Pre-acquire some slots
        file1_data = FileData(
            filename="file1.py", file_size=100, status=FileStatus.STARTING
        )
        file2_data = FileData(
            filename="file2.py", file_size=200, status=FileStatus.STARTING
        )
        file3_data = FileData(
            filename="file3.py", file_size=300, status=FileStatus.STARTING
        )

        slot1 = tracker.acquire_slot(file1_data)
        slot2 = tracker.acquire_slot(file2_data)
        slot3 = tracker.acquire_slot(file3_data)

        errors = []

        def update_worker(slot_id: int, status: FileStatus):
            try:
                for _ in range(10):  # Multiple updates
                    tracker.update_slot(slot_id, status)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Create threads for concurrent updates
        threads = []
        statuses = [FileStatus.CHUNKING, FileStatus.VECTORIZING, FileStatus.FINALIZING]
        slot_ids = [slot1, slot2, slot3]

        for slot_id, status in zip(slot_ids, statuses):
            thread = threading.Thread(target=update_worker, args=(slot_id, status))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert len(errors) == 0

        # Verify final states
        active_files = tracker.get_display_files()
        assert len(active_files) == 3

    def test_full_lifecycle_workflow(self):
        """Test complete file processing lifecycle."""
        tracker = CleanSlotTracker(2)

        # Acquire slot
        file_data = FileData(
            filename="test_file.py", file_size=2048, status=FileStatus.STARTING
        )
        slot_id = tracker.acquire_slot(file_data)

        # Verify initial state
        initial_data = tracker.status_array[slot_id]
        assert initial_data.status == FileStatus.STARTING

        # Progress through all states
        statuses = [
            FileStatus.CHUNKING,
            FileStatus.VECTORIZING,
            FileStatus.FINALIZING,
            FileStatus.COMPLETE,
        ]

        for status in statuses:
            tracker.update_slot(slot_id, status)
            updated_data = tracker.status_array[slot_id]
            assert updated_data.status == status

        # Release slot
        tracker.release_slot(slot_id)

        # Verify cleanup
        assert tracker.status_array[slot_id] is None
        assert tracker.available_slots.qsize() == 2
