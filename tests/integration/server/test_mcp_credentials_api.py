"""
Integration tests for MCP Credentials API endpoints.

Tests the complete API flow for MCP credential generation, listing, and revocation.
Addresses Story #614 code review rejection - E2E tests for API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import UserManager, UserRole
from src.code_indexer.server.auth import dependencies


# Mock user for authentication bypass
class MockUser:
    def __init__(self, username="testuser", role="normal_user"):
        self.username = username
        self.role = role


def override_get_current_user():
    """Override authentication dependency for testing."""
    return MockUser()


@pytest.fixture
def temp_users_file(tmp_path):
    """Create temporary users file for testing."""
    users_file = tmp_path / "users.json"
    return str(users_file)


@pytest.fixture
def user_manager(temp_users_file):
    """Create UserManager instance with temporary file."""
    manager = UserManager(users_file_path=temp_users_file)
    manager.seed_initial_admin()
    # Create test user
    manager.create_user("testuser", "Test123!@#Password", UserRole.NORMAL_USER)
    return manager


@pytest.fixture
def client(user_manager):
    """Create test client with mocked authentication."""
    import src.code_indexer.server.app as app_module

    # Store original manager
    original_user_manager = app_module.user_manager
    original_deps_user_manager = dependencies.user_manager

    # Override with test manager
    app_module.user_manager = user_manager
    dependencies.user_manager = user_manager

    # Create app
    app = create_app()

    # Override authentication
    app.dependency_overrides[dependencies.get_current_user] = override_get_current_user

    # Create client
    test_client = TestClient(app)

    yield test_client

    # Restore original managers
    app_module.user_manager = original_user_manager
    dependencies.user_manager = original_deps_user_manager


class TestMCPCredentialsAPI:
    """Test MCP Credentials API endpoints."""

    def test_create_mcp_credential_success(self, client):
        """
        AC1: User generates new MCP client credentials via API.

        Verifies:
        - POST /api/mcp-credentials returns 201
        - Response contains client_id, client_secret, credential_id, created_at
        - client_id format: mcp_{32 hex chars}
        - client_secret format: mcp_sec_{64 hex chars}
        """
        response = client.post("/api/mcp-credentials", json={"name": "Test Credential"})

        assert response.status_code == 201
        data = response.json()

        # Verify all required fields present
        assert "client_id" in data
        assert "client_secret" in data
        assert "credential_id" in data
        assert "name" in data
        assert "created_at" in data

        # Verify client_id format
        assert data["client_id"].startswith("mcp_")
        assert len(data["client_id"]) == 4 + 32  # "mcp_" + 32 hex chars

        # Verify client_secret format
        assert data["client_secret"].startswith("mcp_sec_")
        assert len(data["client_secret"]) == 8 + 64  # "mcp_sec_" + 64 hex chars

        # Verify name
        assert data["name"] == "Test Credential"

    def test_create_mcp_credential_without_name(self, client):
        """AC1: User generates credential without optional name."""
        response = client.post("/api/mcp-credentials", json={})

        assert response.status_code == 201
        data = response.json()

        # Verify credential created successfully
        assert "client_id" in data
        assert "client_secret" in data
        # Name should be None when not provided
        assert data["name"] is None

    def test_create_mcp_credential_requires_auth(self, client):
        """AC1: Credential generation requires authentication."""
        # Clear authentication override to test auth requirement
        from src.code_indexer.server.app import create_app

        app = create_app()
        unauth_client = TestClient(app)

        response = unauth_client.post("/api/mcp-credentials", json={"name": "Test"})

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_list_mcp_credentials_empty(self, client):
        """AC1: List credentials returns empty array when user has no credentials."""
        response = client.get("/api/mcp-credentials")

        assert response.status_code == 200
        data = response.json()

        assert "credentials" in data
        assert data["credentials"] == []

    def test_list_mcp_credentials_shows_generated_credential(self, client):
        """
        AC2: List credentials shows metadata, not secrets.

        Verifies:
        - GET /api/mcp-credentials returns credentials list
        - Each credential has metadata (credential_id, client_id, client_id_prefix, name, created_at, last_used_at)
        - client_secret NOT included
        - client_secret_hash NOT included
        """
        # Generate credential
        create_response = client.post(
            "/api/mcp-credentials", json={"name": "Test Credential"}
        )
        assert create_response.status_code == 201
        created_credential = create_response.json()

        # List credentials
        list_response = client.get("/api/mcp-credentials")
        assert list_response.status_code == 200

        data = list_response.json()
        assert "credentials" in data
        assert len(data["credentials"]) == 1

        credential = data["credentials"][0]

        # Verify metadata is present
        assert credential["credential_id"] == created_credential["credential_id"]
        assert credential["client_id"] == created_credential["client_id"]
        assert "client_id_prefix" in credential
        assert credential["name"] == "Test Credential"
        assert "created_at" in credential
        assert "last_used_at" in credential

        # Verify secrets are NOT included
        assert "client_secret" not in credential
        assert "client_secret_hash" not in credential

    def test_list_mcp_credentials_requires_auth(self, client):
        """AC2: Listing credentials requires authentication."""
        from src.code_indexer.server.app import create_app

        app = create_app()
        unauth_client = TestClient(app)

        response = unauth_client.get("/api/mcp-credentials")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_delete_mcp_credential_success(self, client):
        """
        AC3: User revokes credential via API.

        Verifies:
        - DELETE /api/mcp-credentials/{credential_id} returns 200
        - Credential removed from storage
        - Subsequent list shows credential is gone
        """
        # Generate credential
        create_response = client.post(
            "/api/mcp-credentials", json={"name": "To Be Deleted"}
        )
        assert create_response.status_code == 201
        credential_id = create_response.json()["credential_id"]

        # Delete credential
        delete_response = client.delete(f"/api/mcp-credentials/{credential_id}")
        assert delete_response.status_code == 200
        assert "message" in delete_response.json()

        # Verify credential is gone
        list_response = client.get("/api/mcp-credentials")
        assert list_response.status_code == 200
        assert len(list_response.json()["credentials"]) == 0

    def test_delete_mcp_credential_not_found(self, client):
        """AC3: Deleting non-existent credential returns 404."""
        fake_credential_id = "00000000-0000-0000-0000-000000000000"

        response = client.delete(f"/api/mcp-credentials/{fake_credential_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_mcp_credential_requires_auth(self, client):
        """AC3: Deleting credentials requires authentication."""
        from src.code_indexer.server.app import create_app

        app = create_app()
        unauth_client = TestClient(app)

        fake_credential_id = "00000000-0000-0000-0000-000000000000"
        response = unauth_client.delete(f"/api/mcp-credentials/{fake_credential_id}")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_delete_one_of_multiple_credentials(self, client):
        """
        AC3: Revoking one credential does not affect others.

        Verifies:
        - Multiple credentials can exist for same user
        - Deleting one leaves others intact
        """
        # Generate two credentials
        response1 = client.post("/api/mcp-credentials", json={"name": "Credential 1"})
        response2 = client.post("/api/mcp-credentials", json={"name": "Credential 2"})

        credential_id_1 = response1.json()["credential_id"]
        credential_id_2 = response2.json()["credential_id"]

        # Delete first credential
        delete_response = client.delete(f"/api/mcp-credentials/{credential_id_1}")
        assert delete_response.status_code == 200

        # Verify second credential still exists
        list_response = client.get("/api/mcp-credentials")
        credentials = list_response.json()["credentials"]

        assert len(credentials) == 1
        assert credentials[0]["credential_id"] == credential_id_2
        assert credentials[0]["name"] == "Credential 2"

    def test_end_to_end_credential_lifecycle(self, client):
        """
        AC4: Complete user journey - generate, list, delete.

        Verifies:
        - User generates credential
        - User sees it in list
        - User deletes it
        - List becomes empty
        """
        # Step 1: List is initially empty
        list_response = client.get("/api/mcp-credentials")
        assert len(list_response.json()["credentials"]) == 0

        # Step 2: Generate credential
        create_response = client.post(
            "/api/mcp-credentials", json={"name": "Test Journey"}
        )
        assert create_response.status_code == 201
        created = create_response.json()

        # Verify client_secret is returned only during generation
        assert "client_secret" in created
        assert created["client_secret"].startswith("mcp_sec_")

        # Step 3: List shows the credential (without secret)
        list_response = client.get("/api/mcp-credentials")
        credentials = list_response.json()["credentials"]
        assert len(credentials) == 1
        assert credentials[0]["credential_id"] == created["credential_id"]
        assert "client_secret" not in credentials[0]  # Secret not in list

        # Step 4: Delete credential
        delete_response = client.delete(
            f"/api/mcp-credentials/{created['credential_id']}"
        )
        assert delete_response.status_code == 200

        # Step 5: List is empty again
        list_response = client.get("/api/mcp-credentials")
        assert len(list_response.json()["credentials"]) == 0

    def test_revoked_credential_fails_authentication_immediately(self, client):
        """
        AC4: Revoked credentials immediately fail authentication.

        Verifies:
        - Credential works before revocation (can authenticate)
        - After revocation, authentication fails immediately
        - No caching delays the revocation effect
        - Returns proper None for revoked credentials
        """
        import src.code_indexer.server.app as app_module
        from src.code_indexer.server.auth.mcp_credential_manager import (
            MCPCredentialManager,
        )

        # Generate credential
        create_response = client.post(
            "/api/mcp-credentials", json={"name": "Test Auth"}
        )
        assert create_response.status_code == 201
        credential = create_response.json()
        client_id = credential["client_id"]
        client_secret = credential["client_secret"]
        credential_id = credential["credential_id"]

        # Use the same user_manager that the app uses (injected by fixture)
        mcp_manager = MCPCredentialManager(user_manager=app_module.user_manager)

        # Step 1: Verify credential works BEFORE revocation
        user_id = mcp_manager.verify_credential(client_id, client_secret)
        assert user_id == "testuser", "Credential should work before revocation"

        # Step 2: Revoke the credential
        delete_response = client.delete(f"/api/mcp-credentials/{credential_id}")
        assert delete_response.status_code == 200

        # Step 3: Verify credential IMMEDIATELY fails authentication (no caching)
        user_id = mcp_manager.verify_credential(client_id, client_secret)
        assert (
            user_id is None
        ), "Revoked credential should immediately fail authentication"

        # Step 4: Additional verification - specific revoked credential should not be in list
        list_response = client.get("/api/mcp-credentials")
        credentials = list_response.json()["credentials"]
        credential_ids = [c["credential_id"] for c in credentials]
        assert (
            credential_id not in credential_ids
        ), "Revoked credential should not appear in list"
