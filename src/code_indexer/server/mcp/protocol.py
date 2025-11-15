"""MCP JSON-RPC 2.0 protocol handler.

Implements the Model Context Protocol (MCP) JSON-RPC 2.0 endpoint for tool discovery
and execution. Phase 1 implementation with stub handlers for tools/list and tools/call.
"""

from fastapi import APIRouter, Depends, Request
from typing import Dict, Any, List, Optional, Tuple, Union
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User

mcp_router = APIRouter()


def validate_jsonrpc_request(
    request: Dict[str, Any],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validate JSON-RPC 2.0 request structure.

    Args:
        request: The JSON-RPC request dictionary

    Returns:
        Tuple of (is_valid, error_dict). error_dict is None if valid.
    """
    # Check jsonrpc field
    if "jsonrpc" not in request:
        return False, {
            "code": -32600,
            "message": "Invalid Request: missing 'jsonrpc' field",
        }

    if request["jsonrpc"] != "2.0":
        return False, {
            "code": -32600,
            "message": "Invalid Request: jsonrpc must be '2.0'",
        }

    # Check method field
    if "method" not in request:
        return False, {
            "code": -32600,
            "message": "Invalid Request: missing 'method' field",
        }

    if not isinstance(request["method"], str):
        return False, {
            "code": -32600,
            "message": "Invalid Request: method must be a string",
        }

    # Check params field (optional, but if present must be object or array)
    if "params" in request and request["params"] is not None:
        if not isinstance(request["params"], (dict, list)):
            return False, {
                "code": -32600,
                "message": "Invalid Request: params must be an object or array",
            }

    return True, None


def create_jsonrpc_response(
    result: Any, request_id: Union[str, int, None]
) -> Dict[str, Any]:
    """
    Create a JSON-RPC 2.0 success response.

    Args:
        result: The result data
        request_id: The request id (can be string, number, or null)

    Returns:
        JSON-RPC success response dictionary
    """
    return {"jsonrpc": "2.0", "result": result, "id": request_id}


def create_jsonrpc_error(
    code: int,
    message: str,
    request_id: Union[str, int, None],
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a JSON-RPC 2.0 error response.

    Args:
        code: Error code (e.g., -32601 for Method not found)
        message: Error message
        request_id: The request id
        data: Optional additional error data

    Returns:
        JSON-RPC error response dictionary
    """
    error_obj = {"code": code, "message": message}

    if data is not None:
        error_obj["data"] = data

    return {"jsonrpc": "2.0", "error": error_obj, "id": request_id}


async def handle_tools_list(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """
    Handle tools/list method.

    Args:
        params: Request parameters
        user: Authenticated user

    Returns:
        Dictionary with tools list filtered by user role
    """
    from .tools import filter_tools_by_role

    tools = filter_tools_by_role(user)
    return {"tools": tools}


async def handle_tools_call(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """
    Handle tools/call method (Phase 1 stub).

    Args:
        params: Request parameters (must contain 'name' and optional 'arguments')
        user: Authenticated user

    Returns:
        Dictionary with call result

    Raises:
        ValueError: If required parameters are missing
    """
    # Validate required 'name' parameter
    if "name" not in params:
        raise ValueError("Missing required parameter: name")

    tool_name = params["name"]
    _ = params.get("arguments", {})  # Arguments will be used in Phase 3

    # Phase 1: Return stub success
    # Phase 3 will implement actual tool wrappers
    return {"success": True, "message": f"Tool {tool_name} called (stub)"}


async def process_jsonrpc_request(
    request: Dict[str, Any], user: User
) -> Dict[str, Any]:
    """
    Process a single JSON-RPC 2.0 request.

    Args:
        request: The JSON-RPC request dictionary
        user: Authenticated user

    Returns:
        JSON-RPC response dictionary (success or error)
    """
    request_id = request.get("id")

    # Validate request structure
    is_valid, error = validate_jsonrpc_request(request)
    if not is_valid:
        return create_jsonrpc_error(error["code"], error["message"], request_id)

    method = request["method"]
    params = request.get("params") or {}

    # Route to appropriate handler
    try:
        if method == "tools/list":
            result = await handle_tools_list(params, user)
            return create_jsonrpc_response(result, request_id)
        elif method == "tools/call":
            result = await handle_tools_call(params, user)
            return create_jsonrpc_response(result, request_id)
        else:
            return create_jsonrpc_error(
                -32601, f"Method not found: {method}", request_id
            )
    except ValueError as e:
        # Invalid params error
        return create_jsonrpc_error(-32602, f"Invalid params: {str(e)}", request_id)
    except Exception as e:
        # Internal error
        return create_jsonrpc_error(
            -32603,
            f"Internal error: {str(e)}",
            request_id,
            data={"exception_type": type(e).__name__},
        )


async def process_batch_request(
    batch: List[Dict[str, Any]], user: User
) -> List[Dict[str, Any]]:
    """
    Process a batch of JSON-RPC 2.0 requests.

    Args:
        batch: List of JSON-RPC request dictionaries
        user: Authenticated user

    Returns:
        List of JSON-RPC response dictionaries
    """
    responses = []

    for request in batch:
        response = await process_jsonrpc_request(request, user)
        responses.append(response)

    return responses


@mcp_router.post("/mcp")
async def mcp_endpoint(
    request: Request, current_user: User = Depends(get_current_user)
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    MCP JSON-RPC 2.0 endpoint.

    Handles tool discovery and execution via JSON-RPC 2.0 protocol.
    Supports both single requests and batch requests.

    Args:
        request: FastAPI Request object
        current_user: Authenticated user (from Bearer token)

    Returns:
        JSON-RPC response (single or batch)
    """
    try:
        body = await request.json()
    except Exception:
        # Parse error - return JSON-RPC error
        return create_jsonrpc_error(-32700, "Parse error: Invalid JSON", None)

    # Check if batch request (array) or single request (object)
    if isinstance(body, list):
        return await process_batch_request(body, current_user)
    elif isinstance(body, dict):
        return await process_jsonrpc_request(body, current_user)
    else:
        return create_jsonrpc_error(
            -32600, "Invalid Request: body must be object or array", None
        )
