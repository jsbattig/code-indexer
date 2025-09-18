"""Remote Status Display and Health Monitoring.

Provides comprehensive status information and health monitoring for remote mode,
including connection testing, credential validation, and repository staleness analysis.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timezone
import aiohttp
import asyncio

from .api_clients.repository_linking_client import (
    RepositoryNotFoundError,
)
from .remote.models import RepositoryStatus, StalenessInfo

if TYPE_CHECKING:
    from .remote.services.repository_service import RemoteRepositoryService


logger = logging.getLogger(__name__)


class RemoteStatusDisplayer:
    """Displays comprehensive remote mode status information."""

    def __init__(
        self,
        repository_service: "RemoteRepositoryService",
    ):
        """Initialize remote status displayer.

        Args:
            repository_service: Repository service for business logic
        """
        self.repository_service = repository_service

    async def display_status(
        self, local_repo_url: str, local_branch: str
    ) -> Dict[str, Any]:
        """Display comprehensive remote mode status information.

        Args:
            local_repo_url: Local repository URL for analysis
            local_branch: Local branch for analysis

        Returns:
            Status information dictionary
        """
        analysis = await self.repository_service.get_repository_analysis(
            local_repo_url, local_branch
        )
        return self._format_analysis_for_display(analysis)

    def _format_analysis_for_display(self, analysis) -> Dict[str, Any]:
        """Format repository analysis for display output.

        Args:
            analysis: RepositoryAnalysis object from service

        Returns:
            Formatted status information dictionary
        """
        return {
            "repositories": {
                "total": len(analysis.repositories),
                "active": analysis.active_repo.name if analysis.active_repo else None,
                "matching": [repo.name for repo in analysis.matching_repos],
                "non_matching": [repo.name for repo in analysis.non_matching_repos],
            },
            "staleness_summary": analysis.staleness_summary,
            "matching_repositories": [
                {
                    "name": repo.name,
                    "url": repo.url,
                    "is_active": repo.is_active,
                    "local_timestamp": repo.local_timestamp,
                    "remote_timestamp": repo.remote_timestamp,
                    "staleness_info": repo.staleness_info,
                }
                for repo in analysis.matching_repos
            ],
        }

    async def get_repository_status(self, repository_alias: str) -> Any:
        """Get status for a specific repository.

        Args:
            repository_alias: Repository alias to get status for

        Returns:
            Repository status information from server

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network operation fails
            RepositoryNotFoundError: If repository is not found
            APIClientError: If API request fails
        """
        details = await self.repository_service.get_repository_details(repository_alias)
        if details:
            return RepositoryStatus(
                repository_alias=repository_alias,
                status=details.get("status", "unknown"),
                last_updated=details.get(
                    "last_updated", datetime.now(timezone.utc).isoformat()
                ),
                branch=details.get("branch"),
                commit_count=details.get("commit_count"),
                last_commit_sha=details.get("last_commit_sha"),
                indexing_progress=details.get("indexing_progress"),
            )
        else:
            raise RepositoryNotFoundError(f"Repository {repository_alias} not found")

    async def check_staleness(self, local_timestamp: str, repository_alias: str) -> Any:
        """Check if repository is stale compared to remote.

        Args:
            local_timestamp: Local repository timestamp
            repository_alias: Repository alias to check

        Returns:
            Staleness information with real timestamp comparison

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network operation fails
            RepositoryNotFoundError: If repository is not found
            APIClientError: If API request fails
        """
        details = await self.repository_service.get_repository_details(repository_alias)
        if details and details.get("last_updated"):
            remote_timestamp = details.get("last_updated")
            if remote_timestamp is not None:
                is_stale = self._compare_timestamps(local_timestamp, remote_timestamp)
            else:
                raise RepositoryNotFoundError(
                    f"Repository {repository_alias} missing timestamp information"
                )

            return StalenessInfo(
                is_stale=is_stale,
                local_timestamp=local_timestamp,
                remote_timestamp=remote_timestamp,
                repository_alias=repository_alias,
                last_commit_sha=details.get("last_commit_sha"),
                branch=details.get("branch"),
            )
        else:
            raise RepositoryNotFoundError(
                f"Repository {repository_alias} not found or missing timestamp"
            )

    def _compare_timestamps(self, local_timestamp: str, remote_timestamp: str) -> bool:
        """Compare local and remote timestamps to determine staleness.

        Args:
            local_timestamp: Local repository timestamp (ISO format)
            remote_timestamp: Remote repository timestamp (ISO format)

        Returns:
            True if local is stale (remote is newer), False otherwise

        Raises:
            ValueError: If timestamp format is invalid
        """
        try:
            # Parse timestamps
            local_dt = datetime.fromisoformat(local_timestamp.replace("Z", "+00:00"))
            remote_dt = datetime.fromisoformat(remote_timestamp.replace("Z", "+00:00"))

            # Ensure both timestamps are timezone-aware
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=timezone.utc)
            if remote_dt.tzinfo is None:
                remote_dt = remote_dt.replace(tzinfo=timezone.utc)

            # Local is stale if remote is newer
            return remote_dt > local_dt

        except ValueError as e:
            raise ValueError(f"Invalid timestamp format: {e}")
        except Exception as e:
            raise ValueError(f"Error comparing timestamps: {e}")


class RemoteConnectionHealthChecker:
    """Tests and monitors remote connection health."""

    def __init__(self, remote_config: Dict[str, Any]):
        """Initialize connection health checker.

        Args:
            remote_config: Remote configuration dictionary
        """
        self.remote_config = remote_config
        self.server_url = remote_config.get("server_url")
        self.encrypted_credentials = remote_config.get("encrypted_credentials")

    async def check_connection_health(self) -> Dict[str, Any]:
        """Test various aspects of remote connection health.

        Returns:
            Dictionary containing health check results
        """
        health_results = {
            "server_reachable": False,
            "authentication_valid": False,
            "repository_accessible": False,
            "connection_health": "unknown",
        }

        try:
            # Test basic server connectivity
            async with aiohttp.ClientSession() as session:
                health_url = f"{self.server_url}/health"

                try:
                    async with session.get(health_url, timeout=10) as response:
                        health_results["server_reachable"] = True

                        if response.status == 200:
                            health_results["connection_health"] = "healthy"
                            health_results["authentication_valid"] = True
                            health_results["repository_accessible"] = True
                        elif response.status == 401:
                            health_results["connection_health"] = (
                                "authentication_failed"
                            )
                            health_results["authentication_valid"] = False
                        elif response.status == 403:
                            health_results["connection_health"] = (
                                "repository_access_denied"
                            )
                            health_results["authentication_valid"] = True
                            health_results["repository_accessible"] = False
                        else:
                            health_results["connection_health"] = "server_error"

                except asyncio.TimeoutError:
                    health_results["connection_health"] = "timeout"
                except aiohttp.ClientError:
                    health_results["connection_health"] = "connection_error"

        except ConnectionError:
            health_results["connection_health"] = "server_unreachable"
        except Exception as e:
            logger.warning(f"Unexpected error during health check: {e}")
            health_results["connection_health"] = "unexpected_error"

        return health_results


class RepositoryStalenessAnalyzer:
    """Analyzes repository staleness and provides guidance."""

    def __init__(self, project_root: Path, remote_config: Dict[str, Any]):
        """Initialize repository staleness analyzer.

        Args:
            project_root: Path to the project root directory
            remote_config: Remote configuration dictionary
        """
        self.project_root = project_root
        self.remote_config = remote_config
        self.repository_link = remote_config.get("repository_link", {})

    async def analyze_staleness(self) -> Dict[str, Any]:
        """Analyze repository staleness and local vs remote differences.

        Returns:
            Dictionary containing staleness analysis results
        """
        staleness_results = {
            "local_branch": None,
            "remote_branch": self.repository_link.get("branch"),
            "uncommitted_changes": False,
            "staleness_status": "unknown",
        }

        try:
            # Check if this is a git repository
            git_dir = self.project_root / ".git"
            if not git_dir.exists():
                staleness_results["staleness_status"] = "not_git_repository"
                return staleness_results

            # Use GitTopologyService if needed for future git analysis
            # git_service = GitTopologyService(self.project_root)

            # Get current branch
            current_branch = await self._get_current_branch()
            staleness_results["local_branch"] = current_branch

            # Check for uncommitted changes
            has_changes = await self._check_uncommitted_changes()
            staleness_results["uncommitted_changes"] = has_changes

            # Determine staleness status
            if has_changes:
                staleness_results["staleness_status"] = "has_local_changes"
            elif current_branch != staleness_results["remote_branch"]:
                staleness_results["staleness_status"] = "branch_mismatch"
            else:
                staleness_results["staleness_status"] = "up_to_date"

        except Exception as e:
            logger.warning(f"Error analyzing repository staleness: {e}")
            staleness_results["staleness_status"] = "analysis_error"

        return staleness_results

    async def _get_current_branch(self) -> Optional[str]:
        """Get the current git branch name.

        Returns:
            Current branch name or None if not available
        """
        try:
            import subprocess

            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() or None
        except subprocess.CalledProcessError:
            return None

    async def _check_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes in the repository.

        Returns:
            True if there are uncommitted changes, False otherwise
        """
        try:
            import subprocess

            # Check for staged changes
            result_staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.project_root,
                capture_output=True,
            )

            # Check for unstaged changes
            result_unstaged = subprocess.run(
                ["git", "diff", "--quiet"], cwd=self.project_root, capture_output=True
            )

            # Check for untracked files
            result_untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )

            # If any command returns non-zero, there are changes
            has_staged = result_staged.returncode != 0
            has_unstaged = result_unstaged.returncode != 0
            has_untracked = bool(result_untracked.stdout.strip())

            return has_staged or has_unstaged or has_untracked

        except subprocess.CalledProcessError:
            return False
