"""
Admin API Client for CIDX Server Integration.

Provides administrative functionality including user creation and management
with real server authentication and network error handling. Follows anti-mock
principles with real API integration.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
)
from .network_error_handler import (
    NetworkConnectionError,
    NetworkTimeoutError,
    DNSResolutionError,
    SSLCertificateError,
    ServerError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class AdminAPIClient(CIDXRemoteAPIClient):
    """Client for administrative operations with CIDX server."""

    def __init__(
        self,
        server_url: str,
        credentials: Dict[str, Any],
        project_root: Optional[Path] = None,
    ):
        """Initialize Admin API client.

        Args:
            server_url: Base URL of the CIDX server
            credentials: Encrypted credentials dictionary (must have admin role)
            project_root: Project root for persistent token storage
        """
        super().__init__(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

    async def create_user(
        self,
        username: str,
        password: str,
        role: str,
    ) -> Dict[str, Any]:
        """Create a new user account with specified role.

        Args:
            username: Username for the new user
            password: Password for the new user
            role: Role for the new user (admin, power_user, normal_user)

        Returns:
            Dictionary with user creation response from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        user_data = {
            "username": username,
            "password": password,
            "role": role,
        }

        try:
            response = await self._authenticated_request(
                "POST", "/api/admin/users", json=user_data
            )

            if response.status_code == 201:
                return dict(response.json())
            elif response.status_code == 400:
                # Bad request - validation error
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Invalid user data")
                except Exception:
                    error_detail = "Invalid user data"
                raise APIClientError(f"Invalid user data: {error_detail}", 400)
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for user creation (admin role required)"
                )
            elif response.status_code == 409:
                # Conflict - user already exists
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "User already exists")
                except Exception:
                    error_detail = "User already exists"
                raise APIClientError(f"User creation conflict: {error_detail}", 409)
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
                    f"Failed to create user: {error_detail}", response.status_code
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error creating user: {e}")

    async def list_users(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List users from CIDX server with pagination.

        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip for pagination

        Returns:
            Dictionary with user listing response from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        # Build query parameters
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        try:
            response = await self.get("/api/admin/users", params=params)

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for user listing (admin role required)"
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
                    f"Failed to list users: {error_detail}", response.status_code
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error listing users: {e}")

    async def get_user(
        self,
        username: str,
    ) -> Dict[str, Any]:
        """Get user details by username.

        Args:
            username: Username to retrieve

        Returns:
            Dictionary with user details response from server

        Raises:
            APIClientError: If API request fails or user not found
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        try:
            # Use list_users to get all users, then filter for the specific user
            # Note: Server doesn't have individual user GET endpoint, so we use list
            response = await self.list_users(limit=1000, offset=0)

            users = response.get("users", [])
            for user in users:
                if user.get("username") == username:
                    return {"user": user}

            # User not found
            raise APIClientError(f"User '{username}' not found", 404)

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error getting user: {e}")

    async def update_user(
        self,
        username: str,
        role: str,
    ) -> Dict[str, Any]:
        """Update user role.

        Args:
            username: Username to update
            role: New role for the user (admin, power_user, normal_user)

        Returns:
            Dictionary with update response from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        user_data = {"role": role}

        try:
            response = await self._authenticated_request(
                "PUT", f"/api/admin/users/{username}", json=user_data
            )

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 400:
                # Bad request - validation error
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Invalid user data")
                except Exception:
                    error_detail = "Invalid user data"
                raise APIClientError(f"Invalid update data: {error_detail}", 400)
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for user update (admin role required)"
                )
            elif response.status_code == 404:
                # Not found - user doesn't exist
                raise APIClientError(f"User '{username}' not found", 404)
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
                    f"Failed to update user: {error_detail}", response.status_code
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error updating user: {e}")

    async def delete_user(
        self,
        username: str,
    ) -> Dict[str, Any]:
        """Delete user account.

        Args:
            username: Username to delete

        Returns:
            Dictionary with deletion response from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        try:
            response = await self._authenticated_request(
                "DELETE", f"/api/admin/users/{username}"
            )

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 400:
                # Bad request - probably trying to delete last admin
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Cannot delete user")
                except Exception:
                    error_detail = "Cannot delete user"
                raise APIClientError(f"Delete failed: {error_detail}", 400)
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for user deletion (admin role required)"
                )
            elif response.status_code == 404:
                # Not found - user doesn't exist
                raise APIClientError(f"User '{username}' not found", 404)
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
                    f"Failed to delete user: {error_detail}", response.status_code
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error deleting user: {e}")

    async def change_user_password(
        self,
        username: str,
        new_password: str,
    ) -> Dict[str, Any]:
        """Change user password (admin only).

        Args:
            username: Username whose password to change
            new_password: New password for the user

        Returns:
            Dictionary with password change response from server

        Raises:
            APIClientError: If API request fails or user not found
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        password_data = {
            "old_password": "",  # Not required for admin endpoint, but model expects it
            "new_password": new_password,
        }

        try:
            response = await self._authenticated_request(
                "PUT",
                f"/api/admin/users/{username}/change-password",
                json=password_data,
            )

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 400:
                # Bad request - validation error
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Invalid password data")
                except Exception:
                    error_detail = "Invalid password data"
                raise APIClientError(f"Invalid password data: {error_detail}", 400)
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for password change (admin role required)"
                )
            elif response.status_code == 404:
                # Not found - user doesn't exist
                raise APIClientError(f"User '{username}' not found", 404)
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
                    f"Failed to change password: {error_detail}", response.status_code
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error changing password: {e}")

    async def add_golden_repository(
        self,
        git_url: str,
        alias: str,
        description: Optional[str] = None,
        default_branch: str = "main",
    ) -> Dict[str, Any]:
        """Add a new golden repository from Git URL (admin only).

        Args:
            git_url: Git repository URL (https, ssh, or git protocol)
            alias: Unique alias for the repository
            description: Optional description for the repository
            default_branch: Default branch name (defaults to "main")

        Returns:
            Dictionary with job ID and status for tracking the async operation

        Raises:
            APIClientError: If API request fails or validation error
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        # Build request payload
        repo_data = {
            "repo_url": git_url,
            "alias": alias,
            "default_branch": default_branch,
        }

        # Add description if provided
        if description is not None:
            repo_data["description"] = description

        try:
            response = await self._authenticated_request(
                "POST", "/api/admin/golden-repos", json=repo_data
            )

            if response.status_code == 202:
                return dict(response.json())
            elif response.status_code == 400:
                # Bad request - validation error
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Invalid repository data")
                except Exception:
                    error_detail = "Invalid repository data"
                raise APIClientError(f"Invalid request data: {error_detail}", 400)
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for golden repository creation (admin role required)"
                )
            elif response.status_code == 409:
                # Conflict - repository alias already exists
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Repository already exists")
                except Exception:
                    error_detail = "Repository already exists"
                raise APIClientError(f"Repository conflict: {error_detail}", 409)
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
                    f"Failed to add golden repository: {error_detail}",
                    response.status_code,
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error adding golden repository: {e}")

    async def list_golden_repositories(self) -> Dict[str, Any]:
        """List all golden repositories (admin only).

        Returns:
            Dictionary with golden repositories list and total count

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        try:
            response = await self.get("/api/admin/golden-repos")

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for golden repository listing (admin role required)"
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
                    f"Failed to list golden repositories: {error_detail}",
                    response.status_code,
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error listing golden repositories: {e}")

    async def refresh_golden_repository(self, alias: str) -> Dict[str, Any]:
        """Refresh a golden repository (admin only).

        Args:
            alias: Alias of the repository to refresh

        Returns:
            Dictionary with job ID and status for tracking the async operation

        Raises:
            APIClientError: If API request fails or repository not found
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        try:
            response = await self._authenticated_request(
                "POST", f"/api/admin/golden-repos/{alias}/refresh"
            )

            if response.status_code == 202:
                return dict(response.json())
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for golden repository refresh (admin role required)"
                )
            elif response.status_code == 404:
                # Not found - repository doesn't exist
                raise APIClientError(f"Golden repository '{alias}' not found", 404)
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
                    f"Failed to refresh golden repository: {error_detail}",
                    response.status_code,
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error refreshing golden repository: {e}")

    async def delete_golden_repository(
        self,
        alias: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Delete a golden repository (admin only).

        Args:
            alias: Alias of the repository to delete
            force: Force deletion without confirmation (for CLI automation)

        Returns:
            Dictionary with deletion confirmation (empty for successful 204 response)

        Raises:
            APIClientError: If API request fails or repository not found
            AuthenticationError: If authentication fails or insufficient privileges
            NetworkError: If network request fails
        """
        # Validate alias parameter
        if not alias or not isinstance(alias, str):
            raise ValueError("Repository alias must be a non-empty string")

        try:
            response = await self._authenticated_request(
                "DELETE", f"/api/admin/golden-repos/{alias}"
            )

            if response.status_code == 204:
                # Successful deletion - return empty dict for 204 No Content
                return {}
            elif response.status_code == 403:
                # Forbidden - insufficient privileges
                raise AuthenticationError(
                    "Insufficient privileges for golden repository deletion (admin role required)"
                )
            elif response.status_code == 404:
                # Not found - repository doesn't exist
                try:
                    error_data = response.json()
                    error_detail = error_data.get(
                        "detail", f"Repository '{alias}' not found"
                    )
                except Exception:
                    error_detail = f"Repository '{alias}' not found"
                raise APIClientError(f"Repository not found: {error_detail}", 404)
            elif response.status_code == 409:
                # Conflict - repository has active instances
                try:
                    error_data = response.json()
                    error_detail = error_data.get(
                        "detail", "Repository deletion conflict"
                    )
                except Exception:
                    error_detail = "Repository deletion conflict"
                raise APIClientError(
                    f"Repository deletion conflict: {error_detail}", 409
                )
            elif response.status_code == 503:
                # Service unavailable
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Service unavailable")
                except Exception:
                    error_detail = "Service unavailable"
                raise APIClientError(f"Service unavailable: {error_detail}", 503)
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
                    f"Failed to delete golden repository: {error_detail}",
                    response.status_code,
                )

        except (
            APIClientError,
            AuthenticationError,
            NetworkError,
            NetworkConnectionError,
            NetworkTimeoutError,
            DNSResolutionError,
            SSLCertificateError,
            ServerError,
            RateLimitError,
        ):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error deleting golden repository: {e}")
