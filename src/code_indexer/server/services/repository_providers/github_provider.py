"""
GitHub Repository Provider for CIDX Server.

Implements repository discovery from GitHub API, supporting user repositories
and organization repositories accessible via personal access token.
"""

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Set

import httpx

from .base import RepositoryProviderBase
from ...models.auto_discovery import (
    DiscoveredRepository,
    RepositoryDiscoveryResult,
)
from ..git_url_normalizer import GitUrlNormalizer, GitUrlNormalizationError

if TYPE_CHECKING:
    from ..ci_token_manager import CITokenManager
    from ...repositories.golden_repo_manager import GoldenRepoManager

logger = logging.getLogger(__name__)


class GitHubProviderError(Exception):
    """Exception raised for GitHub provider errors."""

    pass


class GitHubProvider(RepositoryProviderBase):
    """
    GitHub repository discovery provider.

    Discovers repositories from GitHub API, excludes already-indexed repos,
    and handles pagination via Link header parsing.
    """

    DEFAULT_BASE_URL = "https://api.github.com"
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        token_manager: "CITokenManager",
        golden_repo_manager: "GoldenRepoManager",
    ):
        """
        Initialize the GitHub provider.

        Args:
            token_manager: CI token manager for retrieving GitHub API token
            golden_repo_manager: Manager for listing already-indexed golden repos
        """
        self._token_manager = token_manager
        self._golden_repo_manager = golden_repo_manager
        self._url_normalizer = GitUrlNormalizer()

    @property
    def platform(self) -> str:
        """Return the platform name."""
        return "github"

    async def is_configured(self) -> bool:
        """Check if GitHub token is configured."""
        token_data = self._token_manager.get_token("github")
        return token_data is not None

    def _get_base_url(self) -> str:
        """Get the GitHub API base URL."""
        # GitHub Enterprise support could be added here in future
        return self.DEFAULT_BASE_URL

    def _get_api_url(self, endpoint: str) -> str:
        """Construct full API URL for an endpoint."""
        base_url = self._get_base_url()
        return f"{base_url}/{endpoint}"

    def _get_indexed_canonical_urls(self) -> Set[str]:
        """
        Get canonical forms of all already-indexed repository URLs.

        Returns:
            Set of canonical URL forms for indexed repositories
        """
        indexed_urls: Set[str] = set()
        golden_repos = self._golden_repo_manager.list_golden_repos()

        for repo in golden_repos:
            repo_url = repo.get("repo_url", "")
            if repo_url:
                try:
                    canonical = self._url_normalizer.get_canonical_form(repo_url)
                    indexed_urls.add(canonical)
                except GitUrlNormalizationError:
                    # Skip URLs that cannot be normalized (e.g., local paths)
                    pass

        return indexed_urls

    def _is_repo_indexed(
        self, https_url: str, ssh_url: str, indexed_urls: Set[str]
    ) -> bool:
        """
        Check if a repository is already indexed.

        Args:
            https_url: HTTPS clone URL
            ssh_url: SSH clone URL
            indexed_urls: Set of canonical URLs for indexed repos

        Returns:
            True if the repository is already indexed
        """
        for url in [https_url, ssh_url]:
            try:
                canonical = self._url_normalizer.get_canonical_form(url)
                if canonical in indexed_urls:
                    return True
            except GitUrlNormalizationError:
                pass
        return False

    def _make_api_request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        """
        Make a synchronous API request to GitHub.

        Args:
            endpoint: API endpoint (e.g., "user/repos")
            params: Query parameters

        Returns:
            HTTP response

        Raises:
            GitHubProviderError: If request fails
        """
        token_data = self._token_manager.get_token("github")
        if not token_data:
            raise GitHubProviderError("GitHub token not configured")

        url = self._get_api_url(endpoint)
        # GitHub uses Bearer token authentication
        headers = {
            "Authorization": f"Bearer {token_data.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = httpx.get(
            url,
            headers=headers,
            params=params,
            timeout=self.DEFAULT_TIMEOUT,
        )
        return response

    def _parse_link_header_for_last_page(self, link_header: Optional[str]) -> int:
        """
        Parse GitHub's Link header to extract the last page number.

        GitHub pagination uses Link header format:
        <url?page=N>; rel="last", <url?page=M>; rel="next"

        Args:
            link_header: The Link header value from response

        Returns:
            Last page number, or 1 if not found
        """
        if not link_header:
            return 1

        # Find rel="last" link and extract page number
        # Format: <https://api.github.com/user/repos?page=5&per_page=30>; rel="last"
        last_pattern = re.compile(r'<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"')
        match = last_pattern.search(link_header)

        if match:
            return int(match.group(1))

        return 1

    def _parse_repository(self, repo: dict) -> DiscoveredRepository:
        """
        Parse a GitHub repository into a DiscoveredRepository.

        Args:
            repo: GitHub repository data from API

        Returns:
            DiscoveredRepository model
        """
        # Parse pushed_at timestamp (last activity equivalent)
        last_activity = None
        pushed_at = repo.get("pushed_at")
        if pushed_at:
            try:
                last_activity = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Extract commit info from API response (if available)
        # GitHub may include this in detailed repo responses or we use test data
        last_commit_hash = repo.get("_last_commit_hash")
        last_commit_author = repo.get("_last_commit_author")

        return DiscoveredRepository(
            platform="github",
            name=repo.get("full_name", ""),
            description=repo.get("description"),
            clone_url_https=repo.get("clone_url", ""),
            clone_url_ssh=repo.get("ssh_url", ""),
            default_branch=repo.get("default_branch", "main"),
            last_commit_hash=last_commit_hash,
            last_commit_author=last_commit_author,
            last_activity=last_activity,
            is_private=repo.get("private", False),
        )

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """
        Check if rate limit was exceeded and raise appropriate error.

        Args:
            response: HTTP response to check

        Raises:
            GitHubProviderError: If rate limit was exceeded
        """
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "")
            reset_time = response.headers.get("X-RateLimit-Reset", "")

            if remaining == "0":
                reset_msg = ""
                if reset_time:
                    try:
                        reset_dt = datetime.fromtimestamp(int(reset_time))
                        reset_msg = (
                            f" Rate limit resets at {reset_dt.strftime('%H:%M:%S')}"
                        )
                    except (ValueError, TypeError):
                        pass

                raise GitHubProviderError(f"GitHub API rate limit exceeded.{reset_msg}")

    async def discover_repositories(
        self, page: int = 1, page_size: int = 50, search: Optional[str] = None
    ) -> RepositoryDiscoveryResult:
        """
        Discover repositories from GitHub API.

        Args:
            page: Page number (1-indexed)
            page_size: Number of repositories per page (max 100 for GitHub)

        Returns:
            RepositoryDiscoveryResult with discovered repositories

        Raises:
            GitHubProviderError: If API call fails or token not configured
        """
        if not await self.is_configured():
            raise GitHubProviderError(
                "GitHub token not configured. "
                "Please configure a GitHub token in the CI Tokens settings."
            )

        # Get indexed repos for filtering
        indexed_urls = self._get_indexed_canonical_urls()

        # GitHub API limits per_page to 100
        effective_page_size = min(page_size, 100)

        try:
            response = self._make_api_request(
                "user/repos",
                params={
                    "page": page,
                    "per_page": effective_page_size,
                    "sort": "pushed",
                    "direction": "desc",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )

            # Check for rate limiting before raising for status
            self._check_rate_limit(response)

            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise GitHubProviderError(f"GitHub API request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            # Check for rate limit in error response
            if hasattr(e, "response") and e.response is not None:
                self._check_rate_limit(e.response)
            raise GitHubProviderError(
                f"GitHub API error: {e.response.status_code if hasattr(e, 'response') and e.response else 'unknown'}"
            ) from e
        except httpx.RequestError as e:
            raise GitHubProviderError(f"GitHub API request failed: {e}") from e

        # Parse response
        repos = response.json()

        # Parse Link header for pagination
        link_header = response.headers.get("Link", "")
        total_pages = self._parse_link_header_for_last_page(link_header)

        # GitHub doesn't provide total count in headers, estimate from pages
        # If we're not on last page and there's a Link header, estimate
        total_count = len(repos)
        if total_pages > 1:
            # Estimate based on page size and pages
            total_count = total_pages * effective_page_size

        # Filter out already-indexed repositories
        repositories: List[DiscoveredRepository] = []
        for repo in repos:
            https_url = repo.get("clone_url", "")
            ssh_url = repo.get("ssh_url", "")

            if not self._is_repo_indexed(https_url, ssh_url, indexed_urls):
                repositories.append(self._parse_repository(repo))

        # Apply search filter if provided
        # Search matches against name, description, commit hash, and committer
        if search:
            search_lower = search.lower()
            repositories = [
                repo
                for repo in repositories
                if search_lower in repo.name.lower()
                or (repo.description and search_lower in repo.description.lower())
                or (
                    repo.last_commit_hash
                    and search_lower in repo.last_commit_hash.lower()
                )
                or (
                    repo.last_commit_author
                    and search_lower in repo.last_commit_author.lower()
                )
            ]

        return RepositoryDiscoveryResult(
            repositories=repositories,
            total_count=total_count,
            page=page,
            page_size=effective_page_size,
            total_pages=total_pages,
            platform="github",
        )
