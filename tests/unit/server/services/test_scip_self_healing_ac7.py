"""
Unit tests for SCIP Self-Healing Service AC7: Job Completion Logic.

Tests determine_job_completion() method for calculating final job status
based on per-project resolution results (resolved/unresolvable).

Story #645 AC7.
"""

import pytest
from code_indexer.server.services.scip_self_healing import SCIPSelfHealingService
from code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    JobStatus,
)


class TestSCIPSelfHealingServiceAC7:
    """Test AC7: Job Completion Logic with Partial Resolution Support."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create a BackgroundJobManager for testing."""
        storage_path = tmp_path / "jobs.json"
        return BackgroundJobManager(storage_path=str(storage_path))

    @pytest.fixture
    def service(self, job_manager, tmp_path):
        """Create SCIPSelfHealingService instance."""
        return SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

    @pytest.mark.asyncio
    async def test_all_resolved_returns_completed(self, service, job_manager):
        """Test AC7: All projects resolved → job COMPLETED."""
        # Create job with 3 projects
        job_id = job_manager.submit_job(
            operation_type="scip_indexing",
            func=lambda: {"success": True},
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Set all projects as resolved
        with job_manager._lock:
            job = job_manager.jobs[job_id]
            job.language_resolution_status = {
                "backend/": {"status": "resolved", "language": "python"},
                "frontend/": {"status": "resolved", "language": "typescript"},
                "services/": {"status": "resolved", "language": "java"},
            }
            job_manager._persist_jobs()

        # Act
        final_status = await service.determine_job_completion(job_id)

        # Assert
        assert final_status == JobStatus.COMPLETED
        job = job_manager.jobs[job_id]
        assert job.failure_reason is None or job.failure_reason == ""

    @pytest.mark.asyncio
    async def test_partial_success_returns_completed_with_reason(
        self, service, job_manager
    ):
        """Test AC7: Some resolved + some unresolvable → COMPLETED with partial success reason."""
        # Create job
        job_id = job_manager.submit_job(
            operation_type="scip_indexing",
            func=lambda: {"success": True},
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # 2 resolved, 1 unresolvable
        with job_manager._lock:
            job = job_manager.jobs[job_id]
            job.language_resolution_status = {
                "backend/": {"status": "resolved", "language": "python"},
                "frontend/": {"status": "resolved", "language": "typescript"},
                "native/": {"status": "unresolvable", "language": "cpp"},
            }
            job_manager._persist_jobs()

        # Act
        final_status = await service.determine_job_completion(job_id)

        # Assert
        assert final_status == JobStatus.COMPLETED
        job = job_manager.jobs[job_id]
        assert "2/3 projects resolved" in job.failure_reason
        assert "1 unresolvable" in job.failure_reason
        assert job.extended_error is not None
        assert "backend/" in job.extended_error["resolved_projects"]
        assert "frontend/" in job.extended_error["resolved_projects"]
        assert "native/" in job.extended_error["unresolvable_projects"]

    @pytest.mark.asyncio
    async def test_none_resolved_returns_failed(self, service, job_manager):
        """Test AC7: No projects resolved → job FAILED."""
        # Create job
        job_id = job_manager.submit_job(
            operation_type="scip_indexing",
            func=lambda: {"success": True},
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # All unresolvable
        with job_manager._lock:
            job = job_manager.jobs[job_id]
            job.language_resolution_status = {
                "backend/": {"status": "unresolvable", "language": "python"},
                "frontend/": {"status": "unresolvable", "language": "typescript"},
                "native/": {"status": "unresolvable", "language": "cpp"},
            }
            job_manager._persist_jobs()

        # Act
        final_status = await service.determine_job_completion(job_id)

        # Assert
        assert final_status == JobStatus.FAILED
        job = job_manager.jobs[job_id]
        assert "No projects could be resolved" in job.failure_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
