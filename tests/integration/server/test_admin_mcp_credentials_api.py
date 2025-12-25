"""
Integration tests for admin MCP credentials API endpoints.

Tests admin endpoints for managing user MCP credentials with real FastAPI test client.
Following CLAUDE.md Foundation #1: NO MOCKS - Real integration testing.
"""

import pytest
import json
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timezone

from code_indexer.server.app import create_app
from code_indexer.server.auth.password_manager import PasswordManager


class TestAdminMCPCredentialsAPI:
    """Integration tests for admin MCP credentials API endpoints."""

    @pytest.fixture
    def temp_users_file(self):
        """Create temporary users file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        users_file = temp_dir / "users.json"

        # Create test users (admin and normal users)
        password_manager = PasswordManager()
        test_users = {
            "admin_user": {
                "user_id": "admin_user",
                "username": "admin_user",
                "password_hash": password_manager.hash_password("AdminPass123!"),
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "test_user": {
                "user_id": "test_user",
                "username": "test_user",
                "password_hash": password_manager.hash_password("TestPass123!"),
                "role": "normal_user",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mcp_credentials": []
            },
            "another_user": {
                "user_id": "another_user",
                "username": "another_user",
                "password_hash": password_manager.hash_password("AnotherPass123!"),
                "role": "normal_user",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mcp_credentials": []
            },
        }

        users_file.write_text(json.dumps(test_users, indent=2))

        yield str(users_file)

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def client(self, temp_users_file):
        """Create FastAPI test client with test user manager."""
        import os

        # Set environment variable to use test directory before creating app
        test_data_dir = str(Path(temp_users_file).parent)
        os.environ["CIDX_SERVER_DATA_DIR"] = test_data_dir

        # Create app - it will now use the test users file
        app = create_app()

        return TestClient(app)

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.post(
            "/auth/login",
            json={"username": "admin_user", "password": "AdminPass123!"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture
    def normal_user_token(self, client):
        """Get normal user authentication token."""
        response = client.post(
            "/auth/login",
            json={"username": "test_user", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    def test_admin_list_user_credentials_empty(self, client, admin_token):
        """Test admin listing credentials for user with no credentials."""
        response = client.get(
            "/api/admin/users/test_user/mcp-credentials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data
        assert "username" in data
        assert data["username"] == "test_user"
        assert data["credentials"] == []

    def test_admin_create_credential_for_user(self, client, admin_token):
        """Test admin creating MCP credential for a user."""
        response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test Credential"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "credential_id" in data
        assert "client_id" in data
        assert "client_secret" in data
        assert data["name"] == "Test Credential"
        assert data["client_id"].startswith("mcp_")
        assert data["client_secret"].startswith("mcp_sec_")

    def test_admin_create_credential_without_name(self, client, admin_token):
        """Test admin creating MCP credential without name."""
        response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "credential_id" in data
        assert "client_id" in data
        assert "client_secret" in data

    def test_admin_list_user_credentials_with_credentials(self, client, admin_token):
        """Test admin listing credentials for user with existing credentials."""
        # First create a credential
        create_response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test Cred 1"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == 201
        credential_id = create_response.json()["credential_id"]

        # Then list credentials
        list_response = client.get(
            "/api/admin/users/test_user/mcp-credentials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert list_response.status_code == 200
        data = list_response.json()
        assert data["username"] == "test_user"
        assert len(data["credentials"]) == 1
        assert data["credentials"][0]["credential_id"] == credential_id
        assert data["credentials"][0]["name"] == "Test Cred 1"

    def test_admin_revoke_user_credential(self, client, admin_token):
        """Test admin revoking a user's credential."""
        # First create a credential
        create_response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "To Be Revoked"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == 201
        credential_id = create_response.json()["credential_id"]

        # Then revoke it
        revoke_response = client.delete(
            f"/api/admin/users/test_user/mcp-credentials/{credential_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert revoke_response.status_code == 200
        assert "message" in revoke_response.json()
        assert "revoked" in revoke_response.json()["message"].lower()

        # Verify it's gone
        list_response = client.get(
            "/api/admin/users/test_user/mcp-credentials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["credentials"]) == 0

    def test_admin_revoke_nonexistent_credential(self, client, admin_token):
        """Test admin revoking non-existent credential returns 404."""
        response = client.delete(
            "/api/admin/users/test_user/mcp-credentials/nonexistent-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_admin_operations_on_nonexistent_user(self, client, admin_token):
        """Test admin operations on non-existent user return 404."""
        # List credentials
        list_response = client.get(
            "/api/admin/users/nonexistent_user/mcp-credentials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 404

        # Create credential
        create_response = client.post(
            "/api/admin/users/nonexistent_user/mcp-credentials",
            json={"name": "Test"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == 404

        # Revoke credential
        revoke_response = client.delete(
            "/api/admin/users/nonexistent_user/mcp-credentials/some-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert revoke_response.status_code == 404

    def test_admin_list_all_credentials(self, client, admin_token):
        """Test admin listing all credentials across all users."""
        # Create credentials for multiple users
        client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test User Cred 1"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test User Cred 2"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        client.post(
            "/api/admin/users/another_user/mcp-credentials",
            json={"name": "Another User Cred"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # List all
        response = client.get(
            "/api/admin/mcp-credentials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data
        assert "total" in data
        assert data["total"] == 3

        # Verify usernames are included
        usernames = [cred["username"] for cred in data["credentials"]]
        assert "test_user" in usernames
        assert "another_user" in usernames

    def test_admin_list_all_credentials_with_limit(self, client, admin_token):
        """Test admin listing all credentials with limit."""
        # Create multiple credentials
        for i in range(5):
            client.post(
                "/api/admin/users/test_user/mcp-credentials",
                json={"name": f"Cred {i}"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )

        # List with limit
        response = client.get(
            "/api/admin/mcp-credentials?limit=3",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["credentials"]) == 3
        assert data["total"] == 3

    def test_normal_user_cannot_access_admin_endpoints(self, client, normal_user_token):
        """Test that normal users cannot access admin endpoints."""
        # Try list user credentials
        list_response = client.get(
            "/api/admin/users/test_user/mcp-credentials",
            headers={"Authorization": f"Bearer {normal_user_token}"}
        )
        assert list_response.status_code == 403

        # Try create credential
        create_response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test"},
            headers={"Authorization": f"Bearer {normal_user_token}"}
        )
        assert create_response.status_code == 403

        # Try revoke credential
        revoke_response = client.delete(
            "/api/admin/users/test_user/mcp-credentials/some-id",
            headers={"Authorization": f"Bearer {normal_user_token}"}
        )
        assert revoke_response.status_code == 403

        # Try list all credentials
        list_all_response = client.get(
            "/api/admin/mcp-credentials",
            headers={"Authorization": f"Bearer {normal_user_token}"}
        )
        assert list_all_response.status_code == 403

    def test_unauthenticated_cannot_access_admin_endpoints(self, client):
        """Test that unauthenticated requests cannot access admin endpoints."""
        # No authorization header
        response = client.get("/api/admin/users/test_user/mcp-credentials")
        assert response.status_code == 401

        response = client.post(
            "/api/admin/users/test_user/mcp-credentials",
            json={"name": "Test"}
        )
        assert response.status_code == 401

        response = client.delete("/api/admin/users/test_user/mcp-credentials/some-id")
        assert response.status_code == 401

        response = client.get("/api/admin/mcp-credentials")
        assert response.status_code == 401
