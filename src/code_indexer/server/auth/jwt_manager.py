"""
JWT token management for CIDX Server authentication.

Handles JWT token creation, validation, expiration, and activity-based extension.
Uses 10-minute default expiration with configurable settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError


class TokenExpiredError(Exception):
    """Raised when a JWT token has expired."""

    pass


class InvalidTokenError(Exception):
    """Raised when a JWT token is invalid or malformed."""

    pass


class JWTManager:
    """
    Manages JWT tokens for user authentication.

    Provides token creation, validation, and expiration extension functionality.
    Tokens extend session on API activity (not fixed expiration).
    """

    def __init__(
        self,
        secret_key: str,
        token_expiration_minutes: int = 10,
        algorithm: str = "HS256",
    ):
        """
        Initialize JWT manager.

        Args:
            secret_key: Secret key for JWT signing
            token_expiration_minutes: Token expiration time in minutes (default: 10)
            algorithm: JWT algorithm (default: HS256)
        """
        self.secret_key = secret_key
        self.token_expiration_minutes = token_expiration_minutes
        self.algorithm = algorithm

    def create_token(self, user_data: Dict[str, Any]) -> str:
        """
        Create JWT token for user.

        Args:
            user_data: User information to encode in token

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.token_expiration_minutes)

        # Create JWT payload with high-precision timestamps
        payload = {
            "username": user_data["username"],
            "role": user_data["role"],
            "created_at": user_data.get("created_at"),
            "exp": expire.timestamp(),  # Use timestamp() for microsecond precision
            "iat": now.timestamp(),  # Use timestamp() for microsecond precision
        }

        # Create and return JWT token
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return str(token)

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token and return decoded payload.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid or malformed
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return dict(payload)

        except ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")

        except JWTError as e:
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def extend_token_expiration(self, token: str) -> str:
        """
        Extend token expiration time for active sessions.

        Args:
            token: Current JWT token

        Returns:
            New JWT token with extended expiration

        Raises:
            TokenExpiredError: If current token has expired
            InvalidTokenError: If current token is invalid
        """
        # Validate current token first
        payload = self.validate_token(token)

        # Create new token with extended expiration using high-precision timestamps
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.token_expiration_minutes)

        # Preserve original claims but update timestamps with microsecond precision
        new_payload = {
            "username": payload["username"],
            "role": payload["role"],
            "created_at": payload.get("created_at"),
            "exp": expire.timestamp(),  # Use timestamp() for microsecond precision
            "iat": now.timestamp(),  # Use timestamp() for microsecond precision
        }

        # Create and return new token
        new_token = jwt.encode(new_payload, self.secret_key, algorithm=self.algorithm)
        return str(new_token)
