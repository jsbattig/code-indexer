"""End-to-end workflow tests for MCP Stdio Bridge.

These tests verify complete workflows from stdin to CIDX server and back.
Tests use ZERO mocking - real HTTP server for integration testing.
"""

import asyncio
import json
import pytest

from code_indexer.mcpb.bridge import Bridge
from code_indexer.mcpb.config import BridgeConfig


pytestmark = [pytest.mark.e2e]


class TestCompleteQueryWorkflow:
    """Test complete query workflows from start to finish."""

    @pytest.mark.asyncio
    async def test_full_search_code_workflow(self, bridge_config, test_server):
        """Test complete search_code workflow: request -> bridge -> server -> response."""
        bridge = Bridge(bridge_config)

        # Step 1: Create search request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_code",
                "arguments": {"query_text": "authentication", "limit": 5},
            },
            "id": 1,
        }

        # Step 2: Process through bridge
        response = await bridge.process_request(request)

        # Step 3: Validate response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert "content" in response["result"]

        # Step 4: Validate content structure (MCP format)
        content = response["result"]["content"]
        assert isinstance(content, list)
        assert len(content) > 0
        assert content[0]["type"] == "text"
        assert "text" in content[0]

    @pytest.mark.asyncio
    async def test_tools_list_workflow(self, bridge_config, test_server):
        """Test tools/list workflow: request -> bridge -> server -> response."""
        bridge = Bridge(bridge_config)

        # Step 1: Create tools/list request
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        # Step 2: Process through bridge
        response = await bridge.process_request(request)

        # Step 3: Validate response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

        # Step 4: Validate tools structure
        tools = response["result"]["tools"]
        assert len(tools) == 22
        assert all("name" in t for t in tools)
        assert all("description" in t for t in tools)
        assert all("inputSchema" in t for t in tools)

    @pytest.mark.asyncio
    async def test_stdin_to_stdout_workflow(self, bridge_config, test_server, tmp_path):
        """Test complete stdin -> stdout workflow with file I/O."""
        bridge = Bridge(bridge_config)

        # Step 1: Prepare input requests
        input_file = tmp_path / "input.jsonl"
        input_file.write_text(
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}\n'
            '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search_code", "arguments": {"query_text": "test"}}, "id": 2}\n'
        )

        # Step 2: Prepare output file
        output_file = tmp_path / "output.jsonl"

        # Step 3: Process through bridge
        with open(input_file) as stdin, open(output_file, "w") as stdout:
            await bridge.run_stdio_loop(stdin, stdout)

        # Step 4: Validate output
        output_lines = output_file.read_text().strip().split("\n")
        assert len(output_lines) == 2

        # Step 5: Validate responses
        response1 = json.loads(output_lines[0])
        response2 = json.loads(output_lines[1])

        assert response1["id"] == 1
        assert "result" in response1
        assert len(response1["result"]["tools"]) == 22

        assert response2["id"] == 2
        assert "result" in response2


class TestMultiToolRequestSequences:
    """Test sequences of multiple tool requests."""

    @pytest.mark.asyncio
    async def test_sequential_different_tools(self, bridge_config, test_server):
        """Test calling different tools sequentially."""
        bridge = Bridge(bridge_config)

        # Request 1: tools/list
        response1 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        assert response1["id"] == 1
        assert "result" in response1

        # Request 2: search_code
        response2 = await bridge.process_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_code",
                    "arguments": {"query_text": "test"},
                },
                "id": 2,
            }
        )
        assert response2["id"] == 2
        assert "result" in response2

    @pytest.mark.asyncio
    async def test_repeated_tools_list_calls(self, bridge_config, test_server):
        """Test calling tools/list multiple times."""
        bridge = Bridge(bridge_config)

        for i in range(1, 4):
            response = await bridge.process_request(
                {"jsonrpc": "2.0", "method": "tools/list", "id": i}
            )
            assert response["id"] == i
            assert "result" in response
            assert len(response["result"]["tools"]) == 22

    @pytest.mark.asyncio
    async def test_repeated_search_code_calls(self, bridge_config, test_server):
        """Test calling search_code multiple times with different queries."""
        bridge = Bridge(bridge_config)

        queries = ["authentication", "database", "api"]

        for i, query in enumerate(queries, start=1):
            response = await bridge.process_request(
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_code",
                        "arguments": {"query_text": query},
                    },
                    "id": i,
                }
            )
            assert response["id"] == i
            assert "result" in response

    @pytest.mark.asyncio
    async def test_interleaved_requests_and_errors(self, bridge_config, test_server):
        """Test interleaved successful requests and errors."""
        bridge = Bridge(bridge_config)

        # Success
        response1 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        assert "result" in response1

        # Error
        response2 = await bridge.process_line("invalid json")
        assert "error" in response2

        # Success
        response3 = await bridge.process_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_code",
                    "arguments": {"query_text": "test"},
                },
                "id": 3,
            }
        )
        assert "result" in response3

        # Error
        response4 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "unknown/method", "id": 4}
        )
        assert "error" in response4


class TestErrorRecoveryWorkflows:
    """Test error recovery and continuation workflows."""

    @pytest.mark.asyncio
    async def test_parse_error_then_valid_request(self, bridge_config, test_server):
        """Test recovery from parse error."""
        bridge = Bridge(bridge_config)

        # Parse error
        response1 = await bridge.process_line('{"invalid": json}')
        assert "error" in response1
        assert response1["error"]["code"] == -32700

        # Valid request after error
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2
        assert response2["id"] == 2

    @pytest.mark.asyncio
    async def test_invalid_request_then_valid_request(self, bridge_config, test_server):
        """Test recovery from invalid request error."""
        bridge = Bridge(bridge_config)

        # Invalid request (missing method)
        response1 = await bridge.process_request({"jsonrpc": "2.0", "id": 1})
        assert "error" in response1
        assert response1["error"]["code"] == -32600

        # Valid request after error
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2

    @pytest.mark.asyncio
    async def test_method_not_found_then_valid_request(
        self, bridge_config, test_server
    ):
        """Test recovery from method not found error."""
        bridge = Bridge(bridge_config)

        # Method not found
        response1 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "invalid/method", "id": 1}
        )
        assert "error" in response1
        assert response1["error"]["code"] == -32601

        # Valid request after error
        response2 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2

    @pytest.mark.asyncio
    async def test_auth_error_then_valid_request(self, test_server):
        """Test recovery from authentication error (with token change)."""
        # Invalid token config
        invalid_config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token="invalid-token",
            timeout=30,
        )
        invalid_bridge = Bridge(invalid_config)

        # Auth error
        response1 = await invalid_bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        assert "error" in response1
        assert response1["error"]["code"] == -32000

        # Valid token config
        valid_config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=30,
        )
        valid_bridge = Bridge(valid_config)

        # Valid request with correct token
        response2 = await valid_bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2

    @pytest.mark.asyncio
    async def test_multiple_errors_in_sequence(self, bridge_config, test_server):
        """Test handling multiple errors in sequence."""
        bridge = Bridge(bridge_config)

        # Parse error
        response1 = await bridge.process_line("invalid")
        assert response1["error"]["code"] == -32700

        # Invalid request error
        response2 = await bridge.process_request({"jsonrpc": "2.0", "id": 2})
        assert response2["error"]["code"] == -32600

        # Method not found error
        response3 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "unknown", "id": 3}
        )
        assert response3["error"]["code"] == -32601

        # Valid request after all errors
        response4 = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 4}
        )
        assert "result" in response4


class TestConfigurationBasedWorkflows:
    """Test workflows with different configurations."""

    @pytest.mark.asyncio
    async def test_workflow_with_minimum_timeout(self, test_server):
        """Test workflow with minimum 1-second timeout."""
        config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=1,  # Minimum timeout
        )
        bridge = Bridge(config)

        response = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )

        # Should complete successfully with minimum timeout
        assert "result" in response

    @pytest.mark.asyncio
    async def test_workflow_with_default_timeout(self, test_server):
        """Test workflow with default 30-second timeout."""
        config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=30,  # Default timeout
        )
        bridge = Bridge(config)

        response = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )

        assert "result" in response

    @pytest.mark.asyncio
    async def test_workflow_with_long_timeout(self, test_server):
        """Test workflow with long 300-second timeout."""
        config = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=300,  # Long timeout
        )
        bridge = Bridge(config)

        response = await bridge.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )

        assert "result" in response

    @pytest.mark.asyncio
    async def test_workflow_with_different_server_urls(self, test_server):
        """Test workflow with different server URL formats."""
        # Test with explicit port
        config1 = BridgeConfig(
            server_url=f"http://127.0.0.1:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=30,
        )
        bridge1 = Bridge(config1)

        response1 = await bridge1.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        assert "result" in response1

        # Test with localhost
        config2 = BridgeConfig(
            server_url=f"http://localhost:{test_server.port}",
            bearer_token=test_server.bearer_token,
            timeout=30,
        )
        bridge2 = Bridge(config2)

        response2 = await bridge2.process_request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        )
        assert "result" in response2


class TestStdioLoopWorkflows:
    """Test stdio loop workflows with various input patterns."""

    @pytest.mark.asyncio
    async def test_empty_lines_ignored(self, bridge_config, test_server, tmp_path):
        """Test that empty lines in input are ignored."""
        bridge = Bridge(bridge_config)

        # Input with empty lines
        input_file = tmp_path / "input.jsonl"
        input_file.write_text(
            "\n"  # Empty line
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}\n'
            "\n"  # Empty line
            "\n"  # Empty line
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 2}\n'
            "\n"  # Empty line
        )

        output_file = tmp_path / "output.jsonl"

        with open(input_file) as stdin, open(output_file, "w") as stdout:
            await bridge.run_stdio_loop(stdin, stdout)

        # Only 2 responses (empty lines ignored)
        output_lines = output_file.read_text().strip().split("\n")
        assert len(output_lines) == 2

        response1 = json.loads(output_lines[0])
        response2 = json.loads(output_lines[1])

        assert response1["id"] == 1
        assert response2["id"] == 2

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_requests(
        self, bridge_config, test_server, tmp_path
    ):
        """Test stdio loop with mix of valid and invalid requests."""
        bridge = Bridge(bridge_config)

        input_file = tmp_path / "input.jsonl"
        input_file.write_text(
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}\n'  # Valid
            "invalid json line\n"  # Invalid
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 3}\n'  # Valid
            '{"jsonrpc": "2.0", "id": 4}\n'  # Invalid (missing method)
            '{"jsonrpc": "2.0", "method": "tools/list", "id": 5}\n'  # Valid
        )

        output_file = tmp_path / "output.jsonl"

        with open(input_file) as stdin, open(output_file, "w") as stdout:
            await bridge.run_stdio_loop(stdin, stdout)

        # All 5 lines should produce responses
        output_lines = output_file.read_text().strip().split("\n")
        assert len(output_lines) == 5

        responses = [json.loads(line) for line in output_lines]

        # Response 1: success
        assert responses[0]["id"] == 1
        assert "result" in responses[0]

        # Response 2: parse error
        assert responses[1]["id"] is None
        assert responses[1]["error"]["code"] == -32700

        # Response 3: success
        assert responses[2]["id"] == 3
        assert "result" in responses[2]

        # Response 4: invalid request (ID is None because parse_jsonrpc_request raises ValueError before ID can be extracted)
        assert (
            responses[3]["id"] is None
        )  # Per JSON-RPC 2.0: ID is null when request parsing fails
        assert responses[3]["error"]["code"] == -32600

        # Response 5: success
        assert responses[4]["id"] == 5
        assert "result" in responses[4]

    @pytest.mark.asyncio
    async def test_large_batch_processing(self, bridge_config, test_server, tmp_path):
        """Test processing large batch of requests."""
        bridge = Bridge(bridge_config)

        # Generate 50 requests
        requests = []
        for i in range(1, 51):
            requests.append(
                json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": i})
            )

        input_file = tmp_path / "input.jsonl"
        input_file.write_text("\n".join(requests) + "\n")

        output_file = tmp_path / "output.jsonl"

        with open(input_file) as stdin, open(output_file, "w") as stdout:
            await bridge.run_stdio_loop(stdin, stdout)

        # All 50 requests should be processed
        output_lines = output_file.read_text().strip().split("\n")
        assert len(output_lines) == 50

        # Validate all responses
        for i, line in enumerate(output_lines, start=1):
            response = json.loads(line)
            assert response["id"] == i
            assert "result" in response


class TestConcurrentRequestHandling:
    """Test concurrent request handling capabilities."""

    @pytest.mark.asyncio
    async def test_concurrent_tools_list_requests(self, bridge_config, test_server):
        """Test processing concurrent tools/list requests."""
        bridge = Bridge(bridge_config)

        # Create 10 concurrent requests
        tasks = []
        for i in range(1, 11):
            task = bridge.process_request(
                {"jsonrpc": "2.0", "method": "tools/list", "id": i}
            )
            tasks.append(task)

        # Process all concurrently
        responses = await asyncio.gather(*tasks)

        # Validate all responses
        assert len(responses) == 10
        for i, response in enumerate(responses, start=1):
            assert response["id"] == i
            assert "result" in response
            assert len(response["result"]["tools"]) == 22

    @pytest.mark.asyncio
    async def test_concurrent_mixed_requests(self, bridge_config, test_server):
        """Test concurrent requests with different methods."""
        bridge = Bridge(bridge_config)

        # Mix of tools/list and tools/call
        tasks = []
        for i in range(1, 6):
            task = bridge.process_request(
                {"jsonrpc": "2.0", "method": "tools/list", "id": i}
            )
            tasks.append(task)

        for i in range(6, 11):
            task = bridge.process_request(
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_code",
                        "arguments": {"query_text": f"query{i}"},
                    },
                    "id": i,
                }
            )
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # Validate all responses
        assert len(responses) == 10
        for i, response in enumerate(responses, start=1):
            assert response["id"] == i
            assert "result" in response

    @pytest.mark.asyncio
    async def test_concurrent_with_errors(self, bridge_config, test_server):
        """Test concurrent requests with mix of successes and errors."""
        bridge = Bridge(bridge_config)

        tasks = []

        # Valid requests
        for i in [1, 3, 5, 7, 9]:
            task = bridge.process_request(
                {"jsonrpc": "2.0", "method": "tools/list", "id": i}
            )
            tasks.append(task)

        # Invalid requests (missing method)
        for i in [2, 4, 6, 8, 10]:
            task = bridge.process_request({"jsonrpc": "2.0", "id": i})
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # Validate all responses
        assert len(responses) == 10

        # Check odd IDs succeeded
        for i in [1, 3, 5, 7, 9]:
            response = next((r for r in responses if r["id"] == i), None)
            assert response is not None
            assert "result" in response

        # Check even IDs failed
        for i in [2, 4, 6, 8, 10]:
            response = next((r for r in responses if r["id"] == i), None)
            assert response is not None
            assert "error" in response
