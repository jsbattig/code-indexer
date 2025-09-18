"""Test repository service async/await validation failures.

This test reproduces the exact async/await issues found in the repository service tests.
Following TDD methodology - write failing tests first, then fix the test patterns.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.code_indexer.remote.services.repository_service import (
    RemoteRepositoryService,
    RepositoryInfo,
)


class TestRepositoryServiceAsyncValidation:
    """Test cases to reproduce the async/await pattern failures."""

    @pytest.fixture
    def mock_api_client(self):
        """Create async mock API client."""
        return AsyncMock()

    @pytest.fixture
    def mock_staleness_detector(self):
        """Create mock staleness detector."""
        return Mock()

    @pytest.fixture
    def repository_service(self, mock_api_client, mock_staleness_detector):
        """Create repository service with mocks."""
        return RemoteRepositoryService(mock_api_client, mock_staleness_detector)

    def test_async_method_called_without_await_fails(
        self, repository_service, mock_api_client
    ):
        """Test that calling async methods without await fails (this should fail initially)."""
        # Setup repositories
        repositories = [
            RepositoryInfo("repo1", "https://github.com/user/repo1.git", True),
        ]

        # Setup mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "local_timestamp": "2024-01-01T10:00:00Z",
            "remote_timestamp": "2024-01-01T11:00:00Z",
        }
        mock_api_client.get.return_value = mock_response

        # This should fail because _calculate_staleness_for_repos is async but called without await
        try:
            # Calling async method without await should return a coroutine
            result = repository_service._calculate_staleness_for_repos(
                repositories, "main"
            )

            # If we get here, it means the method returned a coroutine instead of executing
            import inspect

            assert inspect.iscoroutine(result), "Expected coroutine object"

            # This should fail when trying to access repository attributes
            # because the async method didn't actually execute
            assert repositories[0].local_timestamp is None  # Should remain None

        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")

    @pytest.mark.asyncio
    async def test_async_method_called_with_await_succeeds(
        self, repository_service, mock_api_client
    ):
        """Test that calling async methods with await succeeds (this should pass after we understand the pattern)."""
        # Setup repositories
        repositories = [
            RepositoryInfo("repo1", "https://github.com/user/repo1.git", True),
        ]

        # Setup mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "local_timestamp": "2024-01-01T10:00:00Z",
            "remote_timestamp": "2024-01-01T11:00:00Z",
        }
        mock_api_client.get.return_value = mock_response

        # This should succeed with proper await
        await repository_service._calculate_staleness_for_repos(repositories, "main")

        # Verify the method actually executed and set timestamps
        assert repositories[0].local_timestamp == "2024-01-01T10:00:00Z"
        assert repositories[0].remote_timestamp == "2024-01-01T11:00:00Z"
        assert repositories[0].staleness_info is not None

    def test_non_async_method_called_normally_succeeds(self, repository_service):
        """Test that non-async methods work normally."""
        repositories = [
            RepositoryInfo("repo1", "https://github.com/user/repo1.git", True),
            RepositoryInfo("repo2", "https://github.com/user/repo2.git", False),
        ]
        local_repo_url = "git@github.com:user/repo1.git"

        # This should work normally (not async)
        matching, non_matching = repository_service._categorize_repositories(
            repositories, local_repo_url
        )

        # Verify results
        assert len(matching) == 1
        assert matching[0].name == "repo1"
        assert len(non_matching) == 1
