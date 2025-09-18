"""Network Error Handler for CIDX Remote API Client.

Provides comprehensive network error classification, retry logic with exponential backoff,
and user guidance system for network failures in remote repository linking mode.
"""

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any, Optional, List, Callable, cast

import httpx

logger = logging.getLogger(__name__)


@dataclass
class UserGuidance:
    """User guidance information for network errors."""

    error_type: str
    troubleshooting_steps: List[str]
    contact_info: Optional[str] = None
    additional_notes: List[str] = field(default_factory=list)

    def format_for_console(self) -> str:
        """Format guidance for rich console output."""
        content = []
        content.append(f"[bold red]Error Type:[/bold red] {self.error_type}")
        content.append("")
        content.append("[bold yellow]Troubleshooting Steps:[/bold yellow]")

        for i, step in enumerate(self.troubleshooting_steps, 1):
            content.append(f"{i}. {step}")

        if self.additional_notes:
            content.append("")
            content.append("[bold blue]Additional Notes:[/bold blue]")
            for note in self.additional_notes:
                content.append(f"• {note}")

        if self.contact_info:
            content.append("")
            content.append(f"[bold green]Support:[/bold green] {self.contact_info}")

        return "\n".join(content)


@dataclass
class RetryConfig:
    """Configuration for retry logic with exponential backoff."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_enabled: bool = True


class NetworkConnectionError(Exception):
    """Exception raised for connection-related network failures."""

    def __init__(self, message: str, user_guidance: Optional[str] = None):
        super().__init__(message)
        self.user_guidance = user_guidance or ""


class NetworkTimeoutError(Exception):
    """Exception raised for timeout-related network failures."""

    def __init__(self, message: str, user_guidance: Optional[str] = None):
        super().__init__(message)
        self.user_guidance = user_guidance or ""


class DNSResolutionError(Exception):
    """Exception raised for DNS resolution failures."""

    def __init__(self, message: str, user_guidance: Optional[str] = None):
        super().__init__(message)
        self.user_guidance = user_guidance or ""


class SSLCertificateError(Exception):
    """Exception raised for SSL certificate verification failures."""

    def __init__(self, message: str, user_guidance: Optional[str] = None):
        super().__init__(message)
        self.user_guidance = user_guidance or ""


class ServerError(Exception):
    """Exception raised for server-side errors (5xx responses)."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        user_guidance: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.user_guidance = user_guidance or ""
        self.is_retryable = True


class RateLimitError(Exception):
    """Exception raised for rate limiting errors (429 responses)."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        user_guidance: Optional[str] = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.user_guidance = user_guidance or ""
        self.is_retryable = True


class UserGuidanceProvider:
    """Provides user guidance for different network error scenarios."""

    def __init__(self):
        self._guidance_mapping = {
            NetworkConnectionError: self._get_connection_error_guidance,
            DNSResolutionError: self._get_dns_resolution_guidance,
            SSLCertificateError: self._get_ssl_certificate_guidance,
            NetworkTimeoutError: self._get_timeout_guidance,
            ServerError: self._get_server_error_guidance,
            RateLimitError: self._get_rate_limit_guidance,
        }

    def get_guidance(self, error: Exception) -> UserGuidance:
        """Get user guidance for a specific error."""
        error_type = type(error)
        guidance_func = self._guidance_mapping.get(
            error_type, self._get_generic_guidance
        )
        return cast(UserGuidance, guidance_func(error))

    def _get_connection_error_guidance(
        self, error: NetworkConnectionError
    ) -> UserGuidance:
        """Get guidance for connection errors."""
        return UserGuidance(
            error_type="Network Connection Error",
            troubleshooting_steps=[
                "Check if the CIDX server is running and accessible",
                "Verify the server URL is correct",
                "Check your firewall settings",
                "Verify network connectivity to the server",
                "Try connecting to the server from another machine",
            ],
            contact_info="Contact your system administrator if the problem persists",
            additional_notes=[
                "This error typically indicates the server is not reachable",
                "Check server logs to verify the service is running",
            ],
        )

    def _get_dns_resolution_guidance(self, error: DNSResolutionError) -> UserGuidance:
        """Get guidance for DNS resolution errors."""
        return UserGuidance(
            error_type="DNS Resolution Error",
            troubleshooting_steps=[
                "Check your internet connection",
                "Verify the server hostname is correct",
                "Try using an IP address instead of hostname",
                "Check your DNS server settings",
                "Try flushing your DNS cache",
            ],
            additional_notes=[
                "This error means your computer cannot find the server address",
                "DNS resolution issues are often temporary",
            ],
        )

    def _get_ssl_certificate_guidance(self, error: SSLCertificateError) -> UserGuidance:
        """Get guidance for SSL certificate errors."""
        return UserGuidance(
            error_type="SSL Certificate Error",
            troubleshooting_steps=[
                "Check if the server certificate is valid and not expired",
                "Verify the server hostname matches the certificate",
                "Check if you need to update your certificate store",
                "Contact your system administrator",
            ],
            contact_info="Contact your system administrator for certificate issues",
            additional_notes=[
                "SSL certificate errors prevent secure connections",
                "Do not disable certificate verification without proper security review",
            ],
        )

    def _get_timeout_guidance(self, error: NetworkTimeoutError) -> UserGuidance:
        """Get guidance for timeout errors."""
        return UserGuidance(
            error_type="Network Timeout Error",
            troubleshooting_steps=[
                "Check your network connection speed and stability",
                "Try again - this may be a temporary issue",
                "Check if the server is under heavy load",
                "Consider increasing timeout settings if problem persists",
            ],
            additional_notes=[
                "Timeout errors are often temporary",
                "Slow network connections can cause timeouts",
            ],
        )

    def _get_server_error_guidance(self, error: ServerError) -> UserGuidance:
        """Get guidance for server errors."""
        return UserGuidance(
            error_type="Server Error",
            troubleshooting_steps=[
                "The server is experiencing internal issues",
                "Please wait a few minutes and try again",
                "Check server status page if available",
                "Contact server administrator if problem persists",
            ],
            contact_info="Contact server administrator for persistent server errors",
            additional_notes=[
                "Server errors indicate issues on the server side",
                "These errors are typically temporary",
            ],
        )

    def _get_rate_limit_guidance(self, error: RateLimitError) -> UserGuidance:
        """Get guidance for rate limiting errors."""
        retry_after = getattr(error, "retry_after", 60)
        return UserGuidance(
            error_type="Rate Limit Error",
            troubleshooting_steps=[
                "You are sending requests too quickly",
                f"Wait {retry_after} seconds before trying again",
                "Reduce the frequency of your requests",
                "Consider implementing request throttling",
            ],
            additional_notes=[
                "Rate limiting protects servers from excessive requests",
                "This error is temporary and will resolve after waiting",
            ],
        )

    def _get_generic_guidance(self, error: Exception) -> UserGuidance:
        """Get generic guidance for unknown errors."""
        return UserGuidance(
            error_type="Unknown Network Error",
            troubleshooting_steps=[
                "Check your network connection",
                "Verify the server is accessible",
                "Try again in a few minutes",
                "Contact support if the problem persists",
            ],
            contact_info="Contact technical support for assistance",
        )


class NetworkErrorHandler:
    """Handles network error classification and retry logic."""

    def __init__(self):
        self.guidance_provider = UserGuidanceProvider()
        self._dns_error_patterns = [
            r"name.*resolution.*failed",
            r"name.*or.*service.*not.*known",
            r"nodename.*nor.*servname.*provided",
            r"temporary.*failure.*in.*name.*resolution",
        ]
        self._connection_error_patterns = [
            r"connection.*refused",
            r"connection.*reset",
            r"network.*is.*unreachable",
            r"no.*route.*to.*host",
        ]
        self._ssl_error_patterns = [
            r"ssl.*certificate.*verification.*failed",
            r"certificate.*verify.*failed",
            r"ssl.*handshake.*failed",
            r"bad.*certificate",
        ]

    def classify_network_error(self, error: Exception) -> None:
        """Classify network error and raise appropriate specific exception.

        Args:
            error: The original httpx exception

        Raises:
            Specific network error exception based on classification
        """
        error_message = str(error).lower()

        # Handle httpx-specific exceptions
        if isinstance(error, httpx.ConnectError):
            self._handle_connect_error(error, error_message)
        elif isinstance(
            error,
            (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
            ),
        ):
            self._handle_timeout_error(error, error_message)
        elif isinstance(error, httpx.HTTPStatusError):
            self._handle_http_status_error(error)
        elif isinstance(error, httpx.TimeoutException):
            self._handle_timeout_error(error, error_message)
        elif isinstance(error, httpx.NetworkError):
            self._handle_generic_network_error(error, error_message)
        else:
            # Unknown error - raise generic network error
            guidance = self.guidance_provider.get_guidance(error)
            raise NetworkConnectionError(
                f"Unknown network error: {error}",
                user_guidance=guidance.format_for_console(),
            )

    def _handle_connect_error(
        self, error: httpx.ConnectError, error_message: str
    ) -> None:
        """Handle connection errors with specific classification."""
        guidance = None

        # Check for DNS resolution errors
        if any(
            re.search(pattern, error_message) for pattern in self._dns_error_patterns
        ):
            dns_error = DNSResolutionError(
                "Cannot resolve server address. Check your internet connection and server URL."
            )
            guidance = self.guidance_provider.get_guidance(dns_error)
            dns_error.user_guidance = guidance.format_for_console()
            raise dns_error

        # Check for SSL certificate errors
        if any(
            re.search(pattern, error_message) for pattern in self._ssl_error_patterns
        ):
            ssl_error = SSLCertificateError(
                "SSL certificate verification failed. Server may be using invalid certificate."
            )
            guidance = self.guidance_provider.get_guidance(ssl_error)
            ssl_error.user_guidance = guidance.format_for_console()
            raise ssl_error

        # Check for connection refused/reset errors
        if any(
            re.search(pattern, error_message)
            for pattern in self._connection_error_patterns
        ):
            conn_error = NetworkConnectionError(
                "Cannot connect to server. Check if server is running and accessible."
            )
            guidance = self.guidance_provider.get_guidance(conn_error)
            conn_error.user_guidance = guidance.format_for_console()
            raise conn_error

        # Generic connection error
        conn_error = NetworkConnectionError(f"Connection failed: {error}")
        guidance = self.guidance_provider.get_guidance(conn_error)
        conn_error.user_guidance = guidance.format_for_console()
        raise conn_error

    def _handle_timeout_error(self, error: Exception, error_message: str) -> None:
        """Handle timeout errors."""
        if "connect" in error_message:
            timeout_error = NetworkTimeoutError(
                "Connection timed out. Check your network connection or try again later."
            )
        else:
            timeout_error = NetworkTimeoutError(
                "Request timed out. Check your network connection or try again later."
            )

        guidance = self.guidance_provider.get_guidance(timeout_error)
        timeout_error.user_guidance = guidance.format_for_console()
        raise timeout_error

    def _handle_http_status_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP status errors (4xx, 5xx)."""

        status_code = error.response.status_code

        try:
            error_detail = error.response.json().get("detail", f"HTTP {status_code}")
        except (json.JSONDecodeError, AttributeError):
            error_detail = (
                error.response.text
                if hasattr(error.response, "text")
                else f"HTTP {status_code}"
            )

        # Handle rate limiting (429)
        if status_code == 429:
            retry_after = None
            if (
                hasattr(error.response, "headers")
                and "Retry-After" in error.response.headers
            ):
                try:
                    retry_after = int(error.response.headers["Retry-After"])
                except ValueError:
                    retry_after = 60  # Default to 60 seconds

            rate_limit_error = RateLimitError(error_detail, retry_after=retry_after)
            guidance = self.guidance_provider.get_guidance(rate_limit_error)
            rate_limit_error.user_guidance = guidance.format_for_console()
            raise rate_limit_error

        # Handle authentication errors (401)
        elif status_code == 401:
            # Import here to avoid circular dependency
            from ..api_clients.base_client import AuthenticationError

            auth_error = AuthenticationError(f"Authentication failed: {error_detail}")
            raise auth_error

        # Handle server errors (5xx)
        elif 500 <= status_code < 600:
            server_error = ServerError(
                f"Server is experiencing issues: {error_detail}",
                status_code=status_code,
            )
            guidance = self.guidance_provider.get_guidance(server_error)
            server_error.user_guidance = guidance.format_for_console()
            raise server_error

        # Handle other client errors (4xx)
        else:
            # Import here to avoid circular dependency
            from ..api_clients.base_client import APIClientError

            client_error = APIClientError(error_detail, status_code=status_code)
            client_error.is_retryable = False
            raise client_error

    def _handle_generic_network_error(
        self, error: httpx.NetworkError, error_message: str
    ) -> None:
        """Handle generic network errors."""
        conn_error = NetworkConnectionError(f"Network error: {error}")
        guidance = self.guidance_provider.get_guidance(conn_error)
        conn_error.user_guidance = guidance.format_for_console()
        raise conn_error

    def is_error_retryable(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        This method implements a conservative retry policy:
        - Only retry errors that are likely to be transient
        - Don't retry errors that indicate permanent failures
        """
        # Server errors (5xx) are retryable - servers can recover
        if isinstance(error, ServerError):
            return True

        # Rate limit errors are retryable - limits reset over time
        if isinstance(error, RateLimitError):
            return True

        # Timeout errors are retryable - might be temporary network congestion
        if isinstance(error, NetworkTimeoutError):
            return True

        # DNS resolution errors might be temporary - retry with caution
        if isinstance(error, DNSResolutionError):
            return True

        # Connection errors should be retryable for transient failures
        # but not retryable for permanent failures like "connection refused"
        if isinstance(error, NetworkConnectionError):
            # Check if it's a permanent failure
            error_msg = str(error).lower()
            if "connection refused" in error_msg:
                return False
            # Other connection errors might be transient
            return True

        # SSL certificate errors are generally not retryable
        if isinstance(error, SSLCertificateError):
            return False

        # Authentication errors are not retryable - use safe import to avoid circular dependency
        try:
            from ..api_clients.base_client import AuthenticationError, APIClientError

            if isinstance(error, AuthenticationError):
                return False
            # Client errors (4xx except 429) are not retryable
            if isinstance(error, APIClientError):
                return getattr(error, "is_retryable", False)
        except ImportError:
            # Handle case where base_client isn't available yet
            # Check by class name to avoid import issues
            if error.__class__.__name__ == "AuthenticationError":
                return False
            if error.__class__.__name__ == "APIClientError":
                return getattr(error, "is_retryable", False)

        # Default to non-retryable for unknown errors
        return False

    async def retry_with_backoff(
        self,
        operation: Callable[[], Any],
        config: RetryConfig,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Any:
        """Execute operation with retry logic and exponential backoff.

        Args:
            operation: Async function to execute
            config: Retry configuration
            progress_callback: Optional callback for progress indication

        Returns:
            Result of successful operation

        Raises:
            Original exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(config.max_retries + 1):  # +1 for initial attempt
            try:
                return await operation()
            except Exception as e:
                last_exception = e

                # Check if error is retryable
                if not self.is_error_retryable(e):
                    raise

                # If this was the last attempt, raise the exception
                if attempt == config.max_retries:
                    raise

                # Calculate delay for next retry
                delay = min(
                    config.initial_delay * (config.backoff_multiplier**attempt),
                    config.max_delay,
                )

                # Add jitter if enabled
                if config.jitter_enabled:
                    jitter = delay * 0.1 * random.random()  # Up to 10% jitter
                    delay = delay + jitter

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(
                        "Retrying after connection error...",
                        attempt + 1,
                        config.max_retries,
                    )

                # Wait before retrying - for long delays, provide additional progress updates
                if delay >= 4.0 and progress_callback:
                    # For long delays (>=4s), provide progress updates every 2 seconds
                    chunks = max(1, int(delay // 2))  # Update every ~2 seconds
                    chunk_delay = delay / chunks
                    for i in range(chunks):
                        if (
                            i > 0
                        ):  # Don't call progress on first chunk since we called it above
                            progress_callback(
                                f"Waiting... ({i+1}/{chunks})",
                                attempt + 1,
                                config.max_retries,
                            )
                        await asyncio.sleep(chunk_delay)
                else:
                    await asyncio.sleep(delay)

        # This should never be reached
        if last_exception:
            raise last_exception
