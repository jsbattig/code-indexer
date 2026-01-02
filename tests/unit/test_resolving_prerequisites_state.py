"""
Unit tests for RESOLVING_PREREQUISITES job state.

Tests AC2: New Job State - RESOLVING_PREREQUISITES

Following TDD methodology - these tests define the expected behavior
before implementation.
"""

import pytest
from datetime import datetime, timezone

from code_indexer.server.repositories.background_jobs import (
    BackgroundJob,
    JobStatus,
)


class TestResolvingPrerequisitesState:
    """Test RESOLVING_PREREQUISITES job state and transitions."""

    def test_job_status_enum_has_resolving_prerequisites(self):
        """Test that JobStatus enum includes RESOLVING_PREREQUISITES."""
        # This should not raise AttributeError
        assert hasattr(JobStatus, "RESOLVING_PREREQUISITES")
        assert JobStatus.RESOLVING_PREREQUISITES.value == "resolving_prerequisites"

    def test_background_job_can_be_created_with_resolving_prerequisites_status(self):
        """Test that BackgroundJob can be created with RESOLVING_PREREQUISITES status."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
        )

        assert job.status == JobStatus.RESOLVING_PREREQUISITES
        assert job.status.value == "resolving_prerequisites"

    def test_transition_from_running_to_resolving_prerequisites(self):
        """Test valid state transition: RUNNING → RESOLVING_PREREQUISITES."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=25,
            username="testuser",
            repo_alias="backend-golden",
        )

        # Simulate SCIP failure detected during RUNNING
        job.status = JobStatus.RESOLVING_PREREQUISITES

        assert job.status == JobStatus.RESOLVING_PREREQUISITES

    def test_transition_from_resolving_prerequisites_to_running(self):
        """Test valid state transition: RESOLVING_PREREQUISITES → RUNNING (retry)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=1,
        )

        # Simulate retrying SCIP after resolution
        job.status = JobStatus.RUNNING

        assert job.status == JobStatus.RUNNING

    def test_transition_from_resolving_prerequisites_to_failed(self):
        """Test valid state transition: RESOLVING_PREREQUISITES → FAILED (unresolvable)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=3,
            failure_reason="Unresolvable: Missing system dependencies",
        )

        # Simulate max attempts reached or unresolvable issue
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)

        assert job.status == JobStatus.FAILED
        assert job.completed_at is not None

    def test_transition_from_resolving_prerequisites_to_completed(self):
        """Test valid state transition: RESOLVING_PREREQUISITES → COMPLETED (retry succeeds)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=1,
        )

        # Simulate SCIP retry succeeding immediately
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.progress = 100

        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None
        assert job.progress == 100

    def test_resolving_prerequisites_state_serialization(self):
        """Test that RESOLVING_PREREQUISITES state serializes correctly to JSON."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
        )

        from dataclasses import asdict

        job_dict = asdict(job)

        # Status should serialize to string value
        assert job_dict["status"] == JobStatus.RESOLVING_PREREQUISITES
        # When converting to JSON-compatible format
        assert job_dict["status"].value == "resolving_prerequisites"

    def test_resolving_prerequisites_with_language_resolution_status(self):
        """Test that RESOLVING_PREREQUISITES state works with language_resolution_status."""
        lang_resolution = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolving",
                "attempts": 1,
                "last_error": "poetry: command not found",
                "resolution_actions": ["sudo apt-get install poetry"],
                "workspace_path": "/tmp/cidx-scip-abc123/backend/",
            }
        }

        job = BackgroundJob(
            job_id="test-123",
            operation_type="add_golden_repo_index",
            status=JobStatus.RESOLVING_PREREQUISITES,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=1,
            language_resolution_status=lang_resolution,
        )

        assert job.status == JobStatus.RESOLVING_PREREQUISITES
        assert job.language_resolution_status["backend/"]["status"] == "resolving"

    def test_all_job_statuses_present(self):
        """Test that all expected job statuses are present in JobStatus enum."""
        expected_statuses = {
            "PENDING",
            "RUNNING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "RESOLVING_PREREQUISITES",
        }

        actual_statuses = {status.name for status in JobStatus}

        assert expected_statuses == actual_statuses

    def test_resolving_prerequisites_status_value(self):
        """Test that RESOLVING_PREREQUISITES has correct string value."""
        status = JobStatus.RESOLVING_PREREQUISITES
        assert status.value == "resolving_prerequisites"
        # Note: str(status) returns repr (e.g., "JobStatus.RESOLVING_PREREQUISITES"), not value
        # Use status.value for string representation
