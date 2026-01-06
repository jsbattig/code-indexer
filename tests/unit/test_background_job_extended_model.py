"""
Unit tests for extended BackgroundJob model with per-language resolution tracking.

Tests AC1: Extended BackgroundJob Model with Per-Language Tracking (REVISED)

Following TDD methodology - these tests define the expected behavior
before implementation.
"""

import json
from datetime import datetime, timezone
from dataclasses import asdict

from code_indexer.server.repositories.background_jobs import (
    BackgroundJob,
    JobStatus,
)


class TestExtendedBackgroundJobModel:
    """Test extended BackgroundJob model with new SCIP self-healing fields."""

    def test_background_job_has_repo_alias_field(self):
        """Test that BackgroundJob has repo_alias field (nullable for backward compatibility)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            repo_alias="backend-golden",  # NEW FIELD
        )

        assert hasattr(job, "repo_alias")
        assert job.repo_alias == "backend-golden"

    def test_background_job_repo_alias_can_be_none(self):
        """Test that repo_alias can be None for backward compatibility."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            repo_alias=None,  # Should be nullable
        )

        assert job.repo_alias is None

    def test_background_job_has_resolution_attempts_field(self):
        """Test that BackgroundJob has resolution_attempts field (default 0)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            resolution_attempts=3,  # NEW FIELD
        )

        assert hasattr(job, "resolution_attempts")
        assert job.resolution_attempts == 3

    def test_background_job_resolution_attempts_defaults_to_zero(self):
        """Test that resolution_attempts defaults to 0."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
        )

        assert job.resolution_attempts == 0

    def test_background_job_has_claude_actions_field(self):
        """Test that BackgroundJob has claude_actions field (list)."""
        actions = [
            "sudo apt-get install poetry",
            "poetry install",
        ]
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            claude_actions=actions,  # NEW FIELD
        )

        assert hasattr(job, "claude_actions")
        assert job.claude_actions == actions

    def test_background_job_claude_actions_can_be_none(self):
        """Test that claude_actions can be None."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            claude_actions=None,
        )

        assert job.claude_actions is None

    def test_background_job_has_failure_reason_field(self):
        """Test that BackgroundJob has failure_reason field (nullable)."""
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.FAILED,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            failure_reason="Missing build tool: poetry not installed",  # NEW FIELD
        )

        assert hasattr(job, "failure_reason")
        assert job.failure_reason == "Missing build tool: poetry not installed"

    def test_background_job_has_extended_error_field(self):
        """Test that BackgroundJob has extended_error field (JSON blob)."""
        extended_error = {
            "original_error": "poetry: command not found",
            "claude_analysis": "Poetry not installed on system",
            "attempts_history": [
                {"attempt": 1, "action": "sudo apt-get install poetry"}
            ],
            "blocking_issue": "System package manager lacks poetry",
            "admin_guidance": "Install poetry manually",
            "workspace_path": "/tmp/cidx-scip-abc123",
        }
        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.FAILED,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            extended_error=extended_error,  # NEW FIELD
        )

        assert hasattr(job, "extended_error")
        assert job.extended_error == extended_error
        assert job.extended_error["original_error"] == "poetry: command not found"
        assert job.extended_error["claude_analysis"] == "Poetry not installed on system"

    def test_background_job_has_language_resolution_status_field(self):
        """Test that BackgroundJob has language_resolution_status field (per-project tracking)."""
        lang_resolution = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolved",
                "attempts": 1,
                "last_error": "poetry: command not found",
                "resolution_actions": ["sudo apt-get install poetry", "poetry install"],
                "workspace_path": "/tmp/cidx-scip-abc123/backend/",
            },
            "services/api/": {
                "project_path": "services/api/",
                "language": "java",
                "build_system": "maven",
                "status": "unresolvable",
                "attempts": 3,
                "last_error": "maven: BUILD FAILED",
                "resolution_actions": [
                    "sudo apt-get install maven",
                    "mvn clean install",
                ],
                "workspace_path": "/tmp/cidx-scip-abc123/services/api/",
            },
        }

        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.FAILED,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            language_resolution_status=lang_resolution,  # NEW FIELD
        )

        assert hasattr(job, "language_resolution_status")
        assert job.language_resolution_status == lang_resolution
        assert "backend/" in job.language_resolution_status
        assert job.language_resolution_status["backend/"]["status"] == "resolved"
        assert (
            job.language_resolution_status["services/api/"]["status"] == "unresolvable"
        )

    def test_language_resolution_status_structure_validation(self):
        """Test that language_resolution_status follows expected structure."""
        lang_resolution = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "pending",
                "attempts": 0,
                "last_error": "",
                "resolution_actions": [],
                "workspace_path": "/tmp/cidx-scip-abc123/backend/",
            }
        }

        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username="testuser",
            language_resolution_status=lang_resolution,
        )

        # Validate structure
        project_status = job.language_resolution_status["backend/"]
        assert "project_path" in project_status
        assert "language" in project_status
        assert "build_system" in project_status
        assert "status" in project_status
        assert "attempts" in project_status
        assert "last_error" in project_status
        assert "resolution_actions" in project_status
        assert "workspace_path" in project_status

    def test_language_resolution_status_supports_multiple_statuses(self):
        """Test that language_resolution_status supports all expected status values."""
        valid_statuses = ["pending", "resolving", "resolved", "unresolvable"]

        for status_value in valid_statuses:
            lang_resolution = {
                "backend/": {
                    "project_path": "backend/",
                    "language": "python",
                    "build_system": "poetry",
                    "status": status_value,
                    "attempts": 0,
                    "last_error": "",
                    "resolution_actions": [],
                    "workspace_path": "/tmp/cidx-scip-abc123/backend/",
                }
            }

            job = BackgroundJob(
                job_id=f"test-{status_value}",
                operation_type="test_operation",
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                started_at=None,
                completed_at=None,
                result=None,
                error=None,
                progress=0,
                username="testuser",
                language_resolution_status=lang_resolution,
            )

            assert job.language_resolution_status["backend/"]["status"] == status_value

    def test_backward_compatibility_with_existing_jobs(self):
        """Test that BackgroundJob without new fields still works (backward compatibility)."""
        # Create job without new fields (simulates existing jobs)
        job = BackgroundJob(
            job_id="legacy-job",
            operation_type="legacy_operation",
            status=JobStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result={"status": "ok"},
            error=None,
            progress=100,
            username="legacyuser",
        )

        # Should not raise errors
        assert job.job_id == "legacy-job"
        assert job.resolution_attempts == 0  # Should default to 0
        assert job.repo_alias is None  # Should be None if not provided
        assert job.claude_actions is None
        assert job.failure_reason is None
        assert job.extended_error is None
        assert job.language_resolution_status is None

    def test_job_serialization_with_new_fields(self):
        """Test that BackgroundJob with new fields can be serialized to dict."""
        lang_resolution = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolved",
                "attempts": 1,
                "last_error": "",
                "resolution_actions": ["poetry install"],
                "workspace_path": "/tmp/cidx-scip-abc123/backend/",
            }
        }

        job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=1,
            claude_actions=["poetry install"],
            failure_reason=None,
            extended_error=None,
            language_resolution_status=lang_resolution,
        )

        # Convert to dict (simulates JSON persistence)
        job_dict = asdict(job)

        assert job_dict["repo_alias"] == "backend-golden"
        assert job_dict["resolution_attempts"] == 1
        assert job_dict["claude_actions"] == ["poetry install"]
        assert (
            job_dict["language_resolution_status"]["backend/"]["status"] == "resolved"
        )

    def test_job_json_serialization_roundtrip(self):
        """Test that BackgroundJob can be serialized to JSON and back."""
        lang_resolution = {
            "backend/": {
                "project_path": "backend/",
                "language": "python",
                "build_system": "poetry",
                "status": "resolved",
                "attempts": 1,
                "last_error": "",
                "resolution_actions": ["poetry install"],
                "workspace_path": "/tmp/cidx-scip-abc123/backend/",
            }
        }

        extended_error = {
            "original_error": "test error",
            "claude_analysis": "test analysis",
            "attempts_history": [],
            "blocking_issue": None,
            "admin_guidance": "test guidance",
            "workspace_path": "/tmp/test",
        }

        original_job = BackgroundJob(
            job_id="test-123",
            operation_type="test_operation",
            status=JobStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            result=None,
            error=None,
            progress=50,
            username="testuser",
            repo_alias="backend-golden",
            resolution_attempts=1,
            claude_actions=["poetry install"],
            failure_reason="test failure",
            extended_error=extended_error,
            language_resolution_status=lang_resolution,
        )

        # Serialize to dict for JSON
        job_dict = asdict(original_job)

        # Convert datetime to string for JSON serialization
        job_dict["created_at"] = job_dict["created_at"].isoformat()
        job_dict["started_at"] = job_dict["started_at"].isoformat()
        job_dict["status"] = job_dict["status"].value

        # Serialize to JSON
        json_str = json.dumps(job_dict)

        # Deserialize from JSON
        restored_dict = json.loads(json_str)

        # Verify all new fields preserved
        assert restored_dict["repo_alias"] == "backend-golden"
        assert restored_dict["resolution_attempts"] == 1
        assert restored_dict["claude_actions"] == ["poetry install"]
        assert restored_dict["failure_reason"] == "test failure"
        assert restored_dict["extended_error"]["original_error"] == "test error"
        assert (
            restored_dict["language_resolution_status"]["backend/"]["status"]
            == "resolved"
        )
