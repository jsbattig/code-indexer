"""
Claude Server API Client.

Story #719: Execute Delegation Function with Async Job

Provides async HTTP client for communicating with Claude Server
for delegated job execution.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ClaudeServerError(Exception):
    """Base exception for Claude Server client errors."""

    pass


class ClaudeServerAuthError(ClaudeServerError):
    """Raised when authentication to Claude Server fails."""

    pass


class ClaudeServerNotFoundError(ClaudeServerError):
    """Raised when a resource is not found (404)."""

    pass


class ClaudeServerClient:
    """
    Async client for Claude Server API communication.

    Handles authentication, JWT token management, repository operations,
    and job creation/management for delegation function execution.
    """

    def __init__(self, base_url: str, username: str, password: str):
        """
        Initialize the Claude Server client.

        Args:
            base_url: Base URL of the Claude Server (e.g., https://claude.example.com)
            username: Username for authentication
            password: Decrypted password/credential for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._jwt_token: Optional[str] = None
        self._jwt_expires: Optional[datetime] = None

    def __repr__(self) -> str:
        """Prevent accidental credential exposure in logs and debugging output."""
        return f"ClaudeServerClient(base_url={self.base_url!r}, username={self.username!r})"

    async def authenticate(self) -> str:
        """
        Authenticate with Claude Server and obtain JWT token.

        Returns:
            JWT access token string

        Raises:
            ClaudeServerAuthError: If authentication fails
            ClaudeServerError: If connection fails
        """
        login_url = f"{self.base_url}/auth/login"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    login_url,
                    json={"username": self.username, "password": self.password},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Support both Claude Server ("token") and standard OAuth ("access_token")
                    self._jwt_token = data.get("token") or data.get("access_token")
                    if not self._jwt_token:
                        raise ClaudeServerError("No token in authentication response")
                    # Calculate expiration time
                    # Claude Server returns "expires" (ISO datetime), standard returns "expires_in" (seconds)
                    if "expires" in data:
                        from dateutil.parser import parse as parse_datetime
                        self._jwt_expires = parse_datetime(data["expires"])
                    else:
                        expires_in = data.get("expires_in", 3600)
                        self._jwt_expires = datetime.now(timezone.utc) + timedelta(
                            seconds=expires_in
                        )
                    return self._jwt_token
                elif response.status_code == 401:
                    raise ClaudeServerAuthError(
                        f"Authentication failed: {response.status_code}"
                    )
                else:
                    raise ClaudeServerError(
                        f"Authentication error: HTTP {response.status_code}"
                    )

        except httpx.ConnectError as e:
            raise ClaudeServerError(f"Connection error to Claude Server: {e}")
        except httpx.TimeoutException as e:
            raise ClaudeServerError(f"Connection timeout to Claude Server: {e}")

    async def ensure_authenticated(self) -> str:
        """
        Return valid JWT token, refreshing if needed.

        Returns:
            Valid JWT access token

        Raises:
            ClaudeServerAuthError: If authentication fails
            ClaudeServerError: If connection fails
        """
        if self._jwt_token and self._jwt_expires:
            # Check if token is still valid (with 60s buffer)
            if datetime.now(timezone.utc) < self._jwt_expires - timedelta(seconds=60):
                return self._jwt_token

        # Token expired or not set, authenticate
        return await self.authenticate()

    async def _make_authenticated_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """
        Make an authenticated request to Claude Server.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            json_data: Optional JSON body data
            retry_on_401: Whether to retry on 401 (default True)

        Returns:
            httpx Response object

        Raises:
            ClaudeServerError: On connection or server errors
        """
        token = await self.ensure_authenticated()
        url = f"{self.base_url}{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {token}"}

                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, timeout=30.0)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, headers=headers, json=json_data, timeout=30.0
                    )
                else:
                    raise ClaudeServerError(f"Unsupported HTTP method: {method}")

                # Handle 401 with retry
                if response.status_code == 401 and retry_on_401:
                    # Clear token and re-authenticate
                    self._jwt_token = None
                    self._jwt_expires = None
                    return await self._make_authenticated_request(
                        method, endpoint, json_data, retry_on_401=False
                    )
                elif response.status_code == 401 and not retry_on_401:
                    # Second 401 means auth truly failed - raise exception
                    raise ClaudeServerAuthError(
                        "Authentication failed after token refresh"
                    )

                return response

        except httpx.ConnectError as e:
            raise ClaudeServerError(f"Connection error to Claude Server: {e}")
        except httpx.TimeoutException as e:
            raise ClaudeServerError(f"Connection timeout to Claude Server: {e}")

    async def check_repository_exists(self, alias: str) -> bool:
        """
        Check if a repository is registered in Claude Server.

        Args:
            alias: Repository alias to check

        Returns:
            True if repository exists, False otherwise
        """
        response = await self._make_authenticated_request(
            "GET", f"/repositories/{alias}"
        )
        return response.status_code == 200

    async def register_repository(
        self, alias: str, remote: str, branch: str
    ) -> Dict[str, Any]:
        """
        Register a repository with Claude Server.

        Args:
            alias: Unique alias for the repository
            remote: Git remote URL
            branch: Default branch name

        Returns:
            Dictionary with registration result

        Raises:
            ClaudeServerError: On registration failure
        """
        response = await self._make_authenticated_request(
            "POST",
            "/repositories/register",
            json_data={"alias": alias, "remote": remote, "branch": branch},
        )

        if response.status_code in (200, 201):
            return response.json()
        else:
            raise ClaudeServerError(
                f"Repository registration failed: HTTP {response.status_code}"
            )

    async def create_job(
        self, prompt: str, repositories: List[str]
    ) -> Dict[str, Any]:
        """
        Create a new job with the given prompt.

        Args:
            prompt: The rendered prompt for the job
            repositories: List of repository aliases to use

        Returns:
            Dictionary with job info including job_id

        Raises:
            ClaudeServerError: On job creation failure
        """
        response = await self._make_authenticated_request(
            "POST",
            "/jobs",
            # Claude Server expects capitalized field names
            json_data={"prompt": prompt, "Repositories": repositories},
        )

        if response.status_code in (200, 201):
            return response.json()
        elif response.status_code >= 500:
            raise ClaudeServerError(
                f"Claude Server error: HTTP {response.status_code}"
            )
        else:
            raise ClaudeServerError(
                f"Job creation failed: HTTP {response.status_code}"
            )

    async def start_job(self, job_id: str) -> Dict[str, Any]:
        """
        Start execution of a created job.

        Args:
            job_id: The ID of the job to start

        Returns:
            Dictionary with updated job status

        Raises:
            ClaudeServerError: On job start failure
        """
        response = await self._make_authenticated_request(
            "POST", f"/jobs/{job_id}/start"
        )

        if response.status_code in (200, 201):
            return response.json()
        else:
            raise ClaudeServerError(f"Job start failed: HTTP {response.status_code}")

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get current job status from Claude Server.

        Args:
            job_id: The ID of the job to check

        Returns:
            Dictionary with job status and progress info

        Raises:
            ClaudeServerNotFoundError: If job not found (404)
            ClaudeServerError: If server error
        """
        response = await self._make_authenticated_request("GET", f"/jobs/{job_id}")

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise ClaudeServerNotFoundError(f"Job not found: {job_id}")
        else:
            raise ClaudeServerError(
                f"Failed to get job status: HTTP {response.status_code}"
            )

    async def get_job_conversation(self, job_id: str) -> Dict[str, Any]:
        """
        Get job conversation/result from Claude Server.

        Args:
            job_id: The ID of the job

        Returns:
            Dictionary with job result and conversation exchanges

        Raises:
            ClaudeServerNotFoundError: If job not found (404)
            ClaudeServerError: If server error
        """
        response = await self._make_authenticated_request(
            "GET", f"/jobs/{job_id}/conversation"
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise ClaudeServerNotFoundError(f"Job not found: {job_id}")
        else:
            raise ClaudeServerError(
                f"Failed to get job conversation: HTTP {response.status_code}"
            )
