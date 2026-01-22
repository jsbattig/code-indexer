"""
Unit tests for orphaned job cleanup on server startup.

Story #723: Clean Up Orphaned Jobs on Server Startup

Tests written FIRST following TDD methodology.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def backend_with_orphaned_jobs(tmp_path: Path) -> Generator:
    """Create a BackgroundJobsSqliteBackend with pre-seeded orphaned jobs."""
    from code_indexer.server.storage.database_manager import DatabaseSchema
    from code_indexer.server.storage.sqlite_backends import BackgroundJobsSqliteBackend

    db_path = tmp_path / "test.db"
    schema = DatabaseSchema(str(db_path))
    schema.initialize_database()
    backend = BackgroundJobsSqliteBackend(str(db_path))

    # Seed jobs in various states that will be orphaned on "restart"
    now = datetime.now(timezone.utc).isoformat()
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    # Running job (orphaned - should be cleaned up)
    backend.save_job(
        job_id="running-job-1",
        operation_type="add_golden_repo",
        status="running",
        created_at=one_hour_ago,
        started_at=one_hour_ago,
        username="user1",
        progress=50,
        repo_alias="my-repo",
    )

    # Running job (orphaned - should be cleaned up)
    backend.save_job(
        job_id="running-job-2",
        operation_type="refresh_golden_repo",
        status="running",
        created_at=one_hour_ago,
        started_at=one_hour_ago,
        username="user2",
        progress=75,
        repo_alias="other-repo",
    )

    # Pending job (orphaned - should be cleaned up)
    backend.save_job(
        job_id="pending-job-1",
        operation_type="add_golden_repo",
        status="pending",
        created_at=one_hour_ago,
        username="user1",
        progress=0,
        repo_alias="pending-repo",
    )

    # Completed job (should NOT be cleaned up)
    backend.save_job(
        job_id="completed-job-1",
        operation_type="add_golden_repo",
        status="completed",
        created_at=one_hour_ago,
        completed_at=now,
        username="user1",
        progress=100,
        repo_alias="done-repo",
        result={"success": True},
    )

    # Failed job (should NOT be cleaned up)
    backend.save_job(
        job_id="failed-job-1",
        operation_type="refresh_golden_repo",
        status="failed",
        created_at=one_hour_ago,
        completed_at=now,
        username="user2",
        progress=25,
        repo_alias="failed-repo",
        error="Git clone failed",
    )

    # Cancelled job (should NOT be cleaned up)
    backend.save_job(
        job_id="cancelled-job-1",
        operation_type="add_golden_repo",
        status="cancelled",
        created_at=one_hour_ago,
        completed_at=now,
        username="user1",
        progress=10,
        cancelled=True,
    )

    yield backend


class TestBackgroundJobsSqliteBackendOrphanedJobCleanup:
    """Tests for BackgroundJobsSqliteBackend orphaned job cleanup."""

    def test_cleanup_orphaned_jobs_marks_running_jobs_as_failed(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, running jobs are marked as failed."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Running jobs are now failed
        job1 = backend.get_job("running-job-1")
        job2 = backend.get_job("running-job-2")

        assert job1 is not None
        assert job1["status"] == "failed"

        assert job2 is not None
        assert job2["status"] == "failed"

    def test_cleanup_orphaned_jobs_marks_pending_jobs_as_failed(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, pending jobs are marked as failed."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Pending jobs are now failed
        job = backend.get_job("pending-job-1")

        assert job is not None
        assert job["status"] == "failed"

    def test_cleanup_orphaned_jobs_sets_error_message(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() cleans up jobs, they include the expected error message."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Error message is set
        job = backend.get_job("running-job-1")

        assert job is not None
        assert job["error"] == "Job interrupted by server restart"

    def test_cleanup_orphaned_jobs_sets_interrupted_at_timestamp(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() cleans up jobs, they include interrupted_at timestamp."""
        backend = backend_with_orphaned_jobs

        before_cleanup = datetime.now(timezone.utc)

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        after_cleanup = datetime.now(timezone.utc)

        # Assert: interrupted_at is set (stored in completed_at field)
        job = backend.get_job("running-job-1")

        assert job is not None
        assert job["completed_at"] is not None

        # Parse the timestamp and verify it's within expected range
        completed_at = datetime.fromisoformat(job["completed_at"])
        assert before_cleanup <= completed_at <= after_cleanup

    def test_cleanup_orphaned_jobs_returns_count_of_cleaned_jobs(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, it returns the count of jobs cleaned up."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        cleanup_result = backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Returns count of orphaned jobs (2 running + 1 pending = 3)
        assert cleanup_result == 3

    def test_cleanup_orphaned_jobs_does_not_touch_completed_jobs(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, completed jobs are not modified."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Completed job is unchanged
        job = backend.get_job("completed-job-1")

        assert job is not None
        assert job["status"] == "completed"
        assert job["result"] == {"success": True}

    def test_cleanup_orphaned_jobs_does_not_touch_failed_jobs(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, already failed jobs are not modified."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Failed job is unchanged
        job = backend.get_job("failed-job-1")

        assert job is not None
        assert job["status"] == "failed"
        assert job["error"] == "Git clone failed"

    def test_cleanup_orphaned_jobs_does_not_touch_cancelled_jobs(
        self, backend_with_orphaned_jobs
    ) -> None:
        """When cleanup_orphaned_jobs() is called, cancelled jobs are not modified."""
        backend = backend_with_orphaned_jobs

        # Act: Clean up orphaned jobs
        backend.cleanup_orphaned_jobs_on_startup()

        # Assert: Cancelled job is unchanged
        job = backend.get_job("cancelled-job-1")

        assert job is not None
        assert job["status"] == "cancelled"
        assert job["cancelled"] is True

    def test_cleanup_orphaned_jobs_with_no_orphaned_jobs_returns_zero(
        self, tmp_path: Path
    ) -> None:
        """When cleanup_orphaned_jobs() is called with no orphans, it returns 0."""
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            BackgroundJobsSqliteBackend,
        )

        db_path = tmp_path / "clean_test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        backend = BackgroundJobsSqliteBackend(str(db_path))

        # Only add completed jobs
        backend.save_job(
            job_id="completed-only",
            operation_type="add_golden_repo",
            status="completed",
            created_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            username="user1",
            progress=100,
        )

        # Act: Clean up orphaned jobs
        cleanup_result = backend.cleanup_orphaned_jobs_on_startup()

        # Assert: No jobs cleaned up
        assert cleanup_result == 0


class TestBackgroundJobManagerOrphanedJobCleanup:
    """Tests for BackgroundJobManager orphaned job cleanup during initialization."""

    def test_manager_cleans_orphaned_jobs_on_sqlite_load(self, tmp_path: Path) -> None:
        """When BackgroundJobManager initializes with SQLite, orphaned jobs are cleaned up."""
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            BackgroundJobsSqliteBackend,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )

        # Setup: Create database with orphaned jobs
        db_path = tmp_path / "manager_test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        backend = BackgroundJobsSqliteBackend(str(db_path))

        now = datetime.now(timezone.utc).isoformat()

        # Seed running job
        backend.save_job(
            job_id="orphan-running",
            operation_type="add_golden_repo",
            status="running",
            created_at=now,
            started_at=now,
            username="testuser",
            progress=50,
        )

        # Seed pending job
        backend.save_job(
            job_id="orphan-pending",
            operation_type="refresh_golden_repo",
            status="pending",
            created_at=now,
            username="testuser",
            progress=0,
        )

        # Act: Create new BackgroundJobManager (simulates server restart)
        manager = BackgroundJobManager(use_sqlite=True, db_path=str(db_path))

        # Assert: Jobs loaded into memory are marked as failed
        running_job = manager.get_job_status("orphan-running", username="testuser")
        pending_job = manager.get_job_status("orphan-pending", username="testuser")

        assert running_job is not None
        assert running_job["status"] == "failed"
        assert running_job["error"] == "Job interrupted by server restart"

        assert pending_job is not None
        assert pending_job["status"] == "failed"
        assert pending_job["error"] == "Job interrupted by server restart"

        # Cleanup
        manager.shutdown()

    def test_manager_logs_orphaned_job_cleanup_count(
        self, tmp_path: Path, caplog
    ) -> None:
        """When BackgroundJobManager cleans orphaned jobs, it logs the count."""
        import logging
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            BackgroundJobsSqliteBackend,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )

        # Setup: Create database with orphaned jobs
        db_path = tmp_path / "log_test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        backend = BackgroundJobsSqliteBackend(str(db_path))

        now = datetime.now(timezone.utc).isoformat()

        # Seed orphaned jobs
        backend.save_job(
            job_id="orphan-1",
            operation_type="add_golden_repo",
            status="running",
            created_at=now,
            started_at=now,
            username="user1",
            progress=50,
        )
        backend.save_job(
            job_id="orphan-2",
            operation_type="add_golden_repo",
            status="pending",
            created_at=now,
            username="user2",
            progress=0,
        )

        # Act: Create new BackgroundJobManager with logging capture
        with caplog.at_level(logging.INFO):
            manager = BackgroundJobManager(use_sqlite=True, db_path=str(db_path))

        # Assert: Log message indicates cleanup count
        assert any(
            "orphaned" in record.message.lower() and "2" in record.message
            for record in caplog.records
        )

        # Cleanup
        manager.shutdown()

    def test_manager_shows_zero_running_pending_after_restart(
        self, tmp_path: Path
    ) -> None:
        """After restart with orphaned jobs, running and pending counts should be zero."""
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            BackgroundJobsSqliteBackend,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )

        # Setup: Create database with orphaned jobs
        db_path = tmp_path / "counts_test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        backend = BackgroundJobsSqliteBackend(str(db_path))

        now = datetime.now(timezone.utc).isoformat()

        # Seed orphaned running and pending jobs
        backend.save_job(
            job_id="running-orphan",
            operation_type="add_golden_repo",
            status="running",
            created_at=now,
            started_at=now,
            username="user1",
            progress=50,
        )
        backend.save_job(
            job_id="pending-orphan",
            operation_type="add_golden_repo",
            status="pending",
            created_at=now,
            username="user1",
            progress=0,
        )

        # Act: Create new BackgroundJobManager (simulates server restart)
        manager = BackgroundJobManager(use_sqlite=True, db_path=str(db_path))

        # Assert: Dashboard metrics show correct counts
        assert manager.get_active_job_count() == 0  # No running jobs
        assert manager.get_pending_job_count() == 0  # No pending jobs
        assert manager.get_failed_job_count() >= 2  # At least 2 failed (the orphans)

        # Cleanup
        manager.shutdown()

    def test_manager_preserves_completed_jobs_during_cleanup(
        self, tmp_path: Path
    ) -> None:
        """When manager initializes, completed jobs from before restart are preserved."""
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            BackgroundJobsSqliteBackend,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )

        # Setup: Create database with mixed job states
        db_path = tmp_path / "preserve_test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        backend = BackgroundJobsSqliteBackend(str(db_path))

        now = datetime.now(timezone.utc).isoformat()

        # Seed completed job
        backend.save_job(
            job_id="completed-preserved",
            operation_type="add_golden_repo",
            status="completed",
            created_at=now,
            completed_at=now,
            username="user1",
            progress=100,
            result={"files_indexed": 500},
        )

        # Seed orphaned running job
        backend.save_job(
            job_id="running-orphan",
            operation_type="add_golden_repo",
            status="running",
            created_at=now,
            started_at=now,
            username="user1",
            progress=50,
        )

        # Act: Create new BackgroundJobManager
        manager = BackgroundJobManager(use_sqlite=True, db_path=str(db_path))

        # Assert: Completed job is preserved
        completed_job = manager.get_job_status("completed-preserved", username="user1")
        assert completed_job is not None
        assert completed_job["status"] == "completed"
        assert completed_job["result"] == {"files_indexed": 500}

        # Cleanup
        manager.shutdown()
