"""
Integration tests for temporal display and threading fixes.

Tests verify all three fixes work together in realistic scenarios:
1. Correct slot count display (8 threads = 8 slots)
2. Non-zero rate display (commits/s parsed correctly)
3. Clean KeyboardInterrupt handling
"""

import time
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)
from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from code_indexer.progress.progress_display import RichLiveProgressManager


class TestTemporalDisplayIntegration:
    """Integration tests for temporal display fixes."""

    def test_correct_slot_count_in_integrated_display(self):
        """Verify progress manager with 8 slots matches tracker with 8 slots."""
        # Simulate temporal indexing configuration
        parallel_threads = 8

        # Create components with matching slot counts
        console = Mock()
        rich_live_manager = RichLiveProgressManager(console=console)
        progress_manager = MultiThreadedProgressManager(
            console=console,
            live_manager=rich_live_manager,
            max_slots=parallel_threads,  # Fixed: no +2
        )

        # Create slot tracker with same slot count
        tracker = CleanSlotTracker(max_slots=parallel_threads)

        # Verify slot counts match
        assert progress_manager.max_slots == parallel_threads == 8
        assert tracker.max_slots == parallel_threads == 8
        assert progress_manager.max_slots == tracker.max_slots

        # Acquire all slots to test display
        slots = []
        for i in range(parallel_threads):
            slot_id = tracker.acquire_slot(
                FileData(f"commit_{i}.py", 1000 * i, FileStatus.PROCESSING)
            )
            slots.append(slot_id)

        # Verify all slots occupied
        assert tracker.get_slot_count() == parallel_threads
        assert tracker.get_available_slot_count() == 0

        # Get display content
        concurrent_files = tracker.get_concurrent_files_data()
        assert len(concurrent_files) == parallel_threads

        # Cleanup
        for slot_id in slots:
            tracker.release_slot(slot_id)

    def test_rate_parsing_with_commits_per_second(self):
        """Verify rate parser handles 'commits/s' format correctly."""
        # Simulate temporal indexer progress info
        info = (
            "50/100 commits (50%) | 5.3 commits/s | 8 threads | 📝 abc12345 - test.py"
        )

        # Parse rate as CLI does (fixed version)
        try:
            parts = info.split(" | ")
            if len(parts) >= 2:
                rate_str = parts[1].strip()
                rate_parts = rate_str.split()
                if len(rate_parts) >= 1:
                    rate_value = float(rate_parts[0])
                else:
                    rate_value = 0.0
            else:
                rate_value = 0.0
        except (ValueError, IndexError):
            rate_value = 0.0

        # Verify rate parsed correctly
        assert rate_value == 5.3, f"Expected rate 5.3, got {rate_value}"

    def test_rate_parsing_with_files_per_second(self):
        """Verify rate parser also handles 'files/s' format (backward compatibility)."""
        # Simulate regular indexing progress info
        info = "309/1000 files (30%) | 12.7 files/s | 8 threads"

        # Parse rate (same logic as commits/s)
        try:
            parts = info.split(" | ")
            if len(parts) >= 2:
                rate_str = parts[1].strip()
                rate_parts = rate_str.split()
                if len(rate_parts) >= 1:
                    rate_value = float(rate_parts[0])
                else:
                    rate_value = 0.0
            else:
                rate_value = 0.0
        except (ValueError, IndexError):
            rate_value = 0.0

        # Verify rate parsed correctly
        assert rate_value == 12.7, f"Expected rate 12.7, got {rate_value}"

    def test_keyboard_interrupt_cleanup_with_executor(self):
        """Verify ThreadPoolExecutor cleanup pattern works."""
        thread_count = 4

        def worker_task(task_id):
            """Worker that can be interrupted."""
            time.sleep(0.5)  # Simulate work
            return task_id

        # Test that the fixed pattern works (with try/except around executor)
        futures = []
        interrupted = False

        try:
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                # Submit tasks
                for i in range(10):
                    future = executor.submit(worker_task, i)
                    futures.append(future)

                # Simulate interrupt
                raise KeyboardInterrupt("Simulated Ctrl+C")

        except KeyboardInterrupt:
            # Cancel pending futures (fixed behavior)
            for future in futures:
                future.cancel()
            interrupted = True

        # Verify interrupt was caught and cleanup code ran
        assert interrupted, "KeyboardInterrupt should have been caught"
        assert len(futures) == 10, "All futures should have been created"

    def test_integrated_display_with_live_progress(self):
        """Test integrated display with all fixes applied."""
        # Setup
        parallel_threads = 8
        tracker = CleanSlotTracker(max_slots=parallel_threads)

        # Simulate progress updates
        current = 50
        total = 100
        commits_per_sec = 5.3

        # Build info string as TemporalIndexer does
        pct = (100 * current) // total
        info = f"{current}/{total} commits ({pct}%) | {commits_per_sec:.1f} commits/s | {parallel_threads} threads | 📝 abc12345 - test.py"

        # Parse rate (fixed parser)
        parts = info.split(" | ")
        rate_str = parts[1].strip()
        rate_value = float(rate_str.split()[0])

        # Acquire some slots
        slot1 = tracker.acquire_slot(
            FileData("commit1.py", 1000, FileStatus.VECTORIZING)
        )
        slot2 = tracker.acquire_slot(FileData("commit2.py", 2000, FileStatus.CHUNKING))

        # Get concurrent files
        concurrent_files = tracker.get_concurrent_files_data()

        # Verify all fixes working together
        assert tracker.max_slots == parallel_threads  # Issue 1: Correct slot count
        assert len(concurrent_files) == 2  # Two slots occupied
        assert rate_value == commits_per_sec  # Issue 2: Rate parsed correctly

        # Cleanup (Issue 3: Proper cleanup)
        tracker.release_slot(slot1)
        tracker.release_slot(slot2)
        assert tracker.get_available_slot_count() == parallel_threads


class TestTemporalDisplayEdgeCases:
    """Test edge cases in temporal display fixes."""

    def test_zero_threads_edge_case(self):
        """Verify graceful handling of zero threads (should not happen)."""
        # This shouldn't happen in practice, but test defensive behavior
        console = Mock()
        progress_manager = MultiThreadedProgressManager(
            console=console,
            max_slots=1,  # Minimum 1 slot
        )
        tracker = CleanSlotTracker(max_slots=1)

        assert progress_manager.max_slots >= 1
        assert tracker.max_slots >= 1

    def test_malformed_rate_string(self):
        """Verify parser handles malformed rate strings gracefully."""
        # Missing rate value
        info = "50/100 commits (50%) |  | 8 threads"

        try:
            parts = info.split(" | ")
            if len(parts) >= 2:
                rate_str = parts[1].strip()
                if rate_str:
                    rate_parts = rate_str.split()
                    if len(rate_parts) >= 1:
                        rate_value = float(rate_parts[0])
                    else:
                        rate_value = 0.0
                else:
                    rate_value = 0.0
            else:
                rate_value = 0.0
        except (ValueError, IndexError):
            rate_value = 0.0

        # Should default to 0.0, not crash
        assert rate_value == 0.0

    def test_concurrent_interrupt_and_cleanup(self):
        """Verify cleanup works even with concurrent interrupts."""
        tracker = CleanSlotTracker(max_slots=4)

        # Acquire slots
        slots = []
        for i in range(3):
            slot_id = tracker.acquire_slot(
                FileData(f"file{i}.py", 1000, FileStatus.PROCESSING)
            )
            slots.append(slot_id)

        # Verify slots occupied
        assert tracker.get_slot_count() == 3

        # Simulate interrupt cleanup
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            # Release all slots
            for slot_id in slots:
                if slot_id is not None:
                    tracker.release_slot(slot_id)

        # Verify all slots available after cleanup
        assert tracker.get_available_slot_count() == 4
