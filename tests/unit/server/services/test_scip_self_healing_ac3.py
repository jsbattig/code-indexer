"""
Unit tests for SCIP Self-Healing Service AC3: Response Protocol Handling.

Tests handle_project_response() method for all three status types:
- progress: Trigger SCIP retry for that project, handle success/failure
- no_progress: Increment attempts, resume or mark unresolvable based on max (3)
- unresolvable: Mark project unresolvable immediately

Story #645 AC3.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from code_indexer.server.services.scip_self_healing import (
    SCIPSelfHealingService,
    ClaudeResponse,
)
from code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestSCIPSelfHealingServiceAC3:
    """Test AC3: Structured Response Protocol Handling - Per-Project."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create a BackgroundJobManager for testing."""
        storage_path = tmp_path / "jobs.json"
        return BackgroundJobManager(storage_path=str(storage_path))

    @pytest.fixture
    def service(self, job_manager, tmp_path):
        """Create SCIPSelfHealingService instance."""
        return SCIPSelfHealingService(
            job_manager=job_manager,
            repo_root=Path(tmp_path / "test-repo"),
            resolution_queue=AsyncMock(),
        )

    @pytest.fixture
    def job_with_failed_project(self, job_manager):
        """Create a job with one failed project in language_resolution_status."""
        job_id = job_manager.submit_job(
            operation_type="scip_indexing",
            func=lambda: {"success": True},
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Set up language_resolution_status with one failed Python project
        with job_manager._lock:
            job = job_manager.jobs[job_id]
            job.language_resolution_status = {
                "backend/": {
                    "project_path": "backend/",
                    "language": "python",
                    "build_system": "poetry",
                    "status": "resolving",
                    "attempts": 1,
                    "last_error": "poetry not found in PATH",
                    "resolution_actions": [],
                    "workspace_path": "/tmp/cidx-scip-test/backend/",
                }
            }
            job_manager._persist_jobs()

        return job_id

    @pytest.mark.asyncio
    async def test_handle_progress_response_marks_project_resolved_on_scip_success(
        self, service, job_manager, job_with_failed_project
    ):
        """Test 'progress' response: If SCIP retry succeeds, mark project resolved."""
        job_id = job_with_failed_project

        # Create progress response
        response = ClaudeResponse(
            status="progress",
            actions_taken=["sudo apt-get install poetry"],
            reasoning="Installed poetry package manager",
        )

        # Mock SCIP retry to succeed
        with patch.object(
            service, "_retry_scip_for_project", new_callable=AsyncMock
        ) as mock_retry:
            mock_retry.return_value = True  # SCIP succeeds

            # Act
            await service.handle_project_response(
                job_id=job_id,
                project_path="backend/",
                response=response,
            )

        # Assert: Project marked as resolved
        job = job_manager.jobs[job_id]
        assert job.language_resolution_status["backend/"]["status"] == "resolved"
        assert (
            "sudo apt-get install poetry"
            in job.language_resolution_status["backend/"]["resolution_actions"]
        )
        assert (
            job.language_resolution_status["backend/"]["reasoning"]
            == "Installed poetry package manager"
        )

    @pytest.mark.asyncio
    async def test_handle_progress_response_requeues_project_on_scip_failure(
        self, service, job_manager, job_with_failed_project
    ):
        """Test 'progress' response: If SCIP retry fails, re-queue project."""
        job_id = job_with_failed_project

        response = ClaudeResponse(
            status="progress",
            actions_taken=["pip install some-package"],
            reasoning="Attempted dependency installation",
        )

        # Mock SCIP retry to fail
        with patch.object(
            service, "_retry_scip_for_project", new_callable=AsyncMock
        ) as mock_retry:
            with patch.object(
                service, "_enqueue_project_for_retry", new_callable=AsyncMock
            ) as mock_enqueue:
                mock_retry.return_value = False  # SCIP fails

                # Act
                await service.handle_project_response(
                    job_id=job_id,
                    project_path="backend/",
                    response=response,
                )

                # Assert: Project re-queued
                mock_enqueue.assert_called_once_with(job_id, "backend/")

        # Assert: Status remains 'resolving', attempts incremented
        job = job_manager.jobs[job_id]
        assert job.language_resolution_status["backend/"]["status"] == "resolving"
        assert (
            job.language_resolution_status["backend/"]["attempts"] == 2
        )  # Incremented from 1 to 2

    @pytest.mark.asyncio
    async def test_handle_no_progress_response_resumes_when_attempts_below_max(
        self, service, job_manager, job_with_failed_project
    ):
        """Test 'no_progress' response: If attempts < 3, prepare for resume."""
        job_id = job_with_failed_project

        response = ClaudeResponse(
            status="no_progress",
            actions_taken=["Checked dependencies"],
            reasoning="Unable to determine missing packages",
        )

        # Act
        await service.handle_project_response(
            job_id=job_id,
            project_path="backend/",
            response=response,
        )

        # Assert: Attempts incremented, status remains 'resolving'
        job = job_manager.jobs[job_id]
        assert (
            job.language_resolution_status["backend/"]["attempts"] == 2
        )  # Incremented from 1
        assert job.language_resolution_status["backend/"]["status"] == "resolving"

    @pytest.mark.asyncio
    async def test_handle_no_progress_response_marks_unresolvable_when_max_attempts_reached(
        self, service, job_manager, job_with_failed_project
    ):
        """Test 'no_progress' response: If attempts >= 3, mark project unresolvable."""
        job_id = job_with_failed_project

        # Set attempts to 3 (max)
        with job_manager._lock:
            job = job_manager.jobs[job_id]
            job.language_resolution_status["backend/"]["attempts"] = 3
            job_manager._persist_jobs()

        response = ClaudeResponse(
            status="no_progress",
            actions_taken=["Final attempt failed"],
            reasoning="Exhausted all resolution strategies",
        )

        # Act
        await service.handle_project_response(
            job_id=job_id,
            project_path="backend/",
            response=response,
        )

        # Assert: Project marked unresolvable
        job = job_manager.jobs[job_id]
        assert job.language_resolution_status["backend/"]["status"] == "unresolvable"
        assert job.language_resolution_status["backend/"]["attempts"] == 3

    @pytest.mark.asyncio
    async def test_handle_unresolvable_response_marks_project_unresolvable_immediately(
        self, service, job_manager, job_with_failed_project
    ):
        """Test 'unresolvable' response: Mark project unresolvable immediately."""
        job_id = job_with_failed_project

        response = ClaudeResponse(
            status="unresolvable",
            actions_taken=[],
            reasoning="Missing critical system dependencies that cannot be installed",
        )

        # Act
        await service.handle_project_response(
            job_id=job_id,
            project_path="backend/",
            response=response,
        )

        # Assert: Project marked unresolvable immediately
        job = job_manager.jobs[job_id]
        assert job.language_resolution_status["backend/"]["status"] == "unresolvable"
        assert (
            job.language_resolution_status["backend/"]["reasoning"]
            == "Missing critical system dependencies that cannot be installed"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
