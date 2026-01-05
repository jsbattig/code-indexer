"""
E2E integration tests for GitHub Actions MCP tools.

Tests real GitHub API integration (Anti-Mock principle compliance).
Requires GH_TOKEN environment variable for authentication.

Story #633: GitHub Actions Monitoring - E2E validation
"""

import os
import pytest
from unittest.mock import MagicMock

# Check for GitHub token availability
GH_TOKEN = os.environ.get("GH_TOKEN")
SKIP_REASON = "GH_TOKEN environment variable not set. Set GH_TOKEN to run E2E GitHub Actions tests."


@pytest.mark.skipif(not GH_TOKEN, reason=SKIP_REASON)
class TestGitHubActionsE2E:
    """
    E2E tests using real GitHub API.

    Tests against jsbattig/code-indexer repository.
    Validates complete tool chain: handlers -> client -> GitHub API.
    """

    TEST_REPOSITORY = "jsbattig/code-indexer"

    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user for handler tests."""
        user = MagicMock()
        user.username = "test-user"
        user.permissions = {"repository:read", "repository:write"}
        return user

    @pytest.mark.asyncio
    async def test_list_runs_e2e(self, mock_user):
        """
        E2E test for gh_actions_list_runs tool.

        Validates:
        - Real GitHub API call succeeds
        - Returns valid workflow runs
        - Rate limiting info is captured
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import handle_gh_actions_list_runs

        args = {
            "repository": self.TEST_REPOSITORY,
            "limit": 5,
        }

        result = await handle_gh_actions_list_runs(args, mock_user)

        # Validate response structure
        assert result["success"] is True
        assert "runs" in result
        assert "rate_limit" in result
        assert isinstance(result["runs"], list)

        # Validate rate limit info exists
        rate_limit = result["rate_limit"]
        assert "limit" in rate_limit
        assert "remaining" in rate_limit
        assert "reset" in rate_limit

        # If runs exist, validate structure
        if result["runs"]:
            run = result["runs"][0]
            assert "id" in run
            assert "name" in run
            assert "status" in run
            assert "branch" in run
            assert "created_at" in run

    @pytest.mark.asyncio
    async def test_list_runs_with_filters_e2e(self, mock_user):
        """
        E2E test for gh_actions_list_runs with branch and status filters.

        Validates:
        - Filters work against real GitHub API
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import handle_gh_actions_list_runs

        args = {
            "repository": self.TEST_REPOSITORY,
            "branch": "master",
            "status": "completed",
            "limit": 5,
        }

        result = await handle_gh_actions_list_runs(args, mock_user)

        assert result["success"] is True
        assert "runs" in result

        # If runs exist, verify filter was applied
        if result["runs"]:
            for run in result["runs"]:
                # All runs should match filters
                assert run["branch"] == "master"
                assert run["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_run_e2e(self, mock_user):
        """
        E2E test for gh_actions_get_run tool.

        Validates:
        - Can retrieve detailed run information
        - Real GitHub API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gh_actions_list_runs,
            handle_gh_actions_get_run,
        )

        # First, get a run ID from list_runs
        list_args = {"repository": self.TEST_REPOSITORY, "limit": 1}
        list_result = await handle_gh_actions_list_runs(list_args, mock_user)

        if not list_result["runs"]:
            pytest.skip("No workflow runs available in repository")

        run_id = list_result["runs"][0]["id"]

        # Now get detailed run information
        get_args = {
            "repository": self.TEST_REPOSITORY,
            "run_id": run_id,
        }

        result = await handle_gh_actions_get_run(get_args, mock_user)

        assert result["success"] is True
        assert "run" in result

        run_info = result["run"]
        assert run_info["id"] == run_id
        assert "name" in run_info
        assert "status" in run_info
        assert "html_url" in run_info
        assert "jobs_url" in run_info
        assert "run_started_at" in run_info

    @pytest.mark.asyncio
    async def test_search_logs_e2e(self, mock_user):
        """
        E2E test for gh_actions_search_logs tool.

        Validates:
        - Can search logs with ripgrep pattern
        - Real GitHub API call succeeds
        - Returns matching log lines
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gh_actions_list_runs,
            handle_gh_actions_search_logs,
        )

        # Get a completed run
        list_args = {
            "repository": self.TEST_REPOSITORY,
            "status": "completed",
            "limit": 5,
        }
        list_result = await handle_gh_actions_list_runs(list_args, mock_user)

        if not list_result["runs"]:
            pytest.skip("No completed workflow runs available")

        run_id = list_result["runs"][0]["id"]

        # Search for common pattern (pytest, python, test, etc.)
        search_args = {
            "repository": self.TEST_REPOSITORY,
            "run_id": run_id,
            "pattern": "test",  # Common word in test logs
        }

        result = await handle_gh_actions_search_logs(search_args, mock_user)

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
        E2E test for gh_actions_get_job_logs tool.

        Validates:
        - Can retrieve complete job logs
        - Real GitHub API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gh_actions_list_runs,
            handle_gh_actions_search_logs,
            handle_gh_actions_get_job_logs,
        )

        # Get a completed run
        list_args = {
            "repository": self.TEST_REPOSITORY,
            "status": "completed",
            "limit": 1,
        }
        list_result = await handle_gh_actions_list_runs(list_args, mock_user)

        if not list_result["runs"]:
            pytest.skip("No completed workflow runs available")

        run_id = list_result["runs"][0]["id"]

        # Search logs to get a job_id
        search_args = {
            "repository": self.TEST_REPOSITORY,
            "run_id": run_id,
            "pattern": ".*",  # Match anything to get job IDs
        }
        search_result = await handle_gh_actions_search_logs(search_args, mock_user)

        if not search_result["matches"]:
            pytest.skip("No job logs available for run")

        job_id = search_result["matches"][0]["job_id"]

        # Get complete job logs
        job_args = {
            "repository": self.TEST_REPOSITORY,
            "job_id": job_id,
        }

        result = await handle_gh_actions_get_job_logs(job_args, mock_user)

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
        - Real GitHub API error handling
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
            GitHubAuthenticationError,
        )

        # Use invalid token
        client = GitHubActionsClient("invalid-token-12345")

        with pytest.raises(GitHubAuthenticationError):
            await client.list_runs(repository=self.TEST_REPOSITORY)

    @pytest.mark.asyncio
    async def test_repository_not_found_e2e(self, mock_user):
        """
        E2E test for repository not found error handling.

        Validates:
        - Invalid repository produces proper error
        - Real GitHub API error handling
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
            GitHubRepositoryNotFoundError,
        )

        client = GitHubActionsClient(GH_TOKEN)

        with pytest.raises(GitHubRepositoryNotFoundError):
            await client.list_runs(repository="nonexistent/repository-12345")


@pytest.mark.skipif(not GH_TOKEN, reason=SKIP_REASON)
class TestGitHubActionsE2EWriteOperations:
    """
    E2E tests for write operations (retry, cancel).

    CAUTION: These tests modify GitHub Actions state.
    Only run when explicitly intended.
    """

    TEST_REPOSITORY = "jsbattig/code-indexer"

    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user for handler tests."""
        user = MagicMock()
        user.username = "test-user"
        user.permissions = {"repository:read", "repository:write"}
        return user

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Modifies GitHub Actions state - run manually when needed")
    async def test_retry_run_e2e(self, mock_user):
        """
        E2E test for gh_actions_retry_run tool.

        CAUTION: This triggers a real workflow retry.

        Validates:
        - Can retry failed workflow
        - Real GitHub API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gh_actions_list_runs,
            handle_gh_actions_retry_run,
        )

        # Find a failed run
        list_args = {
            "repository": self.TEST_REPOSITORY,
            "status": "completed",
            "limit": 10,
        }
        list_result = await handle_gh_actions_list_runs(list_args, mock_user)

        failed_runs = [r for r in list_result["runs"] if r.get("conclusion") == "failure"]

        if not failed_runs:
            pytest.skip("No failed workflow runs available for retry")

        run_id = failed_runs[0]["id"]

        # Retry the run
        retry_args = {
            "repository": self.TEST_REPOSITORY,
            "run_id": run_id,
        }

        result = await handle_gh_actions_retry_run(retry_args, mock_user)

        assert result["success"] is True
        assert result["run_id"] == run_id
        assert "message" in result

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Modifies GitHub Actions state - run manually when needed")
    async def test_cancel_run_e2e(self, mock_user):
        """
        E2E test for gh_actions_cancel_run tool.

        CAUTION: This cancels a real workflow run.

        Validates:
        - Can cancel running workflow
        - Real GitHub API call succeeds
        - No mocked httpx
        """
        from code_indexer.server.mcp.handlers import (
            handle_gh_actions_list_runs,
            handle_gh_actions_cancel_run,
        )

        # Find a running or queued run
        list_args = {
            "repository": self.TEST_REPOSITORY,
            "limit": 10,
        }
        list_result = await handle_gh_actions_list_runs(list_args, mock_user)

        active_runs = [
            r for r in list_result["runs"]
            if r["status"] in ("queued", "in_progress")
        ]

        if not active_runs:
            pytest.skip("No active workflow runs available for cancellation")

        run_id = active_runs[0]["id"]

        # Cancel the run
        cancel_args = {
            "repository": self.TEST_REPOSITORY,
            "run_id": run_id,
        }

        result = await handle_gh_actions_cancel_run(cancel_args, mock_user)

        assert result["success"] is True
        assert result["run_id"] == run_id
        assert "message" in result
