"""
Data sanitization middleware for CIDX Server.

Sanitizes sensitive information from error messages and logs following
CLAUDE.md Foundation #1: No mocks - real sanitization with actual pattern matching.
"""

import re
import logging
from typing import Dict, Any, Optional
from fastapi import Request

from ..models.error_models import ErrorHandlerConfiguration

# Configure logger for this module
logger = logging.getLogger(__name__)


class SensitiveDataSanitizer:
    """
    Sanitizes sensitive information from error messages and logs.

    Follows CLAUDE.md Foundation #1: No mocks - real sanitization with actual pattern matching.
    Prevents information leakage while maintaining useful debugging information.
    """

    def __init__(self, configuration: Optional[ErrorHandlerConfiguration] = None):
        """Initialize sanitizer with configuration rules."""
        self.config = configuration or ErrorHandlerConfiguration()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for better performance."""
        self._compiled_rules = []
        for rule in self.config.sanitization_rules:
            try:
                flags = 0 if rule.case_sensitive else re.IGNORECASE
                pattern = re.compile(rule.pattern, flags)
                self._compiled_rules.append(
                    (pattern, rule.replacement, rule.field_names)
                )
            except re.error as e:
                logger.warning(
                    f"Invalid sanitization regex pattern '{rule.pattern}': {e}"
                )

    def sanitize_string(self, text: str) -> str:
        """
        Sanitize sensitive data from a string.

        Args:
            text: String that may contain sensitive information

        Returns:
            Sanitized string with sensitive data replaced
        """
        if not text or not isinstance(text, str):
            return text

        sanitized = text
        for pattern, replacement, _ in self._compiled_rules:
            sanitized = pattern.sub(replacement, sanitized)

        return sanitized

    def sanitize_field_value(self, field_name: str, value: Any) -> Any:
        """
        Sanitize field value based on field name and sanitization rules.

        Args:
            field_name: Name of the field
            value: Value to potentially sanitize

        Returns:
            Sanitized value or original value if not sensitive
        """
        # Sensitive field names that should always be redacted
        sensitive_field_names = {
            "password",
            "pwd",
            "pass",
            "secret",
            "token",
            "key",
            "api_key",
            "apikey",
            "auth_token",
            "access_token",
            "refresh_token",
            "bearer",
            "authorization",
            "credential",
            "private_key",
            "secret_key",
            "jwt_secret",
        }

        field_lower = field_name.lower()

        # Check if field name indicates sensitive data
        if any(sensitive in field_lower for sensitive in sensitive_field_names):
            return "[REDACTED]"

        # Apply pattern-based sanitization to field values
        if isinstance(value, str):
            # Check field-specific rules
            for pattern, replacement, field_names in self._compiled_rules:
                if field_names and field_name not in field_names:
                    continue
                if pattern.search(value):
                    return "[REDACTED]"

            # Apply general sanitization
            sanitized = self.sanitize_string(value)
            if sanitized != value:
                return "[REDACTED]"

        return value

    def sanitize_data_structure(self, data: Any) -> Any:
        """
        Recursively sanitize a data structure (dict, list, etc.).

        Args:
            data: Data structure to sanitize

        Returns:
            Sanitized copy of the data structure
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                sanitized_value = self.sanitize_field_value(key, value)
                if sanitized_value == "[REDACTED]":
                    sanitized[key] = sanitized_value
                else:
                    sanitized[key] = self.sanitize_data_structure(value)
            return sanitized
        elif isinstance(data, list):
            return [self.sanitize_data_structure(item) for item in data]
        elif isinstance(data, str):
            return self.sanitize_string(data)
        else:
            return data

    def sanitize_request_info(self, request: Request) -> Dict[str, Any]:
        """
        Extract and sanitize request information for logging.

        Args:
            request: FastAPI request object

        Returns:
            Dictionary with sanitized request information
        """
        try:
            # Basic request info
            request_info = {
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.url.query) if request.url.query else None,
            }

            # Sanitize query parameters
            if request_info["query_params"]:
                request_info["query_params"] = self.sanitize_string(
                    request_info["query_params"]
                )

            # Sanitize and include relevant headers (exclude sensitive ones)
            safe_headers = {}
            for name, value in request.headers.items():
                name_lower = name.lower()
                if name_lower in ["authorization", "cookie", "x-api-key", "api-key"]:
                    safe_headers[name] = "[REDACTED]"
                else:
                    safe_headers[name] = self.sanitize_string(value)

            request_info["headers"] = safe_headers

            return request_info

        except Exception as e:
            logger.warning(f"Error sanitizing request info: {e}")
            return {"method": "UNKNOWN", "path": "UNKNOWN"}
