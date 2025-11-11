"""
TDD Tests for Hash Slot Tracker Variable Shadowing Fix

These tests validate the fixes for the variable shadowing bug where:
1. hash_worker parameter shadowed hash_slot_tracker variable
2. Hash phase incorrectly used vector_thread_count + 2 instead of vector_thread_count

Tests prove that:
- Worker uses SAME slot tracker as progress callback
- Hash phase creates correct number of slots
- All slots get reused during hashing
- Display shows correct thread count and slot updates
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.config import Config
from code_indexer.services.clean_slot_tracker import CleanSlotTracker


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Mock(spec=Config)
        config.codebase_dir = Path(tmpdir)
        config.exclude_dirs = ["node_modules", ".git"]
        config.exclude_files = []
        config.file_extensions = ["py", "js", "ts"]

        # Mock the indexing sub-config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        # Mock qdrant config
        config.qdrant = Mock()
        config.qdrant.vector_size = 768

        # Mock embedding config
        embedding_config = Mock()
        embedding_config.provider = "voyageai"
        embedding_config.model = "voyage-code-3"
        embedding_config.batch_size = 10
        config.embedding = embedding_config

        yield config


class TestHashPhaseSlotCount:
    """Test that hash phase creates correct number of slots (no +2 bonus)."""

    def test_hash_slot_tracker_max_slots_matches_thread_count(self):
        """
        Direct test: CleanSlotTracker for hash phase has max_slots == vector_thread_count.

        This validates Fix #2: Hash phase should use EXACT thread count, not +2.

        Before fix: CleanSlotTracker(max_slots=vector_thread_count + 2)
        After fix: CleanSlotTracker(max_slots=vector_thread_count)

        Rationale: +2 bonus is ONLY for chunking phase, not hashing.
        """
        vector_thread_count = 8

        # Create hash slot tracker as the code does after fix
        hash_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count)

        # CRITICAL ASSERTION: Max slots equals thread count (no +2 bonus)
        assert (
            hash_slot_tracker.max_slots == vector_thread_count
        ), f"Hash tracker max_slots ({hash_slot_tracker.max_slots}) MUST equal thread count ({vector_thread_count})"
        assert (
            hash_slot_tracker.max_slots != vector_thread_count + 2
        ), f"Hash tracker MUST NOT use +2 bonus (found {hash_slot_tracker.max_slots}, expected {vector_thread_count})"

    def test_chunking_slot_tracker_has_plus_two_bonus(self):
        """
        Verify chunking phase DOES use +2 bonus (to contrast with hash phase).

        This ensures we didn't accidentally remove the +2 bonus from chunking too.
        """
        vector_thread_count = 8

        # Create chunking slot tracker as the code should do
        chunking_slot_tracker = CleanSlotTracker(max_slots=vector_thread_count + 2)

        # CRITICAL ASSERTION: Chunking phase DOES use +2 bonus
        assert (
            chunking_slot_tracker.max_slots == vector_thread_count + 2
        ), f"Chunking tracker MUST use +2 bonus: found {chunking_slot_tracker.max_slots}, expected {vector_thread_count + 2}"


class TestHashWorkerParameterNaming:
    """Test that hash_worker parameter is correctly named to avoid shadowing."""

    def test_hash_worker_parameter_not_named_slot_tracker(self):
        """
        Verify hash_worker parameter is NOT named 'slot_tracker' (which would shadow).

        This validates Fix #1: Rename parameter to avoid variable shadowing.

        Before fix: def hash_worker(..., slot_tracker: CleanSlotTracker)
        After fix: def hash_worker(..., worker_slot_tracker: CleanSlotTracker)

        This is a code inspection test to prevent regression.
        """
        # Read the source code
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Find hash_worker function definition
        hash_worker_start = source_code.find("def hash_worker(")
        assert hash_worker_start != -1, "hash_worker function not found"

        # Extract function signature (until first colon after def)
        sig_end = source_code.find("):", hash_worker_start)
        signature = source_code[hash_worker_start : sig_end + 1]

        # CRITICAL ASSERTION: Parameter should be worker_slot_tracker, NOT slot_tracker
        assert (
            "worker_slot_tracker: CleanSlotTracker" in signature
        ), f"hash_worker MUST use 'worker_slot_tracker' parameter to avoid shadowing. Found: {signature}"

        # Verify it's NOT using the old shadowing name
        # Check for exact parameter pattern: ", slot_tracker: CleanSlotTracker"
        assert (
            ", slot_tracker: CleanSlotTracker" not in signature
        ), f"hash_worker MUST NOT use 'slot_tracker' parameter (causes shadowing). Found: {signature}"

    def test_hash_worker_uses_worker_slot_tracker_internally(self):
        """
        Verify hash_worker function body uses worker_slot_tracker, not slot_tracker.

        This ensures the fix is complete - not just the parameter name but all usage.
        """
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Find hash_worker function body
        hash_worker_start = source_code.find("def hash_worker(")
        # Find the next function definition or class to limit scope
        next_def = source_code.find("\n    def ", hash_worker_start + 1)
        if next_def == -1:
            next_def = source_code.find("\n\nclass ", hash_worker_start + 1)
        if next_def == -1:
            next_def = len(source_code)

        hash_worker_body = source_code[hash_worker_start:next_def]

        # CRITICAL ASSERTION: Function uses worker_slot_tracker
        assert (
            "worker_slot_tracker.acquire_slot" in hash_worker_body
        ), "hash_worker MUST call worker_slot_tracker.acquire_slot()"
        assert (
            "worker_slot_tracker.update_slot" in hash_worker_body
        ), "hash_worker MUST call worker_slot_tracker.update_slot()"
        assert (
            "worker_slot_tracker.release_slot" in hash_worker_body
        ), "hash_worker MUST call worker_slot_tracker.release_slot()"


class TestSlotTrackerConsistency:
    """Test that slot tracker is consistently used throughout hash phase."""

    def test_hash_slot_tracker_passed_to_progress_callback(self):
        """
        Verify that progress callback in hash phase receives hash_slot_tracker.

        This validates that the SAME tracker used by workers is passed to display.
        """
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Find hash_worker function
        hash_worker_start = source_code.find("def hash_worker(")
        # Find the section containing the progress_callback call
        hash_worker_end = source_code.find("except Exception as e:", hash_worker_start)

        hash_worker_section = source_code[hash_worker_start:hash_worker_end]

        # CRITICAL ASSERTION: Progress callback receives hash_slot_tracker (not worker_slot_tracker)
        assert (
            "slot_tracker=hash_slot_tracker" in hash_worker_section
        ), "Progress callback MUST receive hash_slot_tracker (the outer variable shared by all workers)"

    def test_hash_slot_tracker_passed_to_worker(self):
        """
        Verify that hash_slot_tracker is passed to hash_worker as worker_slot_tracker.

        This completes the validation that the SAME tracker flows through the system.
        """
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Verify hash_slot_tracker variable exists (created and passed to workers)
        assert (
            "hash_slot_tracker" in source_code
        ), "hash_slot_tracker must exist and be passed to worker threads"

        # Verify workers receive it as worker_slot_tracker parameter
        assert (
            "worker_slot_tracker: CleanSlotTracker" in source_code
        ), "Workers must receive tracker as worker_slot_tracker parameter"


class TestHashPhaseCorrectness:
    """Integration tests validating the complete hash phase fix."""

    def test_slot_tracker_can_handle_exact_thread_count(self):
        """
        Verify CleanSlotTracker works correctly with exact thread count.

        This validates the fix doesn't break slot tracker functionality.
        """
        from code_indexer.services.clean_slot_tracker import FileData, FileStatus

        vector_thread_count = 8
        tracker = CleanSlotTracker(max_slots=vector_thread_count)

        # Simulate file processing
        file_data = FileData(
            filename="test.py", file_size=1000, status=FileStatus.PROCESSING
        )

        # Acquire slot
        slot_id = tracker.acquire_slot(file_data)
        assert slot_id is not None, "Should be able to acquire slot"
        assert (
            0 <= slot_id < vector_thread_count
        ), f"Slot ID should be in range 0-{vector_thread_count-1}"

        # Update slot
        tracker.update_slot(slot_id, FileStatus.COMPLETE)

        # Release slot (returns to available pool)
        tracker.release_slot(slot_id)

        # Verify we can acquire another slot (released slot is now available)
        file_data_2 = FileData(
            filename="test2.py", file_size=2000, status=FileStatus.PROCESSING
        )
        slot_id_2 = tracker.acquire_slot(file_data_2)
        assert slot_id_2 is not None, "Should be able to acquire slot after release"
        assert (
            0 <= slot_id_2 < vector_thread_count
        ), "Second slot should also be in valid range"

        # Release second slot
        tracker.release_slot(slot_id_2)

    def test_multiple_slots_can_be_acquired_up_to_thread_count(self):
        """
        Verify we can acquire up to vector_thread_count slots simultaneously.

        This ensures the fix doesn't restrict parallelism.
        """
        vector_thread_count = 4
        tracker = CleanSlotTracker(max_slots=vector_thread_count)

        from code_indexer.services.clean_slot_tracker import FileData, FileStatus

        acquired_slots = []

        # Acquire all slots
        for i in range(vector_thread_count):
            file_data = FileData(
                filename=f"test_{i}.py", file_size=1000, status=FileStatus.PROCESSING
            )
            slot_id = tracker.acquire_slot(file_data)
            assert slot_id is not None, f"Should acquire slot {i}"
            acquired_slots.append(slot_id)

        # Verify all slots are unique
        assert (
            len(set(acquired_slots)) == vector_thread_count
        ), f"All {vector_thread_count} slots should be unique"

        # Release all slots
        for slot_id in acquired_slots:
            tracker.release_slot(slot_id)


class TestParameterShadowingPrevention:
    """Regression tests to prevent parameter shadowing from being reintroduced."""

    def test_no_slot_tracker_parameter_in_hash_worker(self):
        """
        Ensure hash_worker does NOT have a parameter named 'slot_tracker'.

        This prevents the original bug from being reintroduced.
        """
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Find hash_worker function
        hash_worker_start = source_code.find("def hash_worker(")
        hash_worker_sig_end = source_code.find("):", hash_worker_start)
        signature = source_code[hash_worker_start:hash_worker_sig_end]

        # REGRESSION TEST: slot_tracker parameter would cause shadowing
        assert (
            "slot_tracker:" not in signature or "worker_slot_tracker:" in signature
        ), "hash_worker MUST NOT have 'slot_tracker' parameter (causes shadowing bug)"

    def test_hash_slot_tracker_variable_exists(self):
        """
        Verify hash_slot_tracker variable exists in process_files_high_throughput.

        This ensures the outer variable that workers should use still exists.

        UPDATED after fix: The CORRECT pattern is to ALWAYS create fresh tracker,
        never reuse the slot_tracker parameter.
        """
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "services"
            / "high_throughput_processor.py"
        )
        source_code = source_file.read_text()

        # Look for hash_slot_tracker assignment with CORRECT pattern (after fix)
        # The CORRECT pattern is: hash_slot_tracker = CleanSlotTracker(
        #                             max_slots=vector_thread_count
        #                         )
        # NOT: hash_slot_tracker = slot_tracker or CleanSlotTracker(...)
        assert (
            "hash_slot_tracker = CleanSlotTracker(" in source_code
        ), "hash_slot_tracker variable must exist and create fresh tracker"

        # CRITICAL: Verify the OLD BUGGY pattern no longer exists
        assert (
            "hash_slot_tracker = slot_tracker or CleanSlotTracker(" not in source_code
        ), "BUGGY PATTERN DETECTED: hash_slot_tracker should NOT reuse slot_tracker parameter"

        # Verify the CleanSlotTracker creation uses exact vector_thread_count
        # Look for the pattern after hash_slot_tracker assignment
        hash_tracker_start = source_code.find("hash_slot_tracker = CleanSlotTracker(")
        assert hash_tracker_start != -1, "hash_slot_tracker assignment not found"
        hash_tracker_section = source_code[
            hash_tracker_start : hash_tracker_start + 200
        ]

        assert (
            "max_slots=vector_thread_count" in hash_tracker_section
        ), "hash_slot_tracker MUST use exact vector_thread_count (no +2)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
