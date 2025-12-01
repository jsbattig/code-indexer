"""HTTP client for forwarding requests to CIDX server.

This module handles HTTP communication with the CIDX server, including
Bearer token authentication, SSE streaming, and error handling.
"""

from __future__ import annotations
from typing import Union, Optional
from pathlib import Path
import asyncio
import json
import os
import sys
import tempfile

import httpx


class HttpError(Exception):
    """HTTP transport error."""

    pass


class TimeoutError(HttpError):
    """Request timeout error."""

    pass


class BridgeHttpClient:
    """HTTP client for forwarding JSON-RPC requests to CIDX server.

    Args:
        server_url: Base URL of CIDX server
        bearer_token: Bearer token for authentication
        timeout: Request timeout in seconds
        refresh_token: Refresh token for automatic token renewal (optional)
        config_path: Path to config file for persisting updated tokens (optional)
    """

    def __init__(
        self,
        server_url: str,
        bearer_token: str,
        timeout: int,
        refresh_token: Optional[str] = None,
        config_path: Optional[Path] = None,
    ):
        self.server_url = server_url
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.refresh_token = refresh_token
        self.config_path = config_path
        self._client = None
        self._refresh_lock: Optional[asyncio.Lock] = None

    def get_mcp_endpoint_url(self) -> str:
        """Get full URL to MCP endpoint."""
        return f"{self.server_url}/mcp"

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {"Authorization": f"Bearer {self.bearer_token}"}

    def get_request_headers(self) -> dict[str, str]:
        """Get all request headers including auth, content type, and accept."""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }

    async def forward_request(self, request_data: dict) -> dict:
        """Forward JSON-RPC request to CIDX server.

        Supports both SSE streaming and JSON responses.
        Automatically refreshes token on 401 errors if refresh_token is available.

        Args:
            request_data: JSON-RPC request as dictionary

        Returns:
            JSON-RPC response as dictionary

        Raises:
            HttpError: For HTTP transport errors or non-200 responses
            TimeoutError: For request timeouts
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        url = self.get_mcp_endpoint_url()
        headers = self.get_request_headers()

        # Track if we've already attempted a refresh (prevent infinite loops)
        refresh_attempted = False

        try:
            # _client is guaranteed to be non-None after the check above
            assert self._client is not None
            response = await self._client.post(url, json=request_data, headers=headers)

            # Handle authentication errors
            if response.status_code == 401:
                # Try to refresh token if available and not already attempted
                if self.refresh_token and not refresh_attempted:
                    refresh_attempted = True

                    # Refresh token
                    await self._refresh_access_token()

                    # Retry request with new token
                    headers = self.get_request_headers()
                    response = await self._client.post(
                        url, json=request_data, headers=headers
                    )

                    # If still 401 after refresh, raise error
                    if response.status_code == 401:
                        raise HttpError(
                            f"Authentication failed: {response.status_code} {response.text}"
                        )
                else:
                    # No refresh_token available - try auto-login
                    try:
                        await self._attempt_auto_login()

                        # Retry request with new token from auto-login
                        headers = self.get_request_headers()
                        response = await self._client.post(
                            url, json=request_data, headers=headers
                        )

                        # If still 401 after auto-login, raise error
                        if response.status_code == 401:
                            raise HttpError(
                                f"Authentication failed: {response.status_code} {response.text}"
                            )
                    except HttpError:
                        # Auto-login failed or no credentials - raise original auth error
                        raise HttpError(
                            f"Authentication failed: {response.status_code} {response.text}"
                        )

            # Handle server errors
            if response.status_code >= 500:
                raise HttpError(f"Server error: {response.status_code} {response.text}")

            # Handle other non-200 responses
            if response.status_code != 200:
                raise HttpError(f"HTTP error {response.status_code}: {response.text}")

            # Check Content-Type to determine response format
            content_type = response.headers.get("Content-Type", "")

            if content_type.startswith("text/event-stream"):
                # Process SSE streaming response
                return await self._process_sse_stream(response, request_data.get("id"))
            else:
                # Process standard JSON response
                result: dict = response.json()
                return result

        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"Request timed out after {self.timeout} seconds: {str(e)}"
            ) from e

        except httpx.ConnectError as e:
            raise HttpError(f"Connection failed to {self.server_url}: {str(e)}") from e

        except httpx.NetworkError as e:
            raise HttpError(
                f"Network error connecting to {self.server_url}: {str(e)}"
            ) from e

        except httpx.HTTPError as e:
            raise HttpError(f"HTTP error: {str(e)}") from e

    async def _process_sse_stream(
        self, response: httpx.Response, request_id: Union[int, str, None]
    ) -> dict:
        """Process SSE streaming response.

        Args:
            response: httpx Response with SSE content
            request_id: JSON-RPC request ID

        Returns:
            JSON-RPC response as dictionary
        """
        # Lazy import to avoid startup overhead
        from .sse_parser import SseParser, SseParseError, SseStreamError
        from .protocol import create_error_response, INTERNAL_ERROR

        parser = SseParser()

        try:
            # Parse SSE events line by line
            content = response.text
            lines = content.split("\n")

            for line in lines:
                line = line.strip()

                # Skip empty lines (SSE event separators)
                if not line:
                    continue

                # Parse event
                event = parser.parse_event(line)

                if event["type"] == "chunk":
                    parser.buffer_chunk(event["content"])

                elif event["type"] == "complete":
                    result = parser.assemble_results(event["content"])
                    return {"jsonrpc": "2.0", "result": result, "id": request_id}

                elif event["type"] == "error":
                    error_data = event["error"]
                    error_response = create_error_response(
                        request_id,
                        error_data["code"],
                        error_data["message"],
                        error_data.get("data"),
                    )
                    return error_response.to_dict()

            # Stream ended without complete event
            parser.validate_stream_completed()

        except SseParseError as e:
            error_response = create_error_response(
                request_id, INTERNAL_ERROR, f"SSE parsing error: {str(e)}"
            )
            return error_response.to_dict()

        except SseStreamError as e:
            error_response = create_error_response(request_id, INTERNAL_ERROR, str(e))
            return error_response.to_dict()

        # Should never reach here
        error_response = create_error_response(
            request_id, INTERNAL_ERROR, "Unexpected SSE stream termination"
        )
        return error_response.to_dict()

    async def _attempt_auto_login(self) -> None:
        """Attempt auto-login using stored credentials.

        Updates self.bearer_token and self.refresh_token with new values.
        If config_path is set, persists updated tokens to config file atomically.

        Raises:
            HttpError: If auto-login fails or credentials unavailable
        """
        try:
            from .auto_login import attempt_auto_login
            from .credential_storage import credentials_exist

            if not credentials_exist():
                raise HttpError("No stored credentials available for auto-login")

            print("Attempting auto-login...", file=sys.stderr)
            new_access_token, new_refresh_token = await attempt_auto_login(
                self.server_url, self.timeout
            )

            # Update tokens in memory
            self.bearer_token = new_access_token
            self.refresh_token = new_refresh_token

            # Persist to config file if config_path is set
            if self.config_path is not None:
                await self._update_config_file(new_access_token, new_refresh_token)

        except Exception as e:
            raise HttpError(f"Auto-login failed: {str(e)}") from e

    async def _refresh_access_token(self) -> None:
        """Refresh access token using refresh token.

        Updates self.bearer_token and self.refresh_token with new values.
        If config_path is set, persists updated tokens to config file atomically.

        Raises:
            HttpError: If refresh fails or refresh_token is invalid
        """
        if self.refresh_token is None:
            raise HttpError("Cannot refresh token - no refresh_token available")

        refresh_url = f"{self.server_url}/auth/refresh"

        try:
            # Use existing client or create new one
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self.timeout)

            assert self._client is not None
            response = await self._client.post(
                refresh_url,
                json={"refresh_token": self.refresh_token},
                headers={"Content-Type": "application/json"},
            )

            # Handle 401 - refresh token expired - try auto-login
            if response.status_code == 401:
                try:
                    await self._attempt_auto_login()
                    return  # Success - token refreshed via auto-login
                except Exception as e:
                    # Auto-login failed - log and continue to raise original error
                    print(f"Auto-login failed: {str(e)}", file=sys.stderr)
                    raise HttpError(
                        "Refresh token expired - re-authentication required"
                    )

            # Handle other errors
            if response.status_code >= 500:
                raise HttpError(
                    f"Token refresh failed: {response.status_code} {response.text}"
                )

            if response.status_code != 200:
                raise HttpError(
                    f"Token refresh failed: {response.status_code} {response.text}"
                )

            # Parse response
            try:
                result = response.json()
            except Exception as e:
                raise HttpError(
                    f"Token refresh failed: Invalid JSON response: {str(e)}"
                )

            # Validate response has required fields
            if "access_token" not in result:
                raise HttpError("Invalid refresh response: missing access_token")

            # Update tokens in memory
            new_access_token = result["access_token"]
            new_refresh_token = result.get("refresh_token", self.refresh_token)

            self.bearer_token = new_access_token
            self.refresh_token = new_refresh_token

            # Log refresh event to stderr (for Claude Desktop debugging)
            # Only log first 20 chars of token for security
            print(f"Token refreshed: {new_access_token[:20]}...", file=sys.stderr)

            # Persist to config file if config_path is set
            if self.config_path is not None:
                await self._update_config_file(new_access_token, new_refresh_token)

        except httpx.ConnectError as e:
            raise HttpError(f"Token refresh failed: Connection error: {str(e)}") from e

        except httpx.NetworkError as e:
            raise HttpError(f"Token refresh failed: Network error: {str(e)}") from e

        except httpx.HTTPError as e:
            raise HttpError(f"Token refresh failed: HTTP error: {str(e)}") from e

    async def _update_config_file(
        self, new_access_token: str, new_refresh_token: str
    ) -> None:
        """Update config file with new tokens atomically.

        Args:
            new_access_token: New access token to persist
            new_refresh_token: New refresh token to persist
        """
        if self.config_path is None:
            return

        # Lazy-initialize lock if needed
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()

        async with self._refresh_lock:
            try:
                # Read existing config
                with open(self.config_path) as f:
                    config = json.load(f)

                # Update tokens
                config["bearer_token"] = new_access_token
                config["refresh_token"] = new_refresh_token

                # Write atomically: temp file + rename
                temp_fd, temp_path = tempfile.mkstemp(
                    suffix=".json", dir=self.config_path.parent
                )
                try:
                    with os.fdopen(temp_fd, "w") as f:
                        json.dump(config, f, indent=2)

                    # Set secure permissions (owner read/write only)
                    os.chmod(temp_path, 0o600)

                    # Atomic replace - works correctly on both Unix and Windows
                    # Note: os.rename() fails on Windows if destination exists,
                    # but os.replace() atomically replaces on all platforms
                    os.replace(temp_path, self.config_path)

                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

            except Exception as e:
                # Log error but don't fail the request
                print(
                    f"Warning: Failed to update config file: {str(e)}", file=sys.stderr
                )

    async def close(self):
        """Close HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        await self.close()
