"""System API Client for CIDX Remote Server.

Provides system health monitoring functionality including basic and detailed
health checks with response time measurement and comprehensive error handling.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .base_client import CIDXRemoteAPIClient, APIClientError, AuthenticationError

logger = logging.getLogger(__name__)


class SystemAPIClient(CIDXRemoteAPIClient):
    """API client for system monitoring operations extending base functionality.

    Provides health monitoring functionality including:
    - Basic health check using GET /health endpoint
    - Detailed health check using GET /api/system/health endpoint
    - Response time measurement for performance monitoring
    - Comprehensive error handling with user-friendly messages
    - Authentication integration with JWT token management
    """

    def __init__(
        self,
        server_url: str,
        credentials: Dict[str, Any],
        project_root: Optional[Path] = None,
    ):
        """Initialize system API client.

        Args:
            server_url: Base URL of the CIDX server
            credentials: Encrypted credentials dictionary containing username/password
            project_root: Project root directory for persistent token storage
        """
        super().__init__(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

    async def check_basic_health(self) -> Dict[str, Any]:
        """Check basic system health using GET /health endpoint.

        Performs a basic health check that returns server status and uptime
        information. Measures response time for performance monitoring.

        Returns:
            Dict containing:
            - status: Server health status ("ok" or error status)
            - timestamp: Health check timestamp from server
            - message: Human-readable status message
            - response_time_ms: Response time in milliseconds

        Raises:
            AuthenticationError: If authentication fails (invalid token)
            APIClientError: If server error occurs or health check fails
        """
        logger.debug("Performing basic health check")

        # Measure response time
        start_time = time.time()

        try:
            # Call basic health endpoint
            response = await self._authenticated_request("GET", "/health")

            # Calculate response time
            end_time = time.time()
            response_time_ms = round((end_time - start_time) * 1000, 2)

            # Parse JSON response and add response time to result
            health_data: Dict[str, Any] = response.json()
            health_data["response_time_ms"] = response_time_ms

            logger.debug(f"Basic health check completed in {response_time_ms}ms")
            return health_data

        except AuthenticationError as e:
            logger.error(f"Authentication failed during health check: {e}")
            raise
        except APIClientError as e:
            logger.error(f"Health check failed: {e}")
            raise
        except Exception as e:
            # Calculate response time even for failures
            end_time = time.time()
            response_time_ms = round((end_time - start_time) * 1000, 2)

            logger.error(f"Unexpected error during health check: {e}")
            raise APIClientError(f"Health check failed after {response_time_ms}ms: {e}")

    async def check_detailed_health(self) -> Dict[str, Any]:
        """Check detailed system health using GET /api/system/health endpoint.

        Performs a comprehensive health check that returns detailed information
        about system components, services, and resource usage. Measures response
        time for performance monitoring.

        Returns:
            Dict containing:
            - status: Overall system health status
            - timestamp: Health check timestamp from server
            - services: Dict of individual service health information
            - system: System resource usage information
            - response_time_ms: Response time in milliseconds

        Raises:
            AuthenticationError: If authentication fails (invalid token)
            APIClientError: If server error occurs or health check fails
        """
        logger.debug("Performing detailed health check")

        # Measure response time
        start_time = time.time()

        try:
            # Call detailed health endpoint
            response = await self._authenticated_request("GET", "/api/system/health")

            # Calculate response time
            end_time = time.time()
            response_time_ms = round((end_time - start_time) * 1000, 2)

            # Parse JSON response and add response time to result
            health_data: Dict[str, Any] = response.json()
            health_data["response_time_ms"] = response_time_ms

            logger.debug(f"Detailed health check completed in {response_time_ms}ms")
            return health_data

        except AuthenticationError as e:
            logger.error(f"Authentication failed during detailed health check: {e}")
            raise
        except APIClientError as e:
            logger.error(f"Detailed health check failed: {e}")
            raise
        except Exception as e:
            # Calculate response time even for failures
            end_time = time.time()
            response_time_ms = round((end_time - start_time) * 1000, 2)

            logger.error(f"Unexpected error during detailed health check: {e}")
            raise APIClientError(
                f"Detailed health check failed after {response_time_ms}ms: {e}"
            )


def create_system_client(
    server_url: str,
    project_root: Optional[Path] = None,
    username: Optional[str] = None,
) -> SystemAPIClient:
    """Factory function to create SystemAPIClient with credential loading.

    Args:
        server_url: Server URL for system monitoring
        project_root: Optional project root directory
        username: Optional username for loading stored credentials

    Returns:
        SystemAPIClient: Initialized system monitoring client

    Note:
        If project_root and username are provided, attempts to load stored
        credentials. Falls back to empty credentials if loading fails.
    """
    from ..remote.credential_manager import (
        load_encrypted_credentials,
        CredentialNotFoundError,
        ProjectCredentialManager,
    )

    credentials: Dict[str, Any] = {}

    if project_root and username:
        try:
            # Load encrypted credential data
            encrypted_data = load_encrypted_credentials(project_root)

            # Decrypt credentials
            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username,
                repo_path=str(project_root),
                server_url=server_url,
            )

            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
            logger.debug(f"Loaded stored credentials for user: {username}")
        except (CredentialNotFoundError, Exception) as e:
            logger.debug(f"Could not load stored credentials: {e}")
            # Fall back to empty credentials

    return SystemAPIClient(
        server_url=server_url,
        credentials=credentials,
        project_root=project_root,
    )
