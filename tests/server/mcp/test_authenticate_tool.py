"""Tests for authenticate MCP tool."""

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
    app, _ = test_app
    return TestClient(app)


@pytest.fixture
def admin_api_key(test_app):
    """Create an API key for admin user."""
    _, um = test_app
    from code_indexer.server.auth.api_key_manager import ApiKeyManager

    akm = ApiKeyManager(um)
    raw_key, key_id = akm.generate_key("admin", "test-key")
    return raw_key


class TestAuthenticateToolRegistration:
    """Tests for authenticate tool in registry."""

    def test_authenticate_tool_in_tools_list(self, client):
        """Test authenticate tool appears in tools/list."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert response.status_code == 200
        data = response.json()
        tools = data["result"]["tools"]
        assert any(t["name"] == "authenticate" for t in tools)

    def test_authenticate_tool_has_correct_schema(self, client):
        """Test authenticate tool has required parameters."""
        response = client.post(
            "/mcp-public", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        tools = response.json()["result"]["tools"]
        auth_tool = next(t for t in tools if t["name"] == "authenticate")
        assert "username" in auth_tool["inputSchema"]["properties"]
        assert "api_key" in auth_tool["inputSchema"]["properties"]


class TestAuthenticateSuccess:
    """Tests for successful authentication."""

    def test_valid_credentials_returns_success(self, client, admin_api_key):
        """Test valid username and API key returns success."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "admin", "api_key": admin_api_key},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is True
        assert result["username"] == "admin"

    def test_valid_credentials_sets_cookie(self, client, admin_api_key):
        """Test successful auth sets JWT cookie."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "admin", "api_key": admin_api_key},
                },
            },
        )
        assert "cidx_session" in response.cookies

    def test_cookie_has_security_attributes(self, client, admin_api_key):
        """Test JWT cookie has HttpOnly, Secure, and SameSite attributes."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "admin", "api_key": admin_api_key},
                },
            },
        )

        # Verify cookie exists
        assert "cidx_session" in response.cookies

        # Parse Set-Cookie header to verify security attributes
        set_cookie_header = response.headers.get("set-cookie", "")

        # Verify security attributes are present in Set-Cookie header
        assert "HttpOnly" in set_cookie_header, "Cookie must have HttpOnly flag"
        assert "Secure" in set_cookie_header, "Cookie must have Secure flag"
        assert "SameSite" in set_cookie_header, "Cookie must have SameSite attribute"

        # Also verify via cookie jar
        cookie = next(c for c in response.cookies.jar if c.name == "cidx_session")
        assert cookie.secure is True, "Cookie secure attribute must be True"
        assert cookie.path == "/", "Cookie path must be /"


class TestAuthenticateFailure:
    """Tests for failed authentication."""

    def test_invalid_username_returns_error(self, client, admin_api_key):
        """Test invalid username returns error."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "nonexistent", "api_key": admin_api_key},
                },
            },
        )
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is False
        assert "Invalid credentials" in result["error"]

    def test_invalid_api_key_returns_error(self, client):
        """Test invalid API key returns error."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "admin", "api_key": "cidx_sk_invalid"},
                },
            },
        )
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is False
        assert "Invalid credentials" in result["error"]

    def test_missing_params_returns_error(self, client):
        """Test missing params returns error."""
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "authenticate", "arguments": {}},
            },
        )
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is False


class TestAuthenticateRateLimiting:
    """Integration tests for rate limiting behavior in authenticate handler."""

    def test_rate_limit_blocks_after_10_failures(self, client):
        """After 10 failed attempts for a username, the 11th is rate limited."""
        # Use a distinct username so other tests don't affect its bucket
        username = "rluser"
        for i in range(10):
            response = client.post(
                "/mcp-public",
                json={
                    "jsonrpc": "2.0",
                    "id": i + 1,
                    "method": "tools/call",
                    "params": {
                        "name": "authenticate",
                        "arguments": {
                            "username": username,
                            "api_key": "cidx_sk_invalid",
                        },
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            content = data["result"]["content"][0]["text"]
            import json

            result = json.loads(content)
            # First 10 attempts may show Invalid credentials (rate limiter allows 10)
            assert result["success"] is False

        # 11th attempt should return a rate limit error with retry_after
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": username, "api_key": "cidx_sk_invalid"},
                },
            },
        )
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is False
        assert "rate" in result["error"].lower()
        assert isinstance(result.get("retry_after"), (int, float))
        assert 5 <= result["retry_after"] <= 7

    def test_successful_auth_refund_preserves_tokens(self, client, admin_api_key):
        """Successful authentication should not reduce token bucket for that user."""
        from code_indexer.server.auth.token_bucket import rate_limiter

        # Ensure bucket exists and get starting tokens
        _ = rate_limiter.get_tokens("admin")
        tokens_before = rate_limiter.get_tokens("admin")

        # Perform successful authentication
        response = client.post(
            "/mcp-public",
            json={
                "jsonrpc": "2.0",
                "id": 123,
                "method": "tools/call",
                "params": {
                    "name": "authenticate",
                    "arguments": {"username": "admin", "api_key": admin_api_key},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        content = data["result"]["content"][0]["text"]
        import json

        result = json.loads(content)
        assert result["success"] is True

        tokens_after = rate_limiter.get_tokens("admin")
        # Allow tiny drift due to time passing, but ensure effectively unchanged
        assert tokens_after >= tokens_before - 0.1
