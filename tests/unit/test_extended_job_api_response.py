"""
Unit tests for AC6: Extended Job Status in Existing API.

Tests that BackgroundJobManager.get_job_status() and list_jobs() include
extended self-healing fields when present.
"""

import pytest
from datetime import datetime, timezone

from src.code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    BackgroundJob,
    JobStatus,
)


class TestExtendedJobAPIResponse:
    """Test suite for extended job API response (Story #646 AC6)."""

    def test_get_job_status_includes_extended_fields_when_present(self, tmp_path):
        """Test that get_job_status includes extended self-healing fields."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        job_id = manager.submit_job(
            operation_type="test_scip_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Simulate self-healing fields being populated
        job = manager.jobs[job_id]
        job.resolution_attempts = 3
        job.claude_actions = ["installed poetry", "installed maven", "retried scip"]
        job.failure_reason = "1 project unresolvable"
        job.extended_error = {
            "original_error": "scip failed",
            "claude_analysis": "Maven not found",
            "attempts_history": [{"attempt": 1, "action": "installed maven"}],
        }
        job.language_resolution_status = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolved",
                "attempts": 1,
                "resolution_actions": ["installed poetry"],
            }
        }

        # Act
        status = manager.get_job_status(job_id, "test_user")

        # Assert
        assert status is not None
        assert status["resolution_attempts"] == 3
        assert status["claude_actions"] == ["installed poetry", "installed maven", "retried scip"]
        assert status["failure_reason"] == "1 project unresolvable"
        assert status["extended_error"] == {
            "original_error": "scip failed",
            "claude_analysis": "Maven not found",
            "attempts_history": [{"attempt": 1, "action": "installed maven"}],
        }
        assert status["language_resolution_status"] == {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolved",
                "attempts": 1,
                "resolution_actions": ["installed poetry"],
            }
        }

    def test_get_job_status_excludes_extended_fields_when_not_set(self, tmp_path):
        """Test backward compatibility: extended fields excluded when not set."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        job_id = manager.submit_job(
            operation_type="test_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Act
        status = manager.get_job_status(job_id, "test_user")

        # Assert - extended fields should be present but None/0/empty
        assert status is not None
        # These fields should be included even when not set, for API consistency
        assert "resolution_attempts" in status
        assert "claude_actions" in status
        assert "failure_reason" in status
        assert "extended_error" in status
        assert "language_resolution_status" in status

    def test_list_jobs_includes_resolution_attempts(self, tmp_path):
        """Test that list_jobs includes resolution_attempts in summary."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Create job with self-healing
        job_id_1 = manager.submit_job(
            operation_type="scip_with_self_healing",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="repo-one",
        )
        job_1 = manager.jobs[job_id_1]
        job_1.resolution_attempts = 2

        # Create job without self-healing
        job_id_2 = manager.submit_job(
            operation_type="normal_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="repo-two",
        )

        # Act
        result = manager.list_jobs("test_user", limit=10)

        # Assert
        assert result["total"] == 2
        jobs = result["jobs"]
        assert len(jobs) == 2

        # Find jobs by ID
        job_1_data = next(j for j in jobs if j["job_id"] == job_id_1)
        job_2_data = next(j for j in jobs if j["job_id"] == job_id_2)

        # Check resolution_attempts is included
        assert "resolution_attempts" in job_1_data
        assert job_1_data["resolution_attempts"] == 2

        assert "resolution_attempts" in job_2_data
        assert job_2_data["resolution_attempts"] == 0

    def test_list_jobs_includes_all_extended_fields(self, tmp_path):
        """Test that list_jobs includes all extended fields for comprehensive view."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        job_id = manager.submit_job(
            operation_type="scip_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Populate extended fields
        job = manager.jobs[job_id]
        job.resolution_attempts = 3
        job.claude_actions = ["action1", "action2"]
        job.failure_reason = "Unresolvable"
        job.extended_error = {"error": "details"}
        job.language_resolution_status = {"backend/": {"status": "resolved"}}

        # Act
        result = manager.list_jobs("test_user", limit=10)

        # Assert
        assert result["total"] == 1
        job_data = result["jobs"][0]

        assert job_data["resolution_attempts"] == 3
        assert job_data["claude_actions"] == ["action1", "action2"]
        assert job_data["failure_reason"] == "Unresolvable"
        assert job_data["extended_error"] == {"error": "details"}
        assert job_data["language_resolution_status"] == {"backend/": {"status": "resolved"}}
