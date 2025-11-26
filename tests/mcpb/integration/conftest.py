"""Shared fixtures for MCP Bridge integration tests."""

import asyncio
import threading
import json
from typing import Generator

import pytest
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import uvicorn

from code_indexer.mcpb.config import BridgeConfig
from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestMcpServer:
    """Real HTTP server for integration testing."""

    def __init__(self, port: int = 8765, bearer_token: str = "test-token-123"):
        self.app = FastAPI()
        self.port = port
        self.bearer_token = bearer_token
        self.server = None
        self.thread = None
        self._setup_routes()

    def _setup_routes(self):
        """Setup MCP endpoint routes."""

        @self.app.post("/mcp")
        async def mcp_endpoint(request: Request, authorization: str = Header(None)):
            """MCP endpoint that validates Bearer token and processes requests."""
            # Validate Bearer token
            if not authorization:
                raise HTTPException(
                    status_code=401, detail="Missing Authorization header"
                )

            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=401, detail="Invalid Authorization header format"
                )

            token = authorization[7:]  # Remove "Bearer " prefix
            if token != self.bearer_token:
                raise HTTPException(status_code=401, detail="Invalid token")

            # Parse JSON-RPC request
            try:
                jsonrpc_request = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    },
                )

            # Handle tools/list - return all 22 CIDX MCP tools
            if jsonrpc_request.get("method") == "tools/list":
                # Build tools list from TOOL_REGISTRY (excluding required_permission)
                tools = []
                for name, tool_def in TOOL_REGISTRY.items():
                    tools.append(
                        {
                            "name": tool_def["name"],
                            "description": tool_def["description"],
                            "inputSchema": tool_def["inputSchema"],
                        }
                    )

                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "result": {"tools": tools},
                        "id": jsonrpc_request.get("id"),
                    }
                )

            # Handle tools/call for search_code
            if jsonrpc_request.get("method") == "tools/call":
                params = jsonrpc_request.get("params", {})
                if params.get("name") == "search_code":
                    query_text = params.get("arguments", {}).get("query_text", "")
                    return JSONResponse(
                        content={
                            "jsonrpc": "2.0",
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Results for query: {query_text}",
                                    }
                                ]
                            },
                            "id": jsonrpc_request.get("id"),
                        }
                    )

            # Unknown method
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {jsonrpc_request.get('method')}",
                    },
                    "id": jsonrpc_request.get("id"),
                }
            )

    def start(self):
        """Start the test server in a background thread."""
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=self.port, log_level="error"
        )
        self.server = uvicorn.Server(config)

        def run_server():
            asyncio.run(self.server.serve())

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        # Wait for server to be ready
        import time as time_module

        time_module.sleep(0.5)

    def stop(self):
        """Stop the test server."""
        if self.server:
            self.server.should_exit = True
            if self.thread:
                self.thread.join(timeout=2)


@pytest.fixture
def test_server() -> Generator[TestMcpServer, None, None]:
    """Fixture providing a running test MCP server."""
    server = TestMcpServer(port=8765, bearer_token="test-token-123")
    server.start()
    yield server
    server.stop()


@pytest.fixture
def bridge_config(test_server) -> BridgeConfig:
    """Fixture providing bridge configuration for test server."""
    return BridgeConfig(
        server_url=f"http://127.0.0.1:{test_server.port}",
        bearer_token=test_server.bearer_token,
        timeout=30,
    )
