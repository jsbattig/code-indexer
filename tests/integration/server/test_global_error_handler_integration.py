"""
Integration tests for GlobalErrorHandler middleware with FastAPI app.

Tests complete error handling flow with real FastAPI endpoints following CLAUDE.md Foundation #1: No mocks.
Validates end-to-end error processing through the entire middleware stack.
"""

import uuid
import json
import pytest
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

from code_indexer.server.middleware.error_handler import GlobalErrorHandler
from code_indexer.server.models.error_models import (
    DatabaseRetryableError,
    DatabasePermanentError,
)


class TestIntegrationData(BaseModel):
    """Test model for integration testing."""

    name: str = Field(..., min_length=3, max_length=50)
    age: int = Field(..., ge=0, le=150)
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")


class TestGlobalErrorHandlerIntegration:
    """Integration tests for GlobalErrorHandler middleware with FastAPI."""

    @pytest.fixture
    def test_app(self) -> FastAPI:
        """Create FastAPI test app with global error handler middleware."""
        app = FastAPI(title="Test App", version="1.0.0")

        # Add global error handler middleware
        global_error_handler = GlobalErrorHandler()
        app.add_middleware(GlobalErrorHandler)

        # Add exception handlers for validation errors that FastAPI catches before middleware
        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(
            request: Request, exc: RequestValidationError
        ):
            error_data = global_error_handler.handle_validation_error(exc, request)
            return global_error_handler._create_error_response(error_data)

        # Test endpoints for various error scenarios
        @app.post("/test/validation")
        async def test_validation_endpoint(data: TestIntegrationData):
            return {"message": "success", "data": data}

        @app.get("/test/database-error")
        async def test_database_error():
            raise DatabaseRetryableError("Connection timeout")

        @app.get("/test/permanent-database-error")
        async def test_permanent_database_error():
            raise DatabasePermanentError("Invalid schema")

        @app.get("/test/unhandled-exception")
        async def test_unhandled_exception():
            raise ValueError("Unexpected error in business logic")

        @app.get("/test/http-exception")
        async def test_http_exception():
            raise HTTPException(status_code=404, detail="Resource not found")

        @app.get("/test/sensitive-data-error")
        async def test_sensitive_data_error():
            # Simulate error with sensitive information
            database_url = "postgres://admin:password123@internal-db:5432/app"
            api_key = "sk-live_1234567890abcdef"
            raise RuntimeError(
                f"Connection failed to {database_url} with key {api_key}"
            )

        return app

    @pytest.fixture
    def client(self, test_app: FastAPI) -> TestClient:
        """Create test client for the FastAPI app."""
        return TestClient(test_app)

    def test_validation_error_integration(self, client: TestClient):
        """Test complete validation error handling through middleware."""
        # Send invalid data to trigger validation error
        invalid_data = {
            "name": "ab",  # Too short
            "age": 200,  # Too high
            "email": "not-an-email",  # Invalid format
        }

        response = client.post("/test/validation", json=invalid_data)

        # Verify error response format
        assert response.status_code == 400
        response_data = response.json()

        # Verify standardized error response format
        assert "error" in response_data
        assert "message" in response_data
        assert "correlation_id" in response_data
        assert "timestamp" in response_data
        assert "details" in response_data

        assert response_data["error"] == "validation_error"
        assert "validation failed" in response_data["message"].lower()

        # Verify correlation ID is valid UUID
        uuid.UUID(response_data["correlation_id"])

        # Verify timestamp format
        datetime.fromisoformat(response_data["timestamp"].replace("Z", "+00:00"))

        # Verify field-level error details
        field_errors = response_data["details"]["field_errors"]
        assert len(field_errors) == 3

        # Verify all expected fields have errors
        error_fields = {error["field"] for error in field_errors}
        assert "name" in error_fields
        assert "age" in error_fields
        assert "email" in error_fields

    def test_database_error_integration(self, client: TestClient):
        """Test database error handling with retry logic through middleware."""
        response = client.get("/test/database-error")

        # Should return 503 Service Unavailable for retryable database errors
        assert response.status_code == 503
        response_data = response.json()

        # Verify standardized error response
        assert response_data["error"] == "service_unavailable"
        assert "temporarily unavailable" in response_data["message"].lower()
        assert "correlation_id" in response_data
        assert "timestamp" in response_data
        assert "retry_after" in response_data

        # Verify Retry-After header
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0

    def test_permanent_database_error_integration(self, client: TestClient):
        """Test permanent database error handling through middleware."""
        response = client.get("/test/permanent-database-error")

        # Should return 500 Internal Server Error for permanent database errors
        assert response.status_code == 500
        response_data = response.json()

        # Verify standardized error response
        assert response_data["error"] == "internal_server_error"
        assert "server error" in response_data["message"].lower()
        assert "correlation_id" in response_data
        assert "timestamp" in response_data
        assert "retry_after" not in response_data  # No retry for permanent errors

        # Should not have Retry-After header
        assert "Retry-After" not in response.headers

    def test_unhandled_exception_integration(self, client: TestClient):
        """Test unhandled exception processing through middleware."""
        response = client.get("/test/unhandled-exception")

        # Should return 500 Internal Server Error
        assert response.status_code == 500
        response_data = response.json()

        # Verify standardized error response
        assert response_data["error"] == "internal_server_error"
        assert "internal server error" in response_data["message"].lower()
        assert "correlation_id" in response_data
        assert "timestamp" in response_data

        # Should not contain sensitive information from the original exception
        assert "business logic" not in response_data["message"]
        assert "ValueError" not in response_data["message"]

    def test_http_exception_integration(self, client: TestClient):
        """Test FastAPI HTTPException handling through middleware."""
        response = client.get("/test/http-exception")

        # Should preserve original status code
        assert response.status_code == 404
        response_data = response.json()

        # Verify standardized error response format
        assert response_data["error"] == "not_found_error"
        assert response_data["message"] == "Resource not found"
        assert "correlation_id" in response_data
        assert "timestamp" in response_data

    def test_sensitive_data_sanitization_integration(self, client: TestClient):
        """Test end-to-end sensitive data sanitization through middleware."""
        response = client.get("/test/sensitive-data-error")

        # Should return 500 Internal Server Error
        assert response.status_code == 500
        response_data = response.json()

        # Response should not contain sensitive information
        response_str = json.dumps(response_data)
        assert "password123" not in response_str
        assert "admin:password123" not in response_str
        assert "internal-db" not in response_str
        assert "sk-live_1234567890abcdef" not in response_str

        # Should be generic error message
        assert "internal server error" in response_data["message"].lower()
        assert "correlation_id" in response_data

    def test_successful_request_passes_through(self, client: TestClient):
        """Test that successful requests pass through middleware unchanged."""
        valid_data = {"name": "John Doe", "age": 30, "email": "john@example.com"}

        response = client.post("/test/validation", json=valid_data)

        # Should pass through successfully
        assert response.status_code == 200
        response_data = response.json()

        # Should get the normal endpoint response, not error format
        assert response_data["message"] == "success"
        assert "data" in response_data
        assert response_data["data"]["name"] == "John Doe"
        assert response_data["data"]["age"] == 30
        assert response_data["data"]["email"] == "john@example.com"

        # Should not have error response fields
        assert "error" not in response_data
        assert "correlation_id" not in response_data

    def test_correlation_id_uniqueness_across_requests(self, client: TestClient):
        """Test that different requests get unique correlation IDs."""
        correlation_ids = set()

        # Make multiple error requests
        for _ in range(5):
            response = client.get("/test/unhandled-exception")
            assert response.status_code == 500
            correlation_id = response.json()["correlation_id"]
            correlation_ids.add(correlation_id)

        # All correlation IDs should be unique
        assert len(correlation_ids) == 5

        # All should be valid UUIDs
        for correlation_id in correlation_ids:
            uuid.UUID(correlation_id)

    def test_error_response_content_type(self, client: TestClient):
        """Test that error responses have correct content type."""
        response = client.get("/test/unhandled-exception")

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"

    def test_multiple_validation_errors_consolidated(self, client: TestClient):
        """Test that multiple validation errors are properly consolidated."""
        # Send data that violates multiple validation rules
        invalid_data = {
            "name": "",  # Required and min_length
            "age": -1,  # ge constraint
            "email": "",  # Required and pattern
        }

        response = client.post("/test/validation", json=invalid_data)
        assert response.status_code == 400

        response_data = response.json()
        field_errors = response_data["details"]["field_errors"]

        # Should have one error per field, even if multiple rules violated
        field_names = [error["field"] for error in field_errors]
        assert len(set(field_names)) == len(field_names)  # No duplicates

        # Should have errors for all three fields
        assert "name" in field_names
        assert "age" in field_names
        assert "email" in field_names

    def test_error_handler_with_custom_headers(self, client: TestClient):
        """Test error handler preserves important response headers."""
        response = client.get("/test/database-error")

        assert response.status_code == 503

        # Should have Retry-After header for service unavailable
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

        # Should have standard headers
        assert "content-type" in response.headers
        assert response.headers["content-type"] == "application/json"

    def test_middleware_order_independence(self, client: TestClient):
        """Test that error handler works regardless of other middleware."""
        # Error should be caught even if it occurs after other processing
        response = client.get("/test/unhandled-exception")

        assert response.status_code == 500
        response_data = response.json()

        # Should still have standardized format
        assert "error" in response_data
        assert "correlation_id" in response_data
        assert response_data["error"] == "internal_server_error"

    def test_large_validation_error_handling(self, client: TestClient):
        """Test handling of validation errors with large data."""
        # Create data with very long strings to test sanitization
        invalid_data = {
            "name": "x" * 1000,  # Way too long
            "age": 999,  # Way too high
            "email": "y" * 500 + "@test.com",  # Very long email
        }

        response = client.post("/test/validation", json=invalid_data)
        assert response.status_code == 400

        response_data = response.json()

        # Should handle large validation errors gracefully
        assert "error" in response_data
        assert (
            len(str(response_data)) < 10000
        )  # Response shouldn't be excessively large

        # Sensitive data should be sanitized even in large fields
        field_errors = response_data["details"]["field_errors"]
        for error in field_errors:
            rejected_value = str(error.get("rejected_value", ""))
            # Very long values should be truncated or redacted
            assert len(rejected_value) < 1000
