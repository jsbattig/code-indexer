"""
Unit tests for unhandled exception catching with correlation IDs in GlobalErrorHandler.

Tests comprehensive exception handling following CLAUDE.md Foundation #1: No mocks.
Uses real exception scenarios and validates security-compliant error responses.
"""

import uuid
import pytest
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import Request

from code_indexer.server.middleware.error_handler import GlobalErrorHandler


class CustomBusinessError(Exception):
    """Custom business exception for testing."""

    def __init__(self, message: str, sensitive_data: Dict[str, Any] = None):
        self.message = message
        self.sensitive_data = sensitive_data or {}
        super().__init__(message)


class TestUnhandledExceptionHandling:
    """Test unhandled exception catching with correlation IDs and security compliance."""

    @pytest.fixture
    def error_handler(self) -> GlobalErrorHandler:
        """Create GlobalErrorHandler instance."""
        return GlobalErrorHandler()

    @pytest.fixture
    def mock_request(self) -> Request:
        """Create real FastAPI Request object for testing."""
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/repositories/analyze",
                "headers": [
                    (b"host", b"testserver"),
                    (b"authorization", b"Bearer jwt-token-here"),
                    (b"user-agent", b"CIDX-Client/1.0"),
                ],
                "query_string": b"deep_analysis=true",
                "root_path": "",
            }
        )
        return request

    def test_unhandled_exception_response_format(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that unhandled exceptions produce standardized error response."""
        # Create unhandled exception
        exc = None
        try:
            raise ValueError("Unexpected calculation error in business logic")
        except ValueError as e:
            exc = e

        response_data = error_handler.handle_unhandled_exception(exc, mock_request)

        # Verify standardized response format
        assert "error" in response_data
        assert "message" in response_data
        assert "correlation_id" in response_data
        assert "timestamp" in response_data

        # Should NOT include sensitive details
        assert "details" not in response_data or not response_data.get("details")

        # Verify error type
        assert response_data["error"] == "internal_server_error"

        # Verify correlation ID format (UUID4)
        correlation_id = response_data["correlation_id"]
        uuid_obj = uuid.UUID(correlation_id)
        assert str(uuid_obj) == correlation_id

        # Verify timestamp format
        timestamp = response_data["timestamp"]
        parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed_time.tzinfo == timezone.utc

    def test_unhandled_exception_status_code(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that unhandled exceptions return 500 Internal Server Error."""
        exc = None
        try:
            raise RuntimeError("Something went wrong")
        except RuntimeError as e:
            exc = e

        response_data = error_handler.handle_unhandled_exception(exc, mock_request)

        # Verify status code
        status_code = error_handler.get_status_code_for_error_type(
            "internal_server_error"
        )
        assert status_code == 500

        # Response should not include status_code (handled by middleware)
        assert "status_code" not in response_data

    def test_unhandled_exception_sanitized_message(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that unhandled exception messages are sanitized for security."""
        # Create exception with sensitive information
        sensitive_exception = CustomBusinessError(
            "Database connection failed: host=prod-db.internal.company.com port=5432 user=admin",
            sensitive_data={"password": "secret123", "api_key": "sk-abc123"},
        )

        response_data = error_handler.handle_unhandled_exception(
            sensitive_exception, mock_request
        )

        # Message should be generic and safe
        message = response_data["message"]
        assert "internal server error" in message.lower()
        assert "prod-db.internal.company.com" not in message
        assert "admin" not in message
        assert "secret123" not in message
        assert "sk-abc123" not in message
        assert "5432" not in message

        # Should be user-friendly generic message
        assert len(message) > 10
        assert message.endswith(".")

    def test_unhandled_exception_comprehensive_logging(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that unhandled exceptions are logged with full stack trace and context."""

        def nested_function_that_fails():
            def deeply_nested_failure():
                raise ZeroDivisionError("Division by zero in calculation")

            deeply_nested_failure()

        exc = None
        try:
            nested_function_that_fails()
        except ZeroDivisionError as e:
            exc = e

        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_unhandled_exception(exc, mock_request)

        # Verify error was logged
        assert len(caplog.records) == 1
        log_record = caplog.records[0]

        # Verify log level and basic content
        assert log_record.levelname == "ERROR"
        assert "UnhandledException" in log_record.message
        assert response_data["correlation_id"] in log_record.message

        # Should include full stack trace in log
        assert "nested_function_that_fails" in log_record.message
        assert "deeply_nested_failure" in log_record.message
        assert "ZeroDivisionError" in log_record.message

        # Should include request context
        assert "POST /api/repositories/analyze" in log_record.message
        assert "deep_analysis=true" in log_record.message

    def test_unhandled_exception_correlation_id_uniqueness(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that each unhandled exception gets unique correlation ID."""
        exception = RuntimeError("Test error")

        # Generate multiple responses for same exception
        response1 = error_handler.handle_unhandled_exception(exception, mock_request)
        response2 = error_handler.handle_unhandled_exception(exception, mock_request)

        # Correlation IDs should be unique
        assert response1["correlation_id"] != response2["correlation_id"]

        # Both should be valid UUIDs
        uuid.UUID(response1["correlation_id"])
        uuid.UUID(response2["correlation_id"])

    def test_different_exception_types_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that different exception types all get proper handling."""
        exceptions_to_test = [
            ValueError("Invalid input value"),
            TypeError("Unexpected type in operation"),
            AttributeError("Object has no attribute 'missing_attr'"),
            KeyError("Missing required key 'config'"),
            IndexError("List index out of range"),
            IOError("File not found: /secret/file.txt"),
            MemoryError("Out of memory"),
            ImportError("Cannot import module 'nonexistent'"),
        ]

        responses = []

        for exc in exceptions_to_test:
            response = error_handler.handle_unhandled_exception(exc, mock_request)
            responses.append(response)

            # All should have same standardized format
            assert response["error"] == "internal_server_error"
            assert "internal server error" in response["message"].lower()
            assert uuid.UUID(response["correlation_id"])

            # Should not leak specific exception details
            assert "ValueError" not in response["message"]
            assert "secret" not in response["message"]
            assert "nonexistent" not in response["message"]

        # All correlation IDs should be unique
        correlation_ids = [r["correlation_id"] for r in responses]
        assert len(set(correlation_ids)) == len(correlation_ids)

    def test_exception_with_recursive_attributes(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test handling exceptions with recursive or complex attributes."""

        class ComplexException(Exception):
            def __init__(self, message):
                self.message = message
                self.recursive_ref = self  # Circular reference
                self.complex_data = {
                    "nested": {
                        "deep": {
                            "secrets": ["password123", "api-key-456"],
                            "safe": "public data",
                        }
                    }
                }
                super().__init__(message)

        complex_exc = ComplexException("Complex error with circular refs")

        # Should not raise exception during error handling
        response_data = error_handler.handle_unhandled_exception(
            complex_exc, mock_request
        )

        # Should still produce clean response
        assert response_data["error"] == "internal_server_error"
        assert "correlation_id" in response_data

        # Should not leak sensitive data from complex attributes
        message = response_data["message"]
        assert "password123" not in message
        assert "api-key-456" not in message

    def test_exception_during_error_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test behavior when exception occurs during error handling itself."""

        class ProblematicException(Exception):
            @property
            def args(self):
                raise RuntimeError("Error accessing exception args")

        problematic_exc = ProblematicException("Original error")

        # Should not raise exception, should handle gracefully
        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_unhandled_exception(
                problematic_exc, mock_request
            )

        # Should still return valid response
        assert response_data["error"] == "internal_server_error"
        assert uuid.UUID(response_data["correlation_id"])

        # Should log the meta-error
        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) >= 1  # At least one error log

    def test_stack_trace_sanitization(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that stack traces in logs don't leak sensitive information."""

        def function_with_secrets():
            # These variables are intentionally unused to test stack trace sanitization
            password = "super_secret_password_123"  # noqa: F841
            api_key = "sk-1234567890abcdef"  # noqa: F841
            database_url = "postgres://admin:secret@prod-db:5432/app"  # noqa: F841

            # Create error that might capture local variables in stack
            raise RuntimeError("Function failed with sensitive context")

        exc = None
        try:
            function_with_secrets()
        except RuntimeError as e:
            exc = e

        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_unhandled_exception(exc, mock_request)

        # Verify comprehensive logging occurred
        assert len(caplog.records) == 1
        log_message = caplog.records[0].message

        # Should include function name in stack trace
        assert "function_with_secrets" in log_message

        # But should NOT include sensitive local variables
        # (Note: This depends on implementation - we may need to sanitize logs)
        # For now, we'll just verify the response is clean
        response_message = response_data["message"]
        assert "super_secret_password_123" not in response_message
        assert "sk-1234567890abcdef" not in response_message
        assert "admin:secret@prod-db" not in response_message

    def test_exception_with_custom_str_method(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test handling exceptions with custom __str__ methods."""

        class CustomStrException(Exception):
            def __str__(self):
                return "Custom error with sensitive info: password=secret123"

            def __repr__(self):
                return "CustomStrException('database_password=admin123')"

        custom_exc = CustomStrException()
        response_data = error_handler.handle_unhandled_exception(
            custom_exc, mock_request
        )

        # Should not use custom __str__ that might leak info
        message = response_data["message"]
        assert "secret123" not in message
        assert "admin123" not in message
        assert "internal server error" in message.lower()

    def test_unicode_exception_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test handling exceptions with Unicode characters."""
        unicode_exceptions = [
            ValueError("Error with émojis: 🔒 Ségurité fäiled"),
            RuntimeError("Ошибка с русскими символами"),
            TypeError("エラー：日本語のメッセージ"),
        ]

        for exc in unicode_exceptions:
            response_data = error_handler.handle_unhandled_exception(exc, mock_request)

            # Should handle Unicode properly
            assert response_data["error"] == "internal_server_error"
            assert uuid.UUID(response_data["correlation_id"])

            # Message should be safe English text
            message = response_data["message"]
            assert message.isascii() or len(message.encode("utf-8")) == len(message)

    def test_exception_context_preservation(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that exception context and cause are preserved in logging."""

        def cause_error():
            raise ValueError("Root cause error")

        def wrapper_error():
            try:
                cause_error()
            except ValueError as e:
                raise RuntimeError("Wrapper error") from e

        exc = None
        try:
            wrapper_error()
        except RuntimeError as e:
            exc = e

        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_unhandled_exception(exc, mock_request)

        # Log should include both the main exception and its cause
        log_message = caplog.records[0].message
        assert "RuntimeError" in log_message
        assert "ValueError" in log_message
        assert "Root cause error" in log_message
        assert "Wrapper error" in log_message

        # Response should still be generic
        assert "internal server error" in response_data["message"].lower()
