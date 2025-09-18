"""Remote Sync Execution for CIDX Repository Sync.

Implements Story 10: Sync Command Structure that provides repository synchronization
through the CIDX server with job tracking and progress reporting.
"""

import logging
from pathlib import Path
from typing import List, Optional, Callable, Any, cast
from dataclasses import dataclass

from ..api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
)
from ..remote.credential_manager import (
    CredentialNotFoundError,
    CredentialDecryptionError,
)
from ..remote.repository_linking import (
    load_repository_link,
    RepositoryLinkingError,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncJobResult:
    """Result of a sync job submission."""

    job_id: str
    status: str
    message: str
    repository: str
    estimated_duration: Optional[float] = None
    job_url: Optional[str] = None


class RemoteSyncExecutionError(Exception):
    """Exception raised when remote sync execution fails."""

    pass


class RepositoryNotLinkedException(RemoteSyncExecutionError):
    """Exception raised when repository is not linked for sync."""

    pass


class SyncClient(CIDXRemoteAPIClient):
    """Client for repository synchronization operations."""

    async def sync_repository(
        self,
        repo_alias: str,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> SyncJobResult:
        """Submit repository sync job to server.

        Args:
            repo_alias: Repository alias to sync
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            SyncJobResult with job details

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
        """
        sync_request = {
            "force_sync": force_sync,
            "incremental": incremental,
            "pull_remote": pull_remote,
            "ignore_patterns": None,
        }

        endpoint = f"/api/repositories/{repo_alias}/sync"

        try:
            response = await self._authenticated_request(
                "POST", endpoint, json=sync_request, timeout=timeout
            )

            if response.status_code == 202:
                data = response.json()
                return SyncJobResult(
                    job_id=data["job_id"],
                    status=data["status"],
                    message=data.get("message", "Sync job submitted successfully"),
                    repository=repo_alias,
                    estimated_duration=data.get("estimated_duration"),
                    job_url=data.get("job_url"),
                )
            else:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except Exception:
                    error_detail = f"HTTP {response.status_code}"

                raise APIClientError(
                    f"Sync request failed: {error_detail}", response.status_code
                )

        except (NetworkError, AuthenticationError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise
            raise RemoteSyncExecutionError(f"Unexpected error during sync: {e}")

    async def sync_all_repositories(
        self,
        force_sync: bool = False,
        incremental: bool = True,
        pull_remote: bool = True,
        timeout: int = 300,
    ) -> List[SyncJobResult]:
        """Submit sync jobs for all activated repositories.

        Args:
            force_sync: Force sync by cancelling existing jobs
            incremental: Perform incremental sync for changed files only
            pull_remote: Pull from remote repository before sync
            timeout: Job timeout in seconds

        Returns:
            List of SyncJobResult for each repository

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
        """
        # First get list of activated repositories
        from ..api_clients.repository_linking_client import RepositoryLinkingClient

        linking_client = RepositoryLinkingClient(
            self.server_url, self.credentials, self.project_root
        )

        try:
            repositories = await linking_client.list_user_repositories()

            if not repositories:
                return []

            # Submit sync job for each repository
            results = []
            for repo in repositories:
                try:
                    result = await self.sync_repository(
                        repo_alias=repo.user_alias,
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
                        message=f"Failed to sync {repo.user_alias}: {e}",
                        repository=repo.user_alias,
                    )
                    results.append(error_result)

            return results

        finally:
            await linking_client.close()


async def execute_repository_sync(
    repository_alias: Optional[str],
    project_root: Path,
    sync_all: bool = False,
    full_reindex: bool = False,
    no_pull: bool = False,
    dry_run: bool = False,
    timeout: int = 300,
    enable_polling: bool = True,
    progress_callback: Optional[Callable] = None,
) -> List[SyncJobResult]:
    """Execute repository synchronization with the remote server.

    Args:
        repository_alias: Specific repository to sync (None for current)
        project_root: Project root directory
        sync_all: Sync all activated repositories
        full_reindex: Force full re-indexing instead of incremental
        no_pull: Skip git pull, only perform indexing
        dry_run: Show what would be synced without executing
        timeout: Job timeout in seconds
        enable_polling: Enable job polling for progress updates
        progress_callback: Callback for progress updates (current, total, path, info)

    Returns:
        List of sync job results

    Raises:
        RemoteSyncExecutionError: If sync execution fails
        RepositoryNotLinkedException: If repository is not linked
        CredentialNotFoundError: If credentials are not found
        AuthenticationError: If authentication fails
    """
    try:
        # Load remote configuration using same pattern as query execution
        remote_config_dict = _load_remote_configuration(project_root)

        # Load and decrypt credentials using same pattern as query execution
        decrypted_creds = _load_and_decrypt_credentials(project_root)

        # Create sync client
        sync_client = SyncClient(
            server_url=remote_config_dict["server_url"],
            credentials=decrypted_creds,
            project_root=project_root,
        )

        try:
            if dry_run:
                # For dry run, just return what would be synced
                if sync_all:
                    from ..api_clients.repository_linking_client import (
                        RepositoryLinkingClient,
                    )

                    linking_client = RepositoryLinkingClient(
                        remote_config_dict["server_url"], decrypted_creds, project_root
                    )

                    try:
                        repositories = await linking_client.list_user_repositories()
                        results = []
                        for repo in repositories:
                            results.append(
                                SyncJobResult(
                                    job_id="dry-run",
                                    status="would_sync",
                                    message=f"Would sync repository: {repo.user_alias}",
                                    repository=repo.user_alias,
                                )
                            )
                        return results
                    finally:
                        await linking_client.close()
                else:
                    # Determine repository to sync
                    if repository_alias:
                        repo_name = repository_alias
                    else:
                        # Try to get current repository link
                        try:
                            repo_link = load_repository_link(project_root)
                            if repo_link:
                                repo_name = repo_link.alias
                            else:
                                repo_name = "current"
                        except RepositoryLinkingError:
                            repo_name = "current"

                    return [
                        SyncJobResult(
                            job_id="dry-run",
                            status="would_sync",
                            message=f"Would sync repository: {repo_name}",
                            repository=repo_name,
                        )
                    ]

            # Execute actual sync
            if sync_all:
                results = await sync_client.sync_all_repositories(
                    force_sync=False,
                    incremental=not full_reindex,
                    pull_remote=not no_pull,
                    timeout=timeout,
                )
            else:
                # Determine repository to sync
                if repository_alias:
                    repo_name = repository_alias
                else:
                    # Try to get current repository link
                    try:
                        repo_link = load_repository_link(project_root)
                        if repo_link:
                            repo_name = repo_link.alias
                        else:
                            raise RepositoryNotLinkedException(
                                "Current directory is not linked to a remote repository. "
                                "Use 'cidx link' to link this repository or specify a repository alias."
                            )
                    except RepositoryLinkingError:
                        raise RepositoryNotLinkedException(
                            "Current directory is not linked to a remote repository. "
                            "Use 'cidx link' to link this repository or specify a repository alias."
                        )

                result = await sync_client.sync_repository(
                    repo_alias=repo_name,
                    force_sync=False,
                    incremental=not full_reindex,
                    pull_remote=not no_pull,
                    timeout=timeout,
                )

                results = [result]

            # Poll for job completion if enabled
            if enable_polling and progress_callback and not dry_run:
                await _poll_sync_jobs(sync_client, results, timeout, progress_callback)

            return results

        finally:
            await sync_client.close()

    except (
        CredentialNotFoundError,
        CredentialDecryptionError,
        AuthenticationError,
        NetworkError,
    ):
        raise
    except RepositoryNotLinkedException:
        raise
    except Exception as e:
        if isinstance(e, RemoteSyncExecutionError):
            raise
        raise RemoteSyncExecutionError(f"Sync execution failed: {e}")


async def _poll_sync_jobs(
    sync_client: "SyncClient",
    results: List[SyncJobResult],
    timeout: int,
    progress_callback: Callable,
) -> None:
    """Poll sync jobs for completion with progress updates.

    Args:
        sync_client: Sync client for API requests
        results: List of sync job results to poll
        timeout: Polling timeout in seconds
        progress_callback: Callback for progress updates
    """
    from .polling import JobPollingEngine, PollingConfig

    # Create polling configuration based on timeout
    polling_config = PollingConfig(
        base_interval=1.0,
        timeout=float(timeout),
        max_interval=10.0,
        network_retry_attempts=3,
    )

    # Poll each job
    for job_result in results:
        if job_result.job_id and job_result.status not in [
            "completed",
            "failed",
            "cancelled",
        ]:
            try:
                # Create polling engine for this job
                polling_engine = JobPollingEngine(
                    api_client=sync_client,
                    progress_callback=progress_callback,
                    config=polling_config,
                )

                # Start polling for this job with timeout
                final_status = await polling_engine.start_polling(
                    job_result.job_id, timeout
                )

                # Update result with final status
                job_result.status = final_status.status
                job_result.message = final_status.message

            except Exception as e:
                # Update job result with error
                job_result.status = "error"
                job_result.message = f"Polling failed: {e}"
                logger.error(f"Failed to poll job {job_result.job_id}: {e}")


def _load_remote_configuration(project_root: Path) -> dict[Any, Any]:
    """Load remote configuration from project directory.

    Args:
        project_root: Path to project root directory

    Returns:
        Remote configuration dictionary

    Raises:
        RemoteSyncExecutionError: If configuration cannot be loaded
    """
    import json

    config_path = project_root / ".code-indexer" / ".remote-config"

    if not config_path.exists():
        raise RemoteSyncExecutionError(
            f"Remote configuration not found at {config_path}. "
            "Please run 'cidx init --remote' to configure remote mode."
        )

    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # Validate required fields
        required_fields = ["server_url"]
        for field in required_fields:
            if field not in config_data:
                raise RemoteSyncExecutionError(
                    f"Invalid remote configuration: missing {field}"
                )

        return cast(dict[Any, Any], config_data)

    except json.JSONDecodeError as e:
        raise RemoteSyncExecutionError(f"Invalid remote configuration JSON: {e}")
    except Exception as e:
        raise RemoteSyncExecutionError(f"Failed to load remote configuration: {e}")


def _load_and_decrypt_credentials(project_root: Path) -> dict[Any, Any]:
    """Load and decrypt credentials from project directory.

    Args:
        project_root: Path to project root directory

    Returns:
        Decrypted credentials dictionary

    Raises:
        CredentialNotFoundError: If credentials are not found
        CredentialDecryptionError: If credentials cannot be decrypted
    """
    try:
        # Load encrypted credentials
        if not (project_root / ".code-indexer" / ".creds").exists():
            raise CredentialNotFoundError(
                f"Credentials file not found at {project_root / '.code-indexer' / '.creds'}. "
                "Please run 'cidx init --remote' to configure authentication."
            )

        # Load and decrypt credentials
        from ..remote.credential_manager import (
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Load remote configuration to get username and server_url
        remote_config = _load_remote_configuration(project_root)
        username = remote_config["username"]
        server_url = remote_config["server_url"]
        repo_path = str(project_root)

        encrypted_creds = load_encrypted_credentials(project_root)
        credential_manager = ProjectCredentialManager()
        decrypted_creds = credential_manager.decrypt_credentials(
            encrypted_creds, username, repo_path, server_url
        )

        return cast(dict[Any, Any], decrypted_creds._asdict())

    except Exception as e:
        if isinstance(e, (CredentialNotFoundError, CredentialDecryptionError)):
            raise
        raise CredentialNotFoundError(f"Failed to load credentials: {e}")
