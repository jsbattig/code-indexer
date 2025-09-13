"""
Error response formatters for CIDX Server.

Formats standardized error responses following CLAUDE.md Foundation #1: No mocks.
Provides consistent error response formatting across all endpoints.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from ..models.error_models import (
    ErrorType,
    ValidationFieldError,
    ValidationErrorDetails,
)

# CLAUDE.md Foundation #8 Pattern #7: Named constants for security fix
MINIMUM_RETRY_SECONDS = 5
MAXIMUM_RETRY_SECONDS = 60
RETRY_MULTIPLIER = 10


def generate_correlation_id() -> str:
    """Generate unique correlation ID for error tracking."""
    return str(uuid.uuid4())


def get_current_timestamp() -> datetime:
    """Get current timestamp in UTC."""
    return datetime.now(timezone.utc)


def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp in ISO 8601 format."""
    return timestamp.isoformat().replace("+00:00", "Z")


def humanize_validation_message(pydantic_error: Dict[str, Any]) -> str:
    """Convert Pydantic error messages to human-readable format."""
    error_type = pydantic_error["type"]
    message = pydantic_error.get("msg", "")

    # Map common error types to friendly messages
    friendly_messages = {
        "missing": "This field is required",
        "string_too_short": "This field is too short",
        "string_too_long": "This field is too long",
        "string_pattern_mismatch": "This field has an invalid format",
        "value_error.missing": "This field is required",
        "type_error.integer": "This field must be a number",
        "type_error.str": "This field must be text",
        "type_error.bool": "This field must be true or false",
        "value_error.number.not_gt": "This field must be greater than the minimum value",
        "value_error.number.not_lt": "This field must be less than the maximum value",
        "value_error.email": "This field must be a valid email address",
    }

    return friendly_messages.get(error_type, message or "Invalid value")


def create_validation_error_response(
    validation_error: PydanticValidationError,
    sanitizer,
    correlation_id: str,
    timestamp: datetime,
) -> Dict[str, Any]:
    """
    Create standardized validation error response.

    Args:
        validation_error: Pydantic validation error
        sanitizer: Data sanitizer instance
        correlation_id: Unique correlation ID
        timestamp: Error timestamp

    Returns:
        Standardized error response dictionary
    """
    # Process validation errors into structured format
    field_errors = []

    # Handle both PydanticValidationError and RequestValidationError
    error_details = validation_error.errors()

    for pydantic_error in error_details:
        # Handle location path - RequestValidationError includes 'body' in path
        loc_path = pydantic_error.get("loc", [])
        if loc_path and loc_path[0] == "body":
            # Remove 'body' from path for cleaner field names
            field_path = ".".join(str(loc) for loc in loc_path[1:])
        else:
            field_path = ".".join(str(loc) for loc in loc_path)

        # Sanitize rejected value based on field name
        rejected_value = pydantic_error.get("input", "N/A")
        sanitized_value = sanitizer.sanitize_field_value(field_path, rejected_value)

        field_error = ValidationFieldError(
            field=field_path,
            message=humanize_validation_message(pydantic_error),
            rejected_value=sanitized_value,
            error_type=pydantic_error["type"],
        )
        field_errors.append(field_error)

    # Create validation error details
    validation_details = ValidationErrorDetails(
        field_errors=field_errors, error_count=len(field_errors)
    )

    return {
        "error": ErrorType.VALIDATION_ERROR,
        "message": "Request validation failed. Please check the provided data and try again.",
        "correlation_id": correlation_id,
        "timestamp": format_timestamp(timestamp),
        "details": validation_details.model_dump(),
    }


def create_database_error_response(
    error_type: ErrorType, correlation_id: str, timestamp: datetime, retry_config=None
) -> Dict[str, Any]:
    """
    Create standardized database error response.

    Args:
        error_type: Type of database error
        correlation_id: Unique correlation ID
        timestamp: Error timestamp
        retry_config: Retry configuration for calculating retry-after header

    Returns:
        Standardized error response dictionary
    """
    if error_type == ErrorType.SERVICE_UNAVAILABLE:
        # Transient database error - service unavailable
        message = "The service is temporarily unavailable due to a database issue. Please try again later."

        # Calculate retry_after using constants (security fix)
        if retry_config:
            retry_after = min(
                MAXIMUM_RETRY_SECONDS,
                max(
                    MINIMUM_RETRY_SECONDS,
                    int(retry_config.base_delay_seconds * RETRY_MULTIPLIER),
                ),
            )
        else:
            retry_after = MINIMUM_RETRY_SECONDS

        return {
            "error": error_type,
            "message": message,
            "correlation_id": correlation_id,
            "timestamp": format_timestamp(timestamp),
            "retry_after": retry_after,
        }
    else:
        # Permanent database error - internal server error
        message = "An internal server error occurred. Please contact support if the problem persists."

        return {
            "error": error_type,
            "message": message,
            "correlation_id": correlation_id,
            "timestamp": format_timestamp(timestamp),
        }


def create_http_exception_response(
    status_code: int, detail: str, sanitizer, correlation_id: str, timestamp: datetime
) -> Dict[str, Any]:
    """
    Create standardized HTTP exception response.

    Args:
        status_code: HTTP status code
        detail: Error detail message
        sanitizer: Data sanitizer instance
        correlation_id: Unique correlation ID
        timestamp: Error timestamp

    Returns:
        Standardized error response dictionary
    """
    # Map HTTPException status codes to our error types
    status_to_error_type = {
        400: ErrorType.VALIDATION_ERROR,
        401: ErrorType.AUTHENTICATION_ERROR,
        403: ErrorType.AUTHORIZATION_ERROR,
        404: ErrorType.NOT_FOUND_ERROR,
        409: ErrorType.CONFLICT_ERROR,
        429: ErrorType.RATE_LIMIT_ERROR,
        503: ErrorType.SERVICE_UNAVAILABLE,
    }

    error_type = status_to_error_type.get(status_code, ErrorType.INTERNAL_SERVER_ERROR)

    # Sanitize error message
    sanitized_detail = sanitizer.sanitize_string(str(detail))

    return {
        "error": error_type,
        "message": sanitized_detail,
        "correlation_id": correlation_id,
        "timestamp": format_timestamp(timestamp),
    }


def create_generic_error_response(
    correlation_id: str, timestamp: datetime
) -> Dict[str, Any]:
    """
    Create standardized generic error response for unhandled exceptions.

    Args:
        correlation_id: Unique correlation ID
        timestamp: Error timestamp

    Returns:
        Standardized error response dictionary
    """
    return {
        "error": ErrorType.INTERNAL_SERVER_ERROR,
        "message": "An internal server error occurred. Please contact support if the problem persists.",
        "correlation_id": correlation_id,
        "timestamp": format_timestamp(timestamp),
    }


def create_json_response(
    error_data: Dict[str, Any], status_code_map: Dict[ErrorType, int]
) -> JSONResponse:
    """
    Create JSON error response with appropriate status code and headers.

    Args:
        error_data: Error response data
        status_code_map: Mapping of error types to HTTP status codes

    Returns:
        JSONResponse with proper status code and headers
    """
    error_type = error_data.get("error", ErrorType.INTERNAL_SERVER_ERROR)
    status_code = status_code_map.get(error_type, 500)

    # Override status code to 400 for validation errors (instead of FastAPI's default 422)
    if error_type == ErrorType.VALIDATION_ERROR:
        status_code = 400

    # Add Retry-After header for service unavailable errors
    headers = {}
    if error_data.get("retry_after"):
        headers["Retry-After"] = str(error_data["retry_after"])

    return JSONResponse(status_code=status_code, content=error_data, headers=headers)
