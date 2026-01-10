"""
Unit tests for BackgroundJobsSqliteBackend - SQLite storage for background jobs.

Tests written FIRST following TDD methodology.
Bug Fix: BackgroundJobManager not using SQLite - Jobs not showing in Dashboard
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def backend(tmp_path: Path) -> Generator:
    """Create a BackgroundJobsSqliteBackend with initialized database."""
    from code_indexer.server.storage.database_manager import DatabaseSchema
    from code_indexer.server.storage.sqlite_backends import BackgroundJobsSqliteBackend

    db_path = tmp_path / "test.db"
    schema = DatabaseSchema(str(db_path))
    schema.initialize_database()
    yield BackgroundJobsSqliteBackend(str(db_path))


class TestBackgroundJobsSqliteBackend:
    """Tests for BackgroundJobsSqliteBackend CRUD operations."""

    def test_save_job_inserts_new_record(self, backend, tmp_path: Path) -> None:
        """When save_job() is called, a new record is inserted in background_jobs table."""
        backend.save_job(
            job_id="job-001",
            operation_type="add_golden_repo",
            status="pending",
            created_at="2025-01-15T10:00:00+00:00",
            username="testuser",
            progress=0,
        )

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        cursor = conn.execute(
            "SELECT job_id, operation_type, status, username, progress FROM background_jobs"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "job-001"
        assert row[1] == "add_golden_repo"
        assert row[2] == "pending"
        assert row[3] == "testuser"
        assert row[4] == 0

    def test_save_job_with_all_fields(self, backend) -> None:
        """When save_job() is called with all optional fields, all are stored correctly."""
        result_data = {"files_indexed": 100, "time_seconds": 60}
        claude_actions = ["Installed dependencies", "Built project"]
        extended_error = {"code": "SCIP_FAILED", "project": "backend"}
        language_status = {"python": {"status": "completed"}, "java": {"status": "failed"}}

        backend.save_job(
            job_id="job-full",
            operation_type="scip_generate",
            status="completed",
            created_at="2025-01-15T10:00:00+00:00",
            started_at="2025-01-15T10:00:05+00:00",
            completed_at="2025-01-15T10:05:00+00:00",
            result=result_data,
            error=None,
            progress=100,
            username="admin",
            is_admin=True,
            cancelled=False,
            repo_alias="my-repo",
            resolution_attempts=2,
            claude_actions=claude_actions,
            failure_reason=None,
            extended_error=extended_error,
            language_resolution_status=language_status,
        )

        job = backend.get_job("job-full")

        assert job is not None
        assert job["job_id"] == "job-full"
        assert job["operation_type"] == "scip_generate"
        assert job["status"] == "completed"
        assert job["started_at"] == "2025-01-15T10:00:05+00:00"
        assert job["completed_at"] == "2025-01-15T10:05:00+00:00"
        assert job["result"] == result_data
        assert job["is_admin"] is True
        assert job["repo_alias"] == "my-repo"
        assert job["resolution_attempts"] == 2
        assert job["claude_actions"] == claude_actions
        assert job["extended_error"] == extended_error
        assert job["language_resolution_status"] == language_status

    def test_get_job_returns_existing_record(self, backend) -> None:
        """When get_job() is called with existing job_id, it returns the job details."""
        backend.save_job(
            job_id="job-002",
            operation_type="refresh_repo",
            status="running",
            created_at="2025-01-15T10:00:00+00:00",
            username="user2",
            progress=50,
        )

        result = backend.get_job("job-002")

        assert result is not None
        assert result["job_id"] == "job-002"
        assert result["operation_type"] == "refresh_repo"
        assert result["status"] == "running"

    def test_get_job_returns_none_for_nonexistent(self, backend) -> None:
        """When get_job() is called with nonexistent job_id, it returns None."""
        result = backend.get_job("nonexistent-job")
        assert result is None

    def test_update_job_modifies_record(self, backend) -> None:
        """When update_job() is called with new values, the record is updated."""
        backend.save_job(
            job_id="job-003",
            operation_type="add_golden_repo",
            status="pending",
            created_at="2025-01-15T10:00:00+00:00",
            username="user3",
            progress=0,
        )

        backend.update_job(
            job_id="job-003",
            status="completed",
            progress=100,
            completed_at="2025-01-15T10:05:00+00:00",
            result={"success": True},
        )

        result = backend.get_job("job-003")
        assert result is not None
        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["completed_at"] == "2025-01-15T10:05:00+00:00"
        assert result["result"] == {"success": True}

    def test_list_jobs_returns_all_records(self, backend) -> None:
        """When list_jobs() is called, it returns all jobs."""
        backend.save_job(
            job_id="job-a", operation_type="add_golden_repo", status="pending",
            created_at="2025-01-15T10:00:00+00:00", username="user1", progress=0,
        )
        backend.save_job(
            job_id="job-b", operation_type="refresh_repo", status="running",
            created_at="2025-01-15T10:01:00+00:00", username="user2", progress=50,
        )

        result = backend.list_jobs()

        assert len(result) == 2
        job_ids = [j["job_id"] for j in result]
        assert "job-a" in job_ids
        assert "job-b" in job_ids

    def test_list_jobs_by_username(self, backend) -> None:
        """When list_jobs() is called with username filter, it returns only that user's jobs."""
        backend.save_job(
            job_id="job-user1-a", operation_type="add_golden_repo", status="completed",
            created_at="2025-01-15T10:00:00+00:00", username="user1", progress=100,
        )
        backend.save_job(
            job_id="job-user1-b", operation_type="refresh_repo", status="running",
            created_at="2025-01-15T10:01:00+00:00", username="user1", progress=50,
        )
        backend.save_job(
            job_id="job-user2-a", operation_type="add_golden_repo", status="pending",
            created_at="2025-01-15T10:02:00+00:00", username="user2", progress=0,
        )

        result = backend.list_jobs(username="user1")

        assert len(result) == 2
        assert all(j["username"] == "user1" for j in result)

    def test_list_jobs_by_status(self, backend) -> None:
        """When list_jobs() is called with status filter, it returns only jobs with that status."""
        backend.save_job(
            job_id="job-pending", operation_type="add_golden_repo", status="pending",
            created_at="2025-01-15T10:00:00+00:00", username="user1", progress=0,
        )
        backend.save_job(
            job_id="job-running", operation_type="refresh_repo", status="running",
            created_at="2025-01-15T10:01:00+00:00", username="user1", progress=50,
        )

        result = backend.list_jobs(status="running")

        assert len(result) == 1
        assert result[0]["job_id"] == "job-running"

    def test_list_jobs_with_pagination(self, backend) -> None:
        """When list_jobs() is called with limit and offset, it returns paginated results."""
        for i in range(5):
            backend.save_job(
                job_id=f"job-{i}", operation_type="add_golden_repo", status="completed",
                created_at=f"2025-01-15T10:0{i}:00+00:00", username="user1", progress=100,
            )

        page1 = backend.list_jobs(limit=2, offset=0)
        page2 = backend.list_jobs(limit=2, offset=2)
        page3 = backend.list_jobs(limit=2, offset=4)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

    def test_delete_job_removes_record(self, backend) -> None:
        """When delete_job() is called, the record is removed."""
        backend.save_job(
            job_id="job-del", operation_type="add_golden_repo", status="completed",
            created_at="2025-01-15T10:00:00+00:00", username="user1", progress=100,
        )

        assert backend.get_job("job-del") is not None
        deleted = backend.delete_job("job-del")
        assert deleted is True
        assert backend.get_job("job-del") is None

    def test_delete_job_returns_false_for_nonexistent(self, backend) -> None:
        """When delete_job() is called for nonexistent job, it returns False."""
        deleted = backend.delete_job("nonexistent")
        assert deleted is False

    def test_cleanup_old_jobs_removes_old_completed_jobs(self, backend) -> None:
        """When cleanup_old_jobs() is called, only old completed/failed jobs are removed."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

        backend.save_job(
            job_id="old-completed", operation_type="add_golden_repo", status="completed",
            created_at=old_time.isoformat(), completed_at=old_time.isoformat(),
            username="user1", progress=100,
        )
        backend.save_job(
            job_id="recent-completed", operation_type="add_golden_repo", status="completed",
            created_at=recent_time.isoformat(), completed_at=recent_time.isoformat(),
            username="user1", progress=100,
        )
        backend.save_job(
            job_id="running", operation_type="add_golden_repo", status="running",
            created_at=old_time.isoformat(), username="user1", progress=50,
        )

        cleaned_count = backend.cleanup_old_jobs(max_age_hours=24)

        assert cleaned_count == 1
        assert backend.get_job("old-completed") is None
        assert backend.get_job("recent-completed") is not None
        assert backend.get_job("running") is not None

    def test_count_jobs_by_status(self, backend) -> None:
        """When count_jobs_by_status() is called, it returns counts for each status."""
        backend.save_job(
            job_id="job-pending", operation_type="add_golden_repo", status="pending",
            created_at="2025-01-15T10:00:00+00:00", username="user1", progress=0,
        )
        backend.save_job(
            job_id="job-running-1", operation_type="refresh_repo", status="running",
            created_at="2025-01-15T10:01:00+00:00", username="user1", progress=50,
        )
        backend.save_job(
            job_id="job-running-2", operation_type="refresh_repo", status="running",
            created_at="2025-01-15T10:02:00+00:00", username="user2", progress=30,
        )

        counts = backend.count_jobs_by_status()

        assert counts["pending"] == 1
        assert counts["running"] == 2
        assert counts.get("failed", 0) == 0

    def test_get_job_stats_with_time_filter(self, backend) -> None:
        """When get_job_stats() is called with time_filter, it returns stats for that range."""
        recent_time = datetime.now(timezone.utc) - timedelta(hours=12)
        old_time = datetime.now(timezone.utc) - timedelta(days=3)

        backend.save_job(
            job_id="recent-completed", operation_type="add_golden_repo", status="completed",
            created_at=recent_time.isoformat(), completed_at=recent_time.isoformat(),
            username="user1", progress=100,
        )
        backend.save_job(
            job_id="old-failed", operation_type="refresh_repo", status="failed",
            created_at=old_time.isoformat(), completed_at=old_time.isoformat(),
            error="Something went wrong", username="user1", progress=25,
        )

        stats_24h = backend.get_job_stats(time_filter="24h")
        stats_7d = backend.get_job_stats(time_filter="7d")

        assert stats_24h["completed"] == 1
        assert stats_24h["failed"] == 0
        assert stats_7d["completed"] == 1
        assert stats_7d["failed"] == 1


class TestBackgroundJobsSqliteBackendScipFields:
    """Tests for BackgroundJobsSqliteBackend SCIP self-healing fields."""

    def test_update_scip_resolution_status(self, backend) -> None:
        """When update_job() is called with language_resolution_status, it is updated correctly."""
        backend.save_job(
            job_id="scip-job", operation_type="scip_generate", status="running",
            created_at="2025-01-15T10:00:00+00:00", username="admin", progress=25,
            language_resolution_status={"python": {"status": "pending"}},
        )

        backend.update_job(
            job_id="scip-job",
            status="resolving_prerequisites",
            resolution_attempts=1,
            claude_actions=["Installed python dependencies"],
            language_resolution_status={
                "python": {"status": "in_progress", "attempt": 1},
                "java": {"status": "pending"},
            },
        )

        job = backend.get_job("scip-job")
        assert job is not None
        assert job["status"] == "resolving_prerequisites"
        assert job["resolution_attempts"] == 1
        assert job["claude_actions"] == ["Installed python dependencies"]
        assert job["language_resolution_status"]["python"]["status"] == "in_progress"

    def test_save_job_with_extended_error(self, backend) -> None:
        """When save_job() is called with extended_error, the error context is stored as JSON."""
        extended_error = {
            "error_code": "SCIP_INDEXER_FAILED",
            "project": "backend/api",
            "language": "java",
            "suggested_action": "Run mvn dependency:resolve",
        }

        backend.save_job(
            job_id="failed-scip", operation_type="scip_generate", status="failed",
            created_at="2025-01-15T10:00:00+00:00", completed_at="2025-01-15T10:05:00+00:00",
            error="SCIP indexer failed for java project", username="admin", progress=50,
            extended_error=extended_error, failure_reason="Maven dependencies missing",
        )

        job = backend.get_job("failed-scip")
        assert job is not None
        assert job["error"] == "SCIP indexer failed for java project"
        assert job["extended_error"] == extended_error
        assert job["failure_reason"] == "Maven dependencies missing"
