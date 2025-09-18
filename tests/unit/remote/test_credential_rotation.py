"""Unit tests for credential rotation functionality."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner

from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    CredentialEncryptionError,
)
from code_indexer.remote.config import load_remote_configuration
from code_indexer.remote.exceptions import RemoteConfigurationError


class TestCredentialRotationCLI:
    """Test CLI command structure for credential rotation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(exist_ok=True)

    def test_auth_update_command_requires_username_parameter(self):
        """Test that auth update command requires --username parameter."""
        from code_indexer.cli import cli

        # Test missing username parameter
        result = self.runner.invoke(cli, ["auth", "update", "--password", "newpass"])
        assert result.exit_code != 0
        assert "username" in result.output.lower()
        assert "missing option" in result.output.lower()

    def test_auth_update_command_requires_password_parameter(self):
        """Test that auth update command requires --password parameter."""
        from code_indexer.cli import cli

        # Test missing password parameter
        result = self.runner.invoke(cli, ["auth", "update", "--username", "newuser"])
        assert result.exit_code != 0
        assert "password" in result.output.lower()
        assert "missing option" in result.output.lower()

    def test_auth_update_command_requires_both_parameters(self):
        """Test that auth update command requires both username and password parameters."""
        from code_indexer.cli import cli

        # Test missing both parameters
        result = self.runner.invoke(cli, ["auth", "update"])
        assert result.exit_code != 0
        # Should show usage information
        assert "Usage:" in result.output

    def test_auth_update_shows_help_with_usage_example(self):
        """Test that auth update --help shows clear usage example."""
        from code_indexer.cli import cli

        result = self.runner.invoke(cli, ["auth", "update", "--help"])
        assert result.exit_code == 0
        assert "--username" in result.output
        assert "--password" in result.output
        assert "Update remote credentials" in result.output

    def test_auth_command_group_exists(self):
        """Test that auth command group exists and shows help."""
        from code_indexer.cli import cli

        result = self.runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "update" in result.output
        assert "Authentication commands" in result.output


class TestCredentialRotationCore:
    """Test core credential rotation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(exist_ok=True)
        self.remote_config_path = self.config_dir / ".remote-config"

        # Create mock remote configuration
        self.original_config = {
            "mode": "remote",
            "server_url": "https://original.example.com",
            "username": "originaluser",
            "created_at": "2024-01-01T00:00:00Z",
        }
        with open(self.remote_config_path, "w") as f:
            json.dump(self.original_config, f)

    def test_credential_update_validates_credentials_before_storage(self):
        """Test that new credentials are validated with server before storage."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        # Mock validation to fail
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = False

            manager = CredentialRotationManager(self.temp_dir)

            with pytest.raises(RemoteConfigurationError, match="Invalid credentials"):
                manager.update_credentials("newuser", "newpass")

            # Ensure original credentials are unchanged
            config = load_remote_configuration(self.temp_dir)
            assert config["username"] == "originaluser"

    def test_credential_update_preserves_server_url(self):
        """Test that server URL is preserved during credential update."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)
            manager.update_credentials("newuser", "newpass")

            # Server URL should remain unchanged
            config = load_remote_configuration(self.temp_dir)
            assert config["server_url"] == "https://original.example.com"
            assert config["username"] == "newuser"

    def test_credential_update_preserves_repository_links(self):
        """Test that repository links are preserved during credential update."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        # Add repository links to config
        config_with_links = self.original_config.copy()
        config_with_links["repository_links"] = [
            {"name": "main", "branch": "master", "active": True},
            {"name": "dev", "branch": "develop", "active": False},
        ]
        with open(self.remote_config_path, "w") as f:
            json.dump(config_with_links, f)

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)
            manager.update_credentials("newuser", "newpass")

            # Repository links should be preserved
            config = load_remote_configuration(self.temp_dir)
            assert "repository_links" in config
            assert len(config["repository_links"]) == 2
            assert config["repository_links"][0]["name"] == "main"

    def test_credential_update_creates_backup_before_changes(self):
        """Test that original credentials are backed up before update."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # Should create backup during update
            with patch.object(manager, "_create_credential_backup") as mock_backup:
                manager.update_credentials("newuser", "newpass")
                mock_backup.assert_called_once()

    def test_credential_update_rollback_on_validation_failure(self):
        """Test rollback to original credentials when validation fails."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = False  # Validation fails

            manager = CredentialRotationManager(self.temp_dir)

            with pytest.raises(RemoteConfigurationError):
                manager.update_credentials("newuser", "newpass")

            # Original credentials should be preserved
            config = load_remote_configuration(self.temp_dir)
            assert config["username"] == "originaluser"

    def test_credential_update_rollback_on_storage_failure(self):
        """Test rollback to original credentials when storage fails."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)

            # Mock storage failure
            with patch.object(manager, "_store_encrypted_credentials") as mock_store:
                mock_store.side_effect = CredentialEncryptionError("Storage failed")

                with pytest.raises(CredentialEncryptionError):
                    manager.update_credentials("newuser", "newpass")

                # Original credentials should be preserved
                config = load_remote_configuration(self.temp_dir)
                assert config["username"] == "originaluser"

    def test_credential_update_only_works_in_remote_mode(self):
        """Test that credential update only works when project is in remote mode."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        # Create local mode config
        local_config = {"mode": "local"}
        with open(self.remote_config_path, "w") as f:
            json.dump(local_config, f)

        manager = CredentialRotationManager(self.temp_dir)

        with pytest.raises(RemoteConfigurationError, match="not in remote mode"):
            manager.update_credentials("newuser", "newpass")


class TestCredentialRotationSecurity:
    """Test security aspects of credential rotation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(exist_ok=True)

    def test_secure_parameter_memory_cleanup(self):
        """Test that sensitive parameters are cleared from memory."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        manager = CredentialRotationManager(self.temp_dir)

        # Mock bytearrays to track memory cleanup
        username_bytes = bytearray(b"sensitive_user")
        password_bytes = bytearray(b"sensitive_pass")

        with patch("builtins.bytearray", side_effect=[username_bytes, password_bytes]):
            with patch.object(manager, "_secure_memory_cleanup") as mock_cleanup:
                try:
                    manager.update_credentials("sensitive_user", "sensitive_pass")
                except Exception:
                    pass  # We expect this to fail, but cleanup should still happen

                # Memory cleanup should be called for both parameters
                assert mock_cleanup.call_count == 2

    def test_atomic_file_operations(self):
        """Test that file operations are atomic to prevent corruption."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        # Create initial config
        original_config = {
            "mode": "remote",
            "server_url": "https://original.example.com",
            "username": "originaluser",
        }
        config_path = self.config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(original_config, f)

        manager = CredentialRotationManager(self.temp_dir)

        # Mock file write failure midway through operation
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            # Only mock the specific write operation, not all open calls
            original_open = open

            def mock_open(*args, **kwargs):
                if len(args) >= 2 and args[1] == "w" and "tmp" in str(args[0]):
                    raise OSError("Disk full")
                return original_open(*args, **kwargs)

            with patch("builtins.open", side_effect=mock_open):
                with pytest.raises(
                    RemoteConfigurationError
                ):  # Should be wrapped in our exception
                    manager.update_credentials("newuser", "newpass")

                # Original config should be intact
                with original_open(config_path, "r") as f:
                    config = json.load(f)
                assert config["username"] == "originaluser"

    def test_no_sensitive_parameter_echoing_in_success_message(self):
        """Test that success messages don't echo sensitive parameters."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        original_config = {
            "mode": "remote",
            "server_url": "https://original.example.com",
            "username": "originaluser",
        }
        config_path = self.config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(original_config, f)

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(self.temp_dir)
            success_message = manager.update_credentials(
                "newsecretuser", "newsecretpass"
            )

            # Success message should not contain sensitive information
            assert "newsecretuser" not in success_message
            assert "newsecretpass" not in success_message
            assert "successfully updated" in success_message.lower()


class TestCredentialRotationIntegration:
    """Test integration with existing remote mode functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(exist_ok=True)

    def test_integration_with_existing_credential_manager(self):
        """Test integration with ProjectCredentialManager."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        # Create initial remote config with encrypted credentials
        original_config = {
            "mode": "remote",
            "server_url": "https://original.example.com",
            "username": "originaluser",
            "created_at": "2024-01-01T00:00:00Z",
        }
        config_path = self.config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(original_config, f)

        # Store encrypted credentials using existing manager
        from code_indexer.remote.credential_manager import store_encrypted_credentials

        cred_manager = ProjectCredentialManager()
        encrypted_data = cred_manager.encrypt_credentials(
            "originaluser",
            "originalpass",
            "https://original.example.com",
            str(self.temp_dir),
        )
        store_encrypted_credentials(self.temp_dir, encrypted_data)

        # Test rotation
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            rotation_manager = CredentialRotationManager(self.temp_dir)
            rotation_manager.update_credentials("newuser", "newpass")

            # Verify new credentials can be loaded
            from code_indexer.remote.credential_manager import (
                load_encrypted_credentials,
            )

            encrypted_data = load_encrypted_credentials(self.temp_dir)
            decrypted = cred_manager.decrypt_credentials(
                encrypted_data,
                "newuser",
                str(self.temp_dir),
                "https://original.example.com",
            )
            assert decrypted.username == "newuser"
            assert decrypted.password == "newpass"

    def test_token_invalidation_after_credential_update(self):
        """Test that cached tokens are invalidated after credential update."""
        from code_indexer.remote.credential_rotation import CredentialRotationManager

        original_config = {
            "mode": "remote",
            "server_url": "https://original.example.com",
            "username": "originaluser",
        }
        config_path = self.config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(original_config, f)

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            with patch(
                "code_indexer.remote.credential_rotation.invalidate_cached_tokens"
            ) as mock_invalidate:
                manager = CredentialRotationManager(self.temp_dir)
                manager.update_credentials("newuser", "newpass")

                # Token cache should be invalidated
                mock_invalidate.assert_called_once_with(str(self.temp_dir))
