"""Project-specific credential encryption and management."""

import json
import secrets
import time
from pathlib import Path
from typing import NamedTuple

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes

from .exceptions import RemoteConfigurationError


class CredentialEncryptionError(RemoteConfigurationError):
    """Raised when credential encryption fails."""

    pass


class CredentialDecryptionError(RemoteConfigurationError):
    """Raised when credential decryption fails."""

    pass


class CredentialNotFoundError(RemoteConfigurationError):
    """Raised when stored credentials cannot be found."""

    pass


class InsecureCredentialStorageError(RemoteConfigurationError):
    """Raised when credential storage has insecure permissions."""

    pass


class DecryptedCredentials(NamedTuple):
    """Structured container for decrypted credential data."""

    username: str
    password: str
    server_url: str


class ProjectCredentialManager:
    """Manages project-specific credential encryption and storage.

    Uses PBKDF2 with SHA-256 for key derivation and AES-256-CBC for encryption.
    Each project generates unique encryption keys based on username, project path,
    and server URL combination to ensure credential isolation.
    """

    def __init__(self):
        """Initialize credential manager with security parameters."""
        self.iterations = 100_000  # PBKDF2 iterations for security
        self.key_length = 32  # AES-256 key length in bytes
        self.salt_length = 32  # Salt length for PBKDF2
        self.iv_length = 16  # AES block size for CBC mode

    def _derive_project_key(
        self, username: str, repo_path: str, server_url: str, salt: bytes
    ) -> bytes:
        """Derive project-specific encryption key using PBKDF2.

        Args:
            username: The username for authentication
            repo_path: The project repository path
            server_url: The remote server URL
            salt: Cryptographic salt for key derivation

        Returns:
            bytes: Derived encryption key
        """
        # Create unique input combining user, project, and server
        key_input = f"{username}:{repo_path}:{server_url}".encode("utf-8")

        # Use PBKDF2 with SHA-256 for key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=salt,
            iterations=self.iterations,
        )

        derived_key: bytes = kdf.derive(key_input)
        return derived_key

    def encrypt_credentials(
        self, username: str, password: str, server_url: str, repo_path: str
    ) -> bytes:
        """Encrypt credentials with project-specific key derivation.

        Args:
            username: The username for authentication
            password: The password to encrypt
            server_url: The remote server URL
            repo_path: The project repository path

        Returns:
            bytes: Encrypted credential data (salt + iv + ciphertext)

        Raises:
            CredentialEncryptionError: If encryption fails
        """
        try:
            # Generate cryptographically secure salt
            salt = secrets.token_bytes(self.salt_length)

            # Derive project-specific encryption key
            key = self._derive_project_key(username, repo_path, server_url, salt)

            # Create credential data to encrypt
            credential_data = {
                "username": username,
                "password": password,
                "server_url": server_url,
                "created_at": time.time(),
            }

            # Serialize to JSON bytes
            plaintext = json.dumps(credential_data).encode("utf-8")

            # Generate initialization vector
            iv = secrets.token_bytes(self.iv_length)

            # Encrypt using AES-256-CBC
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            encryptor = cipher.encryptor()

            # PKCS7 padding
            pad_length = 16 - (len(plaintext) % 16)
            padded_plaintext = plaintext + bytes([pad_length]) * pad_length

            # Encrypt the data
            ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

            # Combine salt, IV, and ciphertext for storage
            encrypted_data = salt + iv + ciphertext

            # Clear sensitive data from memory
            del key, plaintext, padded_plaintext

            result: bytes = encrypted_data
            return result

        except Exception as e:
            raise CredentialEncryptionError(f"Failed to encrypt credentials: {str(e)}")

    def decrypt_credentials(
        self, encrypted_data: bytes, username: str, repo_path: str, server_url: str
    ) -> DecryptedCredentials:
        """Decrypt credentials using project-specific key derivation.

        Args:
            encrypted_data: The encrypted credential data
            username: The username for key derivation
            repo_path: The project repository path
            server_url: The remote server URL

        Returns:
            DecryptedCredentials: The decrypted credential data

        Raises:
            CredentialDecryptionError: If decryption fails
        """
        try:
            # Validate minimum data length
            min_length = self.salt_length + self.iv_length
            if len(encrypted_data) < min_length:
                raise ValueError("Encrypted data too short")

            # Extract components from encrypted data
            salt = encrypted_data[: self.salt_length]
            iv = encrypted_data[self.salt_length : self.salt_length + self.iv_length]
            ciphertext = encrypted_data[self.salt_length + self.iv_length :]

            # Derive the same project-specific key
            key = self._derive_project_key(username, repo_path, server_url, salt)

            # Decrypt using AES-256-CBC
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            decryptor = cipher.decryptor()

            # Decrypt the data
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

            # Remove PKCS7 padding
            pad_length = padded_plaintext[-1]
            if pad_length > 16 or pad_length == 0:
                raise ValueError("Invalid padding")

            plaintext = padded_plaintext[:-pad_length]

            # Parse credential data
            credential_data = json.loads(plaintext.decode("utf-8"))

            # Clear sensitive data from memory
            del key, padded_plaintext, plaintext

            return DecryptedCredentials(
                username=credential_data["username"],
                password=credential_data["password"],
                server_url=credential_data["server_url"],
            )

        except Exception as e:
            raise CredentialDecryptionError(f"Failed to decrypt credentials: {str(e)}")


def store_encrypted_credentials(project_root: Path, encrypted_data: bytes) -> None:
    """Store encrypted credentials with secure file permissions.

    Args:
        project_root: The project root directory
        encrypted_data: The encrypted credential data to store

    Raises:
        OSError: If file operations fail
    """
    config_dir = project_root / ".code-indexer"
    config_dir.mkdir(mode=0o700, exist_ok=True)  # Directory accessible only to owner

    credentials_path = config_dir / ".creds"

    # Write encrypted data atomically
    temp_path = credentials_path.with_suffix(".tmp")
    try:
        with open(temp_path, "wb") as f:
            f.write(encrypted_data)

        # Set secure permissions (user read/write only)
        temp_path.chmod(0o600)

        # Atomic move to final location
        temp_path.rename(credentials_path)

    except Exception:
        # Clean up temporary file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def load_encrypted_credentials(project_root: Path) -> bytes:
    """Load encrypted credentials from secure storage.

    Automatically fixes insecure file permissions (non-600) if found.

    Args:
        project_root: The project root directory

    Returns:
        bytes: The encrypted credential data

    Raises:
        CredentialNotFoundError: If no credentials are found
    """
    credentials_path = project_root / ".code-indexer" / ".creds"

    if not credentials_path.exists():
        raise CredentialNotFoundError("No stored credentials found")

    # Verify and fix file permissions
    file_mode = credentials_path.stat().st_mode
    if file_mode & 0o077:  # Check if group/other permissions are set
        # Auto-fix insecure permissions instead of throwing error
        credentials_path.chmod(0o600)
        # Log the fix (could add logging here if needed)

    with open(credentials_path, "rb") as f:
        return f.read()
