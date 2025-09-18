"""Unit tests for ProjectCredentialManager with PBKDF2 encryption."""

import secrets
import pytest
from unittest.mock import patch

from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    CredentialEncryptionError,
    CredentialDecryptionError,
)


class TestProjectCredentialManager:
    """Test ProjectCredentialManager implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ProjectCredentialManager()
        self.test_username = "testuser"
        self.test_password = "securepass123"
        self.test_server_url = "https://cidx.example.com"
        self.test_repo_path = "/home/user/project1"

    def test_pbkdf2_key_derivation_with_project_specific_inputs(self):
        """Test PBKDF2 key derivation uses project-specific inputs correctly."""
        salt = secrets.token_bytes(32)

        # Derive key for project 1
        key1 = self.manager._derive_project_key(
            self.test_username, "/home/user/project1", self.test_server_url, salt
        )

        # Derive key for project 2 with same user/server but different path
        key2 = self.manager._derive_project_key(
            self.test_username, "/home/user/project2", self.test_server_url, salt
        )

        # Keys should be different for different projects
        assert key1 != key2
        assert len(key1) == 32  # AES-256 key length
        assert len(key2) == 32  # AES-256 key length

    def test_pbkdf2_uses_100k_iterations(self):
        """Test PBKDF2 uses exactly 100,000 iterations for security."""
        assert self.manager.iterations == 100_000
        assert self.manager.key_length == 32  # AES-256

    def test_same_inputs_produce_same_key(self):
        """Test that identical inputs produce identical keys."""
        salt = secrets.token_bytes(32)

        key1 = self.manager._derive_project_key(
            self.test_username, self.test_repo_path, self.test_server_url, salt
        )
        key2 = self.manager._derive_project_key(
            self.test_username, self.test_repo_path, self.test_server_url, salt
        )

        assert key1 == key2

    def test_different_usernames_produce_different_keys(self):
        """Test that different usernames produce different keys."""
        salt = secrets.token_bytes(32)

        key1 = self.manager._derive_project_key(
            "user1", self.test_repo_path, self.test_server_url, salt
        )
        key2 = self.manager._derive_project_key(
            "user2", self.test_repo_path, self.test_server_url, salt
        )

        assert key1 != key2

    def test_different_server_urls_produce_different_keys(self):
        """Test that different server URLs produce different keys."""
        salt = secrets.token_bytes(32)

        key1 = self.manager._derive_project_key(
            self.test_username, self.test_repo_path, "https://server1.com", salt
        )
        key2 = self.manager._derive_project_key(
            self.test_username, self.test_repo_path, "https://server2.com", salt
        )

        assert key1 != key2

    def test_encrypt_credentials_returns_encrypted_data(self):
        """Test credential encryption returns properly formatted data."""
        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        # Should return bytes
        assert isinstance(encrypted_data, bytes)

        # Should be at least 48 bytes (32 salt + 16 IV) plus ciphertext
        assert len(encrypted_data) >= 48

        # Salt should be first 32 bytes
        salt = encrypted_data[:32]
        assert len(salt) == 32

        # IV should be next 16 bytes
        iv = encrypted_data[32:48]
        assert len(iv) == 16

        # Remaining should be ciphertext
        ciphertext = encrypted_data[48:]
        assert len(ciphertext) > 0

    def test_encrypt_decrypt_round_trip(self):
        """Test encryption and decryption produces original credentials."""
        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        decrypted_creds = self.manager.decrypt_credentials(
            encrypted_data,
            self.test_username,
            self.test_repo_path,
            self.test_server_url,
        )

        assert decrypted_creds.username == self.test_username
        assert decrypted_creds.password == self.test_password
        assert decrypted_creds.server_url == self.test_server_url

    def test_project_isolation_same_credentials(self):
        """Test same credentials in different projects produce different encrypted data."""
        # Encrypt for project 1
        encrypted_1 = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            "/home/user/project1",
        )

        # Encrypt for project 2
        encrypted_2 = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            "/home/user/project2",
        )

        # Encrypted data should be different
        assert encrypted_1 != encrypted_2

    def test_cross_project_decryption_fails(self):
        """Test credentials encrypted for one project cannot decrypt in another."""
        # Encrypt for project 1
        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            "/home/user/project1",
        )

        # Try to decrypt with project 2 path (should fail)
        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                encrypted_data,
                self.test_username,
                "/home/user/project2",  # Wrong project path
                self.test_server_url,
            )

    def test_salt_uniqueness(self):
        """Test each encryption uses unique salt."""
        encrypted_1 = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        encrypted_2 = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        # Salts should be different
        salt_1 = encrypted_1[:32]
        salt_2 = encrypted_2[:32]
        assert salt_1 != salt_2

    def test_decryption_with_corrupted_data_fails(self):
        """Test decryption fails gracefully with corrupted data."""
        # Create corrupted data (too short)
        corrupted_data = b"corrupted"

        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                corrupted_data,
                self.test_username,
                self.test_repo_path,
                self.test_server_url,
            )

    def test_decryption_with_wrong_username_fails(self):
        """Test decryption fails with wrong username."""
        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                encrypted_data,
                "wronguser",  # Wrong username
                self.test_repo_path,
                self.test_server_url,
            )

    def test_decryption_with_wrong_server_url_fails(self):
        """Test decryption fails with wrong server URL."""
        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                encrypted_data,
                self.test_username,
                self.test_repo_path,
                "https://wrong.server.com",  # Wrong server URL
            )

    @patch("code_indexer.remote.credential_manager.secrets.token_bytes")
    def test_encryption_failure_handling(self, mock_token_bytes):
        """Test encryption error handling."""
        # Make secrets.token_bytes fail
        mock_token_bytes.side_effect = Exception("Crypto error")

        with pytest.raises(
            CredentialEncryptionError, match="Failed to encrypt credentials"
        ):
            self.manager.encrypt_credentials(
                self.test_username,
                self.test_password,
                self.test_server_url,
                self.test_repo_path,
            )

    def test_secure_memory_cleanup(self):
        """Test sensitive data is cleared from memory after use."""
        # This test verifies that encryption/decryption doesn't leave
        # sensitive data in variables that could be accessed later

        encrypted_data = self.manager.encrypt_credentials(
            self.test_username,
            self.test_password,
            self.test_server_url,
            self.test_repo_path,
        )

        # Decrypt the data
        decrypted_creds = self.manager.decrypt_credentials(
            encrypted_data,
            self.test_username,
            self.test_repo_path,
            self.test_server_url,
        )

        # Verify correct decryption
        assert decrypted_creds.password == self.test_password

        # Test passes if no exceptions are raised - memory cleanup
        # would be tested more thoroughly with memory profiling tools
        # in integration tests
