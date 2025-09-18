"""Base CIDX Remote API Client.

Provides common HTTP functionality, authentication, and token management
for all CIDX remote API operations.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, cast
import httpx
from pathlib import Path

from .jwt_token_manager import JWTTokenManager, TokenValidationError
from ..remote.token_manager import PersistentTokenManager, StoredToken
from ..remote.credential_manager import ProjectCredentialManager
from .network_error_handler import (
    NetworkErrorHandler,
    RetryConfig,
    NetworkConnectionError,
    NetworkTimeoutError,
    DNSResolutionError,
    SSLCertificateError,
    ServerError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Base exception for API client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.is_retryable: bool = True  # Default to retryable


class AuthenticationError(APIClientError):
    """Exception raised when authentication fails."""

    pass


class NetworkError(APIClientError):
    """Exception raised when network operations fail."""

    pass


# Import network-specific exceptions
ConnectionError = NetworkConnectionError
TimeoutError = NetworkTimeoutError


class TokenExpiredError(APIClientError):
    """Exception raised when JWT token has expired."""

    pass


class CircuitBreakerOpenError(APIClientError):
    """Exception raised when circuit breaker is open (blocking requests)."""

    pass


class CIDXRemoteAPIClient:
    """Base API client with authentication and common HTTP functionality."""

    def __init__(
        self,
        server_url: str,
        credentials: Dict[str, Any],
        project_root: Optional[Path] = None,
    ):
        """Initialize base API client with persistent token management.

        Args:
            server_url: Base URL of the CIDX server
            credentials: Encrypted credentials dictionary
            project_root: Project root for persistent token storage
        """
        self.server_url = server_url.rstrip("/")
        self.credentials = credentials
        self.project_root = project_root
        self.jwt_manager = JWTTokenManager()
        self._session: Optional[httpx.AsyncClient] = None
        self._current_token: Optional[str] = None
        self._auth_lock = asyncio.Lock()

        # Initialize persistent token manager if project root provided
        self._persistent_token_manager: Optional[PersistentTokenManager] = None
        if project_root and credentials.get("username"):
            try:
                credential_manager = ProjectCredentialManager()
                self._persistent_token_manager = PersistentTokenManager(
                    project_root=project_root,
                    credential_manager=credential_manager,
                    username=credentials["username"],
                    repo_path=str(project_root),
                    server_url=server_url,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize persistent token manager: {e}")

        # Circuit breaker state
        self._auth_failures = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_opened_at = 0.0
        self._circuit_breaker_timeout = 300  # 5 minutes

        # Request rate limiting
        self._request_semaphore = asyncio.Semaphore(10)  # 10 concurrent requests

        # Network error handling
        self._network_error_handler = NetworkErrorHandler()
        self._retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_multiplier=2.0,
            jitter_enabled=True,
        )

    @property
    def _credentials(self) -> Dict[str, Any]:
        """Provide access to credentials for resource isolation testing.

        Returns:
            Copy of credentials dictionary for testing purposes
        """
        return self.credentials.copy()

    @property
    def _server_url(self) -> str:
        """Provide access to server URL for resource isolation testing.

        Returns:
            Server URL for testing purposes
        """
        return self.server_url

    @property
    def session(self) -> httpx.AsyncClient:
        """Get or create HTTP session with optimized configuration."""
        if self._session is None or self._session.is_closed:
            # Configure timeouts according to requirements
            timeouts = httpx.Timeout(
                connect=10.0,  # 10s connect timeout
                read=30.0,  # 30s read timeout
                write=10.0,  # 10s write timeout
                pool=5.0,  # 5s pool timeout
            )

            # Configure connection limits for HTTP/2 pooling
            limits = httpx.Limits(
                max_connections=10,  # Total connections
                max_keepalive_connections=5,  # Keepalive connections
                keepalive_expiry=30.0,  # 30s keepalive expiry
            )

            self._session = httpx.AsyncClient(
                timeout=timeouts,
                limits=limits,
                headers={"Content-Type": "application/json"},
                follow_redirects=True,
                verify=True,  # SSL verification enforced
                http2=False,  # Disable HTTP/2 for now (requires h2 package)
            )
        return self._session

    def _check_circuit_breaker(self) -> None:
        """Check circuit breaker state and handle recovery.

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
        """
        if not self._circuit_breaker_open:
            return

        # Check if recovery timeout has passed
        elapsed = time.time() - self._circuit_breaker_opened_at
        if elapsed >= self._circuit_breaker_timeout:
            # Reset circuit breaker
            self._circuit_breaker_open = False
            self._auth_failures = 0
            logger.info("Circuit breaker recovered, allowing authentication attempts")
        else:
            remaining = self._circuit_breaker_timeout - elapsed
            raise CircuitBreakerOpenError(
                f"Authentication circuit breaker open. Recovery in {remaining:.1f} seconds"
            )

    def _record_auth_failure(self) -> None:
        """Record authentication failure and potentially open circuit breaker."""
        self._auth_failures += 1
        logger.warning(f"Authentication failure count: {self._auth_failures}")

        if self._auth_failures >= 5:
            self._circuit_breaker_open = True
            self._circuit_breaker_opened_at = time.time()
            logger.error(
                f"Circuit breaker opened after {self._auth_failures} failures. "
                f"Recovery timeout: {self._circuit_breaker_timeout} seconds"
            )

    def _record_auth_success(self) -> None:
        """Record successful authentication and reset failure count."""
        if self._auth_failures > 0:
            logger.info(
                f"Authentication succeeded, resetting failure count from {self._auth_failures}"
            )
        self._auth_failures = 0
        self._circuit_breaker_open = False

    async def _authenticate(self) -> str:
        """Authenticate with server and get JWT token with persistent storage.

        Returns:
            JWT access token

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network operation fails
            CircuitBreakerOpenError: If circuit breaker is open
        """
        # Check circuit breaker
        self._check_circuit_breaker()

        auth_endpoint = f"{self.server_url}/auth/login"

        auth_payload = {
            "username": self.credentials["username"],
            "password": self.credentials["password"],
        }

        try:
            response = await self.session.post(auth_endpoint, json=auth_payload)

            if response.status_code == 200:
                auth_response = response.json()
                token = auth_response.get("access_token")
                if not token or not isinstance(token, str):
                    raise AuthenticationError("No valid access token in response")

                # Type assertion after validation - token is guaranteed to be str here
                token = cast(str, token)

                # Record successful authentication
                self._record_auth_success()

                # Store token persistently if possible
                await self._store_token_persistently(token)

                return token

            elif response.status_code == 401:
                self._record_auth_failure()
                try:
                    error_detail = response.json().get("detail", "Invalid credentials")
                except json.JSONDecodeError:
                    error_detail = "Invalid credentials"
                raise AuthenticationError(f"Authentication failed: {error_detail}")

            else:
                self._record_auth_failure()
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except json.JSONDecodeError:
                    error_detail = f"HTTP {response.status_code}"
                raise AuthenticationError(f"Authentication error: {error_detail}")

        except httpx.NetworkError as e:
            self._record_auth_failure()
            try:
                self._network_error_handler.classify_network_error(e)
            except Exception as network_error:
                raise network_error
        except httpx.TimeoutException as e:
            self._record_auth_failure()
            try:
                self._network_error_handler.classify_network_error(e)
            except Exception as network_error:
                raise network_error
        except Exception as e:
            if isinstance(
                e, (AuthenticationError, NetworkError, CircuitBreakerOpenError)
            ):
                raise
            self._record_auth_failure()
            raise AuthenticationError(f"Unexpected error during authentication: {e}")

        # This should never be reached as all paths above either return or raise
        raise AuthenticationError("Unexpected code path in authentication")

    async def _store_token_persistently(self, token: str) -> None:
        """Store JWT token persistently if manager is available.

        Args:
            token: JWT token to store
        """
        if not self._persistent_token_manager:
            return

        try:
            # Get token expiration time
            expiry_time = self.jwt_manager.get_token_expiry_time(token)
            if not expiry_time:
                logger.warning(
                    "Token has no expiration time, cannot store persistently"
                )
                return

            # Create stored token
            stored_token = StoredToken(
                token=token,
                expires_at=expiry_time,
                created_at=datetime.now(timezone.utc),
                encrypted_data=b"",  # Will be set during encryption
            )

            # Store token
            self._persistent_token_manager.store_token(stored_token)
            logger.debug("Token stored persistently")

        except Exception as e:
            logger.warning(f"Failed to store token persistently: {e}")

    async def _load_persistent_token(self) -> Optional[str]:
        """Load JWT token from persistent storage if valid.

        Returns:
            Valid JWT token or None if not available
        """
        if not self._persistent_token_manager:
            return None

        try:
            stored_token = self._persistent_token_manager.load_token()
            if not stored_token:
                return None

            # Check if token is valid
            if self._persistent_token_manager.is_token_valid(stored_token):
                # Check if token expires soon (within 2 minutes)
                if not stored_token.expires_soon(threshold_minutes=2):
                    logger.debug("Loaded valid token from persistent storage")
                    return stored_token.token

            logger.debug("Persistent token is expired or expires soon")
            return None

        except Exception as e:
            logger.warning(f"Failed to load persistent token: {e}")
            return None

    async def _get_valid_token(self) -> str:
        """Get valid JWT token with persistent storage and automatic refresh.

        Returns:
            Valid JWT token

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network operation fails
        """
        async with self._auth_lock:
            # Check if we already have a valid token in memory
            if self._current_token:
                try:
                    # Validate the token
                    if self.jwt_manager.is_token_expired(self._current_token):
                        logger.debug("Current token is expired, clearing from memory")
                        self._current_token = None
                    elif self.jwt_manager.is_token_near_expiry(self._current_token):
                        logger.debug(
                            "Current token is near expiry, clearing from memory"
                        )
                        self._current_token = None
                    else:
                        # Token is still valid - return it immediately
                        logger.debug("Returning existing valid token")
                        return self._current_token
                except TokenValidationError:
                    logger.debug("Current token is invalid, clearing from memory")
                    self._current_token = None

            # Try to load from persistent storage if no valid token in memory
            if self._current_token is None:
                persistent_token = await self._load_persistent_token()
                if persistent_token:
                    self._current_token = persistent_token
                    logger.debug("Loaded persistent token")
                    return self._current_token

            # Need to authenticate - this is the critical section
            # Only one thread should reach this point due to the lock
            if self._current_token is None:
                logger.debug("No token found, authenticating...")
                self._current_token = await self._authenticate()
                logger.debug("Authentication complete")
                return self._current_token

            # Should never reach here, but return token if we have one
            return self._current_token

    async def _authenticated_request(
        self,
        method: str,
        endpoint: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Make authenticated HTTP request with rate limiting, automatic token management, and network error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            progress_callback: Optional callback for progress indication during retries
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response object

        Raises:
            AuthenticationError: If authentication fails
            NetworkConnectionError: If connection fails
            NetworkTimeoutError: If request times out
            DNSResolutionError: If DNS resolution fails
            SSLCertificateError: If SSL certificate verification fails
            ServerError: If server returns 5xx error
            RateLimitError: If rate limited (429)
            APIClientError: If API returns other error status
        """
        # Apply rate limiting
        async with self._request_semaphore:
            url = f"{self.server_url}{endpoint}"
            max_retries = 2
            retry_count = 0
            last_network_error = None

            while retry_count < max_retries:
                try:
                    # Get valid token
                    token = await self._get_valid_token()

                    # Add authorization header
                    headers = kwargs.pop("headers", {})
                    headers["Authorization"] = f"Bearer {token}"

                    # Make request
                    response = await self.session.request(
                        method, url, headers=headers, **kwargs
                    )

                    # Handle 401 Unauthorized - token might be invalid
                    if response.status_code == 401 and retry_count < max_retries - 1:
                        logger.debug("Received 401, invalidating tokens and retrying")
                        self._current_token = None
                        # Also clear persistent token if it exists
                        if self._persistent_token_manager:
                            try:
                                self._persistent_token_manager.delete_token()
                            except Exception as e:
                                logger.warning(f"Failed to clear persistent token: {e}")
                        retry_count += 1
                        continue

                    # Handle other error status codes using network error handler
                    if response.status_code >= 400:
                        # Create HTTPStatusError for classification
                        mock_request = type("MockRequest", (), {})()
                        http_error = httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=mock_request,
                            response=response,
                        )

                        try:
                            self._network_error_handler.classify_network_error(
                                http_error
                            )
                        except Exception as network_error:
                            # Store the network error for potential later propagation
                            last_network_error = network_error
                            # Check if retryable and we haven't exhausted retries
                            if (
                                retry_count < max_retries - 1
                                and self._network_error_handler.is_error_retryable(
                                    network_error
                                )
                            ):
                                delay = 1.0 * (2.0**retry_count)
                                if progress_callback:
                                    progress_callback(
                                        "Retrying after server error...",
                                        retry_count + 1,
                                        max_retries,
                                    )
                                await asyncio.sleep(delay)
                                retry_count += 1
                                continue
                            raise network_error

                    return response

                except (
                    httpx.NetworkError,
                    httpx.TimeoutException,
                    httpx.HTTPStatusError,
                ) as e:
                    # Use network error handler for classification
                    try:
                        self._network_error_handler.classify_network_error(e)
                    except Exception as network_error:
                        # Store the network error for potential later propagation
                        last_network_error = network_error
                        # Check if this is a retryable error and we can retry
                        if (
                            retry_count < max_retries - 1
                            and self._network_error_handler.is_error_retryable(
                                network_error
                            )
                        ):
                            # Use exponential backoff for retries
                            delay = 1.0 * (2.0**retry_count)
                            if progress_callback:
                                progress_callback(
                                    "Retrying after network error...",
                                    retry_count + 1,
                                    max_retries,
                                )
                            await asyncio.sleep(delay)
                            retry_count += 1
                            continue
                        raise network_error
                except Exception as e:
                    if isinstance(
                        e,
                        (
                            AuthenticationError,
                            NetworkError,
                            APIClientError,
                            NetworkConnectionError,
                            NetworkTimeoutError,
                            DNSResolutionError,
                            SSLCertificateError,
                            ServerError,
                            RateLimitError,
                        ),
                    ):
                        raise
                    raise APIClientError(f"Unexpected error: {e}")

            # If we get here, all retries failed
            # If we have a network error, propagate it instead of generic auth error
            if last_network_error:
                raise last_network_error
            raise AuthenticationError("Failed to authenticate after retries")

    async def get(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make authenticated GET request.

        Args:
            endpoint: API endpoint path
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response object

        Raises:
            AuthenticationError: If authentication fails
            NetworkConnectionError: If connection fails
            NetworkTimeoutError: If request times out
            DNSResolutionError: If DNS resolution fails
            SSLCertificateError: If SSL certificate verification fails
            ServerError: If server returns 5xx error
            RateLimitError: If rate limited (429)
            APIClientError: If API returns other error status
        """
        return await self._authenticated_request("GET", endpoint, **kwargs)

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status from server.

        Args:
            job_id: Job ID to get status for

        Returns:
            Job status data from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        try:
            response = await self._authenticated_request(
                "GET", f"/api/jobs/{job_id}/status"
            )

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 404:
                raise APIClientError(f"Job not found: {job_id}", 404)
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
                    f"Failed to get job status: {error_detail}", response.status_code
                )

        except (NetworkError, AuthenticationError):
            raise
        except Exception as e:
            if isinstance(e, APIClientError):
                raise
            raise APIClientError(f"Unexpected error getting job status: {e}")

    async def cancel_job(
        self, job_id: str, reason: str = "User requested cancellation"
    ) -> Dict[str, Any]:
        """Cancel a job on the server.

        Args:
            job_id: Job ID to cancel
            reason: Reason for cancellation

        Returns:
            Cancellation response data from server

        Raises:
            APIClientError: If API request fails
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        try:
            cancel_payload = {"reason": reason}
            response = await self._authenticated_request(
                "POST", f"/api/jobs/{job_id}/cancel", json=cancel_payload
            )

            if response.status_code == 200:
                return dict(response.json())
            elif response.status_code == 404:
                raise APIClientError(f"Job not found: {job_id}", 404)
            elif response.status_code == 409:
                # Job cannot be cancelled (already completed/failed/cancelled)
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "Job cannot be cancelled")
                except Exception:
                    error_detail = "Job cannot be cancelled"
                raise APIClientError(f"Cannot cancel job {job_id}: {error_detail}", 409)
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
                    f"Failed to cancel job: {error_detail}", response.status_code
                )

        except (NetworkError, AuthenticationError):
            raise
        except APIClientError:
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error cancelling job: {e}")

    async def close(self) -> None:
        """Close HTTP session and clean up resources with security cleanup."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()

        # Clean up sensitive data from memory
        if self._persistent_token_manager:
            self._persistent_token_manager.cleanup_sensitive_data()

        # Clear current token securely using proper Foundation #8 pattern
        if self._current_token:
            # Convert string token to bytearray for secure memory cleanup
            token_bytes = bytearray(self._current_token.encode("utf-8"))

            # Proper secure memory cleanup - multiple overwrite iterations
            for _ in range(3):
                for i in range(len(token_bytes)):
                    token_bytes[i] = 0
            token_bytes.clear()

            # Clear the string reference
            self._current_token = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __del__(self):
        """Cleanup when object is destroyed."""
        if self._session and not self._session.is_closed:
            # Cannot use await in __del__, so we'll just log a warning
            logger.warning("CIDXRemoteAPIClient was not properly closed")


class EncryptedCredentials:
    """Handles encrypted credential storage and retrieval.

    This is a placeholder implementation. In production, this would
    handle actual encryption/decryption of credentials.
    """

    def __init__(self, credentials: Dict[str, Any]):
        """Initialize with credentials dictionary.

        Args:
            credentials: Credentials to store
        """
        self._credentials = credentials

    def decrypt(self) -> Dict[str, Any]:
        """Decrypt and return credentials.

        Returns:
            Decrypted credentials dictionary
        """
        # Placeholder implementation - in production this would decrypt
        return self._credentials.copy()

    @classmethod
    def from_config(cls, config_path: Path) -> "EncryptedCredentials":
        """Load encrypted credentials from configuration file.

        Args:
            config_path: Path to configuration file

        Returns:
            EncryptedCredentials instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config format is invalid
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)

            encrypted_creds = config_data.get("encrypted_credentials")
            if not encrypted_creds:
                raise ValueError("No encrypted_credentials found in configuration")

            return cls(encrypted_creds)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load credentials: {e}")
