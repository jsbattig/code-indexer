"""Unit tests for JSON-RPC protocol handling.

This module tests JSON-RPC parsing, validation, and error response generation
according to the JSON-RPC 2.0 specification.
"""

import json
import pytest

from code_indexer.mcpb.protocol import (
    JsonRpcResponse,
    JsonRpcError,
    parse_jsonrpc_request,
    create_error_response,
    PARSE_ERROR,
    INVALID_REQUEST,
    SERVER_ERROR,
)


class TestJsonRpcRequestParsing:
    """Test JSON-RPC request parsing and validation."""

    def test_parse_valid_request_without_params(self):
        """Test parsing a valid JSON-RPC request without params."""
        line = '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
        request = parse_jsonrpc_request(line)

        assert request.jsonrpc == "2.0"
        assert request.method == "tools/list"
        assert request.id == 1
        assert request.params is None

    def test_parse_valid_request_with_params(self):
        """Test parsing a valid JSON-RPC request with params."""
        line = '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "query", "arguments": {"query": "test"}}, "id": 2}'
        request = parse_jsonrpc_request(line)

        assert request.jsonrpc == "2.0"
        assert request.method == "tools/call"
        assert request.id == 2
        assert request.params == {"name": "query", "arguments": {"query": "test"}}

    def test_parse_malformed_json_raises_error(self):
        """Test that malformed JSON raises appropriate error."""
        line = '{"jsonrpc": "2.0", "method": "tools/list", "id": 1'  # Missing closing brace

        with pytest.raises(json.JSONDecodeError):
            parse_jsonrpc_request(line)

    def test_parse_missing_jsonrpc_field_raises_error(self):
        """Test that missing jsonrpc field raises validation error."""
        line = '{"method": "tools/list", "id": 1}'

        with pytest.raises(ValueError, match="Missing required field: jsonrpc"):
            parse_jsonrpc_request(line)

    def test_parse_missing_method_field_raises_error(self):
        """Test that missing method field raises validation error."""
        line = '{"jsonrpc": "2.0", "id": 1}'

        with pytest.raises(ValueError, match="Missing required field: method"):
            parse_jsonrpc_request(line)

    def test_parse_missing_id_field_raises_error(self):
        """Test that missing id field raises validation error."""
        line = '{"jsonrpc": "2.0", "method": "tools/list"}'

        with pytest.raises(ValueError, match="Missing required field: id"):
            parse_jsonrpc_request(line)

    def test_parse_invalid_jsonrpc_version(self):
        """Test that invalid JSON-RPC version raises validation error."""
        line = '{"jsonrpc": "1.0", "method": "tools/list", "id": 1}'

        with pytest.raises(ValueError, match="Invalid jsonrpc version"):
            parse_jsonrpc_request(line)

    def test_parse_integer_id(self):
        """Test parsing request with integer ID."""
        line = '{"jsonrpc": "2.0", "method": "tools/list", "id": 42}'
        request = parse_jsonrpc_request(line)

        assert request.id == 42

    def test_parse_string_id(self):
        """Test parsing request with string ID."""
        line = '{"jsonrpc": "2.0", "method": "tools/list", "id": "req-123"}'
        request = parse_jsonrpc_request(line)

        assert request.id == "req-123"

    def test_parse_null_id(self):
        """Test parsing request with null ID."""
        line = '{"jsonrpc": "2.0", "method": "tools/list", "id": null}'
        request = parse_jsonrpc_request(line)

        assert request.id is None


class TestJsonRpcErrorResponse:
    """Test JSON-RPC error response generation."""

    def test_create_parse_error_response(self):
        """Test creating a parse error response."""
        error_response = create_error_response(
            request_id=None,
            code=PARSE_ERROR,
            message="Parse error",
            data={"detail": "Invalid JSON"},
        )

        assert error_response.jsonrpc == "2.0"
        assert error_response.id is None
        assert error_response.error.code == -32700
        assert error_response.error.message == "Parse error"
        assert error_response.error.data == {"detail": "Invalid JSON"}

    def test_create_invalid_request_error(self):
        """Test creating an invalid request error response."""
        error_response = create_error_response(
            request_id=1, code=INVALID_REQUEST, message="Invalid Request"
        )

        assert error_response.jsonrpc == "2.0"
        assert error_response.id == 1
        assert error_response.error.code == -32600
        assert error_response.error.message == "Invalid Request"
        assert error_response.error.data is None

    def test_create_server_error(self):
        """Test creating a server error response."""
        error_response = create_error_response(
            request_id=2,
            code=SERVER_ERROR,
            message="Server unavailable",
            data={"url": "https://example.com"},
        )

        assert error_response.jsonrpc == "2.0"
        assert error_response.id == 2
        assert error_response.error.code == -32000
        assert error_response.error.message == "Server unavailable"
        assert error_response.error.data == {"url": "https://example.com"}

    def test_error_response_serialization(self):
        """Test that error response can be serialized to JSON."""
        error_response = create_error_response(
            request_id=1, code=SERVER_ERROR, message="Test error"
        )

        json_str = error_response.to_json()
        parsed = json.loads(json_str)

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["error"]["code"] == -32000
        assert parsed["error"]["message"] == "Test error"


class TestJsonRpcSuccessResponse:
    """Test JSON-RPC success response handling."""

    def test_create_success_response(self):
        """Test creating a success response."""
        response = JsonRpcResponse(
            jsonrpc="2.0", id=1, result={"tools": ["query", "index"]}
        )

        assert response.jsonrpc == "2.0"
        assert response.id == 1
        assert response.result == {"tools": ["query", "index"]}
        assert response.error is None

    def test_success_response_serialization(self):
        """Test that success response can be serialized to JSON."""
        response = JsonRpcResponse(jsonrpc="2.0", id=1, result={"status": "ok"})

        json_str = response.to_json()
        parsed = json.loads(json_str)

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"] == {"status": "ok"}
        assert "error" not in parsed

    def test_response_cannot_have_both_result_and_error(self):
        """Test that response cannot have both result and error."""
        with pytest.raises(
            ValueError, match="Response cannot have both result and error"
        ):
            JsonRpcResponse(
                jsonrpc="2.0",
                id=1,
                result={"status": "ok"},
                error=JsonRpcError(code=-32000, message="Error"),
            )

    def test_response_must_have_result_or_error(self):
        """Test that response must have either result or error."""
        with pytest.raises(
            ValueError, match="Response must have either result or error"
        ):
            JsonRpcResponse(jsonrpc="2.0", id=1)
