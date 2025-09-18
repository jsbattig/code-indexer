"""Remote configuration management for CIDX."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .exceptions import RemoteConfigurationError
from .credential_manager import (
    ProjectCredentialManager,
    DecryptedCredentials,
    store_encrypted_credentials,
    load_encrypted_credentials,
)


def create_remote_configuration(
    project_root: Path, server_url: str, username: str, encrypted_credentials: str = ""
) -> None:
    """Create remote configuration files for CIDX.

    Args:
        project_root: The root directory of the project
        server_url: The remote server URL
        username: The username for authentication
        encrypted_credentials: The encrypted credentials data (empty initially, set later)

    Raises:
        RemoteConfigurationError: If configuration creation fails
    """
    try:
        # Create .code-indexer directory if it doesn't exist
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        # Create remote configuration with correct field name expected by mode detector
        remote_config = {
            "mode": "remote",
            "server_url": server_url,
            "username": username,
            "encrypted_credentials": encrypted_credentials,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        # Write remote configuration file
        remote_config_path = config_dir / ".remote-config"

        with open(remote_config_path, "w") as f:
            json.dump(remote_config, f, indent=2)

        # Set secure permissions (owner read/write only)
        os.chmod(remote_config_path, 0o600)

    except OSError as e:
        raise RemoteConfigurationError(
            f"Failed to create configuration directory: {str(e)}"
        )
    except json.JSONDecodeError as e:
        raise RemoteConfigurationError(f"Failed to write configuration file: {str(e)}")
    except Exception as e:
        raise RemoteConfigurationError(
            f"Unexpected error during configuration creation: {str(e)}"
        )


def load_remote_configuration(project_root: Path) -> dict[Any, Any]:
    """Load remote configuration from project directory.

    Args:
        project_root: The root directory of the project

    Returns:
        Dictionary containing remote configuration

    Raises:
        FileNotFoundError: If configuration file doesn't exist
        json.JSONDecodeError: If configuration file is corrupted
    """
    config_file = project_root / ".code-indexer" / ".remote-config"

    if not config_file.exists():
        raise FileNotFoundError(f"Remote configuration not found: {config_file}")

    with open(config_file, "r") as f:
        return cast(dict[Any, Any], json.load(f))


def encrypt_password(password: str) -> str:
    """Encrypt a password for secure storage.

    This is a placeholder implementation. In production, this would use
    proper encryption with a secure key management system.

    Args:
        password: The plain text password to encrypt

    Returns:
        str: The encrypted password
    """
    # TODO: Implement proper encryption
    # For now, this is a placeholder that just base64 encodes the password
    import base64

    return base64.b64encode(password.encode()).decode()


def decrypt_password(encrypted_password: str) -> str:
    """Decrypt a password from secure storage.

    This is a placeholder implementation. In production, this would use
    proper decryption with a secure key management system.

    Args:
        encrypted_password: The encrypted password to decrypt

    Returns:
        str: The decrypted password
    """
    # TODO: Implement proper decryption
    # For now, this is a placeholder that just base64 decodes the password
    import base64

    return base64.b64decode(encrypted_password.encode()).decode()


class RemoteConfig:
    """Remote configuration with encrypted credential management.

    Handles remote server configuration including encrypted credential storage
    and retrieval with project-specific encryption keys.
    """

    def __init__(self, project_root: Path):
        """Initialize remote configuration.

        Args:
            project_root: The project root directory

        Raises:
            RemoteConfigurationError: If configuration loading fails
        """
        self.project_root = project_root
        self.credential_manager = ProjectCredentialManager()
        self._config_data = self._load_config()

    def _load_config(self) -> dict:
        """Load remote configuration from file.

        Returns:
            dict: Configuration data

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is corrupted
        """
        config_file = self.project_root / ".code-indexer" / ".remote-config"

        if not config_file.exists():
            raise FileNotFoundError(f"Remote configuration not found: {config_file}")

        with open(config_file, "r") as f:
            config_data: dict[Any, Any] = json.load(f)
            return config_data

    @property
    def mode(self) -> str:
        """Get the configuration mode."""
        mode: str = self._config_data.get("mode", "remote")
        return mode

    @property
    def server_url(self) -> str:
        """Get the server URL."""
        server_url: str = self._config_data["server_url"]
        return server_url

    @property
    def username(self) -> str:
        """Get the username."""
        username: str = self._config_data["username"]
        return username

    @property
    def created_at(self) -> str:
        """Get the creation timestamp."""
        created_at: str = self._config_data.get("created_at", "")
        return created_at

    def store_credentials(self, password: str) -> None:
        """Store encrypted credentials securely.

        Args:
            password: The password to encrypt and store

        Raises:
            CredentialEncryptionError: If credential encryption fails
        """
        encrypted_data = self.credential_manager.encrypt_credentials(
            self.username, password, self.server_url, str(self.project_root)
        )

        # Store encrypted credentials in separate .creds file (legacy support)
        store_encrypted_credentials(self.project_root, encrypted_data)

        # Also store the encrypted credentials in the configuration file where mode detector expects it
        self._update_encrypted_credentials_in_config(encrypted_data)

    def get_decrypted_credentials(self) -> DecryptedCredentials:
        """Get decrypted credentials for API operations.

        Returns:
            DecryptedCredentials: The decrypted credential data

        Raises:
            CredentialNotFoundError: If no credentials are stored
            CredentialDecryptionError: If decryption fails
            InsecureCredentialStorageError: If stored credentials are insecure
        """
        encrypted_data = load_encrypted_credentials(self.project_root)

        return self.credential_manager.decrypt_credentials(
            encrypted_data, self.username, str(self.project_root), self.server_url
        )

    def has_stored_credentials(self) -> bool:
        """Check if credentials are stored.

        Returns:
            bool: True if credentials are stored, False otherwise
        """
        creds_file = self.project_root / ".code-indexer" / ".creds"
        return creds_file.exists()

    def clear_credentials(self) -> None:
        """Remove stored credentials securely.

        Removes the encrypted credential file from disk.
        """
        creds_file = self.project_root / ".code-indexer" / ".creds"
        if creds_file.exists():
            creds_file.unlink()

    def _update_encrypted_credentials_in_config(self, encrypted_data: bytes) -> None:
        """Update the encrypted_credentials field in the configuration file.

        Args:
            encrypted_data: The encrypted credential data to store

        Raises:
            RemoteConfigurationError: If configuration update fails
        """
        try:
            config_file = self.project_root / ".code-indexer" / ".remote-config"

            # Load current configuration
            with open(config_file, "r") as f:
                config_data = json.load(f)

            # Update the encrypted_credentials field with base64-encoded data
            import base64

            config_data["encrypted_credentials"] = base64.b64encode(
                encrypted_data
            ).decode()
            config_data["updated_at"] = datetime.utcnow().isoformat() + "Z"

            # Write updated configuration
            with open(config_file, "w") as f:
                json.dump(config_data, f, indent=2)

            # Set secure permissions
            os.chmod(config_file, 0o600)

            # Update internal config data
            self._config_data = config_data

        except (OSError, json.JSONDecodeError) as e:
            raise RemoteConfigurationError(
                f"Failed to update configuration with encrypted credentials: {e}"
            )
