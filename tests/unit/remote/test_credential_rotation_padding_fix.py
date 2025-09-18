"""Test credential rotation handles corrupted credentials gracefully."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import secrets

import pytest

from code_indexer.remote.credential_rotation import CredentialRotationManager
from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    store_encrypted_credentials,
)
from code_indexer.remote.exceptions import RemoteConfigurationError


class TestCredentialRotationPaddingFix:
    """Test that credential rotation handles corrupted/undecryptable credentials gracefully."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(exist_ok=True)
        self.remote_config_path = self.config_dir / ".remote-config"

        # Create mock remote configuration
        self.original_config = {
            "mode": "remote",
            "server_url": "https://example.com",
            "username": "testuser",
            "created_at": "2024-01-01T00:00:00Z",
        }
        with open(self.remote_config_path, "w") as f:
            json.dump(self.original_config, f)

    def test_rotation_succeeds_with_corrupted_existing_credentials(self):
        """Test that credential rotation succeeds even when existing credentials are corrupted."""
        # Create corrupted credentials file (random bytes that can't be decrypted)
        corrupted_data = secrets.token_bytes(100)
        store_encrypted_credentials(self.temp_dir, corrupted_data)

        # Mock successful validation for new credentials
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # This should succeed despite corrupted credentials
            result = manager.update_credentials("newuser", "newpass")

            assert "successfully updated" in result.lower()
            assert mock_validate.called

            # Verify configuration was updated with new username
            with open(self.remote_config_path, "r") as f:
                updated_config = json.load(f)
            assert updated_config["username"] == "newuser"

    def test_backup_creation_handles_decryption_error_gracefully(self):
        """Test that backup creation doesn't fail when credentials can't be decrypted."""
        # Create valid but undecryptable credentials (wrong encryption parameters)
        credential_manager = ProjectCredentialManager()
        # Encrypt with different parameters than what will be used for decryption
        wrong_encrypted = credential_manager.encrypt_credentials(
            "olduser",
            "oldpass",
            "https://different.com",  # Different server URL
            str(self.temp_dir),
        )
        store_encrypted_credentials(self.temp_dir, wrong_encrypted)

        manager = CredentialRotationManager(self.temp_dir)

        # Backup creation should not raise exception
        backup_info = manager._create_credential_backup()

        # Backup info should exist but credentials_backup should be None
        assert backup_info is not None
        assert backup_info["credentials_backup"] is None
        assert "timestamp" in backup_info

    def test_rotation_with_no_existing_credentials(self):
        """Test credential rotation works when no existing credentials exist."""
        # No credentials file created

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # Should succeed even without existing credentials
            result = manager.update_credentials("newuser", "newpass")

            assert "successfully updated" in result.lower()
            assert mock_validate.called

    def test_rotation_with_valid_existing_credentials(self):
        """Test credential rotation still works normally with valid existing credentials."""
        # Create valid credentials that can be decrypted
        credential_manager = ProjectCredentialManager()
        valid_encrypted = credential_manager.encrypt_credentials(
            "testuser",  # Matches config username
            "testpass",
            "https://example.com",  # Matches config server_url
            str(self.temp_dir),
        )
        store_encrypted_credentials(self.temp_dir, valid_encrypted)

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # Create backup and verify it contains the credentials
            backup_info = manager._create_credential_backup()

            assert backup_info is not None
            assert backup_info["credentials_backup"] is not None
            assert backup_info["credentials_backup"]["username"] == "testuser"
            assert backup_info["credentials_backup"]["password"] == "testpass"
            assert (
                backup_info["credentials_backup"]["server_url"] == "https://example.com"
            )

    def test_rollback_handles_missing_credential_backup(self):
        """Test that rollback works even when credential backup is None."""
        manager = CredentialRotationManager(self.temp_dir)

        # Create backup info with no credential backup (simulating decryption failure)
        backup_info = {
            "timestamp": "2024-01-01T00:00:00",
            "config_backup": None,
            "credentials_backup": None,  # No credential backup due to decryption failure
        }

        # Rollback should not raise exception
        manager._rollback_credentials(backup_info)

        # Should complete without error even with no credentials to restore

    def test_credential_validation_error_preserves_original_state(self):
        """Test that validation failure preserves original credentials even if corrupted."""
        # Create corrupted credentials
        corrupted_data = secrets.token_bytes(100)
        store_encrypted_credentials(self.temp_dir, corrupted_data)

        # Mock validation to fail
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = False

            manager = CredentialRotationManager(self.temp_dir)

            with pytest.raises(RemoteConfigurationError, match="Invalid credentials"):
                manager.update_credentials("newuser", "newpass")

            # Original configuration should be unchanged
            with open(self.remote_config_path, "r") as f:
                config = json.load(f)
            assert config["username"] == "testuser"

            # Corrupted credentials file should still exist (not replaced)
            creds_path = self.config_dir / ".creds"
            assert creds_path.exists()
            with open(creds_path, "rb") as f:
                data = f.read()
            assert data == corrupted_data  # Original corrupted data preserved

    def test_secure_memory_cleanup_after_rotation(self):
        """Test that sensitive data is securely cleaned from memory after rotation."""
        # Create corrupted credentials to test the fix path
        corrupted_data = secrets.token_bytes(100)
        store_encrypted_credentials(self.temp_dir, corrupted_data)

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # Mock the secure cleanup to verify it's called
            with patch.object(manager, "_secure_memory_cleanup") as mock_cleanup:
                manager.update_credentials("newuser", "newpass")

                # Verify secure cleanup was called for both username and password
                assert mock_cleanup.call_count == 2
