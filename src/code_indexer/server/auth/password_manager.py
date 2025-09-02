"""
Password hashing and verification for CIDX Server.

Uses bcrypt for secure password hashing with salt.
"""

from passlib.context import CryptContext


class PasswordManager:
    """
    Handles password hashing and verification using bcrypt.

    Provides secure password storage using bcrypt with automatic salt generation.
    """

    def __init__(self):
        """Initialize password context with bcrypt."""
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt with salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        return str(self.pwd_context.hash(password))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify plain password against hashed password.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from storage

        Returns:
            True if password matches, False otherwise
        """
        return bool(self.pwd_context.verify(plain_password, hashed_password))
