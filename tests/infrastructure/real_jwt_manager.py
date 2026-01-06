"""Real JWT Token Manager for Testing.

Provides real JWT token generation, validation, and management functionality
to replace all JWT-related mocks in Foundation #1 compliance.
"""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, cast
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dataclasses import dataclass


@dataclass
class RealTokenPair:
    """Real JWT token pair with actual cryptographic signatures."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def is_access_token_expired(self) -> bool:
        """Check if access token is expired based on creation time."""
        expiry_time = self.created_at + timedelta(seconds=self.expires_in)
        return datetime.now(timezone.utc) > expiry_time

    def is_access_token_near_expiry(self, threshold_seconds: int = 60) -> bool:
        """Check if access token is near expiry."""
        expiry_time = self.created_at + timedelta(seconds=self.expires_in)
        threshold_time = datetime.now(timezone.utc) + timedelta(
            seconds=threshold_seconds
        )
        return threshold_time > expiry_time


class RealJWTManager:
    """Real JWT manager using actual RSA cryptography.

    This class provides real JWT operations using RSA key pairs and
    standard JWT libraries. No mocks are used - all operations are authentic.
    """

    def __init__(self):
        """Initialize with real RSA key pair generation."""
        # Generate real RSA key pair
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.public_key = self.private_key.public_key()

        # Convert to PEM format for JWT operations
        self.private_key_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # JWT configuration
        self.algorithm = "RS256"
        self.access_token_expiry_minutes = 10
        self.refresh_token_expiry_days = 30

        # Token storage for validation
        self.issued_tokens: Dict[str, Dict[str, Any]] = {}

    def create_test_user_token(
        self,
        username: str,
        user_id: Optional[str] = None,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> RealTokenPair:
        """Create real JWT tokens for test user.

        Args:
            username: Username for token
            user_id: User ID (defaults to username)
            additional_claims: Additional JWT claims to include

        Returns:
            RealTokenPair with access and refresh tokens
        """
        if user_id is None:
            user_id = username

        # Create access token with real JWT signing
        access_token = self._create_access_token(
            username, user_id, additional_claims or {}
        )
        refresh_token = self._create_refresh_token(username, user_id)

        return RealTokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expiry_minutes * 60,
        )

    def _create_access_token(
        self, username: str, user_id: str, additional_claims: Dict[str, Any]
    ) -> str:
        """Create real access token with RSA signature.

        Args:
            username: Username for token
            user_id: User ID for token
            additional_claims: Additional claims to include

        Returns:
            Signed JWT access token
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "username": username,
            "iat": now,
            "exp": now + timedelta(minutes=self.access_token_expiry_minutes),
            "type": "access",
            **additional_claims,
        }

        token = jwt.encode(payload, self.private_key_pem, algorithm=self.algorithm)

        # Store token metadata for validation
        self.issued_tokens[token] = {
            "payload": payload,
            "created_at": now,
            "token_type": "access",
        }

        return token

    def _create_refresh_token(self, username: str, user_id: str) -> str:
        """Create real refresh token with RSA signature.

        Args:
            username: Username for token
            user_id: User ID for token

        Returns:
            Signed JWT refresh token
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "username": username,
            "iat": now,
            "exp": now + timedelta(days=self.refresh_token_expiry_days),
            "type": "refresh",
        }

        token = jwt.encode(payload, self.private_key_pem, algorithm=self.algorithm)

        # Store token metadata for validation
        self.issued_tokens[token] = {
            "payload": payload,
            "created_at": now,
            "token_type": "refresh",
        }

        return token

    def decode_and_verify_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify JWT token using real cryptographic validation.

        Args:
            token: JWT token to verify

        Returns:
            Decoded token payload

        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid
            ValueError: If token was not issued by this manager
        """
        # Verify token signature and decode
        payload = cast(
            dict[str, Any], jwt.decode(token, self.public_key_pem, algorithms=[self.algorithm])
        )

        # Verify token was issued by this manager
        if token not in self.issued_tokens:
            raise ValueError("Token was not issued by this JWT manager")

        return payload

    def is_token_expired(self, token: str) -> bool:
        """Check if JWT token is expired using real time validation.

        Args:
            token: JWT token to check

        Returns:
            True if token is expired, False otherwise
        """
        try:
            self.decode_and_verify_token(token)
            return False
        except jwt.ExpiredSignatureError:
            return True
        except (jwt.InvalidTokenError, ValueError):
            # Invalid tokens are considered expired
            return True

    def is_token_near_expiry(self, token: str, threshold_seconds: int = 60) -> bool:
        """Check if JWT token is near expiry using real time validation.

        Args:
            token: JWT token to check
            threshold_seconds: Seconds before expiry to consider "near"

        Returns:
            True if token expires within threshold, False otherwise
        """
        try:
            payload = self.decode_and_verify_token(token)
            exp_timestamp = payload["exp"]

            # Convert timestamp to datetime
            if isinstance(exp_timestamp, datetime):
                exp_time = exp_timestamp
            else:
                exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

            threshold_time = datetime.now(timezone.utc) + timedelta(
                seconds=threshold_seconds
            )
            return threshold_time > exp_time
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError, KeyError):
            # Invalid or expired tokens are considered near expiry
            return True

    def get_token_expiry_time(self, token: str) -> Optional[datetime]:
        """Get token expiry time using real JWT decoding.

        Args:
            token: JWT token

        Returns:
            Token expiry time or None if invalid
        """
        try:
            payload = self.decode_and_verify_token(token)
            exp_timestamp = payload["exp"]

            if isinstance(exp_timestamp, datetime):
                return exp_timestamp
            else:
                return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError, KeyError):
            return None

    def get_token_username(self, token: str) -> Optional[str]:
        """Extract username from JWT token.

        Args:
            token: JWT token

        Returns:
            Username from token or None if invalid
        """
        try:
            payload = self.decode_and_verify_token(token)
            return payload.get("username")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
            return None

    def refresh_access_token(self, refresh_token: str) -> RealTokenPair:
        """Create new access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token pair with fresh access token

        Raises:
            jwt.ExpiredSignatureError: If refresh token is expired
            jwt.InvalidTokenError: If refresh token is invalid
            ValueError: If refresh token was not issued by this manager
        """
        # Verify refresh token
        payload = self.decode_and_verify_token(refresh_token)

        if payload.get("type") != "refresh":
            raise ValueError("Token is not a refresh token")

        username = payload["username"]
        user_id = payload["sub"]

        # Create new token pair
        return self.create_test_user_token(username, user_id)

    def create_expired_token(self, username: str, user_id: Optional[str] = None) -> str:
        """Create an expired JWT token for testing expiry handling.

        Args:
            username: Username for token
            user_id: User ID (defaults to username)

        Returns:
            Expired JWT token
        """
        if user_id is None:
            user_id = username

        # Create token that expired 1 minute ago
        now = datetime.now(timezone.utc)
        past_time = now - timedelta(minutes=1)
        payload = {
            "sub": user_id,
            "username": username,
            "iat": past_time - timedelta(minutes=10),  # Issued 11 minutes ago
            "exp": past_time,  # Expired 1 minute ago
            "type": "access",
        }

        token = jwt.encode(payload, self.private_key_pem, algorithm=self.algorithm)

        # Store token metadata
        self.issued_tokens[token] = {
            "payload": payload,
            "created_at": past_time - timedelta(minutes=10),
            "token_type": "access",
        }

        return token

    def create_near_expiry_token(
        self, username: str, user_id: Optional[str] = None, expiry_seconds: int = 30
    ) -> str:
        """Create JWT token that expires soon for testing near-expiry handling.

        Args:
            username: Username for token
            user_id: User ID (defaults to username)
            expiry_seconds: Seconds until expiry

        Returns:
            JWT token that expires soon
        """
        if user_id is None:
            user_id = username

        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "username": username,
            "iat": now,
            "exp": now + timedelta(seconds=expiry_seconds),
            "type": "access",
        }

        token = jwt.encode(payload, self.private_key_pem, algorithm=self.algorithm)

        # Store token metadata
        self.issued_tokens[token] = {
            "payload": payload,
            "created_at": now,
            "token_type": "access",
        }

        return token

    def create_malformed_token(self) -> str:
        """Create a malformed JWT token for testing error handling.

        Returns:
            Malformed token string
        """
        return "invalid.jwt.token.format"

    def invalidate_token(self, token: str):
        """Invalidate a token by removing it from issued tokens.

        Args:
            token: Token to invalidate
        """
        self.issued_tokens.pop(token, None)

    def cleanup_expired_tokens(self):
        """Clean up expired tokens from storage."""
        current_time = datetime.now(timezone.utc)
        expired_tokens = []

        for token, token_data in self.issued_tokens.items():
            try:
                payload = token_data["payload"]
                exp_time = payload["exp"]
                if isinstance(exp_time, datetime):
                    if current_time > exp_time:
                        expired_tokens.append(token)
                else:
                    exp_datetime = datetime.fromtimestamp(exp_time, tz=timezone.utc)
                    if current_time > exp_datetime:
                        expired_tokens.append(token)
            except (KeyError, ValueError, TypeError):
                # Invalid token data, mark for removal
                expired_tokens.append(token)

        for token in expired_tokens:
            self.issued_tokens.pop(token, None)

    def get_token_count(self) -> int:
        """Get count of issued tokens.

        Returns:
            Number of issued tokens
        """
        return len(self.issued_tokens)

    def clear_all_tokens(self):
        """Clear all issued tokens - for test cleanup."""
        self.issued_tokens.clear()


# Test helper functions


def create_real_jwt_manager() -> RealJWTManager:
    """Create a new real JWT manager instance.

    Returns:
        RealJWTManager instance
    """
    return RealJWTManager()


def create_test_token_pair(
    username: str = "testuser", user_id: Optional[str] = None
) -> Tuple[RealJWTManager, RealTokenPair]:
    """Create JWT manager and test token pair.

    Args:
        username: Username for tokens
        user_id: User ID (defaults to username)

    Returns:
        Tuple of (JWT manager, token pair)
    """
    jwt_manager = create_real_jwt_manager()
    token_pair = jwt_manager.create_test_user_token(username, user_id)
    return jwt_manager, token_pair
