"""
Unit tests for GitLabCIClient retry logic.

Tests retry behavior with exponential backoff for network resilience.
Story #632: Network Error Handling - Retry Logic
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from code_indexer.server.clients.gitlab_ci_client import GitLabCIClient


class TestGitLabCIClientRetryLogic:
    """Test suite for retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_list_pipelines_retries_on_503_server_error(self):
        """
        Test that list_pipelines retries on 503 server error and succeeds after retry.

        AC1: Retry on 503 status code with exponential backoff
        """
        client = GitLabCIClient(token="test-token")

        # Create mock responses: first 503, then 200 success
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"message": "Service Temporarily Unavailable"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {
            "ratelimit-limit": "5000",
            "ratelimit-remaining": "4999",
            "ratelimit-reset": "1234567890",
        }
        success_response.json.return_value = [
            {
                "id": 123,
                "status": "success",
                "ref": "main",
                "created_at": "2024-01-01T00:00:00Z",
                "web_url": "https://gitlab.com/test/repo/pipelines/123",
            }
        ]

        # Mock httpx.AsyncClient to return error then success
        with patch(
            "code_indexer.server.clients.gitlab_ci_client.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [error_response, success_response]
            mock_client_class.return_value = mock_client

            # Call should succeed after retry
            pipelines = await client.list_pipelines(project_id="test/repo")

            # Verify we got the successful result
            assert len(pipelines) == 1
            assert pipelines[0]["id"] == 123
            assert pipelines[0]["status"] == "success"

            # Verify we made 2 requests (1 failed, 1 succeeded)
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_list_pipelines_retries_on_429_rate_limit(self):
        """
        Test that list_pipelines retries on 429 rate limit.

        AC2: Retry on 429 with exponential backoff
        """
        client = GitLabCIClient(token="test-token")

        # Create mock responses: first 429, then 200 success
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "2"}
        rate_limit_response.json.return_value = {"message": "API rate limit exceeded"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {
            "ratelimit-limit": "5000",
            "ratelimit-remaining": "4999",
            "ratelimit-reset": "1234567890",
        }
        success_response.json.return_value = [
            {
                "id": 456,
                "status": "running",
                "ref": "develop",
                "created_at": "2024-01-02T00:00:00Z",
                "web_url": "https://gitlab.com/test/repo/pipelines/456",
            }
        ]

        # Mock httpx.AsyncClient
        with patch(
            "code_indexer.server.clients.gitlab_ci_client.httpx.AsyncClient"
        ) as mock_client_class, patch(
            "asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [rate_limit_response, success_response]
            mock_client_class.return_value = mock_client

            # Call should succeed after retry
            pipelines = await client.list_pipelines(project_id="test/repo")

            # Verify we got the successful result
            assert len(pipelines) == 1
            assert pipelines[0]["id"] == 456

            # Verify we waited (at least one sleep call for retry backoff)
            assert mock_sleep.call_count >= 1

    @pytest.mark.asyncio
    async def test_list_pipelines_fails_after_max_retries(self):
        """
        Test that list_pipelines fails after maximum retry attempts (3 retries).

        AC3: Max 3 retry attempts before failing
        """
        client = GitLabCIClient(token="test-token")

        # Create mock response that always returns 503
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"message": "Service Unavailable"}

        # Mock httpx.AsyncClient to always return 503
        with patch(
            "code_indexer.server.clients.gitlab_ci_client.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # Return 503 for all 4 attempts (initial + 3 retries)
            mock_client.get.return_value = error_response
            mock_client_class.return_value = mock_client

            # Call should fail after max retries
            with pytest.raises(Exception) as exc_info:
                await client.list_pipelines(project_id="test/repo")

            # Verify exception is raised
            assert "503" in str(exc_info.value) or "error" in str(exc_info.value).lower()

            # Verify we made 4 attempts (1 initial + 3 retries)
            assert mock_client.get.call_count == 4

    @pytest.mark.asyncio
    async def test_list_pipelines_retries_on_network_error(self):
        """
        Test that list_pipelines retries on network errors and succeeds after retry.

        AC4: Retry on httpx.NetworkError
        """
        client = GitLabCIClient(token="test-token")

        # Create success response
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {
            "ratelimit-limit": "5000",
            "ratelimit-remaining": "4999",
            "ratelimit-reset": "1234567890",
        }
        success_response.json.return_value = [
            {
                "id": 789,
                "status": "failed",
                "ref": "feature",
                "created_at": "2024-01-03T00:00:00Z",
                "web_url": "https://gitlab.com/test/repo/pipelines/789",
            }
        ]

        # Mock httpx.AsyncClient to raise NetworkError then succeed
        with patch(
            "code_indexer.server.clients.gitlab_ci_client.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # First call raises NetworkError, second succeeds
            mock_client.get.side_effect = [
                httpx.NetworkError("Connection failed"),
                success_response,
            ]
            mock_client_class.return_value = mock_client

            # Call should succeed after retry
            pipelines = await client.list_pipelines(project_id="test/repo")

            # Verify we got the successful result
            assert len(pipelines) == 1
            assert pipelines[0]["id"] == 789
            assert pipelines[0]["status"] == "failed"

            # Verify we made 2 requests (1 failed with NetworkError, 1 succeeded)
            assert mock_client.get.call_count == 2
