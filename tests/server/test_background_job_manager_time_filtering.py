"""
Unit tests for BackgroundJobManager time filtering functionality.

Tests AC3, AC4, AC5, AC6 from Story #541.
Following TDD: These tests are written FIRST and will fail until implementation is complete.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    BackgroundJob,
    JobStatus,
)


class TestBackgroundJobManagerTimeFiltering:
    """Test suite for time filtering functionality in BackgroundJobManager."""

    def test_calculate_cutoff_24h(self):
        """Test that _calculate_cutoff returns correct datetime for 24h filter."""
        manager = BackgroundJobManager(storage_path=None)

        # Get cutoff for 24h
        cutoff = manager._calculate_cutoff("24h")

        # Verify cutoff is approximately 24 hours ago
        expected_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        time_diff = abs((cutoff - expected_cutoff).total_seconds())

        # Allow 1 second tolerance for test execution time
        assert time_diff < 1, f"Cutoff should be ~24h ago, got {cutoff}"

    def test_calculate_cutoff_7d(self):
        """Test that _calculate_cutoff returns correct datetime for 7d filter."""
        manager = BackgroundJobManager(storage_path=None)

        cutoff = manager._calculate_cutoff("7d")

        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        time_diff = abs((cutoff - expected_cutoff).total_seconds())

        assert time_diff < 1, f"Cutoff should be ~7 days ago, got {cutoff}"

    def test_calculate_cutoff_30d(self):
        """Test that _calculate_cutoff returns correct datetime for 30d filter."""
        manager = BackgroundJobManager(storage_path=None)

        cutoff = manager._calculate_cutoff("30d")

        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        time_diff = abs((cutoff - expected_cutoff).total_seconds())

        assert time_diff < 1, f"Cutoff should be ~30 days ago, got {cutoff}"

    def test_calculate_cutoff_default(self):
        """Test that _calculate_cutoff defaults to 24h for invalid filter."""
        manager = BackgroundJobManager(storage_path=None)

        cutoff = manager._calculate_cutoff("invalid")

        expected_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        time_diff = abs((cutoff - expected_cutoff).total_seconds())

        assert time_diff < 1, "Invalid filter should default to 24h"

    def test_get_job_stats_with_filter_24h(self):
        """Test job stats filtering for 24h time range (AC3)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Create jobs at different times
        # Job 1: Completed 12 hours ago (within 24h)
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=12),
            started_at=now - timedelta(hours=12),
            completed_at=now - timedelta(hours=12),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        # Job 2: Completed 30 hours ago (outside 24h)
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=30),
            started_at=now - timedelta(hours=30),
            completed_at=now - timedelta(hours=30),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        # Job 3: Failed 6 hours ago (within 24h)
        job3 = BackgroundJob(
            job_id="job3",
            operation_type="test",
            status=JobStatus.FAILED,
            created_at=now - timedelta(hours=6),
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6),
            result=None,
            error="test error",
            progress=0,
            username="testuser",
        )

        # Add jobs to manager
        manager.jobs = {"job1": job1, "job2": job2, "job3": job3}

        # Get stats with 24h filter
        stats = manager.get_job_stats_with_filter("24h")

        # Verify only jobs within 24h are counted
        assert stats["completed"] == 1, "Should count 1 completed job within 24h"
        assert stats["failed"] == 1, "Should count 1 failed job within 24h"

    def test_get_job_stats_with_filter_7d(self):
        """Test job stats filtering for 7d time range (AC3)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Job within 7 days
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(days=5),
            started_at=now - timedelta(days=5),
            completed_at=now - timedelta(days=5),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        # Job outside 7 days
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(days=10),
            started_at=now - timedelta(days=10),
            completed_at=now - timedelta(days=10),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        stats = manager.get_job_stats_with_filter("7d")

        assert stats["completed"] == 1, "Should count 1 completed job within 7 days"
        assert stats["failed"] == 0, "Should count 0 failed jobs"

    def test_get_job_stats_with_filter_30d(self):
        """Test job stats filtering for 30d time range (AC3)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Job within 30 days
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.FAILED,
            created_at=now - timedelta(days=20),
            started_at=now - timedelta(days=20),
            completed_at=now - timedelta(days=20),
            result=None,
            error="test",
            progress=0,
            username="testuser",
        )

        # Job outside 30 days
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.FAILED,
            created_at=now - timedelta(days=35),
            started_at=now - timedelta(days=35),
            completed_at=now - timedelta(days=35),
            result=None,
            error="test",
            progress=0,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        stats = manager.get_job_stats_with_filter("30d")

        assert stats["completed"] == 0, "Should count 0 completed jobs"
        assert stats["failed"] == 1, "Should count 1 failed job within 30 days"

    def test_get_job_stats_ignores_running_and_pending(self):
        """Test that job stats filtering ignores running and pending jobs."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Running job
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.RUNNING,
            created_at=now,
            started_at=now,
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
        )

        # Pending job
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.PENDING,
            created_at=now,
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        stats = manager.get_job_stats_with_filter("24h")

        assert stats["completed"] == 0, "Should not count running jobs"
        assert stats["failed"] == 0, "Should not count pending jobs"

    def test_job_persistence_save(self):
        """Test that jobs are persisted to storage file (AC4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = str(Path(tmpdir) / "jobs.json")
            manager = BackgroundJobManager(storage_path=storage_path)

            now = datetime.now(timezone.utc)

            # Create a job
            job = BackgroundJob(
                job_id="test_job",
                operation_type="test_op",
                status=JobStatus.COMPLETED,
                created_at=now,
                started_at=now,
                completed_at=now,
                result={"status": "success"},
                error=None,
                progress=100,
                username="testuser",
            )

            manager.jobs["test_job"] = job
            manager._persist_jobs()

            # Verify file exists
            assert Path(storage_path).exists(), "Storage file should be created"

            # Verify file contains job data
            with open(storage_path, "r") as f:
                saved_data = json.load(f)

            assert "test_job" in saved_data, "Job should be in saved data"
            assert saved_data["test_job"]["operation_type"] == "test_op"
            assert saved_data["test_job"]["status"] == "completed"

    def test_job_persistence_load(self):
        """Test that jobs are loaded from storage file on initialization (AC4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = str(Path(tmpdir) / "jobs.json")

            # Create initial manager and save a job
            manager1 = BackgroundJobManager(storage_path=storage_path)

            now = datetime.now(timezone.utc)
            job = BackgroundJob(
                job_id="persisted_job",
                operation_type="persist_test",
                status=JobStatus.COMPLETED,
                created_at=now,
                started_at=now,
                completed_at=now,
                result={"data": "test"},
                error=None,
                progress=100,
                username="testuser",
            )

            manager1.jobs["persisted_job"] = job
            manager1._persist_jobs()

            # Create new manager instance (simulating server restart)
            manager2 = BackgroundJobManager(storage_path=storage_path)

            # Verify job was loaded
            assert "persisted_job" in manager2.jobs, "Job should be loaded from storage"
            loaded_job = manager2.jobs["persisted_job"]
            assert loaded_job.operation_type == "persist_test"
            assert loaded_job.status == JobStatus.COMPLETED
            assert loaded_job.username == "testuser"

    def test_get_recent_jobs_with_filter_default_30d(self):
        """Test recent jobs with default 30d filter (AC5)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Job within 30 days
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(days=20),
            started_at=now - timedelta(days=20),
            completed_at=now - timedelta(days=20),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        # Job outside 30 days
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(days=40),
            started_at=now - timedelta(days=40),
            completed_at=now - timedelta(days=40),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        # Get recent jobs with default filter
        recent = manager.get_recent_jobs_with_filter()

        assert len(recent) == 1, "Should return 1 job within default 30d range"
        assert recent[0]["job_id"] == "job1"

    def test_get_recent_jobs_with_filter_24h(self):
        """Test recent jobs with 24h filter (AC5)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Job within 24h
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=12),
            started_at=now - timedelta(hours=12),
            completed_at=now - timedelta(hours=12),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        # Job outside 24h but within 7d
        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(days=3),
            started_at=now - timedelta(days=3),
            completed_at=now - timedelta(days=3),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        recent = manager.get_recent_jobs_with_filter("24h")

        assert len(recent) == 1, "Should return 1 job within 24h"
        assert recent[0]["job_id"] == "job1"

    def test_get_recent_jobs_limit_20(self):
        """Test that recent jobs are limited to 20 items (AC6)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Create 25 jobs all within time range
        for i in range(25):
            job = BackgroundJob(
                job_id=f"job{i}",
                operation_type="test",
                status=JobStatus.COMPLETED,
                created_at=now - timedelta(hours=i),
                started_at=now - timedelta(hours=i),
                completed_at=now - timedelta(hours=i),
                result={},
                error=None,
                progress=100,
                username="testuser",
            )
            manager.jobs[f"job{i}"] = job

        recent = manager.get_recent_jobs_with_filter("30d", limit=20)

        assert len(recent) == 20, "Should return maximum of 20 jobs"

    def test_get_recent_jobs_sorted_by_time(self):
        """Test that recent jobs are sorted by completion time (newest first)."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        # Create jobs in non-chronological order
        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=10),
            started_at=now - timedelta(hours=10),
            completed_at=now - timedelta(hours=10),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=5),
            started_at=now - timedelta(hours=5),
            completed_at=now - timedelta(hours=5),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        job3 = BackgroundJob(
            job_id="job3",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=15),
            started_at=now - timedelta(hours=15),
            completed_at=now - timedelta(hours=15),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2, "job3": job3}

        recent = manager.get_recent_jobs_with_filter("30d")

        # Verify sorted by completion time (newest first)
        assert recent[0]["job_id"] == "job2", "Most recent job should be first"
        assert recent[1]["job_id"] == "job1", "Second most recent should be second"
        assert recent[2]["job_id"] == "job3", "Oldest job should be last"

    def test_get_recent_jobs_includes_failed_jobs(self):
        """Test that recent jobs include failed jobs."""
        manager = BackgroundJobManager(storage_path=None)

        now = datetime.now(timezone.utc)

        job1 = BackgroundJob(
            job_id="job1",
            operation_type="test",
            status=JobStatus.COMPLETED,
            created_at=now - timedelta(hours=5),
            started_at=now - timedelta(hours=5),
            completed_at=now - timedelta(hours=5),
            result={},
            error=None,
            progress=100,
            username="testuser",
        )

        job2 = BackgroundJob(
            job_id="job2",
            operation_type="test",
            status=JobStatus.FAILED,
            created_at=now - timedelta(hours=3),
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=3),
            result=None,
            error="test error",
            progress=0,
            username="testuser",
        )

        manager.jobs = {"job1": job1, "job2": job2}

        recent = manager.get_recent_jobs_with_filter("24h")

        assert len(recent) == 2, "Should include both completed and failed jobs"
        assert recent[0]["status"] == "failed"
        assert recent[1]["status"] == "completed"
