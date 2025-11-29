"""Unit tests for HTTP client with Bearer token authentication.

This module tests HTTP client configuration, request forwarding with authentication,
and error handling for HTTP transport issues.
"""

import pytest
import httpx

from code_indexer.mcpb.http_client import (
    BridgeHttpClient,
    HttpError,
    TimeoutError as BridgeTimeoutError,
)


class TestBridgeHttpClient:
    """Test HTTP client functionality."""

    def test_client_initialization(self):
        """Test HTTP client initialization with config."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            timeout=30,
        )

        assert client.server_url == "https://cidx.example.com"
        assert client.bearer_token == "test-token-123"
        assert client.timeout == 30

    def test_client_builds_mcp_endpoint_url(self):
        """Test that client builds correct MCP endpoint URL."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        mcp_url = client.get_mcp_endpoint_url()
        assert mcp_url == "https://cidx.example.com/mcp"

    def test_client_adds_bearer_token_to_headers(self):
        """Test that Bearer token is added to request headers."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            timeout=30,
        )

        headers = client.get_auth_headers()
        assert headers["Authorization"] == "Bearer test-token-123"

    def test_client_adds_content_type_json(self):
        """Test that Content-Type is set to application/json."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        headers = client.get_request_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
class TestHttpClientRequests:
    """Test HTTP client request handling."""

    async def test_forward_request_success(self, httpx_mock):
        """Test forwarding a successful request."""
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {"tools": []}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

    async def test_forward_request_includes_auth_header(self, httpx_mock):
        """Test that forwarded request includes Authorization header."""
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="secret-token",
            timeout=30,
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        await client.forward_request(request_data)

        request = httpx_mock.get_request()
        assert request.headers["Authorization"] == "Bearer secret-token"

    async def test_forward_request_401_raises_auth_error(
        self, httpx_mock, monkeypatch
    ):
        """Test that 401 response attempts auto-login and raises auth error if no credentials."""
        # Mock credentials_exist to return False (no stored credentials)
        from code_indexer.mcpb import credential_storage

        monkeypatch.setattr(credential_storage, "credentials_exist", lambda: False)

        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Unauthorized",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="invalid-token",
            timeout=30,
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        # Should attempt auto-login but fail due to no credentials
        with pytest.raises(HttpError, match="Authentication failed.*401"):
            await client.forward_request(request_data)

    async def test_forward_request_500_raises_server_error(self, httpx_mock):
        """Test that 500 response raises server error."""
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=500,
            text="Internal Server Error",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Server error.*500"):
            await client.forward_request(request_data)

    async def test_forward_request_connection_error_raises_transport_error(
        self, httpx_mock
    ):
        """Test that connection error raises transport error."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Connection failed"):
            await client.forward_request(request_data)

    async def test_forward_request_timeout_raises_timeout_error(self, httpx_mock):
        """Test that timeout raises timeout error."""
        httpx_mock.add_exception(httpx.TimeoutException("Request timed out"))

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(BridgeTimeoutError, match="Request timed out after 30"):
            await client.forward_request(request_data)

    async def test_forward_request_network_error_includes_diagnostic(self, httpx_mock):
        """Test that network errors include helpful diagnostic message."""
        httpx_mock.add_exception(httpx.NetworkError("Network unreachable"))

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError) as exc_info:
            await client.forward_request(request_data)

        assert "Network unreachable" in str(exc_info.value)
        assert "cidx.example.com" in str(exc_info.value)


@pytest.mark.asyncio
class TestHttpClientContextManager:
    """Test HTTP client context manager protocol."""

    async def test_client_context_manager_closes_connection(self):
        """Test that client closes connection when exiting context."""
        async with BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        ) as client:
            assert client is not None

        # Client should be closed after exiting context
        # This would raise if client tries to make requests after close

    async def test_client_can_be_used_outside_context_manager(self):
        """Test that client can be used outside context manager with explicit close."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        try:
            assert client is not None
        finally:
            await client.close()


@pytest.mark.asyncio
class TestHttpClientStreaming:
    """Test HTTP client SSE streaming support."""

    async def test_request_headers_include_accept_header(self):
        """Test that Accept header includes SSE and JSON formats."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        headers = client.get_request_headers()
        assert headers["Accept"] == "text/event-stream, application/json"

    async def test_forward_request_with_sse_response(self, httpx_mock):
        """Test forwarding request that receives SSE streaming response."""
        # Simulate SSE response
        sse_content = (
            'data: {"type": "chunk", "content": {"file": "test1.py", "score": 0.9}}\n\n'
            'data: {"type": "chunk", "content": {"file": "test2.py", "score": 0.8}}\n\n'
            'data: {"type": "complete", "content": {"total": 2}}\n\n'
        )

        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            content=sse_content.encode(),
            headers={"Content-Type": "text/event-stream"},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {
            "jsonrpc": "2.0",
            "method": "query",
            "params": {"q": "test"},
            "id": 1,
        }
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["total"] == 2
        assert len(response["result"]["chunks"]) == 2

    async def test_forward_request_with_json_fallback(self, httpx_mock):
        """Test that JSON response is handled when server doesn't support SSE."""
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {"files": []}, "id": 1},
            headers={"Content-Type": "application/json"},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "query", "id": 1}
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

    async def test_forward_request_with_sse_error_event(self, httpx_mock):
        """Test handling SSE stream that ends with error event."""
        sse_content = (
            'data: {"type": "chunk", "content": {"file": "test.py"}}\n\n'
            'data: {"type": "error", "error": {"code": -32000, "message": "Query failed"}}\n\n'
        )

        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            content=sse_content.encode(),
            headers={"Content-Type": "text/event-stream"},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "query", "id": 1}
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32000
        assert response["error"]["message"] == "Query failed"

    async def test_forward_request_with_incomplete_sse_stream(self, httpx_mock):
        """Test handling SSE stream that terminates without complete event."""
        sse_content = (
            'data: {"type": "chunk", "content": {"file": "test.py"}}\n\n'
            # Stream ends here without complete event
        )

        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            content=sse_content.encode(),
            headers={"Content-Type": "text/event-stream"},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "query", "id": 1}
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert "Stream terminated unexpectedly" in response["error"]["message"]

    async def test_forward_request_with_malformed_sse_event(self, httpx_mock):
        """Test handling malformed SSE event in stream."""
        sse_content = (
            'data: {"type": "chunk", "content": {"file": "test.py"}}\n\n'
            "data: {invalid json}\n\n"
        )

        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            content=sse_content.encode(),
            headers={"Content-Type": "text/event-stream"},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com", bearer_token="test-token", timeout=30
        )

        request_data = {"jsonrpc": "2.0", "method": "query", "id": 1}
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert "Invalid JSON" in response["error"]["message"]
