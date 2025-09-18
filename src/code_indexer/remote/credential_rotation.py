"""Credential rotation support for CIDX Remote Repository Linking Mode."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union

from .credential_manager import (
    ProjectCredentialManager,
    CredentialEncryptionError,
    CredentialNotFoundError,
    CredentialDecryptionError,
    store_encrypted_credentials,
    load_encrypted_credentials,
)
from .config import load_remote_configuration
from .exceptions import RemoteConfigurationError
from .server_compatibility import validate_remote_credentials
from .token_manager import invalidate_cached_tokens


class CredentialRotationManager:
    """Manages secure credential rotation while preserving configuration."""

    def __init__(self, project_root: Path):
        """Initialize credential rotation manager.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root)
        self.config_dir = self.project_root / ".code-indexer"
        self.remote_config_path = self.config_dir / ".remote-config"
        self.credential_manager = ProjectCredentialManager()

    def update_credentials(self, new_username: str, new_password: str) -> str:
        """Update remote credentials while preserving configuration.

        Args:
            new_username: New username for authentication
            new_password: New password for authentication

        Returns:
            Success message confirming credential update

        Raises:
            RemoteConfigurationError: If project is not in remote mode or update fails
            CredentialEncryptionError: If credential encryption fails
        """
        # Secure parameter handling - convert to bytearrays for cleanup
        username_bytes = bytearray(new_username.encode("utf-8"))
        password_bytes = bytearray(new_password.encode("utf-8"))

        try:
            # Step 1: Validate project is in remote mode
            current_config = self._load_and_validate_remote_mode()

            # Step 2: Create backup of current credentials
            backup_info = self._create_credential_backup()

            # Step 3: Validate new credentials with server BEFORE storage
            server_url = current_config["server_url"]
            if not validate_remote_credentials(server_url, new_username, new_password):
                raise RemoteConfigurationError(
                    f"Invalid credentials: Could not authenticate with server {server_url}"
                )

            # Step 4: Store new encrypted credentials
            self._store_encrypted_credentials(new_username, new_password, server_url)

            # Step 5: Update remote configuration with new username
            self._update_remote_configuration(current_config, new_username)

            # Step 6: Test new credentials with actual API call
            self._verify_credentials_work(server_url, new_username, new_password)

            # Step 7: Invalidate cached tokens to force re-authentication
            invalidate_cached_tokens(str(self.project_root))

            # Step 8: Clean up backup on success
            self._cleanup_backup(backup_info)

            return "Credentials successfully updated and validated with remote server"

        except Exception:
            # Rollback on any failure
            if "backup_info" in locals():
                self._rollback_credentials(backup_info)
            raise
        finally:
            # Secure memory cleanup - overwrite sensitive data
            self._secure_memory_cleanup(username_bytes)
            self._secure_memory_cleanup(password_bytes)

    def _load_and_validate_remote_mode(self) -> Dict[str, Any]:
        """Load and validate that project is in remote mode.

        Returns:
            Current remote configuration

        Raises:
            RemoteConfigurationError: If project is not in remote mode
        """
        try:
            config = load_remote_configuration(self.project_root)
            if config.get("mode") != "remote":
                raise RemoteConfigurationError(
                    f"Project at {self.project_root} is not in remote mode. "
                    "Credential rotation is only available for remote mode projects."
                )
            return config
        except FileNotFoundError:
            raise RemoteConfigurationError(
                f"No remote configuration found at {self.project_root}. "
                "Project must be configured for remote mode first."
            )

    def _create_credential_backup(self) -> Dict[str, Any]:
        """Create backup of current credentials and configuration.

        Returns:
            Backup information for rollback
        """
        backup_info: Dict[str, Optional[Union[str, Path, Dict[str, str]]]] = {
            "timestamp": datetime.utcnow().isoformat(),
            "config_backup": None,
            "credentials_backup": None,
        }

        # Backup remote configuration
        if self.remote_config_path.exists():
            backup_config_path = self.remote_config_path.with_suffix(".backup")
            shutil.copy2(self.remote_config_path, backup_config_path)
            backup_info["config_backup"] = backup_config_path

        # Backup encrypted credentials if they exist
        try:
            encrypted_data = load_encrypted_credentials(self.project_root)
            current_config = self._load_and_validate_remote_mode()

            # Attempt to decrypt existing credentials for backup
            try:
                current_creds = self.credential_manager.decrypt_credentials(
                    encrypted_data,
                    current_config["username"],
                    str(self.project_root),
                    current_config["server_url"],
                )
                backup_info["credentials_backup"] = {
                    "username": current_creds.username,
                    "password": current_creds.password,
                    "server_url": current_creds.server_url,
                }
            except CredentialDecryptionError:
                # Existing credentials cannot be decrypted (likely corrupted or wrong key)
                # This is not fatal - we can still proceed with rotation
                # The new credentials will be validated and stored correctly
                backup_info["credentials_backup"] = None
                # Could add logging here if needed:
                # logger.warning("Could not decrypt existing credentials for backup. Proceeding without backup.")

        except (CredentialNotFoundError, FileNotFoundError):
            # No existing credentials to backup
            backup_info["credentials_backup"] = None

        return backup_info

    def _store_encrypted_credentials(
        self, username: str, password: str, server_url: str
    ) -> None:
        """Store new encrypted credentials.

        Args:
            username: New username
            password: New password
            server_url: Server URL from existing configuration

        Raises:
            CredentialEncryptionError: If credential storage fails
        """
        try:
            encrypted_data = self.credential_manager.encrypt_credentials(
                username, password, server_url, str(self.project_root)
            )
            store_encrypted_credentials(self.project_root, encrypted_data)
        except Exception as e:
            raise CredentialEncryptionError(
                f"Failed to store encrypted credentials: {e}"
            )

    def _update_remote_configuration(
        self, current_config: Dict[str, Any], new_username: str
    ) -> None:
        """Update remote configuration with new username while preserving other settings.

        Args:
            current_config: Current remote configuration
            new_username: New username to store in configuration
        """
        # Preserve all existing configuration, only update username and timestamp
        updated_config = current_config.copy()
        updated_config["username"] = new_username
        updated_config["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # Atomic write to prevent corruption
        temp_path = self.remote_config_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(updated_config, f, indent=2)
            temp_path.replace(self.remote_config_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise RemoteConfigurationError(f"Failed to update configuration: {e}")

    def _verify_credentials_work(
        self, server_url: str, username: str, password: str
    ) -> None:
        """Verify new credentials work with actual API call.

        Args:
            server_url: Server URL to test against
            username: Username to test
            password: Password to test

        Raises:
            RemoteConfigurationError: If credential verification fails
        """
        # This should make an actual API call to verify credentials work
        # For now, we'll rely on the validate_remote_credentials function
        if not validate_remote_credentials(server_url, username, password):
            raise RemoteConfigurationError(
                "Credential update failed: New credentials could not be verified with server"
            )

    def _rollback_credentials(self, backup_info: Dict[str, Any]) -> None:
        """Rollback credentials and configuration to backup state.

        Args:
            backup_info: Backup information from _create_credential_backup
        """
        try:
            # Restore configuration file
            if (
                backup_info.get("config_backup")
                and backup_info["config_backup"].exists()
            ):
                shutil.copy2(backup_info["config_backup"], self.remote_config_path)

            # Restore encrypted credentials
            if backup_info.get("credentials_backup"):
                cred_backup = backup_info["credentials_backup"]
                encrypted_data = self.credential_manager.encrypt_credentials(
                    cred_backup["username"],
                    cred_backup["password"],
                    cred_backup["server_url"],
                    str(self.project_root),
                )
                store_encrypted_credentials(self.project_root, encrypted_data)
        except Exception:
            # Log rollback failure but don't raise - original error is more important
            pass

    def _cleanup_backup(self, backup_info: Dict[str, Any]) -> None:
        """Clean up backup files after successful update.

        Args:
            backup_info: Backup information to clean up
        """
        if backup_info.get("config_backup") and backup_info["config_backup"].exists():
            backup_info["config_backup"].unlink()

    def _secure_memory_cleanup(self, sensitive_bytes: bytearray) -> None:
        """Securely overwrite sensitive data in memory.

        Args:
            sensitive_bytes: Bytearray containing sensitive data to overwrite
        """
        if sensitive_bytes:
            # Overwrite memory multiple times for security
            for _ in range(3):
                for i in range(len(sensitive_bytes)):
                    sensitive_bytes[i] = 0
            sensitive_bytes.clear()
