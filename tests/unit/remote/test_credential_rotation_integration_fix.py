"""Integration test for credential rotation with padding fix."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from code_indexer.remote.credential_rotation import CredentialRotationManager
from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    store_encrypted_credentials,
)


class TestCredentialRotationIntegrationFix:
    """Test real-world scenario where credentials were created with different parameters."""

    def test_real_world_scenario_username_changed_in_config(self):
        """
        Test scenario: User manually edited .remote-config to change username
        but didn't update encrypted credentials, causing padding error.
        """
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        # Step 1: Create initial configuration with original username
        original_config = {
            "mode": "remote",
            "server_url": "https://example.com",
            "username": "original_user",
            "created_at": "2024-01-01T00:00:00Z",
        }

        # Step 2: Create encrypted credentials with original username
        credential_manager = ProjectCredentialManager()
        encrypted_creds = credential_manager.encrypt_credentials(
            "original_user",
            "original_pass",
            "https://example.com",
            str(temp_dir),
        )
        store_encrypted_credentials(temp_dir, encrypted_creds)

        # Step 3: User manually edits config to change username (simulating the problem)
        modified_config = original_config.copy()
        modified_config["username"] = "different_user"  # This breaks decryption!

        config_path = config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(modified_config, f)

        # Step 4: Now try credential rotation - this would fail before the fix
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(temp_dir)

            # This should succeed despite the username mismatch in config
            result = manager.update_credentials("new_user", "new_pass")

            assert "successfully updated" in result.lower()

            # Verify new credentials are stored correctly
            with open(config_path, "r") as f:
                final_config = json.load(f)
            assert final_config["username"] == "new_user"

    def test_real_world_scenario_server_url_mismatch(self):
        """
        Test scenario: Credentials were created with one server URL,
        but config has different server URL (e.g., https vs http).
        """
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        # Create config with https URL
        config = {
            "mode": "remote",
            "server_url": "https://example.com",
            "username": "testuser",
            "created_at": "2024-01-01T00:00:00Z",
        }
        config_path = config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(config, f)

        # But credentials were created with http URL (no 's')
        credential_manager = ProjectCredentialManager()
        encrypted_creds = credential_manager.encrypt_credentials(
            "testuser",
            "testpass",
            "http://example.com",  # Different protocol!
            str(temp_dir),
        )
        store_encrypted_credentials(temp_dir, encrypted_creds)

        # Try credential rotation - should work despite mismatch
        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            manager = CredentialRotationManager(temp_dir)

            # Should succeed and create new properly encrypted credentials
            result = manager.update_credentials("newuser", "newpass")

            assert "successfully updated" in result.lower()

    def test_real_world_scenario_path_normalization_difference(self):
        """
        Test scenario: Credentials created with path like '/home/user/project'
        but rotation called with '/home/user/project/' (trailing slash).
        """
        # Use a real temporary directory path
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        config = {
            "mode": "remote",
            "server_url": "https://example.com",
            "username": "testuser",
            "created_at": "2024-01-01T00:00:00Z",
        }
        config_path = config_dir / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Create credentials with path WITHOUT trailing slash
        credential_manager = ProjectCredentialManager()
        encrypted_creds = credential_manager.encrypt_credentials(
            "testuser",
            "testpass",
            "https://example.com",
            str(temp_dir).rstrip("/"),  # Ensure no trailing slash
        )
        store_encrypted_credentials(temp_dir, encrypted_creds)

        # Now attempt rotation with path WITH trailing slash
        temp_dir_with_slash = Path(str(temp_dir) + "/")

        with patch(
            "code_indexer.remote.credential_rotation.validate_remote_credentials"
        ) as mock_validate:
            mock_validate.return_value = True

            # Create manager with slightly different path
            manager = CredentialRotationManager(temp_dir_with_slash)

            # Should still work despite path difference
            result = manager.update_credentials("newuser", "newpass")

            assert "successfully updated" in result.lower()
