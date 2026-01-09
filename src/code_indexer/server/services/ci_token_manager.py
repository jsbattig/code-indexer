"""
CI Token Manager Service.

Manages GitHub and GitLab API tokens with AES-256-CBC encryption.
Tokens are stored in ~/.cidx-server/ci_tokens.json with 0600 permissions.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import base64
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, cast

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

logger = logging.getLogger(__name__)

# Token validation patterns
GITHUB_TOKEN_PATTERN = re.compile(
    r"^(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,255})$"
)
# GitLab tokens can have periods in newer versioned formats (e.g., glpat-xxx.01.yyy)
GITLAB_TOKEN_PATTERN = re.compile(r"^glpat-[A-Za-z0-9_.-]{20,}$")

# Encryption constants
PBKDF2_ITERATIONS = 100000
AES_KEY_SIZE = 32  # 256 bits
AES_BLOCK_SIZE = 16  # 128 bits


class TokenValidationError(Exception):
    """Raised when token format validation fails."""

    pass


@dataclass
class TokenData:
    """Data structure for stored token information."""

    platform: str
    token: str
    base_url: Optional[str] = None


@dataclass
class TokenStatus:
    """Status information for a platform's token configuration."""

    platform: str
    configured: bool
    base_url: Optional[str] = None


class CITokenManager:
    """
    Manages CI/CD platform API tokens with encryption.

    Features:
    - AES-256-CBC encryption with PBKDF2 key derivation
    - Secure file permissions (0600)
    - Token format validation
    - Support for GitHub and GitLab tokens

    Supports both SQLite backend (Story #702) and JSON file storage (backward compatible).
    """

    def __init__(
        self,
        server_dir_path: Optional[str] = None,
        use_sqlite: bool = False,
        db_path: Optional[str] = None,
    ):
        """
        Initialize the token manager.

        Args:
            server_dir_path: Optional path to server directory.
                           Defaults to ~/.cidx-server
            use_sqlite: If True, use SQLite backend instead of JSON file (Story #702)
            db_path: Path to SQLite database file (required when use_sqlite=True)
        """
        self._use_sqlite = use_sqlite
        self._sqlite_backend: Optional[Any] = None

        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        self._encryption_key = self._derive_encryption_key()

        if use_sqlite:
            if db_path is None:
                raise ValueError("db_path is required when use_sqlite=True")
            from code_indexer.server.storage.sqlite_backends import (
                CITokensSqliteBackend,
            )

            self._sqlite_backend = CITokensSqliteBackend(db_path)
        else:
            # JSON file storage (backward compatible)
            self.token_file = self.server_dir / "ci_tokens.json"

    def _derive_encryption_key(self) -> bytes:
        """
        Derive encryption key using PBKDF2.

        Uses a machine-specific salt for key derivation.

        Returns:
            32-byte AES-256 key
        """
        # Use machine-specific data as salt
        # In production, this could be from a more secure source
        machine_id = os.uname().nodename.encode("utf-8")
        salt = hashlib.sha256(machine_id).digest()

        # Derive key using PBKDF2
        key = hashlib.pbkdf2_hmac(
            "sha256",
            b"cidx-token-encryption-key",
            salt,
            PBKDF2_ITERATIONS,
            dklen=AES_KEY_SIZE,
        )
        return key

    def _encrypt_token(self, token: str) -> str:
        """
        Encrypt token using AES-256-CBC.

        Args:
            token: Plaintext token to encrypt

        Returns:
            Base64-encoded encrypted token
        """
        # Generate random IV
        iv = os.urandom(AES_BLOCK_SIZE)

        # Pad the token to AES block size
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(token.encode("utf-8")) + padder.finalize()

        # Encrypt using AES-256-CBC
        cipher = Cipher(
            algorithms.AES(self._encryption_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        # Combine IV and encrypted data, encode as base64
        combined = iv + encrypted_data
        return base64.b64encode(combined).decode("utf-8")

    def _decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt token using AES-256-CBC.

        Args:
            encrypted_token: Base64-encoded encrypted token

        Returns:
            Plaintext token
        """
        # Decode from base64
        combined = base64.b64decode(encrypted_token.encode("utf-8"))

        # Extract IV and encrypted data
        iv = combined[:AES_BLOCK_SIZE]
        encrypted_data = combined[AES_BLOCK_SIZE:]

        # Decrypt using AES-256-CBC
        cipher = Cipher(
            algorithms.AES(self._encryption_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_data) + decryptor.finalize()

        # Unpad the data
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()

        result: str = data.decode("utf-8")
        return result

    def _validate_token_format(self, platform: str, token: str) -> None:
        """
        Validate token format for the given platform.

        Args:
            platform: Platform name (github or gitlab)
            token: Token to validate

        Raises:
            TokenValidationError: If token format is invalid
        """
        if platform == "github":
            if not GITHUB_TOKEN_PATTERN.match(token):
                raise TokenValidationError(
                    "Invalid GitHub token format. Expected format: "
                    "ghp_<36 chars> or github_pat_<22-255 chars>"
                )
        elif platform == "gitlab":
            if not GITLAB_TOKEN_PATTERN.match(token):
                raise TokenValidationError(
                    "Invalid GitLab token format. Expected format: " "glpat-<20+ chars>"
                )
        else:
            raise TokenValidationError(f"Unknown platform: {platform}")

    def _load_tokens(self) -> Dict[str, Any]:
        """
        Load tokens from storage file.

        Returns:
            Dictionary of stored token data
        """
        if not self.token_file.exists():
            return {}

        with open(self.token_file, "r") as f:
            return cast(Dict[str, Any], json.load(f))

    def _save_tokens(self, tokens: Dict) -> None:
        """
        Save tokens to storage file with secure permissions.

        Args:
            tokens: Dictionary of token data to save
        """
        # Ensure server directory exists
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Write tokens to file
        with open(self.token_file, "w") as f:
            json.dump(tokens, f, indent=2)

        # Set secure permissions (0600)
        os.chmod(self.token_file, 0o600)

    def save_token(
        self, platform: str, token: str, base_url: Optional[str] = None
    ) -> None:
        """
        Save and encrypt a CI/CD platform token.

        Args:
            platform: Platform name (github or gitlab)
            token: API token to save
            base_url: Optional custom base URL (for self-hosted instances)

        Raises:
            TokenValidationError: If token format is invalid
        """
        # Validate token format
        self._validate_token_format(platform, token)

        # Encrypt token
        encrypted_token = self._encrypt_token(token)

        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            self._sqlite_backend.save_token(platform, encrypted_token, base_url)
        else:
            # JSON file storage (backward compatible)
            # Load existing tokens
            tokens = self._load_tokens()

            # Update token data
            tokens[platform] = {"token": encrypted_token, "base_url": base_url}

            # Save to file with secure permissions
            self._save_tokens(tokens)

        logger.info(
            f"Saved encrypted token for platform: {platform}",
            extra={"correlation_id": get_correlation_id()},
        )

    def get_token(self, platform: str) -> Optional[TokenData]:
        """
        Retrieve and decrypt a platform token.

        Args:
            platform: Platform name (github or gitlab)

        Returns:
            TokenData if token exists, None otherwise
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            token_row = self._sqlite_backend.get_token(platform)
            if token_row is None:
                return None
            # Decrypt token
            decrypted_token = self._decrypt_token(token_row["encrypted_token"])
            return TokenData(
                platform=platform,
                token=decrypted_token,
                base_url=token_row.get("base_url"),
            )
        else:
            # JSON file storage (backward compatible)
            tokens = self._load_tokens()

            if platform not in tokens:
                return None

            token_data = tokens[platform]

            # Decrypt token
            decrypted_token = self._decrypt_token(token_data["token"])

            return TokenData(
                platform=platform,
                token=decrypted_token,
                base_url=token_data.get("base_url"),
            )

    def delete_token(self, platform: str) -> None:
        """
        Delete a platform token.

        Args:
            platform: Platform name (github or gitlab)
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            deleted = self._sqlite_backend.delete_token(platform)
            if deleted:
                logger.info(
                    f"Deleted token for platform: {platform}",
                    extra={"correlation_id": get_correlation_id()},
                )
        else:
            # JSON file storage (backward compatible)
            tokens = self._load_tokens()

            if platform in tokens:
                del tokens[platform]
                self._save_tokens(tokens)
                logger.info(
                    f"Deleted token for platform: {platform}",
                    extra={"correlation_id": get_correlation_id()},
                )

    def list_tokens(self) -> Dict[str, TokenStatus]:
        """
        List all platform token statuses.

        Returns:
            Dictionary mapping platform names to TokenStatus objects
        """
        # Known platforms
        platforms = ["github", "gitlab"]

        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            tokens = self._sqlite_backend.list_tokens()

            result = {}
            for platform in platforms:
                if platform in tokens:
                    result[platform] = TokenStatus(
                        platform=platform,
                        configured=True,
                        base_url=tokens[platform].get("base_url"),
                    )
                else:
                    result[platform] = TokenStatus(platform=platform, configured=False)

            return result
        else:
            # JSON file storage (backward compatible)
            tokens = self._load_tokens()

            result = {}
            for platform in platforms:
                if platform in tokens:
                    result[platform] = TokenStatus(
                        platform=platform,
                        configured=True,
                        base_url=tokens[platform].get("base_url"),
                    )
                else:
                    result[platform] = TokenStatus(platform=platform, configured=False)

            return result
