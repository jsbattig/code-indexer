"""Repository Management Client for CIDX Remote Operations.

Handles repository discovery, browsing, and status operations
with clean API abstractions for repository management commands.
"""

import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field

from .base_client import CIDXRemoteAPIClient, APIClientError

# Import for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..remote.sync_execution import SyncJobResult


class ActivatedRepository(BaseModel):
    """Model for an activated repository."""

    alias: str = Field(..., description="Repository alias")
    current_branch: str = Field(..., description="Current active branch")
    sync_status: str = Field(..., description="Synchronization status")
    last_sync: str = Field(..., description="Last synchronization timestamp")
    activation_date: str = Field(..., description="Repository activation timestamp")
    conflict_details: Optional[str] = Field(None, description="Conflict details if any")


class GoldenRepository(BaseModel):
    """Model for a golden repository."""

    alias: str = Field(..., description="Repository alias")
    description: str = Field(..., description="Repository description")
    default_branch: str = Field(..., description="Default branch name")
    indexed_branches: List[str] = Field(..., description="List of indexed branches")
    is_activated: bool = Field(
        ..., description="Whether repository is activated by user"
    )
    last_updated: str = Field(..., description="Last update timestamp")


class DiscoveredRepository(BaseModel):
    """Model for a discovered repository."""

    name: str = Field(..., description="Repository name")
    url: str = Field(..., description="Repository URL")
    description: str = Field(..., description="Repository description")
    is_available: bool = Field(
        ..., description="Whether repository is already available"
    )
    is_accessible: bool = Field(..., description="Whether repository is accessible")
    default_branch: str = Field(..., description="Default branch name")
    last_updated: str = Field(..., description="Last update timestamp")


class RepositoryDiscoveryResult(BaseModel):
    """Model for repository discovery results."""

    discovered_repositories: List[DiscoveredRepository] = Field(
        ..., description="List of discovered repositories"
    )
    source: str = Field(..., description="Discovery source")
    total_discovered: int = Field(
        ..., description="Total number of discovered repositories"
    )
    access_errors: List[str] = Field(..., description="List of access errors")


class ActivatedRepositorySummary(BaseModel):
    """Summary information for activated repositories."""

    total_count: int = Field(..., description="Total activated repositories")
    synced_count: int = Field(..., description="Number of synced repositories")
    needs_sync_count: int = Field(
        ..., description="Number of repositories needing sync"
    )
    conflict_count: int = Field(
        ..., description="Number of repositories with conflicts"
    )
    recent_activations: List[Dict[str, Any]] = Field(
        ..., description="Recently activated repositories"
    )


class AvailableRepositorySummary(BaseModel):
    """Summary information for available repositories."""

    total_count: int = Field(..., description="Total available repositories")
    not_activated_count: int = Field(
        ..., description="Number of repositories not activated"
    )


class RecentActivity(BaseModel):
    """Recent repository activity information."""

    recent_syncs: List[Dict[str, Any]] = Field(
        ..., description="Recent synchronizations"
    )


class RepositoryStatusSummary(BaseModel):
    """Comprehensive repository status summary."""

    activated_repositories: ActivatedRepositorySummary = Field(
        ..., description="Activated repositories summary"
    )
    available_repositories: AvailableRepositorySummary = Field(
        ..., description="Available repositories summary"
    )
    recent_activity: RecentActivity = Field(
        ..., description="Recent activity information"
    )
    recommendations: List[str] = Field(..., description="Actionable recommendations")


class ReposAPIClient(CIDXRemoteAPIClient):
    """Client for repository management operations via CIDX Remote API."""

    async def list_activated_repositories(
        self, filter_pattern: Optional[str] = None
    ) -> List[ActivatedRepository]:
        """List user's activated repositories.

        Args:
            filter_pattern: Optional filter pattern for repository names

        Returns:
            List of activated repositories

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        params = {}
        if filter_pattern:
            params["filter"] = filter_pattern

        response = await self._authenticated_request("GET", "/api/repos", params=params)

        if response.status_code == 200:
            try:
                response_data = response.json()
                repositories_data = response_data["repositories"]

                # Map server ActivatedRepositoryInfo format to client ActivatedRepository format
                mapped_repositories = []
                for repo_data in repositories_data:
                    mapped_repo = ActivatedRepository(
                        alias=repo_data["user_alias"],
                        current_branch=repo_data["current_branch"],
                        sync_status="synced",  # Default status - server doesn't provide this yet
                        last_sync=repo_data.get("last_accessed", ""),
                        activation_date=repo_data.get("activated_at", ""),
                        conflict_details=None,  # Server doesn't provide this yet
                    )
                    mapped_repositories.append(mapped_repo)

                return mapped_repositories
            except (KeyError, TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to list repositories: {error_detail}", response.status_code
            )

    async def list_available_repositories(
        self, search_term: Optional[str] = None
    ) -> List[GoldenRepository]:
        """List available golden repositories.

        Args:
            search_term: Optional search term for repository descriptions/aliases

        Returns:
            List of available golden repositories

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        params = {}
        if search_term:
            params["search"] = search_term

        response = await self._authenticated_request(
            "GET", "/api/repos/available", params=params
        )

        if response.status_code == 200:
            try:
                response_data = response.json()
                repositories_data = response_data["repositories"]
                return [
                    GoldenRepository(**repo_data) for repo_data in repositories_data
                ]
            except (KeyError, TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to list available repositories: {error_detail}",
                response.status_code,
            )

    async def discover_repositories(self, source: str) -> RepositoryDiscoveryResult:
        """Discover repositories from remote sources.

        Args:
            source: Repository source (GitHub org, GitLab group, direct URL)

        Returns:
            Repository discovery results

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails or source is invalid
        """
        params = {"source": source}

        response = await self._authenticated_request(
            "GET", "/api/repos/discover", params=params
        )

        if response.status_code == 200:
            try:
                response_data = response.json()
                return RepositoryDiscoveryResult(**response_data)
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to discover repositories: {error_detail}", response.status_code
            )

    async def get_repository_status_summary(self) -> RepositoryStatusSummary:
        """Get comprehensive repository status summary.

        Returns:
            Repository status summary with statistics and recommendations

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        response = await self._authenticated_request("GET", "/api/repos/status")

        if response.status_code == 200:
            try:
                response_data = response.json()
                return RepositoryStatusSummary(**response_data)
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to get repository status: {error_detail}", response.status_code
            )

    async def activate_repository(
        self, golden_alias: str, user_alias: str, target_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Activate a golden repository for personal use.

        Args:
            golden_alias: The alias of the golden repository to activate
            user_alias: The alias to use for the activated repository
            target_branch: Optional branch to activate (defaults to repository default)

        Returns:
            Dictionary containing activation result with status and details

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails (409 for conflicts, 404 for not found, etc.)
        """
        request_data = {
            "golden_alias": golden_alias,
            "user_alias": user_alias,
            "target_branch": target_branch,
        }

        response = await self._authenticated_request(
            "POST", "/api/repos/activate", json=request_data
        )

        if response.status_code == 202:  # Accepted for async operation
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to activate repository: {error_detail}", response.status_code
            )

    async def deactivate_repository(
        self, user_alias: str, force: bool = False
    ) -> Dict[str, Any]:
        """Deactivate a personal repository.

        Args:
            user_alias: The alias of the repository to deactivate
            force: Whether to force deactivation even if there are conflicts

        Returns:
            Dictionary containing deactivation result with cleanup summary

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails (404 for not found, 409 for conflicts, etc.)
        """
        request_data = {"force": force}

        response = await self._authenticated_request(
            "DELETE", f"/api/repos/{user_alias}", json=request_data
        )

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to deactivate repository: {error_detail}", response.status_code
            )

    async def get_activation_progress(self, activation_id: str) -> Dict[str, Any]:
        """Get activation progress for monitoring.

        Args:
            activation_id: The ID of the activation to monitor

        Returns:
            Dictionary containing activation progress details

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails (404 for not found, etc.)
        """
        response = await self._authenticated_request(
            "GET", f"/api/repos/activation/{activation_id}/progress"
        )

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to get activation progress: {error_detail}",
                response.status_code,
            )

    async def get_repository_info(
        self,
        user_alias: str,
        branches: bool = False,
        health: bool = False,
        activity: bool = False,
    ) -> Dict[str, Any]:
        """Get detailed repository information.

        Args:
            user_alias: The alias of the repository to get information for
            branches: Whether to include detailed branch information
            health: Whether to include health monitoring information
            activity: Whether to include activity tracking information

        Returns:
            Dictionary containing comprehensive repository information

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails (404 for not found, etc.)
        """
        params = {}
        if branches:
            params["branches"] = "true"
        if health:
            params["health"] = "true"
        if activity:
            params["activity"] = "true"

        response = await self._authenticated_request(
            "GET", f"/api/repos/{user_alias}", params=params
        )

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to get repository information: {error_detail}",
                response.status_code,
            )

    async def switch_repository_branch(
        self, user_alias: str, branch_name: str, create: bool = False
    ) -> Dict[str, Any]:
        """Switch branch in activated repository.

        Args:
            user_alias: The alias of the repository to switch branches in
            branch_name: The name of the branch to switch to
            create: Whether to create the branch if it doesn't exist

        Returns:
            Dictionary containing branch switch operation results

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails (404 for not found, 409 for conflicts, etc.)
        """
        request_data = {"branch_name": branch_name, "create": create}

        response = await self._authenticated_request(
            "PUT", f"/api/repos/{user_alias}/branch", json=request_data
        )

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to switch repository branch: {error_detail}",
                response.status_code,
            )

    async def sync_repository(
        self,
        user_alias: str,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> "SyncJobResult":
        """Sync repository with its golden repository.

        Args:
            user_alias: The alias of the repository to sync
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            SyncJobResult with sync operation details

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        from ..remote.sync_execution import SyncJobResult

        sync_request = {
            "force_sync": force_sync,
            "incremental": incremental,
            "pull_remote": pull_remote,
            "timeout": timeout,
        }

        response = await self._authenticated_request(
            "POST", f"/api/repos/{user_alias}/sync", json=sync_request
        )

        if response.status_code == 202:
            try:
                data = response.json()
                return SyncJobResult(
                    job_id=data["job_id"],
                    status=data["status"],
                    message=data.get("message", "Sync job submitted successfully"),
                    repository=user_alias,
                    estimated_duration=data.get("estimated_duration"),
                    job_url=data.get("job_url"),
                )
            except (KeyError, TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to sync repository: {error_detail}",
                response.status_code,
            )

    async def sync_all_repositories(
        self,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> List["SyncJobResult"]:
        """Sync all activated repositories with their golden repositories.

        Args:
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            List of SyncJobResult for each repository

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        from ..remote.sync_execution import SyncJobResult

        # First get list of activated repositories
        repositories = await self.list_activated_repositories()

        if not repositories:
            return []

        # Submit sync job for each repository
        results = []
        for repo in repositories:
            try:
                result = await self.sync_repository(
                    user_alias=repo.alias,
                    force_sync=force_sync,
                    incremental=incremental,
                    pull_remote=pull_remote,
                    timeout=timeout,
                )
                results.append(result)
            except Exception as e:
                # Create error result for this repository
                error_result = SyncJobResult(
                    job_id="",
                    status="error",
                    message=f"Failed to sync {repo.alias}: {e}",
                    repository=repo.alias,
                )
                results.append(error_result)

        return results

    async def get_sync_status(self, user_alias: str) -> Dict[str, Any]:
        """Get sync status for specific repository.

        Args:
            user_alias: The alias of the repository to get status for

        Returns:
            Dictionary containing sync status information

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        response = await self._authenticated_request(
            "GET", f"/api/repos/{user_alias}/sync-status"
        )

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to get sync status: {error_detail}",
                response.status_code,
            )

    async def get_sync_status_all(self) -> Dict[str, Dict[str, Any]]:
        """Get sync status for all activated repositories.

        Returns:
            Dictionary mapping repository alias to sync status information

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If the request fails
        """
        response = await self._authenticated_request("GET", "/api/repos/sync-status")

        if response.status_code == 200:
            try:
                result: Dict[str, Dict[str, Any]] = response.json()
                return result
            except (TypeError, ValueError) as e:
                raise APIClientError(f"Invalid response format: {e}")
        else:
            error_detail = response.json().get("detail", f"HTTP {response.status_code}")
            raise APIClientError(
                f"Failed to get sync status: {error_detail}",
                response.status_code,
            )


class SyncReposAPIClient:
    """Synchronous wrapper for repository management operations.

    Provides synchronous access to repository management functionality
    for CLI commands that cannot use async/await.
    """

    def __init__(self, project_root: Path):
        """Initialize the synchronous repos client.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = project_root
        self._async_client: Optional["ReposAPIClient"] = None

    def _get_async_client(self) -> "ReposAPIClient":
        """Get or create async client instance."""
        if self._async_client is None:
            from ..remote.credential_manager import (
                load_encrypted_credentials,
                ProjectCredentialManager,
            )

            # Load remote configuration
            import json

            config_path = self.project_root / ".code-indexer" / ".remote-config"
            with open(config_path, "r") as f:
                remote_config = json.load(f)

            # Load and decrypt credentials
            encrypted_creds = load_encrypted_credentials(self.project_root)
            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_creds,
                remote_config["username"],
                str(self.project_root),
                remote_config["server_url"],
            )

            self._async_client = ReposAPIClient(
                server_url=remote_config["server_url"],
                credentials=decrypted_creds._asdict(),
                project_root=self.project_root,
            )

        return self._async_client

    def sync_repository(
        self,
        user_alias: str,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> "SyncJobResult":
        """Sync repository with its golden repository.

        Args:
            user_alias: The alias of the repository to sync
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            SyncJobResult with sync operation details
        """

        async def _sync() -> "SyncJobResult":
            client = self._get_async_client()
            try:
                return await client.sync_repository(
                    user_alias=user_alias,
                    force_sync=force_sync,
                    incremental=incremental,
                    pull_remote=pull_remote,
                    timeout=timeout,
                )
            finally:
                await client.close()

        return asyncio.run(_sync())

    def sync_all_repositories(
        self,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> List["SyncJobResult"]:
        """Sync all activated repositories with their golden repositories.

        Args:
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            List of SyncJobResult for each repository
        """

        async def _sync_all():
            client = self._get_async_client()
            try:
                return await client.sync_all_repositories(
                    force_sync=force_sync,
                    incremental=incremental,
                    pull_remote=pull_remote,
                    timeout=timeout,
                )
            finally:
                await client.close()

        return asyncio.run(_sync_all())

    def get_sync_status(self, user_alias: str) -> Dict[str, Any]:
        """Get sync status for specific repository.

        Args:
            user_alias: The alias of the repository to get status for

        Returns:
            Dictionary containing sync status information
        """

        async def _get_status():
            client = self._get_async_client()
            try:
                return await client.get_sync_status(user_alias)
            finally:
                await client.close()

        return asyncio.run(_get_status())

    def get_sync_status_all(self) -> Dict[str, Dict[str, Any]]:
        """Get sync status for all activated repositories.

        Returns:
            Dictionary mapping repository alias to sync status information
        """

        async def _get_status_all():
            client = self._get_async_client()
            try:
                return await client.get_sync_status_all()
            finally:
                await client.close()

        return asyncio.run(_get_status_all())
