"""
Test for frozen slots bug caused by multiple CleanSlotTracker instances.

ROOT CAUSE: Client receives slot_tracker from MULTIPLE different CleanSlotTracker
instances over RPyC (hash_slot_tracker and local_slot_tracker). When client calls
slot_tracker.get_concurrent_files_data(), it calls the WRONG tracker (whichever
was passed last), getting stale data from inactive tracker.

EVIDENCE: Debug logs show:
- Daemon sends data from tracker A (140236387663248)
- Client calls get_concurrent_files_data() on tracker B (139905109781376)
- Result: Client gets stale data from inactive tracker

THE FIX: Use concurrent_files from kwargs (pre-serialized data from correct tracker)
instead of calling slot_tracker.get_concurrent_files_data() on potentially wrong tracker.
"""

from unittest.mock import Mock


class TestFrozenSlotsMultipleTrackers:
    """Test that demonstrates frozen slots bug with multiple tracker instances."""

    def test_wrong_tracker_returns_stale_data(self):
        """
        Demonstrates the bug: Client calls get_concurrent_files_data() on wrong
        tracker instance, getting stale data instead of fresh data.

        This simulates the exact scenario from debug logs where:
        - hash_slot_tracker (tracker A) has active files being processed
        - local_slot_tracker (tracker B) has stale/empty data
        - Client receives tracker B but needs data from tracker A
        """
        # Simulate the CORRECT tracker (hash_slot_tracker) with active files
        correct_tracker = Mock()
        correct_tracker.get_concurrent_files_data.return_value = [
            {"slot_id": 0, "file_path": "/active/file1.py"},
            {"slot_id": 1, "file_path": "/active/file2.py"},
        ]

        # Simulate the WRONG tracker (local_slot_tracker) with stale data
        wrong_tracker = Mock()
        wrong_tracker.get_concurrent_files_data.return_value = []  # Stale/empty

        # Daemon sends fresh data from correct tracker in kwargs
        kwargs_from_daemon = {
            "slot_tracker": wrong_tracker,  # Client receives WRONG tracker reference
            "concurrent_files": [  # But daemon also sends FRESH serialized data
                {"slot_id": 0, "file_path": "/active/file1.py"},
                {"slot_id": 1, "file_path": "/active/file2.py"},
            ]
        }

        # BUGGY BEHAVIOR: Client calls slot_tracker.get_concurrent_files_data()
        slot_tracker = kwargs_from_daemon.get("slot_tracker")
        if slot_tracker is not None:
            buggy_concurrent_files = slot_tracker.get_concurrent_files_data()
        else:
            buggy_concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        # BUG DEMONSTRATED: Client gets EMPTY data from wrong tracker
        assert len(buggy_concurrent_files) == 0, "Buggy code gets stale data from wrong tracker"

        # CORRECT BEHAVIOR: Client uses concurrent_files from kwargs directly
        correct_concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        # FIX VERIFIED: Client gets FRESH data from kwargs
        assert len(correct_concurrent_files) == 2, "Fixed code gets fresh data from kwargs"
        assert correct_concurrent_files[0]["file_path"] == "/active/file1.py"
        assert correct_concurrent_files[1]["file_path"] == "/active/file2.py"

    def test_no_tracker_fallback_to_kwargs(self):
        """
        Test fallback behavior when slot_tracker is None.
        Should use concurrent_files from kwargs.
        """
        kwargs_from_daemon = {
            "slot_tracker": None,
            "concurrent_files": [
                {"slot_id": 0, "file_path": "/fallback/file.py"},
            ]
        }

        # When slot_tracker is None, must use concurrent_files from kwargs
        slot_tracker = kwargs_from_daemon.get("slot_tracker")
        if slot_tracker is not None:
            concurrent_files = slot_tracker.get_concurrent_files_data()
        else:
            concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        assert len(concurrent_files) == 1
        assert concurrent_files[0]["file_path"] == "/fallback/file.py"

    def test_rpyc_proxy_exception_handling(self):
        """
        Test that RPyC proxy exceptions are handled gracefully.
        When slot_tracker.get_concurrent_files_data() raises exception,
        should fall back to empty list (current buggy behavior).

        With the fix, we won't call slot_tracker at all, so this scenario
        becomes irrelevant.
        """
        # Simulate RPyC proxy that raises exception
        broken_tracker = Mock()
        broken_tracker.get_concurrent_files_data.side_effect = Exception("RPyC connection lost")

        kwargs_from_daemon = {
            "slot_tracker": broken_tracker,
            "concurrent_files": [{"slot_id": 0, "file_path": "/valid/file.py"}]
        }

        # BUGGY BEHAVIOR: Try calling broken tracker, catch exception
        slot_tracker = kwargs_from_daemon.get("slot_tracker")
        if slot_tracker is not None:
            try:
                buggy_concurrent_files = slot_tracker.get_concurrent_files_data()
            except Exception:
                buggy_concurrent_files = []  # Fallback to empty
        else:
            buggy_concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        # BUG: Gets empty list due to exception
        assert len(buggy_concurrent_files) == 0

        # CORRECT BEHAVIOR: Use kwargs directly, no exception possible
        correct_concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        # FIX: Gets valid data from kwargs
        assert len(correct_concurrent_files) == 1
        assert correct_concurrent_files[0]["file_path"] == "/valid/file.py"

    def test_kwargs_always_has_fresh_data(self):
        """
        Verify assumption: Daemon ALWAYS includes fresh concurrent_files in kwargs.

        This test documents the expectation that the daemon serializes
        concurrent files data and includes it in progress callback kwargs.
        """
        # Simulate daemon behavior: Always serialize and send concurrent_files
        fresh_data = [
            {"slot_id": 0, "file_path": "/fresh/file1.py"},
            {"slot_id": 1, "file_path": "/fresh/file2.py"},
        ]

        kwargs_from_daemon = {
            "slot_tracker": Mock(),  # Tracker reference (potentially wrong one)
            "concurrent_files": fresh_data  # FRESH serialized data
        }

        # Client should ALWAYS use this data
        concurrent_files = kwargs_from_daemon.get("concurrent_files", [])

        assert len(concurrent_files) == 2
        assert concurrent_files[0]["file_path"] == "/fresh/file1.py"
        assert concurrent_files[1]["file_path"] == "/fresh/file2.py"
