"""
End-to-End tests for SCIP Self-Healing Service (Story #645).

These tests validate the complete vertical slice from SCIP failure detection
through Claude Code integration to final job completion, covering the 4
required E2E scenarios from the story specification.

Tests use REAL service/queue instances and mock ONLY external dependencies
(Claude Code subprocess, SCIP retry operations).
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from tempfile import TemporaryDirectory

from src.code_indexer.server.services.scip_self_healing import (
    SCIPSelfHealingService,
)
from src.code_indexer.server.services.scip_resolution_queue import SCIPResolutionQueue
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
    """Create temporary workspace directory for E2E tests."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def job_manager(temp_workspace):
    """Create real BackgroundJobManager for E2E tests."""
    storage_path = temp_workspace / "jobs.json"
    return BackgroundJobManager(storage_path=str(storage_path))


@pytest.fixture
def self_healing_service(job_manager, temp_workspace):
    """Create real SCIPSelfHealingService for E2E tests."""
    return SCIPSelfHealingService(job_manager=job_manager, repo_root=temp_workspace)


@pytest.fixture
def resolution_queue(self_healing_service):
    """Create real SCIPResolutionQueue for E2E tests."""
    return SCIPResolutionQueue(self_healing_service)


# =============================================================================
# Helper Functions - GenerationResult Construction
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


def create_successful_project(
    path: str, language: str, build_system: str
) -> ProjectGenerationResult:
    """Create a successful SCIP project result."""
    project = DiscoveredProject(
        relative_path=Path(path),
        language=language,
        build_system=build_system,
        build_file=Path(path) / f"build.{build_system}",
    )
    indexer_result = IndexerResult(
        status=IndexerStatus.SUCCESS,
        duration_seconds=5.0,
        output_file=Path(path) / "index.scip.db",
        stdout="Indexing completed successfully",
        stderr="",
        exit_code=0,
    )
    return ProjectGenerationResult(project, indexer_result)


# =============================================================================
# Helper Functions - Claude Code Mocking
# =============================================================================


def mock_claude_subprocess(
    response_status: str,
    actions: list,
    reasoning: str,
):
    """Mock Claude Code subprocess invocation with specified response."""
    process_mock = AsyncMock()
    process_mock.communicate.return_value = (
        json.dumps(
            {
                "status": response_status,
                "actions_taken": actions,
                "reasoning": reasoning,
            }
        ).encode(),
        b"",
    )
    process_mock.returncode = 0
    return process_mock


def mock_scip_retry_success():
    """Mock successful SCIP retry after dependency installation."""
    return True


def mock_scip_retry_failure():
    """Mock failed SCIP retry."""
    return False


# =============================================================================
# Helper Functions - Reusable Project Processing
# =============================================================================


async def invoke_and_handle_project(
    service,
    job_id,
    project_path,
    language,
    build_system,
    stderr,
    workspace_base,
    repo_alias,
    response_status,
    actions,
    reasoning,
    scip_retry_succeeds=True,
):
    """
    Helper to invoke Claude Code and handle response for a project.

    Encapsulates the repetitive pattern of:
    1. Mock Claude Code subprocess
    2. Mock SCIP retry
    3. Create workspace
    4. Invoke Claude Code
    5. Handle response

    Returns the ClaudeResponse for assertions.
    """
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *args, **kwargs: mock_claude_subprocess(
            response_status, actions, reasoning
        ),
    ):
        retry_mock = (
            mock_scip_retry_success if scip_retry_succeeds else mock_scip_retry_failure
        )

        with patch.object(
            service,
            "_retry_scip_for_project",
            side_effect=lambda job_id, project_path: retry_mock(),
        ):
            # Create workspace
            workspace = (
                workspace_base / f"cidx-scip-{job_id}" / project_path.rstrip("/")
            )
            workspace.mkdir(parents=True, exist_ok=True)

            # Invoke Claude Code
            response = await service.invoke_claude_code(
                job_id=job_id,
                project_path=project_path,
                language=language,
                build_system=build_system,
                stderr=stderr,
                workspace=workspace,
                repo_alias=repo_alias,
                attempt=1,
            )

            # Handle the response
            await service.handle_project_response(
                job_id=job_id, project_path=project_path, response=response
            )

            return response


# =============================================================================
# E2E Test Scenario 1: Total Failure Resolved
# =============================================================================


@pytest.mark.asyncio
async def test_scenario1_total_failure_resolved(
    job_manager, self_healing_service, temp_workspace
):
    """
    E2E Scenario 1: Total Failure Resolved

    Given: Repository with single Python project
    And: SCIP indexing fails due to missing poetry
    When: Self-healing service processes the failure
    And: Claude Code responds "progress" (installs poetry)
    And: SCIP retry succeeds
    Then: Job status is COMPLETED
    And: Project status is "resolved" in language_resolution_status
    """
    # Create job
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="test-repo",
    )

    # Create total failure result (single Python project failed)
    failed_python = create_failed_project(
        path="backend/",
        language="python",
        build_system="poetry",
        stderr="Error: poetry not found in PATH\nCommand 'poetry' not found",
    )

    generation_result = GenerationResult(
        total_projects=1,
        successful_projects=0,
        failed_projects=1,
        project_results=[failed_python],
    )

    # Handle SCIP failure (AC1)
    await self_healing_service.handle_scip_failure(
        job_id=job_id, generation_result=generation_result, repo_alias="test-repo"
    )

    # Verify job transitioned to RESOLVING_PREREQUISITES
    job = job_manager.jobs[job_id]
    assert job.status == JobStatus.RESOLVING_PREREQUISITES
    assert "backend/" in job.language_resolution_status

    # Invoke Claude Code with "progress" response
    response = await invoke_and_handle_project(
        service=self_healing_service,
        job_id=job_id,
        project_path="backend/",
        language="python",
        build_system="poetry",
        stderr=failed_python.indexer_result.stderr,
        workspace_base=temp_workspace,
        repo_alias="test-repo",
        response_status="progress",
        actions=["apt-get install python3-poetry", "poetry install"],
        reasoning="Installed poetry and project dependencies",
    )

    # Determine final job status
    final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert results
    assert response.status == "progress"
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "resolved"
    assert final_status == JobStatus.COMPLETED


# =============================================================================
# E2E Test Scenario 2: Partial Failure - All Resolved (CRITICAL)
# =============================================================================


@pytest.mark.asyncio
async def test_scenario2_partial_failure_all_resolved(
    job_manager, self_healing_service, temp_workspace
):
    """
    E2E Scenario 2: Partial Failure - All Resolved (CRITICAL TEST)

    Given: Repository with TypeScript ✓, Python ✗, Java ✗
    When: Self-healing service processes the failures
    And: Claude Code resolves Python dependency
    And: Claude Code resolves Java dependency
    Then: Job status is COMPLETED
    And: All 3 projects have indexes
    And: Python status is "resolved"
    And: Java status is "resolved"
    """
    # Create job
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="multi-lang-repo",
    )

    # Create partial failure result (TypeScript ✓, Python ✗, Java ✗)
    successful_ts = create_successful_project(
        path="frontend/", language="typescript", build_system="npm"
    )
    failed_python = create_failed_project(
        path="backend/",
        language="python",
        build_system="poetry",
        stderr="Error: poetry not found in PATH",
    )
    failed_java = create_failed_project(
        path="services/api/",
        language="java",
        build_system="maven",
        stderr="Error: mvn not found in PATH",
    )

    generation_result = GenerationResult(
        total_projects=3,
        successful_projects=1,
        failed_projects=2,
        project_results=[successful_ts, failed_python, failed_java],
    )

    # Handle SCIP failure (AC1)
    await self_healing_service.handle_scip_failure(
        job_id=job_id, generation_result=generation_result, repo_alias="multi-lang-repo"
    )

    # Verify only failed projects tracked
    job = job_manager.jobs[job_id]
    assert len(job.language_resolution_status) == 2
    assert "backend/" in job.language_resolution_status
    assert "services/api/" in job.language_resolution_status

    # Process Python project
    await invoke_and_handle_project(
        service=self_healing_service,
        job_id=job_id,
        project_path="backend/",
        language="python",
        build_system="poetry",
        stderr=failed_python.indexer_result.stderr,
        workspace_base=temp_workspace,
        repo_alias="multi-lang-repo",
        response_status="progress",
        actions=["apt-get install python3-poetry"],
        reasoning="Installed poetry for Python project",
    )

    # Process Java project
    await invoke_and_handle_project(
        service=self_healing_service,
        job_id=job_id,
        project_path="services/api/",
        language="java",
        build_system="maven",
        stderr=failed_java.indexer_result.stderr,
        workspace_base=temp_workspace,
        repo_alias="multi-lang-repo",
        response_status="progress",
        actions=["apt-get install maven"],
        reasoning="Installed Maven for Java project",
    )

    # Determine final job status
    final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert both projects resolved
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "resolved"
    assert job.language_resolution_status["services/api/"]["status"] == "resolved"
    assert final_status == JobStatus.COMPLETED


# =============================================================================
# E2E Test Scenario 3: Partial Resolution (Graceful Degradation)
# =============================================================================


@pytest.mark.asyncio
async def test_scenario3_partial_resolution(
    job_manager, self_healing_service, temp_workspace
):
    """
    E2E Scenario 3: Partial Resolution (Graceful Degradation)

    Given: Repository with TypeScript ✓, Python ✗, C++ ✗
    When: Self-healing service processes the failures
    And: Claude Code resolves Python dependency
    And: Claude Code returns "unresolvable" for C++
    Then: Job status is COMPLETED
    And: failure_reason documents partial success
    And: Python status is "resolved"
    And: C++ status is "unresolvable"
    """
    # Create job
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="mixed-repo",
    )

    # Create partial failure result (TypeScript ✓, Python ✗, C++ ✗)
    successful_ts = create_successful_project(
        path="frontend/", language="typescript", build_system="npm"
    )
    failed_python = create_failed_project(
        path="backend/",
        language="python",
        build_system="poetry",
        stderr="Error: poetry not found in PATH",
    )
    failed_cpp = create_failed_project(
        path="native/",
        language="cpp",
        build_system="cmake",
        stderr="Error: Unsupported C++ version, requires gcc-13",
    )

    generation_result = GenerationResult(
        total_projects=3,
        successful_projects=1,
        failed_projects=2,
        project_results=[successful_ts, failed_python, failed_cpp],
    )

    # Handle SCIP failure
    await self_healing_service.handle_scip_failure(
        job_id=job_id, generation_result=generation_result, repo_alias="mixed-repo"
    )

    # Process Python project with "progress" response
    await invoke_and_handle_project(
        service=self_healing_service,
        job_id=job_id,
        project_path="backend/",
        language="python",
        build_system="poetry",
        stderr=failed_python.indexer_result.stderr,
        workspace_base=temp_workspace,
        repo_alias="mixed-repo",
        response_status="progress",
        actions=["apt-get install python3-poetry"],
        reasoning="Installed poetry for Python project",
    )

    # Process C++ project with "unresolvable" response
    await invoke_and_handle_project(
        service=self_healing_service,
        job_id=job_id,
        project_path="native/",
        language="cpp",
        build_system="cmake",
        stderr=failed_cpp.indexer_result.stderr,
        workspace_base=temp_workspace,
        repo_alias="mixed-repo",
        response_status="unresolvable",
        actions=[],
        reasoning="Cannot install gcc-13, system repositories only provide gcc-11",
    )

    # Determine final job status
    final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert partial success
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "resolved"
    assert job.language_resolution_status["native/"]["status"] == "unresolvable"
    assert final_status == JobStatus.COMPLETED
    assert job.failure_reason is not None
    assert "1/2 projects resolved" in job.failure_reason


# =============================================================================
# E2E Test Scenario 4: All Unresolvable
# =============================================================================


@pytest.mark.asyncio
async def test_scenario4_all_unresolvable(
    job_manager, self_healing_service, temp_workspace
):
    """
    E2E Scenario 4: All Unresolvable

    Given: Repository with 3 failed projects
    When: Self-healing service processes all failures
    And: Claude Code returns "unresolvable" for all
    Then: Job status is FAILED
    And: failure_reason explains none could be resolved
    """
    # Create job
    job_id = job_manager.submit_job(
        operation_type="scip_indexing",
        func=lambda: {"success": True},
        submitter_username="test_user",
        repo_alias="broken-repo",
    )

    # Create total failure result (all 3 projects failed)
    failed_projects = [
        create_failed_project(
            "backend/", "python", "poetry", "Error: Requires Python 3.13, not available"
        ),
        create_failed_project(
            "services/api/",
            "java",
            "maven",
            "Error: Requires JDK 21, only JDK 11 available",
        ),
        create_failed_project(
            "services/worker/",
            "go",
            "go",
            "Error: Requires Go 1.22, system has Go 1.19",
        ),
    ]

    generation_result = GenerationResult(
        total_projects=3,
        successful_projects=0,
        failed_projects=3,
        project_results=failed_projects,
    )

    # Handle SCIP failure
    await self_healing_service.handle_scip_failure(
        job_id=job_id, generation_result=generation_result, repo_alias="broken-repo"
    )

    # Process all projects with "unresolvable" responses
    project_configs = [
        (
            "backend/",
            "python",
            "poetry",
            failed_projects[0].indexer_result.stderr,
            "Python 3.13 not available in apt repositories",
        ),
        (
            "services/api/",
            "java",
            "maven",
            failed_projects[1].indexer_result.stderr,
            "JDK 21 not available, only JDK 11 provided",
        ),
        (
            "services/worker/",
            "go",
            "go",
            failed_projects[2].indexer_result.stderr,
            "Go 1.22 not available, upgrading requires manual intervention",
        ),
    ]

    for project_path, language, build_system, stderr, reasoning in project_configs:
        await invoke_and_handle_project(
            service=self_healing_service,
            job_id=job_id,
            project_path=project_path,
            language=language,
            build_system=build_system,
            stderr=stderr,
            workspace_base=temp_workspace,
            repo_alias="broken-repo",
            response_status="unresolvable",
            actions=[],
            reasoning=reasoning,
        )

    # Determine final job status
    final_status = await self_healing_service.determine_job_completion(job_id)

    # Assert all unresolvable
    job = job_manager.jobs[job_id]
    assert job.language_resolution_status["backend/"]["status"] == "unresolvable"
    assert job.language_resolution_status["services/api/"]["status"] == "unresolvable"
    assert (
        job.language_resolution_status["services/worker/"]["status"] == "unresolvable"
    )
    assert final_status == JobStatus.FAILED
    assert job.failure_reason == "No projects could be resolved"
