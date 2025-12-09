"""
SSH Key Generator Service.

Generates SSH key pairs with security validation and proper permissions.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class InvalidKeyNameError(Exception):
    """Raised when key name contains invalid characters."""

    pass


class KeyAlreadyExistsError(Exception):
    """Raised when attempting to create a key that already exists."""

    pass


class KeyGenerationError(Exception):
    """Raised when ssh-keygen fails to generate a key."""

    pass


@dataclass
class GeneratedKey:
    """Result of SSH key generation."""

    name: str
    private_path: Path
    public_path: Path
    public_key: str
    fingerprint: str
    key_type: str


class SSHKeyGenerator:
    """
    Generator for SSH key pairs.

    Handles key generation with security validation and proper file permissions.
    """

    def __init__(self, ssh_dir: Optional[Path] = None):
        """
        Initialize the SSH key generator.

        Args:
            ssh_dir: Directory for SSH keys. Defaults to ~/.ssh/
        """
        if ssh_dir is None:
            ssh_dir = Path.home() / ".ssh"
        self.ssh_dir = ssh_dir

    def generate_key(
        self,
        key_name: str,
        key_type: str = "ed25519",
        bits: Optional[int] = None,
        email: Optional[str] = None,
    ) -> GeneratedKey:
        """
        Generate a new SSH key pair.

        Args:
            key_name: Name for the key (used as filename)
            key_type: Type of key (ed25519, rsa, dsa, ecdsa)
            bits: Key size in bits (only for rsa, dsa)
            email: Comment/email to include in the key

        Returns:
            GeneratedKey with paths, public key content, and fingerprint

        Raises:
            InvalidKeyNameError: If key name contains invalid characters
            KeyAlreadyExistsError: If key already exists
            KeyGenerationError: If ssh-keygen fails
        """
        # Validate key name (security critical)
        self._validate_key_name(key_name)

        # Ensure SSH directory exists with correct permissions
        if not self.ssh_dir.exists():
            self.ssh_dir.mkdir(parents=True, mode=0o700)

        key_path = self.ssh_dir / key_name
        pub_path = self.ssh_dir / f"{key_name}.pub"

        # Check if key already exists
        if key_path.exists() or pub_path.exists():
            raise KeyAlreadyExistsError(f"Key already exists: {key_name}")

        # Build ssh-keygen command
        command = ["ssh-keygen", "-t", key_type, "-f", str(key_path), "-N", ""]

        if bits and key_type in ["rsa", "dsa"]:
            command.extend(["-b", str(bits)])

        if email:
            command.extend(["-C", email])

        # Generate key
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise KeyGenerationError(result.stderr)

        # Set correct permissions
        os.chmod(key_path, 0o600)
        os.chmod(pub_path, 0o644)

        # Read public key
        public_key = pub_path.read_text().strip()

        # Get fingerprint
        fingerprint_result = subprocess.run(
            ["ssh-keygen", "-lf", str(key_path)],
            capture_output=True,
            text=True,
        )
        fingerprint = fingerprint_result.stdout.strip()

        return GeneratedKey(
            name=key_name,
            private_path=key_path,
            public_path=pub_path,
            public_key=public_key,
            fingerprint=fingerprint,
            key_type=key_type,
        )

    def _validate_key_name(self, key_name: str) -> None:
        """
        Validate key name for security.

        Args:
            key_name: Key name to validate

        Raises:
            InvalidKeyNameError: If key name is invalid
        """
        # Check for path traversal
        if "/" in key_name or ".." in key_name:
            raise InvalidKeyNameError("Key name contains invalid characters")

        # Check for command injection
        if ";" in key_name:
            raise InvalidKeyNameError("Key name contains invalid characters")

        # Check for dash prefix (could be interpreted as command flag)
        if key_name.startswith("-"):
            raise InvalidKeyNameError("Key name cannot start with dash")

        # Check length
        if len(key_name) > 255:
            raise InvalidKeyNameError("Key name too long")
