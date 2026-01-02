"""
Unit tests for SCIP Self-Healing Service - Prompt Building (Story #645 AC2).

Tests prompt generation for language-specific SCIP failure diagnosis.
"""

import pytest
from code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestSCIPSelfHealingPromptBuilding:
    """Test suite for prompt building functionality."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create a BackgroundJobManager for testing."""
        storage_path = tmp_path / "jobs.json"
        return BackgroundJobManager(storage_path=str(storage_path))

    def test_build_project_prompt_python_poetry(self, job_manager, tmp_path):
        """AC2: Verify language-specific prompt generation for Python/poetry project."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        prompt = service.build_project_prompt(
            repo_alias="test-repo",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="ModuleNotFoundError: No module named 'requests'",
        )

        # Verify prompt contains all required elements
        assert "test-repo" in prompt
        assert "backend/" in prompt
        assert "python" in prompt.lower()
        assert "poetry" in prompt
        assert "ModuleNotFoundError: No module named 'requests'" in prompt
        assert "npm, pip, pip3, pipenv, poetry" in prompt  # Package manager whitelist
        assert '"status":' in prompt  # JSON response format
        assert (
            '"progress"' in prompt
            or '"no_progress"' in prompt
            or '"unresolvable"' in prompt
        )

    def test_build_project_prompt_typescript_npm(self, job_manager, tmp_path):
        """AC2: Verify language-specific prompt generation for TypeScript/npm project."""
        from code_indexer.server.services.scip_self_healing import (
            SCIPSelfHealingService,
        )

        service = SCIPSelfHealingService(job_manager=job_manager, repo_root=tmp_path)

        prompt = service.build_project_prompt(
            repo_alias="test-repo",
            project_path="frontend/",
            language="typescript",
            build_system="npm",
            stderr="Cannot find module '@types/node'",
        )

        assert "frontend/" in prompt
        assert "typescript" in prompt.lower()
        assert "npm" in prompt
        assert "Cannot find module '@types/node'" in prompt
        assert "Other projects in this repository may have succeeded" in prompt
