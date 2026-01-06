"""
Global error handler middleware for CIDX Server.

Implements comprehensive error handling with standardized responses, correlation IDs,
retry logic, and security-compliant sanitization following CLAUDE.md Foundation #1: No mocks.

Key Features:
- Standardized error response format across all endpoints
- Correlation ID generation for error tracking
- Database error retry logic with exponential backoff
- Sensitive data sanitization in responses and logs
- Comprehensive logging with request context
- Security-compliant error messages
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
import traceback
from typing import Dict, Any, Optional, Union, Callable, TypeVar, cast
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.error_models import (
    ErrorType,
    DatabaseError,
    DatabaseRetryableError,
    DatabasePermanentError,
    ErrorHandlerConfiguration,
    RetryConfiguration,
)
from .sanitization import SensitiveDataSanitizer
from .retry_handler import DatabaseRetryHandler
from .error_formatters import (
    generate_correlation_id,
    get_current_timestamp,
    create_validation_error_response,
    create_database_error_response,
    create_http_exception_response,
    create_generic_error_response,
    create_json_response,
)

# Configure logger for this module
logger = logging.getLogger(__name__)

# Type variable for retry functions
T = TypeVar("T")

# CLAUDE.md Foundation #8 Pattern #7: Named constants instead of magic numbers

# Default configuration constants
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_BASE_RETRY_DELAY_SECONDS = 0.1
DEFAULT_MAX_RETRY_DELAY_SECONDS = 60.0

# Security fix constants for retry timing calculations (Foundation #8 Pattern #7)
MINIMUM_RETRY_SECONDS = 5
MAXIMUM_RETRY_SECONDS = 60
RETRY_MULTIPLIER = 10


class GlobalErrorHandler(BaseHTTPMiddleware):
    """
    Global error handler middleware for FastAPI applications.

    Provides comprehensive error handling with:
    - Standardized error responses
    - Correlation ID tracking
    - Database retry logic
    - Sensitive data sanitization
    - Comprehensive logging

    Follows CLAUDE.md Foundation #1: No mocks - real error processing only.
    """

    def __init__(
        self,
        app=None,
        configuration: Optional[ErrorHandlerConfiguration] = None,
        max_retry_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS,
        base_retry_delay: float = DEFAULT_BASE_RETRY_DELAY_SECONDS,
        max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
    ):
        """
        Initialize global error handler.

        Args:
            app: FastAPI application instance
            configuration: Error handler configuration
            max_retry_attempts: Maximum retry attempts for database errors
            base_retry_delay: Base delay between retries in seconds
            max_retry_delay: Maximum delay between retries in seconds
        """
        super().__init__(app)

        self.config = configuration or ErrorHandlerConfiguration()

        # Override retry configuration if parameters provided
        if (
            max_retry_attempts != DEFAULT_MAX_RETRY_ATTEMPTS
            or base_retry_delay != DEFAULT_BASE_RETRY_DELAY_SECONDS
            or max_retry_delay != DEFAULT_MAX_RETRY_DELAY_SECONDS
        ):
            self.config.retry_config = RetryConfiguration(
                max_attempts=max_retry_attempts,
                base_delay_seconds=base_retry_delay,
                max_delay_seconds=max_retry_delay,
            )

        self.sanitizer = SensitiveDataSanitizer(self.config)
        self.retry_handler = DatabaseRetryHandler(self.config.retry_config)

        # Status code mapping
        self._status_code_map = {
            ErrorType.VALIDATION_ERROR: 400,
            ErrorType.AUTHENTICATION_ERROR: 401,
            ErrorType.AUTHORIZATION_ERROR: 403,
            ErrorType.NOT_FOUND_ERROR: 404,
            ErrorType.CONFLICT_ERROR: 409,
            ErrorType.RATE_LIMIT_ERROR: 429,
            ErrorType.SERVICE_UNAVAILABLE: 503,
            ErrorType.INTERNAL_SERVER_ERROR: 500,
        }

    def get_status_code_for_error_type(self, error_type: Union[ErrorType, str]) -> int:
        """Get HTTP status code for error type."""
        if isinstance(error_type, str):
            error_type = ErrorType(error_type)
        return self._status_code_map.get(error_type, 500)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Main middleware dispatch method that catches and handles all errors.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/endpoint in chain

        Returns:
            HTTP response (either successful or error response)
        """
        try:
            # Process the request through the rest of the application
            response = await call_next(request)
            return cast(Response, response)

        except (PydanticValidationError, RequestValidationError) as e:
            # Handle Pydantic validation errors (both direct and FastAPI request validation)
            return self._create_error_response(self.handle_validation_error(e, request))

        except HTTPException as e:
            # Handle FastAPI HTTP exceptions (let them pass through mostly unchanged)
            return self._create_http_exception_response(e, request)

        except (DatabaseRetryableError, DatabasePermanentError) as e:
            # Handle database-specific errors
            return self._create_error_response(self.handle_database_error(e, request))

        except Exception as e:
            # Handle all other unhandled exceptions
            return self._create_error_response(
                self.handle_unhandled_exception(e, request)
            )

    def handle_validation_error(
        self,
        error: Union[PydanticValidationError, RequestValidationError],
        request: Request,
    ) -> Dict[str, Any]:
        """
        Handle Pydantic validation errors with detailed field information.

        Args:
            error: Pydantic validation error
            request: HTTP request that caused the error

        Returns:
            Standardized error response dictionary
        """
        correlation_id = generate_correlation_id()
        timestamp = get_current_timestamp()

        # Use formatter to create validation error response
        response_data = create_validation_error_response(
            error, self.sanitizer, correlation_id, timestamp
        )

        # Log the validation error with request context
        field_count = response_data.get("details", {}).get("error_count", 0)
        self._log_error(
            error_type="ValidationError",
            message=f"Request validation failed: {field_count} field errors",
            correlation_id=correlation_id,
            request=request,
            exception=error,
        )

        return response_data

    def handle_database_error(
        self, error: DatabaseError, request: Request
    ) -> Dict[str, Any]:
        """
        Handle database errors with appropriate retry logic and response.

        Args:
            error: Database error (retryable or permanent)
            request: HTTP request that caused the error

        Returns:
            Standardized error response dictionary
        """
        correlation_id = generate_correlation_id()
        timestamp = get_current_timestamp()

        # Determine error type and create response using formatter
        if isinstance(error, DatabaseRetryableError):
            error_type = ErrorType.SERVICE_UNAVAILABLE
        else:
            error_type = ErrorType.INTERNAL_SERVER_ERROR

        response_data = create_database_error_response(
            error_type, correlation_id, timestamp, self.config.retry_config
        )

        # Log the database error with full context
        self._log_error(
            error_type="DatabaseError",
            message=f"Database operation failed: {self.sanitizer.sanitize_string(str(error))}",
            correlation_id=correlation_id,
            request=request,
            exception=error,
        )

        return response_data

    def handle_unhandled_exception(
        self, error: Exception, request: Request
    ) -> Dict[str, Any]:
        """
        Handle unexpected exceptions with security-compliant responses.

        Args:
            error: Unhandled exception
            request: HTTP request that caused the error

        Returns:
            Standardized error response dictionary
        """
        correlation_id = generate_correlation_id()
        timestamp = get_current_timestamp()

        # Use formatter to create generic error response
        error_response = create_generic_error_response(correlation_id, timestamp)

        # Log comprehensive error details internally
        self._log_error(
            error_type="UnhandledException",
            message=f"Unhandled exception: {type(error).__name__}: {self.sanitizer.sanitize_string(str(error))}",
            correlation_id=correlation_id,
            request=request,
            exception=error,
        )

        return error_response

    def execute_with_database_retry(self, operation: Callable[[], T]) -> T:
        """
        Execute database operation with retry logic.

        Args:
            operation: Database operation to execute

        Returns:
            Result of the operation

        Raises:
            DatabaseError: If operation fails after all retries
        """
        return self.retry_handler.execute_with_retry(operation)

    def _create_error_response(self, error_data: Dict[str, Any]) -> JSONResponse:
        """Create JSON error response with appropriate status code."""
        return create_json_response(error_data, self._status_code_map)

    def _create_http_exception_response(
        self, error: HTTPException, request: Request
    ) -> JSONResponse:
        """Create standardized response for FastAPI HTTPException."""
        correlation_id = generate_correlation_id()
        timestamp = get_current_timestamp()

        # Use formatter to create HTTP exception response
        error_response = create_http_exception_response(
            error.status_code, error.detail, self.sanitizer, correlation_id, timestamp
        )

        # Log HTTP exception
        sanitized_detail = self.sanitizer.sanitize_string(str(error.detail))
        self._log_error(
            error_type="HTTPException",
            message=f"HTTP {error.status_code}: {sanitized_detail}",
            correlation_id=correlation_id,
            request=request,
            exception=error,
        )

        return JSONResponse(
            status_code=error.status_code,
            content=error_response,
            headers=getattr(error, "headers", None),
        )

    def _log_error(
        self,
        error_type: str,
        message: str,
        correlation_id: str,
        request: Request,
        exception: Optional[Exception] = None,
    ) -> None:
        """
        Log error with comprehensive context information.

        Args:
            error_type: Type of error for categorization
            message: Error message to log
            correlation_id: Correlation ID for tracking
            request: HTTP request context
            exception: Original exception (optional)
        """
        try:
            # Get sanitized request information
            request_info = self.sanitizer.sanitize_request_info(request)

            # Prepare log message
            log_parts = [
                f"{error_type} [ID: {correlation_id}]",
                message,
                f"Request: {request_info['method']} {request_info['path']}",
            ]

            if request_info.get("query_params"):
                log_parts.append(f"Query: {request_info['query_params']}")

            # Include stack trace for debugging if configured
            if self.config.include_stack_traces_in_logs and exception:
                # Sanitize stack trace - use format_exception for passed exceptions
                stack_trace = "".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                )
                sanitized_trace = self.sanitizer.sanitize_string(stack_trace)
                log_parts.append(f"Stack trace:\n{sanitized_trace}")

            log_message = " | ".join(log_parts)

            # Log at appropriate level
            if error_type in ["ValidationError", "HTTPException"]:
                logger.warning(
                    log_message, extra={"correlation_id": get_correlation_id()}
                )
            else:
                logger.error(
                    log_message, extra={"correlation_id": get_correlation_id()}
                )

        except Exception as log_error:
            # Fallback logging if there's an error in the logging process
            logger.error(
                f"Error logging failed [ID: {correlation_id}]: {log_error}",
                extra={"correlation_id": get_correlation_id()},
            )
