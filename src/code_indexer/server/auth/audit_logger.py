"""
Comprehensive audit logging for password change attempts.

Implements secure audit logging with IP addresses and timestamps.
Following CLAUDE.md principles: NO MOCKS - Real audit logging implementation.
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class PasswordChangeAuditLogger:
    """
    Comprehensive audit logger for password change attempts.

    Security requirements:
    - Log all password change attempts (successful and failed)
    - Include IP addresses, timestamps, and usernames
    - Structured logging format for analysis
    - Separate audit log file for security monitoring
    """

    def __init__(self, log_file_path: Optional[str] = None):
        """
        Initialize audit logger.

        Args:
            log_file_path: Optional custom path for audit log file
        """
        if log_file_path:
            self.log_file_path = log_file_path
        else:
            # Default audit log location
            server_dir = Path.home() / ".cidx-server"
            server_dir.mkdir(exist_ok=True)
            self.log_file_path = str(server_dir / "password_audit.log")

        # Configure audit logger with unique name based on file path
        # This prevents multiple instances from interfering with each other
        logger_name = f"password_audit_{hash(self.log_file_path)}"
        self.audit_logger = logging.getLogger(logger_name)
        self.audit_logger.setLevel(logging.INFO)

        # Remove any existing handlers to avoid duplicates
        for handler in self.audit_logger.handlers[:]:
            self.audit_logger.removeHandler(handler)

        # Create file handler for audit log
        file_handler = logging.FileHandler(self.log_file_path)
        file_handler.setLevel(logging.INFO)

        # Create formatter for structured logging
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S UTC",
        )
        file_handler.setFormatter(formatter)

        self.audit_logger.addHandler(file_handler)
        self.audit_logger.propagate = False  # Don't propagate to root logger

    def log_password_change_success(
        self,
        username: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log successful password change attempt.

        Args:
            username: Username that changed password
            ip_address: IP address of the request
            user_agent: User agent string from request headers
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "password_change_success",
            "username": username,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }

        self.audit_logger.info(f"PASSWORD_CHANGE_SUCCESS: {json.dumps(log_entry)}")

    def log_password_change_failure(
        self,
        username: str,
        ip_address: str,
        reason: str,
        user_agent: Optional[str] = None,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log failed password change attempt.

        Args:
            username: Username that attempted to change password
            ip_address: IP address of the request
            reason: Reason for failure (e.g., "Invalid old password", "Rate limited")
            user_agent: User agent string from request headers
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "password_change_failure",
            "username": username,
            "ip_address": ip_address,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }

        self.audit_logger.warning(f"PASSWORD_CHANGE_FAILURE: {json.dumps(log_entry)}")

    def log_rate_limit_triggered(
        self,
        username: str,
        ip_address: str,
        attempt_count: int,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Log rate limit being triggered.

        Args:
            username: Username that triggered rate limit
            ip_address: IP address of the request
            attempt_count: Number of failed attempts that triggered rate limit
            user_agent: User agent string from request headers
        """
        log_entry = {
            "event_type": "password_change_rate_limit",
            "username": username,
            "ip_address": ip_address,
            "attempt_count": attempt_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
        }

        self.audit_logger.warning(
            f"PASSWORD_CHANGE_RATE_LIMIT: {json.dumps(log_entry)}"
        )

    def log_concurrent_change_conflict(
        self, username: str, ip_address: str, user_agent: Optional[str] = None
    ) -> None:
        """
        Log concurrent password change conflict.

        Args:
            username: Username that experienced concurrent change conflict
            ip_address: IP address of the request
            user_agent: User agent string from request headers
        """
        log_entry = {
            "event_type": "password_change_concurrent_conflict",
            "username": username,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
        }

        self.audit_logger.warning(
            f"PASSWORD_CHANGE_CONCURRENT_CONFLICT: {json.dumps(log_entry)}"
        )

    def log_token_refresh_success(
        self,
        username: str,
        ip_address: str,
        family_id: str,
        user_agent: Optional[str] = None,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log successful token refresh attempt.

        Args:
            username: Username that refreshed tokens
            ip_address: IP address of the request
            family_id: Token family ID for security tracking
            user_agent: User agent string from request headers
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "token_refresh_success",
            "username": username,
            "ip_address": ip_address,
            "family_id": family_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }

        self.audit_logger.info(f"TOKEN_REFRESH_SUCCESS: {json.dumps(log_entry)}")

    def log_token_refresh_failure(
        self,
        username: str,
        ip_address: str,
        reason: str,
        security_incident: bool = False,
        user_agent: Optional[str] = None,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log failed token refresh attempt.

        Args:
            username: Username that attempted to refresh tokens
            ip_address: IP address of the request
            reason: Reason for failure (e.g., "Invalid refresh token", "Token expired")
            security_incident: Whether this represents a security incident
            user_agent: User agent string from request headers
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "token_refresh_failure",
            "username": username,
            "ip_address": ip_address,
            "reason": reason,
            "security_incident": security_incident,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }

        # Log as warning for security incidents, info for normal failures
        log_level = (
            self.audit_logger.warning if security_incident else self.audit_logger.info
        )
        log_level(f"TOKEN_REFRESH_FAILURE: {json.dumps(log_entry)}")

    def log_security_incident(
        self,
        username: str,
        incident_type: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log security incident related to token management.

        Args:
            username: Username involved in incident
            incident_type: Type of incident (e.g., "token_replay_attack", "family_revoked")
            ip_address: IP address of the request
            user_agent: User agent string from request headers
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "security_incident",
            "incident_type": incident_type,
            "username": username,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }

        self.audit_logger.error(f"SECURITY_INCIDENT: {json.dumps(log_entry)}")

    def log_authentication_failure(
        self,
        username: str,
        error_type: str,
        message: str,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log authentication failure attempt.

        Args:
            username: Username that failed authentication
            error_type: Type of authentication error
            message: Detailed failure message
            additional_context: Additional context information (IP, user agent, etc.)
        """
        log_entry = {
            "event_type": "authentication_failure",
            "username": username,
            "error_type": error_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "additional_context": additional_context or {},
        }

        self.audit_logger.warning(f"AUTHENTICATION_FAILURE: {json.dumps(log_entry)}")

    def log_registration_attempt(
        self,
        email: str,
        success: bool,
        message: str,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log registration attempt.

        Args:
            email: Email address used for registration
            success: Whether registration was successful
            message: Descriptive message about the attempt
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "registration_attempt",
            "email": email,
            "success": success,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "additional_context": additional_context or {},
        }

        log_message = f"REGISTRATION_{'SUCCESS' if success else 'ATTEMPT'}: {json.dumps(log_entry)}"

        if success:
            self.audit_logger.info(log_message)
        else:
            self.audit_logger.warning(log_message)

    def log_password_reset_attempt(
        self,
        email: str,
        success: bool,
        message: str,
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log password reset attempt.

        Args:
            email: Email address for password reset
            success: Whether the email corresponds to an existing account
            message: Descriptive message about the attempt
            additional_context: Additional context information
        """
        log_entry = {
            "event_type": "password_reset_attempt",
            "email": email,
            "account_exists": success,  # For password reset, success means account exists
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "additional_context": additional_context or {},
        }

        self.audit_logger.info(f"PASSWORD_RESET_ATTEMPT: {json.dumps(log_entry)}")

    def log_oauth_client_registration(
        self,
        client_id,
        client_name,
        ip_address,
        user_agent=None,
        additional_context=None,
    ):
        """Log OAuth client registration."""
        log_entry = {
            "event_type": "oauth_client_registration",
            "client_id": client_id,
            "client_name": client_name,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }
        self.audit_logger.info(f"OAUTH_CLIENT_REGISTRATION: {json.dumps(log_entry)}")

    def log_oauth_authorization(
        self, username, client_id, ip_address, user_agent=None, additional_context=None
    ):
        """Log OAuth authorization."""
        log_entry = {
            "event_type": "oauth_authorization",
            "username": username,
            "client_id": client_id,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }
        self.audit_logger.info(f"OAUTH_AUTHORIZATION: {json.dumps(log_entry)}")

    def log_oauth_token_exchange(
        self,
        username,
        client_id,
        grant_type,
        ip_address,
        user_agent=None,
        additional_context=None,
    ):
        """Log OAuth token exchange."""
        log_entry = {
            "event_type": "oauth_token_exchange",
            "username": username,
            "client_id": client_id,
            "grant_type": grant_type,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }
        self.audit_logger.info(f"OAUTH_TOKEN_EXCHANGE: {json.dumps(log_entry)}")

    def log_oauth_token_revocation(
        self, username, token_type, ip_address, user_agent=None, additional_context=None
    ):
        """Log OAuth token revocation."""
        log_entry = {
            "event_type": "oauth_token_revocation",
            "username": username,
            "token_type": token_type,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "additional_context": additional_context or {},
        }
        self.audit_logger.info(f"OAUTH_TOKEN_REVOCATION: {json.dumps(log_entry)}")


# Global audit logger instance
password_audit_logger = PasswordChangeAuditLogger()
