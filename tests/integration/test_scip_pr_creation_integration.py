"""
Integration tests for SCIP Self-Healing → PR Creation flow (Story #659, Priority 4).

Validates that GitStateManager.create_pr_after_fix is automatically called
when SCIP self-healing successfully resolves dependency issues.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

from src.code_indexer.server.services.scip_self_healing import (
    SCIPSelfHealingService,
    ClaudeResponse,
)
from src.code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    JobStatus,
)
from src.code_indexer.scip.generator import GenerationResult, ProjectGenerationResult
from src.code_indexer.scip.discovery import DiscoveredProject
from src.code_indexer.scip.indexers.base import IndexerResult, IndexerStatus


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory for integration tests."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def job_manager(temp_workspace):
    """Create real BackgroundJobManager for integration tests."""
    storage_path = temp_workspace / "jobs.json"
    return BackgroundJobManager(storage_path=str(storage_path))


@pytest.fixture
def self_healing_service(job_manager, temp_workspace):
    """Create real SCIPSelfHealingService for integration tests."""
    return SCIPSelfHealingService(job_manager=job_manager, repo_root=temp_workspace)


# =============================================================================
# Helper Functions
# =============================================================================


def create_failed_project(
    path: str, language: str, build_system: str, stderr: str
) -> ProjectGenerationResult:
    """Create a failed SCIP project result."""
    project = DiscoveredProject(
        relative_path=Path(path),
        language=language,
        build_system=build_system,
        build_file=Path(path) / f"build.{build_system}",
    )
    indexer_result = IndexerResult(
        status=IndexerStatus.FAILED,
        stderr=stderr,
        duration_seconds=0.1,
        output_file=None,
        stdout="",
        exit_code=1,
    )
    return ProjectGenerationResult(project, indexer_result)


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_pr_creation_triggered_on_full_success(
    self_healing_service, job_manager, temp_workspace
):
    """
    Test that PR creation is triggered when ALL projects are resolved successfully.

    Flow:
    1. SCIP fails for Python project
    2. Self-healing resolves it (status: resolved)
    3. determine_job_completion returns COMPLETED
    4. PR creation is triggered with correct parameters
    """
    # Arrange: Create job (func is placeholder, actual failure simulated via handle_scip_failure)
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="test-repo",
    )

    # Simulate SCIP failure detection
    generation_result = GenerationResult(
        total_projects=1,
        successful_projects=0,
        failed_projects=1,
        project_results=[
            create_failed_project(
                "backend/",
                "python",
                "poetry",
                "ModuleNotFoundError: No module named 'requests'",
            )
        ],
    )

    await self_healing_service.handle_scip_failure(
        job_id, generation_result, "test-repo"
    )

    # Verify job transitioned to RESOLVING_PREREQUISITES
    job = job_manager.jobs[job_id]
    assert job.status == JobStatus.RESOLVING_PREREQUISITES
    assert "backend/" in job.language_resolution_status

    # Simulate successful Claude Code response
    response = ClaudeResponse(
        status="progress",
        actions_taken=["poetry add requests"],
        reasoning="Installed missing dependency: requests",
    )

    # Mock SCIP retry success
    with patch.object(
        self_healing_service, "_retry_scip_for_project", return_value=True
    ):
        await self_healing_service.handle_project_response(job_id, "backend/", response)

    # Verify project marked as resolved
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "resolved"

    # Act: Determine job completion (this should trigger PR creation)
    with patch(
        "src.code_indexer.server.services.scip_self_healing.GitStateManager"
    ) as MockGitStateManager:
        mock_git_manager = MockGitStateManager.return_value
        mock_create_pr = mock_git_manager.create_pr_after_fix

        final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert: Job completed successfully
    assert final_status == JobStatus.COMPLETED

    # Assert: PR creation was triggered with correct parameters
    mock_create_pr.assert_called_once()
    call_kwargs = mock_create_pr.call_args.kwargs
    assert call_kwargs["job_id"] == job_id
    assert "fix(scip)" in call_kwargs["pr_description"]


@pytest.mark.asyncio
async def test_pr_creation_triggered_on_partial_success(
    self_healing_service, job_manager, temp_workspace
):
    """
    Test that PR creation is triggered even with partial success (some unresolvable projects).

    Flow:
    1. SCIP fails for 2 projects (Python + TypeScript)
    2. Python resolved successfully
    3. TypeScript marked unresolvable
    4. determine_job_completion returns COMPLETED (partial success)
    5. PR creation triggered for partial resolution
    """
    # Arrange: Create job (func is placeholder, actual failure simulated via handle_scip_failure)
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="test-repo",
    )

    generation_result = GenerationResult(
        total_projects=2,
        successful_projects=0,
        failed_projects=2,
        project_results=[
            create_failed_project(
                "backend/", "python", "poetry", "ModuleNotFoundError: requests"
            ),
            create_failed_project(
                "frontend/", "typescript", "npm", "Cannot find module 'react'"
            ),
        ],
    )

    await self_healing_service.handle_scip_failure(
        job_id, generation_result, "test-repo"
    )

    # Simulate Python resolved
    with patch.object(
        self_healing_service, "_retry_scip_for_project", return_value=True
    ):
        await self_healing_service.handle_project_response(
            job_id,
            "backend/",
            ClaudeResponse("progress", ["poetry add requests"], "Fixed"),
        )

    # Simulate TypeScript unresolvable
    await self_healing_service.handle_project_response(
        job_id,
        "frontend/",
        ClaudeResponse("unresolvable", [], "Missing node/npm tools"),
    )

    # Verify states
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "resolved"
    assert job.language_resolution_status["frontend/"]["status"] == "unresolvable"

    # Act: Determine job completion
    with patch(
        "src.code_indexer.server.services.scip_self_healing.GitStateManager"
    ) as MockGitStateManager:
        mock_git_manager = MockGitStateManager.return_value
        mock_create_pr = mock_git_manager.create_pr_after_fix

        final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert: Job completed with partial success
    assert final_status == JobStatus.COMPLETED
    assert "1/2 projects resolved" in job.failure_reason

    # Assert: PR creation triggered even with partial success
    mock_create_pr.assert_called_once()
    call_kwargs = mock_create_pr.call_args.kwargs
    assert call_kwargs["job_id"] == job_id
    assert call_kwargs["platform"] == "github"
    assert "repo_path" in call_kwargs


@pytest.mark.asyncio
async def test_pr_creation_not_triggered_on_total_failure(
    self_healing_service, job_manager, temp_workspace
):
    """
    Test that PR creation is NOT triggered when ALL projects are unresolvable.

    Flow:
    1. SCIP fails for Python project
    2. Claude Code marks it unresolvable
    3. determine_job_completion returns FAILED
    4. PR creation NOT triggered (no progress made)
    """
    # Arrange: Create job (func is placeholder, actual failure simulated via handle_scip_failure)
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="test-repo",
    )

    generation_result = GenerationResult(
        total_projects=1,
        successful_projects=0,
        failed_projects=1,
        project_results=[
            create_failed_project(
                "backend/", "python", "poetry", "Incompatible Python version"
            )
        ],
    )

    await self_healing_service.handle_scip_failure(
        job_id, generation_result, "test-repo"
    )

    # Simulate unresolvable response
    await self_healing_service.handle_project_response(
        job_id,
        "backend/",
        ClaudeResponse("unresolvable", [], "Python 2.7 not supported"),
    )

    # Verify project marked as unresolvable
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "unresolvable"

    # Act: Determine job completion
    with patch(
        "src.code_indexer.server.services.scip_self_healing.GitStateManager"
    ) as MockGitStateManager:
        mock_git_manager = MockGitStateManager.return_value
        mock_create_pr = mock_git_manager.create_pr_after_fix

        final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert: Job failed
    assert final_status == JobStatus.FAILED
    assert "No projects could be resolved" in job.failure_reason

    # Assert: PR creation NOT triggered (total failure, no progress)
    mock_create_pr.assert_not_called()


@pytest.mark.asyncio
async def test_pr_creation_error_does_not_block_completion(
    self_healing_service, job_manager, temp_workspace
):
    """
    Test that errors during PR creation do NOT prevent job completion.

    Flow:
    1. SCIP resolved successfully
    2. PR creation fails (network error, invalid credentials, etc.)
    3. Job still transitions to COMPLETED
    4. Error is logged but not propagated
    """
    # Arrange: Create job (func is placeholder, actual failure simulated via handle_scip_failure)
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="test-repo",
    )

    generation_result = GenerationResult(
        total_projects=1,
        successful_projects=0,
        failed_projects=1,
        project_results=[
            create_failed_project(
                "backend/", "python", "poetry", "ModuleNotFoundError: requests"
            )
        ],
    )

    await self_healing_service.handle_scip_failure(
        job_id, generation_result, "test-repo"
    )

    # Simulate successful resolution
    with patch.object(
        self_healing_service, "_retry_scip_for_project", return_value=True
    ):
        await self_healing_service.handle_project_response(
            job_id,
            "backend/",
            ClaudeResponse("progress", ["poetry add requests"], "Fixed"),
        )

    # Act: PR creation fails but job completes
    with patch(
        "src.code_indexer.server.services.scip_self_healing.GitStateManager"
    ) as MockGitStateManager:
        mock_git_manager = MockGitStateManager.return_value
        mock_git_manager.create_pr_after_fix.side_effect = Exception(
            "GitHub API rate limit exceeded"
        )

        final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert: Job still completed despite PR creation failure
    assert final_status == JobStatus.COMPLETED
