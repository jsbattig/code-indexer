"""Integration tests for RemoteConfig with credential encryption."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from code_indexer.remote.config import RemoteConfig
from code_indexer.remote.credential_manager import (
    CredentialNotFoundError,
    CredentialDecryptionError,
)


class TestRemoteConfigEncryptionIntegration:
    """Test RemoteConfig integration with credential encryption."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "project"
        self.project_root.mkdir()

        self.test_server_url = "https://cidx.example.com"
        self.test_username = "testuser"
        self.test_password = "securepass123"

        # Create basic remote config file (without credentials)
        self.config_dir = self.project_root / ".code-indexer"
        self.config_dir.mkdir()

        self.remote_config_data = {
            "mode": "remote",
            "server_url": self.test_server_url,
            "username": self.test_username,
            "created_at": "2023-01-01T00:00:00Z",
        }

        config_file = self.config_dir / ".remote-config"
        with open(config_file, "w") as f:
            json.dump(self.remote_config_data, f)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_remote_config_initialization_loads_configuration(self):
        """Test RemoteConfig loads existing configuration on initialization."""
        config = RemoteConfig(self.project_root)

        assert config.server_url == self.test_server_url
        assert config.username == self.test_username
        assert config.mode == "remote"

    def test_get_decrypted_credentials_loads_and_decrypts(self):
        """Test get_decrypted_credentials loads and decrypts stored credentials."""
        # Create and store encrypted credentials first
        config = RemoteConfig(self.project_root)
        config.store_credentials(self.test_password)

        # Load and decrypt
        decrypted_creds = config.get_decrypted_credentials()

        assert decrypted_creds.username == self.test_username
        assert decrypted_creds.password == self.test_password
        assert decrypted_creds.server_url == self.test_server_url

    def test_store_credentials_encrypts_and_stores(self):
        """Test store_credentials encrypts and stores credentials securely."""
        config = RemoteConfig(self.project_root)
        config.store_credentials(self.test_password)

        # Verify encrypted file was created
        creds_file = self.config_dir / ".creds"
        assert creds_file.exists()

        # Verify file has secure permissions
        import stat

        file_mode = creds_file.stat().st_mode
        assert stat.filemode(file_mode) == "-rw-------"

        # Verify credentials can be loaded back
        decrypted_creds = config.get_decrypted_credentials()
        assert decrypted_creds.password == self.test_password

    def test_credential_project_isolation(self):
        """Test credentials are isolated per project."""
        # Create config in project 1
        config1 = RemoteConfig(self.project_root)
        config1.store_credentials("password1")

        # Create config in project 2
        project2_root = self.temp_dir / "project2"
        project2_root.mkdir()
        config2_dir = project2_root / ".code-indexer"
        config2_dir.mkdir()

        # Copy config to project 2 but change username
        config2_data = self.remote_config_data.copy()
        config2_data["username"] = "user2"

        config2_file = config2_dir / ".remote-config"
        with open(config2_file, "w") as f:
            json.dump(config2_data, f)

        config2 = RemoteConfig(project2_root)
        config2.store_credentials("password2")

        # Verify project 1 credentials haven't changed
        creds1 = config1.get_decrypted_credentials()
        assert creds1.password == "password1"
        assert creds1.username == self.test_username

        # Verify project 2 has different credentials
        creds2 = config2.get_decrypted_credentials()
        assert creds2.password == "password2"
        assert creds2.username == "user2"

    def test_get_credentials_without_stored_credentials_raises_error(self):
        """Test getting credentials when none are stored raises CredentialNotFoundError."""
        config = RemoteConfig(self.project_root)

        with pytest.raises(CredentialNotFoundError):
            config.get_decrypted_credentials()

    def test_get_credentials_with_corrupted_file_raises_error(self):
        """Test getting credentials from corrupted file raises CredentialDecryptionError."""
        config = RemoteConfig(self.project_root)

        # Create corrupted credentials file
        creds_file = self.config_dir / ".creds"
        with open(creds_file, "wb") as f:
            f.write(b"corrupted_data")

        creds_file.chmod(0o600)  # Set secure permissions

        with pytest.raises(CredentialDecryptionError):
            config.get_decrypted_credentials()

    def test_get_credentials_auto_fixes_insecure_permissions(self):
        """Test getting credentials auto-fixes insecurely stored file permissions."""
        config = RemoteConfig(self.project_root)
        config.store_credentials(self.test_password)

        # Change file permissions to insecure
        creds_file = self.config_dir / ".creds"
        creds_file.chmod(0o644)  # Readable by group/others

        # Should auto-fix permissions and load successfully
        creds = config.get_decrypted_credentials()
        assert creds.password == self.test_password

        # Verify permissions were fixed to 600
        file_mode = creds_file.stat().st_mode
        assert not (file_mode & 0o077), "File should have secure permissions (600)"

    def test_credential_rotation_updates_stored_credentials(self):
        """Test storing new credentials overwrites existing ones."""
        config = RemoteConfig(self.project_root)

        # Store initial credentials
        config.store_credentials("initial_password")
        initial_creds = config.get_decrypted_credentials()
        assert initial_creds.password == "initial_password"

        # Rotate credentials
        config.store_credentials("new_password")
        updated_creds = config.get_decrypted_credentials()
        assert updated_creds.password == "new_password"

        # Verify username and server URL remain the same
        assert updated_creds.username == self.test_username
        assert updated_creds.server_url == self.test_server_url

    def test_has_stored_credentials_detection(self):
        """Test detection of whether credentials are stored."""
        config = RemoteConfig(self.project_root)

        # Initially no credentials
        assert not config.has_stored_credentials()

        # After storing credentials
        config.store_credentials(self.test_password)
        assert config.has_stored_credentials()

    def test_clear_credentials_removes_stored_data(self):
        """Test clearing credentials removes stored data securely."""
        config = RemoteConfig(self.project_root)
        config.store_credentials(self.test_password)

        # Verify credentials exist
        assert config.has_stored_credentials()

        # Clear credentials
        config.clear_credentials()

        # Verify credentials are gone
        assert not config.has_stored_credentials()

        # Verify file is removed
        creds_file = self.config_dir / ".creds"
        assert not creds_file.exists()

        # Verify getting credentials now raises error
        with pytest.raises(CredentialNotFoundError):
            config.get_decrypted_credentials()

    def test_credential_validation_integration(self):
        """Test credential storage integrates with validation workflow."""
        config = RemoteConfig(self.project_root)

        # Store credentials after validation
        config.store_credentials(self.test_password)

        # Verify credentials for API client usage
        creds = config.get_decrypted_credentials()

        # Create credentials dict for API client
        credentials_dict = {
            "username": creds.username,
            "password": creds.password,
            "server_url": creds.server_url,
        }

        assert credentials_dict["username"] == self.test_username
        assert credentials_dict["password"] == self.test_password
        assert credentials_dict["server_url"] == self.test_server_url

    def test_config_file_corruption_handling(self):
        """Test handling of corrupted remote config file."""
        # Corrupt the remote config file
        config_file = self.config_dir / ".remote-config"
        with open(config_file, "w") as f:
            f.write("invalid json data")

        with pytest.raises(json.JSONDecodeError):
            RemoteConfig(self.project_root)

    def test_missing_config_file_handling(self):
        """Test handling of missing remote config file."""
        # Remove config file
        config_file = self.config_dir / ".remote-config"
        config_file.unlink()

        with pytest.raises(FileNotFoundError):
            RemoteConfig(self.project_root)

    @patch("code_indexer.remote.config.ProjectCredentialManager")
    def test_credential_manager_error_propagation(self, mock_manager_class):
        """Test credential manager errors are properly propagated."""
        # Mock credential manager to raise encryption error
        mock_manager = Mock()
        mock_manager.encrypt_credentials.side_effect = Exception("Encryption failed")
        mock_manager_class.return_value = mock_manager

        config = RemoteConfig(self.project_root)

        with pytest.raises(Exception, match="Encryption failed"):
            config.store_credentials(self.test_password)

    def test_secure_memory_handling_in_integration(self):
        """Test secure memory handling throughout the credential lifecycle."""
        config = RemoteConfig(self.project_root)

        # Store credentials
        config.store_credentials(self.test_password)

        # Load credentials multiple times
        for _ in range(3):
            creds = config.get_decrypted_credentials()
            assert creds.password == self.test_password

        # Test passes if no memory-related exceptions occur
        # Real memory security would require specialized testing tools
