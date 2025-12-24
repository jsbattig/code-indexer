"""
Tests for CleanupManager - background cleanup of old index versions.

Tests AC3 Technical Requirements:
- Cleanup thread monitors ref counts
- Delete old index when ref count = 0
- Keep max 2 versions (current + previous)
"""

import time
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager


class TestCleanupManager:
    """Test suite for CleanupManager component."""

    def test_cleanup_manager_starts_and_stops(self, tmp_path):
        """
        Test that cleanup manager can be started and stopped cleanly.

        Basic lifecycle management
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        cleanup_mgr.start()
        assert cleanup_mgr.is_running()

        cleanup_mgr.stop()
        assert not cleanup_mgr.is_running()

    def test_schedule_cleanup_adds_path_to_queue(self, tmp_path):
        """
        Test that schedule_cleanup() adds path to cleanup queue.

        AC3: Old index path marked for cleanup
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        index_path = str(tmp_path / "v_1234")

        cleanup_mgr.schedule_cleanup(index_path)

        # Verify path is in queue (internal inspection for testing)
        assert index_path in cleanup_mgr._cleanup_queue

    def test_cleanup_deletes_when_ref_count_zero(self, tmp_path):
        """
        Test that cleanup deletes directory when ref count reaches zero.

        AC3: Delete triggered when ref count reaches zero
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Create index directory
        index_path = tmp_path / "v_1234"
        index_path.mkdir()
        (index_path / "test.txt").write_text("test")

        # Schedule cleanup (ref count is 0)
        cleanup_mgr.schedule_cleanup(str(index_path))

        # Start cleanup manager
        cleanup_mgr.start()

        # Wait for cleanup to occur
        time.sleep(0.3)

        cleanup_mgr.stop()

        # Verify directory was deleted
        assert not index_path.exists()

    def test_cleanup_waits_for_active_queries(self, tmp_path):
        """
        Test that cleanup waits while queries are active.

        AC3: Cleanup occurs after query completion
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Create index directory
        index_path = tmp_path / "v_1234"
        index_path.mkdir()

        # Simulate active query (increment ref count)
        tracker.increment_ref(str(index_path))

        # Schedule cleanup
        cleanup_mgr.schedule_cleanup(str(index_path))

        # Start cleanup manager
        cleanup_mgr.start()

        # Wait (cleanup should NOT happen yet)
        time.sleep(0.3)

        # Verify directory still exists (query active)
        assert index_path.exists()

        # Complete query (decrement ref count)
        tracker.decrement_ref(str(index_path))

        # Wait for cleanup
        time.sleep(0.3)

        cleanup_mgr.stop()

        # Verify directory was deleted
        assert not index_path.exists()

    def test_cleanup_handles_nonexistent_directory(self, tmp_path):
        """
        Test that cleanup handles case where directory doesn't exist.

        Error handling: Graceful handling of already-deleted paths
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Schedule cleanup for non-existent path
        nonexistent_path = str(tmp_path / "v_9999")
        cleanup_mgr.schedule_cleanup(nonexistent_path)

        # Start cleanup (should not crash)
        cleanup_mgr.start()
        time.sleep(0.2)
        cleanup_mgr.stop()

        # No exception raised = success

    def test_cleanup_logs_deletion(self, tmp_path, caplog):
        """
        Test that cleanup logs deletion for audit trail.

        AC3: Cleanup is logged for audit
        """
        import logging

        caplog.set_level(logging.INFO)

        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Create index directory
        index_path = tmp_path / "v_1234"
        index_path.mkdir()

        cleanup_mgr.schedule_cleanup(str(index_path))
        cleanup_mgr.start()
        time.sleep(0.3)
        cleanup_mgr.stop()

        # Verify log contains deletion message
        assert "Deleted old index" in caplog.text
        assert str(index_path) in caplog.text

    def test_multiple_paths_cleaned_independently(self, tmp_path):
        """
        Test that multiple paths are cleaned up independently.

        Scenario: Multiple old versions scheduled for cleanup
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        # Create multiple index directories
        path1 = tmp_path / "v_1234"
        path2 = tmp_path / "v_5678"
        path3 = tmp_path / "v_9999"
        path1.mkdir()
        path2.mkdir()
        path3.mkdir()

        # Path1: no active queries (should be deleted)
        cleanup_mgr.schedule_cleanup(str(path1))

        # Path2: active query (should wait)
        tracker.increment_ref(str(path2))
        cleanup_mgr.schedule_cleanup(str(path2))

        # Path3: no active queries (should be deleted)
        cleanup_mgr.schedule_cleanup(str(path3))

        cleanup_mgr.start()
        time.sleep(0.3)

        # Verify path1 and path3 deleted, path2 still exists
        assert not path1.exists()
        assert path2.exists()
        assert not path3.exists()

        # Complete path2 query
        tracker.decrement_ref(str(path2))
        time.sleep(0.3)

        cleanup_mgr.stop()

        # Verify path2 deleted
        assert not path2.exists()

    def test_cleanup_thread_stops_gracefully(self, tmp_path):
        """
        Test that cleanup thread stops within reasonable time.

        Thread management: Clean shutdown
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        cleanup_mgr.start()
        time.sleep(0.1)

        # Stop and measure shutdown time
        start = time.time()
        cleanup_mgr.stop()
        shutdown_time = time.time() - start

        # Should stop within 1 second (generous timeout)
        assert shutdown_time < 1.0

    def test_cleanup_not_started_schedule_still_queues(self, tmp_path):
        """
        Test that schedule_cleanup() works even when manager not started.

        Pattern: Queue operations before starting background thread
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        index_path = str(tmp_path / "v_1234")

        # Schedule before starting
        cleanup_mgr.schedule_cleanup(index_path)

        # Verify queued
        assert index_path in cleanup_mgr._cleanup_queue

    def test_get_pending_cleanups_returns_queue(self, tmp_path):
        """
        Test that get_pending_cleanups() returns queued paths.

        Observability: Inspect pending cleanups
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        path1 = str(tmp_path / "v_1234")
        path2 = str(tmp_path / "v_5678")

        cleanup_mgr.schedule_cleanup(path1)
        cleanup_mgr.schedule_cleanup(path2)

        pending = cleanup_mgr.get_pending_cleanups()

        assert set(pending) == {path1, path2}

    def test_cleanup_manager_double_start_is_safe(self, tmp_path):
        """
        Test that calling start() twice is safe (no duplicate threads).

        Error handling: Idempotent start
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        cleanup_mgr.start()
        cleanup_mgr.start()  # Should be no-op

        assert cleanup_mgr.is_running()

        cleanup_mgr.stop()

    def test_cleanup_manager_double_stop_is_safe(self, tmp_path):
        """
        Test that calling stop() twice is safe.

        Error handling: Idempotent stop
        """
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker, check_interval=0.1)

        cleanup_mgr.start()
        cleanup_mgr.stop()
        cleanup_mgr.stop()  # Should be no-op

        assert not cleanup_mgr.is_running()

    def test_cleanup_check_interval_controls_frequency(self, tmp_path):
        """
        Test that check_interval parameter is accepted and stored.

        Performance: Configurable polling rate
        """
        tracker = QueryTracker()
        # Longer interval for this test
        cleanup_mgr = CleanupManager(tracker, check_interval=1.0)

        # Verify interval is stored
        assert cleanup_mgr._check_interval == 1.0

        # Test with different interval
        cleanup_mgr2 = CleanupManager(tracker, check_interval=0.5)
        assert cleanup_mgr2._check_interval == 0.5
