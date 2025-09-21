"""
Jobs API Client for CIDX Server Integration.

Provides job listing and management functionality with real server authentication
and network error handling. Follows anti-mock principles with real API integration.
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


class JobsAPIClient(CIDXRemoteAPIClient):
    """Client for job management operations with CIDX server."""

    def __init__(
        self,
        server_url: str,
        credentials: Dict[str, Any],
        project_root: Optional[Path] = None,
    ):
        """Initialize Jobs API client.

        Args:
            server_url: Base URL of the CIDX server
            credentials: Encrypted credentials dictionary
            project_root: Project root for persistent token storage
        """
        super().__init__(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

    async def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List jobs from CIDX server with filtering options.

        Args:
            status: Filter by job status (optional)
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip for pagination

        Returns:
            Dictionary with job listing response from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        # Build query parameters
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if status:
            params["status"] = status

        try:
            response = await self.get("/api/jobs", params=params)

            if response.status_code == 200:
                return dict(response.json())
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
                    f"Failed to list jobs: {error_detail}", response.status_code
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
            raise APIClientError(f"Unexpected error listing jobs: {e}")

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a specific job.

        Args:
            job_id: Job ID to get status for

        Returns:
            Job status data from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        # Use the existing method from base class
        return await super().get_job_status(job_id)
