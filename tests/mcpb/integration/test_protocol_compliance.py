"""Protocol compliance tests for MCP Stdio Bridge.

These tests verify JSON-RPC 2.0 and MCP protocol 2024-11-05 compliance.
Tests use ZERO mocking - real HTTP server for integration testing.
"""

import pytest

from code_indexer.mcpb.bridge import Bridge
from code_indexer.mcpb.config import BridgeConfig
from code_indexer.server.mcp.tools import TOOL_REGISTRY


pytestmark = [pytest.mark.protocol, pytest.mark.e2e]


class TestJsonRpcCompliance:
    """Test JSON-RPC 2.0 protocol compliance."""

    @pytest.mark.asyncio
    async def test_jsonrpc_version_field(self, bridge_config, test_server):
        """Test that responses include JSON-RPC 2.0 version field."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        assert (
            response["jsonrpc"] == "2.0"
        ), "Response must include jsonrpc: '2.0' field"

    @pytest.mark.asyncio
    async def test_jsonrpc_id_field_preserved(self, bridge_config, test_server):
        """Test that request ID is preserved in response."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 42}
        response = await bridge.process_request(request)

        assert response["id"] == 42, "Response ID must match request ID"

    @pytest.mark.asyncio
    async def test_jsonrpc_id_field_string(self, bridge_config, test_server):
        """Test that string ID is preserved correctly."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-id-123"}
        response = await bridge.process_request(request)

        assert response["id"] == "test-id-123", "String IDs must be preserved"

    @pytest.mark.asyncio
    async def test_jsonrpc_id_field_null(self, bridge_config, test_server):
        """Test that null ID is preserved (notification)."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": None}
        response = await bridge.process_request(request)

        assert response["id"] is None, "Null ID must be preserved"

    @pytest.mark.asyncio
    async def test_jsonrpc_result_or_error_field(self, bridge_config, test_server):
        """Test that response contains either result or error field."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        # Must have exactly one of result or error
        has_result = "result" in response
        has_error = "error" in response

        assert (
            has_result != has_error
        ), "Response must have exactly one of 'result' or 'error'"

    @pytest.mark.asyncio
    async def test_jsonrpc_error_code_structure(self, bridge_config):
        """Test that error responses have correct structure."""
        bridge = Bridge(bridge_config)

        # Missing method field - should return error
        request = {"jsonrpc": "2.0", "id": 1}
        response = await bridge.process_request(request)

        assert "error" in response, "Error response must have 'error' field"
        assert "code" in response["error"], "Error must have 'code' field"
        assert "message" in response["error"], "Error must have 'message' field"
        assert isinstance(response["error"]["code"], int), "Error code must be integer"
        assert isinstance(
            response["error"]["message"], str
        ), "Error message must be string"

    @pytest.mark.asyncio
    async def test_jsonrpc_parse_error_code(self, bridge_config):
        """Test that parse errors return -32700 code."""
        bridge = Bridge(bridge_config)

        malformed_json = '{"jsonrpc": "2.0", "method": "tools/list"'
        response = await bridge.process_line(malformed_json)

        assert response["error"]["code"] == -32700, "Parse error code must be -32700"

    @pytest.mark.asyncio
    async def test_jsonrpc_invalid_request_code(self, bridge_config):
        """Test that invalid requests return -32600 code."""
        bridge = Bridge(bridge_config)

        # Missing method field
        request = {"jsonrpc": "2.0", "id": 1}
        response = await bridge.process_request(request)

        assert (
            response["error"]["code"] == -32600
        ), "Invalid request code must be -32600"

    @pytest.mark.asyncio
    async def test_jsonrpc_method_not_found_code(self, bridge_config, test_server):
        """Test that unknown methods return -32601 code."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "unknown/method", "id": 1}
        response = await bridge.process_request(request)

        assert (
            response["error"]["code"] == -32601
        ), "Method not found code must be -32601"

    @pytest.mark.asyncio
    async def test_jsonrpc_missing_version_field(self, bridge_config):
        """Test that missing jsonrpc version field returns error."""
        bridge = Bridge(bridge_config)

        # Missing jsonrpc field
        invalid_line = '{"method": "tools/list", "id": 1}'
        response = await bridge.process_line(invalid_line)

        assert response["error"]["code"] == -32600, "Missing version must be error"
        assert "jsonrpc" in response["error"]["data"]["detail"].lower()


class TestMcpProtocolCompliance:
    """Test MCP protocol 2024-11-05 compliance."""

    @pytest.mark.asyncio
    async def test_mcp_tools_list_method(self, bridge_config, test_server):
        """Test that tools/list method is supported."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        assert "result" in response, "tools/list must return result"
        assert "tools" in response["result"], "Result must contain 'tools' array"

    @pytest.mark.asyncio
    async def test_mcp_tools_list_returns_22_tools(self, bridge_config, test_server):
        """Test that tools/list returns all 22 CIDX MCP tools."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        tools = response["result"]["tools"]
        assert len(tools) == 22, f"Must return exactly 22 tools, got {len(tools)}"

    @pytest.mark.asyncio
    async def test_mcp_tool_schema_structure(self, bridge_config, test_server):
        """Test that each tool has required MCP schema fields."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        tools = response["result"]["tools"]

        for tool in tools:
            # Required MCP tool fields
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert (
                "description" in tool
            ), f"Tool {tool.get('name')} missing 'description'"
            assert (
                "inputSchema" in tool
            ), f"Tool {tool.get('name')} missing 'inputSchema'"

            # Validate inputSchema structure
            schema = tool["inputSchema"]
            assert "type" in schema, f"Tool {tool['name']} inputSchema missing 'type'"
            assert (
                schema["type"] == "object"
            ), f"Tool {tool['name']} inputSchema type must be 'object'"
            assert (
                "properties" in schema
            ), f"Tool {tool['name']} inputSchema missing 'properties'"

    @pytest.mark.asyncio
    async def test_mcp_tool_names_match_registry(self, bridge_config, test_server):
        """Test that tool names match TOOL_REGISTRY."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        tools = response["result"]["tools"]
        actual_names = sorted([t["name"] for t in tools])
        expected_names = sorted(TOOL_REGISTRY.keys())

        assert (
            actual_names == expected_names
        ), f"Tool names mismatch.\nExpected: {expected_names}\nGot: {actual_names}"

    @pytest.mark.asyncio
    async def test_mcp_tools_call_method(self, bridge_config, test_server):
        """Test that tools/call method is supported."""
        bridge = Bridge(bridge_config)

        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_code",
                "arguments": {"query_text": "test"},
            },
            "id": 1,
        }
        response = await bridge.process_request(request)

        assert (
            "result" in response or "error" in response
        ), "tools/call must return result or error"

    @pytest.mark.asyncio
    async def test_mcp_search_code_tool_parameters(self, bridge_config, test_server):
        """Test that search_code tool has correct parameter count."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        tools = response["result"]["tools"]
        search_code_tool = next((t for t in tools if t["name"] == "search_code"), None)

        assert search_code_tool is not None, "search_code tool must be present"

        param_count = len(search_code_tool["inputSchema"]["properties"])
        assert (
            param_count == 25
        ), f"search_code must have 25 parameters, got {param_count}"

    @pytest.mark.asyncio
    async def test_mcp_all_tools_accessible(self, bridge_config, test_server):
        """Test that all 22 MCP tools are accessible through tools/list."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        tools = response["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        # All 22 expected tools
        expected_tools = {
            "search_code",
            "list_repositories",
            "get_repository_status",
            "get_all_repositories_status",
            "sync_repository",
            "activate_repository",
            "deactivate_repository",
            "switch_branch",
            "get_branches",
            "list_files",
            "browse_directory",
            "get_file_content",
            "discover_repositories",
            "get_repository_statistics",
            "get_job_statistics",
            "check_health",
            "list_users",
            "create_user",
            "manage_composite_repository",
            "add_golden_repo",
            "refresh_golden_repo",
            "remove_golden_repo",
        }

        assert (
            tool_names == expected_tools
        ), f"Tool names mismatch.\nMissing: {expected_tools - tool_names}\nExtra: {tool_names - expected_tools}"


class TestErrorHandling:
    """Test comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_parse_error_invalid_json(self, bridge_config):
        """Test parse error for invalid JSON."""
        bridge = Bridge(bridge_config)

        response = await bridge.process_line("not valid json")

        assert response["jsonrpc"] == "2.0"
        assert response["id"] is None
        assert response["error"]["code"] == -32700
        assert "parse" in response["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_parse_error_incomplete_json(self, bridge_config):
        """Test parse error for incomplete JSON."""
        bridge = Bridge(bridge_config)

        response = await bridge.process_line(
            '{"jsonrpc": "2.0", "method": "tools/list"'
        )

        assert response["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_invalid_request_missing_method(self, bridge_config):
        """Test invalid request error for missing method field."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "id": 1}
        response = await bridge.process_request(request)

        assert response["error"]["code"] == -32600
        assert "method" in response["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_request_missing_jsonrpc(self, bridge_config):
        """Test invalid request error for missing jsonrpc field."""
        bridge = Bridge(bridge_config)

        response = await bridge.process_line('{"method": "tools/list", "id": 1}')

        assert response["error"]["code"] == -32600
        assert "jsonrpc" in response["error"]["data"]["detail"].lower()

    @pytest.mark.asyncio
    async def test_method_not_found_error(self, bridge_config, test_server):
        """Test method not found error."""
        bridge = Bridge(bridge_config)

        request = {"jsonrpc": "2.0", "method": "invalid/method", "id": 1}
        response = await bridge.process_request(request)

        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_auth_error_invalid_token(self, test_server):
        """Test authentication error with invalid token."""
        invalid_config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token="invalid-token",
            timeout=30,
        )
        bridge = Bridge(invalid_config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        assert response["error"]["code"] == -32000
        assert "401" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_server_error_connection_refused(self):
        """Test server error when server is unavailable."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:9999",
            bearer_token="test-token",
            timeout=5,
        )
        bridge = Bridge(config)

        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        response = await bridge.process_request(request)

        assert response["error"]["code"] == -32000
        assert (
            "connection" in response["error"]["message"].lower()
            or "connect" in response["error"]["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_error_response_structure(self, bridge_config):
        """Test that all error responses have consistent structure."""
        bridge = Bridge(bridge_config)

        # Generate various error types
        errors = []

        # Parse error
        errors.append(await bridge.process_line("invalid json"))

        # Invalid request
        errors.append(await bridge.process_request({"jsonrpc": "2.0", "id": 1}))

        # Validate all errors have required fields
        for error_response in errors:
            assert error_response["jsonrpc"] == "2.0"
            assert "error" in error_response
            assert "code" in error_response["error"]
            assert "message" in error_response["error"]
            assert isinstance(error_response["error"]["code"], int)
            assert isinstance(error_response["error"]["message"], str)


class TestRequestResponseCycle:
    """Test complete request/response cycles."""

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, bridge_config, test_server):
        """Test processing multiple requests sequentially."""
        bridge = Bridge(bridge_config)

        # Request 1
        response1 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        assert response1["id"] == 1
        assert "result" in response1

        # Request 2
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert response2["id"] == 2
        assert "result" in response2

        # Request 3
        response3 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 3}
        )
        assert response3["id"] == 3
        assert "result" in response3

    @pytest.mark.asyncio
    async def test_error_recovery_continue_processing(self, bridge_config, test_server):
        """Test that bridge continues processing after error."""
        bridge = Bridge(bridge_config)

        # Request 1 - error
        response1 = await bridge.process_line("invalid json")
        assert "error" in response1

        # Request 2 - success
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2

        # Request 3 - error
        response3 = await bridge.process_request({"jsonrpc": "2.0", "id": 3})
        assert "error" in response3

        # Request 4 - success
        response4 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 4}
        )
        assert "result" in response4

    @pytest.mark.asyncio
    async def test_different_id_types_in_sequence(self, bridge_config, test_server):
        """Test handling different ID types in sequence."""
        bridge = Bridge(bridge_config)

        # Integer ID
        response1 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 123}
        )
        assert response1["id"] == 123

        # String ID
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": "test-id"}
        )
        assert response2["id"] == "test-id"

        # Null ID
        response3 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": None}
        )
        assert response3["id"] is None

    @pytest.mark.asyncio
    async def test_request_with_params(self, bridge_config, test_server):
        """Test request with params field."""
        bridge = Bridge(bridge_config)

        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_code",
                "arguments": {"query_text": "authentication", "limit": 5},
            },
            "id": 1,
        }
        response = await bridge.process_request(request)

        assert response["id"] == 1
        assert "result" in response or "error" in response
