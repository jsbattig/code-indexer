"""
Unit tests for API key manager.

Tests API key generation, format validation, hashing, and storage.
"""

import pytest
import re
from datetime import datetime
import json
import tempfile
import os

from code_indexer.server.auth.api_key_manager import ApiKeyManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.password_manager import PasswordManager


class TestApiKeyManager:
    """Test API key generation and management."""

    @pytest.fixture
    def temp_users_file(self):
        """Create temporary users file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        # Initialize with empty dict
        with open(path, "w") as f:
            json.dump({}, f)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def user_manager(self, temp_users_file):
        """Create user manager with temp file."""
        return UserManager(users_file_path=temp_users_file)

    @pytest.fixture
    def test_user(self, user_manager):
        """Create a test user."""
        return user_manager.create_user(
            username="testuser",
            password="TestPass123!@#",
            role=UserRole.NORMAL_USER,
        )

    @pytest.fixture
    def api_key_manager(self, user_manager):
        """Create API key manager."""
        return ApiKeyManager(user_manager=user_manager)

    def test_generate_key_format_correct(self, api_key_manager, test_user):
        """Test that generated API keys have correct format: cidx_sk_<32-hex-chars>."""
        raw_key, key_id = api_key_manager.generate_key(test_user.username)

        # Check prefix
        assert raw_key.startswith(
            "cidx_sk_"
        ), f"Key should start with cidx_sk_, got: {raw_key}"

        # Check total length (cidx_sk_ = 8 chars + 32 hex chars = 40 total)
        assert len(raw_key) == 40, f"Key should be 40 chars total, got: {len(raw_key)}"

        # Check hex portion (after prefix)
        hex_portion = raw_key[8:]
        assert (
            len(hex_portion) == 32
        ), f"Hex portion should be 32 chars, got: {len(hex_portion)}"
        assert re.match(
            r"^[a-f0-9]{32}$", hex_portion
        ), f"Hex portion should be lowercase hex, got: {hex_portion}"

    def test_generate_key_unique_each_call(self, api_key_manager, test_user):
        """Test that each call to generate_key returns a unique key."""
        raw_key1, key_id1 = api_key_manager.generate_key(test_user.username)
        raw_key2, key_id2 = api_key_manager.generate_key(test_user.username)

        assert raw_key1 != raw_key2, "Each generated key should be unique"
        assert key_id1 != key_id2, "Each key_id should be unique"

    def test_key_hash_is_bcrypt(self, api_key_manager, test_user, user_manager):
        """Test that key hash stored uses bcrypt (via PasswordManager.hash_password)."""
        raw_key, key_id = api_key_manager.generate_key(
            test_user.username, name="test-key"
        )

        # Load user data to check stored hash
        users_data = user_manager._load_users()
        user_data = users_data[test_user.username]

        assert "api_keys" in user_data, "User should have api_keys field"
        assert len(user_data["api_keys"]) == 1, "User should have 1 API key"

        key_entry = user_data["api_keys"][0]
        stored_hash = key_entry["hash"]

        # Bcrypt hashes start with $2b$ (pwdlib uses BcryptHasher)
        assert stored_hash.startswith(
            "$2b$"
        ), f"Hash should be bcrypt format, got: {stored_hash[:10]}"

        # Verify the hash can validate the raw key
        password_manager = PasswordManager()
        assert password_manager.verify_password(
            raw_key, stored_hash
        ), "Hash should verify against raw key"

    def test_add_api_key_to_user(self, api_key_manager, test_user, user_manager):
        """Test that API key is properly added to user's api_keys array."""
        raw_key, key_id = api_key_manager.generate_key(
            test_user.username, name="my-key"
        )

        # Load user data
        users_data = user_manager._load_users()
        user_data = users_data[test_user.username]

        assert "api_keys" in user_data, "User should have api_keys field"
        assert len(user_data["api_keys"]) == 1, "User should have 1 API key"

        key_entry = user_data["api_keys"][0]

        # Validate structure
        assert "key_id" in key_entry, "Key entry should have key_id"
        assert "name" in key_entry, "Key entry should have name"
        assert "hash" in key_entry, "Key entry should have hash"
        assert "created_at" in key_entry, "Key entry should have created_at"

        # Validate values
        assert (
            key_entry["key_id"] == key_id
        ), "Stored key_id should match returned key_id"
        assert key_entry["name"] == "my-key", "Stored name should match provided name"

        # Validate created_at is ISO format timestamp
        created_at = datetime.fromisoformat(
            key_entry["created_at"].replace("Z", "+00:00")
        )
        assert created_at.tzinfo is not None, "created_at should have timezone"

    def test_api_keys_persisted_to_file(self, api_key_manager, test_user, user_manager):
        """Test that API keys are persisted to users.json file."""
        raw_key, key_id = api_key_manager.generate_key(
            test_user.username, name="persistent-key"
        )

        # Read file directly
        with open(user_manager.users_file_path, "r") as f:
            file_data = json.load(f)

        user_data = file_data[test_user.username]
        assert "api_keys" in user_data, "api_keys should be in file"
        assert len(user_data["api_keys"]) == 1, "File should contain 1 API key"

        key_entry = user_data["api_keys"][0]
        assert key_entry["key_id"] == key_id, "File should contain correct key_id"
        assert key_entry["name"] == "persistent-key", "File should contain correct name"

    def test_generate_key_without_name(self, api_key_manager, test_user, user_manager):
        """Test that API key can be generated without a name (name should be None)."""
        raw_key, key_id = api_key_manager.generate_key(test_user.username)

        users_data = user_manager._load_users()
        user_data = users_data[test_user.username]
        key_entry = user_data["api_keys"][0]

        assert key_entry["name"] is None, "Name should be None when not provided"

    def test_raw_key_not_stored(self, api_key_manager, test_user, user_manager):
        """Test that raw API key is NOT stored in users.json (only the hash)."""
        raw_key, key_id = api_key_manager.generate_key(
            test_user.username, name="secret-key"
        )

        # Read file directly
        with open(user_manager.users_file_path, "r") as f:
            file_contents = f.read()

        # Raw key should NOT appear in file
        assert raw_key not in file_contents, "Raw key should NOT be stored in file"

        # But the hash should be there
        users_data = json.loads(file_contents)
        user_data = users_data[test_user.username]
        key_entry = user_data["api_keys"][0]
        assert "hash" in key_entry, "Hash should be stored"
        assert key_entry["hash"] != raw_key, "Hash should not be the raw key"

    def test_multiple_keys_per_user(self, api_key_manager, test_user, user_manager):
        """Test that a user can have multiple API keys."""
        raw_key1, key_id1 = api_key_manager.generate_key(
            test_user.username, name="key1"
        )
        raw_key2, key_id2 = api_key_manager.generate_key(
            test_user.username, name="key2"
        )

        users_data = user_manager._load_users()
        user_data = users_data[test_user.username]

        assert len(user_data["api_keys"]) == 2, "User should have 2 API keys"

        key_ids = [k["key_id"] for k in user_data["api_keys"]]
        assert key_id1 in key_ids, "First key_id should be in list"
        assert key_id2 in key_ids, "Second key_id should be in list"

    def test_key_id_is_uuid(self, api_key_manager, test_user):
        """Test that key_id is a valid UUID4."""
        from uuid import UUID

        raw_key, key_id = api_key_manager.generate_key(test_user.username)

        # Should be parseable as UUID
        try:
            uuid_obj = UUID(key_id)
            # Should be UUID4 version
            assert (
                uuid_obj.version == 4
            ), f"key_id should be UUID4, got version {uuid_obj.version}"
        except ValueError as e:
            pytest.fail(f"key_id should be valid UUID: {e}")

    def test_delete_api_key_success(self, api_key_manager, test_user, user_manager):
        """Test that delete_api_key successfully removes an existing key."""
        # Generate two keys
        raw_key1, key_id1 = api_key_manager.generate_key(
            test_user.username, name="key1"
        )
        raw_key2, key_id2 = api_key_manager.generate_key(
            test_user.username, name="key2"
        )

        # Verify both keys exist
        users_data = user_manager._load_users()
        assert len(users_data[test_user.username]["api_keys"]) == 2

        # Delete first key
        result = user_manager.delete_api_key(test_user.username, key_id1)
        assert result is True, "delete_api_key should return True on success"

        # Verify only second key remains
        users_data = user_manager._load_users()
        remaining_keys = users_data[test_user.username]["api_keys"]
        assert len(remaining_keys) == 1, "Should have 1 key remaining after deletion"
        assert remaining_keys[0]["key_id"] == key_id2, "Remaining key should be key2"
        assert remaining_keys[0]["name"] == "key2", "Remaining key name should be key2"

    def test_delete_api_key_not_found(self, user_manager, test_user):
        """Test that delete_api_key returns False for non-existent key."""
        result = user_manager.delete_api_key(test_user.username, "non-existent-key-id")
        assert result is False, "delete_api_key should return False when key not found"

    def test_delete_api_key_wrong_user(self, api_key_manager, user_manager):
        """Test that user cannot delete another user's key."""
        # Create two users
        user1 = user_manager.create_user(
            username="user1",
            password="TestPass123!@#",
            role=UserRole.NORMAL_USER,
        )
        user2 = user_manager.create_user(
            username="user2",
            password="TestPass456!@#",
            role=UserRole.NORMAL_USER,
        )

        # Generate key for user1
        raw_key, key_id = api_key_manager.generate_key(user1.username, name="user1-key")

        # Try to delete user1's key as user2
        result = user_manager.delete_api_key(user2.username, key_id)
        assert result is False, "Should not be able to delete another user's key"

        # Verify user1's key still exists
        users_data = user_manager._load_users()
        assert (
            len(users_data[user1.username]["api_keys"]) == 1
        ), "user1 should still have their key"

    def test_delete_api_key_user_not_found(self, user_manager):
        """Test that delete_api_key returns False for non-existent user."""
        result = user_manager.delete_api_key("non-existent-user", "some-key-id")
        assert result is False, "delete_api_key should return False when user not found"

    def test_get_api_keys_no_hash_exposure_in_fallback(
        self, api_key_manager, test_user, user_manager
    ):
        """Test that get_api_keys does not expose bcrypt hash when key_prefix is missing.

        This test simulates legacy or corrupted data where key_prefix is missing from
        stored API key data. The fallback should use a safe masked placeholder, not
        expose any part of the bcrypt hash.
        """
        # Generate a key normally (which includes key_prefix)
        raw_key, key_id = api_key_manager.generate_key(
            test_user.username, name="legacy-key"
        )

        # Simulate legacy data by removing key_prefix from stored data
        users_data = user_manager._load_users()
        user_data = users_data[test_user.username]
        key_entry = user_data["api_keys"][0]

        # Store the hash for validation
        stored_hash = key_entry["hash"]

        # Remove key_prefix to simulate legacy data
        del key_entry["key_prefix"]
        user_manager._save_users(users_data)

        # Get API keys (should use fallback)
        keys = user_manager.get_api_keys(test_user.username)

        assert len(keys) == 1, "Should return 1 key"
        returned_key = keys[0]

        # Validate key_prefix is the safe fallback
        assert (
            returned_key["key_prefix"] == "cidx_sk_****..."
        ), "Fallback key_prefix should be safe masked placeholder"

        # Critical: Verify no part of the bcrypt hash is exposed
        assert stored_hash not in str(
            returned_key
        ), "Bcrypt hash should not be exposed in returned data"
        assert (
            "$2b$" not in returned_key["key_prefix"]
        ), "Bcrypt hash format should not be exposed in key_prefix"

        # Verify other fields are correct
        assert returned_key["key_id"] == key_id
        assert returned_key["name"] == "legacy-key"
        assert "created_at" in returned_key

        # Verify hash is NOT in the returned data
        assert "hash" not in returned_key, "Hash should never be returned to client"
