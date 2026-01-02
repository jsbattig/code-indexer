"""
Unit tests for SCIP Self-Healing Service.

Tests AC1 of Story #645 using strict TDD methodology.
Starting with AC1 only - will add AC2-AC7 tests incrementally.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from code_indexer.scip.generator import GenerationResult, ProjectGenerationResult
from code_indexer.scip.discovery import DiscoveredProject
from code_indexer.scip.indexers.base import IndexerResult, IndexerStatus
from code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    JobStatus,
)


class TestSCIPSelfHealingServiceAC1:
    """Test AC1: SCIP Failure Detection and Per-Project Log Capture."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create a BackgroundJobManager for testing."""
        storage_path = tmp_path / "jobs.json"
        return BackgroundJobManager(storage_path=str(storage_path))

    @pytest.fixture
    def failed_python_project(self):
        """Create a failed Python project for testing."""
        project = DiscoveredProject(
            relative_path=Path("backend/"),
            language="python",
            build_system="poetry",
            build_file=Path("backend/pyproject.toml"),
        )
        indexer_result = IndexerResult(
            status=IndexerStatus.FAILED,
            duration_seconds=2.5,
            output_file=None,
            stdout="",
            stderr="Error: poetry not found in PATH",
            exit_code=1,
        )
        return ProjectGenerationResult(project=project, indexer_result=indexer_result)

    @pytest.fixture
    def failed_typescript_project(self):
        """Create a failed TypeScript project for testing."""
        project = DiscoveredProject(
            relative_path=Path("frontend/"),
            language="typescript",
            build_system="npm",
            build_file=Path("frontend/package.json"),
        )
        indexer_result = IndexerResult(
            status=IndexerStatus.FAILED,
            duration_seconds=1.2,
            output_file=None,
            stdout="",
            stderr="Error: scip-typescript not found",
            exit_code=127,
        )
        return ProjectGenerationResult(project=project, indexer_result=indexer_result)

    @pytest.fixture
    def successful_java_project(self):
        """Create a successful Java project for testing."""
        project = DiscoveredProject(
            relative_path=Path("services/api/"),
            language="java",
            build_system="maven",
            build_file=Path("services/api/pom.xml"),
        )
        indexer_result = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=10.3,
            output_file=Path("services/api/index.scip"),
            stdout="Indexing completed successfully",
            stderr="",
            exit_code=0,
        )
        return ProjectGenerationResult(project=project, indexer_result=indexer_result)

    @pytest.mark.asyncio
    async def test_handle_complete_failure_transitions_to_resolving_state(
        self, job_manager, failed_python_project, failed_typescript_project, tmp_path
    ):
        """Test that complete SCIP failure transitions job to RESOLVING_PREREQUISITES."""
        # This test will fail because SCIPSelfHealingService doesn't exist yet
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        # Arrange: Create job and complete failure result
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
            project_results=[failed_python_project, failed_typescript_project],
            duration_seconds=3.7,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        # Act: Handle SCIP failure
        await service.handle_scip_failure(
            job_id=job_id,
            generation_result=generation_result,
            repo_alias="test-repo",
        )

        # Assert: Job transitioned to RESOLVING_PREREQUISITES
        job = job_manager.jobs[job_id]
        assert job.status == JobStatus.RESOLVING_PREREQUISITES

    @pytest.mark.asyncio
    async def test_handle_failure_extracts_per_project_details(
        self, job_manager, failed_python_project, failed_typescript_project, tmp_path
    ):
        """Test that per-project details are extracted correctly."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        # Arrange
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
            project_results=[failed_python_project, failed_typescript_project],
            duration_seconds=3.7,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        # Act
        await service.handle_scip_failure(
            job_id=job_id,
            generation_result=generation_result,
            repo_alias="test-repo",
        )

        # Assert: language_resolution_status contains per-project entries
        job = job_manager.jobs[job_id]
        assert job.language_resolution_status is not None
        assert "backend/" in job.language_resolution_status
        assert "frontend/" in job.language_resolution_status

        # Assert: Backend project details
        backend = job.language_resolution_status["backend/"]
        assert backend["language"] == "python"
        assert backend["build_system"] == "poetry"
        assert backend["status"] == "pending"
        assert "poetry not found" in backend["last_error"]

        # Assert: Frontend project details
        frontend = job.language_resolution_status["frontend/"]
        assert frontend["language"] == "typescript"
        assert frontend["build_system"] == "npm"
        assert frontend["status"] == "pending"

    @pytest.mark.asyncio
    async def test_handle_partial_failure_only_enqueues_failed_projects(
        self, job_manager, successful_java_project, failed_python_project, tmp_path
    ):
        """Test that only failed projects are tracked in language_resolution_status."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        # Arrange
        job_id = job_manager.submit_job(
            operation_type="scip_indexing",
            func=lambda: {"success": True},
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        generation_result = GenerationResult(
            total_projects=2,
            successful_projects=1,
            failed_projects=1,
            project_results=[successful_java_project, failed_python_project],
            duration_seconds=12.8,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        # Act
        await service.handle_scip_failure(
            job_id=job_id,
            generation_result=generation_result,
            repo_alias="test-repo",
        )

        # Assert: Only failed project in language_resolution_status
        job = job_manager.jobs[job_id]
        assert "backend/" in job.language_resolution_status
        assert "services/api/" not in job.language_resolution_status


class TestSCIPSelfHealingServiceAC2:
    """Test AC2: Claude Code Invocation with Language-Specific Prompts."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create a BackgroundJobManager for testing."""
        storage_path = tmp_path / "jobs.json"
        return BackgroundJobManager(storage_path=str(storage_path))

    def test_build_project_prompt_contains_required_elements(
        self, job_manager, tmp_path
    ):
        """Test that build_project_prompt includes all required elements."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        # Act
        prompt = service.build_project_prompt(
            repo_alias="test-repo",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="Error: poetry not found in PATH",
        )

        # Assert: Prompt contains all required elements
        assert "test-repo" in prompt
        assert "backend/" in prompt
        assert "python" in prompt.lower()
        assert "poetry" in prompt.lower()
        assert "poetry not found" in prompt

        # Assert: Contains whitelisted package managers
        package_managers = ["npm", "pip", "poetry", "maven", "gradle"]
        for manager in package_managers:
            assert manager in prompt.lower()

        # Assert: Specifies JSON response format
        assert "json" in prompt.lower()
        assert "status" in prompt.lower()
        assert "actions_taken" in prompt.lower()

    @pytest.mark.asyncio
    async def test_invoke_claude_code_subprocess_call(self, job_manager, tmp_path):
        """Test that invoke_claude_code calls subprocess with correct parameters."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )
        from unittest.mock import patch, AsyncMock
        import json

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        job_id = "test-job-123"
        workspace = tmp_path / f"cidx-scip-{job_id}" / "backend"
        workspace.mkdir(parents=True, exist_ok=True)

        # Mock subprocess response
        mock_response = {
            "status": "progress",
            "actions_taken": ["sudo apt-get install poetry"],
            "reasoning": "Installed poetry",
        }

        # Mock async subprocess
        mock_process = Mock()
        mock_process.communicate = AsyncMock(
            return_value=(
                json.dumps(mock_response).encode("utf-8"),  # stdout as bytes
                b"",  # stderr as bytes
            )
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            # Act
            response = await service.invoke_claude_code(
                job_id=job_id,
                project_path="backend/",
                language="python",
                build_system="poetry",
                stderr="poetry not found",
                workspace=workspace,
            )

            # Assert: create_subprocess_exec was called
            assert mock_create.called
            call_args = mock_create.call_args

            # Assert: Used /usr/local/bin/claude
            assert "/usr/local/bin/claude" in str(call_args)

            # Assert: Used --dangerously-skip-permissions
            assert "--dangerously-skip-permissions" in str(call_args)

            # Assert: Response was parsed correctly
            assert response.status == "progress"
            assert "sudo apt-get install poetry" in response.actions_taken


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
