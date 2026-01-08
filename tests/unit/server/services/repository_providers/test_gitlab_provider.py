"""
Tests for GitLabProvider.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for GitLab repository discovery.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestGitLabProviderConfiguration:
    """Tests for GitLabProvider configuration handling."""

    def test_provider_has_gitlab_platform(self):
        """Test that GitLabProvider reports gitlab as its platform."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )

        # Create provider with mock token manager
        token_manager = MagicMock()
        golden_repo_manager = MagicMock()
        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert provider.platform == "gitlab"

    @pytest.mark.asyncio
    async def test_is_configured_returns_true_when_token_exists(self):
        """Test is_configured returns True when GitLab token is configured."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert await provider.is_configured() is True

    @pytest.mark.asyncio
    async def test_is_configured_returns_false_when_no_token(self):
        """Test is_configured returns False when no GitLab token is configured."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )

        token_manager = MagicMock()
        token_manager.get_token.return_value = None
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert await provider.is_configured() is False

    @pytest.mark.asyncio
    async def test_uses_custom_base_url_when_provided(self):
        """Test that provider uses custom base URL for self-hosted GitLab."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url="https://gitlab.mycompany.com",
        )
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert provider._get_base_url() == "https://gitlab.mycompany.com"

    def test_default_base_url_is_gitlab_com(self):
        """Test that default base URL is gitlab.com."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert provider._get_base_url() == "https://gitlab.com"


class TestGitLabProviderDiscovery:
    """Tests for GitLabProvider repository discovery."""

    @pytest.mark.asyncio
    async def test_discover_repositories_returns_result_model(self):
        """Test that discover_repositories returns a RepositoryDiscoveryResult."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-total": "0", "x-total-pages": "0"}
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        assert isinstance(result, RepositoryDiscoveryResult)
        assert result.platform == "gitlab"

    @pytest.mark.asyncio
    async def test_discover_repositories_parses_gitlab_response(self):
        """Test that discover_repositories correctly parses GitLab API response."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock GitLab API response
        gitlab_projects = [
            {
                "id": 1,
                "name": "my-project",
                "path_with_namespace": "group/my-project",
                "description": "A test project",
                "http_url_to_repo": "https://gitlab.com/group/my-project.git",
                "ssh_url_to_repo": "git@gitlab.com:group/my-project.git",
                "default_branch": "main",
                "last_activity_at": "2024-01-15T10:30:00Z",
                "visibility": "private",
            }
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-total": "1", "x-total-pages": "1"}
        mock_response.json.return_value = gitlab_projects
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        assert len(result.repositories) == 1
        repo = result.repositories[0]
        assert repo.name == "group/my-project"
        assert repo.description == "A test project"
        assert repo.default_branch == "main"
        assert repo.clone_url_https == "https://gitlab.com/group/my-project.git"
        assert repo.clone_url_ssh == "git@gitlab.com:group/my-project.git"
        assert repo.is_private is True

    @pytest.mark.asyncio
    async def test_discover_repositories_handles_pagination(self):
        """Test that discover_repositories correctly handles pagination."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-total": "150", "x-total-pages": "3"}
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=2, page_size=50)

        assert result.total_count == 150
        assert result.total_pages == 3
        assert result.page == 2
        assert result.page_size == 50


class TestGitLabProviderExclusion:
    """Tests for GitLabProvider excluding already-indexed repositories."""

    @pytest.mark.asyncio
    async def test_excludes_already_indexed_repos_by_https_url(self):
        """Test that already-indexed repos are excluded using HTTPS URL matching."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        # This repo is already indexed
        golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "https://gitlab.com/group/already-indexed.git"}
        ]

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock GitLab API response with both indexed and new repos
        gitlab_projects = [
            {
                "id": 1,
                "name": "already-indexed",
                "path_with_namespace": "group/already-indexed",
                "description": "Already in golden repos",
                "http_url_to_repo": "https://gitlab.com/group/already-indexed.git",
                "ssh_url_to_repo": "git@gitlab.com:group/already-indexed.git",
                "default_branch": "main",
                "last_activity_at": "2024-01-15T10:30:00Z",
                "visibility": "private",
            },
            {
                "id": 2,
                "name": "new-project",
                "path_with_namespace": "group/new-project",
                "description": "Not yet indexed",
                "http_url_to_repo": "https://gitlab.com/group/new-project.git",
                "ssh_url_to_repo": "git@gitlab.com:group/new-project.git",
                "default_branch": "main",
                "last_activity_at": "2024-01-15T10:30:00Z",
                "visibility": "public",
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-total": "2", "x-total-pages": "1"}
        mock_response.json.return_value = gitlab_projects
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        # Should only return the new project
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "group/new-project"

    @pytest.mark.asyncio
    async def test_excludes_already_indexed_repos_by_ssh_url(self):
        """Test that already-indexed repos are excluded using SSH URL matching."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        # This repo is indexed via SSH URL
        golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "git@gitlab.com:group/already-indexed.git"}
        ]

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        gitlab_projects = [
            {
                "id": 1,
                "name": "already-indexed",
                "path_with_namespace": "group/already-indexed",
                "description": "Already in golden repos",
                "http_url_to_repo": "https://gitlab.com/group/already-indexed.git",
                "ssh_url_to_repo": "git@gitlab.com:group/already-indexed.git",
                "default_branch": "main",
                "last_activity_at": "2024-01-15T10:30:00Z",
                "visibility": "private",
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-total": "1", "x-total-pages": "1"}
        mock_response.json.return_value = gitlab_projects
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        # Should be filtered out
        assert len(result.repositories) == 0


class TestGitLabProviderSortingOrder:
    """Tests for GitLabProvider sorting by last activity descending."""

    @pytest.mark.asyncio
    async def test_api_request_uses_last_activity_sort_descending(self):
        """Test that API request sorts by last_activity_at in descending order."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Track the params passed to _make_api_request
        captured_params = {}

        def capture_request(endpoint, params=None):
            captured_params.update(params or {})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"x-total": "0", "x-total-pages": "0"}
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(provider, "_make_api_request", side_effect=capture_request):
            await provider.discover_repositories(page=1, page_size=50)

        # Verify sorting parameters are correct for last activity descending
        assert captured_params.get("order_by") == "last_activity_at", \
            f"Expected order_by='last_activity_at', got '{captured_params.get('order_by')}'"
        assert captured_params.get("sort") == "desc", \
            f"Expected sort='desc', got '{captured_params.get('sort')}'"


class TestGitLabProviderErrorHandling:
    """Tests for GitLabProvider error handling."""

    @pytest.mark.asyncio
    async def test_raises_error_when_not_configured(self):
        """Test that discover_repositories raises error when token not configured."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
            GitLabProviderError,
        )

        token_manager = MagicMock()
        token_manager.get_token.return_value = None
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        with pytest.raises(GitLabProviderError) as exc_info:
            await provider.discover_repositories(page=1, page_size=50)

        assert "not configured" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        """Test that provider handles GitLab API errors gracefully."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
            GitLabProviderError,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Simulate API error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            with pytest.raises(GitLabProviderError) as exc_info:
                await provider.discover_repositories(page=1, page_size=50)

        assert "api" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Test that provider handles request timeout."""
        from code_indexer.server.services.repository_providers.gitlab_provider import (
            GitLabProvider,
            GitLabProviderError,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="gitlab",
            token="glpat-test-token-123456789012",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitLabProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        with patch.object(
            provider,
            "_make_api_request",
            side_effect=httpx.TimeoutException("Connection timed out"),
        ):
            with pytest.raises(GitLabProviderError) as exc_info:
                await provider.discover_repositories(page=1, page_size=50)

        assert "timed out" in str(exc_info.value).lower()
