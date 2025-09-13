"""
Error response models for the CIDX server API.

Provides standardized error response formats following CLAUDE.md Foundation #1: No mocks.
All models represent real error responses that will be returned by the API.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ErrorType(str, Enum):
    """Standardized error types for API responses."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND_ERROR = "not_found_error"
    CONFLICT_ERROR = "conflict_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_SERVER_ERROR = "internal_server_error"


class ValidationFieldError(BaseModel):
    """Individual field validation error details."""

    field: str = Field(..., description="Name of the field that failed validation")
    message: str = Field(..., description="Human-readable error message")
    rejected_value: Any = Field(
        ..., description="The value that was rejected (may be sanitized)"
    )
    error_type: str = Field(
        ...,
        description="Type of validation error (e.g., 'min_length', 'pattern_mismatch')",
    )


class ValidationErrorDetails(BaseModel):
    """Detailed information for validation errors."""

    field_errors: List[ValidationFieldError] = Field(
        ..., description="List of field-specific validation errors"
    )
    error_count: int = Field(..., description="Total number of validation errors")


class ErrorResponse(BaseModel):
    """Standardized error response format for all API errors."""

    error: ErrorType = Field(..., description="Type of error that occurred")
    message: str = Field(..., description="Human-readable error message")
    correlation_id: str = Field(
        ..., description="Unique correlation ID for error tracking"
    )
    timestamp: datetime = Field(
        ..., description="ISO 8601 timestamp when error occurred"
    )
    details: Optional[Union[ValidationErrorDetails, Dict[str, Any]]] = Field(
        None, description="Additional error details (only for specific error types)"
    )
    retry_after: Optional[int] = Field(
        None,
        description="Seconds to wait before retrying (for service unavailable errors)",
    )


class DatabaseError(Exception):
    """Base exception for database-related errors."""

    def __init__(
        self,
        message: str,
        is_transient: bool = False,
        error_code: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        self.message = message
        self.is_transient = is_transient
        self.error_code = error_code
        self.original_exception = original_exception
        super().__init__(message)


class DatabaseRetryableError(DatabaseError):
    """Database error that can be retried (transient failure)."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            is_transient=True,
            error_code=error_code,
            original_exception=original_exception,
        )


class DatabasePermanentError(DatabaseError):
    """Database error that should not be retried (permanent failure)."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            is_transient=False,
            error_code=error_code,
            original_exception=original_exception,
        )


class HTTPErrorResponse(BaseModel):
    """HTTP-specific error response with status code."""

    status_code: int = Field(..., description="HTTP status code")
    error_response: ErrorResponse = Field(
        ..., description="Standardized error response"
    )


class RetryConfiguration(BaseModel):
    """Configuration for database retry logic."""

    max_attempts: int = Field(default=3, description="Maximum number of retry attempts")
    base_delay_seconds: float = Field(
        default=0.1, description="Base delay between retries in seconds"
    )
    max_delay_seconds: float = Field(
        default=60.0, description="Maximum delay between retries in seconds"
    )
    backoff_multiplier: float = Field(
        default=2.0, description="Exponential backoff multiplier"
    )
    jitter_factor: float = Field(
        default=0.1, description="Random jitter factor (0.0-1.0)"
    )


class SanitizationRule(BaseModel):
    """Configuration for sensitive data sanitization."""

    pattern: str = Field(..., description="Regex pattern to match sensitive data")
    replacement: str = Field(
        default="[REDACTED]", description="Replacement text for matched data"
    )
    field_names: List[str] = Field(
        default_factory=list, description="Specific field names to apply this rule to"
    )
    case_sensitive: bool = Field(
        default=False, description="Whether pattern matching is case sensitive"
    )


class ErrorHandlerConfiguration(BaseModel):
    """Configuration for the global error handler."""

    include_stack_traces_in_logs: bool = Field(
        default=True, description="Include full stack traces in error logs"
    )
    include_request_details_in_logs: bool = Field(
        default=True, description="Include request details in error logs"
    )
    sanitize_error_responses: bool = Field(
        default=True, description="Apply sanitization to error responses"
    )
    sanitize_log_messages: bool = Field(
        default=True, description="Apply sanitization to log messages"
    )
    retry_config: RetryConfiguration = Field(
        default_factory=RetryConfiguration, description="Database retry configuration"
    )
    sanitization_rules: List[SanitizationRule] = Field(
        default_factory=lambda: [
            # JSON-style password patterns
            SanitizationRule(
                pattern=r'("[^"]*(?:password|pwd|pass)[^"]*")\s*:\s*"([^"]+)"',
                replacement=r'\1: "[REDACTED]"',
                case_sensitive=False,
            ),
            # Simple password patterns
            SanitizationRule(
                pattern=r'((?:password|pwd|pass)(?:word|wd)?\s*[:=]\s*)(?:["\']?)([^"\'\s,}]+)(?:["\']?)',
                replacement=r"\1[REDACTED]",
                case_sensitive=False,
            ),
            # API key patterns
            SanitizationRule(
                pattern=r'((?:api_key|apikey|api-key)\s*[:=]\s*)(?:["\']?)([^"\'\s,}]+)(?:["\']?)',
                replacement=r"\1[REDACTED]",
                case_sensitive=False,
            ),
            # Token patterns
            SanitizationRule(
                pattern=r'((?:token|bearer|auth_token|access_token|refresh_token)\s*[:=]\s*)(?:["\']?)([^"\'\s,}]+)(?:["\']?)',
                replacement=r"\1[REDACTED]",
                case_sensitive=False,
            ),
            # Database URLs
            SanitizationRule(
                pattern=r"(postgresql|mysql|mongodb|redis)://[^:]+:[^@]+@[^/]+",
                replacement=r"\1://[REDACTED]:[REDACTED]@[HOST]",
                case_sensitive=False,
            ),
            # JWT tokens
            SanitizationRule(
                pattern=r"eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]*",
                replacement="[JWT_TOKEN]",
                case_sensitive=True,
            ),
            # Credit card numbers
            SanitizationRule(
                pattern=r"\b(?:\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}|\d{13,19})\b",
                replacement="[CREDIT_CARD]",
                case_sensitive=True,
            ),
            # SSN patterns
            SanitizationRule(
                pattern=r"\b\d{3}-?\d{2}-?\d{4}\b",
                replacement="[SSN]",
                case_sensitive=True,
            ),
            # Email addresses
            SanitizationRule(
                pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                replacement="[EMAIL]",
                case_sensitive=False,
            ),
            # Internal IP addresses
            SanitizationRule(
                pattern=r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b",
                replacement="[IP_ADDRESS]",
                case_sensitive=True,
            ),
            # File paths with sensitive directories
            SanitizationRule(
                pattern=r"(?:/home/[^/\s]+|/root|/etc/ssl/private|/var/secrets|~/.aws|~/.ssh)[/\w.-]*",
                replacement="[SENSITIVE_PATH]",
                case_sensitive=True,
            ),
        ],
        description="List of sanitization rules to apply",
    )
