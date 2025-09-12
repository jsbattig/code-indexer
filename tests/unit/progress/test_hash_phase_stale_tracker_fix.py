"""Test that verifies hash phase correctly clears stale slot tracker.

This test ensures that when transitioning from indexing phase to hash phase,
any stale slot tracker is cleared so that concurrent_files data is used.
"""

import time
from rich.console import Console

from code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)


class TestHashPhaseStaleTrackerFix:
    """Test suite for hash phase slot tracker clearing fix."""

    def test_stale_slot_tracker_cleared_during_hash_phase(self):
        """Test that stale slot tracker from indexing is cleared during hash phase."""
        # Setup
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=None, max_slots=4
        )

        # Step 1: Simulate indexing phase that sets a slot tracker
        indexing_tracker = CleanSlotTracker(max_slots=4)

        # Add data to indexing tracker
        stale_file = FileData(
            filename="indexed_file.py",
            file_size=1024,
            status=FileStatus.COMPLETE,
            start_time=time.time(),
        )
        slot_id = indexing_tracker.acquire_slot(stale_file)
        indexing_tracker.update_slot(slot_id, FileStatus.COMPLETE)

        # Update with indexing tracker
        progress_manager.update_complete_state(
            current=100,
            total=100,
            files_per_second=10.0,
            kb_per_second=100.0,
            active_threads=4,
            concurrent_files=[],
            slot_tracker=indexing_tracker,
            info="📊 Indexing",
        )

        # Verify tracker was set
        assert progress_manager.slot_tracker is not None
        assert progress_manager.slot_tracker == indexing_tracker

        # Step 2: Simulate hash phase with concurrent_files
        hash_files = [
            {
                "slot_id": 0,
                "file_path": "hash_file1.js",
                "file_size": 2048,
                "status": "processing",
            },
            {
                "slot_id": 1,
                "file_path": "hash_file2.py",
                "file_size": 4096,
                "status": "complete",
            },
        ]

        # Update with hash phase data (slot_tracker=None)
        progress_manager.update_complete_state(
            current=50,
            total=200,
            files_per_second=5.0,
            kb_per_second=50.0,
            active_threads=4,
            concurrent_files=hash_files,
            slot_tracker=None,  # Critical: None during hash phase
            info="🔍 Hashing",
        )

        # Verify fix: tracker should be cleared
        assert progress_manager.slot_tracker is None, "Stale slot tracker not cleared"
        assert (
            len(progress_manager._concurrent_files) == 2
        ), "Concurrent files not stored"
        assert progress_manager._concurrent_files == hash_files

    def test_concurrent_files_used_when_slot_tracker_none(self):
        """Test that concurrent_files data is used when slot_tracker is None."""
        # Setup
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=None, max_slots=4
        )

        # Provide only concurrent_files, no slot_tracker
        concurrent_files = [
            {
                "slot_id": 0,
                "file_path": "test1.py",
                "file_size": 1024,
                "status": "processing",
            },
            {
                "slot_id": 1,
                "file_path": "test2.js",
                "file_size": 2048,
                "status": "complete",
            },
        ]

        progress_manager.update_complete_state(
            current=10,
            total=50,
            files_per_second=2.0,
            kb_per_second=20.0,
            active_threads=2,
            concurrent_files=concurrent_files,
            slot_tracker=None,
            info="🔍 Processing",
        )

        # Verify
        assert progress_manager.slot_tracker is None
        assert progress_manager._concurrent_files == concurrent_files

    def test_slot_tracker_takes_precedence_when_set(self):
        """Test that slot_tracker is used when explicitly set (indexing phase)."""
        # Setup
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=None, max_slots=4
        )

        # Create slot tracker with data
        slot_tracker = CleanSlotTracker(max_slots=4)
        file_data = FileData(
            filename="tracked_file.py",
            file_size=1024,
            status=FileStatus.PROCESSING,
            start_time=time.time(),
        )
        slot_tracker.acquire_slot(file_data)

        # Also provide concurrent_files (should be ignored)
        concurrent_files = [{"file_path": "ignored.py", "status": "processing"}]

        progress_manager.update_complete_state(
            current=10,
            total=50,
            files_per_second=2.0,
            kb_per_second=20.0,
            active_threads=2,
            concurrent_files=concurrent_files,
            slot_tracker=slot_tracker,
            info="📊 Indexing",
        )

        # Verify
        assert progress_manager.slot_tracker == slot_tracker
        assert progress_manager._concurrent_files == concurrent_files
        # Note: Display logic will use slot_tracker over concurrent_files

    def test_phase_detection_from_info_string(self):
        """Test that phase is correctly detected from info string."""
        # Setup
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=None, max_slots=4
        )

        # Test hash phase detection
        progress_manager.update_complete_state(
            current=10,
            total=50,
            files_per_second=1.0,
            kb_per_second=10.0,
            active_threads=2,
            concurrent_files=[],
            slot_tracker=None,
            info="🔍 Hashing files",
        )
        assert progress_manager._current_phase == "🔍 Hashing"

        # Test indexing phase detection
        progress_manager.update_complete_state(
            current=20,
            total=50,
            files_per_second=2.0,
            kb_per_second=20.0,
            active_threads=2,
            concurrent_files=[],
            slot_tracker=None,
            info="📊 Indexing files",
        )
        assert progress_manager._current_phase == "🚀 Indexing"
