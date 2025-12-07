"""API Key generation and validation manager."""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from .password_manager import PasswordManager


class ApiKeyManager:
    """Manages API key generation and validation."""

    KEY_PREFIX = "cidx_sk_"
    KEY_LENGTH = 16  # 16 bytes = 32 hex chars = 128-bit entropy

    def __init__(self, user_manager=None):
        """
        Initialize API key manager.

        Args:
            user_manager: UserManager instance for storing API keys
        """
        self.user_manager = user_manager
        self.password_manager = PasswordManager()

    def generate_key(
        self, username: str, name: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Generate a new API key and store it for the user.

        Args:
            username: Username to associate the key with
            name: Optional name for the key

        Returns:
            Tuple of (raw_key, key_id)
        """
        # Generate random bytes and convert to hex
        random_bytes = secrets.token_hex(self.KEY_LENGTH)
        raw_key = f"{self.KEY_PREFIX}{random_bytes}"

        # Extract key prefix for display (first 12 chars: "cidx_sk_" + first 4 hex chars)
        key_prefix = raw_key[:12]

        # Generate unique key ID
        key_id = str(uuid.uuid4())

        # Hash the key for storage
        key_hash = self.password_manager.hash_password(raw_key)

        # Timestamp
        created_at = datetime.now(timezone.utc).isoformat()

        # Store in user's api_keys array
        if self.user_manager:
            self.user_manager.add_api_key(
                username=username,
                key_id=key_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name=name,
                created_at=created_at,
            )

        return raw_key, key_id

    def validate_key(self, raw_key: str, stored_hash: str) -> bool:
        """
        Validate a raw API key against stored hash.

        Args:
            raw_key: Raw API key from request
            stored_hash: Stored hash from database

        Returns:
            True if key is valid, False otherwise
        """
        result = self.password_manager.verify_password(raw_key, stored_hash)
        return bool(result)  # Explicit cast to satisfy mypy
