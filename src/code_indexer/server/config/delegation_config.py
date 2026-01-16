"""
Claude Delegation Configuration (Story #721).

Configuration dataclass and manager for Claude Server delegation settings.
Credentials are stored encrypted using AES-256-CBC.
"""

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

logger = logging.getLogger(__name__)

# Encryption constants (same as CITokenManager for consistency)
PBKDF2_ITERATIONS = 100000
AES_KEY_SIZE = 32  # 256 bits
AES_BLOCK_SIZE = 16  # 128 bits

# Default function repository alias
DEFAULT_FUNCTION_REPO_ALIAS = "claude-delegation-functions-global"


@dataclass
class ConnectivityResult:
    """Result of connectivity validation to Claude Server."""

    success: bool
    error_message: Optional[str] = None


@dataclass
class ClaudeDelegationConfig:
    """
    Configuration for Claude Delegation feature.

    Contains settings for connecting to Claude Server and locating
    delegation function definitions.
    """

    function_repo_alias: str = DEFAULT_FUNCTION_REPO_ALIAS
    claude_server_url: str = ""
    claude_server_username: str = ""
    claude_server_credential_type: Literal["password", "api_key"] = "password"
    claude_server_credential: str = ""  # Encrypted at rest
    skip_ssl_verify: bool = False  # Allow self-signed certificates for E2E testing
    cidx_callback_url: str = ""  # Story #720: URL that Claude Server uses to POST callbacks

    @property
    def is_configured(self) -> bool:
        """
        Check if the delegation configuration is complete.

        Returns True when URL, username, and credential are all set.
        """
        return bool(
            self.claude_server_url
            and self.claude_server_username
            and self.claude_server_credential
        )


class ClaudeDelegationManager:
    """
    Manages Claude Delegation configuration with credential encryption.

    Credentials are encrypted using AES-256-CBC before storage.
    """

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize the delegation manager.

        Args:
            server_dir_path: Optional path to server directory.
                           Defaults to ~/.cidx-server
        """
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        self.config_file = self.server_dir / "claude_delegation.json"
        self._encryption_key = self._derive_encryption_key()

    def _derive_encryption_key(self) -> bytes:
        """Derive encryption key using PBKDF2 with machine-specific salt."""
        # Use os.uname().nodename for consistency with CITokenManager
        machine_id = os.uname().nodename.encode("utf-8")
        salt = hashlib.sha256(machine_id).digest()

        return hashlib.pbkdf2_hmac(
            "sha256",
            b"cidx-delegation-encryption-key",
            salt,
            PBKDF2_ITERATIONS,
            dklen=AES_KEY_SIZE,
        )

    def _encrypt_credential(self, credential: str) -> str:
        """Encrypt credential using AES-256-CBC. Returns base64-encoded string."""
        if not credential:
            return ""

        iv = os.urandom(AES_BLOCK_SIZE)
        padder = padding.PKCS7(AES_BLOCK_SIZE * 8).padder()
        padded_data = padder.update(credential.encode("utf-8")) + padder.finalize()

        cipher = Cipher(
            algorithms.AES(self._encryption_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        return base64.b64encode(iv + encrypted_data).decode("utf-8")

    def _decrypt_credential(self, encrypted_credential: str) -> str:
        """Decrypt credential using AES-256-CBC. Returns empty string on failure."""
        if not encrypted_credential:
            return ""

        try:
            combined = base64.b64decode(encrypted_credential.encode("utf-8"))
            if len(combined) < AES_BLOCK_SIZE + 1:
                logger.warning("Encrypted credential too short, returning empty")
                return ""

            iv = combined[:AES_BLOCK_SIZE]
            encrypted_data = combined[AES_BLOCK_SIZE:]

            cipher = Cipher(
                algorithms.AES(self._encryption_key),
                modes.CBC(iv),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(encrypted_data) + decryptor.finalize()

            unpadder = padding.PKCS7(AES_BLOCK_SIZE * 8).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            return data.decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to decrypt credential: {e}")
            return ""

    def save_config(self, config: ClaudeDelegationConfig) -> None:
        """Save delegation configuration with encrypted credential."""
        self.server_dir.mkdir(parents=True, exist_ok=True)

        config_dict = asdict(config)
        config_dict["claude_server_credential"] = self._encrypt_credential(
            config.claude_server_credential
        )

        with open(self.config_file, "w") as f:
            json.dump(config_dict, f, indent=2)

        os.chmod(self.config_file, 0o600)
        logger.info("Saved Claude delegation configuration")

    def load_config(self) -> Optional[ClaudeDelegationConfig]:
        """Load delegation configuration, decrypting credential."""
        if not self.config_file.exists():
            return None

        # Check file permissions - warn if not 0600
        file_mode = self.config_file.stat().st_mode & 0o777
        if file_mode != 0o600:
            logger.warning(
                f"Insecure file permissions on {self.config_file}: "
                f"found {oct(file_mode)}, expected 0o600"
            )

        with open(self.config_file, "r") as f:
            config_dict = json.load(f)

        encrypted_credential = config_dict.get("claude_server_credential", "")
        config_dict["claude_server_credential"] = self._decrypt_credential(
            encrypted_credential
        )

        return ClaudeDelegationConfig(**config_dict)

    def validate_connectivity(
        self,
        url: str,
        username: str,
        credential: str,
        credential_type: str,
    ) -> ConnectivityResult:
        """
        Validate connectivity to Claude Server by attempting authentication.

        Args:
            url: Claude Server URL
            username: Username for authentication
            credential: Password or API key
            credential_type: 'password' or 'api_key'

        Returns:
            ConnectivityResult with success status and error message if failed
        """
        from urllib.parse import urlparse

        import httpx

        # Validate URL scheme (SSRF protection)
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https"):
            return ConnectivityResult(
                success=False,
                error_message=f"Invalid URL scheme: {parsed_url.scheme}. Only http/https allowed.",
            )

        # Validate credential type
        if credential_type not in ("password", "api_key"):
            return ConnectivityResult(
                success=False,
                error_message=f"Invalid credential type: {credential_type}. Must be 'password' or 'api_key'.",
            )

        login_url = f"{url.rstrip('/')}/auth/login"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    login_url,
                    json={"username": username, credential_type: credential},
                )

                if response.status_code == 200:
                    return ConnectivityResult(success=True)
                else:
                    return ConnectivityResult(
                        success=False,
                        error_message=f"Authentication failed: HTTP {response.status_code}",
                    )
        except httpx.ConnectError as e:
            # Log detailed error for debugging, return generic message to user
            logger.warning(f"Connection error to {url}: {e}")
            return ConnectivityResult(
                success=False,
                error_message="Connection failed: Unable to connect to server",
            )
        except httpx.TimeoutException:
            return ConnectivityResult(
                success=False,
                error_message="Connection timeout",
            )
        except Exception as e:
            # Log detailed error for debugging, return generic message to user
            # This prevents potential credential exposure in error messages
            logger.warning(f"Validation error for {url}: {e}")
            return ConnectivityResult(
                success=False,
                error_message="Validation failed: An unexpected error occurred",
            )
