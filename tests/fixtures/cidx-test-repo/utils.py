"""
Common utility functions and helpers for the CIDX test application.

This module provides shared utilities for validation, input sanitization,
rate limiting, and other common operations used across the application.
"""

import re
import json
import hashlib
import secrets
import logging
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime, timedelta, timezone
from functools import wraps
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


class RateLimitError(Exception):
    """Custom exception for rate limiting violations."""

    pass


def sanitize_input(
    input_string: str, max_length: int = 1000, allow_html: bool = False
) -> str:
    """
    Sanitize user input to prevent injection attacks.

    Args:
        input_string: Input string to sanitize
        max_length: Maximum allowed length
        allow_html: Whether to allow HTML tags

    Returns:
        Sanitized input string

    Raises:
        ValidationError: If input fails validation
    """
    if not isinstance(input_string, str):
        raise ValidationError("Input must be a string")

    # Trim whitespace
    sanitized = input_string.strip()

    # Check length
    if len(sanitized) > max_length:
        raise ValidationError(f"Input too long (max {max_length} characters)")

    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")

    # Remove/escape HTML if not allowed
    if not allow_html:
        sanitized = sanitized.replace("<", "&lt;").replace(">", "&gt;")

    # Remove control characters except common whitespace
    sanitized = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", sanitized)

    return sanitized


def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if email is valid
    """
    if not email:
        return False

    # Basic email regex pattern
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_username(username: str) -> bool:
    """
    Validate username format.

    Args:
        username: Username to validate

    Returns:
        True if username is valid
    """
    if not username:
        return False

    # Username must be 3-50 characters, alphanumeric plus underscore/dash
    pattern = r"^[a-zA-Z0-9_-]{3,50}$"
    return bool(re.match(pattern, username))


def validate_json_schema(
    data: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
) -> None:
    """
    Validate JSON data against a simple schema.

    Args:
        data: Data to validate
        schema: Schema definition

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError("Data must be a dictionary")

    # Check required fields
    for field, rules in schema.items():
        if rules.get("required", False) and field not in data:
            raise ValidationError(f"Missing required field: {field}")

        if field in data:
            value = data[field]
            expected_type = rules.get("type")

            # Type validation
            if expected_type == "string" and not isinstance(value, str):
                raise ValidationError(f"Field '{field}' must be a string")
            elif expected_type == "integer" and not isinstance(value, int):
                raise ValidationError(f"Field '{field}' must be an integer")
            elif expected_type == "boolean" and not isinstance(value, bool):
                raise ValidationError(f"Field '{field}' must be a boolean")
            elif expected_type == "list" and not isinstance(value, list):
                raise ValidationError(f"Field '{field}' must be a list")

            # Length validation for strings
            if isinstance(value, str):
                min_length = rules.get("min_length", 0)
                max_length = rules.get("max_length", float("inf"))

                if len(value) < min_length:
                    raise ValidationError(
                        f"Field '{field}' too short (min {min_length})"
                    )
                if len(value) > max_length:
                    raise ValidationError(
                        f"Field '{field}' too long (max {max_length})"
                    )

            # Range validation for numbers
            if isinstance(value, (int, float)):
                min_value = rules.get("min_value", float("-inf"))
                max_value = rules.get("max_value", float("inf"))

                if value < min_value:
                    raise ValidationError(
                        f"Field '{field}' too small (min {min_value})"
                    )
                if value > max_value:
                    raise ValidationError(
                        f"Field '{field}' too large (max {max_value})"
                    )

            # Allowed values validation
            allowed_values = rules.get("allowed_values")
            if allowed_values and value not in allowed_values:
                raise ValidationError(
                    f"Field '{field}' must be one of: {allowed_values}"
                )


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self):
        """Initialize rate limiter with request tracking."""
        self.requests: Dict[str, deque] = defaultdict(deque)
        self.logger = logging.getLogger(f"{__name__}.RateLimiter")

    def is_allowed(
        self, identifier: str, max_requests: int, window_minutes: int
    ) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            max_requests: Maximum requests in window
            window_minutes: Time window in minutes

        Returns:
            True if request is allowed
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)

        # Clean old requests outside the window
        user_requests = self.requests[identifier]
        while user_requests and user_requests[0] < window_start:
            user_requests.popleft()

        # Check if under limit
        if len(user_requests) >= max_requests:
            self.logger.warning(f"Rate limit exceeded for {identifier}")
            return False

        # Add current request
        user_requests.append(now)
        return True

    def reset_user(self, identifier: str) -> None:
        """Reset rate limit for specific user."""
        if identifier in self.requests:
            del self.requests[identifier]

    def cleanup_old_entries(self, max_age_hours: int = 24) -> int:
        """Clean up old rate limit entries."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        removed_count = 0

        for identifier in list(self.requests.keys()):
            user_requests = self.requests[identifier]

            # Remove old requests
            while user_requests and user_requests[0] < cutoff_time:
                user_requests.popleft()

            # Remove empty entries
            if not user_requests:
                del self.requests[identifier]
                removed_count += 1

        return removed_count


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(
    max_requests: int, window_minutes: int, identifier_func: Optional[Callable] = None
):
    """
    Decorator for rate limiting function calls.

    Args:
        max_requests: Maximum requests in window
        window_minutes: Time window in minutes
        identifier_func: Function to get unique identifier (defaults to IP)

    Raises:
        RateLimitError: If rate limit is exceeded
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request

            # Get identifier (IP address by default)
            if identifier_func:
                identifier = identifier_func()
            else:
                identifier = request.remote_addr or "unknown"

            if not _rate_limiter.is_allowed(identifier, max_requests, window_minutes):
                raise RateLimitError("Rate limit exceeded")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def generate_secure_token(length: int = 32) -> str:
    """
    Generate cryptographically secure random token.

    Args:
        length: Token length in bytes

    Returns:
        Hex-encoded secure token
    """
    return secrets.token_hex(length)


def hash_data(data: Union[str, bytes], algorithm: str = "sha256") -> str:
    """
    Hash data using specified algorithm.

    Args:
        data: Data to hash
        algorithm: Hash algorithm (sha256, sha512, md5)

    Returns:
        Hex-encoded hash
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    if algorithm == "sha256":
        return hashlib.sha256(data).hexdigest()
    elif algorithm == "sha512":
        return hashlib.sha512(data).hexdigest()
    elif algorithm == "md5":
        return hashlib.md5(data).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def safe_json_parse(json_string: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with error handling.

    Args:
        json_string: JSON string to parse
        default: Default value if parsing fails

    Returns:
        Parsed JSON data or default value
    """
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"JSON parse error: {e}")
        return default


def safe_json_dump(data: Any, indent: int = None, default: str = "{}") -> str:
    """
    Safely serialize data to JSON string.

    Args:
        data: Data to serialize
        indent: JSON indentation
        default: Default value if serialization fails

    Returns:
        JSON string or default value
    """
    try:
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger.warning(f"JSON serialization error: {e}")
        return default


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate string to maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append if truncated

    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def extract_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.

    Args:
        filename: Filename to process

    Returns:
        File extension (lowercase) or empty string
    """
    if not filename or "." not in filename:
        return ""

    return filename.split(".")[-1].lower()


def is_safe_path(path: str, base_path: str = None) -> bool:
    """
    Check if path is safe (no directory traversal).

    Args:
        path: Path to check
        base_path: Base path to restrict to

    Returns:
        True if path is safe
    """
    # Check for directory traversal attempts
    if ".." in path or path.startswith("/"):
        return False

    # Check against base path if provided
    if base_path:
        try:
            from pathlib import Path

            full_path = (Path(base_path) / path).resolve()
            base_resolved = Path(base_path).resolve()
            return str(full_path).startswith(str(base_resolved))
        except Exception:
            return False

    return True


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def parse_duration(duration_string: str) -> timedelta:
    """
    Parse duration string into timedelta.

    Args:
        duration_string: Duration like "1h30m", "2d", "45s"

    Returns:
        Parsed timedelta

    Raises:
        ValueError: If duration format is invalid
    """
    duration_string = duration_string.lower().strip()

    # Pattern for parsing durations like "1h30m45s", "2d", etc.
    pattern = r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?"
    match = re.match(pattern, duration_string)

    if not match:
        raise ValueError(f"Invalid duration format: {duration_string}")

    days, hours, minutes, seconds = match.groups()

    return timedelta(
        days=int(days or 0),
        hours=int(hours or 0),
        minutes=int(minutes or 0),
        seconds=int(seconds or 0),
    )


def get_client_ip(request) -> str:
    """
    Get client IP address from request, handling proxies.

    Args:
        request: Flask request object

    Returns:
        Client IP address
    """
    # Check for forwarded headers (behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to remote address
    return request.remote_addr or "unknown"


def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging/display.

    Args:
        data: Data to mask
        mask_char: Character to use for masking
        visible_chars: Number of characters to leave visible

    Returns:
        Masked string
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ""

    visible_end = data[-visible_chars:] if visible_chars > 0 else ""
    masked_part = mask_char * (len(data) - visible_chars)

    return masked_part + visible_end


class Timer:
    """Simple context manager for timing operations."""

    def __init__(self, name: str = "operation"):
        """Initialize timer with operation name."""
        self.name = name
        self.start_time = None
        self.end_time = None
        self.logger = logging.getLogger(f"{__name__}.Timer")

    def __enter__(self):
        """Start timing."""
        self.start_time = datetime.now(timezone.utc)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End timing and log results."""
        self.end_time = datetime.now(timezone.utc)
        duration = self.elapsed_ms

        if exc_type:
            self.logger.error(f"{self.name} failed after {duration}ms")
        else:
            self.logger.info(f"{self.name} completed in {duration}ms")

    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds."""
        if not self.start_time:
            return 0

        end_time = self.end_time or datetime.now(timezone.utc)
        delta = end_time - self.start_time
        return int(delta.total_seconds() * 1000)


# Utility functions for testing
def create_test_user_data(
    username: str = "testuser", role: str = "normal_user"
) -> Dict[str, Any]:
    """Create test user data for testing purposes."""
    return {
        "username": username,
        "email": f"{username}@example.com",
        "role": role,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def create_test_repository_data(
    name: str = "test_repo", language: str = "python"
) -> Dict[str, Any]:
    """Create test repository data for testing purposes."""
    return {
        "name": name,
        "description": f"Test repository for {language} code",
        "path": f"/tmp/{name}",
        "primary_language": language,
        "indexing_status": "indexed",
        "total_files": 42,
        "indexed_files": 42,
        "total_lines": 1337,
    }


def create_mock_search_results(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Create mock search results for testing."""
    results = []

    for i in range(count):
        results.append(
            {
                "file_path": f"src/module_{i}.py",
                "function_name": f"function_{i}",
                "line_number": (i + 1) * 10,
                "code_snippet": f"def function_{i}():\n    return '{query} result {i}'",
                "relevance_score": 1.0 - (i * 0.1),
                "description": f"Function that handles {query} - result {i}",
            }
        )

    return results
