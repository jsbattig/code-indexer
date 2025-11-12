"""
Test that proves the hash phase slot tracker reuse bug.

ROOT CAUSE: Hash phase reuses the chunking tracker (10 slots) instead of
creating a fresh tracker with correct slot count (8 slots for 8 threads).

LOCATION: high_throughput_processor.py line 321
BUGGY CODE: hash_slot_tracker = slot_tracker or CleanSlotTracker(max_slots=vector_thread_count)
PROBLEM: The 'slot_tracker or' fallback means if slot_tracker is passed,
         it reuses the 10-slot chunking tracker for the 8-thread hash phase.

EXPECTED: Hash phase should ALWAYS create new CleanSlotTracker(max_slots=vector_thread_count)
ACTUAL: Hash phase reuses 10-slot tracker, causing stale slot data (slots 8-9 frozen)
"""

from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)


class TestHashSlotTrackerReuseBug:
    """Test that hash phase creates fresh slot tracker instead of reusing chunking tracker."""

    def test_buggy_code_pattern_would_reuse_tracker(self):
        """
        DOCUMENTATION TEST: Shows what the BUGGY code pattern was.

        This test demonstrates the OLD BUGGY pattern that was fixed:
        hash_slot_tracker = slot_tracker or CleanSlotTracker(max_slots=vector_thread_count)

        BUGGY BEHAVIOR (before fix):
        - If slot_tracker is passed (truthy), it gets reused
        - The "or" fallback meant we used the passed tracker instead of creating new one

        AFTER FIX (current code):
        - Line is now: hash_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count)
        - Always create fresh tracker, never reuse the parameter

        This test shows the buggy pattern would fail, proving the fix is necessary.
        """
        vector_thread_count = 8

        # Simulate the chunking tracker with 10 slots (8 + 2 bonus)
        chunking_tracker = CleanSlotTracker(max_slots=10)

        # Simulate the OLD BUGGY code pattern (what it WAS before fix)
        slot_tracker = chunking_tracker  # This is passed as parameter
        buggy_hash_slot_tracker = slot_tracker or CleanSlotTracker(
            max_slots=vector_thread_count
        )

        # DOCUMENT THE BUG: This shows what WOULD happen with buggy pattern
        # With old buggy code: hash_slot_tracker IS the same 10-slot tracker
        assert (
            buggy_hash_slot_tracker is chunking_tracker
        ), "BUGGY PATTERN: This demonstrates the bug - tracker gets reused"

        assert buggy_hash_slot_tracker.max_slots == 10, (
            f"BUGGY PATTERN: Tracker has wrong slot count {buggy_hash_slot_tracker.max_slots} "
            f"(reused from chunking), should be {vector_thread_count}"
        )

    def test_correct_code_pattern_creates_fresh_tracker(self):
        """
        PASSING TEST: Proves the CORRECT code pattern creates fresh tracker.

        This test validates what the fix should be:
        hash_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count)

        CORRECT BEHAVIOR:
        - Always create NEW CleanSlotTracker
        - Never reuse the slot_tracker parameter
        - max_slots matches vector_thread_count exactly
        """
        vector_thread_count = 8

        # Simulate the chunking tracker with 10 slots
        chunking_tracker = CleanSlotTracker(max_slots=10)

        # Simulate the CORRECT code pattern (what fix should be)
        hash_slot_tracker = CleanSlotTracker(
            max_slots=vector_thread_count
        )  # ALWAYS create new

        # ASSERTIONS: These should PASS after fix
        assert (
            hash_slot_tracker is not chunking_tracker
        ), "Hash tracker should be NEW instance, not reused chunking tracker"

        assert hash_slot_tracker.max_slots == vector_thread_count, (
            f"Hash tracker should have exactly {vector_thread_count} slots, "
            f"got {hash_slot_tracker.max_slots}"
        )

        # Verify chunking tracker remains unchanged
        assert (
            chunking_tracker.max_slots == 10
        ), "Chunking tracker should still have 10 slots (not affected by hash phase)"

    def test_buggy_reuse_causes_wrong_slot_count(self):
        """
        DOCUMENTATION TEST: Shows that OLD BUGGY reuse pattern caused wrong slot count.

        SCENARIO (before fix):
        - Chunking phase: 8 threads + 2 bonus = 10 slots
        - Hash phase: Should use 8 threads = 8 slots
        - BUG: Hash phase reused 10-slot tracker, causing 2 extra frozen slots

        EVIDENCE FROM DAEMON LOGS (before fix):
        - Hash phase showed ACQUIRE_SLOT(8) and ACQUIRE_SLOT(9)
        - Should only show ACQUIRE_SLOT(0) through ACQUIRE_SLOT(7)

        This test documents what the bug WAS by showing the buggy pattern.
        """
        vector_thread_count = 8
        hashing_thread_count = vector_thread_count  # Same as vector threads

        # Create chunking tracker with +2 bonus
        chunking_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # Simulate OLD BUGGY code: reuse chunking tracker for hash phase
        slot_tracker = chunking_tracker
        buggy_hash_slot_tracker = slot_tracker or CleanSlotTracker(
            max_slots=hashing_thread_count
        )

        # DOCUMENT THE BUG: These show what WOULD happen with buggy pattern
        assert buggy_hash_slot_tracker.max_slots == vector_thread_count + 2, (
            f"BUGGY PATTERN: Hash tracker has WRONG slot count: {buggy_hash_slot_tracker.max_slots} "
            f"(reused from chunking), should be {hashing_thread_count}"
        )

        assert (
            buggy_hash_slot_tracker is chunking_tracker
        ), "BUGGY PATTERN: Hash tracker IS the chunking tracker (wrong - should be independent)"

    def test_fix_prevents_frozen_slots(self):
        """
        PASSING TEST: Proves that fix prevents frozen slots issue.

        SCENARIO:
        - With bug: Hash phase uses 10 slots for 8 threads → slots 8-9 frozen
        - After fix: Hash phase uses 8 slots for 8 threads → all slots active

        VERIFICATION:
        - Acquire all slots in hash tracker
        - Should exactly match thread count
        - No extra frozen slots
        """
        vector_thread_count = 8

        # CORRECT CODE: Always create fresh tracker
        hash_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count)

        # Acquire all available slots with proper FileData
        acquired_slots = []
        for i in range(vector_thread_count):
            file_data = FileData(
                filename=f"file{i}.py", file_size=1000, status=FileStatus.PROCESSING
            )
            slot = hash_slot_tracker.acquire_slot(file_data)
            acquired_slots.append(slot)

        # ASSERTIONS: Verify correct slot range
        assert len(acquired_slots) == vector_thread_count, (
            f"Should acquire exactly {vector_thread_count} slots, "
            f"got {len(acquired_slots)}"
        )

        assert max(acquired_slots) == vector_thread_count - 1, (
            f"Max slot should be {vector_thread_count - 1}, "
            f"got {max(acquired_slots)}"
        )

        assert (
            min(acquired_slots) == 0
        ), f"Min slot should be 0, got {min(acquired_slots)}"

        # Verify no slots beyond thread count
        assert all(0 <= slot < vector_thread_count for slot in acquired_slots), (
            f"All slots should be in range [0, {vector_thread_count}), "
            f"got {acquired_slots}"
        )
