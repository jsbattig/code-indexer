"""HTTP client for forwarding requests to CIDX server.

This module handles HTTP communication with the CIDX server, including
Bearer token authentication, SSE streaming, and error handling.
"""

from __future__ import annotations
from typing import Union

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
    """

    def __init__(self, server_url: str, bearer_token: str, timeout: int):
        self.server_url = server_url
        self.bearer_token = bearer_token
        self.timeout = timeout
        self._client = None

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

        try:
            # _client is guaranteed to be non-None after the check above
            assert self._client is not None
            response = await self._client.post(url, json=request_data, headers=headers)

            # Handle authentication errors
            if response.status_code == 401:
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
