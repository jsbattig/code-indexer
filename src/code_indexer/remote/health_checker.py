"""Real server health checking for remote mode.

Provides MESSI RULES compliant health checking that:
- Makes real HTTP calls to server health endpoints (Anti-Mock Rule #1)
- Tests real authentication with stored credentials (Anti-Mock Rule #1)
- Returns real status or fails honestly (Anti-Fallback Rule #2)
- No fake data or simulations (Facts-Based Reasoning)
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, NamedTuple

from ..api_clients.base_client import (
    CIDXRemoteAPIClient,
    AuthenticationError,
    NetworkConnectionError,
    NetworkTimeoutError,
    DNSResolutionError,
    APIClientError,
)
from .config import RemoteConfig
from .credential_manager import (
    CredentialNotFoundError,
    CredentialDecryptionError,
    InsecureCredentialStorageError,
)

logger = logging.getLogger(__name__)


class HealthCheckResult(NamedTuple):
    """Result of server health check with real status information."""

    server_reachable: bool
    authentication_valid: bool
    repository_accessible: bool
    connection_health: (
        str  # "healthy", "authentication_failed", "server_unreachable", etc.
    )
    server_info: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None
    check_timestamp: Optional[datetime] = None


class RealServerHealthChecker:
    """Real server health checker that follows MESSI RULES.

    This implementation:
    - Makes actual HTTP calls to server endpoints (no mocking)
    - Tests real authentication with stored credentials
    - Returns actual server status or fails honestly
    - No fallbacks to fake data
    """

    def __init__(self, project_root: Path):
        """Initialize health checker with project configuration.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = project_root
        self._remote_config: Optional[RemoteConfig] = None

    def _load_remote_config(self) -> RemoteConfig:
        """Load remote configuration, caching for reuse.

        Returns:
            RemoteConfig instance

        Raises:
            FileNotFoundError: If remote config doesn't exist
            ValueError: If config is invalid
        """
        if self._remote_config is None:
            self._remote_config = RemoteConfig(self.project_root)
        return self._remote_config

    async def check_server_health(self) -> HealthCheckResult:
        """Perform comprehensive real server health check.

        Returns:
            HealthCheckResult with real server status information

        Raises:
            FileNotFoundError: If remote configuration is missing
            CredentialNotFoundError: If credentials are not stored
        """
        check_timestamp = datetime.now(timezone.utc)

        try:
            # Load real configuration
            remote_config = self._load_remote_config()
            server_url = remote_config.server_url

            logger.debug(f"Starting health check for server: {server_url}")

            # Test basic server connectivity first (unauthenticated)
            server_reachable = await self._check_server_connectivity(server_url)

            if not server_reachable:
                return HealthCheckResult(
                    server_reachable=False,
                    authentication_valid=False,
                    repository_accessible=False,
                    connection_health="server_unreachable",
                    error_details="Server did not respond to connectivity test",
                    check_timestamp=check_timestamp,
                )

            # Test authentication with real stored credentials
            auth_result = await self._check_authentication(remote_config)

            if not auth_result["valid"]:
                return HealthCheckResult(
                    server_reachable=True,
                    authentication_valid=False,
                    repository_accessible=False,
                    connection_health="authentication_failed",
                    error_details=auth_result.get("error"),
                    check_timestamp=check_timestamp,
                )

            # Test repository accessibility with authenticated client
            repo_accessible = await self._check_repository_access(
                remote_config, auth_result["client"]
            )

            # Get server information from authenticated endpoints
            server_info = await self._get_server_info(auth_result["client"])

            # CRITICAL: Close the client to prevent resource leak
            await auth_result["client"].close()

            # Determine overall health status
            if repo_accessible:
                connection_health = "healthy"
            else:
                connection_health = "repository_access_denied"

            return HealthCheckResult(
                server_reachable=True,
                authentication_valid=True,
                repository_accessible=repo_accessible,
                connection_health=connection_health,
                server_info=server_info,
                check_timestamp=check_timestamp,
            )

        except CredentialNotFoundError:
            return HealthCheckResult(
                server_reachable=False,  # Can't test without credentials
                authentication_valid=False,
                repository_accessible=False,
                connection_health="credentials_not_found",
                error_details="No stored credentials found",
                check_timestamp=check_timestamp,
            )
        except (CredentialDecryptionError, InsecureCredentialStorageError) as e:
            return HealthCheckResult(
                server_reachable=False,  # Can't test without valid credentials
                authentication_valid=False,
                repository_accessible=False,
                connection_health="credential_error",
                error_details=f"Credential error: {e}",
                check_timestamp=check_timestamp,
            )
        except Exception as e:
            logger.error(f"Unexpected error during health check: {e}")
            return HealthCheckResult(
                server_reachable=False,
                authentication_valid=False,
                repository_accessible=False,
                connection_health="health_check_failed",
                error_details=f"Health check failed: {e}",
                check_timestamp=check_timestamp,
            )

    async def _check_server_connectivity(self, server_url: str) -> bool:
        """Test basic server connectivity (unauthenticated).

        Args:
            server_url: Server URL to test

        Returns:
            True if server responds, False otherwise
        """
        try:
            # Test unauthenticated health endpoint if available, or any known endpoint
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try a simple GET to the server root or health endpoint
                # Even if it returns 401, that proves the server is reachable
                try:
                    await client.get(f"{server_url}/health")
                    # Any response (even 401) means server is reachable
                    return True
                except httpx.HTTPStatusError:
                    # HTTP error means server responded (reachable)
                    return True

        except (
            httpx.NetworkError,
            httpx.TimeoutException,
            ConnectionError,
            OSError,
        ) as e:
            logger.debug(f"Server connectivity test failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error in connectivity test: {e}")
            return False

    async def _check_authentication(
        self, remote_config: RemoteConfig
    ) -> Dict[str, Any]:
        """Test authentication with real stored credentials.

        Args:
            remote_config: Remote configuration with credentials

        Returns:
            Dictionary with 'valid' bool and 'client' if successful, 'error' if not
        """
        try:
            # Load real stored credentials
            credentials = remote_config.get_decrypted_credentials()

            # Create authenticated client
            client = CIDXRemoteAPIClient(
                server_url=remote_config.server_url,
                credentials={
                    "username": credentials.username,
                    "password": credentials.password,
                },
                project_root=self.project_root,
            )

            # Test authentication by making a simple authenticated request
            # Try the health endpoint which should require authentication
            response = await client.get("/health")

            if response.status_code == 200:
                logger.debug("Authentication successful")
                return {"valid": True, "client": client}
            else:
                await client.close()
                return {
                    "valid": False,
                    "error": f"Unexpected response: HTTP {response.status_code}",
                }

        except AuthenticationError as e:
            logger.debug(f"Authentication failed: {e}")
            return {"valid": False, "error": f"Authentication failed: {e}"}
        except (NetworkConnectionError, NetworkTimeoutError, DNSResolutionError) as e:
            logger.debug(f"Network error during authentication: {e}")
            return {"valid": False, "error": f"Network error: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            return {"valid": False, "error": f"Authentication error: {e}"}

    async def _check_repository_access(
        self, remote_config: RemoteConfig, client: CIDXRemoteAPIClient
    ) -> bool:
        """Test repository accessibility with authenticated client.

        Args:
            remote_config: Remote configuration
            client: Authenticated API client

        Returns:
            True if repository is accessible, False otherwise
        """
        try:
            # Test repository access by trying to list activated repositories
            # This verifies both authentication and repository permissions
            response = await client.get("/api/repos")
            return bool(response.status_code == 200)

        except APIClientError as e:
            logger.debug(f"Repository access check failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking repository access: {e}")
            return False

    async def _get_server_info(
        self, client: CIDXRemoteAPIClient
    ) -> Optional[Dict[str, Any]]:
        """Get server information from authenticated endpoints.

        Args:
            client: Authenticated API client

        Returns:
            Server information dictionary or None if unavailable
        """
        try:
            # Get comprehensive health information
            response = await client.get("/api/system/health")

            if response.status_code == 200:
                health_data = response.json()
                return {
                    "server_version": health_data.get("version", "unknown"),
                    "api_version": health_data.get("api_version", "unknown"),
                    "uptime": health_data.get("uptime", "unknown"),
                    "status": health_data.get("status", "unknown"),
                }
            else:
                # Try basic health endpoint
                response = await client.get("/health")
                if response.status_code == 200:
                    health_data = response.json()
                    return {
                        "status": health_data.get("status", "unknown"),
                        "server_version": "unknown",
                        "api_version": "unknown",
                        "uptime": "unknown",
                    }

        except Exception as e:
            logger.debug(f"Could not get server info: {e}")

        return None

    async def close(self):
        """Clean up resources."""
        # Nothing to clean up currently, but provides interface for future use
        pass


async def check_remote_server_health(project_root: Path) -> HealthCheckResult:
    """Convenience function for checking remote server health.

    Args:
        project_root: Path to project root directory

    Returns:
        HealthCheckResult with real server status
    """
    checker = RealServerHealthChecker(project_root)
    try:
        return await checker.check_server_health()
    finally:
        await checker.close()
