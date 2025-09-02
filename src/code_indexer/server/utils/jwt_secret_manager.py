"""
JWT Secret Key Management for CIDX Server.

Handles persistent storage of JWT secret keys to ensure tokens remain valid
across server restarts. Stores secret in ~/.cidx-server/.jwt_secret with
secure file permissions.
"""

import secrets
from pathlib import Path
from typing import Optional


class JWTSecretManager:
    """
    Manages persistent JWT secret keys.

    Ensures JWT secret keys are stored securely and persist across server restarts.
    Uses file system storage with appropriate security permissions.
    """

    def __init__(self, server_dir_path: Optional[str] = None):
        """
        Initialize JWT secret manager.

        Args:
            server_dir_path: Path to server directory (defaults to ~/.cidx-server)
        """
        if server_dir_path:
            self.server_dir = Path(server_dir_path)
        else:
            self.server_dir = Path.home() / ".cidx-server"

        self.secret_file_path = self.server_dir / ".jwt_secret"
        self._ensure_server_directory_exists()

    def _ensure_server_directory_exists(self):
        """Ensure server directory exists."""
        self.server_dir.mkdir(exist_ok=True)

    def get_or_create_secret(self) -> str:
        """
        Get existing JWT secret or create a new one if none exists.

        Priority order:
        1. Existing secret file
        2. JWT_SECRET_KEY environment variable
        3. Generate new random secret

        Returns:
            JWT secret key string
        """
        # Try to load existing secret from file
        if self.secret_file_path.exists():
            try:
                secret = self._load_secret_from_file()
                if secret:
                    return secret
            except Exception:
                # If file is corrupted, we'll create a new secret
                pass

        # Try to get secret from environment variable
        import os

        env_secret = os.environ.get("JWT_SECRET_KEY")
        if env_secret and env_secret.strip():
            self._save_secret_to_file(env_secret.strip())
            return env_secret.strip()

        # Generate new random secret
        secret = secrets.token_urlsafe(32)
        self._save_secret_to_file(secret)
        return secret

    def _load_secret_from_file(self) -> Optional[str]:
        """
        Load JWT secret from file.

        Returns:
            Secret string if successful, None if file doesn't exist or is empty
        """
        try:
            secret = self.secret_file_path.read_text().strip()
            return secret if secret else None
        except (FileNotFoundError, PermissionError):
            return None

    def _save_secret_to_file(self, secret: str):
        """
        Save JWT secret to file with secure permissions.

        Args:
            secret: JWT secret string to save
        """
        # Write secret to file
        self.secret_file_path.write_text(secret)

        # Set secure permissions (readable by owner only)
        self.secret_file_path.chmod(0o600)

    def rotate_secret(self) -> str:
        """
        Generate and save a new JWT secret (invalidates all existing tokens).

        Returns:
            New JWT secret key string
        """
        new_secret = secrets.token_urlsafe(32)
        self._save_secret_to_file(new_secret)
        return new_secret
