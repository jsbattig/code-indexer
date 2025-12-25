"""
Unit tests for MCPCredentialManager.

Tests credential generation, storage, verification, and revocation.
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from code_indexer.server.auth.mcp_credential_manager import MCPCredentialManager
from code_indexer.server.auth.user_manager import UserManager, UserRole


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
    return MCPCredentialManager(user_manager)


class TestGenerateCredential:
    """Test MCPCredentialManager.generate_credential()"""

    def test_generate_credential_creates_valid_client_id(self, mcp_manager):
        """AC1: System generates unique client_id in format mcp_{secrets.token_hex(16)}"""
        result = mcp_manager.generate_credential("testuser")

        assert "client_id" in result
        assert result["client_id"].startswith("mcp_")
        assert len(result["client_id"]) == 4 + 32  # "mcp_" + 32 hex chars
        # Verify it's hex characters
        hex_part = result["client_id"][4:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_generate_credential_creates_valid_client_secret(self, mcp_manager):
        """AC1: System generates unique client_secret in format mcp_sec_{secrets.token_hex(32)}"""
        result = mcp_manager.generate_credential("testuser")

        assert "client_secret" in result
        assert result["client_secret"].startswith("mcp_sec_")
        assert len(result["client_secret"]) == 8 + 64  # "mcp_sec_" + 64 hex chars
        # Verify it's hex characters
        hex_part = result["client_secret"][8:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_generate_credential_stores_hashed_secret(self, mcp_manager, user_manager):
        """AC1: Credential stored in user's JSON file with secret as bcrypt hash"""
        result = mcp_manager.generate_credential("testuser")

        # Verify secret is returned in result
        assert "client_secret" in result

        # Verify stored credential has hashed secret, not plain text
        # Access internal storage directly to verify hash is stored
        users_data = user_manager._load_users()
        stored_creds = users_data["testuser"]["mcp_credentials"]
        assert len(stored_creds) == 1
        stored_cred = stored_creds[0]

        assert "client_secret_hash" in stored_cred
        assert stored_cred["client_secret_hash"].startswith("$2b$")  # bcrypt hash prefix
        assert "client_secret" not in stored_cred  # Plain secret not stored

    def test_generate_credential_with_optional_name(self, mcp_manager, user_manager):
        """AC2: Contains optional name field"""
        result = mcp_manager.generate_credential("testuser", name="Claude Desktop Work")

        assert "name" in result
        assert result["name"] == "Claude Desktop Work"

        # Verify name is stored
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 1
        assert credentials[0]["name"] == "Claude Desktop Work"

    def test_generate_credential_without_name(self, mcp_manager, user_manager):
        """AC2: Name field optional"""
        result = mcp_manager.generate_credential("testuser")

        # Verify credential is created without error
        assert "client_id" in result

        # Verify name is None when not provided
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 1
        assert credentials[0]["name"] is None

    def test_generate_credential_stores_metadata(self, mcp_manager, user_manager):
        """AC2: Stored credential contains required metadata"""
        result = mcp_manager.generate_credential("testuser", name="Test")

        # Verify result contains all required fields
        assert "credential_id" in result
        assert "client_id" in result
        assert "client_secret" in result  # Only in generation response
        assert "client_id_prefix" in result
        assert "name" in result
        assert "created_at" in result

        # Verify stored credential has all required fields
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 1
        stored_cred = credentials[0]

        # Verify UUID v4
        credential_id = stored_cred["credential_id"]
        uuid_obj = uuid.UUID(credential_id)
        assert uuid_obj.version == 4

        # Verify client_id_prefix (first 8 characters)
        assert stored_cred["client_id_prefix"] == result["client_id"][:8]

        # Verify created_at is ISO format
        created_at = datetime.fromisoformat(stored_cred["created_at"])
        assert created_at.tzinfo is not None  # Must have timezone

        # Verify last_used_at is initially None
        assert stored_cred["last_used_at"] is None

    def test_generate_credential_returns_plain_secret_once(self, mcp_manager, user_manager):
        """AC3: Full client_secret shown only during generation"""
        result = mcp_manager.generate_credential("testuser")

        # Secret is in generation response
        assert "client_secret" in result
        plain_secret = result["client_secret"]
        assert plain_secret.startswith("mcp_sec_")

        # But not in get_mcp_credentials() output (security)
        credentials = user_manager.get_mcp_credentials("testuser")
        stored_cred = credentials[0]
        assert "client_secret" not in stored_cred
        assert "client_secret_hash" not in stored_cred  # Hash excluded from public API

        # Verify hash IS stored internally
        users_data = user_manager._load_users()
        internal_cred = users_data["testuser"]["mcp_credentials"][0]
        assert "client_secret_hash" in internal_cred

    def test_generate_multiple_credentials_for_same_user(self, mcp_manager, user_manager):
        """User can have multiple credentials"""
        result1 = mcp_manager.generate_credential("testuser", name="Laptop")
        result2 = mcp_manager.generate_credential("testuser", name="Desktop")

        # Each should have unique client_id
        assert result1["client_id"] != result2["client_id"]
        assert result1["client_secret"] != result2["client_secret"]

        # Both should be stored
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 2

    def test_generate_credential_user_not_found(self, mcp_manager):
        """Error when user doesn't exist"""
        with pytest.raises(ValueError, match="User not found"):
            mcp_manager.generate_credential("nonexistent_user")


class TestGetCredentials:
    """Test MCPCredentialManager.get_credentials()"""

    def test_get_credentials_excludes_secret(self, mcp_manager, user_manager):
        """AC3: Subsequent views show only client_id_prefix and metadata, not secret"""
        # Generate credential
        mcp_manager.generate_credential("testuser", name="Test")

        # Retrieve credentials
        credentials = mcp_manager.get_credentials("testuser")

        assert len(credentials) == 1
        cred = credentials[0]

        # Verify metadata is present
        assert "credential_id" in cred
        assert "client_id" in cred
        assert "client_id_prefix" in cred
        assert "name" in cred
        assert "created_at" in cred
        assert "last_used_at" in cred

        # Verify secret and hash are excluded
        assert "client_secret" not in cred
        assert "client_secret_hash" not in cred

    def test_get_credentials_empty_list_for_new_user(self, mcp_manager):
        """Returns empty list when user has no credentials"""
        credentials = mcp_manager.get_credentials("testuser")
        assert credentials == []

    def test_get_credentials_user_not_found(self, mcp_manager):
        """Returns empty list when user doesn't exist"""
        credentials = mcp_manager.get_credentials("nonexistent_user")
        assert credentials == []

    def test_get_credentials_sorted_by_created_at_desc(self, mcp_manager, user_manager):
        """AC1: Credentials sorted by created_at descending (newest first)"""
        import time

        # Generate three credentials with slight time gaps
        result1 = mcp_manager.generate_credential("testuser", name="First")
        time.sleep(0.01)  # Small delay to ensure different timestamps
        result2 = mcp_manager.generate_credential("testuser", name="Second")
        time.sleep(0.01)
        result3 = mcp_manager.generate_credential("testuser", name="Third")

        # Get credentials
        credentials = mcp_manager.get_credentials("testuser")

        # Should have all three
        assert len(credentials) == 3

        # Verify sorted by created_at descending (newest first)
        # Third credential should be first
        assert credentials[0]["name"] == "Third"
        assert credentials[0]["credential_id"] == result3["credential_id"]

        # Second credential should be second
        assert credentials[1]["name"] == "Second"
        assert credentials[1]["credential_id"] == result2["credential_id"]

        # First credential should be last
        assert credentials[2]["name"] == "First"
        assert credentials[2]["credential_id"] == result1["credential_id"]

        # Verify timestamps are in descending order
        created_1 = datetime.fromisoformat(credentials[0]["created_at"])
        created_2 = datetime.fromisoformat(credentials[1]["created_at"])
        created_3 = datetime.fromisoformat(credentials[2]["created_at"])

        assert created_1 >= created_2  # Newest first
        assert created_2 >= created_3


class TestVerifyCredential:
    """Test MCPCredentialManager.verify_credential()"""

    def test_verify_credential_with_valid_credentials(self, mcp_manager):
        """AC3: Verify valid credentials and return user_id"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_id = result["client_id"]
        client_secret = result["client_secret"]

        # Verify credentials
        user_id = mcp_manager.verify_credential(client_id, client_secret)

        assert user_id == "testuser"

    def test_verify_credential_with_invalid_secret(self, mcp_manager):
        """AC3: Returns None for invalid secret"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_id = result["client_id"]

        # Try with wrong secret
        user_id = mcp_manager.verify_credential(client_id, "mcp_sec_wrong_secret_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")

        assert user_id is None

    def test_verify_credential_with_invalid_client_id(self, mcp_manager):
        """AC3: Returns None for invalid client_id"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_secret = result["client_secret"]

        # Try with wrong client_id
        user_id = mcp_manager.verify_credential("mcp_wrong_client_id_12345678", client_secret)

        assert user_id is None

    def test_verify_credential_updates_last_used_at(self, mcp_manager, user_manager):
        """Verify credential updates last_used_at timestamp"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_id = result["client_id"]
        client_secret = result["client_secret"]

        # Initially last_used_at is None
        credentials = user_manager.get_mcp_credentials("testuser")
        assert credentials[0]["last_used_at"] is None

        # Verify credential
        user_id = mcp_manager.verify_credential(client_id, client_secret)
        assert user_id == "testuser"

        # last_used_at should now be set
        credentials = user_manager.get_mcp_credentials("testuser")
        assert credentials[0]["last_used_at"] is not None

        # Verify it's a valid ISO timestamp
        last_used = datetime.fromisoformat(credentials[0]["last_used_at"])
        assert last_used.tzinfo is not None

        # Should be recent (within last minute)
        now = datetime.now(timezone.utc)
        time_diff = (now - last_used).total_seconds()
        assert time_diff < 60

    def test_verify_credential_bcrypt_hash_cannot_be_reversed(self, mcp_manager, user_manager):
        """AC3: client_secret_hash cannot be reversed to obtain secret"""
        result = mcp_manager.generate_credential("testuser", name="Test")

        # Get stored hash from internal storage
        users_data = user_manager._load_users()
        stored_hash = users_data["testuser"]["mcp_credentials"][0]["client_secret_hash"]

        # Verify hash is bcrypt format
        assert stored_hash.startswith("$2b$")

        # Verify we can't reverse it (it's one-way)
        # This is inherent to bcrypt, but we verify the pattern
        assert len(stored_hash) == 60  # Standard bcrypt hash length
        assert stored_hash != result["client_secret"]  # Hash != plain text


class TestRevokeCredential:
    """Test MCPCredentialManager.revoke_credential()"""

    def test_revoke_credential_success(self, mcp_manager, user_manager):
        """Successfully revoke a credential"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        credential_id = result["credential_id"]

        # Verify credential exists
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 1

        # Revoke it
        revoked = mcp_manager.revoke_credential("testuser", credential_id)
        assert revoked is True

        # Verify it's gone
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 0

    def test_revoke_credential_not_found(self, mcp_manager):
        """Returns False when credential doesn't exist"""
        fake_id = str(uuid.uuid4())
        revoked = mcp_manager.revoke_credential("testuser", fake_id)
        assert revoked is False

    def test_revoke_credential_user_not_found(self, mcp_manager):
        """Returns False when user doesn't exist"""
        fake_id = str(uuid.uuid4())
        revoked = mcp_manager.revoke_credential("nonexistent_user", fake_id)
        assert revoked is False

    def test_revoke_one_of_multiple_credentials(self, mcp_manager, user_manager):
        """Revoke only the specified credential"""
        result1 = mcp_manager.generate_credential("testuser", name="Laptop")
        result2 = mcp_manager.generate_credential("testuser", name="Desktop")

        # Revoke first one
        revoked = mcp_manager.revoke_credential("testuser", result1["credential_id"])
        assert revoked is True

        # Second one should still exist
        credentials = user_manager.get_mcp_credentials("testuser")
        assert len(credentials) == 1
        assert credentials[0]["credential_id"] == result2["credential_id"]


class TestGetCredentialByClientId:
    """Test MCPCredentialManager.get_credential_by_client_id()"""

    def test_get_credential_by_client_id_success(self, mcp_manager):
        """Find credential by client_id"""
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_id = result["client_id"]

        # Find it
        found = mcp_manager.get_credential_by_client_id(client_id)

        assert found is not None
        user_id, credential = found
        assert user_id == "testuser"
        assert credential["client_id"] == client_id

    def test_get_credential_by_client_id_not_found(self, mcp_manager):
        """Returns None when client_id doesn't exist"""
        found = mcp_manager.get_credential_by_client_id("mcp_nonexistent_12345678")
        assert found is None

    def test_get_credential_by_client_id_across_multiple_users(self, mcp_manager, user_manager):
        """Find credential across all users"""
        # Create another user
        user_manager.create_user("otheruser", "Test123!@#Password", UserRole.NORMAL_USER)

        # Create credentials for both users
        result1 = mcp_manager.generate_credential("testuser", name="Test1")
        result2 = mcp_manager.generate_credential("otheruser", name="Test2")

        # Find each by client_id
        found1 = mcp_manager.get_credential_by_client_id(result1["client_id"])
        found2 = mcp_manager.get_credential_by_client_id(result2["client_id"])

        assert found1 is not None
        assert found1[0] == "testuser"

        assert found2 is not None
        assert found2[0] == "otheruser"


class TestErrorPathCoverage:
    """Test error paths for complete code coverage."""

    def test_generate_credential_no_user_manager(self):
        """Line 47: Error when UserManager not initialized"""
        mcp_manager = MCPCredentialManager(user_manager=None)

        with pytest.raises(ValueError, match="UserManager not initialized"):
            mcp_manager.generate_credential("testuser")

    def test_get_credentials_no_user_manager(self):
        """Line 105: Returns empty list when UserManager not initialized"""
        mcp_manager = MCPCredentialManager(user_manager=None)

        credentials = mcp_manager.get_credentials("testuser")
        assert credentials == []

    def test_get_credential_by_client_id_no_user_manager(self):
        """Line 124: Returns None when UserManager not initialized"""
        mcp_manager = MCPCredentialManager(user_manager=None)

        found = mcp_manager.get_credential_by_client_id("mcp_test12345678")
        assert found is None

    def test_get_credential_by_client_id_user_data_not_found(self, mcp_manager, user_manager):
        """Line 132: Continue when user_data is None (defensive check)"""
        from unittest.mock import MagicMock

        # Generate credential for testuser
        result = mcp_manager.generate_credential("testuser", name="Test")

        # Create a mock user object for a non-existent user
        ghost_user = MagicMock()
        ghost_user.username = "ghost_user"

        # Store original get_all_users
        original_get_all_users = user_manager.get_all_users

        # Mock get_all_users to return real user + ghost user
        def mock_get_all_users():
            real_users = original_get_all_users()
            return real_users + [ghost_user]

        user_manager.get_all_users = mock_get_all_users

        try:
            # Should still find testuser's credential despite ghost_user causing continue at line 132
            found = mcp_manager.get_credential_by_client_id(result["client_id"])
            assert found is not None
            assert found[0] == "testuser"
        finally:
            # Restore original method
            user_manager.get_all_users = original_get_all_users

    def test_verify_credential_missing_hash(self, mcp_manager, user_manager):
        """Line 162: Returns None when stored_hash is missing"""
        # Generate credential
        result = mcp_manager.generate_credential("testuser", name="Test")
        client_id = result["client_id"]

        # Manually corrupt the stored credential by removing the hash
        users_data = user_manager._load_users()
        users_data["testuser"]["mcp_credentials"][0].pop("client_secret_hash")
        user_manager._save_users(users_data)

        # Try to verify - should return None due to missing hash
        user_id = mcp_manager.verify_credential(client_id, "any_secret")
        assert user_id is None

    def test_revoke_credential_no_user_manager(self):
        """Line 186: Returns False when UserManager not initialized"""
        mcp_manager = MCPCredentialManager(user_manager=None)

        revoked = mcp_manager.revoke_credential("testuser", "fake-credential-id")
        assert revoked is False
