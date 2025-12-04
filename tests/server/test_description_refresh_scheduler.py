"""
Unit tests for DescriptionRefreshScheduler.

Tests the separate timer for AI description regeneration that operates
independently of the 10-minute repository refresh cycle.
"""

import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.server.services.description_refresh_scheduler import (
    DescriptionRefreshScheduler,
)


class TestDescriptionRefreshScheduler:
    """Test suite for DescriptionRefreshScheduler."""

    @pytest.fixture
    def meta_dir(self, tmp_path):
        """Create a temporary meta directory."""
        meta = tmp_path / "cidx-meta"
        meta.mkdir()
        return meta

    @pytest.fixture
    def cli_manager(self):
        """Create a mock ClaudeCliManager."""
        manager = Mock()
        manager.submit_work = Mock()
        return manager

    @pytest.fixture
    def get_interval_hours(self):
        """Create a callable that returns refresh interval."""
        return lambda: 24  # Default 24 hours

    @pytest.fixture
    def get_repo_path(self):
        """Create a mock get_repo_path callable."""
        return Mock(return_value=Path("/mock/repo/path"))

    @pytest.fixture
    def scheduler(self, cli_manager, meta_dir, get_interval_hours, get_repo_path):
        """Create a DescriptionRefreshScheduler instance."""
        return DescriptionRefreshScheduler(
            cli_manager=cli_manager,
            meta_dir=meta_dir,
            get_interval_hours=get_interval_hours,
            get_repo_path=get_repo_path,
        )

    def test_scheduler_starts_and_stops_correctly(self, scheduler):
        """Test that scheduler starts and stops gracefully."""
        # Should not be running initially
        assert scheduler._timer_thread is None

        # Start scheduler
        scheduler.start()
        assert scheduler._timer_thread is not None
        assert scheduler._timer_thread.is_alive()
        assert not scheduler._stop_event.is_set()

        # Stop scheduler
        scheduler.stop()
        assert scheduler._stop_event.is_set()
        # Thread should have stopped
        time.sleep(0.2)  # Give thread time to exit
        assert not scheduler._timer_thread.is_alive()

    def test_start_is_idempotent(self, scheduler):
        """Test that calling start multiple times is safe."""
        scheduler.start()
        first_thread = scheduler._timer_thread

        scheduler.start()  # Call again
        second_thread = scheduler._timer_thread

        # Should be the same thread
        assert first_thread is second_thread

        scheduler.stop()

    def test_stop_is_idempotent(self, scheduler):
        """Test that calling stop multiple times is safe."""
        scheduler.start()
        scheduler.stop()
        scheduler.stop()  # Call again - should not raise

    def test_get_repos_needing_refresh_returns_old_repos(self, scheduler, meta_dir):
        """Test that _get_repos_needing_refresh returns repos older than interval."""
        # Create test files with different ages
        old_file = meta_dir / "old-repo.md"
        old_file.write_text("Old repo content")
        # Set modification time to 25 hours ago
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        os.utime(old_file, (old_timestamp, old_timestamp))

        recent_file = meta_dir / "recent-repo.md"
        recent_file.write_text("Recent repo content")
        # Recent file has current timestamp

        # Get repos needing refresh (24 hour interval)
        repos = scheduler._get_repos_needing_refresh(interval_hours=24)

        # Only old-repo should need refresh
        assert len(repos) == 1
        assert repos[0][0] == "old-repo"
        assert repos[0][1] == old_file

    def test_get_repos_needing_refresh_skips_fallback_files(self, scheduler, meta_dir):
        """Test that _get_repos_needing_refresh skips *_README.md fallback files."""
        # Create fallback file (should be skipped)
        fallback_file = meta_dir / "my-repo_README.md"
        fallback_file.write_text("Fallback content")
        # Set old timestamp
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        os.utime(fallback_file, (old_timestamp, old_timestamp))

        # Create regular generated file (should be included)
        generated_file = meta_dir / "my-other-repo.md"
        generated_file.write_text("Generated content")
        os.utime(generated_file, (old_timestamp, old_timestamp))

        # Get repos needing refresh
        repos = scheduler._get_repos_needing_refresh(interval_hours=24)

        # Only generated file should be returned, fallback should be skipped
        assert len(repos) == 1
        assert repos[0][0] == "my-other-repo"
        assert repos[0][1] == generated_file

    def test_check_and_refresh_submits_work_via_cli_manager(
        self, scheduler, meta_dir, cli_manager
    ):
        """Test that _check_and_refresh submits work via cli_manager.submit_work()."""
        # Create old file needing refresh
        old_file = meta_dir / "old-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        os.utime(old_file, (old_timestamp, old_timestamp))

        # Run check and refresh
        scheduler._check_and_refresh()

        # Verify submit_work was called
        assert cli_manager.submit_work.call_count == 1
        call_args = cli_manager.submit_work.call_args
        repo_path, callback = call_args[0]

        # repo_path should be derived from meta_file.parent
        assert isinstance(repo_path, Path)
        assert callable(callback)

    def test_minimum_interval_enforcement(self, scheduler):
        """Test that minimum interval of 1 hour is enforced."""
        # Override get_interval_hours to return 0
        scheduler._get_interval_hours = lambda: 0

        # Create old file
        old_file = scheduler._meta_dir / "old-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=2)
        old_timestamp = old_time.timestamp()

        os.utime(old_file, (old_timestamp, old_timestamp))

        # Run check and refresh - should enforce minimum 1 hour
        scheduler._check_and_refresh()

        # File should still be selected (it's 2 hours old, > 1 hour minimum)
        assert scheduler._cli_manager.submit_work.call_count == 1

    def test_on_refresh_complete_updates_last_refresh_timestamp(self, scheduler):
        """Test that _on_refresh_complete updates _last_refresh timestamp."""
        alias = "test-repo"

        # Initially no timestamp
        assert alias not in scheduler._last_refresh

        # Call on_refresh_complete with success
        before = datetime.now()
        scheduler._on_refresh_complete(alias, success=True, result="Success")
        after = datetime.now()

        # Timestamp should be set
        assert alias in scheduler._last_refresh
        assert before <= scheduler._last_refresh[alias] <= after

    def test_on_refresh_complete_does_not_update_on_failure(self, scheduler):
        """Test that _on_refresh_complete does not update timestamp on failure."""
        alias = "test-repo"

        # Initially no timestamp
        assert alias not in scheduler._last_refresh

        # Call on_refresh_complete with failure
        scheduler._on_refresh_complete(alias, success=False, result="Failed")

        # Timestamp should NOT be set
        assert alias not in scheduler._last_refresh

    def test_config_changes_apply_without_restart(self, scheduler, meta_dir):
        """Test that config changes apply without restart."""
        # Create old file
        old_file = meta_dir / "old-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=10)
        old_timestamp = old_time.timestamp()

        os.utime(old_file, (old_timestamp, old_timestamp))

        # Initially interval is 24 hours - file should NOT need refresh
        repos = scheduler._get_repos_needing_refresh(interval_hours=24)
        assert len(repos) == 0

        # Change interval to 8 hours via callable
        scheduler._get_interval_hours = lambda: 8

        # Now file should need refresh (10 hours > 8 hours)
        repos = scheduler._get_repos_needing_refresh(interval_hours=8)
        assert len(repos) == 1

    def test_scheduler_runs_independently_no_shared_locks(self, scheduler):
        """Test that scheduler thread runs independently without blocking main thread."""
        # Start scheduler
        scheduler.start()

        # Verify thread is daemon (won't block program exit)
        assert scheduler._timer_thread.daemon

        # Main thread should not be blocked
        # If we can execute this code, main thread is not blocked
        assert not scheduler._stop_event.is_set()

        scheduler.stop()

    def test_empty_meta_directory_returns_no_repos(self, scheduler):
        """Test that empty meta directory returns no repos needing refresh."""
        # Meta directory exists but is empty
        repos = scheduler._get_repos_needing_refresh(interval_hours=24)
        assert len(repos) == 0

    def test_nonexistent_meta_directory_returns_no_repos(self, scheduler, tmp_path):
        """Test that nonexistent meta directory returns no repos."""
        # Set nonexistent meta directory
        scheduler._meta_dir = tmp_path / "nonexistent"

        repos = scheduler._get_repos_needing_refresh(interval_hours=24)
        assert len(repos) == 0

    def test_timer_loop_respects_stop_event(self, scheduler):
        """Test that timer loop exits when stop_event is set."""
        scheduler.start()

        # Stop should complete within reasonable time
        start_time = time.time()
        scheduler.stop()
        elapsed = time.time() - start_time

        # Should exit within 2 seconds (not wait for full hour interval)
        assert elapsed < 2.0

    def test_check_and_refresh_handles_exceptions_gracefully(self, scheduler, meta_dir):
        """Test that _check_and_refresh handles exceptions without crashing."""
        # Create file that will trigger refresh
        old_file = meta_dir / "old-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        os.utime(old_file, (old_timestamp, old_timestamp))

        # Make submit_work raise exception
        scheduler._cli_manager.submit_work.side_effect = RuntimeError("Test error")

        # Should not raise - exception should be caught and logged
        scheduler._check_and_refresh()

    def test_last_refresh_uses_file_mtime_as_initial_timestamp(
        self, scheduler, meta_dir
    ):
        """Test that file modification time is used as initial timestamp."""
        # Create file with specific mtime
        old_file = meta_dir / "test-repo.md"
        old_file.write_text("Content")
        specific_time = datetime.now() - timedelta(hours=30)
        specific_timestamp = specific_time.timestamp()

        os.utime(old_file, (specific_timestamp, specific_timestamp))

        # Get repos needing refresh - this should initialize _last_refresh
        repos = scheduler._get_repos_needing_refresh(interval_hours=24)
        assert len(repos) == 1  # Verify it found the old repo

        # Should have been added to _last_refresh with file's mtime
        assert "test-repo" in scheduler._last_refresh
        # Allow small delta for timing
        assert (
            abs(scheduler._last_refresh["test-repo"].timestamp() - specific_timestamp)
            < 1.0
        )

    def test_multiple_repos_processed_correctly(self, scheduler, meta_dir, cli_manager):
        """Test that multiple repos are processed correctly."""
        # Create multiple old files
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        for i in range(3):
            file = meta_dir / f"repo-{i}.md"
            file.write_text(f"Content {i}")
            os.utime(file, (old_timestamp, old_timestamp))

        # Also create a fallback (should be skipped)
        fallback = meta_dir / "repo-fallback_README.md"
        fallback.write_text("Fallback")
        os.utime(fallback, (old_timestamp, old_timestamp))

        # Run check and refresh
        scheduler._check_and_refresh()

        # Should have submitted work for 3 repos (not the fallback)
        assert cli_manager.submit_work.call_count == 3

    def test_interval_hours_less_than_one_enforced_to_one(self, scheduler, meta_dir):
        """Test that interval hours < 1 is enforced to minimum of 1."""
        # Override to return negative interval
        scheduler._get_interval_hours = lambda: -5

        # Create very recent file (30 minutes old)
        recent_file = meta_dir / "recent-repo.md"
        recent_file.write_text("Recent")
        recent_time = datetime.now() - timedelta(minutes=30)
        recent_timestamp = recent_time.timestamp()

        os.utime(recent_file, (recent_timestamp, recent_timestamp))

        # Should not need refresh (< 1 hour old, minimum enforced)
        scheduler._check_and_refresh()
        assert scheduler._cli_manager.submit_work.call_count == 0

        # Create file > 1 hour old
        old_file = meta_dir / "old-repo.md"
        old_file.write_text("Old")
        old_time = datetime.now() - timedelta(hours=2)
        old_timestamp = old_time.timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Should need refresh (> 1 hour minimum)
        scheduler._check_and_refresh()
        assert scheduler._cli_manager.submit_work.call_count == 1

    def test_last_refresh_access_is_thread_safe(self, scheduler):
        """Test that _last_refresh dict access is protected by lock."""
        assert hasattr(scheduler, "_refresh_lock")
        # threading.Lock() returns _thread.lock object, check for lock-like behavior
        assert hasattr(scheduler._refresh_lock, "acquire")
        assert hasattr(scheduler._refresh_lock, "release")

    def test_get_repo_path_callback_is_used_for_submit_work(
        self, cli_manager, meta_dir, get_interval_hours
    ):
        """Test that get_repo_path callback is used to resolve repo path."""
        actual_repo_path = Path("/actual/repo/path")
        get_repo_path = Mock(return_value=actual_repo_path)

        scheduler = DescriptionRefreshScheduler(
            cli_manager=cli_manager,
            meta_dir=meta_dir,
            get_interval_hours=get_interval_hours,
            get_repo_path=get_repo_path,
        )

        old_file = meta_dir / "test-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))

        scheduler._check_and_refresh()

        get_repo_path.assert_called_once_with("test-repo")
        assert cli_manager.submit_work.call_count == 1
        call_args = cli_manager.submit_work.call_args
        repo_path_arg, callback = call_args[0]
        assert repo_path_arg == actual_repo_path

    def test_get_repo_path_returns_none_skips_repo(
        self, cli_manager, meta_dir, get_interval_hours
    ):
        """Test that repos with unresolvable paths are skipped."""
        get_repo_path = Mock(return_value=None)

        scheduler = DescriptionRefreshScheduler(
            cli_manager=cli_manager,
            meta_dir=meta_dir,
            get_interval_hours=get_interval_hours,
            get_repo_path=get_repo_path,
        )

        old_file = meta_dir / "test-repo.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))

        scheduler._check_and_refresh()

        get_repo_path.assert_called_once_with("test-repo")
        assert cli_manager.submit_work.call_count == 0


class TestDescriptionRefreshSchedulerIntegration:
    """Integration tests for DescriptionRefreshScheduler."""

    @pytest.fixture
    def meta_dir(self, tmp_path):
        """Create a temporary meta directory."""
        meta = tmp_path / "cidx-meta"
        meta.mkdir()
        return meta

    @pytest.fixture
    def actual_repos(self, tmp_path):
        """Create actual repository directories."""
        repos = {}
        for i in range(3):
            repo_path = tmp_path / f"repo-{i}"
            repo_path.mkdir()
            repos[f"repo-{i}"] = repo_path
        return repos

    @pytest.fixture
    def get_repo_path(self, actual_repos):
        """Create get_repo_path callback that resolves aliases."""

        def resolver(alias: str):
            return actual_repos.get(alias)

        return resolver

    @pytest.fixture
    def cli_manager(self):
        """Create a mock ClaudeCliManager."""
        manager = Mock()
        manager.submit_work = Mock()
        return manager

    @pytest.fixture
    def get_interval_hours(self):
        """Create a callable that returns refresh interval."""
        return lambda: 24

    @pytest.fixture
    def scheduler(self, cli_manager, meta_dir, get_interval_hours, get_repo_path):
        """Create a DescriptionRefreshScheduler instance."""
        return DescriptionRefreshScheduler(
            cli_manager=cli_manager,
            meta_dir=meta_dir,
            get_interval_hours=get_interval_hours,
            get_repo_path=get_repo_path,
        )

    def test_refresh_cycle_end_to_end(self, scheduler, meta_dir, cli_manager):
        """Test complete refresh cycle from detection to completion."""
        # Create old file needing refresh
        old_file = meta_dir / "repo-0.md"
        old_file.write_text("Old content")
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Run check and refresh
        scheduler._check_and_refresh()

        # Verify work was submitted
        assert cli_manager.submit_work.call_count == 1
        call_args = cli_manager.submit_work.call_args
        repo_path, callback = call_args[0]

        # Simulate successful completion
        callback(success=True, result="Success")

        # Verify timestamp was updated
        assert "repo-0" in scheduler._last_refresh
        # Should be very recent
        assert (datetime.now() - scheduler._last_refresh["repo-0"]).total_seconds() < 2

        # Run check again - should NOT submit work (just refreshed)
        cli_manager.submit_work.reset_mock()
        scheduler._check_and_refresh()
        assert cli_manager.submit_work.call_count == 0

    def test_config_change_applies_without_restart(
        self, scheduler, meta_dir, cli_manager
    ):
        """Test that config changes take effect without scheduler restart."""
        # Create file that's 10 hours old
        file = meta_dir / "repo-0.md"
        file.write_text("Content")
        old_time = datetime.now() - timedelta(hours=10)
        old_timestamp = old_time.timestamp()
        os.utime(file, (old_timestamp, old_timestamp))

        # With 24 hour interval, should NOT need refresh
        scheduler._check_and_refresh()
        assert cli_manager.submit_work.call_count == 0

        # Change config to 8 hours
        scheduler._get_interval_hours = lambda: 8

        # Now should need refresh
        scheduler._check_and_refresh()
        assert cli_manager.submit_work.call_count == 1

    def test_concurrent_operations_are_safe(self, scheduler, meta_dir, cli_manager):
        """Test that concurrent operations don't cause race conditions."""
        # Create multiple files needing refresh
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()
        for i in range(5):
            file = meta_dir / f"repo-{i}.md"
            file.write_text(f"Content {i}")
            os.utime(file, (old_timestamp, old_timestamp))

        # Run multiple concurrent refresh checks
        def run_check():
            scheduler._check_and_refresh()

        threads = []
        for _ in range(3):
            thread = threading.Thread(target=run_check)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All repos should have been processed without errors
        # Note: submit_work might be called multiple times due to race,
        # but _last_refresh dict should not be corrupted
        assert len(scheduler._last_refresh) > 0

        # Verify no exceptions were raised and dict is accessible
        for alias in scheduler._last_refresh:
            assert isinstance(scheduler._last_refresh[alias], datetime)
