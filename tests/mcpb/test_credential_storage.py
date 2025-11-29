"""Unit tests for encrypted credential storage.

This module tests the credential storage functionality that allows mcpb
to securely store and retrieve username/password for automatic login.
"""

import os
from pathlib import Path

import pytest

from code_indexer.mcpb.credential_storage import (
    save_credentials,
    load_credentials,
    credentials_exist,
    delete_credentials,
)


@pytest.fixture
def temp_mcpb_dir(monkeypatch, tmp_path):
    """Fixture to use temporary directory for ~/.mcpb."""
    mcpb_dir = tmp_path / ".mcpb"
    mcpb_dir.mkdir(parents=True, exist_ok=True)

    # Patch Path.home() to return tmp_path
    def mock_home():
        return tmp_path

    monkeypatch.setattr(Path, "home", mock_home)

    yield mcpb_dir

    # Cleanup handled by tmp_path fixture


class TestCredentialStorage:
    """Test encrypted credential storage functionality."""

    def test_save_and_load_credentials(self, temp_mcpb_dir):
        """Test that credentials can be saved and loaded successfully."""
        username = "test_user"
        password = "test_password_123"

        # Save credentials
        save_credentials(username, password)

        # Verify files exist
        assert (temp_mcpb_dir / "credentials.enc").exists()
        assert (temp_mcpb_dir / "encryption.key").exists()

        # Load credentials
        loaded_username, loaded_password = load_credentials()

        # Verify credentials match
        assert loaded_username == username
        assert loaded_password == password

    def test_credentials_exist_returns_true_when_files_exist(self, temp_mcpb_dir):
        """Test that credentials_exist() returns True when both files exist."""
        username = "test_user"
        password = "test_password"

        # Save credentials
        save_credentials(username, password)

        # Verify credentials_exist returns True
        assert credentials_exist() is True

    def test_credentials_exist_returns_false_when_files_missing(self, temp_mcpb_dir):
        """Test that credentials_exist() returns False when files don't exist."""
        # No credentials saved
        assert credentials_exist() is False

    def test_credentials_exist_returns_false_when_only_key_exists(self, temp_mcpb_dir):
        """Test that credentials_exist() returns False when only key file exists."""
        # Create only key file
        key_file = temp_mcpb_dir / "encryption.key"
        key_file.write_text("fake_key")

        assert credentials_exist() is False

    def test_credentials_exist_returns_false_when_only_creds_exist(self, temp_mcpb_dir):
        """Test that credentials_exist() returns False when only credentials file exists."""
        # Create only credentials file
        creds_file = temp_mcpb_dir / "credentials.enc"
        creds_file.write_text("fake_encrypted_data")

        assert credentials_exist() is False

    def test_load_credentials_raises_error_when_files_missing(self, temp_mcpb_dir):
        """Test that load_credentials() raises error when files don't exist."""
        with pytest.raises(FileNotFoundError, match="Credential files not found"):
            load_credentials()

    def test_load_credentials_raises_error_on_decryption_failure(self, temp_mcpb_dir):
        """Test that load_credentials() raises error when decryption fails."""
        # Create files with invalid content
        key_file = temp_mcpb_dir / "encryption.key"
        creds_file = temp_mcpb_dir / "credentials.enc"

        key_file.write_text("invalid_key_content")
        creds_file.write_text("invalid_encrypted_data")

        with pytest.raises(Exception):  # Will raise cryptography error
            load_credentials()

    def test_delete_credentials_removes_files(self, temp_mcpb_dir):
        """Test that delete_credentials() removes both files."""
        # Save credentials
        save_credentials("user", "pass")

        # Verify files exist
        assert (temp_mcpb_dir / "credentials.enc").exists()
        assert (temp_mcpb_dir / "encryption.key").exists()

        # Delete credentials
        delete_credentials()

        # Verify files removed
        assert not (temp_mcpb_dir / "credentials.enc").exists()
        assert not (temp_mcpb_dir / "encryption.key").exists()

    def test_delete_credentials_handles_missing_files(self, temp_mcpb_dir):
        """Test that delete_credentials() handles missing files gracefully."""
        # No credentials exist
        # Should not raise error
        delete_credentials()

    def test_file_permissions_are_600(self, temp_mcpb_dir):
        """Test that credential files have secure 600 permissions."""
        save_credentials("user", "pass")

        # Check credentials file permissions
        creds_file = temp_mcpb_dir / "credentials.enc"
        creds_perms = os.stat(creds_file).st_mode & 0o777
        assert (
            creds_perms == 0o600
        ), f"credentials.enc has insecure permissions: {oct(creds_perms)}"

        # Check key file permissions
        key_file = temp_mcpb_dir / "encryption.key"
        key_perms = os.stat(key_file).st_mode & 0o777
        assert (
            key_perms == 0o600
        ), f"encryption.key has insecure permissions: {oct(key_perms)}"

    def test_save_credentials_creates_directory_if_not_exists(
        self, monkeypatch, tmp_path
    ):
        """Test that save_credentials() creates ~/.mcpb directory if it doesn't exist."""
        # Use a fresh temp directory without .mcpb
        fresh_tmp = tmp_path / "fresh"
        fresh_tmp.mkdir()

        def mock_home():
            return fresh_tmp

        monkeypatch.setattr(Path, "home", mock_home)

        # Verify .mcpb doesn't exist
        mcpb_dir = fresh_tmp / ".mcpb"
        assert not mcpb_dir.exists()

        # Save credentials
        save_credentials("user", "pass")

        # Verify directory was created
        assert mcpb_dir.exists()
        assert mcpb_dir.is_dir()

    def test_encryption_key_has_600_permissions(self, temp_mcpb_dir):
        """Test that encryption key file has secure 600 permissions."""
        save_credentials("user", "pass")

        key_file = temp_mcpb_dir / "encryption.key"
        key_perms = os.stat(key_file).st_mode & 0o777
        assert key_perms == 0o600

    def test_different_credentials_decrypt_correctly(self, temp_mcpb_dir):
        """Test that different username/password combinations work correctly."""
        test_cases = [
            ("user1", "password1"),
            ("admin@example.com", "complex_P@ssw0rd!"),
            ("test", "simple"),
            ("u" * 100, "p" * 100),  # Long credentials
        ]

        for username, password in test_cases:
            # Save credentials
            save_credentials(username, password)

            # Load and verify
            loaded_username, loaded_password = load_credentials()
            assert loaded_username == username
            assert loaded_password == password

            # Cleanup for next iteration
            delete_credentials()

    def test_save_credentials_overwrites_existing(self, temp_mcpb_dir):
        """Test that saving credentials overwrites existing ones."""
        # Save first set
        save_credentials("user1", "pass1")
        loaded_user1, loaded_pass1 = load_credentials()
        assert loaded_user1 == "user1"
        assert loaded_pass1 == "pass1"

        # Save second set (should overwrite)
        save_credentials("user2", "pass2")
        loaded_user2, loaded_pass2 = load_credentials()
        assert loaded_user2 == "user2"
        assert loaded_pass2 == "pass2"

    def test_credentials_with_special_characters(self, temp_mcpb_dir):
        """Test that credentials with special characters work correctly."""
        username = "user@example.com"
        password = "P@ssw0rd!#$%^&*()_+-=[]{}|;':\",./<>?"

        save_credentials(username, password)
        loaded_username, loaded_password = load_credentials()

        assert loaded_username == username
        assert loaded_password == password

    def test_empty_credentials_raise_error(self, temp_mcpb_dir):
        """Test that empty username or password raises ValueError."""
        with pytest.raises(ValueError, match="Username cannot be empty"):
            save_credentials("", "password")

        with pytest.raises(ValueError, match="Password cannot be empty"):
            save_credentials("username", "")
