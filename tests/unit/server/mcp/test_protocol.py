"""Unit tests for MCP JSON-RPC 2.0 protocol handler.

Tests the protocol handling logic in isolation from FastAPI routing.
Following batched TDD approach approved for Story #479.
"""

import pytest
from unittest.mock import patch, Mock
from code_indexer.server.mcp.protocol import (
    validate_jsonrpc_request,
    create_jsonrpc_response,
    create_jsonrpc_error,
    handle_tools_list,
    handle_tools_call,
    process_jsonrpc_request,
    process_batch_request,
)
from code_indexer.server.auth.user_manager import User, UserRole


class TestRequestValidation:
    """Test JSON-RPC 2.0 request validation."""

    def test_valid_request_with_all_fields(self):
        """Test validation of valid request with all fields."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": "test-1",
        }
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is True
        assert error is None

    def test_valid_request_without_optional_fields(self):
        """Test validation of valid request without params and id."""
        request = {"jsonrpc": "2.0", "method": "tools/list"}
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is True
        assert error is None

    def test_missing_jsonrpc_field(self):
        """Test validation fails when jsonrpc field is missing."""
        request = {"method": "tools/list", "id": "test-1"}
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is False
        assert error["code"] == -32600
        assert "jsonrpc" in error["message"].lower()

    def test_invalid_jsonrpc_version(self):
        """Test validation fails when jsonrpc version is not 2.0."""
        request = {"jsonrpc": "1.0", "method": "tools/list", "id": "test-1"}
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is False
        assert error["code"] == -32600
        assert "2.0" in error["message"]

    def test_missing_method_field(self):
        """Test validation fails when method field is missing."""
        request = {"jsonrpc": "2.0", "id": "test-1"}
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is False
        assert error["code"] == -32600
        assert "method" in error["message"].lower()

    def test_invalid_method_type(self):
        """Test validation fails when method is not a string."""
        request = {"jsonrpc": "2.0", "method": 123, "id": "test-1"}
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is False
        assert error["code"] == -32600

    def test_invalid_params_type(self):
        """Test validation fails when params is not object or array."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": "invalid",
            "id": "test-1",
        }
        is_valid, error = validate_jsonrpc_request(request)
        assert is_valid is False
        assert error["code"] == -32600

    def test_valid_id_types(self):
        """Test validation accepts string, number, and null id values."""
        for id_value in ["string-id", 123, 456.78, None]:
            request = {"jsonrpc": "2.0", "method": "tools/list", "id": id_value}
            is_valid, error = validate_jsonrpc_request(request)
            assert is_valid is True, f"Should accept id value: {id_value}"


class TestResponseFormatting:
    """Test JSON-RPC 2.0 response formatting."""

    def test_success_response_with_string_id(self):
        """Test creation of success response with string id."""
        result = {"data": "test"}
        response = create_jsonrpc_response(result, "test-1")

        assert response["jsonrpc"] == "2.0"
        assert response["result"] == result
        assert response["id"] == "test-1"
        assert "error" not in response

    def test_success_response_with_numeric_id(self):
        """Test creation of success response with numeric id."""
        result = {"data": "test"}
        response = create_jsonrpc_response(result, 42)

        assert response["jsonrpc"] == "2.0"
        assert response["result"] == result
        assert response["id"] == 42

    def test_success_response_with_null_id(self):
        """Test creation of success response with null id."""
        result = {"data": "test"}
        response = create_jsonrpc_response(result, None)

        assert response["jsonrpc"] == "2.0"
        assert response["result"] == result
        assert response["id"] is None

    def test_error_response_basic(self):
        """Test creation of basic error response."""
        error = create_jsonrpc_error(-32601, "Method not found", "test-1")

        assert error["jsonrpc"] == "2.0"
        assert error["error"]["code"] == -32601
        assert error["error"]["message"] == "Method not found"
        assert error["id"] == "test-1"
        assert "result" not in error

    def test_error_response_with_data(self):
        """Test creation of error response with additional data."""
        error_data = {"detail": "Unknown method: test/unknown"}
        error = create_jsonrpc_error(
            -32601, "Method not found", "test-1", data=error_data
        )

        assert error["error"]["data"] == error_data

    def test_error_response_without_data(self):
        """Test creation of error response without data field."""
        error = create_jsonrpc_error(-32601, "Method not found", "test-1")
        assert "data" not in error["error"]


class TestMethodRouting:
    """Test method routing to appropriate handlers."""

    @pytest.mark.asyncio
    async def test_route_to_tools_list(self):
        """Test routing tools/list method to handle_tools_list."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-1"}

        response = await process_jsonrpc_request(request, user)

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["id"] == "test-1"

    @pytest.mark.asyncio
    async def test_route_to_tools_call(self):
        """Test routing tools/call method to handle_tools_call."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_code", "arguments": {"query": "test"}},
            "id": "test-1",
        }

        response = await process_jsonrpc_request(request, user)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "test-1"

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self):
        """Test unknown method returns Method not found error."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"jsonrpc": "2.0", "method": "unknown/method", "id": "test-1"}

        response = await process_jsonrpc_request(request, user)

        assert response["jsonrpc"] == "2.0"
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "not found" in response["error"]["message"].lower()


class TestToolsListHandler:
    """Test tools/list handler (stub implementation for Phase 1)."""

    @pytest.mark.asyncio
    async def test_returns_filtered_tools_list(self):
        """Test tools/list returns filtered tools based on user role."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )

        result = await handle_tools_list({}, user)

        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0, "Power user should get at least some tools"

    @pytest.mark.asyncio
    async def test_accepts_empty_params(self):
        """Test tools/list accepts empty params."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )

        result = await handle_tools_list({}, user)

        assert result is not None
        assert "tools" in result


class TestToolsCallHandler:
    """Test tools/call handler (stub implementation for Phase 1)."""

    @pytest.mark.asyncio
    async def test_missing_name_parameter(self):
        """Test tools/call fails when name parameter is missing."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        params = {"arguments": {}}

        with pytest.raises(ValueError) as exc_info:
            await handle_tools_call(params, user)

        assert "name" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_valid_call_returns_stub_success(self):
        """Test tools/call dispatches to actual handler."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        params = {"name": "list_repositories", "arguments": {}}

        with patch("code_indexer.server.app.activated_repo_manager") as mock_mgr:
            mock_mgr.list_activated_repositories = Mock(return_value=[])
            result = await handle_tools_call(params, user)

        assert result["success"] is True
        assert "repositories" in result

    @pytest.mark.asyncio
    async def test_call_without_arguments(self):
        """Test tools/call accepts missing arguments field."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        params = {"name": "list_repositories"}  # No arguments

        with patch("code_indexer.server.app.activated_repo_manager") as mock_mgr:
            mock_mgr.list_activated_repositories = Mock(return_value=[])
            result = await handle_tools_call(params, user)

        assert result["success"] is True
        assert "repositories" in result


class TestBatchRequests:
    """Test batch request processing."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty_array(self):
        """Test empty batch request returns empty array."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = []

        responses = await process_batch_request(batch, user)

        assert isinstance(responses, list)
        assert len(responses) == 0

    @pytest.mark.asyncio
    async def test_single_request_batch(self):
        """Test batch with single request."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = [{"jsonrpc": "2.0", "method": "tools/list", "id": "test-1"}]

        responses = await process_batch_request(batch, user)

        assert len(responses) == 1
        assert responses[0]["id"] == "test-1"

    @pytest.mark.asyncio
    async def test_multiple_request_batch(self):
        """Test batch with multiple requests."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": "1"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "2"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "3"},
        ]

        responses = await process_batch_request(batch, user)

        assert len(responses) == 3
        assert responses[0]["id"] == "1"
        assert responses[1]["id"] == "2"
        assert responses[2]["id"] == "3"

    @pytest.mark.asyncio
    async def test_batch_maintains_correlation(self):
        """Test batch maintains request/response correlation by id."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": "alpha"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "beta"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "gamma"},
        ]

        responses = await process_batch_request(batch, user)

        # Verify each response has correct id
        response_ids = [r["id"] for r in responses]
        assert response_ids == ["alpha", "beta", "gamma"]

    @pytest.mark.asyncio
    async def test_batch_with_mix_of_valid_and_invalid(self):
        """Test batch processes both valid and invalid requests."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": "1"},
            {"method": "tools/list", "id": "2"},  # Missing jsonrpc
            {"jsonrpc": "2.0", "method": "unknown", "id": "3"},  # Unknown method
        ]

        responses = await process_batch_request(batch, user)

        assert len(responses) == 3
        assert "result" in responses[0]  # Valid
        assert "error" in responses[1]  # Invalid request
        assert "error" in responses[2]  # Unknown method

    @pytest.mark.asyncio
    async def test_batch_processes_sequentially(self):
        """Test batch requests are processed in order."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        batch = [{"jsonrpc": "2.0", "method": "tools/list", "id": i} for i in range(10)]

        responses = await process_batch_request(batch, user)

        # Verify responses are in same order as requests
        for i, response in enumerate(responses):
            assert response["id"] == i


class TestErrorCodeMapping:
    """Test JSON-RPC error code mapping."""

    @pytest.mark.asyncio
    async def test_invalid_request_error_code(self):
        """Test invalid request returns -32600."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"method": "tools/list"}  # Missing jsonrpc

        response = await process_jsonrpc_request(request, user)

        assert response["error"]["code"] == -32600

    @pytest.mark.asyncio
    async def test_method_not_found_error_code(self):
        """Test unknown method returns -32601."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"jsonrpc": "2.0", "method": "unknown/method", "id": "test-1"}

        response = await process_jsonrpc_request(request, user)

        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_invalid_params_error_code(self):
        """Test invalid params returns -32602."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {},  # Missing required 'name' param
            "id": "test-1",
        }

        response = await process_jsonrpc_request(request, user)

        assert response["error"]["code"] == -32602
        assert "name" in response["error"]["message"].lower()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_null_params_treated_as_empty_dict(self):
        """Test null params field is treated as empty dict."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": None,
            "id": "test-1",
        }

        response = await process_jsonrpc_request(request, user)

        # Should succeed as tools/list doesn't require params
        assert "result" in response

    @pytest.mark.asyncio
    async def test_notification_request_without_id(self):
        """Test notification (request without id) is processed."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"jsonrpc": "2.0", "method": "tools/list"}

        response = await process_jsonrpc_request(request, user)

        # Notification should still return response for Phase 1
        assert "jsonrpc" in response

    @pytest.mark.asyncio
    async def test_very_long_method_name(self):
        """Test very long method name is rejected gracefully."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {"jsonrpc": "2.0", "method": "a" * 1000, "id": "test-1"}

        response = await process_jsonrpc_request(request, user)

        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_unicode_in_request(self):
        """Test unicode characters are handled correctly."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_code", "arguments": {"query": "测试 🚀"}},
            "id": "test-1",
        }

        response = await process_jsonrpc_request(request, user)

        # Should handle unicode without errors
        assert "jsonrpc" in response


class TestInitializeMethod:
    """Test MCP initialize method - critical for protocol handshake."""

    @pytest.mark.asyncio
    async def test_initialize_returns_protocol_version(self):
        """Test initialize method returns protocolVersion matching spec."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "TestClient", "version": "1.0.0"},
            },
            "id": "init-1",
        }

        response = await process_jsonrpc_request(request, user)

        # Should return success response
        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["id"] == "init-1"

        # Result must contain required fields per MCP spec
        result = response["result"]
        assert "protocolVersion" in result
        assert result["protocolVersion"] == "2024-11-05"
        assert "capabilities" in result
        assert "serverInfo" in result

        # Server info must contain name and version
        assert "name" in result["serverInfo"]
        assert "version" in result["serverInfo"]

    @pytest.mark.asyncio
    async def test_initialize_includes_tools_capability(self):
        """Test initialize returns tools capability."""
        user = User(
            username="test",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=__import__("datetime").datetime.now(),
        )
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "TestClient", "version": "1.0.0"},
            },
            "id": "init-2",
        }

        response = await process_jsonrpc_request(request, user)

        result = response["result"]
        assert "tools" in result["capabilities"]


class TestStreamableHTTPTransport:
    """Test Streamable HTTP transport features (GET, DELETE, Mcp-Session-Id)."""

    def test_get_mcp_returns_sse_stream_with_auth(self):
        """Test GET /mcp returns SSE event stream when authenticated."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.auth.dependencies import get_current_user
        import datetime

        app = create_app()

        # Mock authentication using dependency override
        test_user = User(
            username="test_user",
            password_hash="hashed",
            role=UserRole.POWER_USER,
            created_at=datetime.datetime.now()
        )

        app.dependency_overrides[get_current_user] = lambda: test_user
        client = TestClient(app)

        try:
            # GET /mcp with auth should return SSE stream
            response = client.get(
                "/mcp",
                headers={"Accept": "text/event-stream"}
            )

            # Should return 200 with SSE content-type
            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}"
            assert "text/event-stream" in response.headers.get("content-type", ""), \
                f"Expected SSE content-type, got {response.headers.get('content-type')}"
        finally:
            app.dependency_overrides.clear()

    def test_get_mcp_requires_authentication(self):
        """Test GET /mcp returns 401 when not authenticated."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app

        app = create_app()
        client = TestClient(app)

        # GET /mcp without auth should return 401
        response = client.get(
            "/mcp",
            headers={"Accept": "text/event-stream"}
        )

        assert response.status_code == 401, \
            f"Expected 401 Unauthorized, got {response.status_code}"
        assert "www-authenticate" in response.headers, \
            "Expected WWW-Authenticate header in 401 response"

    def test_delete_mcp_terminates_session(self):
        """Test DELETE /mcp terminates session."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.auth.dependencies import get_current_user
        import datetime

        app = create_app()

        # Mock authentication
        test_user = User(
            username="test_user",
            password_hash="hashed",
            role=UserRole.POWER_USER,
            created_at=datetime.datetime.now()
        )

        app.dependency_overrides[get_current_user] = lambda: test_user
        client = TestClient(app)

        try:
            # DELETE /mcp should terminate session
            response = client.delete(
                "/mcp",
                headers={"Mcp-Session-Id": "test-session-123"}
            )

            # Should return 200 with terminated status
            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}"
            assert response.json().get("status") == "terminated", \
                f"Expected status='terminated', got {response.json()}"
        finally:
            app.dependency_overrides.clear()

    def test_post_mcp_returns_session_id_header(self):
        """Test POST /mcp returns Mcp-Session-Id header in response."""
        from fastapi.testclient import TestClient
        from code_indexer.server.app import create_app
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.auth.dependencies import get_current_user
        import datetime

        app = create_app()

        # Mock authentication
        test_user = User(
            username="test_user",
            password_hash="hashed",
            role=UserRole.POWER_USER,
            created_at=datetime.datetime.now()
        )

        app.dependency_overrides[get_current_user] = lambda: test_user
        client = TestClient(app)

        try:
            # POST /mcp should return session ID in header
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )

            # Should have Mcp-Session-Id header
            assert "mcp-session-id" in response.headers, \
                f"Expected Mcp-Session-Id header, got headers: {response.headers.keys()}"

            session_id = response.headers["mcp-session-id"]

            # Session ID should be non-empty
            assert len(session_id) > 0, "Session ID should not be empty"

            # Session ID should contain only visible ASCII (0x21-0x7E)
            for char in session_id:
                assert 0x21 <= ord(char) <= 0x7E, \
                    f"Invalid character in session ID: {char} (0x{ord(char):02x})"
        finally:
            app.dependency_overrides.clear()
