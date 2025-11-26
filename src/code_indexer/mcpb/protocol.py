"""JSON-RPC 2.0 protocol handling for MCP Stdio Bridge.

This module handles parsing, validation, and creation of JSON-RPC 2.0 messages
according to the specification at https://www.jsonrpc.org/specification
"""

import json
from dataclasses import dataclass
from typing import Any, Optional, Union


# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000  # Server error (implementation-defined)


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request.

    Args:
        jsonrpc: JSON-RPC version (must be "2.0")
        method: Method name to invoke
        id: Request identifier
        params: Optional method parameters
    """

    jsonrpc: str
    method: str
    id: Union[int, str, None]
    params: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert request to dictionary."""
        result: dict = {"jsonrpc": self.jsonrpc, "method": self.method, "id": self.id}
        if self.params is not None:
            result["params"] = self.params
        return result

    def to_json(self) -> str:
        """Convert request to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class JsonRpcError:
    """JSON-RPC 2.0 error object.

    Args:
        code: Error code
        message: Error message
        data: Optional additional error data
    """

    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> dict:
        """Convert error to dictionary."""
        result = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response.

    Args:
        jsonrpc: JSON-RPC version (must be "2.0")
        id: Request identifier
        result: Result object (for success)
        error: Error object (for errors)

    Note: Response must have either result OR error, but not both.
    """

    jsonrpc: str
    id: Union[int, str, None]
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None

    def __post_init__(self):
        """Validate response after initialization."""
        if self.result is not None and self.error is not None:
            raise ValueError("Response cannot have both result and error")
        if self.result is None and self.error is None:
            raise ValueError("Response must have either result or error")

    def to_dict(self) -> dict:
        """Convert response to dictionary."""
        result: dict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result
        return result

    def to_json(self) -> str:
        """Convert response to JSON string."""
        return json.dumps(self.to_dict())


def parse_jsonrpc_request(line: str) -> JsonRpcRequest:
    """Parse JSON-RPC request from string.

    Args:
        line: JSON string containing request

    Returns:
        JsonRpcRequest instance

    Raises:
        json.JSONDecodeError: If JSON is malformed
        ValueError: If required fields are missing or invalid
    """
    data = json.loads(line)

    # Validate required fields
    if "jsonrpc" not in data:
        raise ValueError("Missing required field: jsonrpc")
    if "method" not in data:
        raise ValueError("Missing required field: method")
    if "id" not in data:
        raise ValueError("Missing required field: id")

    # Validate JSON-RPC version
    if data["jsonrpc"] != "2.0":
        raise ValueError(f"Invalid jsonrpc version: {data['jsonrpc']} (expected '2.0')")

    return JsonRpcRequest(
        jsonrpc=data["jsonrpc"],
        method=data["method"],
        id=data["id"],
        params=data.get("params"),
    )


def create_error_response(
    request_id: Union[int, str, None],
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> JsonRpcResponse:
    """Create JSON-RPC error response.

    Args:
        request_id: Request identifier (can be None for parse errors)
        code: Error code
        message: Error message
        data: Optional additional error data

    Returns:
        JsonRpcResponse with error
    """
    error = JsonRpcError(code=code, message=message, data=data)
    return JsonRpcResponse(jsonrpc="2.0", id=request_id, error=error)


def create_success_response(
    request_id: Union[int, str, None], result: Any
) -> JsonRpcResponse:
    """Create JSON-RPC success response.

    Args:
        request_id: Request identifier
        result: Result data

    Returns:
        JsonRpcResponse with result
    """
    return JsonRpcResponse(jsonrpc="2.0", id=request_id, result=result)
