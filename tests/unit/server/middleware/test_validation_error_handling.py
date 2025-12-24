"""
Unit tests for ValidationError handling in GlobalErrorHandler.

Tests standardized validation error responses following CLAUDE.md Foundation #1: No mocks.
Uses real FastAPI Request objects and Pydantic validation errors.
"""

import uuid
import pytest
from datetime import datetime, timezone
from pydantic import BaseModel, ValidationError as PydanticValidationError, Field
from fastapi import Request
from fastapi.testclient import TestClient

from code_indexer.server.middleware.error_handler import GlobalErrorHandler


class ValidationTestModel(BaseModel):
    """Test model for validation error testing."""

    name: str = Field(..., min_length=3, max_length=50)
    age: int = Field(..., ge=0, le=150)
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")


class TestValidationErrorHandling:
    """Test ValidationError handling with standardized response format."""

    @pytest.fixture
    def error_handler(self) -> GlobalErrorHandler:
        """Create GlobalErrorHandler instance."""
        return GlobalErrorHandler()

    @pytest.fixture
    def mock_request(self) -> Request:
        """Create real FastAPI Request object for testing."""
        from fastapi import FastAPI

        app = FastAPI()
        client = TestClient(app)

        # Create a real request object
        with client:
            client.get("/test")  # This creates the request context
            # Access the request from the test client context
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/test",
                    "headers": [(b"host", b"testserver")],
                    "query_string": b"",
                    "root_path": "",
                }
            )
            return request

    def test_validation_error_response_format(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that ValidationError produces standardized response format."""
        # Create real Pydantic validation error
        validation_error = None
        try:
            ValidationTestModel(name="", age=-1, email="invalid-email")
            pytest.fail("Expected PydanticValidationError was not raised")
        except PydanticValidationError as e:
            validation_error = e

        # Process validation error through handler
        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )

        # Verify standardized response format
        assert "error" in response_data
        assert "message" in response_data
        assert "details" in response_data
        assert "correlation_id" in response_data
        assert "timestamp" in response_data

        # Verify error type
        assert response_data["error"] == "validation_error"

        # Verify correlation ID format (UUID4)
        correlation_id = response_data["correlation_id"]
        uuid_obj = uuid.UUID(correlation_id)
        assert str(uuid_obj) == correlation_id

        # Verify timestamp format (ISO 8601)
        timestamp = response_data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Verify field-level error details
        details = response_data["details"]
        assert isinstance(details, dict)
        assert "field_errors" in details
        field_errors = details["field_errors"]

        # Should contain errors for all three fields
        assert len(field_errors) == 3
        field_names = [error["field"] for error in field_errors]
        assert "name" in field_names
        assert "age" in field_names
        assert "email" in field_names

    def test_validation_error_field_details(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that field-level validation errors contain proper details."""
        validation_error = None
        try:
            ValidationTestModel(name="ab", age=200, email="not-an-email")
            pytest.fail("Expected PydanticValidationError was not raised")
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )
        field_errors = response_data["details"]["field_errors"]

        # Verify field error structure
        for field_error in field_errors:
            assert "field" in field_error
            assert "message" in field_error
            assert "rejected_value" in field_error
            assert "error_type" in field_error

            # Verify field-specific error messages (Pydantic v2 format)
            if field_error["field"] == "name":
                assert "string_too_short" in field_error["error_type"]
                assert field_error["rejected_value"] == "ab"
            elif field_error["field"] == "age":
                assert (
                    "less_than_equal" in field_error["error_type"]
                    or "greater_than_equal" in field_error["error_type"]
                )
                assert field_error["rejected_value"] == 200
            elif field_error["field"] == "email":
                assert "string_pattern_mismatch" in field_error["error_type"]
                assert field_error["rejected_value"] == "not-an-email"

    def test_validation_error_user_friendly_message(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that validation errors have user-friendly messages."""
        validation_error = None
        try:
            ValidationTestModel(name="", age=-1, email="invalid")
            pytest.fail("Expected PydanticValidationError was not raised")
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )

        # Main message should be user-friendly
        message = response_data["message"]
        assert "validation failed" in message.lower()
        assert "request" in message.lower()

        # Field error messages should be readable
        field_errors = response_data["details"]["field_errors"]
        for field_error in field_errors:
            message = field_error["message"]
            assert len(message) > 0
            assert not message.startswith("ValidationError")  # Not raw Pydantic message

    def test_validation_error_status_code(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that validation errors return 400 Bad Request status."""
        validation_error = None
        try:
            ValidationTestModel(name="", age=-1)
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )

        # Should not include status_code in response data (handled by middleware)
        assert "status_code" not in response_data

        # Status code should be accessible through the handler
        status_code = error_handler.get_status_code_for_error_type("validation_error")
        assert status_code == 400

    def test_validation_error_logging(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that validation errors are properly logged with request context."""
        validation_error = None
        try:
            ValidationTestModel(name="x", age=999, email="bad")
        except PydanticValidationError as e:
            validation_error = e

        with caplog.at_level("WARNING"):
            response_data = error_handler.handle_validation_error(
                validation_error, mock_request
            )

        # Verify error was logged
        assert len(caplog.records) == 1
        log_record = caplog.records[0]

        # Verify log level and content
        assert log_record.levelname == "WARNING"
        assert "ValidationError" in log_record.message
        assert response_data["correlation_id"] in log_record.message

        # Verify request context in log
        assert "GET" in log_record.message or "get" in log_record.message.lower()
        assert "/test" in log_record.message

    def test_multiple_validation_errors_same_field(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test handling multiple validation errors for the same field."""
        # This should trigger multiple validation rules for the name field
        validation_error = None
        try:
            ValidationTestModel(
                name="x" * 100, age=50, email="valid@email.com"
            )  # Too long name
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )
        field_errors = response_data["details"]["field_errors"]

        # Should handle multiple errors for same field
        name_errors = [e for e in field_errors if e["field"] == "name"]
        assert len(name_errors) == 1  # Should consolidate multiple errors per field

        # Error message should mention the specific constraint
        name_error = name_errors[0]
        assert "string_too_long" in name_error["error_type"]

    def test_nested_validation_error_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test validation error handling for nested object validation."""

        class NestedModel(BaseModel):
            user: ValidationTestModel
            active: bool

        validation_error = None
        try:
            NestedModel(user={"name": "", "age": -1, "email": "bad"}, active="not_bool")
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )
        field_errors = response_data["details"]["field_errors"]

        # Should handle nested field errors with proper field paths
        field_paths = [error["field"] for error in field_errors]
        nested_fields = [path for path in field_paths if "user." in path]

        # Should have nested field references
        assert len(nested_fields) >= 3  # user.name, user.age, user.email errors
        assert any("user.name" in path for path in field_paths)
        assert any("user.age" in path for path in field_paths)
        assert any("user.email" in path for path in field_paths)

    def test_validation_error_correlation_id_uniqueness(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that each validation error gets a unique correlation ID."""
        validation_error = None
        try:
            ValidationTestModel(name="", age=-1)
        except PydanticValidationError as e:
            validation_error = e

        # Generate multiple responses for the same error
        response1 = error_handler.handle_validation_error(
            validation_error, mock_request
        )
        response2 = error_handler.handle_validation_error(
            validation_error, mock_request
        )

        # Correlation IDs should be unique
        assert response1["correlation_id"] != response2["correlation_id"]

        # Both should be valid UUIDs
        uuid.UUID(response1["correlation_id"])
        uuid.UUID(response2["correlation_id"])

    def test_validation_error_timestamp_accuracy(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that validation error timestamps are accurate and recent."""
        before_time = datetime.now(timezone.utc)

        validation_error = None
        try:
            ValidationTestModel(name="", age=-1)
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )
        after_time = datetime.now(timezone.utc)

        # Parse timestamp
        timestamp_str = response_data["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # Timestamp should be between before and after
        assert before_time <= timestamp <= after_time

        # Should be in UTC
        assert timestamp.tzinfo == timezone.utc
