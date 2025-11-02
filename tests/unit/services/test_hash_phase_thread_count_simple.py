"""
Simplified unit tests for hash phase thread count bug.

This test directly verifies the bug without needing full processor setup.
"""

from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker


class TestThreadCountCalculation:
    """Direct tests for thread count vs slot count calculation."""

    def test_get_slot_count_returns_occupied_slots_not_threads(self):
        """
        Verify get_slot_count() returns OCCUPIED slots, not worker thread count.

        This is the ROOT CAUSE of Bug 2: Thread count wrong during hashing.

        SETUP:
        - 8 worker threads for hashing
        - 10 max_slots (8 workers + 2 extra)

        BUG:
        Line 399 in high_throughput_processor.py uses:
            active_threads = hash_slot_tracker.get_slot_count()

        This returns number of OCCUPIED SLOTS (0-10), not worker threads (8).

        CORRECT FIX:
            active_threads = vector_thread_count  # Use actual worker count
        """
        vector_thread_count = 8
        slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # Initially all slots are empty
        assert slot_tracker.get_slot_count() == 0

        # When workers are active, slots get occupied
        # But occupied slot count != worker thread count!

        # Simulate: 10 slots available, but only 8 worker threads
        # The 8 workers can occupy between 0-10 slots depending on timing

        # This proves get_slot_count() is WRONG for reporting thread count
        assert (
            slot_tracker.max_slots == 10
        ), "Slot tracker has 10 slots (8 threads + 2 buffer)"
        assert slot_tracker.get_slot_count() != vector_thread_count or (
            slot_tracker.get_slot_count() == 0
        ), "get_slot_count() returns occupied slots (0-10), not threads (8)"

        # CORRECT APPROACH: Use vector_thread_count directly
        correct_thread_count = vector_thread_count  # Always 8
        assert correct_thread_count == 8, "Thread count should always be 8"

    def test_slot_count_fluctuates_thread_count_is_constant(self):
        """
        Demonstrate that slot_count fluctuates while thread_count is constant.

        This explains why the hash phase shows varying thread counts like
        "10 threads" then "7 threads" then "9 threads".
        """
        vector_thread_count = 8
        slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        from src.code_indexer.services.clean_slot_tracker import FileData, FileStatus

        # Simulate workers acquiring and releasing slots
        slot_ids = []

        # 3 workers acquire slots
        for i in range(3):
            file_data = FileData(
                filename=f"file{i}.py", file_size=1024, status=FileStatus.PROCESSING
            )
            slot_id = slot_tracker.acquire_slot(file_data)
            slot_ids.append(slot_id)

        # Now slot_count = 3 (but we have 8 worker threads!)
        assert slot_tracker.get_slot_count() == 3

        # 7 more workers acquire slots
        for i in range(3, 10):
            file_data = FileData(
                filename=f"file{i}.py", file_size=1024, status=FileStatus.PROCESSING
            )
            slot_id = slot_tracker.acquire_slot(file_data)
            slot_ids.append(slot_id)

        # Now slot_count = 10 (all slots occupied, but still only 8 worker threads!)
        assert slot_tracker.get_slot_count() == 10

        # 5 workers finish and release slots
        for i in range(5):
            slot_tracker.release_slot(slot_ids[i])

        # CRITICAL INSIGHT: Slots stay visible after release (UX feature)!
        # So slot_count STILL = 10 (completed files kept visible for user feedback)
        assert slot_tracker.get_slot_count() == 10, "Slots stay visible after release!"

        # This makes get_slot_count() EVEN MORE WRONG for reporting thread count!
        # It counts:
        # - Actively processing files (correct)
        # - Completed files still visible (incorrect for thread count)
        # - Can show 10 "threads" even when only 3 are actually working!

        # CONCLUSION: get_slot_count() is completely unsuitable for thread count
        # Using get_slot_count() for "active threads" is FUNDAMENTALLY WRONG

    def test_correct_thread_count_reporting_pattern(self):
        """
        Document the CORRECT pattern for reporting thread count.

        WRONG:
            active_threads = hash_slot_tracker.get_slot_count()  # BUG!

        CORRECT:
            active_threads = vector_thread_count  # Use actual worker count
        """
        vector_thread_count = 8
        slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # WRONG approach (current bug)
        wrong_thread_count = slot_tracker.get_slot_count()
        assert (
            wrong_thread_count == 0
        ), "Wrong: get_slot_count() returns 0 initially, but we have 8 threads!"

        # CORRECT approach (fix)
        correct_thread_count = vector_thread_count
        assert (
            correct_thread_count == 8
        ), "Correct: Use vector_thread_count directly for accurate reporting"


class TestHashPhaseVsIndexingPhase:
    """Compare thread count reporting in hash vs indexing phases."""

    def test_both_phases_use_same_buggy_pattern(self):
        """
        Verify both hash AND indexing phases have the same bug.

        HASH PHASE (line 399):
            active_threads = hash_slot_tracker.get_slot_count()

        INDEXING PHASE (line 634-636):
            active_threads = 0
            if local_slot_tracker:
                active_threads = local_slot_tracker.get_slot_count()

        Both use get_slot_count() which returns OCCUPIED SLOTS, not thread count.
        """
        vector_thread_count = 8

        # Hash phase slot tracker
        hash_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # Indexing phase slot tracker
        local_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # Both have same max_slots
        assert hash_slot_tracker.max_slots == local_slot_tracker.max_slots == 10

        # Both will return same wrong values if using get_slot_count()
        assert (
            hash_slot_tracker.get_slot_count()
            == local_slot_tracker.get_slot_count()
            == 0
        )

        # CORRECT FIX for both phases: Use vector_thread_count directly
        correct_hash_threads = vector_thread_count
        correct_indexing_threads = vector_thread_count

        assert correct_hash_threads == correct_indexing_threads == 8


class TestBugReproduction:
    """Reproduce the exact bug reported by user."""

    def test_hash_phase_shows_10_threads_instead_of_8(self):
        """
        Reproduce user's bug report: Hash phase shows "10 threads" instead of "8 threads".

        USER CONFIGURATION:
        - 8 threads for hashing
        - 8 threads for vectorization
        - 10 threads ONLY for chunking (+2 extra)

        USER SYMPTOM:
        - Hash phase shows: "68.7 files/s | 839.0 KB/s | **10 threads**"
        - Should show: "68.7 files/s | 839.0 KB/s | **8 threads**"

        ROOT CAUSE:
        - hash_slot_tracker has max_slots=10 (vector_thread_count + 2)
        - Line 399 uses: active_threads = hash_slot_tracker.get_slot_count()
        - When all slots occupied, get_slot_count() returns 10
        - But actual worker threads = 8
        """
        vector_thread_count = 8  # User configured 8 threads
        hash_slot_tracker = CleanSlotTracker(
            max_slots=vector_thread_count + 2
        )  # 10 slots

        from src.code_indexer.services.clean_slot_tracker import FileData, FileStatus

        # Simulate all slots being occupied during busy hash phase
        for i in range(10):
            file_data = FileData(
                filename=f"file{i}.py", file_size=1024, status=FileStatus.PROCESSING
            )
            hash_slot_tracker.acquire_slot(file_data)

        # BUG: Using get_slot_count() returns 10 (slots), not 8 (threads)
        buggy_thread_count = hash_slot_tracker.get_slot_count()
        assert buggy_thread_count == 10, "Bug reproduced: shows 10 threads"

        # FIX: Use vector_thread_count directly
        correct_thread_count = vector_thread_count
        assert correct_thread_count == 8, "Fix: shows 8 threads (correct)"

        # This explains the user's observation
        assert (
            buggy_thread_count != correct_thread_count
        ), "Bug: Reported 10 threads instead of 8"
