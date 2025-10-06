"""
Password hashing and verification for CIDX Server.

Uses bcrypt for secure password hashing with salt via pwdlib.
"""

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher


class PasswordManager:
    """
    Handles password hashing and verification using bcrypt via pwdlib.

    Provides secure password storage using bcrypt with automatic salt generation.
    Backward compatible with existing passlib-generated bcrypt hashes.
    """

    def __init__(self) -> None:
        """Initialize password hasher with bcrypt."""
        # Use BcryptHasher explicitly for backward compatibility with passlib hashes
        self.pwd_hash = PasswordHash((BcryptHasher(),))

    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt with salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        return str(self.pwd_hash.hash(password))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify plain password against hashed password.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from storage

        Returns:
            True if password matches, False otherwise
        """
        # PasswordHash.verify() uses (password, hash) order matching passlib CryptContext API
        return bool(self.pwd_hash.verify(plain_password, hashed_password))
