"""
Test Job Queue Verification - Story #693

This module verifies the existing SyncJobManager behavior for job queue
concurrency limits and provides tests for new configuration features.
"""

import pytest

from code_indexer.server.jobs.manager import SyncJobManager
from code_indexer.server.jobs.models import JobType


class TestJobQueueConcurrency:
    """Verify system-wide and per-user concurrency limits are enforced."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create SyncJobManager with specific concurrency limits."""
        return SyncJobManager(
            storage_path=str(tmp_path / "jobs.json"),
            max_total_concurrent_jobs=2,
            max_concurrent_jobs_per_user=1,
        )

    def test_respects_max_total_concurrent_jobs(self, job_manager):
        """Verify system-wide limit is enforced - only 2 jobs run, rest queued."""
        job_ids = []
        for i in range(5):
            job_id = job_manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/repo{i}.git",
            )
            job_ids.append(job_id)

        running_jobs = [
            jid for jid in job_ids
            if job_manager.get_job(jid)["status"] == "running"
        ]
        queued_jobs = [
            jid for jid in job_ids
            if job_manager.get_job(jid)["status"] == "queued"
        ]

        assert len(running_jobs) == 2
        assert len(queued_jobs) == 3

    def test_respects_max_per_user_concurrent_jobs(self, job_manager):
        """Verify per-user limit is enforced - only 1 job per user runs."""
        job_ids = []
        for i in range(3):
            job_id = job_manager.create_job(
                username="same_user",
                user_alias="Same User",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/user-repo{i}.git",
            )
            job_ids.append(job_id)

        running_jobs = [
            jid for jid in job_ids
            if job_manager.get_job(jid)["status"] == "running"
        ]
        queued_jobs = [
            jid for jid in job_ids
            if job_manager.get_job(jid)["status"] == "queued"
        ]

        assert len(running_jobs) == 1
        assert len(queued_jobs) == 2

    def test_queue_fifo_order(self, job_manager):
        """Verify jobs start in FIFO order (first queued, first started)."""
        job_ids = []
        for i in range(5):
            job_id = job_manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/fifo-repo{i}.git",
            )
            job_ids.append(job_id)

        # First 2 jobs should be running
        assert job_manager.get_job(job_ids[0])["status"] == "running"
        assert job_manager.get_job(job_ids[1])["status"] == "running"

        # Jobs 2, 3, 4 should be queued with positions 1, 2, 3
        for idx in range(2, 5):
            job = job_manager.get_job(job_ids[idx])
            assert job["status"] == "queued"
            assert job["queue_position"] == idx - 1

    def test_job_transitions_running_when_slot_available(self, job_manager):
        """Verify queued job transitions to running when job completes."""
        job_ids = []
        for i in range(3):
            job_id = job_manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/slot-repo{i}.git",
            )
            job_ids.append(job_id)

        # Verify initial state
        assert job_manager.get_job(job_ids[0])["status"] == "running"
        assert job_manager.get_job(job_ids[1])["status"] == "running"
        assert job_manager.get_job(job_ids[2])["status"] == "queued"

        # Complete first job
        job_manager.mark_job_completed(job_ids[0])

        # Verify queued job is now running
        assert job_manager.get_job(job_ids[0])["status"] == "completed"
        assert job_manager.get_job(job_ids[1])["status"] == "running"
        assert job_manager.get_job(job_ids[2])["status"] == "running"


class TestJobQueueConfiguration:
    """Test configuration updates for job queue settings."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create SyncJobManager with default config."""
        return SyncJobManager(
            storage_path=str(tmp_path / "jobs.json"),
            max_total_concurrent_jobs=10,
            max_concurrent_jobs_per_user=3,
        )

    def test_update_max_total_concurrent_jobs(self, job_manager):
        """Verify max_total_concurrent_jobs can be updated at runtime."""
        assert job_manager.max_total_concurrent_jobs == 10
        job_manager.max_total_concurrent_jobs = 5
        assert job_manager.max_total_concurrent_jobs == 5

    def test_update_max_concurrent_jobs_per_user(self, job_manager):
        """Verify max_concurrent_jobs_per_user can be updated at runtime."""
        assert job_manager.max_concurrent_jobs_per_user == 3
        job_manager.max_concurrent_jobs_per_user = 2
        assert job_manager.max_concurrent_jobs_per_user == 2

    def test_config_update_affects_new_jobs(self, tmp_path):
        """Verify config changes affect new job creation."""
        manager = SyncJobManager(
            storage_path=str(tmp_path / "jobs.json"),
            max_total_concurrent_jobs=2,
            max_concurrent_jobs_per_user=3,
        )

        # Create 2 jobs - both should run
        job_ids = []
        for i in range(2):
            job_id = manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/config-repo{i}.git",
            )
            job_ids.append(job_id)

        assert manager.get_job(job_ids[0])["status"] == "running"
        assert manager.get_job(job_ids[1])["status"] == "running"

        # Change config to allow 3 concurrent
        manager.max_total_concurrent_jobs = 3

        # Create another job - should also run
        job_id3 = manager.create_job(
            username="user2",
            user_alias="User 2",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/config-repo2.git",
        )

        assert manager.get_job(job_id3)["status"] == "running"


class TestJobQueueStatusAPI:
    """Test queue status retrieval functionality."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create SyncJobManager for status testing."""
        return SyncJobManager(
            storage_path=str(tmp_path / "jobs.json"),
            max_total_concurrent_jobs=2,
            max_concurrent_jobs_per_user=1,
        )

    def test_get_queue_status_counts(self, job_manager):
        """Verify queue status returns correct counts."""
        for i in range(5):
            job_manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/status-repo{i}.git",
            )

        running_count = job_manager._count_total_running_jobs()
        queued_count = len(job_manager._job_queue)

        assert running_count == 2
        assert queued_count == 3

    def test_get_configuration_values(self, job_manager):
        """Verify configuration values are accessible."""
        assert job_manager.max_total_concurrent_jobs == 2
        assert job_manager.max_concurrent_jobs_per_user == 1

    def test_estimated_wait_time(self, tmp_path):
        """Verify estimated wait time is calculated based on queue position."""
        manager = SyncJobManager(
            storage_path=str(tmp_path / "jobs.json"),
            max_total_concurrent_jobs=1,
            max_concurrent_jobs_per_user=1,
            average_job_duration_minutes=15,
        )

        # Create 3 jobs - 1 runs, 2 queued
        job1 = manager.create_job(
            username="user1",
            user_alias="User 1",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/wait-repo1.git",
        )
        job2 = manager.create_job(
            username="user2",
            user_alias="User 2",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/wait-repo2.git",
        )
        job3 = manager.create_job(
            username="user3",
            user_alias="User 3",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/wait-repo3.git",
        )

        # Position 1 * 15 min = 15 min wait
        job2_data = manager.get_job(job2)
        assert job2_data["estimated_wait_minutes"] == 15

        # Position 2 * 15 min = 30 min wait
        job3_data = manager.get_job(job3)
        assert job3_data["estimated_wait_minutes"] == 30
