"""Remote Query Execution for CIDX Remote Repository Linking Mode.

Implements Feature 4 Story 1: Transparent Remote Querying that provides identical
query syntax and output between local and remote modes with automatic repository
linking during first query execution.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, cast, Any

from ..services.git_topology_service import GitTopologyService
from ..mode_detection.command_mode_detector import CommandModeDetector
from ..api_clients.remote_query_client import RemoteQueryClient, QueryResultItem
from ..api_clients.repository_linking_client import RepositoryLinkingClient
from ..remote.repository_linking import (
    ExactBranchMatcher,
    RepositoryLink,
    store_repository_link,
    load_repository_link,
    RepositoryLinkingError,
)
from ..remote.config import RemoteConfig
from ..remote.credential_manager import (
    CredentialNotFoundError,
    CredentialDecryptionError,
)
from ..api_clients.base_client import NetworkError, AuthenticationError

logger = logging.getLogger(__name__)


class RemoteQueryExecutionError(Exception):
    """Exception raised when remote query execution fails."""

    pass


class RepositoryNotLinkedException(RemoteQueryExecutionError):
    """Exception raised when repository is not linked and auto-linking fails."""

    pass


async def execute_remote_query(
    query_text: str,
    limit: int,
    project_root: Path,
    language: Optional[str] = None,
    path: Optional[str] = None,
    min_score: Optional[float] = None,
    include_source: bool = True,
    accuracy: str = "balanced",
) -> List:
    """Execute semantic search query on remote repository with transparent routing.

    This function provides identical API to local query execution, automatically
    handling repository linking during first query and routing subsequent queries
    through established repository links.

    Args:
        query_text: Search query text
        limit: Maximum number of results to return (default: 10)
        project_root: Path to project root directory
        language: Filter by programming language (e.g., python, javascript)
        path: Filter by file path pattern (e.g., */tests/*)
        min_score: Minimum similarity score (0.0-1.0)
        include_source: Whether to include source code in results
        accuracy: Search accuracy profile (fast|balanced|high)

    Returns:
        List of enhanced query result items with staleness detection metadata sorted by relevance score

    Raises:
        ValueError: If parameters are invalid
        RemoteQueryExecutionError: If query execution fails
        RepositoryNotLinkedException: If repository linking fails
        NetworkError: If network operation fails
        AuthenticationError: If authentication fails
    """
    # Validate parameters using same logic as local mode
    if not query_text or not isinstance(query_text, str):
        raise ValueError("Query cannot be empty")

    query_text = query_text.strip()
    if not query_text:
        raise ValueError("Query cannot be empty")

    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("Limit must be positive")

    if limit > 100:
        raise ValueError("Limit cannot exceed 100")

    if min_score is not None:
        if not isinstance(min_score, (int, float)) or not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0")

    if language is not None:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language filter cannot be empty")

    if path is not None:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path filter cannot be empty")

    try:
        # Load remote configuration to validate we're in remote mode
        _load_remote_configuration(project_root)

        # Check if repository is already linked
        repository_link = load_repository_link(project_root)

        if not repository_link:
            # No repository link exists - perform automatic linking during first query
            logger.info(
                "No repository link found - attempting automatic repository linking"
            )
            repository_link = await _establish_repository_link(project_root)

            if not repository_link:
                raise RepositoryNotLinkedException(
                    "Failed to establish repository link automatically. "
                    "Please ensure your local repository matches a remote repository."
                )

            # Store the newly established link for subsequent queries
            store_repository_link(project_root, repository_link)
            logger.info(f"Repository successfully linked: {repository_link.alias}")

        # Execute authenticated query using established repository link
        results = await _execute_authenticated_query(
            query=query_text,
            limit=limit,
            repository_alias=repository_link.alias,
            server_url=repository_link.server_url,
            project_root=project_root,
            language_filter=language,
            path_filter=path,
            min_score=min_score,
            include_source=include_source,
        )

        # Apply staleness detection to enhance results with local file timestamp comparison
        from .staleness_detector import StalenessDetector

        staleness_detector = StalenessDetector()
        enhanced_results = staleness_detector.apply_staleness_detection(
            results, project_root, mode="remote"
        )

        return enhanced_results

    except (RepositoryNotLinkedException, ValueError):
        raise
    except NetworkError as e:
        raise RemoteQueryExecutionError(f"Network error during remote query: {e}")
    except AuthenticationError as e:
        raise RemoteQueryExecutionError(f"Authentication failed: {e}")
    except Exception as e:
        raise RemoteQueryExecutionError(
            f"Unexpected error during remote query execution: {e}"
        )


async def _establish_repository_link(project_root: Path) -> Optional[RepositoryLink]:
    """Establish repository link automatically using exact branch matching.

    Args:
        project_root: Path to project root directory

    Returns:
        RepositoryLink if linking successful, None otherwise

    Raises:
        RepositoryLinkingError: If linking operation fails
        NetworkError: If network operation fails
    """
    try:
        # Detect current mode to ensure we're in remote mode
        mode_detector = CommandModeDetector(project_root)
        current_mode = mode_detector.detect_mode()

        if current_mode != "remote":
            raise RepositoryLinkingError(
                f"Cannot establish repository link in {current_mode} mode"
            )

        # Get git repository URL from local repository
        git_service = GitTopologyService(project_root)

        # Check if git is available and we're in a git repository
        if not git_service.is_git_available():
            raise RepositoryLinkingError(
                "Current directory is not a git repository. Repository linking requires a git repository."
            )

        # Get repository URL using direct git command
        try:
            import subprocess

            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                repo_url = result.stdout.strip()
            else:
                repo_url = None
        except Exception:
            repo_url = None

        if not repo_url:
            raise RepositoryLinkingError(
                "Unable to determine git repository URL. Please ensure repository has a remote origin."
            )

        logger.info(f"Attempting repository linking for: {repo_url}")

        # Load remote configuration for server details
        remote_config = _load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Get decrypted credentials
        credentials = _get_decrypted_credentials(project_root)

        # Initialize repository linking client and exact branch matcher
        async with RepositoryLinkingClient(
            server_url=server_url, credentials=credentials
        ) as linking_client:

            exact_matcher = ExactBranchMatcher(linking_client)

            # Attempt exact branch matching
            repository_link = await exact_matcher.find_exact_branch_match(
                project_root, repo_url
            )

            if repository_link:
                logger.info(
                    f"Repository linking successful: {repository_link.repository_type.value} "
                    f"repository '{repository_link.alias}' with branch '{repository_link.branch}'"
                )
                return repository_link
            else:
                logger.warning(
                    f"No matching repository found for {repo_url}. "
                    "Please check that the repository exists on the remote server and has the correct branch."
                )
                return None

    except RepositoryLinkingError:
        raise
    except Exception as e:
        raise RepositoryLinkingError(f"Unexpected error during repository linking: {e}")


async def _execute_authenticated_query(
    query: str,
    limit: int,
    repository_alias: str,
    server_url: str,
    project_root: Path,
    language_filter: Optional[str] = None,
    path_filter: Optional[str] = None,
    min_score: Optional[float] = None,
    include_source: bool = True,
) -> List[QueryResultItem]:
    """Execute authenticated query against remote repository.

    Args:
        query: Search query text
        limit: Maximum number of results
        repository_alias: Repository alias to query
        server_url: Remote server URL
        project_root: Project root path for credentials
        language_filter: Optional language filter
        path_filter: Optional path pattern filter
        min_score: Optional minimum score threshold
        include_source: Whether to include source code in results

    Returns:
        List of query result items

    Raises:
        AuthenticationError: If authentication fails
        NetworkError: If network operation fails
        Exception: If query execution fails
    """
    try:
        # Get decrypted credentials
        credentials = _get_decrypted_credentials(project_root)

        # Execute query using remote query client
        async with RemoteQueryClient(
            server_url=server_url, credentials=credentials
        ) as query_client:

            results = await query_client.execute_query(
                repository_alias=repository_alias,
                query=query,
                limit=limit,
                include_source=include_source,
                min_score=min_score,
                language=language_filter,
                path_filter=path_filter,
            )

            return cast(List[QueryResultItem], results)

    except (AuthenticationError, NetworkError):
        raise
    except Exception as e:
        raise RemoteQueryExecutionError(f"Query execution failed: {e}")


def _load_remote_configuration(project_root: Path) -> dict[Any, Any]:
    """Load remote configuration from project directory.

    Args:
        project_root: Path to project root directory

    Returns:
        Remote configuration dictionary

    Raises:
        RemoteQueryExecutionError: If configuration cannot be loaded
    """
    config_path = project_root / ".code-indexer" / ".remote-config"

    if not config_path.exists():
        raise RemoteQueryExecutionError(
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
                raise RemoteQueryExecutionError(
                    f"Invalid remote configuration: missing {field}"
                )

        return cast(dict[Any, Any], config_data)

    except json.JSONDecodeError as e:
        raise RemoteQueryExecutionError(f"Invalid remote configuration JSON: {e}")
    except Exception as e:
        raise RemoteQueryExecutionError(f"Failed to load remote configuration: {e}")


def _get_decrypted_credentials(project_root: Path) -> dict:
    """Get decrypted credentials for API client usage.

    Args:
        project_root: Path to project root directory

    Returns:
        Dictionary with username, password, and server_url

    Raises:
        RemoteQueryExecutionError: If credentials cannot be decrypted
    """
    try:
        remote_config = RemoteConfig(project_root)
        decrypted_creds = remote_config.get_decrypted_credentials()

        credentials_dict = {
            "username": decrypted_creds.username,
            "password": decrypted_creds.password,
            "server_url": decrypted_creds.server_url,
        }
        return credentials_dict

    except CredentialNotFoundError:
        raise RemoteQueryExecutionError(
            "No encrypted credentials found. Please run 'cidx init --remote' first."
        )
    except CredentialDecryptionError as e:
        raise RemoteQueryExecutionError(f"Failed to decrypt credentials: {e}")
    except Exception as e:
        raise RemoteQueryExecutionError(f"Failed to load credentials: {e}")
