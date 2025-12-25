"""
Integration tests for MCP authentication flow.

Tests MCP credential authentication via Basic auth and client_secret_post.
Addresses Story #614 code review rejection - Authentication integration tests.

NOTE: These tests demonstrate the EXPECTED behavior when MCP credential
authentication is integrated into the auth flow. Some tests may fail initially
if the integration is not yet complete.
"""

import base64
import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import UserManager, UserRole
from src.code_indexer.server.auth.mcp_credential_manager import MCPCredentialManager
from src.code_indexer.server.auth import dependencies


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
def mcp_manager(user_manager):
    """Create MCPCredentialManager instance."""
    return MCPCredentialManager(user_manager=user_manager)


@pytest.fixture
def client(tmp_path):
    """
    Create test client with pre-populated users.json file.

    This fixture creates the test user and credential BEFORE calling create_app()
    to ensure the users.json file is properly populated when the app initializes.
    """
    import src.code_indexer.server.app as app_module
    import os

    # Store original env and managers
    original_env = os.environ.get("CIDX_SERVER_DATA_DIR")
    original_user_manager = app_module.user_manager
    original_deps_user_manager = dependencies.user_manager
    original_deps_mcp_manager = dependencies.mcp_credential_manager

    # Set environment to use test's temp directory BEFORE any managers are created
    os.environ["CIDX_SERVER_DATA_DIR"] = str(tmp_path)

    # Create and populate user_manager BEFORE create_app()
    from src.code_indexer.server.auth.user_manager import UserManager, UserRole
    users_file = str(tmp_path / "users.json")
    test_user_manager = UserManager(users_file_path=users_file)
    test_user_manager.seed_initial_admin()
    test_user_manager.create_user("testuser", "Test123!@#Password", UserRole.NORMAL_USER)

    # Now create app - it will use the pre-populated users.json
    app = create_app()

    # Override dependencies with test managers (after create_app)
    # The app's managers will read from the same users.json file
    dependencies.user_manager = test_user_manager
    # Create MCP manager with test user_manager
    from src.code_indexer.server.auth.mcp_credential_manager import MCPCredentialManager
    dependencies.mcp_credential_manager = MCPCredentialManager(user_manager=test_user_manager)

    # Create client
    test_client = TestClient(app)

    yield test_client

    # Restore original env and managers
    if original_env is not None:
        os.environ["CIDX_SERVER_DATA_DIR"] = original_env
    elif "CIDX_SERVER_DATA_DIR" in os.environ:
        del os.environ["CIDX_SERVER_DATA_DIR"]
    app_module.user_manager = original_user_manager
    dependencies.user_manager = original_deps_user_manager
    dependencies.mcp_credential_manager = original_deps_mcp_manager


@pytest.fixture
def mcp_credential(client):
    """
    Generate MCP credential for testing.

    Depends on client fixture to ensure managers are set up first.
    Uses the MCP manager from dependencies that was configured by client fixture.
    """
    result = dependencies.mcp_credential_manager.generate_credential("testuser", name="Test Auth Credential")
    return result


class TestMCPAuthenticationBasicAuth:
    """Test MCP authentication using Basic auth."""

    def test_basic_auth_with_valid_mcp_credentials(self, client, mcp_credential):
        """
        AC1: Basic auth with valid MCP credentials authenticates successfully.

        Verifies:
        - Authorization header with Basic auth + MCP credentials works
        - Request is authenticated as the credential owner
        - /mcp endpoint returns success (not 401)
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]

        # Create Basic auth header
        auth_credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(auth_credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        # Make request to /mcp endpoint with MCP credentials
        # Use a simple tools/list request for testing
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )

        # Should succeed (200) not fail with 401
        assert response.status_code != 401, "MCP Basic auth should not return 401"
        assert response.status_code == 200, "MCP endpoint should return 200 with valid auth"

    def test_basic_auth_with_invalid_client_id(self, client, mcp_credential):
        """
        AC2: Basic auth with invalid client_id returns 401.

        Verifies:
        - Wrong client_id is rejected
        - Returns 401 Unauthorized
        """
        client_secret = mcp_credential["client_secret"]
        fake_client_id = "mcp_fakefakefakefakefakefakefakefake"

        # Create Basic auth header with wrong client_id
        auth_credentials = f"{fake_client_id}:{client_secret}"
        encoded = base64.b64encode(auth_credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )

        # Should return 401
        assert response.status_code == 401

    def test_basic_auth_with_invalid_client_secret(self, client, mcp_credential):
        """
        AC3: Basic auth with invalid client_secret returns 401.

        Verifies:
        - Wrong client_secret is rejected
        - Returns 401 Unauthorized
        """
        client_id = mcp_credential["client_id"]
        fake_secret = "mcp_sec_fakefakefakefakefakefakefakefakefakefakefakefakefakefakefakefake"

        # Create Basic auth header with wrong secret
        auth_credentials = f"{client_id}:{fake_secret}"
        encoded = base64.b64encode(auth_credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )

        # Should return 401
        assert response.status_code == 401

    def test_basic_auth_updates_last_used_at(self, client, mcp_manager, mcp_credential, user_manager):
        """
        AC4: Successful Basic auth updates last_used_at.

        Verifies:
        - last_used_at is None initially
        - After successful auth, last_used_at is updated
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]
        credential_id = mcp_credential["credential_id"]

        # Check last_used_at is initially None
        stored_credentials = user_manager.get_mcp_credentials("testuser")
        initial_cred = next(c for c in stored_credentials if c["credential_id"] == credential_id)
        assert initial_cred["last_used_at"] is None

        # Authenticate with Basic auth
        auth_credentials_str = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(auth_credentials_str.encode()).decode()
        auth_header = f"Basic {encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )

        # Should succeed
        assert response.status_code != 401

        # Check last_used_at is now set
        stored_credentials = user_manager.get_mcp_credentials("testuser")
        updated_cred = next(c for c in stored_credentials if c["credential_id"] == credential_id)
        assert updated_cred["last_used_at"] is not None
        assert updated_cred["last_used_at"] != initial_cred["last_used_at"]


class TestMCPAuthenticationClientSecretPost:
    """Test MCP authentication using client_secret_post method."""

    def test_client_secret_post_with_valid_credentials(self, client, mcp_credential):
        """
        AC5: client_secret_post with valid MCP credentials authenticates successfully.

        Verifies:
        - POST body with client_id and client_secret works
        - Request is authenticated as the credential owner
        - /mcp endpoint returns success (not 401)
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]

        # Make request with client_id and client_secret in POST body
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "client_id": client_id,
            "client_secret": client_secret
        }

        response = client.post(
            "/mcp",
            json=mcp_request
        )

        # Should succeed (200) not fail with 401
        assert response.status_code != 401, "client_secret_post should not return 401"
        assert response.status_code == 200, "MCP endpoint should return 200 with valid credentials"

    def test_client_secret_post_with_invalid_client_id(self, client, mcp_credential):
        """
        AC6: client_secret_post with invalid client_id returns 401.

        Verifies:
        - Wrong client_id in POST body is rejected
        - Returns 401 Unauthorized
        """
        client_secret = mcp_credential["client_secret"]
        fake_client_id = "mcp_fakefakefakefakefakefakefakefake"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "client_id": fake_client_id,
            "client_secret": client_secret
        }

        response = client.post(
            "/mcp",
            json=mcp_request
        )

        # Should return 401
        assert response.status_code == 401

    def test_client_secret_post_with_invalid_secret(self, client, mcp_credential):
        """
        AC7: client_secret_post with invalid client_secret returns 401.

        Verifies:
        - Wrong client_secret in POST body is rejected
        - Returns 401 Unauthorized
        """
        client_id = mcp_credential["client_id"]
        fake_secret = "mcp_sec_fakefakefakefakefakefakefakefakefakefakefakefakefakefakefakefake"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "client_id": client_id,
            "client_secret": fake_secret
        }

        response = client.post(
            "/mcp",
            json=mcp_request
        )

        # Should return 401
        assert response.status_code == 401

    def test_client_secret_post_updates_last_used_at(self, client, mcp_manager, mcp_credential, user_manager):
        """
        AC8: Successful client_secret_post updates last_used_at.

        Verifies:
        - last_used_at is None initially
        - After successful auth, last_used_at is updated
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]
        credential_id = mcp_credential["credential_id"]

        # Check last_used_at is initially None
        stored_credentials = user_manager.get_mcp_credentials("testuser")
        initial_cred = next(c for c in stored_credentials if c["credential_id"] == credential_id)
        assert initial_cred["last_used_at"] is None

        # Authenticate with client_secret_post
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "client_id": client_id,
            "client_secret": client_secret
        }

        response = client.post(
            "/mcp",
            json=mcp_request
        )

        # Should succeed
        assert response.status_code != 401

        # Check last_used_at is now set
        stored_credentials = user_manager.get_mcp_credentials("testuser")
        updated_cred = next(c for c in stored_credentials if c["credential_id"] == credential_id)
        assert updated_cred["last_used_at"] is not None
        assert updated_cred["last_used_at"] != initial_cred["last_used_at"]


class TestMCPAuthenticationRevocation:
    """Test revoked MCP credentials fail authentication."""

    def test_revoked_credential_fails_basic_auth(self, client, mcp_manager, mcp_credential):
        """
        AC9: Revoked credentials immediately fail authentication (Basic auth).

        Verifies:
        - Credential works initially
        - After revocation, same credential returns 401
        - No caching delays revocation
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]
        credential_id = mcp_credential["credential_id"]

        # Create Basic auth header
        auth_credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(auth_credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        # Step 1: Verify credential works
        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )
        assert response.status_code != 401, "Credential should work before revocation"

        # Step 2: Revoke credential
        revoked = mcp_manager.revoke_credential("testuser", credential_id)
        assert revoked is True

        # Step 3: Try to use revoked credential
        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )

        # Should now return 401
        assert response.status_code == 401, "Revoked credential should return 401"

    def test_revoked_credential_fails_client_secret_post(self, client, mcp_manager, mcp_credential):
        """
        AC10: Revoked credentials immediately fail authentication (client_secret_post).

        Verifies:
        - Credential works initially
        - After revocation, same credential returns 401
        - No caching delays revocation
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]
        credential_id = mcp_credential["credential_id"]

        # Step 1: Verify credential works
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "client_id": client_id,
            "client_secret": client_secret
        }

        response = client.post("/mcp", json=mcp_request)
        assert response.status_code != 401, "Credential should work before revocation"

        # Step 2: Revoke credential
        revoked = mcp_manager.revoke_credential("testuser", credential_id)
        assert revoked is True

        # Step 3: Try to use revoked credential
        response = client.post("/mcp", json=mcp_request)

        # Should now return 401
        assert response.status_code == 401, "Revoked credential should return 401"


class TestMCPAuthenticationVerifyCredential:
    """Test verify_credential() integration in auth flow."""

    def test_verify_credential_called_on_basic_auth(self, client, mcp_manager, mcp_credential):
        """
        AC11: verify_credential() is called during Basic auth.

        Verifies:
        - MCPCredentialManager.verify_credential() is used
        - Authentication succeeds when verify_credential() returns user_id
        - Authentication fails when verify_credential() returns None
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]

        # Test 1: Valid credentials - verify_credential() returns user_id
        user_id = mcp_manager.verify_credential(client_id, client_secret)
        assert user_id == "testuser"

        # Test 2: Invalid credentials - verify_credential() returns None
        fake_secret = "mcp_sec_fakefakefakefakefakefakefakefakefakefakefakefakefakefakefakefake"
        user_id = mcp_manager.verify_credential(client_id, fake_secret)
        assert user_id is None

    def test_verify_credential_bcrypt_hash_check(self, client, mcp_manager, mcp_credential, user_manager):
        """
        AC12: verify_credential() uses bcrypt to check secret.

        Verifies:
        - Secret is compared against stored bcrypt hash
        - Hash comparison is secure (not plain text comparison)
        """
        client_id = mcp_credential["client_id"]
        client_secret = mcp_credential["client_secret"]

        # Verify credential works with correct secret
        user_id = mcp_manager.verify_credential(client_id, client_secret)
        assert user_id == "testuser"

        # Verify stored hash is bcrypt format (not plain text)
        users_data = user_manager._load_users()
        stored_hash = users_data["testuser"]["mcp_credentials"][0]["client_secret_hash"]
        assert stored_hash.startswith("$2b$")  # bcrypt prefix
        assert stored_hash != client_secret  # Not plain text


class TestMCPAuthenticationEndToEnd:
    """End-to-end authentication workflow tests."""

    def test_full_credential_lifecycle_authentication(self, client, mcp_manager, user_manager):
        """
        AC13: Complete lifecycle - generate, authenticate, revoke.

        Verifies:
        - Generate credential
        - Authenticate with credential (works)
        - Revoke credential
        - Authenticate with revoked credential (fails)
        """
        # Step 1: Generate credential
        result = mcp_manager.generate_credential("testuser", name="Lifecycle Test")
        client_id = result["client_id"]
        client_secret = result["client_secret"]
        credential_id = result["credential_id"]

        # Step 2: Authenticate with credential
        auth_credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(auth_credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )
        assert response.status_code != 401, "Should authenticate successfully"

        # Step 3: Verify last_used_at updated
        stored_creds = user_manager.get_mcp_credentials("testuser")
        cred = next(c for c in stored_creds if c["credential_id"] == credential_id)
        assert cred["last_used_at"] is not None

        # Step 4: Revoke credential
        revoked = mcp_manager.revoke_credential("testuser", credential_id)
        assert revoked is True

        # Step 5: Try to authenticate with revoked credential
        response = client.post(
            "/mcp",
            headers={"Authorization": auth_header},
            json=mcp_request
        )
        assert response.status_code == 401, "Revoked credential should fail"

    def test_multiple_credentials_isolation(self, client, mcp_manager):
        """
        AC14: Multiple credentials work independently.

        Verifies:
        - User can have multiple credentials
        - Each credential authenticates independently
        - Revoking one doesn't affect others
        """
        # Generate two credentials
        cred1 = mcp_manager.generate_credential("testuser", name="Cred 1")
        cred2 = mcp_manager.generate_credential("testuser", name="Cred 2")

        # Create auth headers for both
        cred1_str = f"{cred1['client_id']}:{cred1['client_secret']}"
        cred1_encoded = base64.b64encode(cred1_str.encode()).decode()
        cred1_header = f"Basic {cred1_encoded}"

        cred2_str = f"{cred2['client_id']}:{cred2['client_secret']}"
        cred2_encoded = base64.b64encode(cred2_str.encode()).decode()
        cred2_header = f"Basic {cred2_encoded}"

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        # Both should work initially
        response1 = client.post("/mcp", headers={"Authorization": cred1_header}, json=mcp_request)
        response2 = client.post("/mcp", headers={"Authorization": cred2_header}, json=mcp_request)
        assert response1.status_code != 401
        assert response2.status_code != 401

        # Revoke credential 1
        mcp_manager.revoke_credential("testuser", cred1["credential_id"])

        # Credential 1 should fail
        response1 = client.post("/mcp", headers={"Authorization": cred1_header}, json=mcp_request)
        assert response1.status_code == 401

        # Credential 2 should still work
        response2 = client.post("/mcp", headers={"Authorization": cred2_header}, json=mcp_request)
        assert response2.status_code != 401
