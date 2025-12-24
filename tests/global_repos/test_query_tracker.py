"""
Tests for QueryTracker - reference counting for active queries.

Tests AC3 Technical Requirements:
- Reference counting for active queries per index version
- Query start increments ref count
- Query end decrements ref count
- Thread-safe operations
"""

import pytest
import threading
from code_indexer.global_repos.query_tracker import QueryTracker


class TestQueryTracker:
    """Test suite for QueryTracker component."""

    def test_initial_ref_count_is_zero(self):
        """
        Test that initial reference count for any path is zero.

        AC3: Reference counting starts at zero
        """
        tracker = QueryTracker()

        ref_count = tracker.get_ref_count("/path/to/index")

        assert ref_count == 0

    def test_increment_ref_increases_count(self):
        """
        Test that increment_ref() increases the reference count.

        AC3: Query start increments ref count
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        tracker.increment_ref(index_path)

        assert tracker.get_ref_count(index_path) == 1

    def test_decrement_ref_decreases_count(self):
        """
        Test that decrement_ref() decreases the reference count.

        AC3: Query end decrements ref count
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        tracker.increment_ref(index_path)
        tracker.decrement_ref(index_path)

        assert tracker.get_ref_count(index_path) == 0

    def test_multiple_increments_tracked_correctly(self):
        """
        Test that multiple increments accumulate correctly.

        Scenario: Multiple concurrent queries on same index
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        tracker.increment_ref(index_path)
        tracker.increment_ref(index_path)
        tracker.increment_ref(index_path)

        assert tracker.get_ref_count(index_path) == 3

    def test_decrement_below_zero_raises_error(self):
        """
        Test that decrementing below zero raises exception.

        Safety: Prevent negative ref counts (indicates bug)
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        with pytest.raises(ValueError, match="Reference count cannot be negative"):
            tracker.decrement_ref(index_path)

    def test_different_paths_tracked_independently(self):
        """
        Test that different index paths have independent ref counts.

        Scenario: Multiple index versions in use simultaneously
        """
        tracker = QueryTracker()
        path_old = "/path/to/index/v_1234"
        path_new = "/path/to/index/v_5678"

        tracker.increment_ref(path_old)
        tracker.increment_ref(path_old)
        tracker.increment_ref(path_new)

        assert tracker.get_ref_count(path_old) == 2
        assert tracker.get_ref_count(path_new) == 1

    def test_thread_safety_concurrent_increments(self):
        """
        Test that concurrent increments from multiple threads are thread-safe.

        AC3: Thread-safe operations (critical for production)
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"
        num_threads = 100
        increments_per_thread = 10

        def increment_worker():
            for _ in range(increments_per_thread):
                tracker.increment_ref(index_path)

        threads = [
            threading.Thread(target=increment_worker) for _ in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected_count = num_threads * increments_per_thread
        assert tracker.get_ref_count(index_path) == expected_count

    def test_thread_safety_concurrent_decrements(self):
        """
        Test that concurrent decrements from multiple threads are thread-safe.
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"
        num_threads = 50
        decrements_per_thread = 10

        # Pre-populate with increments
        initial_count = num_threads * decrements_per_thread
        for _ in range(initial_count):
            tracker.increment_ref(index_path)

        def decrement_worker():
            for _ in range(decrements_per_thread):
                tracker.decrement_ref(index_path)

        threads = [
            threading.Thread(target=decrement_worker) for _ in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.get_ref_count(index_path) == 0

    def test_thread_safety_mixed_operations(self):
        """
        Test thread safety with mixed increments and decrements.

        Realistic scenario: queries starting and ending concurrently
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        # Pre-populate
        for _ in range(100):
            tracker.increment_ref(index_path)

        def mixed_worker(inc_count, dec_count):
            for _ in range(inc_count):
                tracker.increment_ref(index_path)
            for _ in range(dec_count):
                tracker.decrement_ref(index_path)

        threads = [
            threading.Thread(target=mixed_worker, args=(10, 5)),
            threading.Thread(target=mixed_worker, args=(5, 10)),
            threading.Thread(target=mixed_worker, args=(8, 8)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Initial 100 + (10+5+8) - (5+10+8) = 100 + 23 - 23 = 100
        assert tracker.get_ref_count(index_path) == 100

    def test_get_all_paths_returns_tracked_paths(self):
        """
        Test that get_all_paths() returns all paths with non-zero ref counts.

        Useful for cleanup manager to iterate active indexes
        """
        tracker = QueryTracker()

        tracker.increment_ref("/path/a")
        tracker.increment_ref("/path/b")
        tracker.increment_ref("/path/c")

        # Decrement one to zero
        tracker.decrement_ref("/path/c")

        paths = tracker.get_all_paths()

        # Should only return paths with non-zero counts
        assert set(paths) == {"/path/a", "/path/b"}

    def test_context_manager_for_query_tracking(self):
        """
        Test using context manager pattern for automatic ref counting.

        Pattern: with tracker.track_query(path): ...
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        # Before context: count is 0
        assert tracker.get_ref_count(index_path) == 0

        # Inside context: count is 1
        with tracker.track_query(index_path):
            assert tracker.get_ref_count(index_path) == 1

        # After context: count back to 0
        assert tracker.get_ref_count(index_path) == 0

    def test_context_manager_decrements_on_exception(self):
        """
        Test that context manager decrements ref count even on exception.

        Critical: Ref count must be accurate even when queries fail
        """
        tracker = QueryTracker()
        index_path = "/path/to/index"

        with pytest.raises(RuntimeError):
            with tracker.track_query(index_path):
                assert tracker.get_ref_count(index_path) == 1
                raise RuntimeError("Simulated query error")

        # Ref count should be decremented despite exception
        assert tracker.get_ref_count(index_path) == 0
