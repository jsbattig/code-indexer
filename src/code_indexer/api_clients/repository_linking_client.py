"""Repository Linking Client for CIDX Remote Operations.

Handles repository discovery, golden repository management, and activation functionality
with clean API abstractions and no raw HTTP calls in business logic.
"""

import re
from typing import List, Dict, Any, cast
from pydantic import BaseModel, Field

from .base_client import CIDXRemoteAPIClient, APIClientError, AuthenticationError
from ..server.models.repository_discovery import (
    RepositoryMatch,  # noqa: F401 - Re-exported for tests
    RepositoryDiscoveryResponse as ServerRepositoryDiscoveryResponse,
)


class RepositoryNotFoundError(APIClientError):
    """Exception raised when repository is not found."""

    pass


class BranchNotFoundError(APIClientError):
    """Exception raised when branch is not found."""

    pass


class ActivationError(APIClientError):
    """Exception raised when repository activation fails."""

    pass


# Use server model directly for consistency
RepositoryDiscoveryResponse = ServerRepositoryDiscoveryResponse


class BranchInfo(BaseModel):
    """Information about a repository branch."""

    name: str = Field(..., description="Branch name")
    is_default: bool = Field(..., description="Whether this is the default branch")
    last_commit_sha: str = Field(..., description="SHA of the last commit")
    last_commit_message: str = Field(..., description="Message of the last commit")
    last_updated: str = Field(..., description="Last update timestamp")
    indexing_status: str = Field(..., description="Current indexing status")
    total_files: int = Field(..., description="Total files in branch")
    indexed_files: int = Field(..., description="Number of files indexed")


class ActivatedRepository(BaseModel):
    """Information about an activated repository."""

    activation_id: str = Field(..., description="Unique activation identifier")
    golden_alias: str = Field(..., description="Golden repository alias")
    user_alias: str = Field(..., description="User-specific repository alias")
    branch: str = Field(..., description="Activated branch name")
    status: str = Field(..., description="Activation status")
    activated_at: str = Field(..., description="Activation timestamp")
    access_permissions: List[str] = Field(..., description="User's access permissions")
    query_endpoint: str = Field(..., description="Query endpoint URL")
    expires_at: str = Field(..., description="Activation expiration timestamp")
    usage_limits: Dict[str, Any] = Field(..., description="Usage limits and quotas")


class RepositoryLinkingClient(CIDXRemoteAPIClient):
    """Client for repository discovery and linking operations."""

    async def discover_repositories(self, repo_url: str) -> RepositoryDiscoveryResponse:
        """Find matching repositories by git origin URL.

        Args:
            repo_url: Git repository URL to search for

        Returns:
            Repository discovery response with matching repositories

        Raises:
            ValueError: If repo_url is invalid
            RepositoryNotFoundError: If discovery fails
            NetworkError: If network operation fails
        """
        # Validate git URL format
        if not repo_url or not isinstance(repo_url, str):
            raise ValueError("Invalid git URL format: empty or invalid type")

        repo_url = repo_url.strip()
        if not repo_url:
            raise ValueError("Invalid git URL format: empty URL")

        # Basic URL validation - must be HTTP(S) and end with .git
        if not re.match(r"^https?://.*\.git$", repo_url):
            raise ValueError(f"Invalid git URL format: {repo_url}")

        discovery_endpoint = f"/api/repos/discover?repo_url={repo_url}"

        try:
            response = await self._authenticated_request("GET", discovery_endpoint)

            if response.status_code == 200:
                discovery_data = response.json()
                return cast(
                    RepositoryDiscoveryResponse,
                    RepositoryDiscoveryResponse.model_validate(discovery_data),
                )

            elif response.status_code == 404:
                error_detail = response.json().get("detail", "Repository not found")
                raise RepositoryNotFoundError(f"Discovery failed: {error_detail}")

            else:
                error_detail = response.json().get(
                    "detail", f"HTTP {response.status_code}"
                )
                raise RepositoryNotFoundError(f"Discovery error: {error_detail}")

        except (RepositoryNotFoundError, ValueError):
            raise
        except Exception as e:
            # Preserve authentication context for connection errors
            if isinstance(e, APIClientError):
                error_msg = str(e).lower()
                if any(
                    term in error_msg for term in ["connection", "network", "timeout"]
                ):
                    # Connection-related errors during repository discovery often indicate
                    # authentication/server availability issues
                    raise RepositoryNotFoundError(
                        f"Discovery failed due to authentication or connection issue: {e}"
                    )
                else:
                    raise RepositoryNotFoundError(f"Discovery failed: {e}")
            # Handle other exceptions with authentication context if they seem connection-related
            error_str = str(e).lower()
            if any(
                term in error_str
                for term in ["connection", "network", "timeout", "failed"]
            ):
                raise RepositoryNotFoundError(
                    f"Discovery failed due to authentication or connection issue: {e}"
                )
            raise RepositoryNotFoundError(f"Unexpected discovery error: {e}")

    async def get_golden_repository_branches(self, alias: str) -> List[BranchInfo]:
        """Get available branches for golden repository.

        Args:
            alias: Golden repository alias

        Returns:
            List of branch information

        Raises:
            ValueError: If alias is invalid
            RepositoryNotFoundError: If repository is not found
            NetworkError: If network operation fails
        """
        # Validate alias format
        if not alias or not isinstance(alias, str):
            raise ValueError("Repository alias cannot be empty")

        alias = alias.strip()
        if not alias:
            raise ValueError("Repository alias cannot be empty")

        # Basic alias validation - alphanumeric, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", alias):
            raise ValueError(f"Invalid repository alias format: {alias}")

        branches_endpoint = f"/api/repos/golden/{alias}/branches"

        try:
            response = await self._authenticated_request("GET", branches_endpoint)

            if response.status_code == 200:
                branches_data = response.json()
                branches = branches_data.get("branches", [])
                return [BranchInfo.model_validate(branch) for branch in branches]

            elif response.status_code == 404:
                error_detail = response.json().get("detail", "Repository not found")
                raise RepositoryNotFoundError(
                    f"Repository '{alias}' not found: {error_detail}"
                )

            else:
                error_detail = response.json().get(
                    "detail", f"HTTP {response.status_code}"
                )
                raise RepositoryNotFoundError(f"Failed to get branches: {error_detail}")

        except (RepositoryNotFoundError, ValueError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise RepositoryNotFoundError(f"Failed to get branches: {e}")
            raise RepositoryNotFoundError(f"Unexpected error getting branches: {e}")

    async def activate_repository(
        self, golden_alias: str, branch: str, user_alias: str
    ) -> ActivatedRepository:
        """Activate a golden repository for user access.

        Args:
            golden_alias: Golden repository alias
            branch: Branch to activate
            user_alias: User-specific alias for the activated repository

        Returns:
            Activated repository information

        Raises:
            ValueError: If parameters are invalid
            BranchNotFoundError: If branch is not found
            ActivationError: If activation fails
            NetworkError: If network operation fails
        """
        # Validate parameters
        if not golden_alias or not isinstance(golden_alias, str):
            raise ValueError("Golden alias cannot be empty")
        if not branch or not isinstance(branch, str):
            raise ValueError("Branch cannot be empty")
        if not user_alias or not isinstance(user_alias, str):
            raise ValueError("User alias cannot be empty")

        golden_alias = golden_alias.strip()
        branch = branch.strip()
        user_alias = user_alias.strip()

        if not golden_alias:
            raise ValueError("Golden alias cannot be empty")
        if not branch:
            raise ValueError("Branch cannot be empty")
        if not user_alias:
            raise ValueError("User alias cannot be empty")

        activation_endpoint = "/api/repos/activate"

        activation_payload = {
            "golden_repo_alias": golden_alias,
            "branch_name": branch,
            "user_alias": user_alias,
        }

        try:
            response = await self._authenticated_request(
                "POST", activation_endpoint, json=activation_payload
            )

            if response.status_code == 201:
                activation_data = response.json()
                return cast(
                    ActivatedRepository,
                    ActivatedRepository.model_validate(activation_data),
                )

            elif response.status_code == 400:
                error_detail = response.json().get("detail", "Invalid request")
                if "branch" in error_detail.lower():
                    raise BranchNotFoundError(f"Branch error: {error_detail}")
                else:
                    raise ActivationError(f"Activation failed: {error_detail}")

            elif response.status_code == 403:
                error_detail = response.json().get("detail", "Access denied")
                raise ActivationError(f"Access denied: {error_detail}")

            elif response.status_code == 409:
                error_detail = response.json().get("detail", "Conflict")
                raise ActivationError(f"Activation conflict: {error_detail}")

            elif response.status_code == 429:
                error_detail = response.json().get("detail", "Quota exceeded")
                raise ActivationError(f"Quota exceeded: {error_detail}")

            else:
                error_detail = response.json().get(
                    "detail", f"HTTP {response.status_code}"
                )
                raise ActivationError(f"Activation error: {error_detail}")

        except (BranchNotFoundError, ActivationError, ValueError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise ActivationError(f"Activation failed: {e}")
            raise ActivationError(f"Unexpected activation error: {e}")

    async def deactivate_repository(self, user_alias: str) -> bool:
        """Deactivate a user's repository access.

        Args:
            user_alias: User-specific repository alias to deactivate

        Returns:
            True if deactivation was successful

        Raises:
            ValueError: If user_alias is invalid
            ActivationError: If deactivation fails
            NetworkError: If network operation fails
        """
        # Validate user alias
        if not user_alias or not isinstance(user_alias, str):
            raise ValueError("User alias cannot be empty")

        user_alias = user_alias.strip()
        if not user_alias:
            raise ValueError("User alias cannot be empty")

        deactivation_endpoint = f"/api/repos/{user_alias}"

        try:
            response = await self._authenticated_request(
                "DELETE", deactivation_endpoint
            )

            if response.status_code == 200:
                return True

            elif response.status_code == 404:
                error_detail = response.json().get("detail", "Repository not found")
                raise ActivationError(
                    f"Repository '{user_alias}' not found: {error_detail}"
                )

            else:
                error_detail = response.json().get(
                    "detail", f"HTTP {response.status_code}"
                )
                raise ActivationError(f"Deactivation error: {error_detail}")

        except (ActivationError, ValueError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise ActivationError(f"Deactivation failed: {e}")
            raise ActivationError(f"Unexpected deactivation error: {e}")

    async def list_user_repositories(self) -> List[ActivatedRepository]:
        """List all repositories activated for the current user.

        Returns:
            List of activated repositories

        Raises:
            ActivationError: If listing fails
            NetworkError: If network operation fails
        """
        list_endpoint = "/api/repos"

        try:
            response = await self._authenticated_request("GET", list_endpoint)

            if response.status_code == 200:
                repositories_data = response.json()
                repositories = repositories_data.get("repositories", [])
                return [
                    ActivatedRepository.model_validate(repo) for repo in repositories
                ]

            elif response.status_code == 401:
                error_detail = response.json().get("detail", "Authentication required")
                raise AuthenticationError(f"Authentication failed: {error_detail}")

            elif response.status_code == 403:
                error_detail = response.json().get("detail", "Access denied")
                raise ActivationError(f"Access denied: {error_detail}")

            elif response.status_code == 404:
                error_detail = response.json().get("detail", "Endpoint not found")
                raise ActivationError(
                    f"Repository list endpoint not available: {error_detail}"
                )

            else:
                error_detail = response.json().get(
                    "detail", f"HTTP {response.status_code}"
                )
                raise ActivationError(f"Failed to list repositories: {error_detail}")

        except (ActivationError, AuthenticationError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise ActivationError(f"Failed to list repositories: {e}")
            raise ActivationError(f"Unexpected error listing repositories: {e}")
