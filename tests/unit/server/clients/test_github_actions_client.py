"""
Unit tests for GitHubActionsClient.

Story #633: Complete GitHub Actions Monitoring
Tests acceptance criteria for GitHub Actions API client using strict TDD.
"""

from unittest.mock import AsyncMock, Mock, patch
import pytest


class TestGitHubActionsClientListRuns:
    """Test AC1: List workflow runs with required fields."""

    @pytest.mark.asyncio
    async def test_list_runs_returns_workflow_runs_with_required_fields(self):
        """
        AC1: List recent workflow runs
        Given there are workflow runs in the repository
        When I call list_runs with repository "owner/repo"
        Then I receive a list of workflow runs with id, name, status, conclusion, branch, created_at
        """
        # This test will FAIL until GitHubActionsClient is implemented
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        # Mock httpx.AsyncClient response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # Empty headers for AC1-AC3 tests
        mock_response.json.return_value = {
            "workflow_runs": [
                {
                    "id": 12345,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "https://github.com/owner/repo/actions/runs/12345",
                }
            ]
        }

        # Mock async context manager for httpx.AsyncClient
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            runs = await client.list_runs(repository="owner/repo")

            assert len(runs) == 1
            assert runs[0]["id"] == 12345
            assert runs[0]["name"] == "CI"
            assert runs[0]["status"] == "completed"
            assert runs[0]["conclusion"] == "success"
            assert runs[0]["branch"] == "main"
            assert runs[0]["created_at"] == "2024-01-01T12:00:00Z"

    @pytest.mark.asyncio
    async def test_list_runs_filters_by_branch(self):
        """
        AC2: List workflow runs filtered by branch
        Given there are workflow runs on branches "main" and "feature-x"
        When I call list_runs with branch "main"
        Then I receive only runs from branch "main"
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # Empty headers for AC2 test
        mock_response.json.return_value = {
            "workflow_runs": [
                {
                    "id": 12345,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "created_at": "2024-01-01T12:00:00Z",
                }
            ]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            runs = await client.list_runs(repository="owner/repo", branch="main")

            # Verify API was called with branch filter in URL
            call_args = mock_client_instance.get.call_args
            assert call_args is not None
            url = call_args[0][0]
            assert "branch=main" in url

            assert len(runs) == 1
            assert runs[0]["branch"] == "main"

    @pytest.mark.asyncio
    async def test_list_runs_filters_by_status(self):
        """
        AC3: List workflow runs filtered by status
        Given there are runs with status "success", "failure", and "in_progress"
        When I call list_runs with status "failure"
        Then I receive only runs with conclusion "failure"
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # Empty headers for AC3 test
        mock_response.json.return_value = {
            "workflow_runs": [
                {
                    "id": 12345,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_branch": "main",
                    "created_at": "2024-01-01T12:00:00Z",
                }
            ]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            runs = await client.list_runs(repository="owner/repo", status="failure")

            # Verify API was called with status filter
            call_args = mock_client_instance.get.call_args
            url = call_args[0][0]
            assert "status=" in url

            assert len(runs) == 1
            assert runs[0]["conclusion"] == "failure"


class TestGitHubActionsClientGetRun:
    """Test AC4: Get detailed workflow run information."""

    @pytest.mark.asyncio
    async def test_get_run_returns_detailed_run_information(self):
        """
        AC4: Get detailed run information
        Given a workflow run ID exists
        When I call get_run with run_id
        Then I receive detailed run information including jobs, steps, and timing
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:05:00Z",
            "html_url": "https://github.com/owner/repo/actions/runs/12345",
            "jobs_url": "https://api.github.com/repos/owner/repo/actions/runs/12345/jobs",
            "run_started_at": "2024-01-01T12:00:30Z",
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            run_details = await client.get_run(repository="owner/repo", run_id=12345)

            # Verify correct API endpoint called
            call_args = mock_client_instance.get.call_args
            url = call_args[0][0]
            assert "/actions/runs/12345" in url

            # Verify returned detailed fields
            assert run_details["id"] == 12345
            assert run_details["name"] == "CI"
            assert run_details["status"] == "completed"
            assert run_details["conclusion"] == "success"
            assert run_details["branch"] == "main"
            assert run_details["created_at"] == "2024-01-01T12:00:00Z"
            assert run_details["updated_at"] == "2024-01-01T12:05:00Z"
            assert run_details["html_url"] == "https://github.com/owner/repo/actions/runs/12345"
            assert run_details["jobs_url"] == "https://api.github.com/repos/owner/repo/actions/runs/12345/jobs"
            assert run_details["run_started_at"] == "2024-01-01T12:00:30Z"


class TestGitHubActionsClientSearchLogs:
    """Test AC5: Search workflow run logs with ripgrep."""

    @pytest.mark.asyncio
    async def test_search_logs_finds_pattern_in_logs(self):
        """
        AC5: Search logs with ripgrep
        Given a workflow run has completed with logs
        When I call search_logs with run_id and pattern "error"
        Then I receive matching log lines with job context
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        # Mock jobs API response
        mock_jobs_response = Mock()
        mock_jobs_response.status_code = 200
        mock_jobs_response.json.return_value = {
            "jobs": [
                {
                    "id": 67890,
                    "name": "build",
                    "status": "completed",
                    "conclusion": "failure",
                }
            ]
        }

        # Mock logs API response (raw text)
        log_content = (
            "2024-01-01T12:01:00 Starting build\n"
            "2024-01-01T12:02:00 Error: compilation failed\n"
            "2024-01-01T12:03:00 Build completed with errors\n"
        )
        mock_logs_response = Mock(status_code=200, text=log_content)

        mock_client_instance = AsyncMock()

        # Configure mock to return responses in order: first jobs, then logs
        mock_client_instance.get.side_effect = [mock_jobs_response, mock_logs_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            matches = await client.search_logs(
                repository="owner/repo", run_id=12345, pattern="error"
            )

            # Verify we got matching lines
            assert len(matches) > 0
            assert any("Error: compilation failed" in match["line"] for match in matches)
            assert all("job_id" in match for match in matches)
            assert all("job_name" in match for match in matches)
            assert all("line_number" in match for match in matches)


class TestGitHubActionsClientGetJobLogs:
    """Test AC6: Get job logs."""

    @pytest.mark.asyncio
    async def test_get_job_logs_returns_job_log_output(self):
        """
        AC6: Get job logs
        Given a job ID exists for a workflow run
        When I call get_job_logs with job_id
        Then I receive the full log output for that job
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock(
            status_code=200,
            text=(
                "2024-01-01T12:01:00 Starting job\n"
                "2024-01-01T12:02:00 Running tests\n"
                "2024-01-01T12:03:00 All tests passed\n"
                "2024-01-01T12:04:00 Job completed successfully\n"
            )
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            log_output = await client.get_job_logs(
                repository="owner/repo", job_id=67890
            )

            # Verify correct API endpoint
            call_args = mock_client_instance.get.call_args
            url = call_args[0][0]
            assert "/jobs/67890/logs" in url

            # Verify log output returned
            assert "Starting job" in log_output
            assert "All tests passed" in log_output
            assert "Job completed successfully" in log_output


class TestGitHubActionsClientRetryRun:
    """Test AC7: Retry failed workflow run."""

    @pytest.mark.asyncio
    async def test_retry_run_retries_failed_workflow(self):
        """
        AC7: Retry workflow run
        Given a failed workflow run exists
        When I call retry_run with run_id
        Then the workflow is retried and I receive confirmation
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock(status_code=201)  # GitHub uses 201 for successful retry

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            result = await client.retry_run(repository="owner/repo", run_id=12345)

            # Verify correct API endpoint called with POST
            call_args = mock_client_instance.post.call_args
            url = call_args[0][0]
            assert "/actions/runs/12345/rerun" in url

            # Verify success confirmation
            assert result["success"] is True
            assert "run_id" in result
            assert result["run_id"] == 12345


class TestGitHubActionsClientCancelRun:
    """Test AC8: Cancel running workflow."""

    @pytest.mark.asyncio
    async def test_cancel_run_cancels_running_workflow(self):
        """
        AC8: Cancel workflow run
        Given a running workflow exists
        When I call cancel_run with run_id
        Then the workflow is cancelled and I receive confirmation
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock(status_code=202)  # GitHub uses 202 for successful cancel

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            result = await client.cancel_run(repository="owner/repo", run_id=12345)

            # Verify correct API endpoint called with POST
            call_args = mock_client_instance.post.call_args
            url = call_args[0][0]
            assert "/actions/runs/12345/cancel" in url

            # Verify success confirmation
            assert result["success"] is True
            assert "run_id" in result
            assert result["run_id"] == 12345


class TestGitHubActionsClientRateLimiting:
    """Test AC9: Rate limiting tracking in responses."""

    @pytest.mark.asyncio
    async def test_list_runs_includes_rate_limit_info(self):
        """
        AC9: Rate limiting tracking
        Given GitHub API response includes rate limit headers
        When I call list_runs
        Then the response includes rate_limit information
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {
                    "id": 12345,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "created_at": "2024-01-01T12:00:00Z",
                }
            ]
        }
        # GitHub rate limit headers
        mock_response.headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4999",
            "x-ratelimit-reset": "1704110400",
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")
            # Store rate limit in client instance
            runs = await client.list_runs(repository="owner/repo")

            # Verify rate limit is tracked (accessed via property)
            rate_limit = client.last_rate_limit
            assert rate_limit is not None
            assert rate_limit["limit"] == 5000
            assert rate_limit["remaining"] == 4999
            assert rate_limit["reset"] == 1704110400


class TestGitHubActionsClientAuthenticationErrors:
    """Test AC10: Authentication failure detection."""

    @pytest.mark.asyncio
    async def test_list_runs_raises_on_authentication_failure(self):
        """
        AC10: Authentication errors
        Given GitHub API returns 401 Unauthorized
        When I call list_runs
        Then a GitHubAuthenticationError is raised with guidance message
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
            GitHubAuthenticationError,
        )

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Bad credentials"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="invalid-token")

            with pytest.raises(GitHubAuthenticationError) as exc_info:
                await client.list_runs(repository="owner/repo")

            # Verify error message includes guidance
            error_msg = str(exc_info.value)
            assert "authentication failed" in error_msg.lower()
            assert "token" in error_msg.lower()


class TestGitHubActionsClientRepositoryNotFound:
    """Test AC11: Repository not found error handling."""

    @pytest.mark.asyncio
    async def test_list_runs_raises_on_repository_not_found(self):
        """
        AC11: Repository not found
        Given repository does not exist or is not accessible
        When I call list_runs with invalid repository
        Then a GitHubRepositoryNotFoundError is raised with helpful message
        """
        from code_indexer.server.clients.github_actions_client import (
            GitHubActionsClient,
            GitHubRepositoryNotFoundError,
        )

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            client = GitHubActionsClient(token="fake-token")

            with pytest.raises(GitHubRepositoryNotFoundError) as exc_info:
                await client.list_runs(repository="nonexistent/repo")

            # Verify error message includes repository name
            error_msg = str(exc_info.value)
            assert "repository" in error_msg.lower()
            assert "nonexistent/repo" in error_msg.lower()
