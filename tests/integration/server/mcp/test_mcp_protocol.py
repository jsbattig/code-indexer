"""Integration tests for MCP JSON-RPC 2.0 protocol handler."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil


class TestMCPProtocolIntegration:
    """Integration tests for MCP protocol endpoint."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for test databases."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def test_app(self, temp_db_dir):
        """Create test FastAPI app with MCP endpoints."""
        from fastapi import FastAPI
        from code_indexer.server.mcp.protocol import mcp_router
        from code_indexer.server.auth.jwt_manager import JWTManager
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.auth import dependencies

        app = FastAPI()

        # Initialize auth infrastructure
        jwt_manager = JWTManager(secret_key="test-secret")
        user_db_path = temp_db_dir / "users.json"
        user_manager = UserManager(str(user_db_path))

        # Create test user with strong password
        user_manager.create_user("testuser", "TestPassword123!@#", UserRole.POWER_USER)

        # Set global dependencies
        dependencies.jwt_manager = jwt_manager
        dependencies.user_manager = user_manager

        # Mount MCP router
        app.include_router(mcp_router, tags=["MCP"])

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, temp_db_dir):
        """Create authentication headers for testing."""
        from code_indexer.server.auth.jwt_manager import JWTManager

        jwt_manager = JWTManager(secret_key="test-secret")
        user_data = {"username": "testuser", "role": "power_user"}
        token = jwt_manager.create_token(user_data)

        return {"Authorization": f"Bearer {token}"}

    def test_valid_jsonrpc_request_structure(self, test_app, auth_headers):
        """Test that valid JSON-RPC 2.0 request is accepted."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-1"}

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["id"] == "test-1"

    def test_missing_jsonrpc_field_returns_error(self, test_app, auth_headers):
        """Test that missing jsonrpc field returns invalid request error."""
        request = {"method": "tools/list", "id": "test-2"}

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == -32600  # Invalid Request
        assert data["id"] == "test-2"

    def test_unauthorized_request_without_token(self, test_app):
        """Test request without Bearer token returns 403."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-3"}

        response = test_app.post("/mcp", json=request)

        assert response.status_code in [401, 403]

    def test_invalid_bearer_token(self, test_app):
        """Test request with invalid Bearer token returns 403."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-4"}
        headers = {"Authorization": "Bearer invalid-token-xyz"}

        response = test_app.post("/mcp", json=request, headers=headers)

        assert response.status_code in [401, 403]

    def test_tools_call_method(self, test_app, auth_headers):
        """Test tools/call method execution."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_code", "arguments": {"query": "test"}},
            "id": "test-5",
        }

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["id"] == "test-5"

    def test_unknown_method(self, test_app, auth_headers):
        """Test unknown method returns Method not found error."""
        request = {"jsonrpc": "2.0", "method": "unknown/method", "id": "test-6"}

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_batch_request_processing(self, test_app, auth_headers):
        """Test batch request processing."""
        batch = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": "batch-1"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "batch-2"},
            {"jsonrpc": "2.0", "method": "tools/list", "id": "batch-3"},
        ]

        response = test_app.post("/mcp", json=batch, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["id"] == "batch-1"
        assert data[1]["id"] == "batch-2"
        assert data[2]["id"] == "batch-3"

    def test_batch_with_errors(self, test_app, auth_headers):
        """Test batch request with mix of valid and invalid requests."""
        batch = [
            {"jsonrpc": "2.0", "method": "tools/list", "id": "1"},
            {"method": "tools/list", "id": "2"},  # Missing jsonrpc
            {"jsonrpc": "2.0", "method": "unknown", "id": "3"},  # Unknown method
        ]

        response = test_app.post("/mcp", json=batch, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert "result" in data[0]
        assert "error" in data[1]
        assert "error" in data[2]

    def test_tools_call_missing_name_param(self, test_app, auth_headers):
        """Test tools/call without name parameter returns error."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"arguments": {}},
            "id": "test-7",
        }

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "name" in data["error"]["message"].lower()

    def test_invalid_json_body(self, test_app, auth_headers):
        """Test invalid JSON body returns parse error."""
        # Send malformed JSON
        response = test_app.post(
            "/mcp",
            data="not valid json{",
            headers={**auth_headers, "Content-Type": "application/json"},
        )

        # Our endpoint handles it gracefully and returns JSON-RPC error
        # or FastAPI returns 422 for invalid JSON
        assert response.status_code in [200, 400, 422]

    def test_numeric_request_id(self, test_app, auth_headers):
        """Test numeric request id is preserved."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 42}

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert isinstance(data["id"], int)

    def test_null_request_id(self, test_app, auth_headers):
        """Test null request id is preserved."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": None}

        response = test_app.post("/mcp", json=request, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] is None
