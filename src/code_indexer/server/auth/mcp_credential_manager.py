"""MCP credential generation and validation manager."""

from code_indexer.server.middleware.correlation import get_correlation_id
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, cast

from .password_manager import PasswordManager


class MCPCredentialManager:
    """Manages MCP client credential generation and validation."""

    CLIENT_ID_PREFIX = "mcp_"
    CLIENT_SECRET_PREFIX = "mcp_sec_"
    CLIENT_ID_LENGTH = 16  # 16 bytes = 32 hex chars = 128-bit entropy
    CLIENT_SECRET_LENGTH = 32  # 32 bytes = 64 hex chars = 256-bit entropy

    def __init__(self, user_manager=None):
        """
        Initialize MCP credential manager.

        Args:
            user_manager: UserManager instance for storing credentials
        """
        self.user_manager = user_manager
        self.password_manager = PasswordManager()

    def generate_credential(self, user_id: str, name: Optional[str] = None) -> dict:
        """
        Generate a new MCP client credential and store it for the user.

        Args:
            user_id: Username to associate the credential with
            name: Optional name for the credential

        Returns:
            dict with credential data including plain secret (one-time)

        Raises:
            ValueError: If user not found
        """
        # Verify user exists
        if not self.user_manager:
            raise ValueError("UserManager not initialized")

        user = self.user_manager.get_user(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        # Generate client_id: mcp_{32 hex chars}
        random_bytes = secrets.token_hex(self.CLIENT_ID_LENGTH)
        client_id = f"{self.CLIENT_ID_PREFIX}{random_bytes}"

        # Generate client_secret: mcp_sec_{64 hex chars}
        secret_bytes = secrets.token_hex(self.CLIENT_SECRET_LENGTH)
        client_secret = f"{self.CLIENT_SECRET_PREFIX}{secret_bytes}"

        # Extract client_id_prefix for display (first 8 characters)
        client_id_prefix = client_id[:8]

        # Generate unique credential ID
        credential_id = str(uuid.uuid4())

        # Hash the secret for storage
        client_secret_hash = self.password_manager.hash_password(client_secret)

        # Timestamp
        created_at = datetime.now(timezone.utc).isoformat()

        # Store in user's mcp_credentials array
        self.user_manager.add_mcp_credential(
            username=user_id,
            credential_id=credential_id,
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            client_id_prefix=client_id_prefix,
            name=name,
            created_at=created_at,
        )

        # Return credential with plain secret (one-time only)
        return {
            "credential_id": credential_id,
            "client_id": client_id,
            "client_secret": client_secret,  # Plain text, shown only once
            "client_id_prefix": client_id_prefix,
            "name": name,
            "created_at": created_at,
        }

    def get_credentials(self, user_id: str) -> list:
        """
        Get all credentials for user (without secrets).

        Args:
            user_id: Username

        Returns:
            List of credential metadata (no secrets or hashes)
        """
        if not self.user_manager:
            return []

        user = self.user_manager.get_user(user_id)
        if not user:
            return []

        return cast(list[Any], self.user_manager.get_mcp_credentials(user_id))

    def get_credential_by_client_id(self, client_id: str) -> Optional[Tuple[str, dict]]:
        """
        Find credential by client_id across all users.

        Args:
            client_id: Client ID to search for

        Returns:
            Tuple of (user_id, credential) if found, None otherwise
        """
        if not self.user_manager:
            return None

        # Search all users
        users = self.user_manager.get_all_users()
        for user in users:
            users_data = self.user_manager._load_users()
            user_data = users_data.get(user.username)
            if not user_data:
                continue

            mcp_credentials = user_data.get("mcp_credentials", [])
            for cred in mcp_credentials:
                if cred.get("client_id") == client_id:
                    return (user.username, cred)

        return None

    def verify_credential(self, client_id: str, client_secret: str) -> Optional[str]:
        """
        Verify credentials, update last_used_at, return user_id or None.

        Args:
            client_id: Client ID to verify
            client_secret: Client secret to verify

        Returns:
            Username if valid, None otherwise
        """
        import logging

        logger = logging.getLogger(__name__)

        # Find credential by client_id
        result = self.get_credential_by_client_id(client_id)
        logger.debug(
            f"[verify_credential] client_id={client_id[:20]}... result={result is not None}",
            extra={"correlation_id": get_correlation_id()},
        )
        if not result:
            logger.debug(
                "[verify_credential] Credential not found for client_id",
                extra={"correlation_id": get_correlation_id()},
            )
            return None

        user_id, credential = result
        logger.debug(
            f"[verify_credential] Found credential for user_id={user_id}",
            extra={"correlation_id": get_correlation_id()},
        )

        # Verify secret against hash
        stored_hash = credential.get("client_secret_hash")
        if not stored_hash:
            return None

        if not self.password_manager.verify_password(client_secret, stored_hash):
            return None

        # Valid credential - update last_used_at
        credential_id = credential.get("credential_id")
        if credential_id:
            self.user_manager.update_mcp_credential_last_used(user_id, credential_id)

        return user_id

    def revoke_credential(self, user_id: str, credential_id: str) -> bool:
        """
        Revoke (delete) a credential.

        Args:
            user_id: Username
            credential_id: Credential ID to revoke

        Returns:
            True if revoked, False if not found
        """
        if not self.user_manager:
            return False

        return cast(
            bool, self.user_manager.delete_mcp_credential(user_id, credential_id)
        )
