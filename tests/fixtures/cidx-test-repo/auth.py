"""
Authentication and authorization utilities for the CIDX test application.

This module provides JWT-based authentication, password hashing,
role-based access control, and user session management.
"""

import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from enum import Enum

import jwt
from passlib.context import CryptContext

from database import DatabaseManager


logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User role enumeration with privilege levels."""

    ADMIN = "admin"
    POWER_USER = "power_user"
    NORMAL_USER = "normal_user"

    @property
    def privilege_level(self) -> int:
        """Get numeric privilege level for role comparison."""
        levels = {"admin": 3, "power_user": 2, "normal_user": 1}
        return levels.get(self.value, 0)


class AuthenticationError(Exception):
    """Custom exception for authentication-related errors."""

    pass


class AuthorizationError(Exception):
    """Custom exception for authorization-related errors."""

    pass


class TokenManager:
    """JWT token management functionality."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        Initialize token manager.

        Args:
            secret_key: Secret key for token signing
            algorithm: JWT signing algorithm
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.logger = logging.getLogger(f"{__name__}.TokenManager")

    def generate_token(
        self, user_info: Dict[str, Any], expires_minutes: int = 60
    ) -> str:
        """
        Generate JWT token for authenticated user.

        Args:
            user_info: User information dictionary
            expires_minutes: Token expiration time in minutes

        Returns:
            Encoded JWT token string
        """
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=expires_minutes)

        payload = {
            "sub": user_info["username"],
            "user_id": user_info["user_id"],
            "role": user_info["role"],
            "iat": now.timestamp(),
            "exp": expiry.timestamp(),
            "jti": self._generate_jti(),
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        self.logger.debug(f"Generated token for user {user_info['username']}")
        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Additional validation
            required_fields = ["sub", "user_id", "role", "exp"]
            for field in required_fields:
                if field not in payload:
                    raise AuthenticationError(f"Missing required field: {field}")

            # Check expiration
            exp_timestamp = payload["exp"]
            if datetime.now(timezone.utc).timestamp() > exp_timestamp:
                raise AuthenticationError("Token expired")

            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")
        except Exception as e:
            self.logger.error(f"Token validation error: {e}")
            raise AuthenticationError("Token validation failed")

    def refresh_token(
        self, current_payload: Dict[str, Any], expires_minutes: int = 60
    ) -> str:
        """
        Refresh JWT token with new expiration.

        Args:
            current_payload: Current token payload
            expires_minutes: New expiration time in minutes

        Returns:
            New JWT token
        """
        user_info = {
            "username": current_payload["sub"],
            "user_id": current_payload["user_id"],
            "role": current_payload["role"],
        }

        return self.generate_token(user_info, expires_minutes)

    def _generate_jti(self) -> str:
        """Generate unique token identifier."""
        return secrets.token_hex(16)


class PasswordManager:
    """Password hashing and verification functionality."""

    def __init__(self):
        """Initialize password manager with bcrypt context."""
        self.pwd_context = CryptContext(
            schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12
        )
        self.logger = logging.getLogger(f"{__name__}.PasswordManager")

    def hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        if not password:
            raise ValueError("Password cannot be empty")

        hashed = self.pwd_context.hash(password)
        self.logger.debug("Password hashed successfully")
        return hashed

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """
        Verify password against hash.

        Args:
            password: Plain text password
            hashed_password: Previously hashed password

        Returns:
            True if password matches, False otherwise
        """
        try:
            result = self.pwd_context.verify(password, hashed_password)
            self.logger.debug(
                f"Password verification: {'success' if result else 'failed'}"
            )
            return result
        except Exception as e:
            self.logger.error(f"Password verification error: {e}")
            return False

    def is_hash_deprecated(self, hashed_password: str) -> bool:
        """
        Check if password hash needs updating.

        Args:
            hashed_password: Hashed password to check

        Returns:
            True if hash needs updating
        """
        return self.pwd_context.needs_update(hashed_password)


class SessionManager:
    """User session management functionality."""

    def __init__(self):
        """Initialize session manager."""
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(f"{__name__}.SessionManager")

    def create_session(
        self, user_id: str, token_jti: str, metadata: Dict[str, Any] = None
    ) -> None:
        """
        Create new user session.

        Args:
            user_id: User identifier
            token_jti: JWT token identifier
            metadata: Optional session metadata
        """
        session_data = {
            "user_id": user_id,
            "token_jti": token_jti,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        self.active_sessions[token_jti] = session_data
        self.logger.info(f"Session created for user {user_id}")

    def update_session_activity(self, token_jti: str) -> None:
        """
        Update session's last activity timestamp.

        Args:
            token_jti: JWT token identifier
        """
        if token_jti in self.active_sessions:
            self.active_sessions[token_jti]["last_activity"] = datetime.now(
                timezone.utc
            ).isoformat()

    def invalidate_session(self, token_jti: str) -> bool:
        """
        Invalidate user session.

        Args:
            token_jti: JWT token identifier

        Returns:
            True if session was invalidated, False if not found
        """
        if token_jti in self.active_sessions:
            user_id = self.active_sessions[token_jti]["user_id"]
            del self.active_sessions[token_jti]
            self.logger.info(f"Session invalidated for user {user_id}")
            return True
        return False

    def is_session_valid(self, token_jti: str) -> bool:
        """
        Check if session is still valid.

        Args:
            token_jti: JWT token identifier

        Returns:
            True if session is valid
        """
        return token_jti in self.active_sessions

    def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired sessions.

        Args:
            max_age_hours: Maximum session age in hours

        Returns:
            Number of sessions cleaned up
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        expired_sessions = []

        for token_jti, session_data in self.active_sessions.items():
            last_activity = datetime.fromisoformat(
                session_data["last_activity"].replace("Z", "+00:00")
            )
            if last_activity < cutoff_time:
                expired_sessions.append(token_jti)

        for token_jti in expired_sessions:
            self.invalidate_session(token_jti)

        self.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        return len(expired_sessions)


class AuthenticationManager:
    """Main authentication manager coordinating all auth components."""

    def __init__(
        self,
        secret_key: str,
        token_expiry: int = 60,
        db_manager: DatabaseManager = None,
    ):
        """
        Initialize authentication manager.

        Args:
            secret_key: JWT secret key
            token_expiry: Default token expiry in minutes
            db_manager: Database manager instance
        """
        self.secret_key = secret_key
        self.token_expiry = token_expiry
        self.db_manager = db_manager

        self.token_manager = TokenManager(secret_key)
        self.password_manager = PasswordManager()
        self.session_manager = SessionManager()

        self.logger = logging.getLogger(f"{__name__}.AuthenticationManager")

    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user credentials.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User information dictionary

        Raises:
            AuthenticationError: If authentication fails
        """
        if not username or not password:
            raise AuthenticationError("Username and password required")

        try:
            # Get user from database
            user = self.db_manager.get_user_by_username(username)
            if not user:
                raise AuthenticationError("Invalid credentials")

            # Verify password
            if not self.password_manager.verify_password(password, user.password_hash):
                self.logger.warning(f"Failed login attempt for user: {username}")
                raise AuthenticationError("Invalid credentials")

            # Check if user account is active
            if not user.is_active:
                raise AuthenticationError("Account disabled")

            user_info = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role.value,
                "last_login": datetime.now(timezone.utc).isoformat(),
            }

            # Update last login timestamp
            self.db_manager.update_user_last_login(user.id)

            self.logger.info(f"User {username} authenticated successfully")
            return user_info

        except AuthenticationError:
            raise
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            raise AuthenticationError("Authentication failed")

    def generate_token(self, user_info: Dict[str, Any]) -> str:
        """
        Generate JWT token for authenticated user.

        Args:
            user_info: User information dictionary

        Returns:
            JWT token string
        """
        token = self.token_manager.generate_token(user_info, self.token_expiry)

        # Extract JTI from token for session management
        payload = self.token_manager.validate_token(token)
        self.session_manager.create_session(
            user_info["user_id"],
            payload["jti"],
            {"login_time": user_info.get("last_login")},
        )

        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token and return user info.

        Args:
            token: JWT token string

        Returns:
            User information from token

        Raises:
            AuthenticationError: If token is invalid
        """
        payload = self.token_manager.validate_token(token)

        # Check session validity
        if not self.session_manager.is_session_valid(payload["jti"]):
            raise AuthenticationError("Session invalid or expired")

        # Update session activity
        self.session_manager.update_session_activity(payload["jti"])

        return payload

    def refresh_token(self, current_payload: Dict[str, Any]) -> str:
        """
        Refresh JWT token.

        Args:
            current_payload: Current token payload

        Returns:
            New JWT token
        """
        new_token = self.token_manager.refresh_token(current_payload, self.token_expiry)

        # Invalidate old session and create new one
        self.session_manager.invalidate_session(current_payload["jti"])

        new_payload = self.token_manager.validate_token(new_token)
        self.session_manager.create_session(
            current_payload["user_id"], new_payload["jti"]
        )

        return new_token

    def revoke_token(self, token: str) -> bool:
        """
        Revoke JWT token.

        Args:
            token: JWT token to revoke

        Returns:
            True if token was revoked successfully
        """
        try:
            payload = self.token_manager.validate_token(token)
            return self.session_manager.invalidate_session(payload["jti"])
        except AuthenticationError:
            return False

    def check_permission(self, user_role: str, required_role: str) -> bool:
        """
        Check if user has required permission level.

        Args:
            user_role: Current user's role
            required_role: Required role for operation

        Returns:
            True if user has sufficient privileges
        """
        try:
            user_role_enum = UserRole(user_role)
            required_role_enum = UserRole(required_role)

            return user_role_enum.privilege_level >= required_role_enum.privilege_level

        except ValueError:
            return False

    def health_check(self) -> Dict[str, Any]:
        """
        Perform authentication system health check.

        Returns:
            Health status dictionary
        """
        status = {
            "status": "healthy",
            "active_sessions": len(self.session_manager.active_sessions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Test token generation/validation
            test_user = {
                "user_id": "test",
                "username": "healthcheck",
                "role": "normal_user",
            }
            test_token = self.token_manager.generate_token(test_user, 1)
            self.token_manager.validate_token(test_token)

            status["token_system"] = "healthy"

        except Exception as e:
            status["status"] = "degraded"
            status["token_system"] = f"unhealthy: {e}"

        return status
