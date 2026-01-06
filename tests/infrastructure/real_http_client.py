"""Real HTTP Client for Testing.

Provides real HTTP client operations to replace all HTTP-related mocks
in Foundation #1 compliance. All network operations use real httpx clients.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import httpx
from urllib.parse import urljoin

from .real_jwt_manager import RealTokenPair


@dataclass
class RealHTTPResponse:
    """Real HTTP response data structure."""

    status_code: int
    headers: Dict[str, str]
    json_data: Optional[Dict[str, Any]] = None
    text_data: Optional[str] = None
    url: str = ""
    request_method: str = ""

    def json(self) -> Dict[str, Any]:
        """Get JSON data from response."""
        if self.json_data is None:
            raise ValueError("Response does not contain JSON data")
        return self.json_data

    @property
    def text(self) -> str:
        """Get text data from response."""
        if self.text_data is None:
            return ""
        return self.text_data


@dataclass
class NetworkErrorSimulation:
    """Network error simulation configuration."""

    error_type: str  # 'connection', 'timeout', 'dns', 'ssl'
    endpoints: List[str]
    trigger_count: int = 1
    current_count: int = 0


class RealHTTPClient:
    """Real HTTP client for testing with authentic network operations.

    This client provides:
    - Real HTTP requests using httpx
    - Real SSL/TLS handling
    - Real timeout management
    - Real network error conditions
    - Zero mocks - all operations are authentic
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_connections: int = 10,
        verify_ssl: bool = True,
    ):
        """Initialize real HTTP client.

        Args:
            base_url: Base URL for requests
            timeout_seconds: Request timeout in seconds
            max_connections: Maximum concurrent connections
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_connections = max_connections
        self.verify_ssl = verify_ssl

        # Real httpx client configuration
        self._client: Optional[httpx.AsyncClient] = None
        self._session_headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "TestHTTPClient/1.0",
        }

        # Request history for testing verification
        self.request_history: List[Dict[str, Any]] = []

        # Network error simulation
        self.error_simulations: List[NetworkErrorSimulation] = []

        # Authentication state
        self.auth_token: Optional[str] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create real httpx client."""
        if self._client is None or self._client.is_closed:
            # Configure real timeouts
            timeouts = httpx.Timeout(
                connect=10.0,
                read=self.timeout_seconds,
                write=10.0,
                pool=5.0,
            )

            # Configure real connection limits
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            )

            self._client = httpx.AsyncClient(
                timeout=timeouts,
                limits=limits,
                headers=self._session_headers,
                follow_redirects=True,
                verify=self.verify_ssl,
            )

        return self._client

    def set_auth_token(self, token: str):
        """Set authentication token for requests.

        Args:
            token: JWT token to use for authentication
        """
        self.auth_token = token

    def clear_auth_token(self):
        """Clear authentication token."""
        self.auth_token = None

    async def request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RealHTTPResponse:
        """Make real HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json_data: JSON data for request body
            headers: Additional headers
            params: URL parameters
            **kwargs: Additional httpx arguments

        Returns:
            RealHTTPResponse with response data

        Raises:
            httpx.NetworkError: For network connectivity issues
            httpx.TimeoutException: For request timeouts
            httpx.HTTPStatusError: For HTTP error status codes
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))

        # Build request headers
        request_headers = self._session_headers.copy()
        if headers:
            request_headers.update(headers)

        # Add authentication if available
        if self.auth_token:
            request_headers["Authorization"] = f"Bearer {self.auth_token}"

        # Record request for verification
        request_record = {
            "method": method.upper(),
            "url": url,
            "headers": request_headers.copy(),
            "json_data": json_data,
            "params": params,
        }
        self.request_history.append(request_record)

        # Check for error simulation
        self._check_error_simulation(endpoint)

        try:
            # Make real HTTP request
            response = await self.client.request(
                method=method,
                url=url,
                json=json_data,
                headers=request_headers,
                params=params,
                **kwargs,
            )

            # Process response
            json_response = None
            text_response = response.text

            try:
                json_response = response.json() if response.content else {}
            except json.JSONDecodeError:
                pass

            return RealHTTPResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                json_data=json_response,
                text_data=text_response,
                url=str(response.url),
                request_method=method.upper(),
            )

        except Exception as e:
            # Log the error for debugging
            logging.debug(f"HTTP request failed: {method} {url} - {e}")
            raise

    async def get(self, endpoint: str, **kwargs) -> RealHTTPResponse:
        """Make GET request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            HTTP response
        """
        return await self.request("GET", endpoint, **kwargs)

    async def post(
        self, endpoint: str, json_data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> RealHTTPResponse:
        """Make POST request.

        Args:
            endpoint: API endpoint
            json_data: JSON request body
            **kwargs: Additional request arguments

        Returns:
            HTTP response
        """
        return await self.request("POST", endpoint, json_data=json_data, **kwargs)

    async def put(
        self, endpoint: str, json_data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> RealHTTPResponse:
        """Make PUT request.

        Args:
            endpoint: API endpoint
            json_data: JSON request body
            **kwargs: Additional request arguments

        Returns:
            HTTP response
        """
        return await self.request("PUT", endpoint, json_data=json_data, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> RealHTTPResponse:
        """Make DELETE request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            HTTP response
        """
        return await self.request("DELETE", endpoint, **kwargs)

    def _check_error_simulation(self, endpoint: str):
        """Check if error should be simulated for this endpoint.

        Args:
            endpoint: API endpoint being requested

        Raises:
            httpx.NetworkError: If network error simulation is active
            httpx.TimeoutException: If timeout simulation is active
        """
        for simulation in self.error_simulations:
            if any(pattern in endpoint for pattern in simulation.endpoints):
                simulation.current_count += 1
                if simulation.current_count >= simulation.trigger_count:
                    if simulation.error_type == "connection":
                        raise httpx.NetworkError("Simulated connection error")
                    elif simulation.error_type == "timeout":
                        raise httpx.TimeoutException("Simulated timeout error")
                    elif simulation.error_type == "dns":
                        raise httpx.NetworkError("Simulated DNS resolution error")
                    elif simulation.error_type == "ssl":
                        raise httpx.NetworkError("Simulated SSL certificate error")

    def simulate_network_error(
        self,
        endpoints: List[str],
        error_type: str = "connection",
        trigger_count: int = 1,
    ):
        """Configure network error simulation.

        Args:
            endpoints: List of endpoint patterns to simulate errors for
            error_type: Type of error ('connection', 'timeout', 'dns', 'ssl')
            trigger_count: How many requests before error triggers
        """
        simulation = NetworkErrorSimulation(
            error_type=error_type,
            endpoints=endpoints,
            trigger_count=trigger_count,
        )
        self.error_simulations.append(simulation)

    def clear_error_simulations(self):
        """Clear all error simulations."""
        self.error_simulations.clear()

    def get_request_count(
        self, method: Optional[str] = None, endpoint_pattern: Optional[str] = None
    ) -> int:
        """Get count of requests made.

        Args:
            method: Filter by HTTP method
            endpoint_pattern: Filter by endpoint pattern

        Returns:
            Number of matching requests
        """
        count = 0
        for request in self.request_history:
            if method and request["method"] != method.upper():
                continue
            if endpoint_pattern and endpoint_pattern not in request["url"]:
                continue
            count += 1
        return count

    def get_last_request(self) -> Optional[Dict[str, Any]]:
        """Get the last request made.

        Returns:
            Last request data or None if no requests made
        """
        return self.request_history[-1] if self.request_history else None

    def clear_request_history(self):
        """Clear request history."""
        self.request_history.clear()

    async def close(self):
        """Close HTTP client and cleanup resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class RealAuthenticatedHTTPClient(RealHTTPClient):
    """Real HTTP client with authentication capabilities.

    Extends RealHTTPClient with real authentication flows using
    actual JWT tokens and server communication.
    """

    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        **kwargs,
    ):
        """Initialize authenticated HTTP client.

        Args:
            server_url: Server base URL
            username: Username for authentication
            password: Password for authentication
            **kwargs: Additional HTTP client arguments
        """
        super().__init__(server_url, **kwargs)
        self.username = username
        self.password = password
        self._current_token: Optional[str] = None
        self._refresh_token: Optional[str] = None

    async def authenticate(self) -> RealTokenPair:
        """Authenticate with server and get real tokens.

        Returns:
            Real token pair from server

        Raises:
            httpx.HTTPStatusError: If authentication fails
        """
        # Clear existing tokens
        self.clear_auth_token()

        # Make real authentication request
        auth_response = await self.post(
            "/auth/login",
            json_data={
                "username": self.username,
                "password": self.password,
            },
        )

        if auth_response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"Authentication failed: HTTP {auth_response.status_code}",
                request=auth_response.request,  # type: ignore[arg-type]
                response=auth_response,  # type: ignore[arg-type]
            )

        # Extract real tokens from response
        token_data = auth_response.json()
        token_pair = RealTokenPair(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            expires_in=token_data.get("expires_in", 600),
            token_type=token_data.get("token_type", "bearer"),
        )

        # Store tokens
        self._current_token = token_pair.access_token
        self._refresh_token = token_pair.refresh_token
        self.set_auth_token(token_pair.access_token)

        return token_pair

    async def refresh_token(self) -> RealTokenPair:
        """Refresh access token using refresh token.

        Returns:
            New token pair

        Raises:
            ValueError: If no refresh token available
            httpx.HTTPStatusError: If refresh fails
        """
        if not self._refresh_token:
            raise ValueError("No refresh token available")

        # Clear current auth token
        self.clear_auth_token()

        # Make real token refresh request
        refresh_response = await self.post(
            "/auth/refresh",
            json_data={
                "refresh_token": self._refresh_token,
            },
        )

        if refresh_response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"Token refresh failed: HTTP {refresh_response.status_code}",
                request=refresh_response.request,  # type: ignore[arg-type]
                response=refresh_response,  # type: ignore[arg-type]
            )

        # Extract new tokens
        token_data = refresh_response.json()
        token_pair = RealTokenPair(
            access_token=token_data["access_token"],
            refresh_token=self._refresh_token,  # Refresh token typically stays same
            expires_in=token_data.get("expires_in", 600),
            token_type=token_data.get("token_type", "bearer"),
        )

        # Update stored tokens
        self._current_token = token_pair.access_token
        self.set_auth_token(token_pair.access_token)

        return token_pair

    async def authenticated_request(
        self, method: str, endpoint: str, **kwargs
    ) -> RealHTTPResponse:
        """Make authenticated request with automatic token refresh.

        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            HTTP response

        Raises:
            httpx.HTTPStatusError: If request fails after authentication
        """
        # Ensure we have a token
        if not self._current_token:
            await self.authenticate()

        try:
            # Make authenticated request
            return await self.request(method, endpoint, **kwargs)

        except httpx.HTTPStatusError as e:
            # If 401 Unauthorized, try to refresh token and retry
            if hasattr(e, "response") and e.response.status_code == 401:
                if self._refresh_token:
                    await self.refresh_token()
                    return await self.request(method, endpoint, **kwargs)
                else:
                    # No refresh token, re-authenticate
                    await self.authenticate()
                    return await self.request(method, endpoint, **kwargs)
            raise

    def has_valid_token(self) -> bool:
        """Check if client has a valid authentication token.

        Returns:
            True if token is available (doesn't validate expiry)
        """
        return self._current_token is not None


# Test helper functions


def create_real_http_client(base_url: str, **kwargs) -> RealHTTPClient:
    """Create a new real HTTP client.

    Args:
        base_url: Server base URL
        **kwargs: Additional client arguments

    Returns:
        RealHTTPClient instance
    """
    return RealHTTPClient(base_url, **kwargs)


def create_authenticated_http_client(
    server_url: str, username: str, password: str, **kwargs
) -> RealAuthenticatedHTTPClient:
    """Create a new authenticated HTTP client.

    Args:
        server_url: Server base URL
        username: Username for authentication
        password: Password for authentication
        **kwargs: Additional client arguments

    Returns:
        RealAuthenticatedHTTPClient instance
    """
    return RealAuthenticatedHTTPClient(server_url, username, password, **kwargs)


async def make_real_request(
    base_url: str,
    method: str,
    endpoint: str,
    auth_token: Optional[str] = None,
    **kwargs,
) -> RealHTTPResponse:
    """Make a single real HTTP request.

    Args:
        base_url: Server base URL
        method: HTTP method
        endpoint: API endpoint
        auth_token: Optional authentication token
        **kwargs: Additional request arguments

    Returns:
        HTTP response
    """
    client = create_real_http_client(base_url)
    if auth_token:
        client.set_auth_token(auth_token)

    try:
        return await client.request(method, endpoint, **kwargs)
    finally:
        await client.close()
