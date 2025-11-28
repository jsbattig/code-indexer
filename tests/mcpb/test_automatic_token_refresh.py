"""Unit tests for automatic token refresh in BridgeHttpClient.

This module tests the automatic token refresh functionality that handles
JWT token expiration (401 errors) transparently by refreshing the token
and retrying the request.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import httpx

from code_indexer.mcpb.http_client import BridgeHttpClient, HttpError


@pytest.mark.asyncio
class TestAutomaticTokenRefresh:
    """Test automatic token refresh on 401 errors."""

    async def test_client_initialization_with_refresh_token(self):
        """Test HTTP client initialization with refresh_token."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        assert client.server_url == "https://cidx.example.com"
        assert client.bearer_token == "test-token-123"
        assert client.timeout == 30
        assert client.refresh_token == "test-refresh-token"

    async def test_client_initialization_without_refresh_token(self):
        """Test HTTP client initialization without refresh_token (optional)."""
        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            timeout=30,
        )

        assert client.server_url == "https://cidx.example.com"
        assert client.bearer_token == "test-token-123"
        assert client.refresh_token is None

    async def test_client_initialization_with_config_path(self):
        """Test HTTP client initialization with config_path for token persistence."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.example.com",
                "bearer_token": "test-token",
                "refresh_token": "test-refresh",
            }
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            client = BridgeHttpClient(
                server_url="https://cidx.example.com",
                bearer_token="test-token-123",
                timeout=30,
                refresh_token="test-refresh-token",
                config_path=config_path,
            )

            assert client.config_path == config_path
        finally:
            os.unlink(config_path)

    async def test_401_without_refresh_token_raises_auth_error(self, httpx_mock):
        """Test that 401 without refresh_token raises authentication error."""
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token=None,  # No refresh token
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Authentication failed.*401"):
            await client.forward_request(request_data)

    async def test_401_with_refresh_token_triggers_refresh_and_retry(self, httpx_mock):
        """Test that 401 with refresh_token triggers token refresh and retries request."""
        # First request returns 401 (expired token)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns new tokens
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            json={
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Retry with new token succeeds
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {"tools": []}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await client.forward_request(request_data)

        # Verify response is successful
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

        # Verify bearer token was updated
        assert client.bearer_token == "new-access-token"

    async def test_refresh_endpoint_failure_raises_error(self, httpx_mock):
        """Test that refresh endpoint failure raises clear error."""
        # First request returns 401 (expired token)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns 401 (refresh token expired)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            status_code=401,
            text="Refresh token expired",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="expired-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(
            HttpError, match="Refresh token expired - re-authentication required"
        ):
            await client.forward_request(request_data)

    async def test_refresh_only_happens_once_per_request(self, httpx_mock):
        """Test that token refresh only happens once per request (prevents infinite loops)."""
        # First request returns 401 (expired token)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns new tokens
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            json={
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Retry with new token ALSO returns 401 (should not refresh again)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="New token also expired",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        # Should raise error on second 401, not loop infinitely
        with pytest.raises(HttpError, match="Authentication failed.*401"):
            await client.forward_request(request_data)

        # Verify refresh was only called once (3 requests total: initial, refresh, retry)
        assert len(httpx_mock.get_requests()) == 3

    async def test_refresh_updates_config_file_atomically(self, httpx_mock):
        """Test that token refresh updates config file atomically with secure permissions."""
        # Create config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.example.com",
                "bearer_token": "old-token",
                "refresh_token": "old-refresh",
            }
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            # First request returns 401
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/mcp",
                status_code=401,
                text="Token has expired",
            )

            # Refresh endpoint returns new tokens
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/auth/refresh",
                json={
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                },
                status_code=200,
            )

            # Retry succeeds
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/mcp",
                json={"jsonrpc": "2.0", "result": {}, "id": 1},
                status_code=200,
            )

            client = BridgeHttpClient(
                server_url="https://cidx.example.com",
                bearer_token="old-token",
                timeout=30,
                refresh_token="old-refresh",
                config_path=config_path,
            )

            request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            await client.forward_request(request_data)

            # Verify config file was updated
            with open(config_path) as f:
                updated_config = json.load(f)

            assert updated_config["bearer_token"] == "new-access-token"
            assert updated_config["refresh_token"] == "new-refresh-token"

            # Verify file has secure permissions (0600)
            file_perms = os.stat(config_path).st_mode & 0o777
            assert file_perms == 0o600

        finally:
            os.unlink(config_path)

    async def test_refresh_without_config_path_does_not_persist(self, httpx_mock):
        """Test that token refresh without config_path updates in-memory but doesn't persist."""
        # First request returns 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns new tokens
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            json={
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Retry succeeds
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="old-token",
            timeout=30,
            refresh_token="old-refresh",
            config_path=None,  # No config path
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        await client.forward_request(request_data)

        # Verify in-memory token was updated
        assert client.bearer_token == "new-access-token"
        assert client.refresh_token == "new-refresh-token"

        # No file operations should have occurred (verified by httpx_mock only having 3 requests)
        assert len(httpx_mock.get_requests()) == 3

    async def test_refresh_token_logs_to_stderr(self, httpx_mock, capsys):
        """Test that token refresh logs event to stderr (for Claude Desktop debugging)."""
        # First request returns 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns new tokens
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            json={
                "access_token": "new-access-token-123456789012345678901234567890",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Retry succeeds
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="old-token",
            timeout=30,
            refresh_token="old-refresh",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        await client.forward_request(request_data)

        # Verify stderr contains refresh log
        captured = capsys.readouterr()
        assert "Token refreshed:" in captured.err
        # Verify only first 20 chars of token are logged
        assert "new-access-token-123" in captured.err
        # Verify full token is NOT logged
        assert "new-access-token-123456789012345678901234567890" not in captured.err

    async def test_refresh_endpoint_non_401_error_propagates(self, httpx_mock):
        """Test that non-401 errors from refresh endpoint propagate correctly."""
        # First request returns 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns 500 (server error)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            status_code=500,
            text="Internal server error",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Token refresh failed.*500"):
            await client.forward_request(request_data)

    async def test_refresh_endpoint_connection_error_propagates(self, httpx_mock):
        """Test that connection errors from refresh endpoint propagate correctly."""
        # First request returns 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint has connection error
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://cidx.example.com/auth/refresh",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Token refresh failed.*Connection"):
            await client.forward_request(request_data)

    async def test_refresh_endpoint_malformed_response_raises_error(self, httpx_mock):
        """Test that malformed response from refresh endpoint raises error."""
        # First request returns 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=401,
            text="Token has expired",
        )

        # Refresh endpoint returns malformed JSON (missing access_token)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/refresh",
            json={"refresh_token": "new-refresh-token"},  # Missing access_token
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="expired-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Invalid refresh response.*access_token"):
            await client.forward_request(request_data)

    async def test_non_401_errors_do_not_trigger_refresh(self, httpx_mock):
        """Test that non-401 errors (500, 404, etc.) do not trigger token refresh."""
        # Request returns 500 (server error, not auth error)
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            status_code=500,
            text="Internal server error",
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="valid-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        with pytest.raises(HttpError, match="Server error.*500"):
            await client.forward_request(request_data)

        # Verify refresh endpoint was NOT called (only 1 request)
        assert len(httpx_mock.get_requests()) == 1

    async def test_successful_request_does_not_trigger_refresh(self, httpx_mock):
        """Test that successful requests do not trigger token refresh."""
        # Request succeeds immediately
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/mcp",
            json={"jsonrpc": "2.0", "result": {"tools": []}, "id": 1},
            status_code=200,
        )

        client = BridgeHttpClient(
            server_url="https://cidx.example.com",
            bearer_token="valid-token",
            timeout=30,
            refresh_token="test-refresh-token",
        )

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await client.forward_request(request_data)

        assert response["jsonrpc"] == "2.0"
        assert "result" in response

        # Verify refresh endpoint was NOT called (only 1 request)
        assert len(httpx_mock.get_requests()) == 1

    async def test_config_file_preserves_other_fields(self, httpx_mock):
        """Test that config file update preserves other fields (timeout, log_level)."""
        # Create config file with all fields
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.example.com",
                "bearer_token": "old-token",
                "refresh_token": "old-refresh",
                "timeout": 60,
                "log_level": "debug",
            }
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            # First request returns 401
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/mcp",
                status_code=401,
                text="Token has expired",
            )

            # Refresh endpoint returns new tokens
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/auth/refresh",
                json={
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                },
                status_code=200,
            )

            # Retry succeeds
            httpx_mock.add_response(
                method="POST",
                url="https://cidx.example.com/mcp",
                json={"jsonrpc": "2.0", "result": {}, "id": 1},
                status_code=200,
            )

            client = BridgeHttpClient(
                server_url="https://cidx.example.com",
                bearer_token="old-token",
                timeout=30,
                refresh_token="old-refresh",
                config_path=config_path,
            )

            request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            await client.forward_request(request_data)

            # Verify config file was updated with new tokens
            with open(config_path) as f:
                updated_config = json.load(f)

            assert updated_config["bearer_token"] == "new-access-token"
            assert updated_config["refresh_token"] == "new-refresh-token"
            # Verify other fields preserved
            assert updated_config["server_url"] == "https://cidx.example.com"
            assert updated_config["timeout"] == 60
            assert updated_config["log_level"] == "debug"

        finally:
            os.unlink(config_path)


@pytest.mark.asyncio
class TestRefreshTokenIntegration:
    """Integration tests for token refresh with Bridge."""

    async def test_bridge_passes_refresh_token_to_client(self):
        """Test that Bridge passes refresh_token to BridgeHttpClient."""
        from code_indexer.mcpb.bridge import Bridge
        from code_indexer.mcpb.config import BridgeConfig

        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token",
            refresh_token="test-refresh-token",
        )

        bridge = Bridge(config)

        assert bridge.http_client.refresh_token == "test-refresh-token"

    async def test_bridge_passes_none_refresh_token_to_client(self):
        """Test that Bridge handles missing refresh_token gracefully."""
        from code_indexer.mcpb.bridge import Bridge
        from code_indexer.mcpb.config import BridgeConfig

        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token",
            # No refresh_token
        )

        bridge = Bridge(config)

        assert bridge.http_client.refresh_token is None
