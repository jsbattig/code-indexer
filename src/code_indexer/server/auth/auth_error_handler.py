"""
Authentication error handler for standardized security responses.

Implements secure error handling that prevents user enumeration, timing attacks,
and information leakage while maintaining comprehensive audit logging.

Following CLAUDE.md Foundation #1: NO MOCKS - Real security implementation only.
"""

import time
import hashlib
import secrets
from enum import Enum
from typing import Dict, Any, Optional

# datetime imports removed - not needed for this implementation

from .audit_logger import PasswordChangeAuditLogger
from .timing_attack_prevention import TimingAttackPrevention


class AuthErrorType(Enum):
    """Standardized authentication error types for internal categorization."""

    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_DISABLED = "account_disabled"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    GENERIC_AUTH_FAILURE = "generic_auth_failure"


class AuthError(Exception):
    """
    Authentication error with separation of public and internal information.

    Ensures that sensitive details are logged internally but never exposed
    to clients, preventing information leakage attacks.
    """

    def __init__(
        self,
        error_type: AuthErrorType,
        public_message: str,
        internal_message: str,
        user_context: str,
    ):
        """
        Initialize authentication error.

        Args:
            error_type: Internal categorization of the error
            public_message: Safe message to return to client
            internal_message: Detailed message for internal logging
            user_context: Username or user identifier for logging
        """
        self.error_type = error_type
        self.public_message = public_message
        self.internal_message = internal_message
        self.user_context = user_context

        # Exception str() should only show public message
        super().__init__(public_message)

    def __str__(self) -> str:
        """Return only public message to prevent information leakage."""
        return self.public_message


class AuthErrorHandler:
    """
    Authentication error handler with security-focused response standardization.

    Security Features:
    - Generic error messages for all authentication failures
    - Constant-time responses to prevent timing attacks
    - Dummy password hashing for non-existent users
    - Comprehensive audit logging of detailed error information
    - Standardized response format across all auth endpoints
    """

    def __init__(self, minimum_response_time_ms: int = 100):
        """
        Initialize authentication error handler.

        Args:
            minimum_response_time_ms: Minimum response time in milliseconds
        """
        self.minimum_response_time_seconds = minimum_response_time_ms / 1000.0
        self.timing_prevention = TimingAttackPrevention(minimum_response_time_ms)
        self.audit_logger = PasswordChangeAuditLogger()

        # Generic messages that don't leak information
        self._generic_messages = {
            "auth_failure": "Invalid credentials",
            "registration_success": "Registration initiated. Please check your email.",
            "password_reset_success": "Password reset email sent if account exists",
        }

    def create_error_response(
        self,
        error_type: AuthErrorType,
        user_context: str,
        internal_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create standardized error response with timing attack prevention.

        Args:
            error_type: Type of authentication error
            user_context: Username or user identifier
            internal_message: Detailed message for audit logging
            ip_address: Client IP address for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Standardized error response dictionary
        """

        def create_response() -> Dict[str, Any]:
            # Log detailed information internally
            if hasattr(self.audit_logger, "log_authentication_failure"):
                additional_context = {}
                if ip_address:
                    additional_context["ip_address"] = ip_address
                if user_agent:
                    additional_context["user_agent"] = user_agent

                self.audit_logger.log_authentication_failure(
                    username=user_context,
                    error_type=error_type.value,
                    message=internal_message
                    or f"Authentication failed: {error_type.value}",
                    additional_context=(
                        additional_context if additional_context else None
                    ),
                )

            # Perform dummy work to normalize timing
            self._perform_security_work()

            # Return generic response that doesn't leak information
            return {
                "message": self._generic_messages["auth_failure"],
                "status_code": 401,
            }

        # Execute with constant timing
        result = self.timing_prevention.constant_time_execute(create_response)
        return result  # type: ignore[no-any-return]

    def perform_dummy_password_work(self) -> None:
        """
        Perform dummy password hashing work for timing consistency.

        When a user doesn't exist, we still need to perform password-like
        work to prevent timing-based user enumeration attacks.
        """
        # Generate dummy password and salt
        dummy_password = secrets.token_hex(16)
        dummy_salt = secrets.token_hex(8)

        # Perform bcrypt-like work (multiple hashing rounds with more computation)
        # Need to match real bcrypt timing (~50-200ms)
        result = dummy_password.encode("utf-8")
        for _ in range(5000):  # Many more rounds to match bcrypt cost
            result = hashlib.sha256(result + dummy_salt.encode("utf-8")).digest()
            # Add some additional computational work
            for i in range(20):
                result = hashlib.sha256(result + str(i).encode("utf-8")).digest()

    def create_registration_response(
        self,
        email: str,
        account_exists: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create standardized registration response regardless of account existence.

        Args:
            email: Email address used for registration
            account_exists: Whether account already exists (internal use only)
            ip_address: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Standardized registration response
        """

        def create_response() -> Dict[str, Any]:
            # Log registration attempt internally
            if hasattr(self.audit_logger, "log_registration_attempt"):
                additional_context = {"account_exists": account_exists, "email": email}
                if ip_address:
                    additional_context["ip_address"] = ip_address
                if user_agent:
                    additional_context["user_agent"] = user_agent

                self.audit_logger.log_registration_attempt(
                    email=email,
                    success=not account_exists,  # New registration is success
                    message=f"Registration attempt for {'existing' if account_exists else 'new'} account",
                    additional_context=additional_context,
                )

            # Always perform some work for timing consistency
            if account_exists:
                # If account exists, perform dummy password work
                self.perform_dummy_password_work()
            else:
                # If new account, simulate account creation work
                self._perform_security_work()

            return {
                "message": self._generic_messages["registration_success"],
                "status_code": 200,
            }

        result = self.timing_prevention.constant_time_execute(create_response)
        return result  # type: ignore[no-any-return]

    def create_password_reset_response(
        self,
        email: str,
        account_exists: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create standardized password reset response regardless of account existence.

        Args:
            email: Email address for password reset
            account_exists: Whether account exists (internal use only)
            ip_address: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Standardized password reset response
        """

        def create_response() -> Dict[str, Any]:
            # Log password reset attempt internally
            if hasattr(self.audit_logger, "log_password_reset_attempt"):
                additional_context = {"account_exists": account_exists, "email": email}
                if ip_address:
                    additional_context["ip_address"] = ip_address
                if user_agent:
                    additional_context["user_agent"] = user_agent

                self.audit_logger.log_password_reset_attempt(
                    email=email,
                    success=account_exists,  # Only existing accounts get real reset
                    message=f"Password reset attempt for {'existing' if account_exists else 'non-existent'} account",
                    additional_context=additional_context,
                )

            # Perform work for timing consistency
            self._perform_security_work()

            return {
                "message": self._generic_messages["password_reset_success"],
                "status_code": 200,
            }

        result = self.timing_prevention.constant_time_execute(create_response)
        return result  # type: ignore[no-any-return]

    def _perform_security_work(self) -> None:
        """
        Perform consistent security work to normalize timing across operations.

        This ensures all authentication operations take similar time
        regardless of the specific path taken.
        """
        # Generate some random work similar to what real auth operations do
        dummy_data = secrets.token_bytes(32)

        # Perform hash operations similar to password validation
        for _ in range(5):
            dummy_data = hashlib.sha256(dummy_data).digest()

        # Add a small random delay to prevent precise timing analysis
        time.sleep(secrets.randbelow(10) / 1000.0)  # 0-9ms random


# Global instance for use across authentication endpoints
auth_error_handler = AuthErrorHandler()
