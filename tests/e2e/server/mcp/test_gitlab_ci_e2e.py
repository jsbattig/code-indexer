"""
E2E integration tests for GitLab CI MCP tools.

Tests real GitLab API integration (Anti-Mock principle compliance).
Requires GITLAB_TOKEN environment variable for authentication.

Story #634: GitLab CI Monitoring - E2E validation
"""

import os
import pytest
from unittest.mock import MagicMock

# Check for GitLab token availability
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")
SKIP_REASON = "GITLAB_TOKEN environment variable not set. Set GITLAB_TOKEN to run E2E GitLab CI tests."


@pytest.mark.skipif(not GITLAB_TOKEN, reason=SKIP_REASON)
class TestGitLabCIE2E:
    """
    E2E tests using real GitLab API.

    Tests against gitlab-org/gitlab-foss repository (public project).
    Validates complete tool chain: handlers -> client -> GitLab API.
    """

    TEST_PROJECT = "gitlab-org/gitlab-foss"  # Public GitLab project for testing

    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user for handler tests."""
        user = MagicMock()
        user.username = "test-user"
        user.permissions = {"repository:read", "repository:write"}
        return user

    @pytest.mark.asyncio
    async def test_list_pipelines_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_list_pipelines tool.

        Validates:
        - Real GitLab API call succeeds
        - Returns valid pipelines
        - Rate limiting info is captured
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import handle_gitlab_ci_list_pipelines

        args = {
            "project_id": self.TEST_PROJECT,
            "limit": 5,
        }

        result = await handle_gitlab_ci_list_pipelines(args, mock_user)

        # Validate response structure
        assert result["success"] is True
        assert "pipelines" in result
        assert "rate_limit" in result
        assert isinstance(result["pipelines"], list)

        # Validate rate limit info exists
        rate_limit = result["rate_limit"]
        assert "limit" in rate_limit
        assert "remaining" in rate_limit
        assert "reset" in rate_limit

        # If pipelines exist, validate structure
        if result["pipelines"]:
            pipeline = result["pipelines"][0]
            assert "id" in pipeline
            assert "status" in pipeline
            assert "ref" in pipeline
            assert "created_at" in pipeline

    @pytest.mark.asyncio
    async def test_list_pipelines_with_filters_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_list_pipelines with ref and status filters.

        Validates:
        - Filters work against real GitLab API
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import handle_gitlab_ci_list_pipelines

        args = {
            "project_id": self.TEST_PROJECT,
            "ref": "master",
            "status": "success",
            "limit": 5,
        }

        result = await handle_gitlab_ci_list_pipelines(args, mock_user)

        assert result["success"] is True
        assert "pipelines" in result

        # If pipelines exist, verify filter was applied
        if result["pipelines"]:
            for pipeline in result["pipelines"]:
                # All pipelines should match filters
                assert pipeline["ref"] == "master"
                assert pipeline["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_pipeline_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_get_pipeline tool.

        Validates:
        - Can retrieve detailed pipeline information
        - Real GitLab API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gitlab_ci_list_pipelines,
            handle_gitlab_ci_get_pipeline,
        )

        # First, get a pipeline ID from list_pipelines
        list_args = {"project_id": self.TEST_PROJECT, "limit": 1}
        list_result = await handle_gitlab_ci_list_pipelines(list_args, mock_user)

        if not list_result["pipelines"]:
            pytest.skip("No pipelines available in project")

        pipeline_id = list_result["pipelines"][0]["id"]

        # Now get detailed pipeline information
        get_args = {
            "project_id": self.TEST_PROJECT,
            "pipeline_id": pipeline_id,
        }

        result = await handle_gitlab_ci_get_pipeline(get_args, mock_user)

        assert result["success"] is True
        assert "pipeline" in result

        pipeline_info = result["pipeline"]
        assert pipeline_info["id"] == pipeline_id
        assert "status" in pipeline_info
        assert "ref" in pipeline_info
        assert "web_url" in pipeline_info
        assert "jobs" in pipeline_info
        assert isinstance(pipeline_info["jobs"], list)

    @pytest.mark.asyncio
    async def test_search_logs_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_search_logs tool.

        Validates:
        - Can search logs with ripgrep pattern
        - Real GitLab API call succeeds
        - Returns matching log lines
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gitlab_ci_list_pipelines,
            handle_gitlab_ci_search_logs,
        )

        # Get a completed pipeline
        list_args = {
            "project_id": self.TEST_PROJECT,
            "status": "success",
            "limit": 5,
        }
        list_result = await handle_gitlab_ci_list_pipelines(list_args, mock_user)

        if not list_result["pipelines"]:
            pytest.skip("No completed pipelines available")

        pipeline_id = list_result["pipelines"][0]["id"]

        # Search for common pattern (test, build, etc.)
        search_args = {
            "project_id": self.TEST_PROJECT,
            "pipeline_id": pipeline_id,
            "pattern": "test",  # Common word in test logs
        }

        result = await handle_gitlab_ci_search_logs(search_args, mock_user)

        assert result["success"] is True
        assert "matches" in result
        assert isinstance(result["matches"], list)

        # If matches found, validate structure
        if result["matches"]:
            match = result["matches"][0]
            assert "job_id" in match
            assert "job_name" in match
            assert "line" in match
            assert "line_number" in match

    @pytest.mark.asyncio
    async def test_get_job_logs_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_get_job_logs tool.

        Validates:
        - Can retrieve complete job logs
        - Real GitLab API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gitlab_ci_list_pipelines,
            handle_gitlab_ci_search_logs,
            handle_gitlab_ci_get_job_logs,
        )

        # Get a completed pipeline
        list_args = {
            "project_id": self.TEST_PROJECT,
            "status": "success",
            "limit": 1,
        }
        list_result = await handle_gitlab_ci_list_pipelines(list_args, mock_user)

        if not list_result["pipelines"]:
            pytest.skip("No completed pipelines available")

        pipeline_id = list_result["pipelines"][0]["id"]

        # Search logs to get a job_id
        search_args = {
            "project_id": self.TEST_PROJECT,
            "pipeline_id": pipeline_id,
            "pattern": ".*",  # Match anything to get job IDs
        }
        search_result = await handle_gitlab_ci_search_logs(search_args, mock_user)

        if not search_result["matches"]:
            pytest.skip("No job logs available for pipeline")

        job_id = search_result["matches"][0]["job_id"]

        # Get complete job logs
        job_args = {
            "project_id": self.TEST_PROJECT,
            "job_id": job_id,
        }

        result = await handle_gitlab_ci_get_job_logs(job_args, mock_user)

        assert result["success"] is True
        assert "logs" in result
        assert isinstance(result["logs"], str)
        assert len(result["logs"]) > 0

    @pytest.mark.asyncio
    async def test_authentication_error_e2e(self, mock_user):
        """
        E2E test for authentication error handling.

        Validates:
        - Invalid token produces proper error
        - Real GitLab API error handling
        """
        from code_indexer.server.clients.gitlab_ci_client import (
            GitLabCIClient,
            GitLabAuthenticationError,
        )

        # Use invalid token
        client = GitLabCIClient("invalid-token-12345")

        with pytest.raises(GitLabAuthenticationError):
            await client.list_pipelines(project_id=self.TEST_PROJECT)

    @pytest.mark.asyncio
    async def test_project_not_found_e2e(self, mock_user):
        """
        E2E test for project not found error handling.

        Validates:
        - Invalid project produces proper error
        - Real GitLab API error handling
        """
        from code_indexer.server.clients.gitlab_ci_client import (
            GitLabCIClient,
            GitLabProjectNotFoundError,
        )

        client = GitLabCIClient(GITLAB_TOKEN)

        with pytest.raises(GitLabProjectNotFoundError):
            await client.list_pipelines(project_id="nonexistent/project-12345")


@pytest.mark.skipif(not GITLAB_TOKEN, reason=SKIP_REASON)
class TestGitLabCIE2EWriteOperations:
    """
    E2E tests for write operations (retry, cancel).

    CAUTION: These tests modify GitLab CI state.
    Only run when explicitly intended.
    """

    TEST_PROJECT = "gitlab-org/gitlab-foss"

    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user for handler tests."""
        user = MagicMock()
        user.username = "test-user"
        user.permissions = {"repository:read", "repository:write"}
        return user

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Modifies GitLab CI state - run manually when needed")
    async def test_retry_pipeline_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_retry_pipeline tool.

        CAUTION: This triggers a real pipeline retry.

        Validates:
        - Can retry failed pipeline
        - Real GitLab API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gitlab_ci_list_pipelines,
            handle_gitlab_ci_retry_pipeline,
        )

        # Find a failed pipeline
        list_args = {
            "project_id": self.TEST_PROJECT,
            "status": "failed",
            "limit": 10,
        }
        list_result = await handle_gitlab_ci_list_pipelines(list_args, mock_user)

        if not list_result["pipelines"]:
            pytest.skip("No failed pipelines available for retry")

        pipeline_id = list_result["pipelines"][0]["id"]

        # Retry the pipeline
        retry_args = {
            "project_id": self.TEST_PROJECT,
            "pipeline_id": pipeline_id,
        }

        result = await handle_gitlab_ci_retry_pipeline(retry_args, mock_user)

        assert result["success"] is True
        assert result["pipeline_id"] == pipeline_id
        assert "message" in result

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Modifies GitLab CI state - run manually when needed")
    async def test_cancel_pipeline_e2e(self, mock_user):
        """
        E2E test for gitlab_ci_cancel_pipeline tool.

        CAUTION: This cancels a real pipeline.

        Validates:
        - Can cancel running pipeline
        - Real GitLab API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gitlab_ci_list_pipelines,
            handle_gitlab_ci_cancel_pipeline,
        )

        # Find a running or pending pipeline
        list_args = {
            "project_id": self.TEST_PROJECT,
            "limit": 10,
        }
        list_result = await handle_gitlab_ci_list_pipelines(list_args, mock_user)

        active_pipelines = [
            p for p in list_result["pipelines"] if p["status"] in ("running", "pending")
        ]

        if not active_pipelines:
            pytest.skip("No active pipelines available for cancellation")

        pipeline_id = active_pipelines[0]["id"]

        # Cancel the pipeline
        cancel_args = {
            "project_id": self.TEST_PROJECT,
            "pipeline_id": pipeline_id,
        }

        result = await handle_gitlab_ci_cancel_pipeline(cancel_args, mock_user)

        assert result["success"] is True
        assert result["pipeline_id"] == pipeline_id
        assert "message" in result
