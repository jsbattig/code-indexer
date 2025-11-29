"""Encrypted credential storage for MCPB automatic login.

This module provides secure storage of username/password credentials
using Fernet symmetric encryption. Credentials are stored in ~/.mcpb/
with secure file permissions (600).
"""

import os
import json
from pathlib import Path
from typing import Tuple

from cryptography.fernet import Fernet, InvalidToken


def _get_mcpb_dir() -> Path:
    """Get the .mcpb directory path (allows testing with mocked home)."""
    return Path.home() / ".mcpb"


def _get_credentials_file() -> Path:
    """Get credentials file path."""
    return _get_mcpb_dir() / "credentials.enc"


def _get_encryption_key_file() -> Path:
    """Get encryption key file path."""
    return _get_mcpb_dir() / "encryption.key"


def save_credentials(username: str, password: str) -> None:
    """Save credentials encrypted to ~/.mcpb/credentials.enc.

    Generates encryption key if not exists. Stores both encrypted
    credentials and encryption key with secure 600 permissions.

    Args:
        username: Username for authentication
        password: Password for authentication

    Raises:
        ValueError: If username or password is empty
    """
    # Validate inputs
    if not username:
        raise ValueError("Username cannot be empty")
    if not password:
        raise ValueError("Password cannot be empty")

    # Get file paths
    mcpb_dir = _get_mcpb_dir()
    credentials_file = _get_credentials_file()
    encryption_key_file = _get_encryption_key_file()

    # Create ~/.mcpb directory if not exists
    mcpb_dir.mkdir(parents=True, exist_ok=True)

    # Generate or load encryption key
    if encryption_key_file.exists():
        # Load existing key
        with open(encryption_key_file, "rb") as f:
            key = f.read()
    else:
        # Generate new key
        key = Fernet.generate_key()

        # Write key with secure permissions
        with open(encryption_key_file, "wb") as f:
            f.write(key)

        # Set secure permissions (owner read/write only)
        os.chmod(encryption_key_file, 0o600)

    # Encrypt credentials
    fernet = Fernet(key)
    credentials_data = json.dumps({"username": username, "password": password})
    encrypted_data = fernet.encrypt(credentials_data.encode("utf-8"))

    # Write encrypted credentials with secure permissions
    with open(credentials_file, "wb") as f:
        f.write(encrypted_data)

    # Set secure permissions
    os.chmod(credentials_file, 0o600)


def load_credentials() -> Tuple[str, str]:
    """Load and decrypt credentials from ~/.mcpb/credentials.enc.

    Returns:
        Tuple of (username, password)

    Raises:
        FileNotFoundError: If credential files don't exist
        Exception: If decryption fails (cryptography.fernet.InvalidToken)
    """
    # Get file paths
    credentials_file = _get_credentials_file()
    encryption_key_file = _get_encryption_key_file()

    # Check if files exist
    if not encryption_key_file.exists() or not credentials_file.exists():
        raise FileNotFoundError(
            "Credential files not found. Run --setup-credentials to configure automatic login."
        )

    # Load encryption key
    with open(encryption_key_file, "rb") as f:
        key = f.read()

    # Load encrypted credentials
    with open(credentials_file, "rb") as f:
        encrypted_data = f.read()

    # Decrypt credentials
    try:
        fernet = Fernet(key)
        decrypted_data = fernet.decrypt(encrypted_data)
        credentials = json.loads(decrypted_data.decode("utf-8"))

        return credentials["username"], credentials["password"]

    except InvalidToken as e:
        raise Exception(f"Failed to decrypt credentials: {str(e)}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise Exception(f"Invalid credential file format: {str(e)}") from e


def credentials_exist() -> bool:
    """Check if encrypted credentials exist.

    Returns:
        True if both credentials.enc and encryption.key exist, False otherwise
    """
    credentials_file = _get_credentials_file()
    encryption_key_file = _get_encryption_key_file()
    return encryption_key_file.exists() and credentials_file.exists()


def delete_credentials() -> None:
    """Delete encrypted credentials and encryption key.

    Removes both ~/.mcpb/credentials.enc and ~/.mcpb/encryption.key if they exist.
    Does not raise error if files don't exist.
    """
    credentials_file = _get_credentials_file()
    encryption_key_file = _get_encryption_key_file()

    # Remove credentials file if exists
    if credentials_file.exists():
        credentials_file.unlink()

    # Remove encryption key if exists
    if encryption_key_file.exists():
        encryption_key_file.unlink()
