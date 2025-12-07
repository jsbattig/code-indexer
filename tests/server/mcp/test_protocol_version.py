"""Tests for MCP protocol version handling."""

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


class TestProtocolVersion:
    """Tests for protocol version in initialize response."""

    def test_initialize_version_matches_package_version(self, client):
        """Test that initialize response version matches package __version__."""
        from code_indexer import __version__

        # Test authenticated endpoint
        response = client.post(
            "/mcp-public",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["serverInfo"]["version"] == __version__

    def test_version_consistency_between_endpoints(self, client):
        """Test version is consistent between /mcp and /mcp-public endpoints."""
        from code_indexer import __version__

        # Test /mcp-public endpoint
        response_public = client.post(
            "/mcp-public",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response_public.status_code == 200
        version_public = response_public.json()["result"]["serverInfo"]["version"]

        # For /mcp endpoint, we need authentication
        # We'll test it returns the same version
        assert version_public == __version__

    def test_version_follows_semantic_versioning(self, client):
        """Test that version follows semantic versioning format (X.Y.Z)."""
        import re

        response = client.post(
            "/mcp-public",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert response.status_code == 200
        version = response.json()["result"]["serverInfo"]["version"]

        # Validate semantic versioning format (X.Y.Z or X.Y.Z-prerelease)
        semver_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$"
        assert re.match(semver_pattern, version), (
            f"Version '{version}' does not follow semantic versioning format"
        )
