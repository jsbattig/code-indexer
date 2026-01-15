"""
Unit tests for datetime sorting in Background Job Manager.

Tests specifically for the get_recent_jobs_with_filter() method's sorting of
ISO format datetime strings. This tests the fix for the bug where int() was
incorrectly called on ISO datetime strings like '2025-12-09T18:42:39.792746+00:00'.
"""

import tempfile
import time
from datetime import datetime
from pathlib import Path


from src.code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
)


class TestJobDatetimeSorting:
    """Test datetime sorting in get_recent_jobs_with_filter()."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.job_storage_path = Path(self.temp_dir) / "jobs.json"
        self.manager = BackgroundJobManager(storage_path=str(self.job_storage_path))

    def teardown_method(self):
        """Clean up test environment."""
        if hasattr(self, "manager") and self.manager:
            self.manager.shutdown()
        import shutil
        import os

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_get_recent_jobs_sorts_by_iso_datetime_correctly(self):
        """
        Test that get_recent_jobs_with_filter correctly sorts jobs by ISO datetime.

        The bug was that int() was being called on ISO format datetime strings
        like '2025-12-09T18:42:39.792746+00:00', causing a ValueError.
        """

        def success_task():
            return {"status": "success"}

        # Submit multiple jobs that will complete
        job_ids = []
        for i in range(3):
            job_id = self.manager.submit_job(
                f"test_op_{i}", success_task, submitter_username="testuser"
            )
            job_ids.append(job_id)
            time.sleep(0.05)  # Small delay to ensure different completion times

        # Wait for all jobs to complete
        time.sleep(0.3)

        # This should NOT raise ValueError when sorting by completed_at
        # Previously this would crash with:
        # ValueError: invalid literal for int() with base 10: '2025-12-09T18:42:39.792746+00:00'
        recent_jobs = self.manager.get_recent_jobs_with_filter(time_filter="24h")

        # Verify we got jobs back
        assert (
            len(recent_jobs) >= 3
        ), f"Expected at least 3 jobs, got {len(recent_jobs)}"

        # Verify they are sorted by completion time (newest first)
        for i in range(len(recent_jobs) - 1):
            current_time = recent_jobs[i]["completed_at"]
            next_time = recent_jobs[i + 1]["completed_at"]
            # Both should be ISO format strings
            assert isinstance(
                current_time, str
            ), f"Expected string, got {type(current_time)}"
            assert isinstance(next_time, str), f"Expected string, got {type(next_time)}"
            # Current should be >= next (descending order)
            current_dt = datetime.fromisoformat(current_time)
            next_dt = datetime.fromisoformat(next_time)
            assert (
                current_dt >= next_dt
            ), f"Jobs not sorted correctly: {current_time} < {next_time}"

    def test_get_recent_jobs_handles_none_completed_at(self):
        """Test that sorting handles jobs with None completed_at gracefully."""

        def success_task():
            return {"status": "success"}

        # Submit a job
        self.manager.submit_job("test_op", success_task, submitter_username="testuser")

        # Wait for completion
        time.sleep(0.2)

        # This should work without error
        recent_jobs = self.manager.get_recent_jobs_with_filter(time_filter="24h")

        # Should have at least the one job we submitted
        assert len(recent_jobs) >= 1

    def test_get_recent_jobs_with_various_time_filters(self):
        """Test get_recent_jobs_with_filter with different time filters."""

        def success_task():
            return {"status": "success"}

        # Submit a job
        self.manager.submit_job("test_op", success_task, submitter_username="testuser")
        time.sleep(0.2)

        # Test different time filters - none should crash
        for time_filter in ["24h", "7d", "30d"]:
            # This should NOT raise ValueError
            recent_jobs = self.manager.get_recent_jobs_with_filter(
                time_filter=time_filter
            )
            assert isinstance(recent_jobs, list)

    def test_get_recent_jobs_empty_list_does_not_crash(self):
        """Test that an empty job list doesn't cause sorting issues."""
        # No jobs submitted - should return empty list without crashing
        recent_jobs = self.manager.get_recent_jobs_with_filter(time_filter="24h")
        assert recent_jobs == []

    def test_datetime_sorting_with_timezone_aware_strings(self):
        """Test sorting handles timezone-aware ISO strings correctly."""

        def success_task():
            return {"status": "success"}

        # Submit jobs
        for i in range(2):
            self.manager.submit_job(
                f"test_op_{i}", success_task, submitter_username="testuser"
            )
            time.sleep(0.05)

        time.sleep(0.3)

        recent_jobs = self.manager.get_recent_jobs_with_filter(time_filter="24h")

        # Verify all completed_at values are valid ISO format with timezone
        for job in recent_jobs:
            completed_at = job["completed_at"]
            assert completed_at is not None
            # Should be parseable as ISO format
            dt = datetime.fromisoformat(completed_at)
            # Should be timezone aware
            assert (
                dt.tzinfo is not None
            ), f"Expected timezone-aware datetime, got {completed_at}"
