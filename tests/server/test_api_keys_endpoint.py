"""Integration tests for API keys endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Create test app with isolated user storage."""
    users_file = tmp_path / "users.json"
    users_file.write_text("{}")

    # Set environment variable before importing
    monkeypatch.setenv("CIDX_USERS_FILE", str(users_file))

    from code_indexer.server.app import create_app
    from code_indexer.server.auth.user_manager import UserManager
    from code_indexer.server.auth import dependencies
    import code_indexer.server.app as app_module

    # Create user manager
    um = UserManager(str(users_file))

    # Create app
    app = create_app()

    # Override user_manager in both places
    dependencies.user_manager = um
    app_module.user_manager = um

    # Seed initial admin
    um.seed_initial_admin()

    return app, um


@pytest.fixture
def client(test_app):
    """Create test client."""
    app, _ = test_app
    return TestClient(app)


@pytest.fixture
def auth_headers(client, test_app):
    """Get auth headers by logging in as admin."""
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestListApiKeys:
    """Tests for GET /api/keys endpoint."""

    def test_list_api_keys_empty(self, client, auth_headers):
        """Test listing keys when user has none."""
        response = client.get("/api/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert data["keys"] == []

    def test_list_api_keys_success(self, client, auth_headers):
        """Test listing keys after creating one."""
        # Create a key first
        create_response = client.post(
            "/api/keys", headers=auth_headers, json={"name": "test-key"}
        )
        assert create_response.status_code == 201

        # List keys
        response = client.get("/api/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["keys"]) == 1
        assert data["keys"][0]["name"] == "test-key"
        assert "key_id" in data["keys"][0]
        assert "created_at" in data["keys"][0]
        assert "key_prefix" in data["keys"][0]
        # Should NOT contain hash
        assert "hash" not in data["keys"][0]

    def test_list_api_keys_unauthenticated(self, client):
        """Test that unauthenticated requests are rejected."""
        response = client.get("/api/keys")
        assert response.status_code == 401


class TestDeleteApiKey:
    """Tests for DELETE /api/keys/{key_id} endpoint."""

    def test_delete_api_key_success(self, client, auth_headers):
        """Test successful key deletion."""
        # Create a key first
        create_response = client.post(
            "/api/keys", headers=auth_headers, json={"name": "to-delete"}
        )
        assert create_response.status_code == 201
        key_id = create_response.json()["key_id"]

        # Delete the key
        response = client.delete(f"/api/keys/{key_id}", headers=auth_headers)
        assert response.status_code == 200

        # Verify it's gone
        list_response = client.get("/api/keys", headers=auth_headers)
        assert list_response.status_code == 200
        assert len(list_response.json()["keys"]) == 0

    def test_delete_api_key_not_found(self, client, auth_headers):
        """Test deleting non-existent key returns 404."""
        response = client.delete("/api/keys/non-existent-id", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_api_key_unauthenticated(self, client):
        """Test that unauthenticated requests are rejected."""
        response = client.delete("/api/keys/some-id")
        assert response.status_code == 401
