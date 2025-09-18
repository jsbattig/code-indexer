"""Remote repository service for business logic operations."""

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
import logging

if TYPE_CHECKING:
    from ...api_clients.base_client import CIDXRemoteAPIClient
    from ..staleness_detector import StalenessDetector

logger = logging.getLogger(__name__)


@dataclass
class RepositoryInfo:
    """Repository information with metadata."""

    name: str
    url: str
    is_active: bool
    local_timestamp: Optional[str] = None
    remote_timestamp: Optional[str] = None
    staleness_info: Optional[Dict] = None


@dataclass
class RepositoryAnalysis:
    """Complete repository analysis results."""

    repositories: List[RepositoryInfo]
    active_repo: Optional[RepositoryInfo]
    matching_repos: List[RepositoryInfo]
    non_matching_repos: List[RepositoryInfo]
    staleness_summary: Dict


class RemoteRepositoryService:
    """Service for remote repository operations and analysis."""

    def __init__(
        self, api_client: "CIDXRemoteAPIClient", staleness_detector: "StalenessDetector"
    ):
        """Initialize service with dependencies.

        Args:
            api_client: CIDX Remote API client for server communication
            staleness_detector: Detector for staleness analysis
        """
        self.api_client = api_client
        self.staleness_detector = staleness_detector

    async def get_repository_analysis(
        self, local_repo_url: str, local_branch: str
    ) -> RepositoryAnalysis:
        """Get complete repository analysis including staleness.

        Args:
            local_repo_url: Local repository URL for matching
            local_branch: Local branch for analysis

        Returns:
            Complete repository analysis with staleness information
        """
        logger.debug(
            f"Starting repository analysis for {local_repo_url}:{local_branch}"
        )

        # Get repositories from server
        repositories_data = await self._fetch_repositories()

        # Convert to repository info objects
        repositories = [
            RepositoryInfo(
                name=repo["name"], url=repo["url"], is_active=repo["is_active"]
            )
            for repo in repositories_data
        ]

        # Find active repository
        active_repo = next((repo for repo in repositories if repo.is_active), None)

        # Separate matching and non-matching repositories
        matching_repos, non_matching_repos = self._categorize_repositories(
            repositories, local_repo_url
        )

        # Calculate staleness for matching repositories
        await self._calculate_staleness_for_repos(matching_repos, local_branch)

        # Generate staleness summary
        staleness_summary = self._generate_staleness_summary(matching_repos)

        return RepositoryAnalysis(
            repositories=repositories,
            active_repo=active_repo,
            matching_repos=matching_repos,
            non_matching_repos=non_matching_repos,
            staleness_summary=staleness_summary,
        )

    async def _fetch_repositories(self) -> List[Dict]:
        """Fetch repositories from the server.

        Returns:
            List of repository dictionaries from server
        """
        try:
            response = await self.api_client.get("/repositories")
            if response.status_code == 200:
                data = response.json()
                return data.get("repositories", []) if isinstance(data, dict) else []
            else:
                logger.warning(f"Failed to fetch repositories: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching repositories: {e}")
            return []

    def _categorize_repositories(
        self, repositories: List[RepositoryInfo], local_repo_url: str
    ) -> Tuple[List[RepositoryInfo], List[RepositoryInfo]]:
        """Categorize repositories into matching and non-matching.

        Args:
            repositories: All repositories from server
            local_repo_url: Local repository URL for matching

        Returns:
            Tuple of (matching_repos, non_matching_repos)
        """
        matching_repos = []
        non_matching_repos = []

        for repo in repositories:
            if self._urls_match(repo.url, local_repo_url):
                matching_repos.append(repo)
            else:
                non_matching_repos.append(repo)

        return matching_repos, non_matching_repos

    def _urls_match(self, url1: str, url2: str) -> bool:
        """Check if two repository URLs represent the same repository.

        Args:
            url1: First repository URL
            url2: Second repository URL

        Returns:
            True if URLs represent the same repository
        """
        # Normalize URLs for comparison
        normalized_url1 = self._normalize_url(url1)
        normalized_url2 = self._normalize_url(url2)

        return normalized_url1 == normalized_url2

    def _normalize_url(self, url: str) -> str:
        """Normalize repository URL for comparison.

        Args:
            url: Repository URL to normalize

        Returns:
            Normalized URL
        """
        # Remove trailing slashes and .git suffix
        normalized = url.rstrip("/").rstrip(".git")

        # Convert SSH to HTTPS format for comparison
        if normalized.startswith("git@"):
            # Convert git@github.com:user/repo to https://github.com/user/repo
            parts = normalized.replace("git@", "").replace(":", "/")
            normalized = f"https://{parts}"

        return normalized.lower()

    async def _calculate_staleness_for_repos(
        self, repositories: List[RepositoryInfo], local_branch: str
    ):
        """Calculate staleness information for repositories.

        Args:
            repositories: Repositories to analyze
            local_branch: Local branch for staleness calculation
        """
        for repo in repositories:
            try:
                # Get timestamps for repository/branch
                timestamps = await self._get_repository_timestamps(
                    repo.name, local_branch
                )

                if timestamps:
                    repo.local_timestamp = timestamps.get("local_timestamp")
                    repo.remote_timestamp = timestamps.get("remote_timestamp")

                    # Calculate staleness
                    if repo.local_timestamp and repo.remote_timestamp:
                        # For now, use simple timestamp comparison
                        # TODO: Integrate with actual StalenessDetector methods
                        from datetime import datetime

                        try:
                            local_dt = datetime.fromisoformat(
                                repo.local_timestamp.replace("Z", "+00:00")
                            )
                            remote_dt = datetime.fromisoformat(
                                repo.remote_timestamp.replace("Z", "+00:00")
                            )
                            is_stale = remote_dt > local_dt
                        except (ValueError, AttributeError):
                            # Fallback to string comparison if datetime parsing fails
                            is_stale = repo.remote_timestamp > repo.local_timestamp

                        staleness_result = {
                            "is_stale": is_stale,
                            "local_timestamp": repo.local_timestamp,
                            "remote_timestamp": repo.remote_timestamp,
                        }
                        repo.staleness_info = staleness_result

            except Exception as e:
                logger.warning(f"Failed to calculate staleness for {repo.name}: {e}")

    async def _get_repository_timestamps(
        self, repo_name: str, branch: str
    ) -> Optional[Dict]:
        """Get timestamps for a repository/branch combination.

        Args:
            repo_name: Repository name
            branch: Branch name

        Returns:
            Dictionary with local and remote timestamps
        """
        try:
            response = await self.api_client.get(
                f"/repositories/{repo_name}/branches/{branch}/timestamps"
            )
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, dict) else None
            else:
                logger.debug(f"No timestamps found for {repo_name}:{branch}")
                return None
        except Exception as e:
            logger.warning(f"Error getting timestamps for {repo_name}:{branch}: {e}")
            return None

    def _generate_staleness_summary(self, repositories: List[RepositoryInfo]) -> Dict:
        """Generate summary of staleness analysis.

        Args:
            repositories: Repositories with staleness information

        Returns:
            Summary dictionary with staleness statistics
        """
        total_repos = len(repositories)
        stale_repos = []
        fresh_repos = []
        unknown_repos = []

        for repo in repositories:
            if repo.staleness_info:
                if repo.staleness_info.get("is_stale", False):
                    stale_repos.append(repo)
                else:
                    fresh_repos.append(repo)
            else:
                unknown_repos.append(repo)

        return {
            "total_repositories": total_repos,
            "stale_count": len(stale_repos),
            "fresh_count": len(fresh_repos),
            "unknown_count": len(unknown_repos),
            "stale_repositories": [repo.name for repo in stale_repos],
            "fresh_repositories": [repo.name for repo in fresh_repos],
            "unknown_repositories": [repo.name for repo in unknown_repos],
        }

    async def get_repository_details(self, repo_name: str) -> Optional[Dict]:
        """Get detailed information about a specific repository.

        Args:
            repo_name: Name of the repository

        Returns:
            Repository details or None if not found
        """
        try:
            response = await self.api_client.get(f"/repositories/{repo_name}")
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, dict) else None
            else:
                logger.warning(
                    f"Repository {repo_name} not found: {response.status_code}"
                )
                return None
        except Exception as e:
            logger.error(f"Error getting repository details for {repo_name}: {e}")
            return None

    async def get_repository_branches(self, repo_name: str) -> List[str]:
        """Get list of branches for a repository.

        Args:
            repo_name: Name of the repository

        Returns:
            List of branch names
        """
        try:
            response = await self.api_client.get(f"/repositories/{repo_name}/branches")
            if response.status_code == 200:
                data = response.json()
                return data.get("branches", []) if isinstance(data, dict) else []
            else:
                logger.warning(
                    f"Failed to get branches for {repo_name}: {response.status_code}"
                )
                return []
        except Exception as e:
            logger.error(f"Error getting branches for {repo_name}: {e}")
            return []
