"""
Unit tests for GitLabCIClient.

Story #634: Complete GitLab CI Monitoring
Tests all acceptance criteria using TDD methodology.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

# Import will fail until we implement the client
# This is expected in TDD - write the test first
from code_indexer.server.clients.gitlab_ci_client import (
    GitLabCIClient,
    GitLabAuthenticationError,
    GitLabProjectNotFoundError,
)


class TestGitLabCIClient:
    """Test suite for GitLabCIClient."""

    @pytest.fixture
    def mock_token(self):
        """Provide test GitLab token."""
        return "glpat-test123456"

    @pytest.fixture
    def client(self, mock_token):
        """Create GitLabCIClient instance."""
        return GitLabCIClient(mock_token)

    # ===== AC1: List recent pipelines =====
    @pytest.mark.asyncio
    async def test_list_pipelines_returns_expected_fields(self, client):
        """
        AC1: List recent pipelines
        GIVEN there are pipelines in the project
        WHEN I call list_pipelines with project_id "namespace/project"
        THEN I receive a list of pipelines with id, status, ref, created_at, web_url
        """
        # Mock response from GitLab API
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ratelimit-limit": "2000",
            "ratelimit-remaining": "1950",
            "ratelimit-reset": "1735689600",
        }
        mock_response.json.return_value = [
            {
                "id": 12345,
                "status": "success",
                "ref": "main",
                "created_at": "2024-12-31T10:00:00.000Z",
                "web_url": "https://gitlab.com/namespace/project/-/pipelines/12345",
            },
            {
                "id": 12346,
                "status": "failed",
                "ref": "feature-x",
                "created_at": "2024-12-31T11:00:00.000Z",
                "web_url": "https://gitlab.com/namespace/project/-/pipelines/12346",
            },
        ]

        # Mock async context manager for httpx.AsyncClient
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            pipelines = await client.list_pipelines(project_id="namespace/project")

        # Verify expected fields present
        assert len(pipelines) == 2
        assert pipelines[0]["id"] == 12345
        assert pipelines[0]["status"] == "success"
        assert pipelines[0]["ref"] == "main"
        assert pipelines[0]["created_at"] == "2024-12-31T10:00:00.000Z"
        assert pipelines[0]["web_url"] == "https://gitlab.com/namespace/project/-/pipelines/12345"

    # ===== AC2: List pipelines filtered by branch =====
    @pytest.mark.asyncio
    async def test_list_pipelines_filtered_by_ref(self, client):
        """
        AC2: List pipelines filtered by branch
        GIVEN there are pipelines on branches "main" and "feature-x"
        WHEN I call list_pipelines with ref "main"
        THEN I receive only pipelines from branch "main"
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ratelimit-limit": "2000",
            "ratelimit-remaining": "1950",
            "ratelimit-reset": "1735689600",
        }
        mock_response.json.return_value = [
            {
                "id": 12345,
                "status": "success",
                "ref": "main",
                "created_at": "2024-12-31T10:00:00.000Z",
                "web_url": "https://gitlab.com/namespace/project/-/pipelines/12345",
            }
        ]

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            pipelines = await client.list_pipelines(project_id="namespace/project", ref="main")

        # Verify API was called with ref parameter
        call_args = mock_client_instance.get.call_args
        assert "ref=main" in call_args[0][0]

        # Verify only main branch pipelines returned
        assert len(pipelines) == 1
        assert pipelines[0]["ref"] == "main"

    # ===== AC3: List pipelines filtered by status =====
    @pytest.mark.asyncio
    async def test_list_pipelines_filtered_by_status(self, client):
        """
        AC3: List pipelines filtered by status
        GIVEN there are pipelines with status "success", "failed", and "running"
        WHEN I call list_pipelines with status "failed"
        THEN I receive only pipelines with status "failed"
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ratelimit-limit": "2000",
            "ratelimit-remaining": "1950",
            "ratelimit-reset": "1735689600",
        }
        mock_response.json.return_value = [
            {
                "id": 12346,
                "status": "failed",
                "ref": "feature-x",
                "created_at": "2024-12-31T11:00:00.000Z",
                "web_url": "https://gitlab.com/namespace/project/-/pipelines/12346",
            }
        ]

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            pipelines = await client.list_pipelines(project_id="namespace/project", status="failed")

        # Verify API was called with status parameter
        call_args = mock_client_instance.get.call_args
        assert "status=failed" in call_args[0][0]

        # Verify only failed pipelines returned
        assert len(pipelines) == 1
        assert pipelines[0]["status"] == "failed"

    # ===== AC4: Get detailed pipeline information =====
    @pytest.mark.asyncio
    async def test_get_pipeline_returns_detailed_info(self, client):
        """
        AC4: Get detailed pipeline information
        GIVEN a pipeline exists with id 12345
        WHEN I call get_pipeline with pipeline_id 12345
        THEN I receive detailed pipeline information including stages, jobs, duration, coverage, commit
        """
        # Mock main pipeline response
        pipeline_response = Mock()
        pipeline_response.status_code = 200
        pipeline_response.json.return_value = {
            "id": 12345,
            "status": "success",
            "ref": "main",
            "created_at": "2024-12-31T10:00:00.000Z",
            "updated_at": "2024-12-31T10:10:00.000Z",
            "web_url": "https://gitlab.com/namespace/project/-/pipelines/12345",
            "duration": 600,
            "coverage": "95.5",
            "sha": "abc123def456",
        }

        # Mock jobs response
        jobs_response = Mock()
        jobs_response.status_code = 200
        jobs_response.json.return_value = [
            {
                "id": 67890,
                "name": "test",
                "stage": "test",
                "status": "success",
                "created_at": "2024-12-31T10:01:00.000Z",
                "started_at": "2024-12-31T10:02:00.000Z",
                "finished_at": "2024-12-31T10:08:00.000Z",
            }
        ]

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = [pipeline_response, jobs_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            pipeline = await client.get_pipeline(project_id="namespace/project", pipeline_id=12345)

        # Verify all AC4 required fields present
        assert pipeline["id"] == 12345
        assert pipeline["status"] == "success"
        assert "jobs" in pipeline
        assert len(pipeline["jobs"]) == 1
        assert pipeline["jobs"][0]["stage"] == "test"
        assert pipeline["duration"] == 600
        assert pipeline["coverage"] == "95.5"
        assert pipeline["sha"] == "abc123def456"

    # ===== AC5: Search pipeline logs for error pattern =====
    @pytest.mark.asyncio
    async def test_search_logs_returns_matches_with_job_context(self, client):
        """
        AC5: Search pipeline logs for error pattern
        GIVEN a completed pipeline exists with job logs containing "ERROR: test failed"
        WHEN I call search_logs with pipeline_id and pattern "ERROR.*failed"
        THEN I receive matching log lines with context
        AND the search is performed server-side using ripgrep
        AND each match includes job name and stage
        """
        # Mock jobs response
        jobs_response = Mock()
        jobs_response.status_code = 200
        jobs_response.json.return_value = [
            {
                "id": 67890,
                "name": "test",
                "stage": "test",
            }
        ]

        # Mock job logs response
        logs_response = Mock()
        logs_response.status_code = 200
        logs_response.text = """Running tests...
Test case 1: PASS
ERROR: test failed on line 42
Test case 3: PASS
"""

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = [jobs_response, logs_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            matches = await client.search_logs(
                project_id="namespace/project",
                pipeline_id=12345,
                pattern="ERROR.*failed"
            )

        # Verify matches include required context
        assert len(matches) == 1
        assert matches[0]["job_id"] == 67890
        assert matches[0]["job_name"] == "test"
        assert matches[0]["stage"] == "test"
        assert "ERROR: test failed" in matches[0]["line"]
        assert matches[0]["line_number"] == 3

    # ===== Bug Fix: Case-sensitive/insensitive search =====
    @pytest.mark.asyncio
    async def test_search_logs_case_sensitive(self, client):
        """
        Test case-sensitive log search.
        GIVEN a job log contains "ERROR: Test Failed" (mixed case)
        WHEN I call search_logs with pattern "ERROR.*Failed" and case_sensitive=True
        THEN I receive matches with exact case
        AND pattern "error.*failed" (lowercase) does NOT match
        """
        # Mock jobs response
        jobs_response = Mock()
        jobs_response.status_code = 200
        jobs_response.json.return_value = [
            {
                "id": 67890,
                "name": "test",
                "stage": "test",
            }
        ]

        # Mock job logs response with mixed case
        logs_response = Mock()
        logs_response.status_code = 200
        logs_response.text = """Running tests...
ERROR: Test Failed on line 42
Test case 3: PASS
"""

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = [jobs_response, logs_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            # Case-sensitive match should succeed
            matches = await client.search_logs(
                project_id="namespace/project",
                pipeline_id=12345,
                pattern="ERROR.*Failed",
                case_sensitive=True
            )

        # Verify exact case match found
        assert len(matches) == 1
        assert "ERROR: Test Failed" in matches[0]["line"]

        # Reset mock for second test
        mock_client_instance.get.side_effect = [jobs_response, logs_response]

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            # Lowercase pattern should NOT match with case_sensitive=True
            matches_lowercase = await client.search_logs(
                project_id="namespace/project",
                pipeline_id=12345,
                pattern="error.*failed",
                case_sensitive=True
            )

        # Verify lowercase pattern did not match
        assert len(matches_lowercase) == 0

    @pytest.mark.asyncio
    async def test_search_logs_case_insensitive(self, client):
        """
        Test case-insensitive log search (default behavior).
        GIVEN a job log contains "ERROR: Test Failed" (mixed case)
        WHEN I call search_logs with pattern "error.*failed" (lowercase) and case_sensitive=False
        THEN I receive matches regardless of case
        """
        # Mock jobs response
        jobs_response = Mock()
        jobs_response.status_code = 200
        jobs_response.json.return_value = [
            {
                "id": 67890,
                "name": "test",
                "stage": "test",
            }
        ]

        # Mock job logs response with mixed case
        logs_response = Mock()
        logs_response.status_code = 200
        logs_response.text = """Running tests...
ERROR: Test Failed on line 42
Test case 3: PASS
"""

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = [jobs_response, logs_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            # Lowercase pattern should match mixed case with case_sensitive=False
            matches = await client.search_logs(
                project_id="namespace/project",
                pipeline_id=12345,
                pattern="error.*failed",
                case_sensitive=False
            )

        # Verify case-insensitive match found
        assert len(matches) == 1
        assert "ERROR: Test Failed" in matches[0]["line"]

    # ===== AC6: Get specific job logs =====
    @pytest.mark.asyncio
    async def test_get_job_logs_returns_complete_output(self, client):
        """
        AC6: Get specific job logs
        GIVEN a pipeline has a job named "test" with id 67890
        WHEN I call get_job_logs with job_id 67890
        THEN I receive the complete log output for that job
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """Running tests...
Test case 1: PASS
Test case 2: PASS
All tests passed!
"""

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            logs = await client.get_job_logs(project_id="namespace/project", job_id=67890)

        # Verify complete log output returned
        assert "Running tests..." in logs
        assert "Test case 1: PASS" in logs
        assert "All tests passed!" in logs

    # ===== AC7: Retry a failed pipeline =====
    @pytest.mark.asyncio
    async def test_retry_pipeline_returns_updated_status(self, client):
        """
        AC7: Retry a failed pipeline
        GIVEN a pipeline with id 12345 has status "failed"
        WHEN I call retry_pipeline with pipeline_id 12345
        THEN failed jobs are retried
        AND I receive the updated pipeline status
        """
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 12345,
            "status": "running",
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await client.retry_pipeline(project_id="namespace/project", pipeline_id=12345)

        # Verify retry succeeded
        assert result["success"] is True
        assert result["pipeline_id"] == 12345

    # ===== AC8: Cancel a running pipeline =====
    @pytest.mark.asyncio
    async def test_cancel_pipeline_stops_running_jobs(self, client):
        """
        AC8: Cancel a running pipeline
        GIVEN a pipeline with id 12345 has status "running"
        WHEN I call cancel_pipeline with pipeline_id 12345
        THEN the pipeline is cancelled
        AND all running jobs are stopped
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "status": "canceled",
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await client.cancel_pipeline(project_id="namespace/project", pipeline_id=12345)

        # Verify cancellation succeeded
        assert result["success"] is True
        assert result["pipeline_id"] == 12345

    # ===== AC9: Handle rate limiting =====
    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, client):
        """
        AC9: Handle rate limiting
        GIVEN the GitLab API rate limit is approaching
        WHEN I make a monitoring request
        THEN the response includes rate limit information
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ratelimit-limit": "2000",
            "ratelimit-remaining": "50",  # Low remaining
            "ratelimit-reset": "1735689600",
        }
        mock_response.json.return_value = []

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            await client.list_pipelines(project_id="namespace/project")

        # Verify rate limit captured
        rate_limit = client.last_rate_limit
        assert rate_limit is not None
        assert rate_limit["limit"] == 2000
        assert rate_limit["remaining"] == 50
        assert rate_limit["reset"] == 1735689600

    # ===== AC10: Handle authentication failure =====
    @pytest.mark.asyncio
    async def test_authentication_error_provides_guidance(self, client):
        """
        AC10: Handle authentication failure
        GIVEN an invalid GitLab token is configured
        WHEN I call any gitlab_ci tool
        THEN I receive an authentication error with guidance on token configuration
        """
        mock_response = Mock()
        mock_response.status_code = 401

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with pytest.raises(GitLabAuthenticationError) as exc_info:
                await client.list_pipelines(project_id="namespace/project")

        # Verify error message includes guidance
        error_message = str(exc_info.value)
        assert "token" in error_message.lower()
        assert "valid" in error_message.lower() or "configuration" in error_message.lower()

    # ===== AC11: Handle self-hosted GitLab =====
    @pytest.mark.asyncio
    async def test_self_hosted_gitlab_url(self, mock_token):
        """
        AC11: Handle self-hosted GitLab
        GIVEN a GitLab token for self-hosted instance at "https://gitlab.company.com"
        WHEN I call gitlab_ci tools with the configured instance URL
        THEN requests go to the self-hosted instance
        AND authentication works correctly
        """
        # Create client with custom base URL
        client = GitLabCIClient(mock_token, base_url="https://gitlab.company.com")

        assert client.base_url == "https://gitlab.company.com"

        # Verify URL construction uses custom base
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ratelimit-limit": "2000",
            "ratelimit-remaining": "1950",
            "ratelimit-reset": "1735689600",
        }
        mock_response.json.return_value = []

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            await client.list_pipelines(project_id="namespace/project")

        # Verify custom base URL was used
        call_args = mock_client_instance.get.call_args
        assert "https://gitlab.company.com" in call_args[0][0]

    # ===== Additional Error Handling =====
    @pytest.mark.asyncio
    async def test_project_not_found_error(self, client):
        """
        Test handling of project not found (404) errors.
        """
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with pytest.raises(GitLabProjectNotFoundError) as exc_info:
                await client.list_pipelines(project_id="invalid/project")

        # Verify error message includes project ID
        error_message = str(exc_info.value)
        assert "project" in error_message.lower() or "not found" in error_message.lower()
