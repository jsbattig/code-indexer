"""Tests for /mcp-public endpoint."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Create test app with isolated user storage."""
    users_file = tmp_path / "users.json"
    users_file.write_text("{}")
    monkeypatch.setenv("CIDX_USERS_FILE", str(users_file))

    from code_indexer.server.app import create_app
    from code_indexer.server.auth.user_manager import UserManager
    from code_indexer.server.auth import dependencies
    import code_indexer.server.app as app_module

    um = UserManager(str(users_file))
    app = create_app()
    dependencies.user_manager = um
    app_module.user_manager = um
    um.seed_initial_admin()

    return app, um


@pytest.fixture
def client(test_app):
    """Create test client."""
    app, _ = test_app
    return TestClient(app)


class TestMcpPublicEndpointAccess:
    """Tests for /mcp-public accessibility without auth."""

    def test_mcp_public_post_accessible_without_auth(self, client):
        """Test POST /mcp-public accessible without authentication."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data

    @pytest.mark.skip(
        reason="SSE endpoints with infinite generators block TestClient; verified by POST tests and integration"
    )
    def test_mcp_public_get_accessible_without_auth(self, client):
        """Test GET /mcp-public (SSE) accessible without authentication.

        Note: This test is skipped because SSE endpoints with infinite generators
        cannot be properly tested with sync TestClient. The endpoint functionality
        is verified by:
        1. POST endpoint tests (same routing and auth logic)
        2. Manual integration testing
        """
        pass

    def test_mcp_public_no_www_authenticate_header(self, client):
        """Test /mcp-public doesn't return WWW-Authenticate header."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        assert "WWW-Authenticate" not in response.headers

    def test_mcp_public_has_session_id_header(self, client):
        """Test /mcp-public returns Mcp-Session-Id header."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        assert "Mcp-Session-Id" in response.headers


class TestMcpPublicToolsListUnauthenticated:
    """Tests for tools/list on /mcp-public without authentication."""

    def test_tools_list_returns_only_authenticate(self, client):
        """Test unauthenticated tools/list returns only authenticate tool."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        tools = data["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "authenticate"

    def test_authenticate_tool_has_input_schema(self, client):
        """Test authenticate tool has proper input schema."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        data = response.json()
        tool = data["result"]["tools"][0]
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "username" in schema["properties"]
        assert "api_key" in schema["properties"]


class TestMcpPublicToolCallUnauthenticated:
    """Tests for tools/call on /mcp-public without authentication."""

    def test_tool_call_blocked_without_auth(self, client):
        """Test non-authenticate tools/call returns auth required error."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_repositories", "arguments": {}},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "Authentication required" in data["error"]["message"]

    def test_authenticate_tool_call_allowed_without_auth(self, client):
        """Test authenticate tool can be called without prior auth."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "test", "api_key": "test"},
                },
            },
        )
        data = response.json()
        if "error" in data:
            assert "Authentication required" not in data["error"]["message"]


class TestMcpPublicInitialize:
    """Tests for initialize method on /mcp-public."""

    def test_initialize_returns_protocol_version(self, client):
        """Test initialize returns proper MCP protocol info."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["serverInfo"]["name"] == "CIDX"
        assert "capabilities" in result


class TestMcpPublicVsRegularMcp:
    """Tests comparing /mcp-public vs /mcp behavior."""

    def test_regular_mcp_requires_auth(self, client):
        """Test regular /mcp POST requires authentication."""
        response = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 401

    def test_regular_mcp_sse_returns_www_authenticate(self, client):
        """Test regular /mcp GET returns WWW-Authenticate header."""
        response = client.get("/mcp")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers


class TestMcpPublicInputValidation:
    """Tests for input validation on /mcp-public endpoint."""

    def test_invalid_params_type_returns_error(self, client):
        """Test that non-dict params returns JSON-RPC error -32602."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": ["invalid", "array", "params"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "must be an object" in data["error"]["message"]

    def test_valid_dict_params_accepted(self, client):
        """Test that dict params are accepted normally."""
        response = client.post(
            "/mcp-public",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
