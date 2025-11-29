"""Tests for MCP-specific null ID prohibition.

MCP specification STRICTLY PROHIBITS null IDs in responses, unlike standard JSON-RPC 2.0.
Per MCP spec: id field MUST be string or integer, NEVER null.

These tests verify that ALL error responses use valid IDs (0 for parse errors where
request ID cannot be extracted, original request ID otherwise).
"""

import json
import pytest

from code_indexer.mcpb.bridge import Bridge
from code_indexer.mcpb.config import BridgeConfig
from code_indexer.mcpb.protocol import (
    create_error_response,
    PARSE_ERROR,
    INVALID_REQUEST,
)


class TestMcpNullIdProhibition:
    """Test that MCP responses NEVER contain null IDs."""

    def test_parse_error_uses_zero_id_not_null(self):
        """Test that parse errors use id=0 instead of null per MCP spec."""
        # MCP spec: For parse errors where request ID cannot be determined,
        # use id=0 instead of null
        error_response = create_error_response(
            request_id=0,  # MCP requires valid ID, use 0 for parse errors
            code=PARSE_ERROR,
            message="Parse error",
            data={"detail": "Invalid JSON"},
        )

        response_dict = error_response.to_dict()

        # CRITICAL: MCP spec PROHIBITS null IDs
        assert response_dict["id"] is not None, "MCP spec prohibits null IDs"
        assert response_dict["id"] == 0, "Parse errors should use id=0 per MCP spec"
        assert response_dict["error"]["code"] == PARSE_ERROR

    def test_invalid_request_uses_zero_id_when_id_cannot_be_extracted(self):
        """Test that invalid request errors use id=0 when request ID unavailable."""
        # When request is so malformed that ID cannot be extracted,
        # use id=0 per MCP spec
        error_response = create_error_response(
            request_id=0,
            code=INVALID_REQUEST,
            message="Invalid Request",
            data={"detail": "Missing required field"},
        )

        response_dict = error_response.to_dict()

        # CRITICAL: MCP spec PROHIBITS null IDs
        assert response_dict["id"] is not None, "MCP spec prohibits null IDs"
        assert (
            response_dict["id"] == 0
        ), "Invalid request errors should use id=0 when ID unavailable"

    @pytest.mark.asyncio
    async def test_bridge_parse_error_never_returns_null_id(self):
        """Test that bridge.process_line returns id=0 for parse errors, not null."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:8765",
            bearer_token="test-token",
            timeout=30,
        )
        bridge = Bridge(config)

        # Malformed JSON that cannot be parsed
        malformed_line = '{"jsonrpc": "2.0", "method": "tools/list", "id": 1'
        response = await bridge.process_line(malformed_line)

        # CRITICAL: MCP spec PROHIBITS null IDs
        assert response["id"] is not None, "MCP spec prohibits null IDs in responses"
        assert response["id"] == 0, "Parse errors must use id=0 per MCP spec"
        assert response["error"]["code"] == PARSE_ERROR

    @pytest.mark.asyncio
    async def test_bridge_invalid_request_never_returns_null_id(self):
        """Test that bridge.process_line returns id=0 for invalid requests when ID unavailable."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:8765",
            bearer_token="test-token",
            timeout=30,
        )
        bridge = Bridge(config)

        # Invalid JSON-RPC request (missing jsonrpc field)
        invalid_line = '{"method": "tools/list", "id": 1}'
        response = await bridge.process_line(invalid_line)

        # CRITICAL: MCP spec PROHIBITS null IDs
        assert response["id"] is not None, "MCP spec prohibits null IDs in responses"
        assert (
            response["id"] == 0
        ), "Invalid requests must use id=0 when ID cannot be extracted"
        assert response["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_bridge_preserves_request_id_when_available(self):
        """Test that bridge preserves original request ID when it can be extracted."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:8765",
            bearer_token="test-token",
            timeout=30,
        )
        bridge = Bridge(config)

        # Invalid request but with valid ID that can be extracted
        request = {"jsonrpc": "2.0", "id": 42}  # Missing method field
        response = await bridge.process_request(request)

        # Should preserve original request ID
        assert (
            response["id"] == 42
        ), "Should preserve original request ID when available"
        assert response["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_bridge_uses_string_id_when_provided(self):
        """Test that bridge correctly handles string IDs."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:8765",
            bearer_token="test-token",
            timeout=30,
        )
        bridge = Bridge(config)

        # Invalid request with string ID
        request = {"jsonrpc": "2.0", "id": "test-id-123"}  # Missing method field
        response = await bridge.process_request(request)

        # Should preserve string ID
        assert response["id"] == "test-id-123", "Should preserve string IDs"
        assert response["error"]["code"] == INVALID_REQUEST

    def test_error_response_serialization_never_produces_null_id(self):
        """Test that serialized error responses never contain null IDs."""
        # Test with id=0 (MCP-compliant parse error)
        error_response = create_error_response(
            request_id=0,
            code=PARSE_ERROR,
            message="Parse error",
        )

        json_str = error_response.to_json()
        parsed = json.loads(json_str)

        # Verify no null ID in serialized JSON
        assert parsed["id"] is not None, "Serialized response must not have null ID"
        assert parsed["id"] == 0, "Parse error should serialize with id=0"

    @pytest.mark.asyncio
    async def test_completely_invalid_json_returns_zero_id(self):
        """Test that completely invalid JSON (not parseable at all) returns id=0."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:8765",
            bearer_token="test-token",
            timeout=30,
        )
        bridge = Bridge(config)

        # Completely invalid JSON
        response = await bridge.process_line("not valid json at all")

        # CRITICAL: MCP spec PROHIBITS null IDs
        assert response["id"] is not None, "MCP spec prohibits null IDs"
        assert response["id"] == 0, "Unparseable JSON should return id=0"
        assert response["error"]["code"] == PARSE_ERROR
