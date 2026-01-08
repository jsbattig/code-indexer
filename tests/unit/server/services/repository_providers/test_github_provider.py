"""
Tests for GitHubProvider.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for GitHub repository discovery.
"""

import pytest
from unittest.mock import MagicMock, patch
import httpx


class TestGitHubProviderConfiguration:
    """Tests for GitHubProvider configuration handling."""

    def test_provider_has_github_platform(self):
        """Test that GitHubProvider reports github as its platform."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )

        # Create provider with mock token manager
        token_manager = MagicMock()
        golden_repo_manager = MagicMock()
        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert provider.platform == "github"

    @pytest.mark.asyncio
    async def test_is_configured_returns_true_when_token_exists(self):
        """Test is_configured returns True when GitHub token is configured."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert await provider.is_configured() is True

    @pytest.mark.asyncio
    async def test_is_configured_returns_false_when_no_token(self):
        """Test is_configured returns False when no GitHub token is configured."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )

        token_manager = MagicMock()
        token_manager.get_token.return_value = None
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert await provider.is_configured() is False

    def test_default_base_url_is_github_api(self):
        """Test that default base URL is api.github.com."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        assert provider._get_base_url() == "https://api.github.com"


class TestGitHubProviderDiscovery:
    """Tests for GitHubProvider repository discovery."""

    @pytest.mark.asyncio
    async def test_discover_repositories_returns_result_model(self):
        """Test that discover_repositories returns a RepositoryDiscoveryResult."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}  # No Link header for single page
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        assert isinstance(result, RepositoryDiscoveryResult)
        assert result.platform == "github"

    @pytest.mark.asyncio
    async def test_discover_repositories_parses_github_response(self):
        """Test that discover_repositories correctly parses GitHub API response."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock GitHub API response
        github_repos = [
            {
                "id": 1,
                "name": "my-project",
                "full_name": "owner/my-project",
                "description": "A test project",
                "html_url": "https://github.com/owner/my-project",
                "clone_url": "https://github.com/owner/my-project.git",
                "ssh_url": "git@github.com:owner/my-project.git",
                "default_branch": "main",
                "pushed_at": "2024-01-15T10:30:00Z",
                "private": True,
            }
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = github_repos
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        assert len(result.repositories) == 1
        repo = result.repositories[0]
        assert repo.name == "owner/my-project"
        assert repo.description == "A test project"
        assert repo.default_branch == "main"
        assert repo.clone_url_https == "https://github.com/owner/my-project.git"
        assert repo.clone_url_ssh == "git@github.com:owner/my-project.git"
        assert repo.is_private is True

    @pytest.mark.asyncio
    async def test_discover_repositories_handles_pagination(self):
        """Test that discover_repositories correctly handles pagination."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock response with Link header for pagination
        mock_response = MagicMock()
        mock_response.status_code = 200
        # GitHub's Link header format with last page info
        mock_response.headers = {
            "Link": '<https://api.github.com/user/repos?page=3&per_page=50>; rel="last", '
            '<https://api.github.com/user/repos?page=3&per_page=50>; rel="next"'
        }
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=2, page_size=50)

        assert result.total_pages == 3
        assert result.page == 2
        assert result.page_size == 50


class TestGitHubProviderLinkHeaderParsing:
    """Tests for parsing GitHub's Link header for pagination."""

    def test_parse_link_header_extracts_last_page(self):
        """Test that Link header parsing correctly extracts last page number."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )

        token_manager = MagicMock()
        golden_repo_manager = MagicMock()
        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        link_header = (
            '<https://api.github.com/user/repos?page=1&per_page=30>; rel="prev", '
            '<https://api.github.com/user/repos?page=5&per_page=30>; rel="last"'
        )

        total_pages = provider._parse_link_header_for_last_page(link_header)
        assert total_pages == 5

    def test_parse_link_header_returns_1_when_no_last(self):
        """Test that Link header returns 1 when no last page."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )

        token_manager = MagicMock()
        golden_repo_manager = MagicMock()
        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Only prev, no last - means we're on the last page
        link_header = '<https://api.github.com/user/repos?page=1&per_page=30>; rel="prev"'

        total_pages = provider._parse_link_header_for_last_page(link_header)
        assert total_pages == 1

    def test_parse_link_header_handles_empty(self):
        """Test that empty Link header returns 1."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )

        token_manager = MagicMock()
        golden_repo_manager = MagicMock()
        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        total_pages = provider._parse_link_header_for_last_page("")
        assert total_pages == 1

        total_pages = provider._parse_link_header_for_last_page(None)
        assert total_pages == 1


class TestGitHubProviderExclusion:
    """Tests for GitHubProvider excluding already-indexed repositories."""

    @pytest.mark.asyncio
    async def test_excludes_already_indexed_repos_by_https_url(self):
        """Test that already-indexed repos are excluded using HTTPS URL matching."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        # This repo is already indexed
        golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "https://github.com/owner/already-indexed.git"}
        ]

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Mock GitHub API response with both indexed and new repos
        github_repos = [
            {
                "id": 1,
                "name": "already-indexed",
                "full_name": "owner/already-indexed",
                "description": "Already in golden repos",
                "clone_url": "https://github.com/owner/already-indexed.git",
                "ssh_url": "git@github.com:owner/already-indexed.git",
                "default_branch": "main",
                "pushed_at": "2024-01-15T10:30:00Z",
                "private": True,
            },
            {
                "id": 2,
                "name": "new-project",
                "full_name": "owner/new-project",
                "description": "Not yet indexed",
                "clone_url": "https://github.com/owner/new-project.git",
                "ssh_url": "git@github.com:owner/new-project.git",
                "default_branch": "main",
                "pushed_at": "2024-01-15T10:30:00Z",
                "private": False,
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = github_repos
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        # Should only return the new project
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/new-project"

    @pytest.mark.asyncio
    async def test_excludes_already_indexed_repos_by_ssh_url(self):
        """Test that already-indexed repos are excluded using SSH URL matching."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        # This repo is indexed via SSH URL
        golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "git@github.com:owner/already-indexed.git"}
        ]

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        github_repos = [
            {
                "id": 1,
                "name": "already-indexed",
                "full_name": "owner/already-indexed",
                "description": "Already in golden repos",
                "clone_url": "https://github.com/owner/already-indexed.git",
                "ssh_url": "git@github.com:owner/already-indexed.git",
                "default_branch": "main",
                "pushed_at": "2024-01-15T10:30:00Z",
                "private": True,
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = github_repos
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        # Should be filtered out
        assert len(result.repositories) == 0

    @pytest.mark.asyncio
    async def test_cross_platform_no_false_positives(self):
        """Test that GitLab repo doesn't exclude GitHub repo with same name."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        # GitLab repo with same name as GitHub repo
        golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "https://gitlab.com/owner/my-project.git"}
        ]

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # GitHub repo with same name should NOT be excluded
        github_repos = [
            {
                "id": 1,
                "name": "my-project",
                "full_name": "owner/my-project",
                "description": "GitHub version",
                "clone_url": "https://github.com/owner/my-project.git",
                "ssh_url": "git@github.com:owner/my-project.git",
                "default_branch": "main",
                "pushed_at": "2024-01-15T10:30:00Z",
                "private": False,
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = github_repos
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            result = await provider.discover_repositories(page=1, page_size=50)

        # GitHub repo should NOT be excluded - different host
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/my-project"


class TestGitHubProviderSortingOrder:
    """Tests for GitHubProvider sorting by last push descending."""

    @pytest.mark.asyncio
    async def test_api_request_uses_pushed_sort_descending(self):
        """Test that API request sorts by pushed (last push date) in descending order."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()
        golden_repo_manager.list_golden_repos.return_value = []

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Track the params passed to _make_api_request
        captured_params = {}

        def capture_request(endpoint, params=None):
            captured_params.update(params or {})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(provider, "_make_api_request", side_effect=capture_request):
            await provider.discover_repositories(page=1, page_size=50)

        # Verify sorting parameters are correct for last push descending
        assert captured_params.get("sort") == "pushed", \
            f"Expected sort='pushed', got '{captured_params.get('sort')}'"
        assert captured_params.get("direction") == "desc", \
            f"Expected direction='desc', got '{captured_params.get('direction')}'"


class TestGitHubProviderErrorHandling:
    """Tests for GitHubProvider error handling."""

    @pytest.mark.asyncio
    async def test_raises_error_when_not_configured(self):
        """Test that discover_repositories raises error when token not configured."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
            GitHubProviderError,
        )

        token_manager = MagicMock()
        token_manager.get_token.return_value = None
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        with pytest.raises(GitHubProviderError) as exc_info:
            await provider.discover_repositories(page=1, page_size=50)

        assert "not configured" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        """Test that provider handles GitHub API errors gracefully."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
            GitHubProviderError,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
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
            with pytest.raises(GitHubProviderError) as exc_info:
                await provider.discover_repositories(page=1, page_size=50)

        assert "api" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Test that provider handles request timeout."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
            GitHubProviderError,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        with patch.object(
            provider,
            "_make_api_request",
            side_effect=httpx.TimeoutException("Connection timed out"),
        ):
            with pytest.raises(GitHubProviderError) as exc_info:
                await provider.discover_repositories(page=1, page_size=50)

        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_rate_limit(self):
        """Test that provider handles GitHub rate limit response."""
        from code_indexer.server.services.repository_providers.github_provider import (
            GitHubProvider,
            GitHubProviderError,
        )
        from code_indexer.server.services.ci_token_manager import TokenData

        token_manager = MagicMock()
        token_manager.get_token.return_value = TokenData(
            platform="github",
            token="ghp_test123456789012345678901234567890",
            base_url=None,
        )
        golden_repo_manager = MagicMock()

        provider = GitHubProvider(
            token_manager=token_manager,
            golden_repo_manager=golden_repo_manager,
        )

        # Simulate rate limit response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1704067200"
        }
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "rate limit exceeded", request=MagicMock(), response=mock_response
        )

        with patch.object(provider, "_make_api_request", return_value=mock_response):
            with pytest.raises(GitHubProviderError) as exc_info:
                await provider.discover_repositories(page=1, page_size=50)

        # Should include rate limit info in error
        assert "rate limit" in str(exc_info.value).lower() or "api" in str(exc_info.value).lower()
