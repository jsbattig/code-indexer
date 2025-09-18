"""Remote Operations Business Logic.

Clean business logic that uses API client abstractions with no raw HTTP calls.
All HTTP functionality is delegated to dedicated API client classes.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, cast

from ..remote.config import RemoteConfig
from ..remote.credential_manager import (
    CredentialNotFoundError,
    CredentialDecryptionError,
)

from ..api_clients import (
    RepositoryLinkingClient,
    RemoteQueryClient,
    QueryResultItem,
    RepositoryInfo,
    ActivatedRepository,
    RepositoryNotFoundError,
    BranchNotFoundError,
    ActivationError,
    QueryExecutionError,
    RepositoryAccessError,
    QueryLimitExceededError,
    AuthenticationError,
    NetworkError,
)

logger = logging.getLogger(__name__)


class RemoteOperationError(Exception):
    """Exception raised when remote operations fail."""

    pass


class RepositoryLinkingError(Exception):
    """Exception raised when repository linking operations fail."""

    pass


async def execute_remote_query(
    query: str,
    limit: int,
    project_root: Path,
    language_filter: Optional[str] = None,
    path_filter: Optional[str] = None,
    min_score: Optional[float] = None,
) -> List[QueryResultItem]:
    """Execute query in remote mode with no HTTP code here.

    Args:
        query: Search query text
        limit: Maximum number of results
        project_root: Path to project root directory
        language_filter: Optional language filter
        path_filter: Optional path pattern filter
        min_score: Optional minimum score threshold

    Returns:
        List of query result items

    Raises:
        RemoteOperationError: If remote operation fails
    """
    try:
        # Load remote configuration
        remote_config = _load_remote_configuration(project_root)

        # Extract repository alias from configuration
        repository_link = remote_config.get("repository_link")
        if not repository_link:
            raise RemoteOperationError("Repository not linked in remote configuration")

        repository_alias = repository_link.get("alias")
        if not repository_alias:
            raise RemoteOperationError("Repository alias not found in configuration")

        # Get decrypted credentials for API client
        credentials = _get_decrypted_credentials(project_root)
        server_url = remote_config["server_url"]

        async with RemoteQueryClient(
            server_url=server_url, credentials=credentials
        ) as client:
            # Execute query using API client abstraction
            results = await client.execute_query(
                repository_alias=repository_alias,
                query=query,
                limit=limit,
                language_filter=language_filter,
                path_filter=path_filter,
                min_score=min_score,
            )

            return cast(List[QueryResultItem], results)

    except (QueryExecutionError, RepositoryAccessError, QueryLimitExceededError) as e:
        raise RemoteOperationError(f"Query execution failed: {e}")
    except AuthenticationError as e:
        raise RemoteOperationError(f"Authentication failed: {e}")
    except NetworkError as e:
        raise RemoteOperationError(f"Network error: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Unexpected error during remote query: {e}")


async def discover_and_link_repository(
    git_url: str,
    branch: str,
    server_url: str,
    credentials: Dict[str, Any],
    project_root: Path,
) -> ActivatedRepository:
    """Discover and link repository with no HTTP code here.

    Args:
        git_url: Git repository URL to discover
        branch: Branch to activate
        server_url: CIDX server URL
        credentials: Authentication credentials
        project_root: Path to project root directory

    Returns:
        Activated repository information

    Raises:
        RepositoryLinkingError: If linking operation fails
    """
    try:
        async with RepositoryLinkingClient(
            server_url=server_url, credentials=credentials
        ) as client:
            # Discover repositories using API client abstraction
            discovery_response = await client.discover_repositories(git_url)

            if discovery_response.total_matches == 0:
                raise RepositoryLinkingError(
                    f"No repositories found for URL: {git_url}"
                )

            if discovery_response.total_matches > 1:
                raise RepositoryLinkingError(
                    f"Multiple repositories found for URL: {git_url}. "
                    f"Found {discovery_response.total_matches} matches."
                )

            # Get the single matching repository
            repository_match = discovery_response.matches[0]

            # Validate requested branch is available
            if branch not in repository_match.available_branches:
                available = ", ".join(repository_match.available_branches)
                raise RepositoryLinkingError(
                    f"Branch '{branch}' not available. Available branches: {available}"
                )

            # Generate user alias for activation
            user_alias = f"{repository_match.alias}-{credentials['username']}"

            # Activate repository using API client abstraction
            activated_repo = await client.activate_repository(
                golden_alias=repository_match.alias,
                branch=branch,
                user_alias=user_alias,
            )

            # Save linking information to local configuration
            _save_repository_link(
                project_root,
                activated_repo,
                git_url,
                server_url,
                credentials["username"],
            )

            return cast(ActivatedRepository, activated_repo)

    except (RepositoryNotFoundError, BranchNotFoundError, ActivationError) as e:
        raise RepositoryLinkingError(f"Repository linking failed: {e}")
    except AuthenticationError as e:
        raise RepositoryLinkingError(f"Authentication failed: {e}")
    except NetworkError as e:
        raise RepositoryLinkingError(f"Network error: {e}")
    except Exception as e:
        raise RepositoryLinkingError(f"Unexpected error during repository linking: {e}")


async def get_remote_repository_status(project_root: Path) -> RepositoryInfo:
    """Get remote repository status with no HTTP code here.

    Args:
        project_root: Path to project root directory

    Returns:
        Repository information

    Raises:
        RemoteOperationError: If status retrieval fails
    """
    try:
        # Load remote configuration
        remote_config = _load_remote_configuration(project_root)

        # Extract repository alias from configuration
        repository_link = remote_config.get("repository_link")
        if not repository_link:
            raise RemoteOperationError("Repository not linked in remote configuration")

        repository_alias = repository_link.get("alias")
        if not repository_alias:
            raise RemoteOperationError("Repository alias not found in configuration")

        # Get decrypted credentials for API client
        credentials = _get_decrypted_credentials(project_root)
        server_url = remote_config["server_url"]

        async with RemoteQueryClient(
            server_url=server_url, credentials=credentials
        ) as client:
            # Get repository info using API client abstraction
            repo_info = await client.get_repository_info(repository_alias)

            return cast(RepositoryInfo, repo_info)

    except RepositoryAccessError as e:
        raise RemoteOperationError(f"Repository access denied: {e}")
    except AuthenticationError as e:
        raise RemoteOperationError(f"Authentication failed: {e}")
    except NetworkError as e:
        raise RemoteOperationError(f"Network error: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Unexpected error getting repository status: {e}")


def _load_remote_configuration(project_root: Path) -> Dict[str, Any]:
    """Load remote configuration from project directory.

    Args:
        project_root: Path to project root directory

    Returns:
        Remote configuration dictionary

    Raises:
        RemoteOperationError: If configuration cannot be loaded
    """
    config_path = project_root / ".code-indexer" / ".remote-config"

    if not config_path.exists():
        raise RemoteOperationError(f"Remote configuration not found at {config_path}")

    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # Validate required fields
        required_fields = ["server_url", "username"]
        for field in required_fields:
            if field not in config_data:
                raise RemoteOperationError(
                    f"Invalid remote configuration: missing {field}"
                )

        return cast(Dict[str, Any], config_data)

    except json.JSONDecodeError as e:
        raise RemoteOperationError(f"Invalid remote configuration JSON: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Failed to load remote configuration: {e}")


def _get_decrypted_credentials(project_root: Path) -> Dict[str, Any]:
    """Get decrypted credentials for API client usage.

    Args:
        project_root: Path to project root directory

    Returns:
        Dictionary with username, password, and server_url

    Raises:
        RemoteOperationError: If credentials cannot be decrypted
    """
    try:
        remote_config = RemoteConfig(project_root)
        decrypted_creds = remote_config.get_decrypted_credentials()

        credentials_dict: Dict[str, Any] = {
            "username": decrypted_creds.username,
            "password": decrypted_creds.password,
            "server_url": decrypted_creds.server_url,
        }
        return credentials_dict

    except CredentialNotFoundError:
        raise RemoteOperationError(
            "No encrypted credentials found. Please run 'cidx init remote' first."
        )
    except CredentialDecryptionError as e:
        raise RemoteOperationError(f"Failed to decrypt credentials: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Failed to load credentials: {e}")


def _save_repository_link(
    project_root: Path,
    activated_repo: ActivatedRepository,
    git_url: str,
    server_url: str,
    username: str,
) -> None:
    """Save repository linking information to local configuration.

    Args:
        project_root: Path to project root directory
        activated_repo: Activated repository information
        git_url: Original git URL
        server_url: CIDX server URL
        username: Username for configuration

    Raises:
        RemoteOperationError: If configuration cannot be saved
    """
    try:
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        config_path = config_dir / ".remote-config"

        # Create or update remote configuration (without credentials)
        config_data = {
            "mode": "remote",
            "server_url": server_url,
            "username": username,
            "repository_link": {
                "alias": activated_repo.user_alias,
                "url": git_url,
                "branch": activated_repo.branch,
                "golden_alias": activated_repo.golden_alias,
                "activation_id": activated_repo.activation_id,
                "activated_at": activated_repo.activated_at,
                "query_endpoint": activated_repo.query_endpoint,
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Saved repository link configuration to {config_path}")

    except Exception as e:
        raise RemoteOperationError(f"Failed to save repository link configuration: {e}")


async def list_available_repositories(
    server_url: str, credentials: Dict[str, Any]
) -> List[ActivatedRepository]:
    """List all repositories available to the current user.

    Args:
        server_url: CIDX server URL
        credentials: Authentication credentials

    Returns:
        List of activated repositories

    Raises:
        RemoteOperationError: If listing fails
    """
    try:
        async with RepositoryLinkingClient(
            server_url=server_url, credentials=credentials
        ) as client:
            repositories = await client.list_user_repositories()
            return cast(List[ActivatedRepository], repositories)

    except ActivationError as e:
        raise RemoteOperationError(f"Failed to list repositories: {e}")
    except AuthenticationError as e:
        raise RemoteOperationError(f"Authentication failed: {e}")
    except NetworkError as e:
        raise RemoteOperationError(f"Network error: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Unexpected error listing repositories: {e}")


async def deactivate_repository_link(project_root: Path) -> bool:
    """Deactivate current repository link.

    Args:
        project_root: Path to project root directory

    Returns:
        True if deactivation was successful

    Raises:
        RemoteOperationError: If deactivation fails
    """
    try:
        # Load remote configuration
        remote_config = _load_remote_configuration(project_root)

        # Extract repository alias from configuration
        repository_link = remote_config.get("repository_link")
        if not repository_link:
            raise RemoteOperationError("No repository link to deactivate")

        repository_alias = repository_link.get("alias")
        if not repository_alias:
            raise RemoteOperationError("Repository alias not found in configuration")

        # Get decrypted credentials for API client
        credentials = _get_decrypted_credentials(project_root)
        server_url = remote_config["server_url"]

        async with RepositoryLinkingClient(
            server_url=server_url, credentials=credentials
        ) as client:
            # Deactivate repository using API client abstraction
            success = await client.deactivate_repository(repository_alias)

            if success:
                # Remove local configuration files
                config_dir = project_root / ".code-indexer"
                config_path = config_dir / ".remote-config"
                creds_path = config_dir / ".creds"

                if config_path.exists():
                    config_path.unlink()
                    logger.info("Removed remote configuration")

                if creds_path.exists():
                    creds_path.unlink()
                    logger.info("Removed encrypted credentials")

            return cast(bool, success)

    except ActivationError as e:
        raise RemoteOperationError(f"Repository deactivation failed: {e}")
    except AuthenticationError as e:
        raise RemoteOperationError(f"Authentication failed: {e}")
    except NetworkError as e:
        raise RemoteOperationError(f"Network error: {e}")
    except Exception as e:
        raise RemoteOperationError(f"Unexpected error during deactivation: {e}")
